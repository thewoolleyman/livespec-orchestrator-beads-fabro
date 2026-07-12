"""`plan_native_status_remaps` planning + the standalone `ledger-normalize` CLI.

The dispatch-path expansion (an `in_progress` row now clears the
pre-dispatch gate) lives in the sibling
`test_dispatcher_ledger_normalize.py`. This file covers the reused pure
planner and the standalone command that self-heals ANY tenant's
beads-native statuses WITHOUT needing a dispatch: `open` → `backlog`,
`in_progress` → `active`, everything else left for the status-conformance
check. `--dry-run` plans + reports without writing; a real run applies via
the store and reports the residual non-conformant rows.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import (
    plan_native_status_remaps,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="livespec-impl-beads-t1",
        type="task",
        status="ready",
        title="A ready task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-06-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, **overrides)


def _current_statuses(*, config: StoreConfig) -> dict[str, str]:
    materialized = materialize_work_items(records=read_work_items(path=config))
    return {item.id: str(item.status) for item in materialized.values()}


@pytest.fixture(autouse=True)
def _tmp_repo_connection_config(tmp_path: Path) -> None:
    """Give each test's `tmp_path` a `.livespec.jsonc` with a `prefix`.

    `ledger-normalize` resolves the tenant connection via
    `resolve_store_config(cwd=--project-root)`, which requires an explicit
    `connection.prefix`; a real governed repo always carries one.
    """
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# plan_native_status_remaps (the pure, reused planner)
# ---------------------------------------------------------------------------


def test_plan_remaps_open_to_backlog() -> None:
    plan = plan_native_status_remaps(items=[_item(id="o-1", status="open")])
    assert plan == [
        {
            "item_id": "o-1",
            "from": "open",
            "to": "backlog",
            "reason": "beads-native intake default",
        }
    ]


def test_plan_remaps_in_progress_to_active() -> None:
    plan = plan_native_status_remaps(items=[_item(id="p-1", status="in_progress")])
    assert plan == [
        {
            "item_id": "p-1",
            "from": "in_progress",
            "to": "active",
            "reason": "raw claim normalized to active",
        }
    ]


def test_plan_remaps_leaves_everything_else_untouched() -> None:
    items = [
        _item(id="deferred-1", status="deferred"),
        _item(id="hooked-1", status="hooked"),
        _item(id="unknown-1", status="frobnicate"),
        _item(id="backlog-1", status="backlog"),
        _item(id="active-1", status="active"),
        _item(id="ready-1", status="ready"),
    ]
    assert plan_native_status_remaps(items=items) == []


def test_plan_remaps_mixed_set_plans_only_native_statuses() -> None:
    items = [
        _item(id="o-1", status="open"),
        _item(id="p-1", status="in_progress"),
        _item(id="d-1", status="deferred"),
        _item(id="r-1", status="ready"),
    ]
    planned = {remap["item_id"]: remap["to"] for remap in plan_native_status_remaps(items=items)}
    assert planned == {"o-1": "backlog", "p-1": "active"}


# ---------------------------------------------------------------------------
# CLI surface — ledger-normalize
# ---------------------------------------------------------------------------


def test_ledger_normalize_dry_run_reports_and_mutates_nothing(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    config = _config()
    append_work_item(path=config, item=_item(id="native-open", status="open"))
    append_work_item(path=config, item=_item(id="raw-claim", status="in_progress"))
    append_work_item(path=config, item=_item(id="stuck-deferred", status="deferred"))

    exit_code = main(argv=["ledger-normalize", "--project-root", str(tmp_path), "--dry-run"])

    assert exit_code == 1  # the deferred row is residual non-conformance
    out = capsys.readouterr().out
    assert "would remap  native-open  open -> backlog" in out
    assert "would remap  raw-claim  in_progress -> active" in out
    assert "RESIDUAL  FAIL  status-conformance  stuck-deferred" in out
    # Dry-run performs NO store mutation: every status is untouched.
    assert _current_statuses(config=config) == {
        "native-open": "open",
        "raw-claim": "in_progress",
        "stuck-deferred": "deferred",
    }


def test_ledger_normalize_dry_run_json_shape(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    config = _config()
    append_work_item(path=config, item=_item(id="native-open", status="open"))
    append_work_item(path=config, item=_item(id="raw-claim", status="in_progress"))
    append_work_item(path=config, item=_item(id="stuck-deferred", status="deferred"))

    exit_code = main(
        argv=["ledger-normalize", "--project-root", str(tmp_path), "--dry-run", "--json"]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    remapped_by_id = {remap["item_id"]: remap for remap in payload["remapped"]}
    assert remapped_by_id["native-open"]["to"] == "backlog"
    assert remapped_by_id["raw-claim"]["to"] == "active"
    residual_ids = {finding["item_id"] for finding in payload["residual"]}
    assert residual_ids == {"stuck-deferred"}
    # Still no mutation.
    assert _current_statuses(config=config)["native-open"] == "open"


def test_ledger_normalize_real_run_remaps_both_and_reports_residual(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    config = _config()
    append_work_item(path=config, item=_item(id="native-open", status="open"))
    append_work_item(path=config, item=_item(id="raw-claim", status="in_progress"))
    append_work_item(path=config, item=_item(id="stuck-deferred", status="deferred"))

    exit_code = main(argv=["ledger-normalize", "--project-root", str(tmp_path)])

    assert exit_code == 1  # the deferred row it cannot map remains residual
    out = capsys.readouterr().out
    assert "remapped  native-open  open -> backlog" in out
    assert "remapped  raw-claim  in_progress -> active" in out
    assert "RESIDUAL  FAIL  status-conformance  stuck-deferred" in out
    # Both native statuses were written through to the store; the deferred
    # row is left untouched for a human.
    assert _current_statuses(config=config) == {
        "native-open": "backlog",
        "raw-claim": "active",
        "stuck-deferred": "deferred",
    }


def test_ledger_normalize_real_run_all_clean_exits_zero(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    config = _config()
    append_work_item(path=config, item=_item(id="native-open", status="open"))
    append_work_item(path=config, item=_item(id="raw-claim", status="in_progress"))

    exit_code = main(argv=["ledger-normalize", "--project-root", str(tmp_path), "--json"])

    assert exit_code == 0  # nothing residual once both native rows are remapped
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is False
    assert {remap["item_id"] for remap in payload["remapped"]} == {"native-open", "raw-claim"}
    assert payload["residual"] == []
    assert _current_statuses(config=config) == {
        "native-open": "backlog",
        "raw-claim": "active",
    }


def test_ledger_normalize_nothing_to_normalize(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    append_work_item(path=_config(), item=_item(id="ready-1", status="ready"))

    exit_code = main(argv=["ledger-normalize", "--project-root", str(tmp_path)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "(nothing to normalize)" in out
    assert "(no residual findings)" in out
