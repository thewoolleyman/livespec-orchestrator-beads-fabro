"""Pure decision surface of the pre-push ledger-conformance gate.

The IO wiring (the `--gate` CLI flag, the in-place per-remap heal writes/prints,
the fail-soft could-not-check path, the projection-not-reload residual
computation) lives in the sibling `test_dispatcher_ledger_gate_cli.py`. This
file covers the PURE `decide_ledger_gate` verdict function and the residual
message it builds from the heal COUNT + residual findings: clean, healed-only,
residual-only, both, and the skipped-severity filter — each a total function of
the count + findings, with no tenant read and no write.
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


def _residual(*, item_id: str, status: str) -> LedgerFinding:
    return LedgerFinding(
        check="status-conformance",
        item_id=item_id,
        message=f"status {status!r} is outside the livespec lifecycle (allowed: backlog)",
    )


def test_clean_ledger_exits_zero_with_clean_marker() -> None:
    decision = decide_ledger_gate(healed_count=0, residual=[])

    assert isinstance(decision, LedgerGateDecision)
    assert decision.exit_code == 0
    assert decision.message.startswith(LEDGER_GATE_CLEAN_MARKER)
    assert "ledger conformant" in decision.message


def test_healed_only_exits_zero_with_healed_marker_and_no_block() -> None:
    decision = decide_ledger_gate(healed_count=2, residual=[])

    # Auto-mappable remaps were applied in place (printed by the IO layer as they
    # were written); the verdict is exit 0 with the loud HEALED marker + count,
    # and never the block marker or the human-decision remedy.
    assert decision.exit_code == 0
    assert decision.message.startswith(LEDGER_GATE_HEALED_MARKER)
    assert "healed 2" in decision.message
    assert LEDGER_GATE_DRIFT_MARKER not in decision.message
    assert "bd update" not in decision.message


def test_residual_only_exits_one_with_human_decision_message() -> None:
    residual = [_residual(item_id="stuck-deferred", status="deferred")]

    decision = decide_ledger_gate(healed_count=0, residual=residual)

    assert decision.exit_code == 1
    assert decision.message.startswith(LEDGER_GATE_DRIFT_MARKER)
    assert "human lane" in decision.message
    assert "stuck-deferred" in decision.message
    assert "bd update <id> --status" in decision.message
    # It must tell the operator normalize will NOT fix residual rows, so an
    # agent never loops re-running it.
    assert "will NOT fix these" in decision.message
    # A residual-only verdict never claims the HEALED marker.
    assert LEDGER_GATE_HEALED_MARKER not in decision.message


def test_both_healed_and_residual_blocks_on_residual() -> None:
    residual = [_residual(item_id="stuck-hooked", status="hooked")]

    decision = decide_ledger_gate(healed_count=1, residual=residual)

    # A remap was applied (printed by the IO layer) but the residual row still
    # blocks the push: exit 1, the DRIFT block + the residual remedy.
    assert decision.exit_code == 1
    assert decision.message.startswith(LEDGER_GATE_DRIFT_MARKER)
    assert "stuck-hooked" in decision.message
    assert "bd update <id> --status" in decision.message


def test_skipped_severity_residual_is_not_confirmed_drift() -> None:
    skipped = LedgerFinding(
        check="status-conformance",
        item_id="probe-skip",
        message="precondition unmet",
        severity="skipped",
    )

    decision = decide_ledger_gate(healed_count=0, residual=[skipped])

    assert decision.exit_code == 0
    assert decision.message.startswith(LEDGER_GATE_CLEAN_MARKER)
