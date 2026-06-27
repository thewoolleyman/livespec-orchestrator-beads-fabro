"""Tests for the next thin-transport ranker (beads substrate).

Per `SPECIFICATION/contracts.md`: the wrapper
emits a `{candidates[], pagination}` envelope with optional `--limit`
(default 5, positive int) and `--offset` (default 0, non-negative int)
flags. Empty `candidates[]` is the no-work signal — the wrapper MUST NOT
degrade to any legacy single-object shape.

`rank_candidates` / `build_envelope` are pure functions over a
`list[WorkItem]` and carry verbatim from the plaintext sibling. The
`main`-level integration tests seed the hermetic `FakeBeadsClient` (autouse
fixture) via `append_work_item` with a `fake=True` connection descriptor.
"""

import json

import pytest
from livespec_orchestrator_beads_fabro.commands.next import (
    build_envelope,
    main,
    rank_candidates,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
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


def _seed(item: WorkItem) -> None:
    append_work_item(path=_config(), item=item)


def _item(
    *,
    id_: str,
    priority: int = 2,
    origin: str = "freeform",
    captured_at: str = "2026-05-19T00:00:00Z",
    status: str = "open",
    depends_on: tuple[str, ...] = (),
) -> WorkItem:
    return WorkItem(
        id=id_,
        type="task",
        status=status,  # type: ignore[arg-type]
        title=id_,
        description="d",
        origin=origin,  # type: ignore[arg-type]
        gap_id="G1" if origin == "gap-tied" else None,
        priority=priority,
        assignee=None,
        depends_on=depends_on,
        captured_at=captured_at,
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


# ---------------------------------------------------------------------------
# rank_candidates — pure-function tier, enumerates ALL ripe candidates.
# ---------------------------------------------------------------------------


def test_rank_candidates_no_items_returns_empty_list() -> None:
    assert rank_candidates(items=[]) == []


def test_rank_candidates_picks_highest_priority_first() -> None:
    items = [_item(id_="li-a", priority=3), _item(id_="li-b", priority=1)]
    result = rank_candidates(items=items)
    assert [c["work_item_ref"] for c in result] == ["li-b", "li-a"]


def test_rank_candidates_gap_tied_beats_freeform_at_same_priority() -> None:
    items = [
        _item(id_="li-a", priority=2, origin="freeform"),
        _item(id_="li-b", priority=2, origin="gap-tied"),
    ]
    result = rank_candidates(items=items)
    assert [c["work_item_ref"] for c in result] == ["li-b", "li-a"]


def test_rank_candidates_oldest_first_at_same_priority_origin() -> None:
    items = [
        _item(id_="li-newer", priority=2, captured_at="2026-05-19T02:00:00Z"),
        _item(id_="li-older", priority=2, captured_at="2026-05-19T01:00:00Z"),
    ]
    result = rank_candidates(items=items)
    assert [c["work_item_ref"] for c in result] == ["li-older", "li-newer"]


def test_rank_candidates_id_tiebreaker() -> None:
    items = [
        _item(id_="li-zzz", priority=2, captured_at="t"),
        _item(id_="li-aaa", priority=2, captured_at="t"),
    ]
    result = rank_candidates(items=items)
    assert [c["work_item_ref"] for c in result] == ["li-aaa", "li-zzz"]


def test_rank_candidates_excludes_blocked_status() -> None:
    items = [_item(id_="li-a", status="blocked"), _item(id_="li-b")]
    result = rank_candidates(items=items)
    assert [c["work_item_ref"] for c in result] == ["li-b"]


def test_rank_candidates_excludes_closed_status() -> None:
    items = [_item(id_="li-a", status="closed"), _item(id_="li-b")]
    result = rank_candidates(items=items)
    assert [c["work_item_ref"] for c in result] == ["li-b"]


def test_rank_candidates_unresolved_dependency_excludes_item() -> None:
    items = [
        _item(id_="li-blocker"),
        _item(id_="li-blocked", depends_on=("li-blocker",)),
    ]
    result = rank_candidates(items=items)
    assert [c["work_item_ref"] for c in result] == ["li-blocker"]


def test_rank_candidates_closed_dependency_unblocks_item() -> None:
    items = [
        _item(id_="li-done", status="closed"),
        _item(id_="li-ready", depends_on=("li-done",)),
    ]
    result = rank_candidates(items=items)
    assert [c["work_item_ref"] for c in result] == ["li-ready"]


def test_rank_candidates_missing_local_dependency_does_not_exclude() -> None:
    """Missing local ids resolve to UNKNOWN; only OPEN excludes per v072 contract."""
    items = [_item(id_="li-x", depends_on=("li-missing",))]
    result = rank_candidates(items=items)
    assert [c["work_item_ref"] for c in result] == ["li-x"]


def test_rank_candidates_carries_required_envelope_fields() -> None:
    items = [_item(id_="li-x", priority=0, origin="gap-tied")]
    candidates = rank_candidates(items=items)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["action"] == "implement"
    assert candidate["work_item_ref"] == "li-x"
    assert candidate["urgency"] == "high"
    assert isinstance(candidate["reason"], str)
    assert candidate["reason"]
    # impl-beads-specific fields MAY ride along (contract permits)
    assert candidate["priority"] == 0
    assert candidate["origin"] == "gap-tied"


def test_rank_candidates_urgency_high_for_p0() -> None:
    items = [_item(id_="li-x", priority=0)]
    assert rank_candidates(items=items)[0]["urgency"] == "high"


def test_rank_candidates_urgency_medium_for_p2() -> None:
    items = [_item(id_="li-x", priority=2)]
    assert rank_candidates(items=items)[0]["urgency"] == "medium"


def test_rank_candidates_urgency_low_for_p4() -> None:
    items = [_item(id_="li-x", priority=4)]
    assert rank_candidates(items=items)[0]["urgency"] == "low"


# ---------------------------------------------------------------------------
# build_envelope — pagination + envelope wrapping.
# ---------------------------------------------------------------------------


def test_build_envelope_no_items_emits_empty_candidates_with_pagination() -> None:
    envelope = build_envelope(items=[], offset=0, limit=5)
    assert envelope == {
        "candidates": [],
        "pagination": {"offset": 0, "limit": 5, "total": 0, "has_more": False},
    }


def test_build_envelope_applies_limit() -> None:
    items = [_item(id_=f"li-{i:02d}", priority=i) for i in range(10)]
    envelope = build_envelope(items=items, offset=0, limit=3)
    candidates = envelope["candidates"]
    assert isinstance(candidates, list)
    assert len(candidates) == 3
    pagination = envelope["pagination"]
    assert pagination == {"offset": 0, "limit": 3, "total": 10, "has_more": True}


def test_build_envelope_applies_offset() -> None:
    items = [_item(id_=f"li-{i:02d}", priority=i) for i in range(5)]
    envelope = build_envelope(items=items, offset=2, limit=2)
    candidates = envelope["candidates"]
    assert isinstance(candidates, list)
    # priority order p0..p4 → offset 2 skips li-00, li-01 → emits li-02, li-03
    assert [c["work_item_ref"] for c in candidates] == ["li-02", "li-03"]
    assert envelope["pagination"] == {
        "offset": 2,
        "limit": 2,
        "total": 5,
        "has_more": True,
    }


def test_build_envelope_has_more_false_when_slice_reaches_end() -> None:
    items = [_item(id_=f"li-{i:02d}", priority=i) for i in range(3)]
    envelope = build_envelope(items=items, offset=0, limit=5)
    pagination = envelope["pagination"]
    assert pagination == {"offset": 0, "limit": 5, "total": 3, "has_more": False}


def test_build_envelope_offset_past_total_returns_empty_with_has_more_false() -> None:
    items = [_item(id_="li-x")]
    envelope = build_envelope(items=items, offset=5, limit=5)
    assert envelope["candidates"] == []
    assert envelope["pagination"] == {
        "offset": 5,
        "limit": 5,
        "total": 1,
        "has_more": False,
    }


# ---------------------------------------------------------------------------
# main — wrapper-level integration (--json output, flag validation).
# ---------------------------------------------------------------------------


def test_main_empty_store_emits_empty_envelope_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload["candidates"] == []
    assert payload["pagination"] == {
        "offset": 0,
        "limit": 5,
        "total": 0,
        "has_more": False,
    }


def test_main_empty_store_human_output_says_no_work(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main([])
    captured = capsys.readouterr()
    assert rc == 0
    # Human-readable no-work signal — no JSON, no legacy "none" action.
    assert "no candidates" in captured.out.lower() or "no work" in captured.out.lower()


def test_main_json_output_envelope_shape(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed(_item(id_="li-x"))
    rc = main(["--json"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert set(payload.keys()) == {"candidates", "pagination"}
    assert len(payload["candidates"]) == 1
    candidate = payload["candidates"][0]
    assert candidate["work_item_ref"] == "li-x"
    assert candidate["action"] == "implement"
    assert payload["pagination"] == {
        "offset": 0,
        "limit": 5,
        "total": 1,
        "has_more": False,
    }


def test_main_human_output_lists_each_candidate(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed(_item(id_="li-x"))
    rc = main([])
    captured = capsys.readouterr()
    assert rc == 0
    assert "li-x" in captured.out
    assert "implement" in captured.out


def test_main_limit_applied_in_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for i in range(7):
        _seed(_item(id_=f"li-{i:02d}", priority=i))
    rc = main(["--json", "--limit", "3"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert len(payload["candidates"]) == 3
    assert payload["pagination"]["limit"] == 3
    assert payload["pagination"]["total"] == 7
    assert payload["pagination"]["has_more"] is True


def test_main_offset_applied_in_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for i in range(5):
        _seed(_item(id_=f"li-{i:02d}", priority=i))
    rc = main(["--json", "--offset", "2", "--limit", "2"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert [c["work_item_ref"] for c in payload["candidates"]] == ["li-02", "li-03"]
    assert payload["pagination"]["offset"] == 2


def test_main_invalid_limit_zero_exits_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["--limit", "0"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "limit" in captured.err.lower()


def test_main_invalid_limit_negative_exits_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["--limit", "-1"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "limit" in captured.err.lower()


def test_main_invalid_limit_nonint_exits_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["--limit", "abc"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "limit" in captured.err.lower()


def test_main_invalid_offset_negative_exits_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["--offset", "-1"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "offset" in captured.err.lower()


def test_main_invalid_offset_nonint_exits_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["--offset", "xyz"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "offset" in captured.err.lower()


def test_main_offset_zero_is_valid(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--offset 0` is the documented default; it MUST be accepted."""
    _seed(_item(id_="li-x"))
    rc = main(["--json", "--offset", "0"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload["pagination"]["offset"] == 0
