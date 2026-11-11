"""A seeded launch writes its receipt from the launcher, and only for a ruled seed."""

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_seed_ruling_launch as seed_launch_module,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling_consumption import (
    backfill_seed_ruling_consumptions,
)

_REF = "refs/seed"
_SHA = "a" * 40
_INSTANT = "2026-11-11T00:00:00Z"


def _ruling() -> str:
    return "\n".join(
        (
            "livespec-seed-ruling",
            "work-item: item",
            f"preservation-ref: {_REF}",
            f"commit-sha: {_SHA}",
            "invoker: coordinator",
            "reason: preserve",
            f"instant: {_INSTANT}",
        )
    )


def _launcher(*, inner_run_id: str | None, tmp_path: Path) -> Any:
    return seed_launch_module.ReceiptWritingLauncher(
        inner=SimpleNamespace(
            launch=lambda **_: SimpleNamespace(run_id=inner_run_id, marker="launched")
        ),
        args=argparse.Namespace(resume_fetch_ref=_REF, resume_head=_SHA),
        comments=(_ruling(),),
        work_item_id="item",
        dispatch_id="dispatch",
        repo=tmp_path,
    )


def test_the_launcher_returns_the_inner_result_after_consuming_the_ruling_for_its_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts: list[Any] = []
    monkeypatch.setattr(
        seed_launch_module,
        "consume_seed_ruling_for_run",
        lambda *, receipt, **_: receipts.append(receipt),
    )

    launched = _launcher(inner_run_id="run-1", tmp_path=tmp_path).launch(
        plan=object(), runner=object(), journal=object()
    )

    assert launched.marker == "launched"
    assert [(r.run_id, r.dispatch_id, r.commit_sha) for r in receipts] == [
        ("run-1", "dispatch", _SHA)
    ]


def test_a_launch_that_produced_no_run_id_consumes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts: list[Any] = []
    monkeypatch.setattr(
        seed_launch_module,
        "consume_seed_ruling_for_run",
        lambda *, receipt, **_: receipts.append(receipt),
    )

    _ = _launcher(inner_run_id=None, tmp_path=tmp_path).launch(
        plan=object(), runner=object(), journal=object()
    )

    assert receipts == [None]


def test_a_malformed_marker_that_merely_contains_the_instant_does_not_block_a_receipt() -> None:
    comments = [_ruling(), f"livespec-seed-ruling-consumed\nruling-instant: prefix-{_INSTANT}"]
    written: list[tuple[str, str]] = []
    records = [
        {"stage": "dispatch-id", "work_item_id": "item", "dispatch_id": "d"},
        {
            "stage": "recovery-route",
            "route": "seeded",
            "work_item_id": "item",
            "preservation_ref": _REF,
            "commit_sha": _SHA,
        },
        {"stage": "fabro-run", "work_item_id": "item", "run_id": "r"},
    ]

    backfill_seed_ruling_consumptions(
        records=records,
        comments_for_item=lambda _item: comments,
        append_comment=lambda item, body: written.append((item, body)),
        append_journal=lambda _record: None,
    )

    assert [item for item, _ in written] == ["item"]
    assert f"ruling-instant: {_INSTANT}" in written[0][1]
