"""Write a ruled seed's durable receipt after its Fabro run exists."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import JournalWriter
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import (
    CommandRunner,
    FabroLauncher,
    FabroRunResult,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry import (
    RESUME_FETCH_REF_ARG,
    RESUME_HEAD_ARG,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling_consumption import (
    consume_seed_ruling_for_run as consume_receipt,
)
from livespec_orchestrator_beads_fabro.store import append_work_item_comment

__all__: list[str] = [
    "ReceiptWritingLauncher",
    "SeededLaunchReceipt",
    "consume_seed_ruling_for_run",
    "seeded_launch_receipt",
]


@dataclass(frozen=True, kw_only=True)
class SeededLaunchReceipt:
    """The ruled seed and durable identifiers a launched receipt must name."""

    comments: Sequence[str]
    work_item_id: str
    preservation_ref: str
    commit_sha: str
    dispatch_id: str
    run_id: str


def seeded_launch_receipt(
    *,
    args: argparse.Namespace,
    comments: Sequence[str],
    work_item_id: str,
    dispatch_id: str,
    run_id: str | None,
) -> SeededLaunchReceipt | None:
    """Return the receipt facts only for a launched seeded recovery."""
    preservation_ref = getattr(args, RESUME_FETCH_REF_ARG, None)
    commit_sha = getattr(args, RESUME_HEAD_ARG, None)
    if run_id is None or not isinstance(preservation_ref, str) or not isinstance(commit_sha, str):
        return None
    return SeededLaunchReceipt(
        comments=comments,
        work_item_id=work_item_id,
        preservation_ref=preservation_ref,
        commit_sha=commit_sha,
        dispatch_id=dispatch_id,
        run_id=run_id,
    )


def consume_seed_ruling_for_run(
    *, receipt: SeededLaunchReceipt | None, repo: Path, journal: JournalWriter
) -> None:
    """Persist a receipt, only when the launch consumed a matching ruling."""
    if receipt is None:
        return
    consume_receipt(
        comments=receipt.comments,
        work_item_id=receipt.work_item_id,
        preservation_ref=receipt.preservation_ref,
        commit_sha=receipt.commit_sha,
        dispatch_id=receipt.dispatch_id,
        run_id=receipt.run_id,
        append_comment=lambda body: append_work_item_comment(
            path=store_config(repo=repo), work_item_id=receipt.work_item_id, body=body
        ),
        append_journal=lambda record: journal.append(record=record),
    )


@dataclass(frozen=True, kw_only=True)
class ReceiptWritingLauncher:
    """A launcher that writes the consumed receipt as soon as the run id exists.

    The receipt is written when the launch returns, before the engine opens the
    pull-request and merge flow, so a seeded run never outlives its receipt for
    the length of that flow.
    """

    inner: FabroLauncher
    args: argparse.Namespace
    comments: Sequence[str]
    work_item_id: str
    dispatch_id: str
    repo: Path

    def launch(
        self, *, plan: DispatchPlan, runner: CommandRunner, journal: JournalWriter
    ) -> FabroRunResult:
        launched = self.inner.launch(plan=plan, runner=runner, journal=journal)
        consume_seed_ruling_for_run(
            receipt=seeded_launch_receipt(
                args=self.args,
                comments=self.comments,
                work_item_id=self.work_item_id,
                dispatch_id=self.dispatch_id,
                run_id=launched.run_id,
            ),
            repo=self.repo,
            journal=journal,
        )
        return launched
