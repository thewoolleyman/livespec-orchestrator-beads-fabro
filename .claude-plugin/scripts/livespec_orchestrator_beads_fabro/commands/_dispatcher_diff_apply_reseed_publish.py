"""Publishing a diff-apply reseed's tree as one commit on a reseed ref.

THE MECHANICS ONLY. `_dispatcher_diff_apply_reseed` decides whether a reseed is owed
and computes the tree the seed's work makes over the default branch's tip; this module
puts that tree on the forge as one commit over the tip, creates the reseed ref, and
confirms the ref by one remote read, reporting which step failed.

EVERY WRITE GOES THROUGH THE FORGE'S GIT DATA API, AND NONE THROUGH `git push`. The
Dispatcher runs from the host's PRIMARY CHECKOUT, whose commit-refuse pre-push hook
refuses every push, for the reason `_dispatcher_preserved_tree_publish` records. The
reseed therefore builds its objects on the forge: a blob for each changed file the
forge does not already hold, a tree over the tip's tree, a commit over the tip and the
ref, with no working tree written and no hook run.

A BLOB IS POSTED ONLY WHEN THE FORGE CANNOT ALREADY HOLD IT. A file the seed changed
and the tip did not has the seed's own blob in the applied tree, and the seed ref
already carries that object on the forge, so the tree entry names it by id. Only a file
BOTH sides changed has a merged blob nobody has published, and its bytes are read from
the local object database and posted. The forge's tree id is then compared with the
tree the apply computed locally: git object ids are content addresses, so equality
proves the forge holds byte-for-byte the tree the apply made, and a mismatch (a text
mode that rewrote a line ending, for one) refuses before any commit exists.
"""

from __future__ import annotations

import base64
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publish_branch_preserve import (
    create_ref_argv,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling import (
    observed_ref_commit,
)

__all__: list[str] = [
    "AppliedTree",
    "PublishedReseed",
    "ReseedRefusal",
    "TreeChange",
    "publish_reseed",
    "reseed_ref",
]

_FORGE_TIMEOUT_SECONDS = 120.0
_COMMITS_ENDPOINT = "/repos/{owner}/{repo}/git/commits"
_BLOBS_ENDPOINT = "/repos/{owner}/{repo}/git/blobs"
_TREES_ENDPOINT = "/repos/{owner}/{repo}/git/trees"


@dataclass(frozen=True, kw_only=True)
class TreeChange:
    """One path the applied tree differs from the tip's tree at.

    `blob` is `None` for a removal. `on_origin` says the forge already holds the blob,
    because the seed ref carries it; a blob it does not hold is posted before the tree.
    """

    path: str
    mode: str
    blob: str | None
    on_origin: bool


@dataclass(frozen=True, kw_only=True)
class AppliedTree:
    """The seed's work applied onto the tip: the tree, how it differs, and its commit message."""

    message: str
    tip: str
    tip_tree: str
    applied_tree: str
    changes: tuple[TreeChange, ...]


@dataclass(frozen=True, kw_only=True)
class PublishedReseed:
    """The reseed ref, confirmed by a remote read at the reseed commit."""

    ref: str
    commit: str


@dataclass(frozen=True, kw_only=True)
class ReseedRefusal:
    """Nothing was published, or the publication could not be confirmed; `detail` says why."""

    detail: str


def reseed_ref(*, work_item_id: str, commit: str) -> str:
    """The ref a reseed commit is published at."""
    return f"refs/livespec/reseed/{work_item_id}/{commit}"


def publish_reseed(
    *, runner: CommandRunner, repo: Path, work_item_id: str, applied: AppliedTree
) -> PublishedReseed | ReseedRefusal:
    """Put the applied tree on the forge as one commit over the tip, then confirm its ref."""
    entries: list[dict[str, object]] = []
    for change in applied.changes:
        blob = change.blob
        if blob is not None and not change.on_origin:
            blob = _posted_blob(runner=runner, repo=repo, change=change)
            if isinstance(blob, ReseedRefusal):
                return blob
        entries.append({"path": change.path, "mode": change.mode, "type": "blob", "sha": blob})
    tree = _posted(
        runner=runner,
        repo=repo,
        endpoint=_TREES_ENDPOINT,
        body={"base_tree": applied.tip_tree, "tree": entries},
    )
    if tree != applied.applied_tree:
        return ReseedRefusal(
            detail=(
                f"the forge's tree {tree or 'none'} differs from the applied tree "
                f"{applied.applied_tree}, so no commit was created and nothing was published"
            )
        )
    commit = _posted(
        runner=runner,
        repo=repo,
        endpoint=_COMMITS_ENDPOINT,
        body={"message": applied.message, "tree": tree, "parents": [applied.tip]},
    )
    if commit is None:
        return ReseedRefusal(
            detail=(
                f"the forge named no commit for tree {tree} over parent {applied.tip}; "
                "nothing was published"
            )
        )
    ref = reseed_ref(work_item_id=work_item_id, commit=commit)
    created = runner.run(
        argv=create_ref_argv(ref=ref, sha=commit),
        cwd=repo,
        timeout_seconds=_FORGE_TIMEOUT_SECONDS,
    )
    if created.exit_code != 0:
        return ReseedRefusal(
            detail=(
                f"creating the ref {ref} at {commit} through the forge "
                f"exited {created.exit_code}"
            )
        )
    return _confirmed(runner=runner, repo=repo, ref=ref, commit=commit)


def _confirmed(
    *, runner: CommandRunner, repo: Path, ref: str, commit: str
) -> PublishedReseed | ReseedRefusal:
    """One remote read: the ref must stand at the reseed commit before success is reported."""
    listing = runner.run(
        argv=["git", "ls-remote", "origin", ref],
        cwd=repo,
        timeout_seconds=_FORGE_TIMEOUT_SECONDS,
    )
    observed = observed_ref_commit(stdout=listing.stdout, ref=ref)
    if listing.exit_code == 0 and observed == commit:
        return PublishedReseed(ref=ref, commit=commit)
    return ReseedRefusal(
        detail=(
            f"the remote read did not confirm {ref} at {commit}: "
            f"origin observed {observed or 'nothing'}"
        )
    )


def _posted_blob(*, runner: CommandRunner, repo: Path, change: TreeChange) -> str | ReseedRefusal:
    """Read one merged blob out of the local object database and post it to the forge."""
    read = runner.run(
        argv=["git", "cat-file", "blob", str(change.blob)],
        cwd=repo,
        timeout_seconds=_FORGE_TIMEOUT_SECONDS,
    )
    if read.exit_code != 0:
        return ReseedRefusal(detail=f"the merged blob of {change.path} could not be read locally")
    posted = _posted(
        runner=runner,
        repo=repo,
        endpoint=_BLOBS_ENDPOINT,
        body={
            "content": base64.b64encode(read.stdout.encode("utf-8")).decode("ascii"),
            "encoding": "base64",
        },
    )
    if posted is None:
        return ReseedRefusal(detail=f"the forge named no blob for the merged {change.path}")
    return posted


def _posted(
    *, runner: CommandRunner, repo: Path, endpoint: str, body: dict[str, object]
) -> str | None:
    """POST one Git Data object and return the name the forge gave it, or `None`.

    The body travels on an unlinked temporary file's descriptor rather than in argv: a
    changed file's base64 content can exceed the argument-length limit.
    """
    with tempfile.TemporaryFile() as handle:
        _ = handle.write(json.dumps(body, sort_keys=True).encode("utf-8"))
        _ = handle.seek(0)
        result: CommandResult = runner.run(
            argv=["gh", "api", "--method", "POST", endpoint, "--input", "-", "--jq", ".sha"],
            cwd=repo,
            timeout_seconds=_FORGE_TIMEOUT_SECONDS,
            stdin=handle.fileno(),
        )
    named = result.stdout.strip()
    return named if result.exit_code == 0 and named else None
