"""One loop wave: the admission-time credential wait, the valve, the launch.

Split out of `_dispatcher_loop_command` so each stays a cohesive unit under the
file LLOC ceiling. The command module owns the INVOCATION — preamble, store
preparation, the dry-run report, the pre-dispatch criteria wall, the verdict and
every post-verdict stage — while this module owns the one thing that happens
between them: admitting a wave of candidates and launching it.

The admission-time credential wait lives here rather than beside the invocation
stages for the same reason: it is an admission-time condition, and the ratified
clause -- the admission-time credential-probe refusal among the provider
spend-containment rules in `SPECIFICATION/contracts.md` -- places it BEFORE any
sandbox is launched. It runs ahead of the valve rather than after it, because
admitting first would move ready items to `active` and then hold them there for
the length of the wait.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_admission import (
    admit_and_select,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_reprobe import (
    await_usable_credential,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_ledger import (
    args_with_dispatch_factory_target,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop import dispatch_one
from livespec_orchestrator_beads_fabro.commands._dispatcher_rework_admission import ReworkPass
from livespec_orchestrator_beads_fabro.commands._dispatcher_workflow_ledger import (
    args_with_dispatch_workflow_name,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "dispatch_loop_wave",
]


def dispatch_loop_wave(  # noqa: PLR0913 — kw-only wave inputs; `rework` is the pass's own narrowing, not a variant of the candidate list.
    *,
    args: argparse.Namespace,
    repo: Path,
    items: list[WorkItem],
    selected_candidates: list[WorkItem],
    journal: JournalFile,
    janitor: tuple[str, ...] | None,
    rework: ReworkPass,
) -> list[DispatchOutcome]:
    # A provider-limited worker credential holds the wave here instead of
    # ending the invocation: the probe's own next result retires the wait, and
    # no provider-stated reset instant gates it. Every other probe condition
    # returns immediately and is reported by the dispatch path's own refusal.
    await_usable_credential(repo=repo, journal=journal, budget=args.budget)
    return _admit_and_dispatch_loop_wave(
        args=args,
        repo=repo,
        items=items,
        selected_candidates=selected_candidates,
        journal=journal,
        janitor=janitor,
        rework=rework,
    )


def _admit_and_dispatch_loop_wave(  # noqa: PLR0913 — see `dispatch_loop_wave`; this is the same input set one call deeper.
    *,
    args: argparse.Namespace,
    repo: Path,
    items: list[WorkItem],
    selected_candidates: list[WorkItem],
    journal: JournalFile,
    janitor: tuple[str, ...] | None,
    rework: ReworkPass,
) -> list[DispatchOutcome]:
    # The admission valve drains the candidate set up to the per-repo WIP cap:
    # host-only items are routed away, manual / unresolvable items are held +
    # surfaced, marked rework rows re-occupy the slots their own `active` rows
    # already hold BEFORE any new admission, and the highest-rank
    # admission-eligible items fill what free slots remain (ready -> active,
    # assignee set). Capacity-deferred items simply wait for the next pass.
    admission = admit_and_select(
        repo=repo,
        items=items,
        candidates=selected_candidates,
        journal=journal,
        enforce_cap=True,
        rework=rework,
    )
    # Rework first in the launch order too, so the audit record and the wave's
    # observable sequence report the same precedence the valve applied.
    picked = [*admission.rework, *admission.admitted]
    journal.append(
        record={
            "stage": "loop-pick",
            "dry_run": False,
            "budget": args.budget,
            "picked": [item.id for item in picked],
            "rework_picked": [item.id for item in admission.rework],
        }
    )
    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        futures = [
            pool.submit(
                dispatch_one,
                # BOTH per-dispatch ledger pins, applied in one place so the
                # factory this dispatch goes to and the workflow variant it
                # runs are recorded on the item together — a retry that reuses
                # one and re-resolves the other is the drift both pins exist
                # to prevent.
                args=args_with_dispatch_workflow_name(
                    args=args_with_dispatch_factory_target(
                        args=args, repo=repo, work_item_id=item.id
                    ),
                    repo=repo,
                    work_item_id=item.id,
                ),
                repo=repo,
                item=item,
                journal=journal,
                janitor=janitor,
            )
            for item in picked
        ]
        dispatched = [future.result() for future in futures]
    # Held / host-only-refused items ride in the outcomes so the verdict and
    # post-verdict alarm see them; capacity-deferred items ride along too, but
    # verdict/alarm classification treats them as non-defects.
    return admission.refused + admission.deferred + dispatched
