"""Coverage for the HELD reasons: the shared verdict, capacity excepted.

The fixture project carries a governed spec tree and a conforming Definition
of Done on every item that is meant to be admitted, because the reason set is
read through the SAME acceptance wall the dispatch path reads: an item whose
section is missing is refused there, and that refusal is one of the reasons
under test rather than fixture noise.
"""

import importlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_idle_slot_holds.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_holds"
_SPEC_HEADING = "## Effective acceptance criteria"
_DEFINITION_OF_DONE = (
    "## Definition of Done\n"
    "\n"
    "- The idle-slot audit classifies this item.\n"
    "\n"
    f"References: {_SPEC_HEADING}\n"
)


def _item(*, id_: str, status: str = "ready", **overrides: object) -> WorkItem:
    base = WorkItem(
        id=id_,
        type="task",
        status=status,  # pyright: ignore[reportArgumentType]
        title=f"{id_} title",
        description=_DEFINITION_OF_DONE,
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-16T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    return replace(base, **overrides)  # pyright: ignore[reportArgumentType]


def _write_project(root: Path) -> None:
    (root / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": {"wip_cap": 5}}}),
        encoding="utf-8",
    )
    spec = root / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_SPEC_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    journal = root / "tmp" / "fabro-dispatch-journal.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text("", encoding="utf-8")


def _module() -> object:
    return importlib.import_module(_MODULE_NAME)


def _reasons(**kwargs: object) -> dict[str, str]:
    return _module().tenant_hold_reasons(**kwargs)


def test_an_admissible_ready_row_carries_no_hold_reason(tmp_path: Path) -> None:
    """A row the shared verdict admits with capacity excepted is simply absent."""
    assert _MODULE_PATH.is_file()
    _write_project(tmp_path)

    assert _reasons(repo=tmp_path, items=[_item(id_="bd-ready")]) == {}


def test_a_row_the_acceptance_wall_refuses_carries_the_verdicts_own_refusal(
    tmp_path: Path,
) -> None:
    """The reason is the verdict's text, not a re-worded summary of it."""
    assert _MODULE_PATH.is_file()
    _write_project(tmp_path)

    reasons = _reasons(
        repo=tmp_path,
        items=[_item(id_="bd-no-section", description="No Definition of Done here.")],
    )

    assert "bd-no-section" in reasons
    assert reasons["bd-no-section"] != ""


def test_a_row_readiness_refuses_is_reported_by_stage(tmp_path: Path) -> None:
    """Readiness exposes no reason, so the STAGE is what the clause asks for."""
    assert _MODULE_PATH.is_file()
    _write_project(tmp_path)
    module = _module()
    blocked = _item(id_="bd-waiting", depends_on=({"kind": "local", "work_item_id": "bd-open"},))

    reasons = _reasons(repo=tmp_path, items=[blocked, _item(id_="bd-open", status="backlog")])

    assert reasons["bd-waiting"] == module.HOLD_STAGE_READINESS


def test_a_non_ready_row_never_gets_a_hold_reason(tmp_path: Path) -> None:
    """Every other status is already its own class; a second answer would clash."""
    assert _MODULE_PATH.is_file()
    _write_project(tmp_path)

    reasons = _reasons(repo=tmp_path, items=[_item(id_="bd-parked", status="backlog")])

    assert reasons == {}


def test_a_recorded_provider_exhaustion_wait_holds_every_ready_row(tmp_path: Path) -> None:
    """A vendor ceiling is a fact about the tenant, so it holds the whole set."""
    assert _MODULE_PATH.is_file()
    _write_project(tmp_path)
    module = _module()
    (tmp_path / "tmp" / "fabro-dispatch-journal.jsonl").write_text(
        json.dumps(
            {
                "at": "2099-01-01T00:00:00Z",
                "stage": "provider-exhaustion-observed",
                "work_item_id": "bd-one",
                "provider": "anthropic",
                "governing_condition": "provider_usage_limit",
                "record_expires_at": "2099-01-01T00:15:00Z",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    reasons = _reasons(
        repo=tmp_path, items=[_item(id_="bd-one"), _item(id_="bd-two", status="backlog")]
    )

    assert reasons == {"bd-one": module.HOLD_PROVIDER_EXHAUSTION_WAIT}


def test_an_admission_required_acp_chain_wait_holds_every_ready_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second tenant-wide wait, read through the same verdict admission reads."""
    assert _MODULE_PATH.is_file()
    _write_project(tmp_path)
    module = _module()

    def _chain_wait_held(*, project_root: Path) -> bool:
        _ = project_root
        return True

    monkeypatch.setattr(module, "acp_chain_wait_active", _chain_wait_held)

    reasons = _reasons(repo=tmp_path, items=[_item(id_="bd-one")])

    assert reasons == {"bd-one": module.HOLD_ACP_CHAIN_WAIT}
