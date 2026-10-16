"""Rework re-dispatch applies the ADMISSION-REQUIRED predicate, not the narrower one.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "If any potentially reachable node has no eligible candidate, the
item MUST remain ready without a claim or blocked reason ... The same predicate
governs rework admission, where the parked item stays parked without a claim."

THE NODE IS A CONDITIONAL ONE, AND THAT IS THE WHOLE POINT. `fix` is a
conditional repair node: it dominates no green terminal path, so it is NOT
success-critical, and a pre-v127 rework leg grading only the dominator set
admitted straight past an emptied `fix` chain. Every case here therefore
asserts that `fix` is ABSENT from `success_critical` before asserting anything
about the refusal -- a fixture whose emptied node happened to be
success-critical would pass against the behaviour this item replaces and prove
nothing about the widening. `test_acp_preflight_admission.py` already covers
the success-critical leg; this module exists for the node that one cannot
reach.

THE UNREACHABLE CONTROL IS WHAT MAKES THE PREDICATE A PREDICATE. A leg that
simply refused on any non-empty `exhausted` tuple would satisfy every refusal
case here. So the final case empties the SAME node while leaving it out of the
admission-required set -- the "node proven unreachable in that graph imposes no
candidate requirement" arm -- and asserts the parked row is ADMITTED. Refusal
and admission on one emptied node, told apart only by membership, is the only
shape that establishes which set governs.

"STAYS PARKED WITHOUT A CLAIM" IS ASSERTED THROUGH THE WRITES THAT MUST NOT
HAPPEN. A rework row is already `active`, so its refusal looks identical to its
admission from the row's own status -- the observable difference is the claim:
`admit_rework` takes a dispatch lock and journals `ledger-rework-admit` for a
row it admits. Both are therefore counted, and the marker is asserted
untouched, because a leg that refused the dispatch while clearing the marker
would strand the row where no later drain re-selects it.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.types import WorkItem

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_REWORK_ID = "bd-ib-rework"
_READY_ID = "bd-ib-ready"
_DOMAIN = "availability-domain"


@dataclass(frozen=True, kw_only=True)
class _Accounting:
    """The accounting verdict, stubbed so the rework leg has one marked row."""

    active_count: int = 0
    rework_pending_active_ids: tuple[str, ...] = ()
    abandoned: tuple[str, ...] = ()
    live_locked_ids: tuple[str, ...] = ()
    claimed_ids: tuple[str, ...] = ()


@dataclass(kw_only=True)
class _Writes:
    """Every claim-shaped write the rework leg could perform."""

    locks: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _item(*, item_id: str, status: str, assignee: str | None = None) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status=status,
        title=f"Item {item_id}",
        description="## Definition of Done\n\n- The product waits.\n",
        origin="freeform",
        gap_id=None,
        rank="a4",
        assignee=assignee,
        depends_on=(),
        captured_at="2026-10-15T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
        admission_policy="auto",
    )


def _verdict(*, admission_required: tuple[str, ...]) -> Any:
    """An emptied CONDITIONAL `fix` chain, held by a live domain record.

    `success_critical` deliberately omits `fix`: the dominator set for the
    committed graph is the five nodes every green path visits, and `fix` is not
    one of them.
    """
    preflight = _module(name="_acp_candidate_preflight")
    records = _module(name="_acp_hold_records")
    hold = records.AcpAvailabilityHold(
        schema_version=1,
        observation_id="obs-fix",
        scope=_DOMAIN,
        hold_key="codex",
        candidate_key=None,
        cause="quota",
        occurred_at="2026-10-15T11:55:00Z",
        expires_at="2026-10-15T12:40:00Z",
    )
    skip = preflight.SkippedCandidate(
        availability_key="codex",
        candidate_key="only",
        reason=preflight.TYPED_HOLD_SKIP,
        cause="quota",
        scope=_DOMAIN,
        hold_key="codex",
    )
    return _module(name="_acp_preflight_verdict").AcpPreflightVerdict(
        fallback_enabled=True,
        nodes=(preflight.NodePreflight(node="fix", enabled=True, candidates=(), skipped=(skip,)),),
        success_critical=("dod_gate", "implement", "proof_capture", "proof_verify", "review"),
        admission_required=admission_required,
        exhausted=("fix",) if "fix" in admission_required else (),
        holds=(hold,),
    )


def _run_admission(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    verdict: Any,
) -> tuple[Any, _Writes, list[dict[str, Any]]]:
    admission = _module(name="_dispatcher_admission")
    eligibility = _module(name="_dispatcher_admission_eligibility")
    rework = _module(name="_dispatcher_rework_admission")
    writes = _Writes()

    monkeypatch.setattr(admission, "store_config", lambda **_: tmp_path)
    monkeypatch.setattr(eligibility, "read_dispatch_labels", lambda **_: ())
    monkeypatch.setattr(
        admission,
        "claimed_active_accounting",
        lambda **_: _Accounting(rework_pending_active_ids=(_REWORK_ID,)),
    )
    monkeypatch.setattr(admission, "resolve_acp_preflight", lambda **_: verdict)

    def _record_status(*, item_id: str, **_kwargs: Any) -> None:
        writes.statuses.append(item_id)

    def _record_lock(*, repo: Path, work_item_id: str, dispatch_id: str) -> Path:
        _ = (repo, dispatch_id)
        writes.locks.append(work_item_id)
        return tmp_path / f"{work_item_id}.lock"

    monkeypatch.setattr(admission, "update_work_item_status", _record_status)
    monkeypatch.setattr(rework, "write_dispatch_lock", _record_lock)

    journal = _module(name="_dispatcher_io").JournalFile(path=tmp_path / "journal.jsonl")
    result = admission.admit_and_select(
        repo=tmp_path,
        items=[_item(item_id=_REWORK_ID, status="active", assignee="fabro")],
        candidates=[_item(item_id=_READY_ID, status="ready")],
        journal=journal,
        enforce_cap=False,
    )
    records = [
        json.loads(line)
        for line in (tmp_path / "journal.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return result, writes, records


def test_a_parked_rework_row_is_refused_for_an_emptied_conditional_node(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The widening, at the rework leg: `fix` is not success-critical."""
    verdict = _verdict(admission_required=("implement", "fix"))
    # The control that makes this the CONDITIONAL case rather than the one
    # `test_acp_preflight_admission.py` already covers.
    assert "fix" not in verdict.success_critical
    assert "fix" in verdict.admission_required

    result, _writes, records = _run_admission(
        tmp_path=tmp_path, monkeypatch=monkeypatch, verdict=verdict
    )

    stage = _module(name="_dispatcher_acp_preflight").ACP_PREFLIGHT_REFUSAL_STAGE
    assert result.rework == []
    assert result.admitted == []
    refused = {outcome.work_item_id for outcome in result.refused}
    assert refused == {_REWORK_ID, _READY_ID}
    assert [outcome.stage for outcome in result.refused] == [stage, stage]
    # Both legs name the same emptied node, from the one shared verdict.
    assert [
        record["admission_required_node"] for record in records if record.get("stage") == stage
    ] == ["fix", "fix"]


def test_the_refused_rework_row_takes_no_claim_and_keeps_its_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "The parked item stays parked without a claim."

    The dispatch lock and the `ledger-rework-admit` record are the two writes
    that constitute a rework claim, so both are asserted absent; the marker is
    asserted untouched because clearing it would strand the row.
    """
    result, writes, records = _run_admission(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        verdict=_verdict(admission_required=("implement", "fix")),
    )

    assert result.rework == []
    assert writes.locks == []
    assert writes.statuses == []
    admit_stage = _module(name="_dispatcher_rework_admission").REWORK_ADMIT_STAGE
    assert [record for record in records if record.get("stage") == admit_stage] == []
    assert (tmp_path / f"{_REWORK_ID}.lock").exists() is False


def test_an_emptied_node_outside_the_admission_required_set_admits_the_rework_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The discriminating control: MEMBERSHIP is what governs, not emptiness.

    "A node proven unreachable in that graph imposes no candidate requirement."
    The same `fix` chain is just as empty here and the same hold is just as
    live; only its admission-required membership differs, and the parked row is
    admitted with its claim taken.
    """
    verdict = _verdict(admission_required=("implement",))
    assert verdict.node_preflight(node="fix") is not None
    assert verdict.node_preflight(node="fix").exhausted is True
    assert verdict.viable is True

    result, writes, records = _run_admission(
        tmp_path=tmp_path, monkeypatch=monkeypatch, verdict=verdict
    )

    assert [item.id for item in result.rework] == [_REWORK_ID]
    assert writes.locks == [_REWORK_ID]
    admit_stage = _module(name="_dispatcher_rework_admission").REWORK_ADMIT_STAGE
    assert [record["work_item_id"] for record in records if record.get("stage") == admit_stage] == [
        _REWORK_ID
    ]
