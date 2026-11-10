"""Deleting a closed item's preservation refs from origin.

The preservation refs a factory run leaves on origin -- `refs/livespec/wip/<item>/
<run>/<n>` captures, `refs/livespec/preserved-publish/<item>/<head>` copies of a dead
run's published head, and `refs/heads/needs-human/<run>` branches -- exist so a
re-dispatch of an OPEN item can seed from the work a dead run left behind. Once the
Dispatcher itself has closed the item, or has collected an ended run of a closed
item, nothing can use them any more, and nothing else ever removes them: origin held
617 of them on 2026-11-04.

TWO ENTRY POINTS, ONE PER MOMENT THE CONTRACT NAMES. `delete_closed_item_refs` is
the close/accept moment and takes every ref under the item's two namespaces.
`delete_ended_run_refs` is the ended-run collection and takes that run's own
work-in-progress refs, its `needs-human` ref and the item's preserved-publish refs.
Neither runs for an item that is not closed: the callers decide that, and this
module is handed only the item (and run) a deletion is owed for.

A DELETION THAT FAILS IS JOURNALED, NEVER RAISED. The caller reads the boolean and
leaves the run (and so the next pass's retry) standing; the item's own state is not
touched here at all. A listing the forge refuses is journaled under the prefix it
could not list, since no individual ref is known, and nothing is deleted for it.

THE TRANSPORT IS THE FORGE REFERENCE INTERFACE, NEVER `git push`, for the reason
`_dispatcher_publish_branch_preserve` records: the Dispatcher runs from the host's
primary checkout, whose pre-push hook refuses every push. The deletion argv is that
module's own `delete_ref_argv`.

THE LISTING IS A PREFIX MATCH AND A PREFIX CAN OVER-MATCH. A run id that is the
leading part of another run's id (`RUN1` and `RUN10`) matches both under
`matching-refs/heads/needs-human/RUN1`, so a target that names one exact ref keeps
only the listed ref equal to it. Item namespaces end in a slash so that one item's
id is never the leading part of another's.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    JournalWriter,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publish_branch_preserve import (
    PRESERVED_PUBLISH_REF_PREFIX,
    delete_ref_argv,
)

__all__: list[str] = [
    "JOURNAL_STAGE_DELETION_FAILED",
    "delete_closed_item_refs",
    "delete_ended_run_refs",
]

JOURNAL_STAGE_DELETION_FAILED = "preservation-ref-deletion-failed"

_WIP_REF_PREFIX = "refs/livespec/wip"
_NEEDS_HUMAN_REF_PREFIX = "refs/heads/needs-human"
_FORGE_TIMEOUT_SECONDS = 120.0
_DETAIL_EXCERPT_CHARS = 2000
_MATCHING_REFS_ENDPOINT = "/repos/{owner}/{repo}/git/matching-refs"


@dataclass(frozen=True, kw_only=True)
class _Target:
    """One namespace (or one exact ref) whose refs are to be deleted."""

    prefix: str
    exact: bool


def delete_closed_item_refs(
    *,
    runner: CommandRunner,
    repo: Path,
    journal: JournalWriter,
    work_item_id: str,
) -> bool:
    """Delete every wip and preserved-publish ref of a closed item; whether all went."""
    return _delete(
        runner=runner,
        repo=repo,
        journal=journal,
        work_item_id=work_item_id,
        targets=_item_targets(work_item_id=work_item_id),
    )


def delete_ended_run_refs(
    *,
    runner: CommandRunner,
    repo: Path,
    journal: JournalWriter,
    work_item_id: str,
    run_id: str,
) -> bool:
    """Delete an ended run's refs and its closed item's preserved-publish refs."""
    return _delete(
        runner=runner,
        repo=repo,
        journal=journal,
        work_item_id=work_item_id,
        targets=(
            _Target(prefix=f"{_WIP_REF_PREFIX}/{work_item_id}/{run_id}/", exact=False),
            _Target(prefix=f"{PRESERVED_PUBLISH_REF_PREFIX}/{work_item_id}/", exact=False),
            _Target(prefix=f"{_NEEDS_HUMAN_REF_PREFIX}/{run_id}", exact=True),
        ),
    )


def _item_targets(*, work_item_id: str) -> tuple[_Target, ...]:
    return (
        _Target(prefix=f"{_WIP_REF_PREFIX}/{work_item_id}/", exact=False),
        _Target(prefix=f"{PRESERVED_PUBLISH_REF_PREFIX}/{work_item_id}/", exact=False),
    )


def _delete(
    *,
    runner: CommandRunner,
    repo: Path,
    journal: JournalWriter,
    work_item_id: str,
    targets: tuple[_Target, ...],
) -> bool:
    complete = True
    for target in targets:
        refs = _listed(
            runner=runner, repo=repo, journal=journal, work_item_id=work_item_id, target=target
        )
        if refs is None:
            complete = False
            continue
        for ref in refs:
            deleted = runner.run(
                argv=delete_ref_argv(ref=ref), cwd=repo, timeout_seconds=_FORGE_TIMEOUT_SECONDS
            )
            if deleted.exit_code != 0:
                complete = False
                _journal_failure(
                    journal=journal,
                    work_item_id=work_item_id,
                    operation="delete",
                    ref=ref,
                    exit_code=deleted.exit_code,
                    detail=deleted.stderr,
                )
    return complete


def _listed(
    *,
    runner: CommandRunner,
    repo: Path,
    journal: JournalWriter,
    work_item_id: str,
    target: _Target,
) -> list[str] | None:
    """The refs origin carries under `target`, or None when the forge refused to list."""
    result = runner.run(
        argv=[
            "gh",
            "api",
            "--paginate",
            f"{_MATCHING_REFS_ENDPOINT}/{target.prefix.removeprefix('refs/')}",
            "--jq",
            ".[].ref",
        ],
        cwd=repo,
        timeout_seconds=_FORGE_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        _journal_failure(
            journal=journal,
            work_item_id=work_item_id,
            operation="list",
            ref=target.prefix,
            exit_code=result.exit_code,
            detail=result.stderr,
        )
        return None
    listed = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return [ref for ref in listed if ref == target.prefix] if target.exact else listed


def _journal_failure(
    *,
    journal: JournalWriter,
    work_item_id: str,
    operation: str,
    ref: str,
    exit_code: int,
    detail: str,
) -> None:
    journal.append(
        record={
            "stage": JOURNAL_STAGE_DELETION_FAILED,
            "work_item_id": work_item_id,
            "operation": operation,
            "ref": ref,
            "exit_code": exit_code,
            "detail": detail.strip()[:_DETAIL_EXCERPT_CHARS],
        }
    )
