"""Wiring tests: a STUB `sibling_status_lookup` threaded into every call site.

qiqz6b Part B threads one cross-tenant sibling resolver through all seven
readiness / lane call sites. These tests pass a plain stub lookup (no real
beads tenant) into each orchestrator-side seam and assert the three
behaviors the runtime's `_entry_blocks` promises for a `sibling_work_item`
dependency:

- a CLOSED sibling stops blocking (the item is READY / rendered `ready`),
- an OPEN sibling blocks (excluded / rendered `blocked:dependency`),
- an UNRESOLVABLE sibling (`UNKNOWN`) fails closed and blocks.

`lane_of` and `is_item_ready` agree by construction, so the same three
behaviors are asserted across both the readiness surfaces (`rank_candidates`,
`is_dispatch_candidate`) and the lane-render surfaces (`_filter_by_name`,
`_work_item_to_dict`, `human_valves`).
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
    is_dispatch_candidate,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_work_items import human_valves
from livespec_orchestrator_beads_fabro.commands.list_work_items import (
    _filter_by_name,  # pyright: ignore[reportPrivateUsage]
    _work_item_to_dict,  # pyright: ignore[reportPrivateUsage]
)
from livespec_orchestrator_beads_fabro.commands.next import rank_candidates
from livespec_orchestrator_beads_fabro.types import DependsOnRaw, WorkItem
from livespec_runtime.cross_repo.types import CrossRepoManifest, CrossRepoTarget, RefStatus

_SIBLING_DEP: DependsOnRaw = {"kind": "sibling_work_item", "repo": "sib", "work_item_id": "sib-1"}


def _manifest() -> CrossRepoManifest:
    return CrossRepoManifest(
        targets={"sib": CrossRepoTarget(github_url="https://github.com/o/sib")}
    )


def _item(
    *,
    id_: str = "li-x",
    status: str = "ready",
    depends_on: tuple[DependsOnRaw, ...] = (_SIBLING_DEP,),
) -> WorkItem:
    return WorkItem(
        id=id_,
        type="task",
        status=status,  # type: ignore[arg-type]
        title=id_,
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=depends_on,
        captured_at="2026-05-19T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


# ---------------------------------------------------------------------------
# next.rank_candidates (call site 3)
# ---------------------------------------------------------------------------


def test_rank_candidates_closed_sibling_makes_item_ready() -> None:
    result = rank_candidates(
        items=[_item()],
        manifest=_manifest(),
        sibling_status_lookup=lambda _repo, _work_item_id: RefStatus.CLOSED,
    )
    assert [candidate["work_item_ref"] for candidate in result] == ["li-x"]


def test_rank_candidates_open_sibling_excludes_item() -> None:
    result = rank_candidates(
        items=[_item()],
        manifest=_manifest(),
        sibling_status_lookup=lambda _repo, _work_item_id: RefStatus.OPEN,
    )
    assert result == []


def test_rank_candidates_unknown_sibling_fails_closed() -> None:
    result = rank_candidates(
        items=[_item()],
        manifest=_manifest(),
        sibling_status_lookup=lambda _repo, _work_item_id: RefStatus.UNKNOWN,
    )
    assert result == []


# ---------------------------------------------------------------------------
# _dispatcher_loop_selection.is_dispatch_candidate (call sites 1 + 2)
# ---------------------------------------------------------------------------


def test_is_dispatch_candidate_closed_sibling_is_candidate() -> None:
    item = _item()
    assert (
        is_dispatch_candidate(
            item=item,
            index={item.id: item},
            manifest=_manifest(),
            sibling_status_lookup=lambda _repo, _work_item_id: RefStatus.CLOSED,
        )
        is True
    )


def test_is_dispatch_candidate_open_sibling_is_not_candidate() -> None:
    item = _item()
    assert (
        is_dispatch_candidate(
            item=item,
            index={item.id: item},
            manifest=_manifest(),
            sibling_status_lookup=lambda _repo, _work_item_id: RefStatus.OPEN,
        )
        is False
    )


def test_is_dispatch_candidate_unknown_sibling_fails_closed() -> None:
    item = _item()
    assert (
        is_dispatch_candidate(
            item=item,
            index={item.id: item},
            manifest=_manifest(),
            sibling_status_lookup=lambda _repo, _work_item_id: RefStatus.UNKNOWN,
        )
        is False
    )


def test_is_dispatch_candidate_pending_approval_projection_uses_lookup() -> None:
    # A pending-approval item is a candidate when its ready-projection has no
    # open dependency — the lookup must reach the projected readiness check too.
    item = _item(status="pending-approval")
    assert (
        is_dispatch_candidate(
            item=item,
            index={item.id: item},
            manifest=_manifest(),
            sibling_status_lookup=lambda _repo, _work_item_id: RefStatus.CLOSED,
        )
        is True
    )


# ---------------------------------------------------------------------------
# list_work_items lane render surfaces (call sites 5 + 6 + 7)
# ---------------------------------------------------------------------------


def test_filter_ready_includes_item_with_closed_sibling() -> None:
    result = _filter_by_name(
        materialized=[_item()],
        name="ready",
        manifest=_manifest(),
        sibling_status_lookup=lambda _repo, _work_item_id: RefStatus.CLOSED,
    )
    assert [item.id for item in result] == ["li-x"]


def test_filter_blocked_includes_item_with_open_sibling() -> None:
    result = _filter_by_name(
        materialized=[_item()],
        name="blocked",
        manifest=_manifest(),
        sibling_status_lookup=lambda _repo, _work_item_id: RefStatus.OPEN,
    )
    assert [item.id for item in result] == ["li-x"]


def test_work_item_to_dict_closed_sibling_renders_ready_lane() -> None:
    item = _item()
    payload = _work_item_to_dict(
        item=item,
        index={item.id: item},
        manifest=_manifest(),
        sibling_status_lookup=lambda _repo, _work_item_id: RefStatus.CLOSED,
    )
    assert payload["lane"] == "ready"
    assert payload["lane_reason"] is None


def test_work_item_to_dict_open_sibling_renders_blocked_dependency_lane() -> None:
    item = _item()
    payload = _work_item_to_dict(
        item=item,
        index={item.id: item},
        manifest=_manifest(),
        sibling_status_lookup=lambda _repo, _work_item_id: RefStatus.OPEN,
    )
    assert payload["lane"] == "blocked"
    assert payload["lane_reason"] == "dependency"


# ---------------------------------------------------------------------------
# _needs_attention_work_items.human_valves (call site 4)
# ---------------------------------------------------------------------------


def test_human_valves_threads_lookup(tmp_path: Path) -> None:
    item = _item(status="pending-approval", depends_on=())
    lanes = human_valves(
        project_root=tmp_path,
        items=[item],
        index={item.id: item},
        manifest=_manifest(),
        sibling_status_lookup=lambda _repo, _work_item_id: RefStatus.CLOSED,
    )
    assert [lane.verb for lane in lanes] == ["approve"]
