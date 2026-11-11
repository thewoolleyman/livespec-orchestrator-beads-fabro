"""A seeded ruling is consumed once its launch has a real Fabro run id."""

from __future__ import annotations

import importlib
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import dispatcher

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling_consumption"
_ITEM = "bd-ib-consumed"
_REF = "refs/heads/needs-human/seed"
_SHA = "a" * 40
_INSTANT = "2026-11-11T12:00:00Z"
_DISPATCH = "dispatch-1"
_RUN = "run-1"


def _module_path() -> Path:
    """The consumption writer is a cohesive dispatcher concern."""
    return Path(dispatcher.__file__).parent / "_dispatcher_seed_ruling_consumption.py"


def test_a_seeded_run_consumes_its_ruling_on_the_ledger_and_in_the_journal() -> None:
    """The durable consumption facts name the exact ruling, dispatch, and run."""
    assert _module_path().is_file()
    module = importlib.import_module(_MODULE)
    comments: list[str] = []
    records: list[dict[str, object]] = []

    module.record_seed_ruling_consumption(
        work_item_id=_ITEM,
        preservation_ref=_REF,
        commit_sha=_SHA,
        ruling_instant=_INSTANT,
        dispatch_id=_DISPATCH,
        run_id=_RUN,
        append_comment=comments.append,
        append_journal=records.append,
    )

    assert comments == [
        "\n".join(
            (
                "livespec-seed-ruling-consumed",
                f"ruling-instant: {_INSTANT}",
                f"dispatch-id: {_DISPATCH}",
                f"run-id: {_RUN}",
            )
        )
    ]
    assert records == [
        {
            "stage": "seed-ruling-consumed",
            "work_item_id": _ITEM,
            "preservation_ref": _REF,
            "commit_sha": _SHA,
            "ruling_instant": _INSTANT,
            "dispatch_id": _DISPATCH,
            "run_id": _RUN,
        }
    ]


def test_reconciliation_backfills_a_missing_consumed_comment_from_the_runs_seed_record() -> None:
    """The matched ruling is the one with the seed record's ref and immutable SHA."""
    module = importlib.import_module(_MODULE)
    comments = [
        "\n".join(
            (
                "livespec-seed-ruling",
                f"work-item: {_ITEM}",
                f"preservation-ref: {_REF}",
                f"commit-sha: {_SHA}",
                "invoker: coordinator",
                "reason: keep the checked tree",
                f"instant: {_INSTANT}",
            )
        )
    ]
    written_comments: list[str] = []
    written_records: list[dict[str, object]] = []
    records = (
        {
            "stage": "dispatch-id",
            "work_item_id": _ITEM,
            "dispatch_id": _DISPATCH,
        },
        {
            "stage": "recovery-route",
            "work_item_id": _ITEM,
            "route": "seeded",
            "preservation_ref": _REF,
            "commit_sha": _SHA,
        },
        {"stage": "fabro-run", "work_item_id": _ITEM, "run_id": _RUN},
    )

    assert hasattr(module, "backfill_seed_ruling_consumptions")
    module.backfill_seed_ruling_consumptions(
        records=records,
        comments_for_item=lambda item: comments if item == _ITEM else [],
        append_comment=lambda item, body: written_comments.append(f"{item}:{body}"),
        append_journal=written_records.append,
    )

    assert written_comments == [
        f"{_ITEM}:livespec-seed-ruling-consumed\nruling-instant: {_INSTANT}"
        f"\ndispatch-id: {_DISPATCH}\nrun-id: {_RUN}"
    ]
    assert written_records[0]["stage"] == "seed-ruling-consumed"
