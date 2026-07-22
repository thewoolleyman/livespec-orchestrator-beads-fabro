"""Dispatch-loop selection, preparation, and janitor ref helpers."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import asdict, replace
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import load_items
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
    journal_path,
    workflow_toml,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    janitor_core_ref_from_config,
)
from livespec_orchestrator_beads_fabro.commands._sibling_status_lookup import (
    make_sibling_status_lookup,
)
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "candidates",
    "is_dispatch_candidate",
    "janitor_core_ref",
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
    journal = JournalFile(path=journal_path(args=args, repo=repo))
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
    config = repo / ".livespec.jsonc"
    if not config.exists():
        return janitor_core_ref_from_config(config_text="{}")
    return janitor_core_ref_from_config(config_text=config.read_text(encoding="utf-8"))


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
        )
    ]
    # Compose the single canonical ranking authority so the Dispatcher's
    # drain order never diverges from what `next` advertises (i3jiny):
    # (rank, id) — the fractional rank is the sole ordering key.
    return sorted(ready, key=ready_sort_key)


def is_dispatch_candidate(
    *,
    item: WorkItem,
    index: dict[str, WorkItem],
    manifest: CrossRepoManifest,
    sibling_status_lookup: Callable[[str, str], RefStatus] | None = None,
) -> bool:
    if is_item_ready(
        item=item, index=index, manifest=manifest, sibling_status_lookup=sibling_status_lookup
    ):
        return True
    if item.status != "pending-approval":
        return False
    ready_projection = replace(item, status="ready")
    return is_item_ready(
        item=ready_projection,
        index=index,
        manifest=manifest,
        sibling_status_lookup=sibling_status_lookup,
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
    if outcome.status == "green" and args.close_on_merge:
        complete_and_accept(
            repo=repo,
            item=item,
            outcome=outcome,
            journal=journal,
        )
    journal.append(record={"stage": "outcome", "outcome": asdict(outcome)})
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
