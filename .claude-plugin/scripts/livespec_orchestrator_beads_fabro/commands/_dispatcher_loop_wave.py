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

from livespec_orchestrator_beads_fabro.commands._acp_factory_run_reader import (
    FactoryRunReader,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
    resolve_acp_preflight,
)
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
    utc_now_iso,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop import dispatch_one
from livespec_orchestrator_beads_fabro.commands._dispatcher_pre_dispatch_wall import (
    post_admission_publish_branch_reclaim,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_launch import (
    LaunchPins,
    journal_recovery_route,
    recovery_launch_args,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routing import (
    route_recovery,
)
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
    #
    # The wait is GATED on this pass's own ACP preflight verdict, because
    # `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
    # priority" admits the wait only for "a legacy single candidate and a
    # genuinely exhausted fallback chain, never a primary-only probe refusal
    # with a viable fallback". The verdict has to be resolved HERE rather than
    # taken from the admission valve below: the wait runs strictly before
    # admission, so there is no earlier verdict to inherit. Resolving it twice
    # in one pass costs nothing observable — no probe is supplied on either
    # side, so the resolution reads only committed configuration, the workflow
    # graph and the journal, and writes nothing.
    await_usable_credential(
        repo=repo,
        journal=journal,
        budget=args.budget,
        preflight=resolve_acp_preflight(
            repo=repo,
            journal_path=journal.path,
            now_iso=utc_now_iso(),
            factory_runs=FactoryRunReader(repo=repo),
        ),
    )
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
    # RECOVERY ROUTING, which the clause places after the pre-dispatch wall (run
    # by the command module above) and strictly BEFORE the valve, while every
    # candidate is still `ready`. It reads only; a candidate with no earlier
    # dispatch that released it is routed `fresh` without any remote measurement,
    # so an ordinary drain pays nothing for it.
    routing = route_recovery(args=args, repo=repo, candidates=selected_candidates, journal=journal)
    # The admission valve drains the candidate set up to the per-repo WIP cap:
    # host-only items are routed away, manual / unresolvable items are held +
    # surfaced, marked rework rows re-occupy the slots their own `active` rows
    # already hold BEFORE any new admission, and the highest-rank
    # admission-eligible items fill what free slots remain (ready -> active,
    # assignee set). Capacity-deferred items simply wait for the next pass.
    admission = admit_and_select(
        repo=repo,
        items=items,
        # A HELD item is withheld from the valve, which is the whole of "it stays
        # `ready`": the valve is the only thing that writes `ready -> active`.
        candidates=routing.offered(candidates=selected_candidates),
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
    # The stale publish-branch reclaim, for exactly what this wave is about to
    # launch and no more. It DELETES `feat/<item>` on origin and closes any pull
    # request open on it, so a candidate the valve DEFERRED must reach the next
    # pass with its branch and that pull request intact (bd-ib-huoyk7) -- which
    # is why it is here, past the capacity decision, rather than in the
    # pre-dispatch wall every entry point runs before admission. It still
    # precedes every launch below, which is what keeps each new run's
    # `publish_draft` push a plain fast-forward.
    # A `resume`-routed item is deliberately NOT offered: the surviving publish
    # branch is the branch its run resumes on, so preserving that head to a ref
    # and deleting the branch would destroy exactly what the resume exists to
    # finish, and the journal would read like a healthy reclaim.
    post_admission_publish_branch_reclaim(
        args=args,
        repo=repo,
        items=[item for item in picked if routing.reclaims(work_item_id=item.id)],
        journal=journal,
    )
    # Each launching item's route, recorded now that the valve has decided it
    # will launch. Here rather than at the measurement, because a route is valid
    # only for the pass that measured it and a deferred item must carry nothing
    # out of this one. Written on this thread, in `picked` order, so the journal
    # reads as the wave's own sequence rather than as whatever order the pool
    # happened to start the launches in.
    for item in picked:
        journal_recovery_route(route=routing.route_for(work_item_id=item.id), journal=journal)
    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        futures = [
            pool.submit(
                dispatch_one,
                # BOTH per-dispatch ledger pins AND this item's recovery route,
                # applied in one per-item place so the factory this dispatch
                # goes to, the workflow variant it runs and the tree it starts
                # from are decided together — a retry that reuses one and
                # re-resolves another is the drift the pins exist to prevent,
                # and a route written onto the wave's shared namespace would
                # apply one item's head to every item in the wave.
                args=recovery_launch_args(
                    args=args,
                    repo=repo,
                    work_item_id=item.id,
                    route=routing.route_for(work_item_id=item.id),
                    pins=LaunchPins(
                        factory=args_with_dispatch_factory_target,
                        workflow=args_with_dispatch_workflow_name,
                    ),
                ),
                repo=repo,
                item=item,
                journal=journal,
                janitor=janitor,
                # The valve's OWN evaluation, so each launch selects its
                # per-node ACP candidate from the read that admitted the item.
                # Re-resolving one here would be a second read of the
                # availability evidence, which the clause forbids outright --
                # and the two reads would disagree silently, because each
                # produces a perfectly well-formed candidate.
                verdict=admission.verdict,
            )
            for item in picked
        ]
        dispatched = [future.result() for future in futures]
    # Held / host-only-refused items ride in the outcomes so the verdict and
    # post-verdict alarm see them; capacity-deferred items ride along too, but
    # verdict/alarm classification treats them as non-defects. A RECOVERY-held
    # item rides on the same terms the clause gives it — "reported as a deferred
    # outcome on the same terms as a capacity deferral" — so a drain that held one
    # reports it rather than returning a wave that silently lost a candidate.
    return admission.refused + admission.deferred + routing.held_outcomes() + dispatched
