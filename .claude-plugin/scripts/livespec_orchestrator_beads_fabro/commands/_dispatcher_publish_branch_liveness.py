"""Whether any run of one work-item is still live on the configured factory.

The question the publish-branch reclaim must answer before it deletes anything.
`_dispatcher_publish_branch_reclaim` owns the decision and the record; this module
owns the MEASUREMENT, which is a different concern with a different failure mode
and a different external system behind it.

FAIL-CLOSED IS THE WHOLE POINT. An unanswerable `fabro ps` and a factory with no
runs at all produce the same empty set, and nothing downstream can tell them
apart — so `observed` carries that difference explicitly and `reclaimable` is
false for both. A gauge that reported "nothing alive" when it could not see would
clear a running publish's branch and leave a journal record that reads exactly
like a healthy reclaim, which is worse than an honest refusal: it falsifies the
one artifact an operator would use to reconstruct what happened.

THE ATTRIBUTION IS DELIBERATELY THE WIDER READING. A run exists for a window
before the Dispatcher journals its id, and in that window its rendered brief is
the only thing naming its item, so the goal-text leg rides alongside the journaled
one. Over-inclusion costs a hold an operator can clear by hand; under-inclusion
costs a live run the branch it is about to push to. The two errors are not
symmetric, so the reading is not either.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    NON_TERMINAL_STATUS_KINDS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroRunSummary
from livespec_orchestrator_beads_fabro.commands._run_attribution import journaled_run_ids

__all__: list[str] = [
    "HELD_FACTORY_UNOBSERVABLE",
    "HELD_LIVE_RUN",
    "ItemRunLiveness",
    "item_run_liveness",
    "live_run_ids_for_item",
]

# The two reasons a liveness reading holds a reclaim. Each names a MEASUREMENT
# rather than a judgment, because the journal record's whole job is to tell an
# operator which question stopped the reclaim before `publish_draft` refused.
HELD_LIVE_RUN = "live-run"
HELD_FACTORY_UNOBSERVABLE = "factory-unobservable"

_PS_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True, kw_only=True)
class ItemRunLiveness:
    """Which runs of one item are still live, and whether that was MEASURED.

    `observed` false means the factory could not be ASKED, which is deliberately
    not the same value as "no live runs": the two carry the same empty tuple and
    must not produce the same decision, because one authorizes a deletion and the
    other cannot.
    """

    live_run_ids: tuple[str, ...]
    observed: bool

    @property
    def reclaimable(self) -> bool:
        """Whether a reclaim may proceed: measured, and nothing of this item alive."""
        return self.observed and not self.live_run_ids

    @property
    def held_reason(self) -> str:
        """Which measurement held the reclaim -- the live run, or the absent answer."""
        return HELD_LIVE_RUN if self.live_run_ids else HELD_FACTORY_UNOBSERVABLE

    def detail(self, *, branch: str) -> str:
        """The held record's prose, naming what was found or what went unanswered."""
        if self.live_run_ids:
            return (
                f"{branch} is this item's publish branch and"
                f" {', '.join(self.live_run_ids)} is still non-terminal on the"
                " configured factory, so the branch may still be pushed to;"
                " leaving it exactly as it stands"
            )
        return (
            "`fabro ps` did not answer for the configured factory, so whether a"
            " previous run of this item is still alive could not be established;"
            f" {branch} is left standing rather than cleared on an unmeasured"
            " liveness answer"
        )


def item_run_liveness(
    *,
    args: argparse.Namespace,
    repo: Path,
    work_item_id: str,
    journal_path: Path,
    runner: CommandRunner,
) -> ItemRunLiveness:
    """Ask the configured factory which runs of this item are still non-terminal.

    The factory target is read off `args` the way every other post-selection seam
    reads it -- `dispatch_preamble` pins it before either dispatch entry point
    reaches the wall this serves -- and an absent one degrades to the client's own
    default rather than raising, which is the shape a non-dispatching caller has.
    """
    target = getattr(args, "fabro_factory_target", None)
    ps = FabroPort(
        fabro_bin=args.fabro_bin,
        target=FabroTarget(
            server_url=getattr(target, "server", None),
            dev_token=getattr(target, "dev_token", None),
        ),
        runner=runner,
        cwd=repo,
    ).ps(timeout_seconds=_PS_TIMEOUT_SECONDS)
    if ps.command.exit_code != 0:
        return ItemRunLiveness(live_run_ids=(), observed=False)
    return ItemRunLiveness(
        live_run_ids=live_run_ids_for_item(
            runs=ps.runs,
            journaled=journaled_run_ids(
                records=read_journal_records(journal_path=journal_path),
                work_item_id=work_item_id,
            ),
            work_item_id=work_item_id,
        ),
        observed=True,
    )


def live_run_ids_for_item(
    *,
    runs: Sequence[FabroRunSummary],
    journaled: Sequence[str],
    work_item_id: str,
) -> tuple[str, ...]:
    """Every non-terminal run attributable to one item, by journaled id or goal text.

    `NON_TERMINAL_STATUS_KINDS` is the run reconciler's own set rather than a
    second list of status names, so "still alive" means the same thing to this
    reading as it does to the sweep that reaps stranded runs -- including the
    parked statuses a narrower `running`-only test would have read as dead.
    """
    named = frozenset(journaled)
    return tuple(
        run.run_id
        for run in runs
        if run.status_kind in NON_TERMINAL_STATUS_KINDS
        and (run.run_id in named or run.work_item_id == work_item_id)
    )
