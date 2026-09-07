"""Dispatch-loop selection, preparation, and janitor ref helpers."""

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
from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration_emit import (
    emit_calibration,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion import (
    bounce_non_convergence_to_backlog,
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
    journal_path,
    plugin_root,
    workflow_toml,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    janitor_core_ref_from_config,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserve_reference import (
    preserve_checkpointed_work_reference,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_exhaustion import (
    record_provider_exhaustion_if_observed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_registered_install_currency import (
    default_install_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_staleness_gate import (
    apply_dispatcher_staleness_gate,
)
from livespec_orchestrator_beads_fabro.commands._sibling_status_lookup import (
    make_sibling_status_lookup,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "candidates",
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


def candidates(
    *,
    args: argparse.Namespace,
    items: list[WorkItem],
    repo: Path,
) -> list[WorkItem]:
    ranked = ready_items(items=items, repo=repo)
    requested = set(args.items or [])
    if requested:
        return [item for item in ranked if item.id in requested]
    return ranked


def janitor_core_ref(*, repo: Path) -> str:
    return janitor_core_ref_from_config(config_text=livespec_config_text(repo=repo))


def livespec_config_text(*, repo: Path) -> str:
    """The target repository's committed `.livespec.jsonc`; `{}` when it has none.

    A repository with no config declares nothing, which is the same input as an
    empty object -- the resolver, not this reader, decides which fields that
    leaves unresolved.

    PUBLIC because plan build reads it too: the WHOLE integration contract now
    resolves from this one text, so the reader that answers it crosses a module
    boundary rather than staying private to the core-pin wrapper above.
    """
    config = repo / ".livespec.jsonc"
    if not config.exists():
        return "{}"
    return config.read_text(encoding="utf-8")


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
    # Compose the single canonical ranking authority so the Dispatcher's
    # drain order never diverges from what `next` advertises (i3jiny):
    # (rank, id) — the fractional rank is the sole ordering key. The key is
    # built ONCE per pass, and with no `ready_since_lookup` injected the aging
    # tiebreak stays inert, so the ordering is exactly what it was.
    return sorted(ready, key=ready_sort_key(now=datetime.now(tz=timezone.utc)))


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
) -> None:
    """Run the machine-path dispositions after a dispatch reaches its terminal.

    The sequence the Dispatcher runs once a `run_dispatch` returns: on a
    confirmed merge (when armed) run the post-merge acceptance valve
    (`complete` -> `acceptance`, then `accept` per `acceptance_policy`),
    journal the terminal outcome, bounce a non-converging slice to `backlog`
    (n5kina), and emit the calibration telemetry (yfsv4j). Aggregated here so
    `_dispatch_one` stays a single readable sequence; every step is keyed off
    the terminal `outcome` and is independently fail-soft where it touches IO.
    """
    # The acceptance valve is the POST-MERGE valve, and every green outcome had
    # merged until the merge hold introduced one that has not. Completing a held
    # item into `acceptance` would accept unmerged work, and the item leaving
    # `active` would retract the attention row that keeps the hold visible; the
    # hold is released by a person, and the merge and this valve follow then.
    if outcome.status == "green" and outcome.stage != MERGE_HELD_STAGE and args.close_on_merge:
        complete_and_accept(
            repo=repo,
            item=item,
            outcome=outcome,
            journal=journal,
        )
    record_provider_exhaustion_if_observed(
        outcome=outcome,
        journal=journal,
        now_iso=utc_now_iso(),
    )
    record_dead_implementer_truncation_if_observed(outcome=outcome, journal=journal)
    journal.append(record={"stage": "outcome", "outcome": asdict(outcome)})
    preserved = attempt(
        action=lambda: preserve_checkpointed_work_reference(
            args=args,
            repo=repo,
            item=item,
            outcome=outcome,
            journal=journal,
        ),
        exceptions=(OSError,),
    )
    if isinstance(preserved, AttemptFailure):
        journal.append(
            record={
                "stage": "preserve-by-reference-error",
                "work_item_id": item.id,
                "reason": type(preserved.error).__name__,
                "outcome_stage": outcome.stage,
                "outcome_status": outcome.status,
            }
        )
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
    if not groom_cut_filed:
        escalate_needs_human_block(repo=repo, item=item, outcome=outcome, journal=journal)
    bounce_non_convergence_to_backlog(repo=repo, item=item, outcome=outcome, journal=journal)
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
