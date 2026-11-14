"""Delete a closed item's preservation refs when the Dispatcher closes or accepts it.

The close-time half of `_dispatcher_preservation_ref_deletion`, reached from the
lifecycle write seam (`_dispatcher_lifecycle_writes._reconcile`) AFTER the run
reconciliation: the item's non-terminal runs have been terminated by then, so no
run can push another ref behind the deletion.

IT NEVER FAILS THE LEDGER WRITE, for the reason `_dispatcher_run_reconcile_hook`
gives: the disposition has already landed and is correct, and a forge that will not
answer is a fact about the forge. A refused deletion is journaled by the deletion
itself with the ref; the retry is the Dispatcher's ended-run collection, which
deletes the same namespaces again for any ended run of the closed item before it
removes the run, so a refusal leaves the run standing for the next pass.

Only an item the write left CLOSED is acted on. Every other landing -- an item moved
to `blocked`, `ready`, `backlog`, or `active` -- keeps every preservation ref, because
a re-dispatch of an open item is exactly what those refs are for. The StoreConfig with
no `repo_root` carries no repository to delete from, so it is a documented no-op.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preservation_ref_deletion import (
    delete_closed_item_refs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_reconcile_hook import (
    dispatch_journal_path,
)
from livespec_orchestrator_beads_fabro.effects import attempt
from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = ["delete_refs_after_lifecycle_write"]

_CLOSED_STATUSES = frozenset({"closed", "done"})


def delete_refs_after_lifecycle_write(
    *,
    path: StoreConfig,
    item_id: str,
    status: str,
    runner: CommandRunner | None = None,
) -> None:
    """Delete `item_id`'s preservation refs when a ledger write landed it closed."""
    if status not in _CLOSED_STATUSES:
        return
    repo = path.repo_root
    if repo is None:
        return
    # The journal append is the one operation that can raise here (the runner maps a
    # launch failure to a non-zero result), and it must not fail the ledger write.
    _ = attempt(
        action=lambda: delete_closed_item_refs(
            runner=ShellCommandRunner() if runner is None else runner,
            repo=repo,
            journal=JournalFile(path=dispatch_journal_path(repo=repo)),
            work_item_id=item_id,
        ),
        exceptions=(OSError,),
    )
