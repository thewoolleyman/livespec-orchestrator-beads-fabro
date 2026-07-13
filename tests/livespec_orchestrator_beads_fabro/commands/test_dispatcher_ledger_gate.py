"""Pure decision surface of the pre-push ledger-conformance gate.

The IO wiring (the `--gate` CLI flag, the in-place heal write, the fail-soft
could-not-check path) lives in the sibling `test_dispatcher_ledger_gate_cli.py`.
This file covers the PURE `decide_ledger_gate` verdict function and the
case-aware message it builds from the ALREADY-APPLIED remaps + residual
findings: clean, healed-only, residual-only, both, and the skipped-severity
filter — each a total function of the healed remaps + residual findings, with no
tenant read and no write.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_checks import LedgerFinding
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_gate import (
    LEDGER_GATE_CLEAN_MARKER,
    LEDGER_GATE_DRIFT_MARKER,
    LEDGER_GATE_HEALED_MARKER,
    LedgerGateDecision,
    decide_ledger_gate,
)


def _remap(*, item_id: str, from_status: str, to_status: str) -> dict[str, str]:
    return {"item_id": item_id, "from": from_status, "to": to_status, "reason": "native"}


def _residual(*, item_id: str, status: str) -> LedgerFinding:
    return LedgerFinding(
        check="status-conformance",
        item_id=item_id,
        message=f"status {status!r} is outside the livespec lifecycle (allowed: backlog)",
    )


def test_clean_ledger_exits_zero_with_clean_marker() -> None:
    decision = decide_ledger_gate(healed=[], residual=[])

    assert isinstance(decision, LedgerGateDecision)
    assert decision.exit_code == 0
    assert decision.message.startswith(LEDGER_GATE_CLEAN_MARKER)
    assert "ledger conformant" in decision.message


def test_healed_only_exits_zero_with_healed_marker_and_no_block() -> None:
    healed = [_remap(item_id="native-open", from_status="open", to_status="backlog")]

    decision = decide_ledger_gate(healed=healed, residual=[])

    # An auto-mappable remap is applied in place and the push proceeds: exit 0,
    # the loud HEALED marker + the applied remap, and never the block marker.
    assert decision.exit_code == 0
    assert decision.message.startswith(LEDGER_GATE_HEALED_MARKER)
    assert "native-open: open -> backlog" in decision.message
    assert LEDGER_GATE_DRIFT_MARKER not in decision.message
    # A healed-only case must NOT emit the human-decision `bd update` remedy.
    assert "bd update" not in decision.message


def test_residual_only_exits_one_with_human_decision_message() -> None:
    residual = [_residual(item_id="stuck-deferred", status="deferred")]

    decision = decide_ledger_gate(healed=[], residual=residual)

    assert decision.exit_code == 1
    assert decision.message.startswith(LEDGER_GATE_DRIFT_MARKER)
    assert "human lane" in decision.message
    assert "stuck-deferred" in decision.message
    assert "bd update <id> --status" in decision.message
    # It must tell the operator normalize will NOT fix residual rows, so an
    # agent never loops re-running it.
    assert "will NOT fix these" in decision.message
    # A residual-only case names no healed remap section.
    assert LEDGER_GATE_HEALED_MARKER not in decision.message


def test_both_heals_the_mappable_and_blocks_on_residual() -> None:
    healed = [_remap(item_id="raw-claim", from_status="in_progress", to_status="active")]
    residual = [_residual(item_id="stuck-hooked", status="hooked")]

    decision = decide_ledger_gate(healed=healed, residual=residual)

    # The mappable remap is applied (printed loud) but the residual row still
    # blocks the push: exit 1, both sections present.
    assert decision.exit_code == 1
    assert decision.message.startswith(LEDGER_GATE_DRIFT_MARKER)
    assert "raw-claim: in_progress -> active" in decision.message
    assert "stuck-hooked" in decision.message
    assert "bd update <id> --status" in decision.message


def test_skipped_severity_residual_is_not_confirmed_drift() -> None:
    skipped = LedgerFinding(
        check="status-conformance",
        item_id="probe-skip",
        message="precondition unmet",
        severity="skipped",
    )

    decision = decide_ledger_gate(healed=[], residual=[skipped])

    assert decision.exit_code == 0
    assert decision.message.startswith(LEDGER_GATE_CLEAN_MARKER)
