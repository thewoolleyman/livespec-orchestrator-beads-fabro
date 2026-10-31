"""The tracked causal-recovery receipt-transition proof command."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from types import FunctionType

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._plan_recovery_receipt_write import (
    RecoveryReceiptWrite,
)
from livespec_orchestrator_beads_fabro.commands._plan_recovery_receipts import (
    ReceiptRefusal,
    ReceiptSet,
)


def _source() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
        / "receipt_transition_reproduction.py"
    )


def _helpers() -> dict[str, object]:
    return runpy.run_path(str(Path(__file__).with_name("test_plan_recovery_receipts.py")))


def _unexpected_write() -> RecoveryReceiptWrite:
    return RecoveryReceiptWrite(
        attempt_id="unexpected-attempt",
        receipts=ReceiptSet(),
        status="unexpected-status",
        epoch=0,
        idempotent=False,
    )


def _function(name: str) -> FunctionType:
    function = runpy.run_path(str(_source()))[name]
    assert isinstance(function, FunctionType)
    return function


def test_receipt_transition_reproducer_reports_committed_receipts_and_invariants(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A fresh replay can materialize and execute the tracked proof command."""
    source = _source()
    assert source.is_file()
    main = runpy.run_path(str(source))["main"]
    assert callable(main)
    main()

    executed, undispatched = (json.loads(line) for line in capsys.readouterr().out.splitlines())
    assert executed["receipts"] == {
        "claim": "dispatch dispatch-77",
        "execution": "fabro run 01M4RECEIPTRUN",
        "outcome": "green pull request 2904",
    }
    assert executed["authority_invariants"] == {
        "consumed_handoffs": 3,
        "epoch_advanced": True,
        "item_attributable_attempts": 2,
        "original_deadline": "2026-10-20T09:00:00Z",
    }
    assert undispatched == {
        "historical_records_not_inherited": True,
        "undispatched_receipts": {"claim": None, "execution": None, "outcome": None},
        "undispatched_status": "recorded-but-not-executed",
    }


def test_receipt_transition_reproducer_refuses_an_unreadable_authority_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The behavior command fails closed when the authority read cannot be trusted."""
    transition = _function("_print_executed_transition")
    monkeypatch.setitem(transition.__globals__, "read_chain_head", lambda **_kwargs: object())

    with pytest.raises(TypeError, match="unreadable"):
        transition(helpers=_helpers())

    reset_fake_singleton()


def test_receipt_transition_reproducer_refuses_a_receipt_write_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refusal from the tracked write does not become fabricated evidence."""
    transition = _function("_print_executed_transition")
    monkeypatch.setitem(
        transition.__globals__,
        "record_recovery_receipts",
        lambda **_kwargs: ReceiptRefusal(detail="receipt write refused"),
    )

    with pytest.raises(TypeError, match="receipt write refused"):
        transition(helpers=_helpers())

    reset_fake_singleton()


def test_receipt_transition_reproducer_refuses_an_unexpected_receipt_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A write with the wrong terminal state cannot pass as executed evidence."""
    transition = _function("_print_executed_transition")
    monkeypatch.setitem(
        transition.__globals__,
        "record_recovery_receipts",
        lambda **_kwargs: _unexpected_write(),
    )

    with pytest.raises(RuntimeError, match="did not record"):
        transition(helpers=_helpers())

    reset_fake_singleton()


def test_receipt_transition_reproducer_refuses_a_later_unexpected_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The undispatched leg also fails closed if its durable status changes."""
    transition = _function("_print_later_undispatched_attempt")
    monkeypatch.setitem(
        transition.__globals__,
        "record_recovery_receipts",
        lambda **_kwargs: _unexpected_write(),
    )

    with pytest.raises(RuntimeError, match="marked executed"):
        transition(helpers=_helpers())

    reset_fake_singleton()


def test_receipt_transition_reproducer_refuses_a_later_receipt_write_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The later-attempt read also refuses an uncommitted receipt write."""
    transition = _function("_print_later_undispatched_attempt")
    monkeypatch.setitem(
        transition.__globals__,
        "record_recovery_receipts",
        lambda **_kwargs: ReceiptRefusal(detail="later receipt write refused"),
    )

    with pytest.raises(TypeError, match="later receipt write refused"):
        transition(helpers=_helpers())

    reset_fake_singleton()
