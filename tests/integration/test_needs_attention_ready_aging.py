"""Integration-tier acceptance for the ready-work aging fact.

Binds `SPECIFICATION/scenarios.md` "Scenario 84 — Aged ready work with nothing
in flight surfaces an unblock" through the real `build_attention` composition
and the real store/client seam against the in-memory `FakeBeadsClient`.

The dwell instant is seeded through the tenant metadata the store reads, not
through a stubbed reader, so the age the fact reports is derived the way a live
repository derives it. `now` is pinned rather than taken from the clock, because
an aging assertion against a moving clock is not a test.

The discriminating case is the last one: an item captured long ago that only
recently entered `ready` must NOT count as aged. Without it, a fact keyed on
`captured_at` — the obvious wrong field, and the one every record carries —
would pass every other case in this file.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client, reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _needs_attention_hygiene as hygiene
from livespec_orchestrator_beads_fabro.commands import needs_attention
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    write_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands.needs_attention import build_attention
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.attention_item import AttentionItem
from livespec_runtime.needs_attention import SpecNextOutput

_AGING_FACT_ID = "hygiene:ready-aging:repo"
_NOW = "2026-08-26T12:00:00Z"
_THRESHOLD_HOURS = 24


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _seed_ready(
    *, id_: str, ready_since: object, captured_at: str = "2026-08-24T00:00:00Z"
) -> None:
    """File a `ready` row and stamp the dwell instant the aging lane reads."""
    base = WorkItem(
        id=id_,
        type="task",
        status="ready",
        title=f"{id_} title",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at=captured_at,
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    append_work_item(path=_config(), item=replace(base))
    client = make_beads_client(config=_config())
    record = client.show_issue(issue_id=id_)
    raw = record.get("metadata")
    metadata = dict(raw) if isinstance(raw, dict) else {}
    metadata["ready_since"] = ready_since
    client.update_issue(issue_id=id_, metadata=metadata)


def _write_project(*, root: Path) -> None:
    (root / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "livespec-impl-beads",
                        "prefix": "bd",
                        "server_user": "livespec-impl-beads",
                        "database": "livespec-impl-beads",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {"ready_aging_threshold_hours": _THRESHOLD_HOURS},
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _no_spec_next(*, project_root: Path) -> SpecNextOutput | None:
    _ = project_root
    return None


def _no_watchable_runs(*, repo: Path) -> frozenset[str]:
    _ = repo
    return frozenset()


def _snapshot(
    *,
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    watchable: frozenset[str] = frozenset(),
) -> list[AttentionItem]:
    monkeypatch.setattr(needs_attention, "spec_next", _no_spec_next)
    monkeypatch.setattr(hygiene, "_utc_now_iso", lambda: _NOW)

    def _watchable_item_ids(*, repo: Path) -> frozenset[str]:
        _ = repo
        return watchable

    monkeypatch.setattr(
        hygiene,
        "watchable_fabro_run_item_ids",
        _watchable_item_ids if watchable else _no_watchable_runs,
    )
    return build_attention(project_root=root, repo_name="repo", include_hygiene=False)


def _aging(*, attention: list[AttentionItem]) -> list[AttentionItem]:
    return [item for item in attention if item.id == _AGING_FACT_ID]


def test_the_aging_fact_names_the_count_the_oldest_age_and_an_unblock_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_project(root=tmp_path)
    _seed_ready(id_="bd-oldest", ready_since="2026-08-24T00:00:00Z")
    _seed_ready(id_="bd-younger", ready_since="2026-08-25T12:00:00Z")

    [aging] = _aging(attention=_snapshot(root=tmp_path, monkeypatch=monkeypatch))

    # One of the two is past the threshold; the other is 24h old exactly and is
    # not, so the count discriminates rather than merely counting the queue.
    assert f"1 ready work-item has waited past {_THRESHOLD_HOURS}h" in aging.summary
    assert "oldest age 60h" in aging.summary
    assert "oldest work-item bd-oldest" in aging.summary
    assert "Unblock handoff" in aging.summary
    assert aging.handoff.kind == "shell"
    assert "ready-aging repo" in aging.handoff.command
    assert str(tmp_path) in aging.handoff.command


def test_the_fact_does_not_appear_while_a_dispatch_holds_a_live_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_project(root=tmp_path)
    _seed_ready(id_="bd-oldest", ready_since="2026-08-24T00:00:00Z")
    _ = write_dispatch_lock(repo=tmp_path, work_item_id="bd-oldest", dispatch_id="run-oldest")

    assert _aging(attention=_snapshot(root=tmp_path, monkeypatch=monkeypatch)) == []


def test_the_fact_does_not_appear_while_a_watchable_run_is_in_flight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_project(root=tmp_path)
    _seed_ready(id_="bd-oldest", ready_since="2026-08-24T00:00:00Z")
    _seed_ready(id_="bd-moving", ready_since="2026-08-24T00:00:00Z")

    attention = _snapshot(
        root=tmp_path, monkeypatch=monkeypatch, watchable=frozenset({"bd-moving"})
    )

    # A watchable run for a DIFFERENT item of this repository still means the
    # repository is moving, so the aged queue is waiting on capacity rather
    # than stalled — and `bd-oldest` is aged, so the fact would otherwise fire.
    assert _aging(attention=attention) == []


def test_an_item_whose_ready_instant_is_unknowable_is_reported_never_omitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_project(root=tmp_path)
    _seed_ready(id_="bd-aged", ready_since="2026-08-24T00:00:00Z")
    _seed_ready(id_="bd-unknown", ready_since="not-a-timestamp")

    [aging] = _aging(attention=_snapshot(root=tmp_path, monkeypatch=monkeypatch))

    # An undeterminable instant is neither counted as aged nor dropped: it is
    # named, because a silently shorter list is the failure this clause exists
    # to prevent.
    assert f"1 ready work-item has waited past {_THRESHOLD_HOURS}h" in aging.summary
    assert "age-unknown: bd-unknown" in aging.summary


def test_a_recently_ready_item_captured_long_ago_does_not_count_as_aged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_project(root=tmp_path)
    _seed_ready(
        id_="bd-fresh",
        ready_since="2026-08-26T06:00:00Z",
        captured_at="2026-01-01T00:00:00Z",
    )

    # `captured_at` is nearly eight months old while the ready transition is six
    # hours old. The age is the dwell in `ready`, so no fact appears.
    assert _aging(attention=_snapshot(root=tmp_path, monkeypatch=monkeypatch)) == []
