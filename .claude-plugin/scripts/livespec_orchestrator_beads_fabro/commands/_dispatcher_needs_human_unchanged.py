"""Separate the needs-human refs that carry work from the ones that carry none.

A needs-human ref CARRIES NO WORK when its tip commit's tree is identical to the
tree of the tip's merge base with the default branch. Such a ref is not preserved
work and is not any run's terminal tree, so recovery routing never seeds from it
and never lets it outrank another ref, published head or capture; it is listed as
passed over with the reason `no-change` instead. The rule applies whatever wrote
the ref, which is why it is read here, from the tips, and never from the ref name.

A COMPARISON THAT CANNOT BE TAKEN IS ITS OWN ANSWER. It is read neither as a change
nor as the absence of one: reading it as a change seeds a run from the default
branch's own tree, and reading it as no change discards finished work. Every step
that can fail therefore returns `NeedsHumanRefsUnobservable`.

THE DEFAULT BRANCH IS FETCHED WITH THE TIPS. A remote-tracking ref this clone last
fetched days ago gives a merge base older than the one the run branched from, and
a ref that changed nothing then differs from that old base by every commit master
has gained since. A tip missing from the local object store would likewise make
every comparison unobservable, so the tips are fetched in the same round trip.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_default_branch import (
    resolve_default_branch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_refs import (
    NeedsHumanRef,
    NeedsHumanRefsUnobservable,
)

__all__: list[str] = [
    "UnchangedSplit",
    "split_unchanged_needs_human_refs",
]

_TREE_LINES = 2
_NO_COMMON_ANCESTOR = 1


@dataclass(frozen=True, kw_only=True)
class UnchangedSplit:
    """The carrying refs that hold work, and the ones that hold none."""

    with_work: list[NeedsHumanRef]
    unchanged: list[NeedsHumanRef]


def split_unchanged_needs_human_refs(
    *,
    runner: CommandRunner,
    repo: Path,
    carrying: list[NeedsHumanRef],
    remote: str,
    timeout_seconds: float,
) -> UnchangedSplit | NeedsHumanRefsUnobservable:
    """Each carrying ref, sorted by whether its tip tree differs from its merge base's."""
    if not carrying:
        return UnchangedSplit(with_work=[], unchanged=[])
    default = resolve_default_branch(repo=repo, runner=runner)
    if default is None:
        return NeedsHumanRefsUnobservable(
            detail=(
                "the default branch could not be resolved, so whether a needs-human ref"
                " carries any work could not be established"
            )
        )
    tracking = f"refs/remotes/{remote}/{default}"
    fetched = runner.run(
        argv=[
            "git",
            "fetch",
            "--quiet",
            "--no-tags",
            remote,
            f"+refs/heads/{default}:{tracking}",
            *sorted({one.ref for one in carrying}),
        ],
        cwd=repo,
        timeout_seconds=timeout_seconds,
    )
    if fetched.exit_code != 0:
        return NeedsHumanRefsUnobservable(
            detail=(
                f"git fetch {remote} of {default} and {len(carrying)} needs-human tips exited"
                f" {fetched.exit_code}; whether a needs-human ref carries any work could not"
                " be established"
            )
        )
    with_work: list[NeedsHumanRef] = []
    unchanged: list[NeedsHumanRef] = []
    for one in carrying:
        same = _tree_equals_merge_base_tree(
            runner=runner,
            repo=repo,
            commit=one.commit_sha,
            tracking=tracking,
            timeout_seconds=timeout_seconds,
        )
        if isinstance(same, NeedsHumanRefsUnobservable):
            return same
        (unchanged if same else with_work).append(one)
    return UnchangedSplit(with_work=with_work, unchanged=unchanged)


def _tree_equals_merge_base_tree(
    *, runner: CommandRunner, repo: Path, commit: str, tracking: str, timeout_seconds: float
) -> bool | NeedsHumanRefsUnobservable:
    """Whether the tip's tree is the tree of its merge base with the default branch.

    A tip sharing no history with the default branch has no merge base and therefore
    differs from it: that is a tree with work, not a comparison that failed.
    """
    base = runner.run(
        argv=["git", "merge-base", commit, tracking],
        cwd=repo,
        timeout_seconds=timeout_seconds,
    )
    if base.exit_code == _NO_COMMON_ANCESTOR and not base.stdout.strip():
        return False
    merge_base = base.stdout.strip()
    if base.exit_code != 0 or not merge_base:
        return _unreadable(commit=commit, step="merge base", code=base.exit_code)
    trees = runner.run(
        argv=["git", "rev-parse", f"{commit}^{{tree}}", f"{merge_base}^{{tree}}"],
        cwd=repo,
        timeout_seconds=timeout_seconds,
    )
    named = trees.stdout.split()
    if trees.exit_code != 0 or len(named) != _TREE_LINES:
        return _unreadable(commit=commit, step="tree", code=trees.exit_code)
    return named[0] == named[1]


def _unreadable(*, commit: str, step: str, code: int) -> NeedsHumanRefsUnobservable:
    """The unobservable answer for a comparison step that failed."""
    return NeedsHumanRefsUnobservable(
        detail=(
            f"the {step} of needs-human tip {commit} could not be read (exit {code}), so"
            " whether the ref carries any work could not be established"
        )
    )
