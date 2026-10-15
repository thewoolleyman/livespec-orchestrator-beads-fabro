"""Preserving a checkpoint-failed run's tree on a forge ref.

The run whose engine checkpoint failed left its work in a stopped container's
work tree on the factory server and nowhere else: the checkpoint is what would
have committed it, a stage diff artifact never carries a failed node's tree,
and the run's terminal patch -- the one other carrier -- is exactly what is
absent in the case this module exists for. So the sequence here is the only
route from that work to anything durable: read the changed files off the
factory that ran the dispatch, then publish them as one commit on a
preservation ref.

THIS MODULE JOINS A READ TO A PUBLICATION AND OWNS NEITHER. `_fabro_run_files`
reads, `_dispatcher_preserved_tree_publish` publishes, and both are reachable
without the other so each is exercisable on its own. What is owned here is the
STEP ATTRIBUTION across the join: a failed read is the clause's "the files
read" step, which the publication layer never sees and therefore cannot name.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_publish import (
    STEP_FILES_READ,
    PreservedTree,
    PublishFailure,
    publish_preserved_tree,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpPort
from livespec_orchestrator_beads_fabro.commands._fabro_run_files import (
    RunFilesUnreadable,
    read_run_files,
)

__all__: list[str] = ["preserved_tree_message", "publish_run_tree"]


def preserved_tree_message(*, work_item_id: str, run_id: str) -> str:
    """The commit message the preservation commit carries.

    It says on its own face that the commit is a RECOVERY ARTIFACT, because the
    one way this ref does harm is being mistaken for work to land: it ran no
    hook, passed no check suite and carries no Red/Green trailers.
    """
    return (
        f"fabro({run_id}): preserved tree of a checkpoint-failed run for {work_item_id}\n"
        "\n"
        "Recovery artifact, NOT a commit to land: these are the changed files the\n"
        "factory still held after the run's engine checkpoint failed. No hook ran\n"
        "and no check suite passed on them. Recover by checking out this commit's\n"
        "parent and taking this tree onto it as uncommitted work.\n"
    )


def publish_run_tree(
    *,
    port: FabroHttpPort,
    runner: CommandRunner,
    repo: Path,
    work_item_id: str,
    run_id: str,
    base_commit: str,
) -> PreservedTree | PublishFailure:
    """Read one run's changed files from its factory and publish them.

    An unreadable read is reported as the FILES-READ step rather than let the
    publication proceed on an empty file set: publishing nothing would create a
    ref whose tree equals the base commit's, which reads as a run that changed
    nothing -- the one conclusion this whole clause exists to prevent.
    """
    read = read_run_files(port=port, run_id=run_id)
    if isinstance(read, RunFilesUnreadable):
        return PublishFailure(step=STEP_FILES_READ, detail=read.detail)
    return publish_preserved_tree(
        runner=runner,
        repo=repo,
        work_item_id=work_item_id,
        base_commit=base_commit,
        files=read.files,
        message=preserved_tree_message(work_item_id=work_item_id, run_id=run_id),
    )
