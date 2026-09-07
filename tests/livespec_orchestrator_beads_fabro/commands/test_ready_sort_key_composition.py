"""How every ready-ordering call site COMPOSES the canonical sort key.

`livespec_runtime.work_items.lifecycle.ready_sort_key` is a FACTORY since
runtime v0.27.0: it takes a clock, the durable ready-instant lookup and the
aging bound, and RETURNS the key, so a call site builds the key ONCE per pass
and hands the result to `sorted`. Before v0.27.0 it was the bare key itself,
passed straight to `sort(key=...)`.

This module pins the composition rather than the ordering, which is what makes
the two halves of the ratified ready-aging clause separately checkable: the
ORDERING the composed key produces is asserted end to end over a seeded tenant
by `tests/integration/test_ready_aging_tiebreak_scenario123.py`, while what is
asserted HERE is which sites opt into aging at all. That split matters because
the clause governs the ready-DISPATCH queue specifically: `next`, the
Dispatcher's drain and the drain's rework leg must each pass a ready-since
lookup and the bound, so one drain cannot rank one tenant two ways, and
`rebalance-ranks` must NOT — it re-keys stored `rank`, and folding a transient
age into persisted ordering keys would bake today's dwell into the ledger.

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

# The sites the ready-dispatch ordering clause binds, and the site it excludes.
_AGING_AWARE_SITES = ("next", "dispatcher-drain", "rework-admission")
_RANK_STORAGE_SITE = "rebalance-ranks"

_AGING_KWARGS = {"now", "ready_since_lookup", "ready_aging_threshold_hours"}


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
        _RANK_STORAGE_SITE: _RecordingFactory(),
        "rework-admission": _RecordingFactory(),
    }
    monkeypatch.setattr(next_command, "ready_sort_key", recorders["next"])
    monkeypatch.setattr(_dispatcher_loop_selection, "ready_sort_key", recorders["dispatcher-drain"])
    monkeypatch.setattr(rebalance_ranks, "ready_sort_key", recorders[_RANK_STORAGE_SITE])
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


def test_every_ready_ordering_call_site_composes_the_factory_once_with_a_clock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One composition per pass, every one of them carrying the current time."""
    recorders = _compositions(monkeypatch=monkeypatch, tmp_path=tmp_path)

    for site, recorder in recorders.items():
        assert len(recorder.calls) == 1, f"{site} did not compose the factory exactly once"
        assert isinstance(recorder.calls[0]["now"], datetime), f"{site} passed a non-datetime now"


def test_the_ready_dispatch_sites_opt_into_aging_and_rank_storage_does_not(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The three ready-dispatch sites pass both aging inputs; the rank re-key passes neither.

    Asserted as an exact kwarg SET in both directions, because each half alone
    is satisfiable by a wrong build: a site that passed the bound but no lookup
    would still ignore age, and `rebalance-ranks` picking up a lookup would
    persist a transient dwell into stored `rank` keys without changing any
    surface a reader watches.
    """
    recorders = _compositions(monkeypatch=monkeypatch, tmp_path=tmp_path)

    for site in _AGING_AWARE_SITES:
        composed = recorders[site].calls[0]
        assert set(composed) == _AGING_KWARGS, f"{site} did not compose both aging inputs"
        assert callable(composed["ready_since_lookup"]), f"{site} passed a non-callable lookup"
        assert isinstance(
            composed["ready_aging_threshold_hours"], float
        ), f"{site} passed a non-float bound"
    assert set(recorders[_RANK_STORAGE_SITE].calls[0]) == {"now"}, "rank storage must stay un-aged"
