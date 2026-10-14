"""The native-status remap and the dispatch pre-flight survive a malformed rank.

Measured 2026-10-14 on plugin v0.196.3: every dispatch on this tenant died in
the dispatcher loop pre-flight, before any Fabro run existed, with
`FIError invalid order key: zz` raised from `key_between` inside
`plan_native_status_remaps`. One live row — `bd-ib-hiduhs`, resting at
`pending-approval` since 2026-09-06 — stored the rank `zz`, which is NOT a
valid fractional-indexing key (`z` declares a 27-character integer part), while
`_bottom_live_rank` took the plain `max` of the live ranks. So the greatest
live rank WAS that malformed value, and every pre-flight that planned a
beads-native remap asked `key_between` for a key ordering after it.

Companion normalization tests live in `test_dispatcher_ledger_normalize.py` and
`test_dispatcher_ledger_normalize_cli.py`; this file carries only the
malformed-rank tolerance.
"""

from __future__ import annotations

from dataclasses import replace

from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import (
    plan_native_status_remaps,
)
from livespec_orchestrator_beads_fabro.types import WorkItem
from livespec_runtime.work_items.rank import BOTTOM_SENTINEL


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


def test_remap_assigns_a_valid_rank_despite_a_malformed_live_rank() -> None:
    """The adopted row's fresh key lands after the greatest VALID live rank.

    `zz` sorts above `a2` lexicographically, so a plain `max` picks it and the
    insert crashes. The bottom of the live order is the greatest live rank that
    `key_between` can actually extend — here `a2`, whose next key is `a3`.
    """
    items = [
        _item(id="stuck", status="pending-approval", rank="zz"),
        _item(id="ranked", status="ready", rank="a2"),
        _item(id="fresh", status="open", rank=BOTTOM_SENTINEL),
    ]

    planned = plan_native_status_remaps(items=items)

    assert [remap["item_id"] for remap in planned] == ["fresh"]
    assert planned[0]["rank"] == "a3"
