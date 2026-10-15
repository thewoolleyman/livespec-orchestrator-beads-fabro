"""Publishing a dead run's changed files as one commit on a preservation ref.

THE MECHANICS ONLY. `_dispatcher_preserved_tree` owns whether to act, the
ledger comment and the journal record; this module performs the four forge
operations and reports WHICH ONE failed, because the ratified clause requires
the failure comment to name the step (a blob, the tree, the commit, or the ref)
and a caller re-deriving that from a message would be a second account of it.

EVERY OPERATION GOES THROUGH THE FORGE'S GIT DATA API, AND NONE THROUGH `git`.
The run's work exists only inside a stopped container's work tree on the
factory server: there is no local checkout carrying it, so there is nothing to
`git push` even if pushing were available. It is not. The Dispatcher runs from
the host's PRIMARY CHECKOUT, whose commit-refuse pre-push hook refuses every
push -- the measured defect `_dispatcher_publish_branch_preserve`'s own
docstring records. Creating the objects directly is therefore both the only
route and the correct one: no working tree is written, no hook runs, and the
commit is built from the bytes the factory reported rather than from whatever a
checkout happened to hold.

THE COMMIT IS A RECOVERY ARTIFACT AND NOT A COMMIT TO LAND. It carries no
Red/Green trailers, passed no check suite and ran no hook, which is exactly why
the ratified clause forbids a recovery seed from carrying it: a seed records the
run's BASE commit and this REF, so that checking out the base and taking this
tree onto it as uncommitted work are one act.

THE REF IS CREATED THROUGH `_dispatcher_publish_branch_preserve.create_ref_argv`
rather than through a builder of this module's own. Both writers put a commit
under `refs/livespec/preserved-publish/`, and two spellings of one forge call
drift silently because each one's own tests keep passing.
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
    preserved_publish_ref,
)
from livespec_orchestrator_beads_fabro.commands._fabro_run_files import RunFile

__all__: list[str] = [
    "STEP_BLOB",
    "STEP_COMMIT",
    "STEP_REF",
    "STEP_TREE",
    "PreservedTree",
    "PublishFailure",
    "publish_preserved_tree",
]

# The four publication steps, as the ratified clause names them. A failure
# carries one of these verbatim, so the comment an operator reads names the
# operation rather than a paraphrase of it.
STEP_BLOB = "blob"
STEP_TREE = "tree"
STEP_COMMIT = "commit"
STEP_REF = "ref"

_FORGE_TIMEOUT_SECONDS = 120.0

_COMMITS_ENDPOINT = "/repos/{owner}/{repo}/git/commits"
_BLOBS_ENDPOINT = "/repos/{owner}/{repo}/git/blobs"
_TREES_ENDPOINT = "/repos/{owner}/{repo}/git/trees"

# The mode a tree entry takes when the factory reported none. A regular
# non-executable file is what a run changes in every measured case, and a wrong
# guess here is recoverable (the recovered tree is applied as uncommitted work,
# where mode is re-decided) while refusing the publication is not.
DEFAULT_FILE_MODE = "100644"


@dataclass(frozen=True, kw_only=True)
class PreservedTree:
    """The ref the run's tree now rests on, and the commit it carries."""

    ref: str
    commit: str
    file_count: int


@dataclass(frozen=True, kw_only=True)
class PublishFailure:
    """Nothing, or only part, was published; `step` names what failed."""

    step: str
    detail: str


def publish_preserved_tree(
    *,
    runner: CommandRunner,
    repo: Path,
    work_item_id: str,
    base_commit: str,
    files: tuple[RunFile, ...],
    message: str,
) -> PreservedTree | PublishFailure:
    """Put `files` on a preservation ref as one commit over `base_commit`.

    The base TREE is read before anything is created, because a tree built
    without it would carry only the files the run touched and would read as a
    commit that DELETED the rest of the repository -- a recovery artifact that
    silently misreports the run's work is worse than none.
    """
    base_tree = _object_name(
        result=runner.run(
            argv=["gh", "api", f"{_COMMITS_ENDPOINT}/{base_commit}", "--jq", ".tree.sha"],
            cwd=repo,
            timeout_seconds=_FORGE_TIMEOUT_SECONDS,
        )
    )
    if base_tree is None:
        return PublishFailure(
            step=STEP_TREE,
            detail=f"the forge named no tree for the run's base commit {base_commit}",
        )
    tree = _changed_tree(runner=runner, repo=repo, base_tree=base_tree, files=files)
    if isinstance(tree, PublishFailure):
        return tree
    commit = _posted(
        runner=runner,
        repo=repo,
        endpoint=_COMMITS_ENDPOINT,
        body={"message": message, "tree": tree, "parents": [base_commit]},
    )
    if commit is None:
        return PublishFailure(
            step=STEP_COMMIT,
            detail=f"the forge named no commit for tree {tree} over parent {base_commit}",
        )
    ref = preserved_publish_ref(work_item_id=work_item_id, head=commit)
    created = runner.run(
        argv=create_ref_argv(ref=ref, sha=commit),
        cwd=repo,
        timeout_seconds=_FORGE_TIMEOUT_SECONDS,
    )
    if created.exit_code != 0:
        return PublishFailure(
            step=STEP_REF,
            detail=(
                f"creating {ref} at {commit} through the forge reference interface"
                f" exited {created.exit_code}"
            ),
        )
    return PreservedTree(ref=ref, commit=commit, file_count=len(files))


def _changed_tree(
    *,
    runner: CommandRunner,
    repo: Path,
    base_tree: str,
    files: tuple[RunFile, ...],
) -> str | PublishFailure:
    """One tree entry per change, REMOVALS INCLUDED, posted over the base tree.

    A removal is an entry whose `sha` is JSON null, which is how the Git Data
    API spells "drop this path from the base tree". Leaving a removal out
    instead would publish a tree in which the deleted file still stands -- a
    recovery artifact that disagrees with the run in the one direction nobody
    inspects, because the file being present looks like the normal case.
    """
    entries: list[dict[str, object]] = []
    for changed in files:
        if changed.content is None:
            entries.append(
                {"path": changed.path, "mode": changed.mode, "type": "blob", "sha": None}
            )
            continue
        blob = _posted(
            runner=runner,
            repo=repo,
            endpoint=_BLOBS_ENDPOINT,
            body={
                "content": base64.b64encode(changed.content).decode("ascii"),
                "encoding": "base64",
            },
        )
        if blob is None:
            return PublishFailure(
                step=STEP_BLOB,
                detail=f"the forge named no blob for the run's {changed.path}",
            )
        entries.append({"path": changed.path, "mode": changed.mode, "type": "blob", "sha": blob})
    tree = _posted(
        runner=runner,
        repo=repo,
        endpoint=_TREES_ENDPOINT,
        body={"base_tree": base_tree, "tree": entries},
    )
    if tree is None:
        return PublishFailure(
            step=STEP_TREE,
            detail=f"the forge named no tree for the {len(files)} changed file(s) read",
        )
    return tree


def _posted(
    *,
    runner: CommandRunner,
    repo: Path,
    endpoint: str,
    body: dict[str, object],
) -> str | None:
    """POST one Git Data object and return the name the forge gave it.

    The body travels on an UNLINKED TEMPORARY FILE'S DESCRIPTOR rather than in
    argv, for the reason the vault sink gives: an argument is visible in the
    host process table and is what a timeout diagnostic quotes back. Here it is
    also a size question -- a changed file's base64 content can exceed the
    argument-length limit, which would fail the publication for a reason that
    has nothing to do with the forge.
    """
    with tempfile.TemporaryFile() as handle:
        _ = handle.write(json.dumps(body, sort_keys=True).encode("utf-8"))
        _ = handle.seek(0)
        return _object_name(
            result=runner.run(
                argv=["gh", "api", "--method", "POST", endpoint, "--input", "-", "--jq", ".sha"],
                cwd=repo,
                timeout_seconds=_FORGE_TIMEOUT_SECONDS,
                stdin=handle.fileno(),
            )
        )


def _object_name(*, result: CommandResult) -> str | None:
    """The object name one `gh api` call reported, or `None` for any non-answer.

    An exit 0 that printed NOTHING is a non-answer and not an empty name: `--jq`
    renders a null field as the empty string, so a response missing the key
    reaches here looking exactly like a success. Returning it would put the
    empty string into the next request as a parent or a tree.
    """
    if result.exit_code != 0:
        return None
    named = result.stdout.strip()
    return named if named else None
