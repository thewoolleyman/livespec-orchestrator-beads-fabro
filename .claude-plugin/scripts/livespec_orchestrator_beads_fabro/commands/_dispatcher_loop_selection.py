"""Dispatch-loop selection, preparation, and post-run disposition.

The janitor ref and the `.livespec.jsonc` read this module used to carry now
live in `_dispatcher_repo_config`, which that module's docstring explains; both
are imported back here, so this module's `__all__` and every existing call site
are unchanged.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from livespec_runtime.cross_repo.types import CrossRepoManifest, RefStatus
from livespec_runtime.work_items.lifecycle import is_item_ready, ready_sort_key

from livespec_orchestrator_beads_fabro.commands import _dispatcher_self_update as selfup
from livespec_orchestrator_beads_fabro.commands._cross_repo import load_manifest
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_result import (
    outcome_after_acceptance,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance_record import (
    record_base_advanced_after_arming,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration_emit import (
    emit_calibration,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion import (
    complete_and_accept,
    escalate_needs_human_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dead_implementer import (
    record_dead_implementer_truncation_if_observed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    MERGE_HELD_STAGE,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_groom_door import groom_door_claimed
from livespec_orchestrator_beads_fabro.commands._dispatcher_groom_park import record_groom_draft
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import invoker_from_args
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile, utc_now_iso
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import load_items
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_cause import (
    record_needs_human_cause,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
    journal_path,
    plugin_root,
    workflow_toml,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_exhaustion import (
    record_provider_exhaustion_if_observed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_registered_install_currency import (
    default_install_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_repo_config import (
    janitor_core_ref,
    livespec_config_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_staleness_gate import (
    apply_dispatcher_staleness_gate,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_terminal_preservation import (
    preserve_terminated_run_work,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_terminal_routing import (
    dispose_terminal_routing,
)
from livespec_orchestrator_beads_fabro.commands._ready_aging_order import ready_aging_order
from livespec_orchestrator_beads_fabro.commands._sibling_status_lookup import (
    make_sibling_status_lookup,
)
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "is_dispatch_candidate",
    "janitor_core_ref",
    "livespec_config_text",
    "post_run_dispositions",
    "prepare",
    "ready_items",
    "run_id",
]


def run_id() -> str:
    """A non-credential-bearing correlation id for one dispatch run.

    Generated per invocation (a random uuid4 hex): it carries no env / goal
    / secret material by construction, so it is always safe to ship in the
    alarm body and to correlate against the journal.
    """
    return selfup.run_id()


def prepare(
    *,
    args: argparse.Namespace,
    repo: Path,
) -> tuple[list[WorkItem], JournalFile] | None:
    if not repo.is_dir() or not workflow_toml(args=args).is_file():
        _ = write_stderr(text="ERROR: --repo or workflow config does not exist\n")
        return None
    journal = JournalFile(
        path=journal_path(args=args, repo=repo),
        identity=invoker_from_args(args=args),
    )
    staleness_exit = apply_dispatcher_staleness_gate(
        plugin_root=plugin_root(),
        journal=journal,
        cwd=repo,
        # The host install registry: a session executing a build older than
        # what `repo` resolves is surfaced here (never refused), with a
        # restart remedy -- a plugin update cannot move a running session.
        install_record=default_install_record(),
    )
    if staleness_exit is not None:
        return None
    return load_items(repo=repo), journal


def ready_items(*, items: list[WorkItem], repo: Path) -> list[WorkItem]:
    index = {item.id: item for item in items}
    manifest = load_manifest(project_root=repo)
    # Build the cross-tenant sibling resolver ONCE per readiness pass and thread
    # the same instance through every candidate check, so a CLOSED cross-repo
    # sibling stops blocking while OPEN / unresolvable ones still fail closed
    # (qiqz6b Part B). Lazy + memoized: it reads nothing unless an item actually
    # carries a sibling dependency.
    sibling_status_lookup = make_sibling_status_lookup(project_root=repo)
    ready = [
        item
        for item in items
        if is_dispatch_candidate(
            item=item,
            index=index,
            manifest=manifest,
            sibling_status_lookup=sibling_status_lookup,
            repo=repo,
        )
    ]
    # Compose the single canonical ranking authority so the Dispatcher's drain
    # order never diverges from what `next` advertises (i3jiny): the fractional
    # rank stays the sole primary key, with the equal-rank ready-age tiebreak
    # inside each rank tier. Both aging inputs are resolved from the SAME
    # project root `next` resolves them from — the Dispatcher does not re-sort
    # ready work by age on its own, which the ratified clause forbids. The key
    # is built ONCE per pass, so the tenant's ready instants are read once.
    order = ready_aging_order(project_root=repo)
    return sorted(
        ready,
        key=ready_sort_key(
            now=datetime.now(tz=timezone.utc),
            ready_since_lookup=order.ready_since_lookup,
            ready_aging_threshold_hours=order.ready_aging_threshold_hours,
        ),
    )


def is_dispatch_candidate(
    *,
    item: WorkItem,
    index: dict[str, WorkItem],
    manifest: CrossRepoManifest,
    sibling_status_lookup: Callable[[str, str], RefStatus] | None = None,
    repo: Path | None = None,
) -> bool:
    """Whether this row is one the Dispatcher may launch on this pass.

    Three members, and the third is the narrow one: a `ready` row, a
    `pending-approval` row whose dependencies are clear, and an `active` row
    the GROOM DOOR itself claimed and pinned. The door opens `backlog ->
    active` under a claim and a groom-variant pin and then returns, so without
    the third arm the row it prepared is one no launch path can pick up — it
    is not `ready`, so this predicate refused it, and the `--item` preflight
    that consumes this predicate read the door's own claim as somebody else's
    in-flight dispatch. `groom_door_claimed` owns that recognition, and it is
    scoped to the door's own claim: an ordinary `active` row is unaffected, so
    this is NOT a widening to `active` work in general. The status test that
    scopes it stays INSIDE that predicate rather than being restated as a guard
    here, so ONE module answers "is this the door's claim?" end to end.

    `repo` is the target repository the claim and pin are read against; it
    defaults, like `sibling_status_lookup`, to the working directory.
    """
    effective_repo = repo if repo is not None else Path.cwd()
    effective_sibling_status_lookup = (
        sibling_status_lookup
        if sibling_status_lookup is not None
        else make_sibling_status_lookup(project_root=effective_repo)
    )
    if is_item_ready(
        item=item,
        index=index,
        manifest=manifest,
        sibling_status_lookup=effective_sibling_status_lookup,
    ):
        return True
    if groom_door_claimed(repo=effective_repo, item=item):
        return True
    if item.status != "pending-approval":
        return False
    ready_projection = replace(item, status="ready")
    return is_item_ready(
        item=ready_projection,
        index=index,
        manifest=manifest,
        sibling_status_lookup=effective_sibling_status_lookup,
    )


def post_run_dispositions(  # noqa: PLR0913 — kw-only post-run stage; each field is an independent caller input.
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
    wall_clock_seconds: float,
    dispatch_context_size: int,
    token_supplier: Callable[[], str],
) -> DispatchOutcome:
    """Run the machine-path dispositions after a dispatch reaches its terminal.

    The sequence the Dispatcher runs once a `run_dispatch` returns: on a
    confirmed merge (when armed) run the post-merge acceptance valve
    (`complete` -> `acceptance`, then `accept` per `acceptance_policy`),
    journal the terminal outcome, bounce a non-converging slice to `backlog`
    (n5kina), and emit the calibration telemetry (yfsv4j). Aggregated here so
    `_dispatch_one` stays a single readable sequence; every step is keyed off
    the terminal `outcome` and is independently fail-soft where it touches IO.

    RETURNS the outcome as the acceptance valve left it, which is what the
    dispatch RESULT reports. Every step below reads the REVISED outcome rather
    than the janitor's: the revision happens first, so the journaled terminal, the
    alarm and the exit code all describe the same dispatch — a park reported as a
    close is the finding (`_dispatcher_acceptance_result`), and a journal that
    disagreed with the result would just move it.
    """
    # The acceptance valve is the POST-MERGE valve, and every green outcome had
    # merged until the merge hold introduced one that has not. Completing a held
    # item into `acceptance` would accept unmerged work, and the item leaving
    # `active` would retract the attention row that keeps the hold visible; the
    # hold is released by a person, and the merge and this valve follow then.
    if outcome.status == "green" and outcome.stage != MERGE_HELD_STAGE and args.close_on_merge:
        outcome = outcome_after_acceptance(
            outcome=outcome,
            disposition=complete_and_accept(
                repo=repo,
                item=item,
                outcome=outcome,
                journal=journal,
            ),
        )
    record_provider_exhaustion_if_observed(
        outcome=outcome,
        journal=journal,
        journal_path=journal.path,
        now_iso=utc_now_iso(),
    )
    # NO EVENT PROJECTION FOLLOWS THE TERMINAL. v127 made "the per-node
    # selection record ... and the `provider-limit-release` record" the
    # authoritative fallback history and forbade depending on any engine
    # failover event, so this terminal's fallback evidence is already written:
    # the selection record by the dispatch that rendered it, and the release
    # record by `dispose_provider_limit_release` through the terminal routing
    # below. A second read of the run's event stream could only re-derive what
    # those two already carry, and on the current engine it re-derives nothing
    # at all -- the event it looked for does not exist.
    record_dead_implementer_truncation_if_observed(outcome=outcome, journal=journal)
    journal.append(record={"stage": "outcome", "outcome": asdict(outcome)})
    # BEFORE the escalation below, which is the blocked transition: the tree
    # clause requires its ledger comment written "before the item's blocked
    # transition", because that comment is the only durable pointer at the
    # preservation ref. Both legs are fail-soft, so neither can cost the item
    # its rest state or change this dispatch's exit code.
    preserve_terminated_run_work(args=args, repo=repo, item=item, outcome=outcome, journal=journal)
    # BESIDE the pointer, by the ratified groom-cut clause's own word: a
    # groom-pinned run that terminated needs-human carries the drafted
    # decomposition, and the comment written here is where that draft rests
    # and what the later apply dispatch reads. A no-op for every other run.
    #
    # An APPLY run publishes a FILING PLAN over that same channel instead, and
    # the seam files it host-side. When it does, there is no human decision
    # left and the original has already CLOSED as regroomed-out, so escalating
    # would move a closed regroom target to `blocked` — undoing the very
    # disposition the contract calls this run's terminal one.
    groom_cut_filed = record_groom_draft(
        args=args, repo=repo, item=item, outcome=outcome, journal=journal
    )
    # BEFORE the escalation, which is the opposite of the needs-human pair
    # below and is the ratified clause's own choice. This record is the only
    # account of which head was armed against which default-branch tip, so a
    # lifecycle write that landed while the record was never attempted would
    # leave an operator an item at needs-human with nothing to reconstruct the
    # overtaking from. Neither write prevents the other — every arm of this one
    # is fail-soft — so the order decides only which account survives a partial
    # failure. A no-op for every outcome that is not this ending.
    record_base_advanced_after_arming(repo=repo, item=item, outcome=outcome, journal=journal)
    if not groom_cut_filed:
        escalate_needs_human_block(repo=repo, item=item, outcome=outcome, journal=journal)
        # AFTER the escalation, because the escalation owns the lifecycle write
        # and this owns only the account of WHY. Writing the account first
        # would leave a record explaining a block that a failed lifecycle write
        # then never applied. A no-op for every outcome that is not a
        # needs-human ending, and for the groom-cut path above, whose own
        # comment is that run's terminal record.
        record_needs_human_cause(repo=repo, item=item, outcome=outcome, journal=journal)
    # Every non-green terminal route, as one group: the non-convergence bounce,
    # the stall-watchdog cancellation, and the provider-limit release. They are
    # mutually exclusive by predicate, so the order among them cannot change
    # which one fires, and `_dispatcher_terminal_routing` is where a reader can
    # see that no non-green terminal is left with no disposition at all.
    dispose_terminal_routing(
        repo=repo, item=item, outcome=outcome, journal=journal, now_iso=utc_now_iso()
    )
    emit_calibration(
        args=args,
        repo=repo,
        item=item,
        outcome=outcome,
        journal=journal,
        wall_clock_seconds=wall_clock_seconds,
        dispatch_context_size=dispatch_context_size,
        token_supplier=token_supplier,
    )
    return outcome
