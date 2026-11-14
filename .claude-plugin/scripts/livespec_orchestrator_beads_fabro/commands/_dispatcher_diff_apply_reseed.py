"""Re-seeding a stale preserved seed by diff-applying its work onto the default branch's tip.

A preserved seed is the tree a released item's next dispatch starts from. When the
default branch has moved far past the seed's merge base, the seed is moved onto the
current tip. THE MOVE IS A DIFF-APPLY AND NEVER A REBASE: a rebase replays each of the
seed's commits and stops inside itself at the first conflict, and a stage that then
continues it makes a commit the commit runner's authored-subject guard refuses
(`LIVESPEC_COMMIT_NO_AUTHORED_SUBJECT`). A diff-apply produces ONE commit with ONE
authored subject, and either applies or names its conflicting paths, leaving no partial
operation behind. A seed sixty-six commits ahead is one apply rather than sixty-six
replays.

THE APPLY IS GIT'S OWN THREE-WAY TREE MERGE OF THE TIP AND THE SEED OVER THE SEED'S
MERGE BASE (`git merge-tree --write-tree --merge-base`). That is exactly "the seed's
merge-base diff applied to the tip's tree", computed without a working tree, an index
or a checkout, so no checkout is touched and no hook can run. It only writes objects to
the local object database.

EVERY READ OF THE REMOTE IS EXPLICIT AND A FAILED ONE IS NEVER AN ANSWER. A tip, a
seed, a merge base, a tree, an apply or a diff that cannot be read refuses and says
which, because reading any of them as a conflict, a clean apply or the absence of work
would route the item on a measurement nobody took. The three REAL refusals are kept
apart from those: a seed that carries no work (its tree equals its merge base's tree),
a conflict (every conflicting path named), and a seed whose work the tip already
carries. NONE of them publishes anything, and none of them moves, deletes or rewrites
the seed's ref.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_diff_apply_reseed_publish import (
    AppliedTree,
    ReseedRefusal,
    TreeChange,
    publish_reseed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling import (
    observed_ref_commit,
)

__all__: list[str] = [
    "ReseedRefusal",
    "Reseeded",
    "diff_apply_reseed",
]

_GIT_TIMEOUT_SECONDS = 300.0
_MERGE_CONFLICT_EXIT = 1
_GITLINK_MODE = "160000"
_REMOVED = "D"


@dataclass(frozen=True, kw_only=True)
class Reseeded:
    """One reseed commit, published and confirmed, with the facts a seed record names."""

    ref: str
    commit: str
    source_ref: str
    source_commit: str
    tip_commit: str
    default_branch: str


@dataclass(frozen=True, kw_only=True)
class _Revision:
    """The two remote commits a reseed joins, and the names its commit message carries."""

    work_item_id: str
    seed_ref: str
    seed: str
    default_branch: str
    tip: str


def _plan(*, runner: CommandRunner, repo: Path, revision: _Revision) -> AppliedTree | ReseedRefusal:
    """Everything up to the forge: the applied tree, how it differs, and the commit message."""
    basis = _basis(runner=runner, repo=repo, revision=revision)
    if isinstance(basis, ReseedRefusal):
        return basis
    tip_tree = basis.tip_tree
    if basis.seed_tree == basis.base_tree:
        return ReseedRefusal(
            detail=(
                f"seed ref {revision.seed_ref} at {revision.seed} carries no work: its tree "
                f"equals the tree of its merge base with {revision.default_branch}; "
                "nothing was published"
            )
        )
    applied = _applied_tree(runner=runner, repo=repo, revision=revision, base=basis.base)
    if isinstance(applied, ReseedRefusal):
        return applied
    if applied == tip_tree:
        return ReseedRefusal(
            detail=(
                f"the work of seed ref {revision.seed_ref} at {revision.seed} is already in "
                f"{revision.default_branch} at {revision.tip}: applying it changes no file; "
                "nothing was published"
            )
        )
    changes = _changes(
        runner=runner, repo=repo, seed=revision.seed, tip_tree=tip_tree, applied_tree=applied
    )
    if isinstance(changes, ReseedRefusal):
        return changes
    message = (
        f"reseed {revision.work_item_id} from {revision.seed_ref} "
        f"onto {revision.default_branch}\n\n"
        f"Livespec-Reseed-Source: {revision.seed_ref} {revision.seed}\n"
        f"Livespec-Reseed-Onto: {revision.tip}\n"
    )
    return AppliedTree(
        message=message, tip=revision.tip, tip_tree=tip_tree, applied_tree=applied, changes=changes
    )


@dataclass(frozen=True, kw_only=True)
class _Basis:
    """The merge base of the seed and the tip, and the three trees a reseed compares."""

    base: str
    tip_tree: str
    seed_tree: str
    base_tree: str


def _basis(*, runner: CommandRunner, repo: Path, revision: _Revision) -> _Basis | ReseedRefusal:
    """Fetch both commits, then read the tip's, the seed's and the merge base's trees."""
    fetched = _git(
        runner=runner, repo=repo, args=["fetch", "--no-tags", "origin", revision.tip, revision.seed]
    )
    if fetched.exit_code != 0:
        return _unread(what="the fetch of the seed and the default-branch tip", result=fetched)
    found = _git(runner=runner, repo=repo, args=["merge-base", revision.tip, revision.seed])
    if found.exit_code != 0:
        return _unread(
            what=f"the merge base of {revision.seed_ref} and {revision.default_branch}",
            result=found,
        )
    base = found.stdout.strip()
    trees = _trees(runner=runner, repo=repo, commits=(revision.tip, revision.seed, base))
    if isinstance(trees, ReseedRefusal):
        return trees
    return _Basis(base=base, tip_tree=trees[0], seed_tree=trees[1], base_tree=trees[2])


def diff_apply_reseed(
    *,
    runner: CommandRunner,
    repo: Path,
    work_item_id: str,
    seed_ref: str,
    default_branch: str,
) -> Reseeded | ReseedRefusal:
    """Apply the seed's merge-base diff onto the default branch's tip as one commit.

    Returns the published, remote-confirmed reseed, or the refusal naming why nothing
    was published.
    """
    tip = _remote_commit(
        runner=runner, repo=repo, ref=f"refs/heads/{default_branch}", what="the default-branch tip"
    )
    if isinstance(tip, ReseedRefusal):
        return tip
    seed = _remote_commit(runner=runner, repo=repo, ref=seed_ref, what="the seed")
    if isinstance(seed, ReseedRefusal):
        return seed
    applied = _plan(
        runner=runner,
        repo=repo,
        revision=_Revision(
            work_item_id=work_item_id,
            seed_ref=seed_ref,
            seed=seed,
            default_branch=default_branch,
            tip=tip,
        ),
    )
    if isinstance(applied, ReseedRefusal):
        return applied
    published = publish_reseed(
        runner=runner,
        repo=repo,
        work_item_id=work_item_id,
        applied=applied,
    )
    if isinstance(published, ReseedRefusal):
        return published
    return Reseeded(
        ref=published.ref,
        commit=published.commit,
        source_ref=seed_ref,
        source_commit=seed,
        tip_commit=tip,
        default_branch=default_branch,
    )


def _git(*, runner: CommandRunner, repo: Path, args: list[str]) -> CommandResult:
    return runner.run(argv=["git", *args], cwd=repo, timeout_seconds=_GIT_TIMEOUT_SECONDS)


def _unread(*, what: str, result: CommandResult) -> ReseedRefusal:
    """A read that could not be taken: never a conflict, a clean apply or an absence of work."""
    return ReseedRefusal(
        detail=(
            f"{what} could not be read (exit {result.exit_code}: {result.stderr.strip()}); "
            "the reseed was not attempted and nothing was published"
        )
    )


def _remote_commit(
    *, runner: CommandRunner, repo: Path, ref: str, what: str
) -> str | ReseedRefusal:
    """The commit origin advertises for `ref`, or why it could not be established."""
    listing = _git(runner=runner, repo=repo, args=["ls-remote", "origin", ref])
    if listing.exit_code != 0:
        return _unread(what=f"the remote read of {what} {ref}", result=listing)
    observed = observed_ref_commit(stdout=listing.stdout, ref=ref)
    if observed is None:
        return ReseedRefusal(detail=f"origin carries no {ref}; nothing was published")
    return observed


def _trees(
    *, runner: CommandRunner, repo: Path, commits: tuple[str, str, str]
) -> tuple[str, str, str] | ReseedRefusal:
    """The tree of each of three commits, in order."""
    trees: list[str] = []
    for commit in commits:
        read = _git(runner=runner, repo=repo, args=["rev-parse", "--verify", f"{commit}^{{tree}}"])
        if read.exit_code != 0:
            return _unread(what=f"the tree of {commit}", result=read)
        trees.append(read.stdout.strip())
    return (trees[0], trees[1], trees[2])


def _applied_tree(
    *, runner: CommandRunner, repo: Path, revision: _Revision, base: str
) -> str | ReseedRefusal:
    """The tip's tree with the seed's merge-base diff applied, or the conflicting paths."""
    merged = _git(
        runner=runner,
        repo=repo,
        args=[
            "merge-tree",
            "--write-tree",
            "-z",
            "--name-only",
            "--no-messages",
            f"--merge-base={base}",
            revision.tip,
            revision.seed,
        ],
    )
    fields = merged.stdout.split("\0")
    if merged.exit_code == 0:
        return fields[0]
    if merged.exit_code != _MERGE_CONFLICT_EXIT:
        return _unread(what=f"the apply of {revision.seed_ref} onto {revision.tip}", result=merged)
    paths = sorted({one for one in fields[1:] if one != ""})
    return ReseedRefusal(
        detail=(
            f"the diff of seed ref {revision.seed_ref} at {revision.seed} does not apply "
            f"cleanly onto {revision.tip}; "
            f"conflicting paths: {', '.join(paths)}; nothing was published"
        )
    )


def _changes(
    *, runner: CommandRunner, repo: Path, seed: str, tip_tree: str, applied_tree: str
) -> tuple[TreeChange, ...] | ReseedRefusal:
    """Every path the applied tree differs from the tip's tree at, as forge tree entries."""
    diff = _git(
        runner=runner,
        repo=repo,
        args=["diff-tree", "-r", "-z", "--no-renames", tip_tree, applied_tree],
    )
    if diff.exit_code != 0:
        return _unread(what="the diff from the tip's tree to the applied tree", result=diff)
    fields = diff.stdout.split("\0")
    changes: list[TreeChange] = []
    for header, path in zip(fields[0::2], fields[1::2], strict=False):
        old_mode, new_mode, _old_blob, new_blob, status = header.removeprefix(":").split(" ")
        if _GITLINK_MODE in (old_mode, new_mode):
            return ReseedRefusal(
                detail=(
                    f"the seed changes the submodule entry {path}, which a diff-apply cannot "
                    "publish through the forge; nothing was published"
                )
            )
        if status == _REMOVED:
            changes.append(TreeChange(path=path, mode=old_mode, blob=None, on_origin=False))
            continue
        held = _git(
            runner=runner, repo=repo, args=["rev-parse", "--verify", "--quiet", f"{seed}:{path}"]
        )
        changes.append(
            TreeChange(
                path=path,
                mode=new_mode,
                blob=new_blob,
                on_origin=held.exit_code == 0 and held.stdout.strip() == new_blob,
            )
        )
    return tuple(changes)
