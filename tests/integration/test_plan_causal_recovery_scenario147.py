"""Scenario 147 — an expired obligation reopens only through typed causal recovery.

`contracts.md` section "Required result, budget and progress epoch": "After
expiry, same-obligation continuation MUST be refused before appending a handoff
or updating the pointer unless a fresh typed causal recovery attempt is supplied
or a genuine required human decision is recorded. Neither path resets or
postpones the original obligation deadline." And: "A changed approach MUST be a
typed causal recovery event naming the unresolved obligation, previous epoch,
measured failure evidence, cause classification, executable authorized next
operation, stable unique attempt id and bounded attempt deadline. A prose
`approach:` line, acknowledgment, repair-child milestone or cosmetic pointer
rewrite MUST NOT qualify."

THE TWO MEASURED DEFECTS THIS MODULE EXISTS TO CLOSE, both recorded on
`bd-ib-zi5ygh` from a read-only probe of the terminal run's draft validator:
`next_operation="I will try a different approach."` with `cause="host"` was
ACCEPTED, and `next_operation="diagnose-this-is-not-a-supported-operation"` with
`cause="unknown"` was ACCEPTED. Both are asserted here as refusals, and a REAL
SUPPORTED operation is asserted as an acceptance beside them — without that
positive case a validator that refused everything would satisfy both negatives.

WHY BOTH GATES ARE EXERCISED SEPARATELY. The draft validator treated EQUALITY
with a caller-derived operation as authorization, so a caller who authored the
operation authorized itself. Refusal now needs two independent things to hold:
the operation must be in the CLOSED grammar of operations this fleet can
actually execute, and it must equal the one AUTHORIZED for the measured cause.
The `spec-op` case below is the one that separates them — it supplies a
`next_operation` equal to the pointer's own `ref`, which satisfies equality
exactly as the defect did.

A RECORDED ATTEMPT IS NOT AN EXECUTION, and the last case asserts that directly:
a fresh attempt may carry no claim, execution or outcome receipt, because
"recording it is not evidence that the command executed or that the target was
fulfilled" and "Claim, execution and outcome receipts MUST remain distinct".
"""

from __future__ import annotations

import importlib
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
    read_chain_head,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import (
    PLAN_PROGRESS_PREFIX,
    chain_cache_metadata,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import create_token
from livespec_orchestrator_beads_fabro.commands._plan_handoff import append_handoff
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    NextAction,
    set_next_action,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_PROJECT_NAME = "repo"
_EPIC_ID = "bd-ib-relayrecovery"
_TARGET_ID = "bd-ib-recoverytarget"
_ORIGINAL_DEADLINE = "2026-10-14T09:00:00Z"
_AFTER_DEADLINE = "2026-10-15T09:00:00Z"
_ATTEMPT_DEADLINE = "2026-10-15T12:00:00Z"
_BEFORE_DEADLINE = "2026-10-13T09:00:00Z"
_EVIDENCE = "hp run 01M4HQQZJCNP5HZ89M80PYCHXK ended: provider usageLimitExceeded at 18:13:14Z"
_MODULE = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_plan_recovery.py"
)


@pytest.fixture(autouse=True)
def _hermetic_backend(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _recovery_module() -> Any:
    """Import the recovery module, proving it exists before reaching for it.

    The `is_file` assertion is the genuine first failure at Red: a top-level
    import of a module that does not exist yet would die at COLLECTION, which
    proves only unimportability rather than that the behaviour is unimplemented.
    """
    assert _MODULE.is_file(), f"{_MODULE} does not exist"
    return importlib.import_module("livespec_orchestrator_beads_fabro.commands._plan_recovery")


def _fake(*, config: StoreConfig) -> FakeBeadsClient:
    client = make_beads_client(config=config)
    assert isinstance(client, FakeBeadsClient)
    return client


def _required_result() -> dict[str, object]:
    return {
        "repo": _PROJECT_NAME,
        "item_status": {"item_id": _TARGET_ID, "status": "done"},
    }


def _action(
    *,
    kind: str = "impl",
    ref: str = _TARGET_ID,
    deadline: str = _ORIGINAL_DEADLINE,
    max_handoffs: int = 5,
) -> NextAction:
    return NextAction(
        kind=kind,
        ref=ref,
        text="Keep going.",
        required_result=_required_result(),
        budget={"deadline": deadline, "max_handoffs": max_handoffs},
    )


def _seed(*, tmp_path: Path, max_handoffs: int = 5) -> StoreConfig:
    """A plan epic holding an ESTABLISHED, still-live obligation.

    `max_handoffs` is the ceiling the ESTABLISHING write records, which is the
    only write that can set it: every later write preserves the original, so a
    case about the ceiling has to establish the ceiling it then exhausts.
    """
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
    genesis = create_token(client=fake)
    fake.update_issue(
        issue_id=_EPIC_ID,
        metadata=chain_cache_metadata(
            existing_metadata={"rank": "a0"},
            latest_closed=None,
            current=genesis,
        ),
    )
    assert (
        set_next_action(
            config=config,
            epic_id=_EPIC_ID,
            action=_action(max_handoffs=max_handoffs),
            session="relay-session",
            now=_BEFORE_DEADLINE,
        )
        is None
    )
    return config


def _authority(*, config: StoreConfig) -> Any:
    head = read_chain_head(config=config, epic_id=_EPIC_ID)
    assert isinstance(head, ChainHead), head
    return head.authority


def _handoff_comments(*, config: StoreConfig) -> list[dict[str, Any]]:
    return [
        comment
        for comment in _fake(config=config).list_comments(issue_id=_EPIC_ID)
        if not str(comment.get("text", "")).startswith(PLAN_PROGRESS_PREFIX)
    ]


def _recovery(
    *,
    cause: str,
    next_operation: str,
    previous_epoch: int | None = None,
    attempt_id: str = "attempt-0001",
    **overrides: object,
) -> Any:
    module = _recovery_module()
    fields: dict[str, object] = {
        "required_result": _required_result(),
        "previous_epoch": 1 if previous_epoch is None else previous_epoch,
        "failure_evidence": _EVIDENCE,
        "cause": cause,
        "next_operation": next_operation,
        "attempt_id": attempt_id,
        "attempt_deadline": _ATTEMPT_DEADLINE,
    }
    fields.update(overrides)
    return module.CausalRecovery(**fields)


def test_an_expired_obligation_refuses_plain_continuation_before_any_write(
    tmp_path: Path,
) -> None:
    """The deadline has passed and no recovery is supplied, so nothing is written.

    The comment count is asserted because the refusal is required BEFORE the
    handoff is appended — a writer that appended first and refused afterwards
    would leave the entry on the timeline permanently.
    """
    config = _seed(tmp_path=tmp_path)
    comments_before = len(_handoff_comments(config=config))

    refusal = append_handoff(
        config=config,
        epic_id=_EPIC_ID,
        body="Still working on it.",
        author="relay-session",
        now=_AFTER_DEADLINE,
        next_action=_action(),
    )

    assert refusal is not None
    assert "expired" in refusal.detail
    assert len(_handoff_comments(config=config)) == comments_before
    assert _authority(config=config).consumed_handoffs == 0


def test_an_exhausted_handoff_ceiling_refuses_the_next_continuation(
    tmp_path: Path,
) -> None:
    """The other limit, reached exactly: "when accepted handoffs reach
    max_handoffs, the next continuation is expired".

    The ceiling of 2 is set by the ESTABLISHING write, because a later write
    cannot lower it — and the clock is deliberately left unexpired throughout,
    so the refusal can only come from the count.
    """
    config = _seed(tmp_path=tmp_path, max_handoffs=2)
    for index in range(2):
        assert (
            append_handoff(
                config=config,
                epic_id=_EPIC_ID,
                body=f"Handoff {index}.",
                author="relay-session",
                now=_BEFORE_DEADLINE,
                next_action=_action(max_handoffs=2),
            )
            is None
        )
    assert _authority(config=config).consumed_handoffs == 2

    refusal = append_handoff(
        config=config,
        epic_id=_EPIC_ID,
        body="One more.",
        author="relay-session",
        now=_BEFORE_DEADLINE,
        next_action=_action(max_handoffs=2),
    )

    assert refusal is not None
    assert "expired" in refusal.detail


def test_prose_passed_as_the_next_operation_is_refused(tmp_path: Path) -> None:
    """The first measured defect: this exact string was ACCEPTED by the draft.

    A changed-approach sentence is not an executable operation, and "A prose
    `approach:` line ... MUST NOT qualify".
    """
    config = _seed(tmp_path=tmp_path)

    refusal = append_handoff(
        config=config,
        epic_id=_EPIC_ID,
        body="Trying something else.",
        author="relay-session",
        now=_AFTER_DEADLINE,
        next_action=_action(),
        recovery=_recovery(cause="host", next_operation="I will try a different approach."),
    )

    assert refusal is not None
    assert "executable" in refusal.detail
    assert _authority(config=config).consumed_handoffs == 0


def test_an_unsupported_diagnose_prefixed_operation_is_refused(tmp_path: Path) -> None:
    """The second measured defect: a `diagnose-` prefix is not authorization.

    "A non-empty string or a `diagnose-` prefix is not enough." The operation
    has the shape of a diagnosis and names nothing this fleet can execute.
    """
    config = _seed(tmp_path=tmp_path)

    refusal = append_handoff(
        config=config,
        epic_id=_EPIC_ID,
        body="Diagnosing.",
        author="relay-session",
        now=_AFTER_DEADLINE,
        next_action=_action(),
        recovery=_recovery(
            cause="unknown",
            next_operation="diagnose-this-is-not-a-supported-operation",
        ),
    )

    assert refusal is not None
    assert "executable" in refusal.detail


def test_an_operation_equal_to_a_caller_authored_ref_is_still_refused(
    tmp_path: Path,
) -> None:
    """Equality with a caller-derived operation must not be authorization.

    This is the shape the draft validator mistook for authorization: the
    `next_operation` is exactly the pointer's own `ref`, so any equality test
    passes. The closed grammar is what refuses it.
    """
    config = _seed(tmp_path=tmp_path)
    prose_ref = "I will try a different approach."

    refusal = append_handoff(
        config=config,
        epic_id=_EPIC_ID,
        body="Self-authored operation.",
        author="relay-session",
        now=_AFTER_DEADLINE,
        next_action=_action(kind="spec-op", ref=prose_ref),
        recovery=_recovery(cause="host", next_operation=prose_ref),
    )

    assert refusal is not None


def test_an_unknown_cause_authorizes_the_real_diagnosis_operation(
    tmp_path: Path,
) -> None:
    """The POSITIVE control, and the one that makes the refusals meaningful.

    "Unknown causes require diagnosis". The authorized operation is the real
    `diagnose-plan-progress:<epic>` action the drive surface executes, and the
    write is admitted while the ORIGINAL deadline stands unchanged.
    """
    config = _seed(tmp_path=tmp_path)

    refusal = append_handoff(
        config=config,
        epic_id=_EPIC_ID,
        body="Cause is not yet established; diagnosing.",
        author="relay-session",
        now=_AFTER_DEADLINE,
        next_action=_action(),
        recovery=_recovery(
            cause="unknown",
            next_operation=f"diagnose-plan-progress:{_EPIC_ID}",
        ),
    )

    assert refusal is None, refusal
    authority = _authority(config=config)
    assert authority.original_deadline == _ORIGINAL_DEADLINE
    assert authority.max_handoffs == 5


def test_a_host_cause_authorizes_the_pointers_own_bounded_operation(
    tmp_path: Path,
) -> None:
    """ "known host causes require bounded host recovery".

    The authorized operation is the pointer's own executable operation, re-run
    under the attempt's bound — and the original obligation deadline survives it.
    """
    config = _seed(tmp_path=tmp_path)

    refusal = append_handoff(
        config=config,
        epic_id=_EPIC_ID,
        body="Provider limit measured; re-running bounded.",
        author="relay-session",
        now=_AFTER_DEADLINE,
        next_action=_action(),
        recovery=_recovery(cause="host", next_operation=f"impl:{_TARGET_ID}"),
    )

    assert refusal is None, refusal
    assert _authority(config=config).original_deadline == _ORIGINAL_DEADLINE


def test_a_recovery_attempt_never_postpones_the_original_deadline(
    tmp_path: Path,
) -> None:
    """The attempt is bounded SEPARATELY and the obligation keeps its own clock.

    The attempt deadline here is LATER than the obligation's, which is the
    shape that would extend it if the two were conflated.
    """
    config = _seed(tmp_path=tmp_path)

    assert (
        append_handoff(
            config=config,
            epic_id=_EPIC_ID,
            body="Bounded recovery.",
            author="relay-session",
            now=_AFTER_DEADLINE,
            next_action=_action(deadline="2099-01-01T00:00:00Z", max_handoffs=99),
            recovery=_recovery(cause="host", next_operation=f"impl:{_TARGET_ID}"),
        )
        is None
    )

    authority = _authority(config=config)
    assert authority.original_deadline == _ORIGINAL_DEADLINE
    assert authority.max_handoffs == 5
    # The obligation is STILL expired after the attempt: recovery authorizes one
    # bounded attempt, it does not reopen the budget.
    refusal = append_handoff(
        config=config,
        epic_id=_EPIC_ID,
        body="And again, with nothing new.",
        author="relay-session",
        now=_AFTER_DEADLINE,
        next_action=_action(),
    )
    assert refusal is not None
    assert "expired" in refusal.detail


def test_a_stale_previous_epoch_is_refused_as_a_replayed_attempt(
    tmp_path: Path,
) -> None:
    """ "an old attempt ... cannot reset the budget".

    The attempt names an epoch the chain has already moved past, which is what
    a replayed recovery record looks like.
    """
    config = _seed(tmp_path=tmp_path)

    refusal = append_handoff(
        config=config,
        epic_id=_EPIC_ID,
        body="Replayed attempt.",
        author="relay-session",
        now=_AFTER_DEADLINE,
        next_action=_action(),
        recovery=_recovery(
            cause="host",
            next_operation=f"impl:{_TARGET_ID}",
            previous_epoch=0,
        ),
    )

    assert refusal is not None
    assert "epoch" in refusal.detail


def test_a_fresh_attempt_asserting_an_execution_receipt_is_refused(
    tmp_path: Path,
) -> None:
    """ "Claim, execution and outcome receipts MUST remain distinct."

    Registering an attempt is not evidence that its command ran, so an attempt
    that arrives already claiming it did is refused rather than recorded.
    """
    config = _seed(tmp_path=tmp_path)

    refusal = append_handoff(
        config=config,
        epic_id=_EPIC_ID,
        body="Attempt claiming its own execution.",
        author="relay-session",
        now=_AFTER_DEADLINE,
        next_action=_action(),
        recovery=_recovery(
            cause="host",
            next_operation=f"impl:{_TARGET_ID}",
            execution_receipt="I already ran it.",
        ),
    )

    assert refusal is not None
    assert "receipt" in refusal.detail


def test_recovery_supplied_to_an_unexpired_obligation_is_refused(
    tmp_path: Path,
) -> None:
    """There is nothing to recover from, so the attempt is not admitted.

    Admitting one would let a session bank recovery attempts against a healthy
    obligation and spend them later.
    """
    config = _seed(tmp_path=tmp_path)

    refusal = append_handoff(
        config=config,
        epic_id=_EPIC_ID,
        body="Premature recovery.",
        author="relay-session",
        now=_BEFORE_DEADLINE,
        next_action=_action(),
        recovery=_recovery(cause="host", next_operation=f"impl:{_TARGET_ID}"),
    )

    assert refusal is not None
    assert "not expired" in refusal.detail


def test_an_unrecognized_cause_classification_is_refused(tmp_path: Path) -> None:
    """The cause set is closed, so an invented classification earns nothing."""
    config = _seed(tmp_path=tmp_path)

    refusal = append_handoff(
        config=config,
        epic_id=_EPIC_ID,
        body="Invented cause.",
        author="relay-session",
        now=_AFTER_DEADLINE,
        next_action=_action(),
        recovery=_recovery(cause="vibes", next_operation=f"impl:{_TARGET_ID}"),
    )

    assert refusal is not None
    assert "cause" in refusal.detail


def test_an_attempt_with_no_measured_failure_evidence_is_refused(
    tmp_path: Path,
) -> None:
    """ "measured failure evidence" is required, so an empty one is not an attempt."""
    config = _seed(tmp_path=tmp_path)

    refusal = append_handoff(
        config=config,
        epic_id=_EPIC_ID,
        body="No evidence.",
        author="relay-session",
        now=_AFTER_DEADLINE,
        next_action=_action(),
        recovery=_recovery(
            cause="host",
            next_operation=f"impl:{_TARGET_ID}",
            failure_evidence="   ",
        ),
    )

    assert refusal is not None
    assert "evidence" in refusal.detail


def test_an_attempt_deadline_already_passed_is_refused(tmp_path: Path) -> None:
    """A bound that has already elapsed bounds nothing."""
    config = _seed(tmp_path=tmp_path)

    refusal = append_handoff(
        config=config,
        epic_id=_EPIC_ID,
        body="Elapsed bound.",
        author="relay-session",
        now=_AFTER_DEADLINE,
        next_action=_action(),
        recovery=_recovery(
            cause="host",
            next_operation=f"impl:{_TARGET_ID}",
            attempt_deadline=_BEFORE_DEADLINE,
        ),
    )

    assert refusal is not None
    assert "attempt deadline" in refusal.detail


def test_host_and_unknown_causes_leave_the_item_repetition_count_alone(
    tmp_path: Path,
) -> None:
    """ "neither increments or resets the item-attributable repetition count".

    An item-attributable cause DOES increment it, which is the contrast that
    makes the other two readings mean something.
    """
    config = _seed(tmp_path=tmp_path)
    module = _recovery_module()

    for index, cause in enumerate(("host", "unknown")):
        operation = (
            f"impl:{_TARGET_ID}" if cause == "host" else f"diagnose-plan-progress:{_EPIC_ID}"
        )
        assert (
            append_handoff(
                config=config,
                epic_id=_EPIC_ID,
                body=f"Attempt under {cause}.",
                author="relay-session",
                now=_AFTER_DEADLINE,
                next_action=_action(),
                recovery=_recovery(
                    cause=cause,
                    next_operation=operation,
                    previous_epoch=1 + index,
                    attempt_id=f"attempt-{cause}",
                ),
            )
            is None
        )
        assert module.item_attributable_attempts(authority=_authority(config=config)) == 0, cause

    assert (
        append_handoff(
            config=config,
            epic_id=_EPIC_ID,
            body="Attempt under item.",
            author="relay-session",
            now=_AFTER_DEADLINE,
            next_action=_action(),
            recovery=_recovery(
                cause="item",
                next_operation=f"impl:{_TARGET_ID}",
                previous_epoch=3,
                attempt_id="attempt-item",
            ),
        )
        is None
    )

    assert module.item_attributable_attempts(authority=_authority(config=config)) == 1
