"""Scenario 148 — an unattended resume reports progress and withholds dispatch.

`contracts.md` section "Required result, budget and progress epoch":
"resume_directive MUST report missing, expired and unobservable tracking
findings. It MUST NOT automatically dispatch an exhausted or unobservable
obligation. An unattended expired resume MUST retain the obligation and expose
an authorized diagnosis/recovery action for the independent consumer. ... The
progress check MUST precede the unattended dispatch decision."

WHY THE DURABLE AUTHORITY IS WHAT THE RESUME MUST READ. The budget used to be
read off the `next_action` pointer, which every sanctioned writer rewrites
wholesale — so the one thing a resume most needs to be unable to lie about was
stored where a writer could hand it a new value. The fixtures here make that
difference OBSERVABLE: the pointer is left carrying a 2099 deadline and a
handoff count of zero while the chain's authority records the real, exhausted
one. A resume reading the pointer reports a healthy obligation and dispatches
it; a resume reading the authority reports expiry. Both produce a confident
directive and nothing in the shape distinguishes them, which is why the pointer
is deliberately well-formed rather than absent.

WHAT "WITHHOLDS DISPATCH" MEANS HERE, PRECISELY. The exhausted obligation's own
action must NOT be taken; an AUTHORIZED diagnosis action is exposed instead,
because the clause requires the independent consumer to be given something
executable rather than left with a dead end. So the assertions check that
`next_action` is not the impl action AND that it is the diagnosis action — one
without the other would pass for a resume that stalls, or for one that
dispatches the thing it was told not to.
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain import (
    ChainHead,
    CommittedTransition,
    TransitionRequest,
    commit_transition,
    read_chain_head,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import AuthorityState
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import (
    chain_cache_metadata,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import create_token
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    NEXT_ACTION_METADATA_KEY,
    NextAction,
    next_action_metadata,
    plan_record_metadata,
    resume_directive,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_PROJECT_NAME = "repo"
_EPIC_ID = "bd-ib-relayresume"
_TARGET_ID = "bd-ib-resumetarget"
_ORIGINAL_DEADLINE = "2026-10-14T09:00:00Z"
_FAR_FUTURE = "2099-01-01T00:00:00Z"
# Deliberately in the PAST, and it must stay there: the resume reads the real
# clock, so an "already elapsed" bound has to be elapsed at every future run
# date rather than only at the one this was written on. Every expiry assertion
# in this module that must hold REGARDLESS of the clock is driven by the handoff
# ceiling instead, which no passage of time can un-reach.
_ELAPSED_BOUND = "2026-10-12T10:00:00Z"
_DIAGNOSIS = f"diagnose-plan-progress:{_EPIC_ID}"
_IMPL_ACTION = f"impl:{_TARGET_ID}"


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


def _required_result(*, item_id: str = _TARGET_ID) -> dict[str, object]:
    return {
        "repo": _PROJECT_NAME,
        "item_status": {"item_id": item_id, "status": "done"},
    }


def _seed(
    *,
    tmp_path: Path,
    authority: AuthorityState,
    pointer: NextAction | None = None,
    target_status: str = "ready",
) -> StoreConfig:
    """An epic whose chain carries `authority` and whose pointer is HEALTHY.

    The pointer is written DIRECTLY rather than through a sanctioned writer, so
    it can carry the far-future budget a rewrite would have produced before the
    authority moved to the chain. That divergence is the whole instrument.
    """
    repo = tmp_path / _PROJECT_NAME
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    config = store_config(repo=repo)
    fake = _fake(config=config)
    for issue_id, status in ((_EPIC_ID, "active"), (_TARGET_ID, target_status)):
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
    genesis = create_token(client=fake)
    fake.update_issue(
        issue_id=_EPIC_ID,
        metadata=chain_cache_metadata(
            existing_metadata={"rank": "a0"},
            latest_closed=None,
            current=genesis,
        ),
    )
    head = read_chain_head(config=config, epic_id=_EPIC_ID)
    assert isinstance(head, ChainHead), head
    committed = commit_transition(
        config=config,
        epic_id=_EPIC_ID,
        request=TransitionRequest(
            operation_id="op-seed",
            observed_head=head,
            authority=authority,
            event_kind="handoff",
            author="relay-session",
            now="2026-10-13T08:30:00Z",
        ),
    )
    assert isinstance(committed, CommittedTransition), committed
    healthy = (
        NextAction(
            kind="impl",
            ref=_TARGET_ID,
            text="Keep going.",
            required_result=_required_result(),
            budget={"deadline": _FAR_FUTURE, "max_handoffs": 99, "handoff_count": 0},
        )
        if pointer is None
        else pointer
    )
    record = fake.show_issue(issue_id=_EPIC_ID)
    fake.update_issue(
        issue_id=_EPIC_ID,
        metadata=next_action_metadata(
            existing_metadata=plan_record_metadata(record=record),
            action=healthy,
            session="relay-session",
            now="2026-10-13T08:30:00Z",
        ),
    )
    return config


def _exhausted_authority() -> AuthorityState:
    """Both limits reached: the ceiling is spent AND the deadline has passed."""
    return AuthorityState(
        required_result=_required_result(),
        original_deadline=_ORIGINAL_DEADLINE,
        max_handoffs=2,
        consumed_handoffs=2,
    )


def _live_authority(*, item_id: str = _TARGET_ID) -> AuthorityState:
    return AuthorityState(
        required_result=_required_result(item_id=item_id),
        original_deadline=_FAR_FUTURE,
        max_handoffs=5,
        consumed_handoffs=1,
    )


def _findings_text(*, findings: tuple[str, ...]) -> str:
    return "\n".join(findings)


def test_the_healthy_pointer_the_fixtures_leave_is_itself_dispatchable(
    tmp_path: Path,
) -> None:
    """The POSITIVE CONTROL for every case below.

    The fixtures all leave a far-future pointer in place. If that pointer were
    not dispatchable on its own, "the resume withheld dispatch" would be
    evidence of nothing — every case would pass against a resume that never
    dispatches anything.
    """
    config = _seed(tmp_path=tmp_path, authority=_live_authority())

    directive = resume_directive(config=config, epic_id=_EPIC_ID, unattended=True)

    assert directive.ask is False
    assert directive.next_action == _IMPL_ACTION


def test_an_expired_obligation_is_reported_even_though_the_pointer_looks_healthy(
    tmp_path: Path,
) -> None:
    """The durable authority governs, not the rewritable pointer.

    The pointer on this epic carries a 2099 deadline and a zero handoff count;
    the chain says the obligation is spent. Reading the pointer reports a
    healthy obligation and dispatches it.
    """
    config = _seed(tmp_path=tmp_path, authority=_exhausted_authority())
    pointer = plan_record_metadata(record=_fake(config=config).show_issue(issue_id=_EPIC_ID))[
        NEXT_ACTION_METADATA_KEY
    ]
    assert isinstance(pointer, dict)
    assert pointer["budget"] == {
        "deadline": _FAR_FUTURE,
        "max_handoffs": 99,
        "handoff_count": 0,
    }

    directive = resume_directive(config=config, epic_id=_EPIC_ID, unattended=True)

    assert "plan-progress-tracking: expired" in _findings_text(findings=directive.findings)
    assert _ORIGINAL_DEADLINE in _findings_text(findings=directive.findings)


def test_an_expired_unattended_resume_withholds_the_exhausted_action(
    tmp_path: Path,
) -> None:
    """ "It MUST NOT automatically dispatch an exhausted ... obligation"."""
    config = _seed(tmp_path=tmp_path, authority=_exhausted_authority())

    directive = resume_directive(config=config, epic_id=_EPIC_ID, unattended=True)

    assert directive.next_action != _IMPL_ACTION


def test_an_expired_unattended_resume_exposes_the_authorized_diagnosis(
    tmp_path: Path,
) -> None:
    """ "expose an authorized diagnosis/recovery action for the independent
    consumer".

    Asserted separately from the withholding above because the two can fail
    independently: a resume that stalls satisfies the withholding and leaves
    the consumer a dead end.
    """
    config = _seed(tmp_path=tmp_path, authority=_exhausted_authority())

    directive = resume_directive(config=config, epic_id=_EPIC_ID, unattended=True)

    assert directive.next_action == _DIAGNOSIS
    assert _DIAGNOSIS in _findings_text(findings=directive.findings)


def test_an_expired_resume_retains_the_obligation_it_reports(tmp_path: Path) -> None:
    """ "MUST retain the obligation" — reading is not writing.

    The authority is read back after the resume and must be byte-identical: a
    resume that cleared or advanced the obligation while reporting it would
    make the next reader see a healthy plan.
    """
    config = _seed(tmp_path=tmp_path, authority=_exhausted_authority())
    before = read_chain_head(config=config, epic_id=_EPIC_ID)
    assert isinstance(before, ChainHead)

    _ = resume_directive(config=config, epic_id=_EPIC_ID, unattended=True)

    after = read_chain_head(config=config, epic_id=_EPIC_ID)
    assert isinstance(after, ChainHead)
    assert after.authority == before.authority
    assert after.epoch == before.epoch


def test_an_unobservable_obligation_is_reported_and_withheld(tmp_path: Path) -> None:
    """ "It MUST NOT automatically dispatch an ... unobservable obligation".

    The authority names a ledger item the tenant does not hold, so the ordinary
    reader cannot observe it — an unobservable reading rather than a confident
    negative.
    """
    config = _seed(
        tmp_path=tmp_path,
        authority=_live_authority(item_id="bd-ib-never-filed"),
    )

    directive = resume_directive(config=config, epic_id=_EPIC_ID, unattended=True)

    assert "plan-progress-tracking: unobservable" in _findings_text(findings=directive.findings)
    assert directive.next_action != _IMPL_ACTION
    assert directive.next_action == _DIAGNOSIS


def test_a_satisfied_obligation_is_neither_expired_nor_unobservable(
    tmp_path: Path,
) -> None:
    """The control that separates the two findings from "reports everything".

    The target really stands at `done`, so the obligation is met and neither
    finding is owed. A reader emitting one here would be reporting a healthy
    plan as broken.
    """
    config = _seed(
        tmp_path=tmp_path,
        authority=_live_authority(),
        target_status="done",
    )

    directive = resume_directive(config=config, epic_id=_EPIC_ID, unattended=True)

    text = _findings_text(findings=directive.findings)
    assert "plan-progress-tracking: expired" not in text
    assert "plan-progress-tracking: unobservable" not in text


def test_a_present_chain_with_no_obligation_names_the_pointer_write_as_the_remedy(
    tmp_path: Path,
) -> None:
    """The state a genesis and the sanctioned migration both leave behind.

    The chain is PRESENT — the walk reached an open token at epoch 1 — and no
    transition has committed a required result or a budget yet. Reporting that
    as a plan epic that "carries no authority chain" names
    `migrate-plan-records` as the remedy, which is the write that has ALREADY
    run here and whose re-run creates nothing, so the finding could never be
    cleared by the remedy it named. Only an executable-kind pointer write
    carrying both tracking fields creates the obligation.

    The OPEN TOKEN is asserted because it is the checkable form of "the chain
    is present": a finding that merely dropped the false sentence would read as
    an absence of evidence either way.
    """
    config = _seed(tmp_path=tmp_path, authority=AuthorityState())
    head = read_chain_head(config=config, epic_id=_EPIC_ID)
    assert isinstance(head, ChainHead), head

    directive = resume_directive(config=config, epic_id=_EPIC_ID, unattended=True)

    text = _findings_text(findings=directive.findings)
    assert "plan-progress-tracking: missing" in text
    assert head.current_token_id in text
    assert "executable-kind next_action write carrying required_result and budget" in text
    assert "migrate-plan-records" not in text


def test_the_progress_check_precedes_the_unattended_dispatch_decision(
    tmp_path: Path,
) -> None:
    """ "The progress check MUST precede the unattended dispatch decision."

    The epic carries NO Definition of Done section, which is the other
    pre-emption in this path, AND an exhausted obligation. The progress finding
    must still be reported — a resume that settled the dispatch question first
    would answer with the gap pointer and never read the obligation.
    """
    config = _seed(tmp_path=tmp_path, authority=_exhausted_authority())
    fake = _fake(config=config)
    fake.update_issue(issue_id=_EPIC_ID, description="A plan with no Definition of Done.")

    directive = resume_directive(config=config, epic_id=_EPIC_ID, unattended=True)

    assert "plan-progress-tracking: expired" in _findings_text(findings=directive.findings)
    assert directive.next_action != _IMPL_ACTION


def test_an_attended_resume_reports_the_same_finding_without_acting(
    tmp_path: Path,
) -> None:
    """The findings are owed to every resume, not only the unattended one.

    "resume_directive MUST report missing, expired and unobservable tracking
    findings" is unqualified, and an attended session needs the finding most:
    it is the one that will decide what to do about it.
    """
    config = _seed(tmp_path=tmp_path, authority=_exhausted_authority())

    directive = resume_directive(config=config, epic_id=_EPIC_ID, unattended=False)

    assert "plan-progress-tracking: expired" in _findings_text(findings=directive.findings)
    assert directive.next_action != _IMPL_ACTION


def test_an_expired_obligation_with_a_bounded_attempt_exposes_that_operation(
    tmp_path: Path,
) -> None:
    """ "A typed causal attempt MAY restore bounded execution without resetting
    the original deadline".

    A recorded, still-bounded attempt is what the consumer should run, so the
    directive exposes the ATTEMPT's operation rather than a fresh diagnosis —
    while the finding still reports the obligation as expired.
    """
    attempt: dict[str, Any] = {
        "attempt": {
            "attempt_id": "attempt-0001",
            "previous_epoch": 1,
            "cause": "host",
            "failure_evidence": "the provider returned usageLimitExceeded",
            "next_operation": _IMPL_ACTION,
            "attempt_deadline": _FAR_FUTURE,
            "recorded_at": "2026-10-15T09:00:00Z",
            "claim_receipt": None,
            "execution_receipt": None,
            "outcome_receipt": None,
        },
        "item_attributable_attempts": 0,
    }
    config = _seed(
        tmp_path=tmp_path,
        authority=AuthorityState(
            required_result=_required_result(),
            original_deadline=_ORIGINAL_DEADLINE,
            max_handoffs=2,
            consumed_handoffs=2,
            last_recovery_attempt=attempt,
        ),
    )

    directive = resume_directive(config=config, epic_id=_EPIC_ID, unattended=True)

    text = _findings_text(findings=directive.findings)
    assert "plan-progress-tracking: expired" in text
    assert "attempt-0001" in text
    assert directive.next_action == _IMPL_ACTION


def test_an_expired_attempt_falls_back_to_a_fresh_diagnosis(tmp_path: Path) -> None:
    """A bound that has elapsed authorizes nothing further.

    Without this the first attempt would authorize its operation forever, which
    is exactly the self-renewing budget the clause forbids.
    """
    attempt: dict[str, Any] = {
        "attempt": {
            "attempt_id": "attempt-0001",
            "previous_epoch": 1,
            "cause": "host",
            "failure_evidence": "the provider returned usageLimitExceeded",
            "next_operation": _IMPL_ACTION,
            "attempt_deadline": _ELAPSED_BOUND,
            "recorded_at": "2026-10-12T09:30:00Z",
            "claim_receipt": None,
            "execution_receipt": None,
            "outcome_receipt": None,
        },
        "item_attributable_attempts": 0,
    }
    config = _seed(
        tmp_path=tmp_path,
        authority=AuthorityState(
            required_result=_required_result(),
            original_deadline=_ORIGINAL_DEADLINE,
            max_handoffs=2,
            consumed_handoffs=2,
            last_recovery_attempt=attempt,
        ),
    )

    directive = resume_directive(config=config, epic_id=_EPIC_ID, unattended=True)

    assert directive.next_action == _DIAGNOSIS
