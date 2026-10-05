"""Which pull request a host record targets: the latest merged run's, resolved.

The host-leg clause of `SPECIFICATION/contracts.md` (v115) binds a host record to "the
pull request of the latest merged run for the item", and says outright that "a host
record on an earlier pull request ... is not evidence". This module answers that one
question for the posting primitive.

WHY IT IS RESOLVED AND NOT NAMED. A `--pull-request` flag would put the clause's own
precondition in the publisher's hands, and getting it wrong is silent: the post succeeds,
the record is permanent, and the acceptance pass later refuses it for sitting on an
earlier pull request — a refusal the successful post gave no hint of. Resolving it means
the primitive cannot publish onto the wrong one at all.

IT IS THE RECONCILE VALVE'S OWN AUTHORITY, reused rather than re-rolled. Two resolutions
of "which merge belongs to this item" could name two different pull requests, and the
disagreement would be invisible because each would be a plausible merge — so the record
the primitive posts and the merge the acceptance pass grades would simply be about
different things.

WHY THE IMPORTS ARE LOCAL. Resolving the merge pulls in the reconcile supervisor, which
imports the completion path, which imports the acceptance pass — and the acceptance pass
imports the proof evidence the posting primitive also uses. A module-scope import closes
that cycle; these are deferred to the call so the chain stays one-directional.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import resolve_fabro_bin
from livespec_orchestrator_beads_fabro.commands._dispatcher_default_branch import (
    resolve_default_branch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
    livespec_config_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    build_plan,
    janitor_reconcile_checkout_path,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "host_record_target",
]


def host_record_target(*, repo: Path, item: WorkItem, runner: CommandRunner) -> int | None:
    """The pull request of the item's latest merged run, or `None` when none resolves.

    Resolved through the reconcile valve's own authority rather than from a flag, so a
    record cannot be published onto an earlier pull request — where the acceptance pass
    would correctly refuse it, for a reason the successful post would not reveal.
    """
    # Imported here rather than at module scope: the resolution pulls in the reconcile
    # supervisor, which imports the completion path, which imports the acceptance pass —
    # and the acceptance pass imports the proof evidence this module also uses. A
    # module-scope import closes that cycle.
    from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
        JournalFile,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_merged_pr import (
        resolve_merged_pr,
    )

    plan = build_plan(
        repo=repo,
        work_item_id=item.id,
        workflow_toml=repo / "tmp" / f"host-record-{item.id}-workflow.toml",
        goal_file=repo / "tmp" / f"host-record-{item.id}-goal.md",
        fabro_bin=resolve_fabro_bin(cwd=repo),
        janitor=None,
        janitor_checkout=janitor_reconcile_checkout_path(repo=repo, work_item_id=item.id),
        config_text=livespec_config_text(repo=repo),
        default_branch=resolve_default_branch(repo=repo, runner=runner),
    )
    merged = resolve_merged_pr(
        plan=plan,
        item=item,
        runner=runner,
        journal=JournalFile(path=repo / "tmp" / f"host-record-{item.id}.jsonl"),
    )
    return merged.number if merged is not None and not isinstance(merged, str) else None
