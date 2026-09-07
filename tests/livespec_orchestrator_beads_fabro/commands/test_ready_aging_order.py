"""The orchestrator-side ready-age inputs handed to the canonical sort key.

`_ready_aging_order` is the injection point for the age half of
`ready_sort_key`. The ORDERING it produces is asserted end to end over a seeded
tenant by `tests/integration/test_ready_aging_tiebreak_scenario123.py`; what is
asserted here are the resolution and degradation paths that a healthy tenant
never reaches — the unreadable store, the unparseable instant, and the memo
that keeps one pass to one read.

Every degradation is asserted to land on `None`, the runtime's unknowable-ready
instant. That direction is the load-bearing one: `None` keeps the `id` tiebreak
and no age advantage, whereas a failure resolving to any instant would let a
substrate hiccup silently reorder the dispatch queue.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    DEFAULT_READY_AGING_THRESHOLD_HOURS,
)
from livespec_orchestrator_beads_fabro.commands._ready_aging_order import (
    ready_aging_order,
    unaged_ready_order,
)

_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_TENANT = "livespec-orchestrator-beads-fabro"

# The module-private reader the lookup memoizes; patched to observe the memo and
# to hand back instants without standing up a tenant.
_INSTANT_READER = "livespec_orchestrator_beads_fabro.commands._ready_aging_order._read_instants"


def _reader_returning(*, instants: dict[str, str | None]) -> Callable[..., dict[str, str | None]]:
    """A stand-in `_read_instants` that answers `instants` for any project root."""

    def _reader(*, project_root: Path) -> dict[str, str | None]:
        _ = project_root
        return instants

    return _reader


def _repo(*, tmp_path: Path, threshold_hours: int | None = None) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    block: dict[str, object] = {
        "connection": {
            "tenant": _TENANT,
            "prefix": "bd-ib",
            "server_user": _TENANT,
            "database": _TENANT,
            "bd_path": "bd",
            "fake": True,
        }
    }
    if threshold_hours is not None:
        block["dispatcher"] = {"ready_aging_threshold_hours": threshold_hours}
    _ = (repo / ".livespec.jsonc").write_text(json.dumps({_PLUGIN_BLOCK: block}), encoding="utf-8")
    return repo


def test_unaged_order_reports_every_instant_unknowable_at_the_default_bound() -> None:
    order = unaged_ready_order()

    assert order.ready_since_lookup("bd-ib-anything") is None
    assert order.ready_aging_threshold_hours == float(DEFAULT_READY_AGING_THRESHOLD_HOURS)


def test_the_bound_comes_from_the_repositorys_own_declaration(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path, threshold_hours=36)

    assert ready_aging_order(project_root=repo).ready_aging_threshold_hours == 36.0


def test_a_repository_declaring_no_bound_gets_the_documented_default(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)

    assert ready_aging_order(project_root=repo).ready_aging_threshold_hours == float(
        DEFAULT_READY_AGING_THRESHOLD_HOURS
    )


def test_a_stored_instant_resolves_as_a_utc_datetime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        _INSTANT_READER, _reader_returning(instants={"bd-ib-aged": "2026-08-25T12:00:00Z"})
    )
    lookup = ready_aging_order(project_root=_repo(tmp_path=tmp_path)).ready_since_lookup

    assert lookup("bd-ib-aged") == datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


def test_the_tenant_is_read_once_per_pass_however_many_items_ask(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The memo is what keeps an ordering pass to ONE tenant read.

    Read per item, a drain over a large ready queue would re-read the whole
    tenant once per comparison subject, so the call count is the property under
    test rather than the returned instants.
    """
    reads: list[Path] = []

    def _reader(*, project_root: Path) -> dict[str, str | None]:
        reads.append(project_root)
        return {"bd-ib-one": "2026-08-25T12:00:00Z"}

    monkeypatch.setattr(_INSTANT_READER, _reader)
    lookup = ready_aging_order(project_root=_repo(tmp_path=tmp_path)).ready_since_lookup

    resolved = [lookup("bd-ib-one"), lookup("bd-ib-two"), lookup("bd-ib-one")]

    assert len(reads) == 1
    assert [instant is None for instant in resolved] == [False, True, False]


def test_an_item_the_tenant_never_reported_is_unknowable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_INSTANT_READER, _reader_returning(instants={"bd-ib-other": None}))
    lookup = ready_aging_order(project_root=_repo(tmp_path=tmp_path)).ready_since_lookup

    assert lookup("bd-ib-absent") is None


def test_an_unparseable_stored_instant_is_unknowable_rather_than_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        _INSTANT_READER, _reader_returning(instants={"bd-ib-bad": "not-a-timestamp"})
    )
    lookup = ready_aging_order(project_root=_repo(tmp_path=tmp_path)).ready_since_lookup

    assert lookup("bd-ib-bad") is None


def test_an_unreadable_tenant_degrades_to_unknowable_instants(tmp_path: Path) -> None:
    """A project root with no connection declaration at all still ranks.

    `resolve_store_config` raises against it, which is the shape every
    unconfigured, unreachable or malformed tenant presents. Ranking must survive
    it: the ordering falls back to the `id` tiebreak instead of the pass dying.
    """
    unconfigured = tmp_path / "no-config"
    unconfigured.mkdir()

    order = ready_aging_order(project_root=unconfigured)

    assert order.ready_since_lookup("bd-ib-anything") is None
    assert order.ready_aging_threshold_hours == float(DEFAULT_READY_AGING_THRESHOLD_HOURS)
