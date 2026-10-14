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

import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import (
    ledger_blocked_after_normalization,
    plan_native_status_remaps,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
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


@pytest.mark.parametrize("malformed", ["zz", ""])
def test_preflight_completes_and_reports_a_malformed_live_rank(
    tmp_path: Path,
    malformed: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The pre-flight clears, and the offending row's id AND rank are reported.

    Tolerating the malformed key is only half the remedy: a rank no insert can
    extend is a stored value that has to be REPAIRED, and a pre-flight that
    silently routed around it would leave nothing naming the row to repair.
    Both the id and the rank are reported, because the id alone does not say
    what is wrong with the row and the rank alone does not say which row holds
    it. The empty-string case is the arm `validate_order_key` indexes before it
    can reject.
    """
    config = _config()
    append_work_item(path=config, item=_item(id="fresh", status="open"))
    items = [
        _item(id="stuck", status="pending-approval", rank=malformed),
        _item(id="fresh", status="open", rank=BOTTOM_SENTINEL),
    ]
    journal = JournalFile(path=tmp_path / "journal.jsonl")

    blocked = ledger_blocked_after_normalization(items=items, config=config, journal=journal)

    assert blocked is False
    records = [json.loads(line) for line in (tmp_path / "journal.jsonl").read_text().splitlines()]
    reported = [record for record in records if record["stage"] == "malformed-rank"]
    assert [record["rows"] for record in reported] == [[{"item_id": "stuck", "rank": malformed}]]
    stderr = capsys.readouterr().err
    assert "stuck" in stderr
    assert repr(malformed) in stderr
