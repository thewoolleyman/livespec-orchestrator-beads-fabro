"""Receipts on an executed causal recovery attempt, over the in-memory tenant.

`bd-ib-zi5ygh` left `CausalRecovery`'s three receipt fields correctly REFUSED on
a fresh attempt and never filled in afterwards, so a reader of an epic's
`last_recovery_attempt` could not tell an attempt that executed from one that was
only recorded. These cases bind the other half: what each receipt says, which
durable executor record it is read from, and what a recorded-but-undispatched
attempt reports instead.

EVERY END-TO-END CASE ASSERTS THE LEDGER AND NOT ONLY THE RETURN VALUE. A writer
that returned the right object while committing nothing would satisfy every
assertion about its result, so each case re-reads the receipts off the epic's own
authority chain.
"""

from __future__ import annotations

import json
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
from livespec_orchestrator_beads_fabro.commands import _plan_recovery_receipt_write
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain import (
    ChainHead,
    CommittedTransition,
    StaleEpochRefusal,
    TransitionRequest,
    commit_transition,
    read_chain_head,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import (
    chain_fork_finding,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import AuthorityState
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import (
    chain_cache_metadata,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import create_token
from livespec_orchestrator_beads_fabro.commands._plan_recovery_receipt_write import (
    RecoveryReceiptRequest,
    RecoveryReceiptWrite,
    record_recovery_receipts,
)
from livespec_orchestrator_beads_fabro.commands._plan_recovery_receipts import (
    RECEIPTS_RECORDED,
    RECORDED_NOT_EXECUTED,
    ExecutionRecords,
    ReceiptRefusal,
    ReceiptSet,
    attempt_boundary_record,
    dispatched_subject,
    execution_records,
    recorded_attempt,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_PROJECT_NAME = "repo"
_EPIC_ID = "bd-ib-receiptepic"
_TARGET_ID = "bd-ib-receipttarget"
_DEADLINE = "2026-10-20T09:00:00Z"
_NOW = "2026-10-13T09:00:00Z"
_ATTEMPT_ID = "attempt-0001"
_DISPATCH_ID = "dispatch-77"
_RUN_ID = "01M4RECEIPTRUN"
_MAX_HANDOFFS = 5
_CONSUMED_HANDOFFS = 3
_ITEM_ATTEMPTS = 2
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


def _attempt_record(
    *,
    next_operation: str = f"impl:{_TARGET_ID}",
    receipts: ReceiptSet | None = None,
) -> dict[str, Any]:
    """One `last_recovery_attempt` as `_plan_recovery.recovery_record` renders it."""
    receipts = ReceiptSet() if receipts is None else receipts
    return {
        "attempt": {
            "attempt_id": _ATTEMPT_ID,
            "previous_epoch": 1,
            "cause": "host",
            "failure_evidence": "the provider returned usageLimitExceeded",
            "next_operation": next_operation,
            "attempt_deadline": "2026-10-20T12:00:00Z",
            "recorded_at": _NOW,
            "claim_receipt": receipts.claim,
            "execution_receipt": receipts.execution,
            "outcome_receipt": receipts.outcome,
        },
        "item_attributable_attempts": _ITEM_ATTEMPTS,
    }


def _authority(*, attempt: dict[str, Any] | None = None) -> AuthorityState:
    return AuthorityState(
        required_result=_RESULT,
        original_deadline=_DEADLINE,
        max_handoffs=_MAX_HANDOFFS,
        consumed_handoffs=_CONSUMED_HANDOFFS,
        last_recovery_attempt=_attempt_record() if attempt is None else attempt,
    )


def _seed(*, tmp_path: Path, authority: AuthorityState | None = None) -> StoreConfig:
    """A tenant holding one plan epic whose chain records one recovery attempt."""
    repo = tmp_path / _PROJECT_NAME
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    config = store_config(repo=repo)
    fake = _fake(config=config)
    _ = fake.create_issue(
        draft=IssueDraft(
            issue_id=_EPIC_ID,
            issue_type="epic",
            title=_EPIC_ID,
            description="Definition of Done\n\n- A thing holds.",
            assignee=None,
            created_at="2026-10-13T08:00:00Z",
            metadata={"rank": "a0"},
        )
    )
    fake.update_issue(issue_id=_EPIC_ID, status="active")
    genesis = create_token(client=fake)
    fake.update_issue(
        issue_id=_EPIC_ID,
        metadata=chain_cache_metadata(
            existing_metadata={"rank": "a0"},
            latest_closed=None,
            current=genesis,
        ),
    )
    _commit(config=config, authority=_authority() if authority is None else authority)
    return config


def _commit(*, config: StoreConfig, authority: AuthorityState) -> None:
    head = read_chain_head(config=config, epic_id=_EPIC_ID)
    assert isinstance(head, ChainHead)
    committed = commit_transition(
        config=config,
        epic_id=_EPIC_ID,
        request=TransitionRequest(
            operation_id=f"seed-{head.epoch}",
            observed_head=head,
            authority=authority,
            event_kind="recovery",
            author="seed-session",
            now=_NOW,
        ),
    )
    assert isinstance(committed, CommittedTransition)


def _journal(*, tmp_path: Path, records: tuple[dict[str, Any], ...]) -> Path:
    path = tmp_path / "dispatcher-journal.jsonl"
    # The drive executor writes this boundary before it hands the impl action to
    # the Dispatcher.  Receipt selection reads only executor records between
    # that attempt's boundary and the next one, never the item's whole history.
    records = (
        {
            "stage": "causal-recovery-attempt",
            "work_item_id": _TARGET_ID,
            "attempt_id": _ATTEMPT_ID,
        },
        *records,
    )
    _ = path.write_text(
        "".join(f"{json.dumps(record, sort_keys=True)}\n" for record in records),
        encoding="utf-8",
    )
    return path


def _dispatch_record(
    *,
    work_item_id: str = _TARGET_ID,
    dispatch_id: object = _DISPATCH_ID,
) -> dict[str, Any]:
    return {"stage": "dispatch-id", "work_item_id": work_item_id, "dispatch_id": dispatch_id}


def _run_record(*, run_id: str = _RUN_ID) -> dict[str, Any]:
    return {"stage": "fabro-run", "work_item_id": _TARGET_ID, "run_id": run_id}


def _outcome_record(
    *,
    status: str = "green",
    stage: object = "done",
    pr_number: object = 2904,
    work_item_id: str = _TARGET_ID,
) -> dict[str, Any]:
    outcome: dict[str, Any] = {"work_item_id": work_item_id, "status": status}
    if stage is not None:
        outcome["stage"] = stage
    if pr_number is not None:
        outcome["pr_number"] = pr_number
    return {"stage": "outcome", "outcome": outcome}


def _request(
    *,
    config: StoreConfig,
    journal_path: Path | None,
    attempt_id: str = _ATTEMPT_ID,
    operation_id: str | None = None,
) -> RecoveryReceiptRequest:
    return RecoveryReceiptRequest(
        config=config,
        epic_id=_EPIC_ID,
        attempt_id=attempt_id,
        journal_path=journal_path,
        author="relay-session",
        now=_NOW,
        operation_id=operation_id,
    )


def _write(outcome: object) -> RecoveryReceiptWrite:
    assert isinstance(outcome, RecoveryReceiptWrite), outcome
    return outcome


def _refusal(outcome: object) -> ReceiptRefusal:
    assert isinstance(outcome, ReceiptRefusal), outcome
    return outcome


def _head(*, config: StoreConfig) -> ChainHead:
    head = read_chain_head(config=config, epic_id=_EPIC_ID)
    assert isinstance(head, ChainHead)
    return head


def _recorded_receipts(*, config: StoreConfig) -> ReceiptSet:
    """The three receipt fields as the epic's authority chain now holds them."""
    attempt = recorded_attempt(
        authority_record=_head(config=config).authority.last_recovery_attempt
    )
    assert attempt is not None
    return attempt.receipts


def test_a_dispatched_recovery_attempt_records_a_claim_receipt_naming_the_dispatch_id(
    tmp_path: Path,
) -> None:
    """The claim receipt comes from the journal's own `dispatch-id` record.

    The dispatch id is the one identifier that says the authorized operation was
    CLAIMED by an executor, and it exists nowhere else: a work-item accumulates
    many dispatches and only that record names the one this attempt authorized.
    """
    config = _seed(tmp_path=tmp_path)
    journal = _journal(tmp_path=tmp_path, records=(_dispatch_record(),))

    write = _write(record_recovery_receipts(request=_request(config=config, journal_path=journal)))

    assert write.status == RECEIPTS_RECORDED
    assert write.attempt_id == _ATTEMPT_ID
    assert write.receipts.claim == f"dispatch {_DISPATCH_ID}"
    assert _recorded_receipts(config=config) == ReceiptSet(claim=f"dispatch {_DISPATCH_ID}")


def test_an_attempt_whose_operation_produced_a_run_records_an_execution_receipt(
    tmp_path: Path,
) -> None:
    """The execution receipt names the Fabro run, and it is NOT the claim receipt.

    A dispatch id says an executor claimed the operation; a run id says the
    factory actually started one. The claim is asserted alongside so a build that
    rendered one receipt into both fields cannot pass.
    """
    config = _seed(tmp_path=tmp_path)
    journal = _journal(tmp_path=tmp_path, records=(_dispatch_record(), _run_record()))

    write = _write(record_recovery_receipts(request=_request(config=config, journal_path=journal)))

    assert write.receipts == ReceiptSet(
        claim=f"dispatch {_DISPATCH_ID}",
        execution=f"fabro run {_RUN_ID}",
    )
    assert _recorded_receipts(config=config) == write.receipts


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        pytest.param(_outcome_record(), "green pull request 2904", id="green-pull-request"),
        pytest.param(
            _outcome_record(status="failed", stage="fabro-run", pr_number=None),
            "failed at failure stage fabro-run",
            id="failed-stage",
        ),
        pytest.param(
            _outcome_record(status="failed", stage="pr", pr_number=True),
            "failed at failure stage pr",
            id="non-integer-pull-request",
        ),
        pytest.param(
            _outcome_record(status="blocked", stage=None, pr_number=None),
            "blocked",
            id="neither-pull-request-nor-stage",
        ),
    ],
)
def test_a_terminal_run_records_an_outcome_receipt_naming_its_pull_request_or_stage(
    tmp_path: Path,
    outcome: dict[str, Any],
    expected: str,
) -> None:
    """The outcome receipt names the terminal AND how to reach its evidence.

    The two trailers are not interchangeable: a green terminal is identified by
    the pull request it produced and a failed one by the stage it died in, and an
    operator triaging an exhausted obligation needs whichever one exists. The
    non-integer case is kept because a pull-request field holding a boolean is
    truthy, so a reader testing truthiness would render `pull request True`.
    """
    config = _seed(tmp_path=tmp_path)
    journal = _journal(
        tmp_path=tmp_path,
        records=(_dispatch_record(), _run_record(), outcome),
    )

    write = _write(record_recovery_receipts(request=_request(config=config, journal_path=journal)))

    assert write.receipts.outcome == expected
    assert _recorded_receipts(config=config).outcome == expected


@pytest.mark.parametrize(
    ("next_operation", "records"),
    [
        pytest.param(
            f"diagnose-plan-progress:{_EPIC_ID}",
            (_dispatch_record(), _run_record(), _outcome_record()),
            id="read-only-diagnosis",
        ),
        pytest.param(
            "I will try a different approach.",
            (_dispatch_record(), _run_record(), _outcome_record()),
            id="unexecutable-operation",
        ),
        pytest.param(f"impl:{_TARGET_ID}", (), id="dispatchable-but-never-dispatched"),
    ],
)
def test_an_undispatched_attempt_keeps_every_receipt_null_and_reports_not_executed(
    tmp_path: Path,
    next_operation: str,
    records: tuple[dict[str, Any], ...],
) -> None:
    """An attempt nobody dispatched is RECORDED, and says so rather than guessing.

    The first two cases carry a FULL journal on purpose: a read-only diagnosis
    and an unexecutable operation dispatch nothing, so those journal records
    belong to some other work and must not be credited to this attempt — which is
    what tells "the operation dispatches nothing" apart from "the journal was
    empty". No transition is committed either, because an observation that
    observed nothing has nothing to make durable.
    """
    config = _seed(
        tmp_path=tmp_path,
        authority=_authority(attempt=_attempt_record(next_operation=next_operation)),
    )
    epoch_before = _head(config=config).epoch
    journal = _journal(tmp_path=tmp_path, records=records)

    write = _write(record_recovery_receipts(request=_request(config=config, journal_path=journal)))

    assert write.status == RECORDED_NOT_EXECUTED
    assert write.receipts == ReceiptSet()
    assert write.epoch == epoch_before
    assert _recorded_receipts(config=config) == ReceiptSet()
    assert _head(config=config).epoch == epoch_before


def test_a_later_attempt_refuses_to_inherit_an_earlier_attempts_executor_records(
    tmp_path: Path,
) -> None:
    """Executor records belong to the attempt whose journal boundary names them.

    A work item may be authorized again after an earlier dispatch.  The later
    attempt is recorded but undispatched, so it must not turn the earlier
    attempt's durable journal rows into its own claim, execution, or outcome
    receipts merely because both attempts authorized the same `impl:` action.
    """
    later_attempt_id = "attempt-0002"
    config = _seed(
        tmp_path=tmp_path,
        authority=_authority(
            attempt={
                **_attempt_record(),
                "attempt": {
                    **_attempt_record()["attempt"],
                    "attempt_id": later_attempt_id,
                },
            }
        ),
    )
    journal = _journal(
        tmp_path=tmp_path,
        records=(
            {
                "stage": "causal-recovery-attempt",
                "work_item_id": _TARGET_ID,
                "attempt_id": _ATTEMPT_ID,
            },
            _dispatch_record(),
            _run_record(),
            _outcome_record(),
            {
                "stage": "causal-recovery-attempt",
                "work_item_id": _TARGET_ID,
                "attempt_id": later_attempt_id,
            },
            {
                "stage": "causal-recovery-attempt",
                "work_item_id": _TARGET_ID,
                "attempt_id": "attempt-0003",
            },
        ),
    )

    write = _write(
        record_recovery_receipts(
            request=_request(
                config=config,
                journal_path=journal,
                attempt_id=later_attempt_id,
            )
        )
    )

    assert write.status == RECORDED_NOT_EXECUTED
    assert write.receipts == ReceiptSet()
    assert _recorded_receipts(config=config) == ReceiptSet()


def test_a_retried_executor_invocation_uses_its_latest_attempt_boundary(
    tmp_path: Path,
) -> None:
    """One attempt's later executor invocation supersedes only its own receipts.

    The journal is append-only, so a retry of the SAME authorized attempt has a
    second executor-owned boundary.  The receipt writer must take the later
    dispatch, run, and terminal outcome together; retaining the first segment
    would describe a command the executor subsequently retried.  The authority
    observations alongside the receipts make the transition's non-budgetary
    nature replayable too.
    """
    config = _seed(tmp_path=tmp_path)
    journal = _journal(
        tmp_path=tmp_path,
        records=(
            _dispatch_record(dispatch_id="dispatch-first"),
            _run_record(run_id="01M4FIRST"),
            _outcome_record(pr_number=2904),
            attempt_boundary_record(
                work_item_id=_TARGET_ID,
                attempt_ids=(_ATTEMPT_ID,),
            ),
            _dispatch_record(dispatch_id="dispatch-latest"),
            _run_record(run_id="01M4LATEST"),
            _outcome_record(pr_number=2905),
        ),
    )

    write = _write(record_recovery_receipts(request=_request(config=config, journal_path=journal)))

    assert write.status == RECEIPTS_RECORDED
    assert write.receipts == ReceiptSet(
        claim="dispatch dispatch-latest",
        execution="fabro run 01M4LATEST",
        outcome="green pull request 2905",
    )
    authority = _head(config=config).authority
    assert authority.original_deadline == _DEADLINE
    assert authority.consumed_handoffs == _CONSUMED_HANDOFFS
    assert isinstance(authority.last_recovery_attempt, dict)
    assert authority.last_recovery_attempt["item_attributable_attempts"] == _ITEM_ATTEMPTS


def test_recording_a_receipt_leaves_the_deadline_the_count_and_the_attempt_tally_alone(
    tmp_path: Path,
) -> None:
    """Recording an observation accepts no handoff and grants no time.

    The clause puts all three beyond a writer's reach — "Its attempt budget MUST
    NOT replace or postpone the original obligation deadline" and "neither
    increments or resets the item-attributable repetition count" — and a receipt
    write is a writer like any other. The item-attributable tally is read back
    too, because it lives in the attempt object this write REWRITES, which is the
    one place a careless rebuild would drop it.
    """
    config = _seed(tmp_path=tmp_path)
    journal = _journal(
        tmp_path=tmp_path,
        records=(_dispatch_record(), _run_record(), _outcome_record()),
    )

    assert (
        _write(
            record_recovery_receipts(request=_request(config=config, journal_path=journal))
        ).receipts.outcome
        is not None
    )

    authority = _head(config=config).authority
    assert authority.original_deadline == _DEADLINE
    assert authority.max_handoffs == _MAX_HANDOFFS
    assert authority.consumed_handoffs == _CONSUMED_HANDOFFS
    assert authority.required_result == _RESULT
    assert isinstance(authority.last_recovery_attempt, dict)
    assert authority.last_recovery_attempt["item_attributable_attempts"] == _ITEM_ATTEMPTS


def test_a_receipt_for_a_superseded_attempt_is_refused_rather_than_reattached(
    tmp_path: Path,
) -> None:
    """A receipt is evidence about ONE authorized operation.

    Attaching it to whatever attempt happens to be current would credit a later
    attempt with an earlier attempt's dispatch, and the result reads exactly like
    a correct receipt — so the mismatch refuses and names both ids.
    """
    config = _seed(tmp_path=tmp_path)
    journal = _journal(tmp_path=tmp_path, records=(_dispatch_record(),))

    refusal = _refusal(
        record_recovery_receipts(
            request=_request(config=config, journal_path=journal, attempt_id="attempt-0002")
        )
    )

    assert "attempt-0002" in refusal.detail
    assert _ATTEMPT_ID in refusal.detail
    assert _recorded_receipts(config=config) == ReceiptSet()


def test_a_second_identical_receipt_write_recovers_its_own_transition(
    tmp_path: Path,
) -> None:
    """A retry is recognised by the chain rather than committed twice.

    The derived operation identity carries the receipts themselves, so a re-read
    of the same journal is the SAME operation and the chain hands back the
    original transition. Without that, every re-read would burn an epoch and
    append a second progress event for one dispatch.
    """
    config = _seed(tmp_path=tmp_path)
    journal = _journal(tmp_path=tmp_path, records=(_dispatch_record(),))
    first = _write(record_recovery_receipts(request=_request(config=config, journal_path=journal)))
    assert first.idempotent is False

    retried = _write(
        record_recovery_receipts(request=_request(config=config, journal_path=journal))
    )

    assert retried.idempotent is True
    assert retried.epoch == first.epoch
    assert retried.receipts == first.receipts


def test_a_caller_supplied_operation_identity_is_used_as_the_retry_key(
    tmp_path: Path,
) -> None:
    """A caller holding its own operation identity keeps it, as every writer may."""
    config = _seed(tmp_path=tmp_path)
    journal = _journal(tmp_path=tmp_path, records=(_dispatch_record(),))

    write = _write(
        record_recovery_receipts(
            request=_request(config=config, journal_path=journal, operation_id="op-receipt")
        )
    )

    assert write.status == RECEIPTS_RECORDED
    assert _head(config=config).winning_operation_id == "op-receipt"


def test_an_absent_journal_leaves_every_receipt_null(tmp_path: Path) -> None:
    """A repository that has never dispatched has no journal to read."""
    config = _seed(tmp_path=tmp_path)

    write = _write(record_recovery_receipts(request=_request(config=config, journal_path=None)))

    assert write.receipts == ReceiptSet()


def test_a_chain_that_cannot_be_read_refuses_the_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fork or an unreadable record means the attempt cannot be identified.

    Committing anyway would attach a receipt to whichever branch happened to
    parse, which is a repair the reader invented.
    """
    config = _seed(tmp_path=tmp_path)
    finding = chain_fork_finding(
        epic_id=_EPIC_ID,
        token_id=_TOKEN_B,
        claimed_prior=_TOKEN_A,
        walked_from=_TOKEN_Z,
    )
    monkeypatch.setattr(
        _plan_recovery_receipt_write,
        "read_chain_head",
        lambda *, config, epic_id: finding,  # noqa: ARG005 -- stub matches the seam.
    )

    refusal = _refusal(record_recovery_receipts(request=_request(config=config, journal_path=None)))

    assert finding.code in refusal.detail
    assert finding.remedy in refusal.detail


def test_an_epic_recording_no_readable_attempt_refuses_the_receipt(tmp_path: Path) -> None:
    """There is nothing to receipt, which is not the same as nothing to report."""
    config = _seed(tmp_path=tmp_path, authority=AuthorityState(required_result=_RESULT))

    refusal = _refusal(record_recovery_receipts(request=_request(config=config, journal_path=None)))

    assert "records no readable causal recovery attempt" in refusal.detail


def test_a_concurrent_writer_winning_the_race_refuses_with_a_retry_instruction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale observed head is refused rather than committed over."""
    config = _seed(tmp_path=tmp_path)
    stale = StaleEpochRefusal(
        epic_id=_EPIC_ID,
        attempted_operation_id="op-loser",
        observed_epoch=1,
        winning_operation_id="op-winner",
        detail="the close was not admitted by operation op-winner",
    )
    monkeypatch.setattr(
        _plan_recovery_receipt_write,
        "commit_transition",
        lambda *, config, epic_id, request: stale,  # noqa: ARG005 -- stub matches the seam.
    )
    journal = _journal(tmp_path=tmp_path, records=(_dispatch_record(),))

    refusal = _refusal(
        record_recovery_receipts(request=_request(config=config, journal_path=journal))
    )

    assert "a concurrent writer committed from epoch 1" in refusal.detail
    assert "re-read the plan and retry" in refusal.detail


def test_a_failed_transition_finding_refuses_rather_than_reporting_a_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A chain that cannot complete its transition recorded no receipt."""
    config = _seed(tmp_path=tmp_path)
    finding = chain_fork_finding(
        epic_id=_EPIC_ID,
        token_id=_TOKEN_B,
        claimed_prior=_TOKEN_A,
        walked_from=_TOKEN_Z,
    )
    monkeypatch.setattr(
        _plan_recovery_receipt_write,
        "commit_transition",
        lambda *, config, epic_id, request: finding,  # noqa: ARG005 -- stub matches the seam.
    )
    journal = _journal(tmp_path=tmp_path, records=(_dispatch_record(),))

    refusal = _refusal(
        record_recovery_receipts(request=_request(config=config, journal_path=journal))
    )

    assert finding.code in refusal.detail


@pytest.mark.parametrize(
    "authority_record",
    [
        pytest.param(None, id="no-record"),
        pytest.param("attempt-0001", id="record-is-text"),
        pytest.param({"attempt": "a prose attempt"}, id="attempt-is-text"),
        pytest.param({"attempt": {"next_operation": f"impl:{_TARGET_ID}"}}, id="no-attempt-id"),
        pytest.param({"attempt": {"attempt_id": _ATTEMPT_ID}}, id="no-operation"),
    ],
)
def test_an_unreadable_attempt_record_reads_as_no_attempt_at_all(
    authority_record: object,
) -> None:
    """Every partial read fails CLOSED, because the id is what a receipt MATCHES.

    A half-read record would let a receipt land on an attempt nobody could
    identify, which is indistinguishable at every surface from a receipt that was
    matched correctly.
    """
    assert recorded_attempt(authority_record=authority_record) is None


def test_a_readable_attempt_record_reports_its_id_operation_and_receipts() -> None:
    """The positive control: without it, a reader refusing EVERY record passes above."""
    recorded = recorded_attempt(
        authority_record=_attempt_record(receipts=ReceiptSet(claim=f"dispatch {_DISPATCH_ID}"))
    )

    assert recorded is not None
    assert recorded.attempt_id == _ATTEMPT_ID
    assert recorded.next_operation == f"impl:{_TARGET_ID}"
    assert recorded.receipts == ReceiptSet(claim=f"dispatch {_DISPATCH_ID}")


@pytest.mark.parametrize(
    ("next_operation", "expected"),
    [
        pytest.param(f"impl:{_TARGET_ID}", _TARGET_ID, id="dispatchable-item"),
        pytest.param(f"diagnose-plan-progress:{_EPIC_ID}", None, id="read-only-diagnosis"),
        pytest.param("revise:some-topic", None, id="spec-operation"),
        pytest.param("I will try a different approach.", None, id="prose"),
        pytest.param("diagnose-this-is-not-a-supported-operation", None, id="resembles-one"),
    ],
)
def test_only_an_executable_impl_operation_names_a_dispatched_subject(
    next_operation: str,
    expected: str | None,
) -> None:
    """The stored operation is re-checked against the closed grammar, not trusted.

    It is read back out of ledger data, and a stored string is not evidence that
    it was ever validated — the two refused shapes here are the exact pair
    `_plan_recovery` measured a draft validator accepting.
    """
    assert dispatched_subject(next_operation=next_operation) == expected


@pytest.mark.parametrize(
    "records",
    [
        pytest.param((), id="no-records"),
        pytest.param((_dispatch_record(work_item_id="bd-ib-other"),), id="another-item"),
        pytest.param((_dispatch_record(dispatch_id=7),), id="non-string-dispatch-id"),
        pytest.param((_dispatch_record(dispatch_id="   "),), id="blank-dispatch-id"),
        pytest.param((_run_record(run_id="   "),), id="blank-run-id"),
        pytest.param(({"stage": "ledger-admit", "work_item_id": _TARGET_ID},), id="another-stage"),
        pytest.param(({"stage": "outcome", "outcome": "green"},), id="outcome-is-text"),
        pytest.param(
            (_outcome_record(work_item_id="bd-ib-other"),),
            id="another-items-outcome",
        ),
    ],
)
def test_no_readable_record_for_this_item_yields_no_receipt_at_all(
    records: tuple[dict[str, Any], ...],
) -> None:
    """A receipt is evidence, so an unreadable or foreign record yields none.

    The foreign-item cases are the ones worth keeping: a journal is shared by
    every item a repository dispatches, so a reader matching on the stage alone
    would credit another item's dispatch, run or terminal to this attempt.
    """
    assert execution_records(records=records, work_item_id=_TARGET_ID) == ExecutionRecords()


def test_an_attempt_boundary_is_nonempty_and_can_authorize_several_attempts() -> None:
    """One executor invocation can name each current epic attempt it authorized."""
    assert attempt_boundary_record(
        work_item_id=_TARGET_ID,
        attempt_ids=(_ATTEMPT_ID, "attempt-0002", _ATTEMPT_ID),
    ) == {
        "stage": "causal-recovery-attempt",
        "work_item_id": _TARGET_ID,
        "attempt_ids": [_ATTEMPT_ID, "attempt-0002"],
    }
    with pytest.raises(ValueError, match="^$"):
        _ = attempt_boundary_record(work_item_id=_TARGET_ID, attempt_ids=())


def test_plural_attempt_boundary_scopes_executor_records_to_each_authorized_attempt() -> None:
    """The current executor spelling binds shared work to the named attempt ids."""
    records = (
        attempt_boundary_record(
            work_item_id=_TARGET_ID,
            attempt_ids=(_ATTEMPT_ID, "attempt-0002"),
        ),
        _dispatch_record(),
        _run_record(),
        _outcome_record(),
    )

    assert (
        execution_records(
            records=records,
            work_item_id=_TARGET_ID,
            attempt_id="attempt-0002",
        ).dispatch_id
        == _DISPATCH_ID
    )
    assert (
        execution_records(
            records=records,
            work_item_id=_TARGET_ID,
            attempt_id="attempt-never-dispatched",
        )
        == ExecutionRecords()
    )


def test_impl_recovery_attempt_ids_deduplicate_matching_epics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The journal marker is one record even when multiple epics share an attempt id."""
    monkeypatch.setattr(
        _plan_recovery_receipt_write,
        "_matching_impl_attempts",
        lambda **_: ((_EPIC_ID, _ATTEMPT_ID), ("bd-ib-other", _ATTEMPT_ID)),
    )

    assert _plan_recovery_receipt_write.impl_recovery_attempt_ids(
        config=_seed(tmp_path=tmp_path),
        work_item_id=_TARGET_ID,
    ) == (_ATTEMPT_ID,)


def test_impl_executor_records_the_matching_attempts_three_durable_receipts(
    tmp_path: Path,
) -> None:
    """The executor, rather than a caller, attaches its journal evidence."""
    assert hasattr(_plan_recovery_receipt_write, "record_impl_recovery_receipts")
    config = _seed(tmp_path=tmp_path)
    journal = _journal(
        tmp_path=tmp_path,
        records=(_dispatch_record(), _run_record(), _outcome_record()),
    )

    writes = _plan_recovery_receipt_write.record_impl_recovery_receipts(
        config=config,
        work_item_id=_TARGET_ID,
        journal_path=journal,
        author="relay-session",
        now=_NOW,
    )

    assert len(writes) == 1
    write = _write(writes[0])
    assert write.status == RECEIPTS_RECORDED
    assert write.receipts == ReceiptSet(
        claim=f"dispatch {_DISPATCH_ID}",
        execution=f"fabro run {_RUN_ID}",
        outcome="green pull request 2904",
    )
    assert _recorded_receipts(config=config) == write.receipts
