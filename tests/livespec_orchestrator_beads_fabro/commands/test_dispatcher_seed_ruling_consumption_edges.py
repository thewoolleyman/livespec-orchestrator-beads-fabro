"""Coverage controls for consumed seed-ruling reconciliation."""

from __future__ import annotations

import argparse
import importlib
from collections.abc import Sequence
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling_consumption import (
    backfill_seed_ruling_consumptions,
    consume_seed_ruling_for_run,
)


def _ruling(*, ref: str = "refs/seed", sha: str = "a" * 40) -> str:
    return "\n".join(
        (
            "livespec-seed-ruling",
            "work-item: item",
            f"preservation-ref: {ref}",
            f"commit-sha: {sha}",
            "invoker: coordinator",
            "reason: preserve",
            "instant: 2026-11-11T00:00:00Z",
        )
    )


def _backfill(*, records: Sequence[dict[str, object]], comments: Sequence[str]) -> list[str]:
    written: list[str] = []
    backfill_seed_ruling_consumptions(
        records=records,
        comments_for_item=lambda _item: comments,
        append_comment=lambda _item, body: written.append(body),
        append_journal=lambda _record: None,
    )
    return written


def test_incomplete_or_unmatched_seed_evidence_is_inert() -> None:
    assert (
        _backfill(records=({}, {"work_item_id": "item", "stage": "dispatch-id"}), comments=[]) == []
    )
    assert (
        _backfill(
            records=(
                {"work_item_id": "item", "stage": "dispatch-id", "dispatch_id": "d"},
                {"work_item_id": "item", "stage": "recovery-route", "route": "seeded"},
                {"work_item_id": "item", "stage": "fabro-run", "run_id": "r"},
            ),
            comments=[_ruling(ref="other")],
        )
        == []
    )


def test_an_existing_consumption_is_not_written_again() -> None:
    assert (
        _backfill(
            records=(
                {"work_item_id": "item", "stage": "dispatch-id", "dispatch_id": "d"},
                {
                    "work_item_id": "item",
                    "stage": "recovery-route",
                    "route": "seeded",
                    "preservation_ref": "refs/seed",
                    "commit_sha": "a" * 40,
                },
                {"work_item_id": "item", "stage": "fabro-run", "run_id": "r"},
            ),
            comments=[
                _ruling(),
                "livespec-seed-ruling-consumed\nruling-instant: 2026-11-11T00:00:00Z",
            ],
        )
        == []
    )


def test_a_launch_does_not_consume_the_same_ruling_twice() -> None:
    """The dispatch-path writer leaves one receipt when its launch is retried."""
    comments = [
        _ruling(),
        "livespec-seed-ruling-consumed\nruling-instant: 2026-11-11T00:00:00Z",
    ]
    written_comments: list[str] = []
    written_records: list[dict[str, object]] = []

    consume_seed_ruling_for_run(
        comments=comments,
        work_item_id="item",
        preservation_ref="refs/seed",
        commit_sha="a" * 40,
        dispatch_id="dispatch",
        run_id="run",
        append_comment=written_comments.append,
        append_journal=written_records.append,
    )

    assert written_comments == []
    assert written_records == []


def test_a_seeded_launch_writes_its_receipt_after_its_run_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The dispatch bridge carries the exact seed and launched run to both writers."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling_launch"
    )
    comments = [_ruling()]
    ledger_comments: list[tuple[object, str, str]] = []
    journal_records: list[dict[str, object]] = []

    class _Journal:
        def append(self, *, record: dict[str, object]) -> None:
            journal_records.append(record)

    monkeypatch.setattr(module, "store_config", lambda *, repo: repo)
    monkeypatch.setattr(
        module,
        "append_work_item_comment",
        lambda *, path, work_item_id, body: ledger_comments.append((path, work_item_id, body)),
    )
    receipt = module.seeded_launch_receipt(
        args=argparse.Namespace(resume_fetch_ref="refs/seed", resume_head="a" * 40),
        comments=comments,
        work_item_id="item",
        dispatch_id="dispatch",
        run_id="run",
    )

    assert receipt is not None
    module.consume_seed_ruling_for_run(receipt=receipt, repo=tmp_path, journal=_Journal())

    assert ledger_comments == [
        (
            tmp_path,
            "item",
            "livespec-seed-ruling-consumed\nruling-instant: 2026-11-11T00:00:00Z\ndispatch-id: dispatch\nrun-id: run",
        )
    ]
    assert journal_records[0]["stage"] == "seed-ruling-consumed"


def test_a_launch_without_a_run_is_not_consumed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No run id means the bridge cannot write a durable consumption receipt."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling_launch"
    )
    written: list[str] = []
    monkeypatch.setattr(module, "store_config", lambda *, repo: repo)
    monkeypatch.setattr(
        module,
        "append_work_item_comment",
        lambda *, body, **_: written.append(body),
    )
    receipt = module.seeded_launch_receipt(
        args=argparse.Namespace(resume_fetch_ref="refs/seed", resume_head="a" * 40),
        comments=[_ruling()],
        work_item_id="item",
        dispatch_id="dispatch",
        run_id=None,
    )

    assert receipt is None
    module.consume_seed_ruling_for_run(receipt=receipt, repo=tmp_path, journal=object())
    assert written == []


def test_inert_values_and_nonmatching_consumption_shapes_do_not_block_backfill() -> None:
    """Malformed journal values and receipts cannot consume a valid ruled seed."""
    records = (
        {"work_item_id": "item", "stage": "unrelated"},
        {"work_item_id": "item", "stage": "dispatch-id", "dispatch_id": 1},
        {
            "work_item_id": "item",
            "stage": "recovery-route",
            "route": "seeded",
            "preservation_ref": "",
            "commit_sha": "a" * 40,
        },
        {"work_item_id": "item", "stage": "fabro-run", "run_id": ""},
        {"work_item_id": "item", "stage": "dispatch-id", "dispatch_id": "d"},
        {
            "work_item_id": "item",
            "stage": "recovery-route",
            "route": "seeded",
            "preservation_ref": "refs/seed",
            "commit_sha": "a" * 40,
        },
        {"work_item_id": "item", "stage": "fabro-run", "run_id": "r"},
    )

    assert _backfill(
        records=records,
        comments=[
            _ruling(),
            "",
            "livespec-seed-ruling-consumed\nruling-instant: another-instant",
        ],
    ) == [
        "livespec-seed-ruling-consumed\nruling-instant: 2026-11-11T00:00:00Z"
        "\ndispatch-id: d\nrun-id: r"
    ]
