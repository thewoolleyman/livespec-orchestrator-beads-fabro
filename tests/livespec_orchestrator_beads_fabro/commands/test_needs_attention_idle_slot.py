"""Coverage for the one `hygiene:idle-slot` row the finding composes.

The audit itself is substituted here, because this module's whole subject is
the ROW: which fields it carries, that it is exactly one, and that it clears
whenever the finding does. The audit's own conditions are asserted where they
live.
"""

import importlib
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_needs_attention_idle_slot.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._needs_attention_idle_slot"
_AUDIT_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_audit"
_BOARD_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_board"
_FACT_ID = "hygiene:idle-slot:hp"


def _module() -> object:
    return importlib.import_module(_MODULE_NAME)


def _result(*, finding: object | None) -> object:
    audit = importlib.import_module(_AUDIT_NAME)
    return audit.IdleSlotAuditResult(
        configured=finding is not None,
        configuration_finding=None,
        factory="hp" if finding is not None else None,
        board=importlib.import_module(_BOARD_NAME).UNOBSERVABLE_BOARD,
        entries=(),
        finding=finding,
    )


def _finding(*, dispatchable: tuple[str, ...], stale: tuple[str, ...]) -> object:
    return importlib.import_module(_AUDIT_NAME).IdleSlotFinding(
        factory="hp",
        live_count=2,
        child_ids=dispatchable + stale,
        dispatchable_ids=dispatchable,
        stale_edge_ids=stale,
    )


def _patch(monkeypatch: pytest.MonkeyPatch, *, result: object) -> object:
    """Substitute the audit itself: this module's subject is the ROW, not the audit."""
    module = _module()

    def _audit(*, project_root: Path) -> object:
        _ = project_root
        return result

    monkeypatch.setattr(module, "idle_slot_audit", _audit)
    return module


def test_the_finding_composes_exactly_one_high_urgency_inspection_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One row, keyed on the factory, handing over the audit rather than a dispatch."""
    assert _MODULE_PATH.is_file()
    module = _patch(
        monkeypatch,
        result=_result(finding=_finding(dispatchable=("bd-one", "bd-two"), stale=("bd-stale",))),
    )

    attention = module.idle_slot_items(project_root=tmp_path, repo="repo")

    assert [item.id for item in attention] == [_FACT_ID]
    row = attention[0]
    assert (row.kind, row.urgency) == ("hygiene", "high")
    assert "2 priority-epic children are classified DISPATCHABLE-NOW" in row.summary
    assert "1 are classified STALE-EDGE" in row.summary
    assert "the first is bd-one" in row.summary
    assert row.handoff.kind == "shell"
    assert "idle-slot-audit" in row.handoff.command
    assert row.handoff.action_id is None
    assert row.source_ref.repo == "repo"
    assert row.source_ref.work_item is None


def test_no_finding_composes_no_row(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The row clears the instant the finding line would not print."""
    assert _MODULE_PATH.is_file()
    module = _patch(monkeypatch, result=_result(finding=None))

    assert module.idle_slot_items(project_root=tmp_path, repo="repo") == []


def test_the_row_is_byte_identical_across_two_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No clock, dwell, or run id may reach the summary the operator reads."""
    assert _MODULE_PATH.is_file()
    module = _patch(
        monkeypatch, result=_result(finding=_finding(dispatchable=("bd-one",), stale=()))
    )

    first = module.idle_slot_items(project_root=tmp_path, repo="repo")
    second = module.idle_slot_items(project_root=tmp_path, repo="repo")

    assert [item.summary for item in first] == [item.summary for item in second]
    assert [item.handoff.command for item in first] == [item.handoff.command for item in second]
