"""The reconcile-merged valve's PREFLIGHT: may this invocation proceed, and how.

Split out of `_dispatcher_reconcile_merged` along its cohesion seam once that
module gained a third arm. Everything here answers ONE question — is this
invocation admissible, and what did it resolve for the arms to use — and nothing
here does any half of the reconcile. The supervisor keeps the other concern: the
journal, the arm selection, and the shared outcome tail.

The refusal ORDER is load-bearing and is preserved verbatim from the supervisor:
the repository, then the item's existence, then the refusals its own ledger state
decides, then the `--janitor` declaration, and only then the `--force`-gated
live-dispatch lock. Every refusal reports before any write, which is what lets the
valve be re-run after one.

The REPOSITORY half of that order is `repo_path_refusal`, and it is published
because the supervisor calls it ahead of everything — including the invoker
refusal, which reads `dispatcher.require_invoker` from the repository's committed
configuration. That is one position earlier than this function, and the position
is the whole repair: a `--repo` value that is not a repository path resolves a
configuration read onto nothing, and every refusal downstream of that read then
names a cause drawn from an EMPTY block rather than from the operator's mistake.

`ACCEPTANCE_STATUS` is published because the supervisor's arm selection reads it:
the status vocabulary belongs with the admission decision that validates it, and a
second literal in the supervisor could drift from the admitted set.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_check_suite_view import (
    check_suite_refusal,
    resolve_janitor_check_suite,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    live_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import load_items
from livespec_orchestrator_beads_fabro.commands._dispatcher_otel_wiring import parse_janitor
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "ACCEPTANCE_STATUS",
    "ReconcilePreflight",
    "reconcile_preflight",
    "repo_path_refusal",
]

# The refusal for a `--repo` value that is not a repository path. It NAMES the
# submitted value, because the operator's mistake is in that value and a refusal
# that withheld it left nothing to compare against what was meant.
_REPO_PATH_REFUSAL = (
    "ERROR: reconcile-merged refused: --repo requires a path to an existing "
    "repository directory, and {given} is not one. Pass the repository's path — "
    "absolute, or relative to the current directory — rather than its name.\n"
)

# The one status that selects the re-accept arm rather than the janitor arm.
ACCEPTANCE_STATUS = "acceptance"
_RECONCILE_MERGED_ALLOWED_STATUSES = frozenset(
    {ACCEPTANCE_STATUS, "active", "backlog", "ready", "blocked"}
)
# The refusal for a rework-pending item, which NAMES the route that replaces
# this valve. It is deliberately unconditional on `--force`: forcing past it
# would re-run a post-run disposition that already ran and chose rework.
_REWORK_PENDING_REFUSAL = (
    "ERROR: reconcile-merged refused: work-item {item_id} carries rework:pending, so its "
    "dispatch already COMPLETED its post-run disposition and that disposition's outcome "
    "was rework. Drive the fix-forward rework re-dispatch instead — the next dispatcher "
    "drain pass, or `dispatcher.py dispatch --repo {repo} --item {item_id}`. --force does "
    "not bypass this refusal. When the work is ALREADY merged and only the acceptance "
    "criteria have since been repaired, re-run with --regrade to re-grade the merge "
    "instead of re-implementing it.\n"
)
# The mirror refusal: `--regrade` revisits a verdict, so an item that never
# reached a failing one has nothing for the arm to do.
_REGRADE_UNMARKED_REFUSAL = (
    "ERROR: reconcile-merged --regrade refused: work-item {item_id} does not carry "
    "rework:pending, so no acceptance verdict is waiting to be revisited. Run "
    "reconcile-merged without --regrade.\n"
)


@dataclass(frozen=True, kw_only=True)
class ReconcilePreflight:
    item: WorkItem
    janitor: tuple[str, ...] | None


def repo_path_refusal(*, repo: Path, given: str) -> str | None:
    """Refuse a `--repo` value that is not a repository path, or `None` to proceed.

    `given` is the value as SUBMITTED rather than the `Path` it was parsed into,
    because `Path` normalises — a trailing slash, a leading `./` — and a refusal
    quoting the normalised form asks the operator to recognise a string they did
    not type.

    An existence test is deliberately not enough: a regular file EXISTS, so the
    configuration read it admits lands on nothing in exactly the way an absent
    path does, and the refusal downstream names the same wrong cause.
    """
    if not repo.is_dir():
        return _REPO_PATH_REFUSAL.format(given=given)
    return None


def reconcile_preflight(*, args: argparse.Namespace, repo: Path) -> ReconcilePreflight | int:
    items = {item.id: item for item in load_items(repo=repo)}
    item = items.get(args.item)
    if item is None:
        _ = write_stderr(text=f"ERROR: work-item {args.item} not found\n")
        return EXIT_PRECONDITION_ERROR
    item_refusal = _item_precondition_refusal(item=item, repo=repo, regrade=args.regrade)
    if item_refusal is not None:
        _ = write_stderr(text=item_refusal)
        return EXIT_PRECONDITION_ERROR
    janitor, janitor_exit = _janitor_preflight(args=args, repo=repo)
    if janitor_exit is not None:
        return janitor_exit
    if not args.force:
        live_detail = _live_dispatch_refusal(args=args, repo=repo, item=item)
        if live_detail is not None:
            _ = write_stderr(text=live_detail)
            return EXIT_PRECONDITION_ERROR
    return ReconcilePreflight(item=item, janitor=janitor)


def _janitor_preflight(
    *, args: argparse.Namespace, repo: Path
) -> tuple[tuple[str, ...] | None, int | None]:
    """The `--janitor` half of the preflight: parse the override, then resolve it.

    Returns `(janitor, None)` to proceed, or `(None, exit_code)` to
    short-circuit. The reconcile valve is the second `--janitor` entry point, so
    it refuses on the same unresolvable declaration the dispatch preamble does:
    `build_plan` would otherwise hand the janitor the empty argv a
    present-but-unusable `dispatcher.janitor.check_suite` resolves to, and it
    would do so on an item whose merge has already landed.
    """
    janitor, janitor_ok = parse_janitor(raw=args.janitor)
    if not janitor_ok:
        return None, 2
    check_suite_error = check_suite_refusal(
        check_suite=resolve_janitor_check_suite(cwd=repo, janitor=janitor)
    )
    if check_suite_error is not None:
        _ = write_stderr(text=check_suite_error)
        return None, EXIT_PRECONDITION_ERROR
    return janitor, None


def _item_precondition_refusal(*, item: WorkItem, repo: Path, regrade: bool) -> str | None:
    """The refusals decided by the item's own ledger state, in order.

    Rework-pending is checked FIRST because it binds WHATEVER the item's
    status is, so a marked `acceptance` item is refused here rather than
    reaching the status gate; and it sits ahead of the `--force`-gated live
    lock check in the caller so `--force` cannot reach past it.

    `--regrade` is the ONE thing that reaches past it, and only onto the marked
    item the arm exists for. The two flags are deliberately not
    interchangeable: `--force` bypasses the live-dispatch heartbeat and is
    explicitly refused here, while `--regrade` selects a different arm that
    re-grades rather than re-dispositions. An UNMARKED item is refused the arm
    for the mirror-image reason — its acceptance never failed, so there is no
    verdict to revisit and the ordinary valve is the route.

    `ACCEPTANCE_STATUS` is in the admitted set rather than refused: an item
    resting there has its own arm, which re-runs only the acceptance pass. The
    statuses still refused are the ones no arm serves — a closed item has nothing
    to reconcile, and an unadmitted one never dispatched.
    """
    if item.rework_pending and not regrade:
        return _REWORK_PENDING_REFUSAL.format(item_id=item.id, repo=repo)
    if regrade and not item.rework_pending:
        return _REGRADE_UNMARKED_REFUSAL.format(item_id=item.id)
    if item.status not in _RECONCILE_MERGED_ALLOWED_STATUSES:
        return (
            f"ERROR: reconcile-merged expected active or parked item {item.id}; "
            f"found {item.status}\n"
        )
    return None


def _live_dispatch_refusal(*, args: argparse.Namespace, repo: Path, item: WorkItem) -> str | None:
    _ = args
    lock = live_dispatch_lock(repo=repo, work_item_id=item.id)
    if lock is None:
        return None
    age_seconds = max(0.0, time.time() - lock.started_at_epoch)
    return (
        f"ERROR: reconcile-merged refused: dispatch lock is held by live pid "
        f"{lock.pid} for work-item {item.id} (age {age_seconds:.1f}s). "
        f"Confirm with `fabro ps`, wait for the janitor window to close, or rerun "
        f"with --force only after confirming the original dispatcher process is dead.\n"
    )
