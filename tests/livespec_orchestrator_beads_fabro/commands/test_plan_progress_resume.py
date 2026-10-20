"""The resume's durable-progress reading, at the arms a journey cannot produce.

`tests/integration/test_plan_resume_progress_scenario148.py` binds the scenario
end to end through `resume_directive`. This module covers the states no ordinary
sequence creates — a forked or unreadable authority chain — and the fail-closed
ladder that decides whether a RECORDED recovery attempt still authorizes its
operation.

THAT LADDER IS THE PART WORTH READING. The operation it returns is one an
independent consumer will EXECUTE, and it comes out of ledger data a stored
string in a comment nobody can edit afterwards. So every malformed shape must
fall back to a fresh diagnosis rather than becoming an executable action, and the
operation is re-checked against the closed grammar rather than trusted: a value
being present in the record is not evidence that it was ever validated. The
accepted case sits beside the refused ones so a ladder that rejected everything
cannot pass.
"""

from __future__ import annotations

from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _plan_progress_resume
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain_head import ChainHead
from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import (
    chain_fork_finding,
    missing_tracking_finding,
    partial_write_finding,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import AuthorityState
from livespec_orchestrator_beads_fabro.commands._plan_progress_resume import (
    TRACKING_MISSING,
    TRACKING_UNOBSERVABLE,
    ResumeProgress,
    diagnosis_operation,
    evaluate_resume_progress,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_EPIC_ID = "bd-ib-progressepic"
_TARGET_ID = "bd-ib-progresstarget"
_NOW = "2026-10-15T09:00:00Z"
_IMPL_ACTION = f"impl:{_TARGET_ID}"
_TOKEN_A = "chain-record-a"
_TOKEN_B = "chain-record-b"
_TOKEN_Z = "chain-record-z"
_TOKEN_GENESIS = "chain-record-genesis"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="t", prefix="bd-ib", server_user="u", database="d", bd_path="bd", fake=True
    )


def _progress(*, finding: object, monkeypatch: pytest.MonkeyPatch) -> ResumeProgress:
    monkeypatch.setattr(
        _plan_progress_resume,
        "authorized_head",
        lambda *, config, epic_id: finding,  # noqa: ARG005 -- stub matches the seam.
    )
    return evaluate_resume_progress(config=_config(), epic_id=_EPIC_ID, now=_NOW)


def test_a_missing_chain_reports_missing_tracking_and_still_permits_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A legacy plan has no obligation to withhold — it has none at all.

    "Legacy three-key pointers MUST remain readable, report
    `plan-progress-tracking: missing`" — withholding here would strand every
    unmigrated plan behind a finding rather than reporting one.
    """
    progress = _progress(
        finding=missing_tracking_finding(epic_id=_EPIC_ID),
        monkeypatch=monkeypatch,
    )

    assert progress.dispatch is True
    assert progress.authorized_action is None
    assert progress.findings[0].startswith(TRACKING_MISSING)
    assert "migrate-plan-records" in progress.findings[0]
    assert "next_action write carrying required_result and budget" not in progress.findings[0]


@pytest.mark.parametrize(
    "finding",
    [
        chain_fork_finding(
            epic_id=_EPIC_ID,
            token_id=_TOKEN_B,
            claimed_prior=_TOKEN_A,
            walked_from=_TOKEN_Z,
        ),
        partial_write_finding(epic_id=_EPIC_ID, detail="a writer stopped after its close"),
    ],
)
def test_an_unreadable_chain_is_unobservable_rather_than_missing(
    finding: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The obligation EXISTS and this reader could not measure it.

    Collapsing these onto the missing finding would tell an operator with a
    forked chain or an unreconciled partial write to run a migration — and
    "A partial write MUST be diagnosable and must not authorize a fresh
    dispatch until reconciled", so dispatch is withheld here and not there.
    """
    progress = _progress(finding=finding, monkeypatch=monkeypatch)

    assert progress.dispatch is False
    assert progress.authorized_action == diagnosis_operation(epic_id=_EPIC_ID)
    assert progress.findings[0].startswith(TRACKING_UNOBSERVABLE)
    assert TRACKING_MISSING not in progress.findings[0]


def test_a_chain_that_exists_but_tracks_no_obligation_names_the_pointer_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The state the sanctioned migration leaves behind, before any obligation.

    The chain is healthy and its authority is empty, which is NOT a legacy
    pointer and NOT a broken chain — there is simply nothing tracked yet. It
    permits dispatch for the same reason the legacy arm does, an obligation
    that does not exist cannot have expired; but its REMEDY is the executable
    pointer write rather than the migration, which has already run here and
    whose second run creates nothing. The open token is named because that is
    the checkable form of "the chain is present".
    """
    progress = _progress(
        finding=ChainHead(
            current_token_id=_TOKEN_GENESIS,
            latest_closed_token_id=None,
            epoch=0,
            authority=AuthorityState(),
        ),
        monkeypatch=monkeypatch,
    )

    assert progress.dispatch is True
    assert progress.authorized_action is None
    assert progress.findings[0].startswith(TRACKING_MISSING)
    assert _TOKEN_GENESIS in progress.findings[0]
    assert "next_action write carrying required_result and budget" in progress.findings[0]
    assert "migrate-plan-records" not in progress.findings[0]


def _attempt(**overrides: object) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "attempt_id": "attempt-0001",
        "previous_epoch": 1,
        "cause": "host",
        "failure_evidence": "the provider returned usageLimitExceeded",
        "next_operation": _IMPL_ACTION,
        "attempt_deadline": "2099-01-01T00:00:00Z",
        "recorded_at": "2026-10-15T08:00:00Z",
        "claim_receipt": None,
        "execution_receipt": None,
        "outcome_receipt": None,
    }
    fields.update(overrides)
    return fields


def _bounded(*, record: object) -> tuple[str, str, str] | None:
    return _plan_progress_resume._bounded_attempt(  # noqa: SLF001 -- the fail-closed ladder.
        authority_record=record,
        now=_NOW,
    )


def test_a_well_formed_bounded_attempt_authorizes_its_own_operation() -> None:
    """The POSITIVE case, without which every refusal below is vacuous."""
    assert _bounded(record={"attempt": _attempt(), "item_attributable_attempts": 0}) == (
        "attempt-0001",
        _IMPL_ACTION,
        "2099-01-01T00:00:00Z",
    )


@pytest.mark.parametrize(
    ("label", "record"),
    [
        ("not a record", "attempt-0001"),
        ("no attempt key", {"item_attributable_attempts": 0}),
        ("attempt is not an object", {"attempt": "attempt-0001"}),
        ("absent attempt id", {"attempt": _attempt(attempt_id=None)}),
        ("blank attempt id", {"attempt": _attempt(attempt_id="   ")}),
        ("absent operation", {"attempt": _attempt(next_operation=None)}),
        ("prose operation", {"attempt": _attempt(next_operation="I will try again.")}),
        (
            "unsupported operation",
            {"attempt": _attempt(next_operation="diagnose-not-a-real-operation")},
        ),
        ("absent bound", {"attempt": _attempt(attempt_deadline=None)}),
        ("unreadable bound", {"attempt": _attempt(attempt_deadline="not-an-instant")}),
        ("elapsed bound", {"attempt": _attempt(attempt_deadline="2026-10-14T09:00:00Z")}),
        ("bound exactly at now", {"attempt": _attempt(attempt_deadline=_NOW)}),
    ],
)
def test_every_unusable_recorded_attempt_authorizes_nothing(
    label: str,
    record: object,
) -> None:
    """Each arm falls back to a fresh diagnosis rather than to an action.

    The prose and unsupported-operation rows are the load-bearing pair: the
    record is well-formed and the string is simply not an operation, which is
    the shape that would reach a consumer as something to run. The
    exactly-at-now row fixes the bound as INCLUSIVE, matching every other
    deadline in this tree.
    """
    assert _bounded(record=record) is None, label
