"""Coverage controls for consumed seed-ruling reconciliation."""

from __future__ import annotations

from collections.abc import Sequence

from livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling_consumption import (
    backfill_seed_ruling_consumptions,
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
