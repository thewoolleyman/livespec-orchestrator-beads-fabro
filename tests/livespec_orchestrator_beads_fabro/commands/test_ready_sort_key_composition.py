"""How every ready-ordering call site COMPOSES the canonical sort key.

`livespec_runtime.work_items.lifecycle.ready_sort_key` is a FACTORY since
runtime v0.27.0: it takes a clock (and optionally a durable ready-instant
lookup) and RETURNS the key, so a call site builds the key ONCE per pass and
hands the result to `sorted`. Before v0.27.0 it was the bare key itself, passed
straight to `sort(key=...)`.

This module pins the composition rather than the ordering: it asserts that each
of the four call sites calls the factory exactly once per pass, with `now` and
NOTHING else. Omitting `ready_since_lookup` is what keeps the aging tiebreak
inert, so the key degrades to the `(rank, id)` ordering these surfaces already
had — and the ordering assertions that prove that are the pre-existing ones in
`test_next.py`, `test_rebalance_ranks.py` and the dispatcher suites, which pass
unchanged.

Each pass is driven over an EMPTY candidate set, which is what makes the
recorded call count discriminating in both directions: the factory is composed
once per pass regardless of how many items there are, while the pre-factory
bare key is only ever invoked PER ITEM and so is never called at all.
"""

from __future__ import annotations

from datetime import datetime
from operator import attrgetter
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_loop_selection,
    _dispatcher_rework_admission,
    rebalance_ranks,
)
from livespec_orchestrator_beads_fabro.commands import (
    next as next_command,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_reclaim import (
    ActiveClaimAccounting,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_rework_admission import ReworkPass


class _RecordingFactory:
    """Stand-in for `ready_sort_key` that records how a call site composed it."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return attrgetter("rank", "id")


def _accounting() -> ActiveClaimAccounting:
    return ActiveClaimAccounting(
        active_count=0,
        live_lock_active_ids=(),
        green_terminal_active_ids=(),
        journal_unreadable_active_ids=(),
    )


def _compositions(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> dict[str, _RecordingFactory]:
    """Drive one pass through each call site over an empty candidate set.

    An empty set is deliberate: the factory is composed once per PASS, so the
    recorded call count is the composition itself and not a per-item artifact.
    Under the pre-factory shape the bare key is never invoked at all, which is
    what makes the count discriminating.
    """
    recorders = {
        "next": _RecordingFactory(),
        "dispatcher-drain": _RecordingFactory(),
        "rebalance-ranks": _RecordingFactory(),
        "rework-admission": _RecordingFactory(),
    }
    monkeypatch.setattr(next_command, "ready_sort_key", recorders["next"])
    monkeypatch.setattr(_dispatcher_loop_selection, "ready_sort_key", recorders["dispatcher-drain"])
    monkeypatch.setattr(rebalance_ranks, "ready_sort_key", recorders["rebalance-ranks"])
    monkeypatch.setattr(
        _dispatcher_rework_admission, "ready_sort_key", recorders["rework-admission"]
    )

    _ = next_command.rank_candidates(items=[])
    _ = _dispatcher_loop_selection.ready_items(items=[], repo=tmp_path)
    _ = rebalance_ranks.rebalanced(items=[])
    _ = _dispatcher_rework_admission.rework_pending_candidates(
        items=[], accounting=_accounting(), rework=ReworkPass()
    )
    return recorders


def test_every_ready_ordering_call_site_composes_the_factory_once_with_now(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One composition per pass, carrying the current time and no ready-since lookup."""
    recorders = _compositions(monkeypatch=monkeypatch, tmp_path=tmp_path)

    for site, recorder in recorders.items():
        assert len(recorder.calls) == 1, f"{site} did not compose the factory exactly once"
        assert set(recorder.calls[0]) == {"now"}, f"{site} passed more than the clock"
        assert isinstance(recorder.calls[0]["now"], datetime), f"{site} passed a non-datetime now"
