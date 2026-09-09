"""`plan_native_status_remaps` planning + the standalone `ledger-normalize` CLI.

The dispatch-path expansion (an `in_progress` row now clears the
pre-dispatch gate) lives in the sibling
`test_dispatcher_ledger_normalize.py`. This file covers the reused pure
planner and the standalone command that self-heals ANY tenant's
beads-native statuses WITHOUT needing a dispatch: `open` → `backlog`,
`in_progress` → `active`, everything else left for the status-conformance
check. `--dry-run` plans + reports without writing; a real run applies via
the store and reports the residual non-conformant rows.

An adopted row that carries no real `rank` is also assigned one, so the
planner cases below come in pairs: an already-ranked row plans the status
alone, and a rank-less row plans a `rank` beside it. `_item`'s default `rank`
is a real key, so every pre-existing case here is the already-ranked leg.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import IssueDraft, make_beads_client
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import (
    plan_native_status_remaps,
    project_native_status_remaps,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.work_items.rank import BOTTOM_SENTINEL


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


def _raw_native_row(*, item_id: str) -> None:
    """Write one row the way a writer performing no second step leaves it.

    `create_issue` lands beads `open` carrying exactly the metadata handed to
    it, so an empty metadata object genuinely holds no `rank` key and reads
    back through the adapter's bottom-sentinel — the state `append_work_item`
    cannot produce, since it always writes the item's non-null `rank`.
    """
    _ = make_beads_client(config=_config()).create_issue(
        draft=IssueDraft(
            issue_id=item_id,
            issue_type="task",
            title=item_id,
            description=item_id,
            assignee=None,
            created_at="2026-06-11T00:00:00Z",
            labels=["origin:freeform"],
            metadata={},
        )
    )


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


def test_plan_remaps_leaves_parked_and_unknown_statuses_untouched() -> None:
    items = [
        _item(id="deferred-1", status="deferred"),
        _item(id="hooked-1", status="hooked"),
        _item(id="unknown-1", status="frobnicate"),
        _item(id="backlog-1", status="backlog"),
        _item(id="active-1", status="active"),
        _item(id="ready-1", status="ready"),
    ]
    assert plan_native_status_remaps(items=items) == []


def test_plan_assigns_a_bottom_of_order_rank_to_each_rank_less_adopted_row() -> None:
    """A rank-less adoption plans a fresh key after the greatest LIVE real key.

    The `done` row carries a key sorting after every live one, so a plan that
    took it for the bottom would produce keys after `zz` instead of before it;
    the already-ranked `open` row is the control that no other row is re-keyed.
    """
    items = [
        _item(id="anchor", status="backlog", rank="a1"),
        _item(id="ranked-open", status="open", rank="a5"),
        _item(id="rankless-open", status="open", rank=BOTTOM_SENTINEL),
        _item(id="rankless-claim", status="in_progress", rank=BOTTOM_SENTINEL),
        _item(id="closed-tail", status="done", rank="zz"),
    ]

    planned = {remap["item_id"]: remap for remap in plan_native_status_remaps(items=items)}

    assert "rank" not in planned["ranked-open"]
    assigned = [planned["rankless-open"]["rank"], planned["rankless-claim"]["rank"]]
    assert all("a5" < key < "zz" for key in assigned)
    assert assigned[0] != assigned[1]


def test_plan_assigns_a_rank_when_no_live_row_carries_a_real_key() -> None:
    """With the live order empty, the insert takes `key_between`'s open start."""
    items = [_item(id="only-open", status="open", rank=BOTTOM_SENTINEL)]

    planned = plan_native_status_remaps(items=items)

    assert planned[0]["rank"] != BOTTOM_SENTINEL


def test_project_applies_the_assigned_rank_and_leaves_unplanned_rows_alone() -> None:
    """The in-memory view carries the adoption's rank half, not the status half alone."""
    items = [
        _item(id="rankless-open", status="open", rank=BOTTOM_SENTINEL),
        _item(id="ranked-open", status="open", rank="a5"),
        _item(id="untouched", status="ready", rank="a1"),
    ]
    remaps = plan_native_status_remaps(items=items)

    projected = {item.id: item for item in project_native_status_remaps(items=items, remaps=remaps)}

    assert projected["rankless-open"].status == "backlog"
    assert projected["rankless-open"].rank != BOTTOM_SENTINEL
    assert (projected["ranked-open"].status, projected["ranked-open"].rank) == ("backlog", "a5")
    assert (projected["untouched"].status, projected["untouched"].rank) == ("ready", "a1")


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

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "would remap  native-open  open -> backlog" in out
    assert "would remap  raw-claim  in_progress -> active" in out
    assert "(no residual findings)" in out
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

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    remapped_by_id = {remap["item_id"]: remap for remap in payload["remapped"]}
    assert remapped_by_id["native-open"]["to"] == "backlog"
    assert remapped_by_id["raw-claim"]["to"] == "active"
    assert payload["residual"] == []
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

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "remapped  native-open  open -> backlog" in out
    assert "remapped  raw-claim  in_progress -> active" in out
    assert "(no residual findings)" in out
    # The transient native statuses were written through to the store; the
    # parked deferred row is conforming and left untouched.
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


def test_ledger_normalize_assigns_and_persists_a_rank_for_a_rank_less_adopted_row(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """The CLI reports the assigned key AND the store reads it back.

    Reported and persisted are separate claims: a summary naming a key the
    write never carried would satisfy either one alone. The already-ranked
    anchor is the control that no other row was re-keyed.
    """
    config = _config()
    append_work_item(path=config, item=_item(id="ranked-anchor", status="backlog", rank="a5"))
    _raw_native_row(item_id="rankless-open")

    exit_code = main(argv=["ledger-normalize", "--project-root", str(tmp_path), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    remapped = {remap["item_id"]: remap for remap in payload["remapped"]}
    assigned = remapped["rankless-open"]["rank"]
    assert assigned > "a5"
    stored = materialize_work_items(records=read_work_items(path=config))
    assert stored["rankless-open"].rank == assigned
    assert stored["ranked-anchor"].rank == "a5"


def test_ledger_normalize_dry_run_plans_a_rank_and_writes_none(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """`--dry-run` reports the key it WOULD assign and leaves the row unranked."""
    config = _config()
    _raw_native_row(item_id="rankless-open")

    exit_code = main(
        argv=["ledger-normalize", "--project-root", str(tmp_path), "--dry-run", "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["remapped"][0]["rank"] != BOTTOM_SENTINEL
    stored = materialize_work_items(records=read_work_items(path=config))
    assert stored["rankless-open"].rank == BOTTOM_SENTINEL


def test_ledger_normalize_reports_unknown_status_residual(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    config = _config()
    append_work_item(path=config, item=_item(id="bad-hooked", status="hooked"))

    exit_code = main(argv=["ledger-normalize", "--project-root", str(tmp_path)])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "(nothing to normalize)" in out
    assert "RESIDUAL  FAIL  status-conformance  bad-hooked" in out
    assert "status 'hooked' is outside the livespec lifecycle" in out


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
