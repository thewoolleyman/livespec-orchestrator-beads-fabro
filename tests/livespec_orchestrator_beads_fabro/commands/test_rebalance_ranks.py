"""Tests for the rebalance-ranks orchestrator-private maintenance command.

The pure `rebalanced` / `legacy_seed` cores are exercised directly; `main`
is driven hermetically through the in-memory `FakeBeadsClient` (the autouse
conftest sets `LIVESPEC_BEADS_FAKE=1` and resets the singleton), seeding via
`append_work_item` and reading back the re-keyed ranks.
"""

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands.rebalance_ranks import (
    LegacySeedRow,
    legacy_seed,
    main,
    rebalanced,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.work_items.rank import n_keys_between


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


@pytest.fixture(autouse=True)
def _in_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )


def _item(*, id_: str, rank: str, status: str = "ready") -> WorkItem:
    return WorkItem(
        id=id_,
        type="task",
        status=status,  # type: ignore[arg-type]
        title=f"{id_} title",
        description="d",
        origin="freeform",
        gap_id=None,
        rank=rank,
        assignee=None,
        depends_on=(),
        captured_at="2026-05-19T00:00:00Z",
        resolution="completed" if status == "done" else None,
        reason="done" if status == "done" else None,
        audit=None,
        superseded_by=None,
    )


def _seed(item: WorkItem) -> None:
    append_work_item(path=_config(), item=item)


def _stored() -> dict[str, WorkItem]:
    return materialize_work_items(records=read_work_items(path=_config()))


# -- rebalanced (pure core) ---------------------------------------------


def test_rebalanced_empty_is_empty() -> None:
    assert rebalanced(items=[]) == []


def test_rebalanced_preserves_order_and_rekeys_evenly() -> None:
    # Ranks deliberately out of canonical order; (rank, id) ordering is z1<z2<z3.
    items = [
        _item(id_="c", rank="z3"),
        _item(id_="a", rank="z1"),
        _item(id_="b", rank="z2"),
    ]
    result = rebalanced(items=items)
    assert [item.id for item in result] == ["a", "b", "c"]
    assert [item.rank for item in result] == n_keys_between(a=None, b=None, n=3)


def test_rebalanced_breaks_rank_ties_by_id() -> None:
    items = [_item(id_="b", rank="z0"), _item(id_="a", rank="z0")]
    result = rebalanced(items=items)
    assert [item.id for item in result] == ["a", "b"]


# -- legacy_seed (the L2 backfill primitive) ----------------------------


def test_legacy_seed_empty_is_empty() -> None:
    assert legacy_seed(rows=[]) == []


def test_legacy_seed_orders_by_priority_then_captured_then_id() -> None:
    rows = [
        LegacySeedRow(priority=2, captured_at="2026-01-01T00:00:00Z", work_item_id="late"),
        LegacySeedRow(priority=0, captured_at="2026-01-02T00:00:00Z", work_item_id="p0-newer"),
        LegacySeedRow(priority=0, captured_at="2026-01-01T00:00:00Z", work_item_id="p0-older"),
    ]
    result = legacy_seed(rows=rows)
    keys = n_keys_between(a=None, b=None, n=3)
    # priority 0 (older-first) before priority 2; keys are evenly spaced ascending.
    assert result == [
        ("p0-older", keys[0]),
        ("p0-newer", keys[1]),
        ("late", keys[2]),
    ]


def test_legacy_seed_breaks_priority_captured_ties_by_id() -> None:
    rows = [
        LegacySeedRow(priority=1, captured_at="2026-01-01T00:00:00Z", work_item_id="b"),
        LegacySeedRow(priority=1, captured_at="2026-01-01T00:00:00Z", work_item_id="a"),
    ]
    assert [pair[0] for pair in legacy_seed(rows=rows)] == ["a", "b"]


# -- main (store-backed re-key) -----------------------------------------


def test_main_empty_store_rekeys_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main([])
    captured = capsys.readouterr()
    assert rc == 0
    assert "re-keyed 0" in captured.out


def test_main_rekeys_live_items_in_order(capsys: pytest.CaptureFixture[str]) -> None:
    _seed(_item(id_="ra", rank="z1"))
    _seed(_item(id_="rb", rank="z2"))
    _seed(_item(id_="rc", rank="z3"))
    rc = main([])
    captured = capsys.readouterr()
    assert rc == 0
    assert "re-keyed 3" in captured.out
    stored = _stored()
    keys = n_keys_between(a=None, b=None, n=3)
    assert stored["ra"].rank == keys[0]
    assert stored["rb"].rank == keys[1]
    assert stored["rc"].rank == keys[2]


def test_main_excludes_done_items(capsys: pytest.CaptureFixture[str]) -> None:
    _seed(_item(id_="live", rank="z9"))
    _seed(_item(id_="closed", rank="z8", status="done"))
    rc = main([])
    captured = capsys.readouterr()
    assert rc == 0
    # Only the one live head is re-keyed; the done head keeps its rank.
    assert "re-keyed 1" in captured.out
    assert _stored()["closed"].rank == "z8"


def test_main_second_run_is_a_noop(capsys: pytest.CaptureFixture[str]) -> None:
    """A rebalance is idempotent: a second pass re-keys nothing (skip branch)."""
    _seed(_item(id_="ra", rank="z1"))
    _seed(_item(id_="rb", rank="z2"))
    _ = main([])
    _ = capsys.readouterr()
    rc = main([])
    captured = capsys.readouterr()
    assert rc == 0
    assert "re-keyed 0" in captured.out
