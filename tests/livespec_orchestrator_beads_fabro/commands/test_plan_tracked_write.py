"""The chain-routed write path, at the refusals and retries a writer cannot reach.

`tests/integration/test_plan_result_budget_scenario147.py` binds the scenario
end to end over the three public writers. This module covers what that tier
cannot produce: a chain in a state no ordinary sequence creates (a fork, an
unreadable record), a concurrent writer winning between the read and the commit,
and the retry that must write NOTHING.

The retry case is the one worth reading before editing. It asserts the HANDOFF
COMMENT COUNT and not just the returned value — a retry that re-appended its
entry would return a perfectly correct idempotent result while duplicating the
handoff the clause forbids, so a test reading only the return value would pass
against exactly the defect. The count filters out `plan-progress-event`
comments, because the chain writes one of those per transition and a filter that
counted them could not tell a duplicated handoff from a recorded epoch.

THE EXHAUSTING RETRY IS THE CASE THAT DISCRIMINATES THE ORDER OF THE SEQUENCE,
and it is why the plain retry above is not sufficient on its own. That one is
answered identically whether the recovery runs before the obligation decision
or after it, because a budget with units left refuses nothing — so it passes
against a build in which the recovery is unreachable for the one retry that
needs it most. The retry of the handoff that consumed the FINAL unit is the
shape where the two orders disagree: the decision ladder reads the observed
head, whose consumed count already equals `max_handoffs`, and refuses the write
as expired before the operation identity is ever consulted. Its control — a
DIFFERENT operation identity at that same exhausted budget — is what keeps the
fix from being "stop grading expiry": one refusal must survive, and only the
pair says which.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import _plan_tracked_write
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain import (
    RECOVERED_FROM_PROGRESS_EVENT,
    ChainHead,
    CommittedTransition,
    read_chain_head,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import (
    ChainFinding,
    chain_fork_finding,
    receipt_without_event_finding,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import (
    AuthorityState,
    TransitionPayload,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import (
    PLAN_PROGRESS_PREFIX,
    chain_cache_metadata,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import create_token
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    NEXT_ACTION_METADATA_KEY,
    NextAction,
    plan_record_metadata,
)
from livespec_orchestrator_beads_fabro.commands._plan_next_action_validation import (
    NextActionRefusal,
)
from livespec_orchestrator_beads_fabro.commands._plan_recovery import CausalRecovery
from livespec_orchestrator_beads_fabro.commands._plan_tracked_write import (
    TrackedWrite,
    TrackedWriteRequest,
    commit_tracked_write,
    derived_operation_id,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_PROJECT_NAME = "repo"
_EPIC_ID = "bd-ib-trackedwrite"
_TARGET_ID = "bd-ib-trackedtarget"
_DEADLINE = "2026-10-20T09:00:00Z"
_NOW = "2026-10-13T09:00:00Z"
_TOKEN_A = "chain-record-a"
_TOKEN_B = "chain-record-b"
_TOKEN_Z = "chain-record-z"
_RESULT: dict[str, object] = {
    "repo": _PROJECT_NAME,
    "item_status": {"item_id": _TARGET_ID, "status": "done"},
}


@pytest.fixture(autouse=True)
def _hermetic_backend(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _fake(*, config: StoreConfig) -> FakeBeadsClient:
    client = make_beads_client(config=config)
    assert isinstance(client, FakeBeadsClient)
    return client


def _action(*, max_handoffs: int = 5) -> NextAction:
    return NextAction(
        kind="impl",
        ref=_TARGET_ID,
        text="Keep going.",
        required_result=_RESULT,
        budget={"deadline": _DEADLINE, "max_handoffs": max_handoffs},
    )


def _seed(*, tmp_path: Path, with_chain: bool = True) -> StoreConfig:
    repo = tmp_path / _PROJECT_NAME
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    config = store_config(repo=repo)
    fake = _fake(config=config)
    for issue_id, status in ((_EPIC_ID, "active"), (_TARGET_ID, "ready")):
        _ = fake.create_issue(
            draft=IssueDraft(
                issue_id=issue_id,
                issue_type="epic" if issue_id == _EPIC_ID else "feature",
                title=issue_id,
                description="Definition of Done\n\n- A thing holds.",
                assignee=None,
                created_at="2026-10-13T08:00:00Z",
                metadata={"rank": "a0"},
            )
        )
        fake.update_issue(issue_id=issue_id, status=status)
    if with_chain:
        genesis = create_token(client=fake)
        fake.update_issue(
            issue_id=_EPIC_ID,
            metadata=chain_cache_metadata(
                existing_metadata={"rank": "a0"},
                latest_closed=None,
                current=genesis,
            ),
        )
    return config


def _request(
    *,
    config: StoreConfig,
    is_handoff: bool = False,
    operation_id: str | None = None,
    action: NextAction | None = None,
) -> TrackedWriteRequest:
    return TrackedWriteRequest(
        config=config,
        epic_id=_EPIC_ID,
        action=_action() if action is None else action,
        author="relay-session",
        now=_NOW,
        is_handoff=is_handoff,
        body="A handoff entry." if is_handoff else None,
        operation_id=operation_id,
    )


def _write(outcome: object) -> TrackedWrite:
    assert isinstance(outcome, TrackedWrite), outcome
    return outcome


def _refusal(outcome: object) -> NextActionRefusal:
    assert isinstance(outcome, NextActionRefusal), outcome
    return outcome


def _handoff_comments(*, config: StoreConfig) -> list[dict[str, Any]]:
    comments = _fake(config=config).list_comments(issue_id=_EPIC_ID)
    return [
        comment
        for comment in comments
        if not str(comment.get("text", "")).startswith(PLAN_PROGRESS_PREFIX)
    ]


def test_an_invalid_pointer_is_refused_before_the_chain_is_even_read(
    tmp_path: Path,
) -> None:
    """Validation runs first, so a malformed write touches nothing."""
    config = _seed(tmp_path=tmp_path)
    before = read_chain_head(config=config, epic_id=_EPIC_ID)
    assert isinstance(before, ChainHead)

    refusal = _refusal(
        commit_tracked_write(
            request=_request(
                config=config,
                action=NextAction(
                    kind="not-a-kind",
                    ref=_TARGET_ID,
                    text="Keep going.",
                    required_result=_RESULT,
                    budget={"deadline": _DEADLINE, "max_handoffs": 5},
                ),
            )
        )
    )

    assert "unknown next_action kind" in refusal.detail
    after = read_chain_head(config=config, epic_id=_EPIC_ID)
    assert isinstance(after, ChainHead)
    assert after.epoch == before.epoch


@pytest.mark.parametrize(
    ("write", "expected_comments"),
    [("handoff", 1), ("pointer", 0)],
)
def test_an_epic_with_no_chain_takes_the_legacy_path_and_creates_no_genesis(
    tmp_path: Path,
    write: str,
    expected_comments: int,
) -> None:
    """Research note 007: these writers MUST NEVER create a chain genesis.

    A genesis created by a writer racing another writer forks the authority
    permanently. The pointer still acquires its five-field shape, as the clause
    requires, with no durable authority behind it — which is the honest state,
    and the one a reader must keep reporting as missing tracking.

    Both arms are run because the legacy path is the one place the handoff
    comment is written outside the chain, so a direct pointer write must be
    shown to append nothing there too.
    """
    config = _seed(tmp_path=tmp_path, with_chain=False)
    tokens_before = _fake(config=config).no_history_issue_ids()

    write = _write(
        commit_tracked_write(request=_request(config=config, is_handoff=write == "handoff"))
    )

    assert write.tracked is False
    assert write.idempotent is False
    assert _fake(config=config).no_history_issue_ids() == tokens_before
    assert isinstance(read_chain_head(config=config, epic_id=_EPIC_ID), ChainFinding)
    record = _fake(config=config).show_issue(issue_id=_EPIC_ID)
    pointer = plan_record_metadata(record=record)[NEXT_ACTION_METADATA_KEY]
    assert isinstance(pointer, dict)
    assert pointer["budget"] == {"deadline": _DEADLINE, "max_handoffs": 5}
    assert len(_handoff_comments(config=config)) == expected_comments


def test_a_chain_finding_other_than_missing_refuses_the_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fork or an unreadable chain means the prior obligation CANNOT be read.

    Proceeding would preserve a budget nobody measured, so the write fails
    closed and the refusal carries the finding's own remedy.
    """
    config = _seed(tmp_path=tmp_path)
    finding = chain_fork_finding(
        epic_id=_EPIC_ID,
        token_id=_TOKEN_B,
        claimed_prior=_TOKEN_A,
        walked_from=_TOKEN_Z,
    )
    monkeypatch.setattr(
        _plan_tracked_write,
        "read_chain_head",
        lambda *, config, epic_id: finding,  # noqa: ARG005 -- stub matches the seam.
    )

    refusal = _refusal(commit_tracked_write(request=_request(config=config, is_handoff=True)))

    assert finding.code in refusal.detail
    assert finding.remedy in refusal.detail
    assert _handoff_comments(config=config) == []


def test_a_decision_refusal_refuses_before_appending_or_updating_anything(
    tmp_path: Path,
) -> None:
    """ "refused BEFORE appending a handoff or updating the pointer"."""
    config = _seed(tmp_path=tmp_path)
    assert _write(commit_tracked_write(request=_request(config=config))).tracked is True
    renamed = NextAction(
        kind="impl",
        ref="bd-ib-other",
        text="Different target.",
        required_result={
            "repo": _PROJECT_NAME,
            "item_status": {"item_id": "bd-ib-other", "status": "done"},
        },
        budget={"deadline": _DEADLINE, "max_handoffs": 5},
    )
    comments_before = len(_handoff_comments(config=config))

    refusal = _refusal(
        commit_tracked_write(request=_request(config=config, is_handoff=True, action=renamed))
    )

    assert "cannot be renamed" in refusal.detail
    assert len(_handoff_comments(config=config)) == comments_before


def test_a_concurrent_writer_winning_the_race_refuses_with_a_retry_instruction(
    tmp_path: Path,
) -> None:
    """A stale observed head is refused rather than committed over.

    The head is read, then a second write commits from it, then the first write
    is submitted against the head it had already read — which is the shape a
    genuine race leaves behind.
    """
    config = _seed(tmp_path=tmp_path)
    stale_head = read_chain_head(config=config, epic_id=_EPIC_ID)
    assert isinstance(stale_head, ChainHead)
    assert _write(commit_tracked_write(request=_request(config=config, operation_id="op-winner")))
    comments_before = len(_handoff_comments(config=config))

    outcome = _plan_tracked_write._tracked_write(  # noqa: SLF001 -- the seam a race reaches.
        request=_request(config=config, is_handoff=True, operation_id="op-loser"),
        head=stale_head,
    )

    refusal = _refusal(outcome)
    assert "a concurrent writer committed from epoch" in refusal.detail
    assert "re-read the plan and retry" in refusal.detail
    assert len(_handoff_comments(config=config)) == comments_before


def test_a_failed_transition_finding_refuses_rather_than_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A chain that cannot complete its transition writes no projection."""
    config = _seed(tmp_path=tmp_path)
    finding = chain_fork_finding(
        epic_id=_EPIC_ID,
        token_id=_TOKEN_B,
        claimed_prior=_TOKEN_A,
        walked_from=_TOKEN_Z,
    )
    monkeypatch.setattr(
        _plan_tracked_write,
        "commit_transition",
        lambda *, config, epic_id, request: finding,  # noqa: ARG005 -- stub matches the seam.
    )

    refusal = _refusal(commit_tracked_write(request=_request(config=config, is_handoff=True)))

    assert finding.code in refusal.detail
    assert _handoff_comments(config=config) == []


def test_a_retried_operation_recovers_its_event_and_appends_no_second_handoff(
    tmp_path: Path,
) -> None:
    """ "retried calls ... MUST recover the original event rather than duplicate
    handoffs or extend a deadline".

    The comment count and the pointer authorship are asserted because a retry
    that re-appended its entry would still return a correct-looking idempotent
    result.
    """
    config = _seed(tmp_path=tmp_path)
    first = _write(
        commit_tracked_write(
            request=_request(config=config, is_handoff=True, operation_id="op-retry")
        )
    )
    assert first.idempotent is False
    assert len(_handoff_comments(config=config)) == 1

    retried = _write(
        commit_tracked_write(
            request=_request(config=config, is_handoff=True, operation_id="op-retry")
        )
    )

    assert retried.idempotent is True
    assert retried.epoch == first.epoch
    assert retried.consumed_handoffs == first.consumed_handoffs
    assert len(_handoff_comments(config=config)) == 1


def _exhaust(*, config: StoreConfig, operation_id: str) -> TrackedWrite:
    """Establish a one-unit obligation and spend its final unit on a handoff.

    The establishing write is a DIRECT pointer write, which consumes nothing, so
    the handoff that follows is the one that takes the obligation to its ceiling
    — which is the state the retry below has to be answered from.
    """
    action = _action(max_handoffs=1)
    assert _write(commit_tracked_write(request=_request(config=config, action=action))).tracked
    return _write(
        commit_tracked_write(
            request=_request(
                config=config,
                is_handoff=True,
                operation_id=operation_id,
                action=action,
            )
        )
    )


def test_a_retry_of_the_handoff_that_exhausted_the_budget_recovers_it(
    tmp_path: Path,
) -> None:
    """ "retried calls with the same operation identity MUST recover the original
    event rather than duplicate handoffs or extend a deadline."

    The retried handoff is the one that consumed the FINAL `max_handoffs` unit,
    so the head it is submitted against already reads as expired. The clause
    gives no exemption for that state: the write it is retrying SUCCEEDED, so
    the answer owed is the original event, not a refusal that would send the
    caller to register a causal recovery for an obligation it had just met.
    """
    config = _seed(tmp_path=tmp_path)
    first = _exhaust(config=config, operation_id="op-final")
    assert first.idempotent is False
    assert first.consumed_handoffs == 1
    assert len(_handoff_comments(config=config)) == 1

    retried = _write(
        commit_tracked_write(
            request=_request(
                config=config,
                is_handoff=True,
                operation_id="op-final",
                action=_action(max_handoffs=1),
            )
        )
    )

    assert retried.idempotent is True
    assert retried.epoch == first.epoch
    assert retried.consumed_handoffs == first.consumed_handoffs
    assert retried.action.budget == first.action.budget
    assert len(_handoff_comments(config=config)) == 1


def test_a_different_operation_at_the_exhausted_budget_is_still_refused_as_expired(
    tmp_path: Path,
) -> None:
    """The control: expiry still refuses every write that is not that retry.

    Without this, "recover the retry" is satisfiable by not grading expiry at
    all — which would hand a fresh deadline to every continuation that asked.
    The pointer is read back because a refusal that had already rewritten it
    would leave a perfectly well-formed pointer behind.
    """
    config = _seed(tmp_path=tmp_path)
    _ = _exhaust(config=config, operation_id="op-final")
    pointer_before = plan_record_metadata(record=_fake(config=config).show_issue(issue_id=_EPIC_ID))

    refusal = _refusal(
        commit_tracked_write(
            request=_request(
                config=config,
                is_handoff=True,
                operation_id="op-successor",
                action=_action(max_handoffs=1),
            )
        )
    )

    assert "is expired at its handoffs limit" in refusal.detail
    assert "causal recovery attempt" in refusal.detail
    assert len(_handoff_comments(config=config)) == 1
    after = plan_record_metadata(record=_fake(config=config).show_issue(issue_id=_EPIC_ID))
    assert after[NEXT_ACTION_METADATA_KEY] == pointer_before[NEXT_ACTION_METADATA_KEY]


def test_an_unreadable_recovery_scan_refuses_rather_than_deciding_afresh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A receipt naming an operation whose event cannot be read is FAIL-CLOSED.

    The ring is proof the transition happened, so a scan that cannot produce its
    event must not fall through to the obligation decision: deciding afresh
    would commit a second transition for an operation already accounted for,
    which is the duplicated handoff the clause forbids.
    """
    config = _seed(tmp_path=tmp_path)
    finding = receipt_without_event_finding(epic_id=_EPIC_ID, operation_id="op-ringed")
    monkeypatch.setattr(
        _plan_tracked_write,
        "recover_committed_operation",
        lambda *, config, epic_id, operation_id, observed_head: finding,  # noqa: ARG005 -- stub matches the seam.
    )

    refusal = _refusal(
        commit_tracked_write(
            request=_request(config=config, is_handoff=True, operation_id="op-ringed")
        )
    )

    assert finding.code in refusal.detail
    assert finding.detail in refusal.detail
    assert _handoff_comments(config=config) == []


def test_a_twin_committing_after_the_scan_is_still_projected_as_recovered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The chain keeps its OWN retry guard, and this write respects its answer.

    A twin of this call can commit in the window between the pre-decision scan
    and the chain's own, so `commit_transition` can still hand back a recovery
    that the scan did not see. Projecting it as a fresh commit would append the
    handoff that twin already appended.
    """
    config = _seed(tmp_path=tmp_path)
    recovered = CommittedTransition(
        payload=TransitionPayload(
            operation_id="op-twin",
            prior_epoch=0,
            new_epoch=1,
            prior_token_id=_TOKEN_A,
            next_token_id=_TOKEN_B,
            event_kind="handoff",
            authority=AuthorityState(
                required_result=_RESULT,
                original_deadline=_DEADLINE,
                max_handoffs=5,
                consumed_handoffs=1,
            ),
        ),
        source=RECOVERED_FROM_PROGRESS_EVENT,
    )
    monkeypatch.setattr(
        _plan_tracked_write,
        "commit_transition",
        lambda *, config, epic_id, request: recovered,  # noqa: ARG005 -- stub matches the seam.
    )

    write = _write(
        commit_tracked_write(
            request=_request(config=config, is_handoff=True, operation_id="op-twin")
        )
    )

    assert write.idempotent is True
    assert write.epoch == 1
    assert write.consumed_handoffs == 1
    assert write.tracked is True
    assert _handoff_comments(config=config) == []


def test_the_derived_operation_identity_is_stable_per_logical_operation() -> None:
    """Two identical calls are one retry; any differing field is a new operation.

    The PROPOSED BUDGET case is the one that matters most and the one most
    easily left out: on the fresh-obligation arm that budget is what becomes
    durable, so two establishing writes differing only there must not collapse
    into one identity — the second would otherwise be recovered as a retry and
    adopt a budget its caller never asked for.
    """
    config = StoreConfig(
        tenant="t", prefix="bd-ib", server_user="u", database="d", bd_path="bd", fake=True
    )
    base = _request(config=config, is_handoff=True)
    base_id = derived_operation_id(request=base)

    assert base_id == derived_operation_id(request=_request(config=config, is_handoff=True))
    assert base_id.startswith("plan-write-")
    assert base_id != derived_operation_id(request=_request(config=config, is_handoff=False))
    assert base_id != derived_operation_id(
        request=_request(config=config, is_handoff=True, action=_action(max_handoffs=6))
    )


def test_a_reordered_but_equal_reference_derives_the_same_operation_identity() -> None:
    """Two spellings of one reference are one operation, not two.

    Dict insertion order is not part of a reference's meaning, so an identity
    sensitive to it would read an ordinary retry as fresh work and consume a
    second handoff unit for it.
    """
    config = StoreConfig(
        tenant="t", prefix="bd-ib", server_user="u", database="d", bd_path="bd", fake=True
    )
    reordered: dict[str, object] = {
        "item_status": {"status": "done", "item_id": _TARGET_ID},
        "repo": _PROJECT_NAME,
    }
    assert reordered == _RESULT
    assert list(reordered) != list(_RESULT)

    assert derived_operation_id(request=_request(config=config, is_handoff=True)) == (
        derived_operation_id(
            request=_request(
                config=config,
                is_handoff=True,
                action=NextAction(
                    kind="impl",
                    ref=_TARGET_ID,
                    text="Keep going.",
                    required_result=reordered,
                    budget={"max_handoffs": 5, "deadline": _DEADLINE},
                ),
            )
        )
    )


def test_an_unset_repo_root_reads_the_prior_target_from_the_working_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reader needs a clone, and a config naming none falls back to `cwd`.

    The fallback is asserted by making `cwd` the project root and observing the
    prior obligation get READ — a reading taken against the wrong root reports
    the repository as unresolvable instead.
    """
    config = _seed(tmp_path=tmp_path)
    assert _write(commit_tracked_write(request=_request(config=config))).tracked is True
    monkeypatch.chdir(tmp_path / _PROJECT_NAME)
    rootless = StoreConfig(
        tenant=config.tenant,
        prefix=config.prefix,
        server_user=config.server_user,
        database=config.database,
        bd_path=config.bd_path,
        fake=True,
        repo_root=None,
    )

    observation = _plan_tracked_write._prior_observation(  # noqa: SLF001 -- the fallback seam.
        request=_request(config=rootless),
        head=ChainHead(
            current_token_id=_TOKEN_A,
            latest_closed_token_id=None,
            epoch=1,
            authority=AuthorityState(
                required_result=_RESULT,
                original_deadline=_DEADLINE,
                max_handoffs=5,
            ),
        ),
    )

    assert observation is not None
    assert observation.status == "unsatisfied"


def test_no_prior_obligation_means_no_target_read_is_attempted(
    tmp_path: Path,
) -> None:
    """There is nothing to observe, so the reader is not consulted at all."""
    config = _seed(tmp_path=tmp_path)

    assert (
        _plan_tracked_write._prior_observation(  # noqa: SLF001 -- the no-obligation seam.
            request=_request(config=config),
            head=ChainHead(
                current_token_id=_TOKEN_A,
                latest_closed_token_id=None,
                epoch=0,
                authority=AuthorityState(),
            ),
        )
        is None
    )


def test_recovery_on_an_epic_with_no_authority_chain_is_refused(tmp_path: Path) -> None:
    """The legacy arm holds no obligation, so none of it can have expired.

    Without this the attempt would be silently DROPPED on the legacy path: the
    write would succeed, nothing would record the attempt, and the caller would
    have no way to tell that from a recovery that was admitted.
    """
    config = _seed(tmp_path=tmp_path, with_chain=False)
    recovery = CausalRecovery(
        required_result=_RESULT,
        previous_epoch=1,
        failure_evidence="the provider returned usageLimitExceeded",
        cause="host",
        next_operation=f"impl:{_TARGET_ID}",
        attempt_id="attempt-0001",
        attempt_deadline="2026-10-20T12:00:00Z",
    )

    refusal = _refusal(
        commit_tracked_write(
            request=TrackedWriteRequest(
                config=config,
                epic_id=_EPIC_ID,
                action=_action(),
                author="relay-session",
                now=_NOW,
                is_handoff=True,
                body="A handoff entry.",
                recovery=recovery,
            )
        )
    )

    assert "no authority chain" in refusal.detail
    assert _handoff_comments(config=config) == []
