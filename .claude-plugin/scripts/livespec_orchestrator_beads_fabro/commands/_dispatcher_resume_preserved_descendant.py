"""The refusal text for a preservation that contains unpublished work."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoverySeed

__all__: list[str] = [
    "PreservedDescendant",
    "PreservedDescendantUnobservable",
    "descending_preservation_refusal",
    "preserved_descendant",
]


@dataclass(frozen=True, kw_only=True)
class PreservedDescendant:
    """A preservation ref that contains work absent from its published head."""

    preservation_ref: str
    preservation_tip: str
    published_head: str


@dataclass(frozen=True, kw_only=True)
class PreservedDescendantUnobservable:
    """The ancestry or tree read needed to protect a preservation did not answer."""

    detail: str


def descending_preservation_refusal(
    *, preservation_ref: str, preservation_tip: str, published_head: str
) -> str:
    """Name the preserved descendant a resume would otherwise discard."""
    return (
        f"preserved ref {preservation_ref} at {preservation_tip} descends from the"
        f" published head {published_head} with a different tree, so a resume would"
        " discard preserved work; dispatch it plainly instead"
    )


def preserved_descendant(
    *,
    runner: CommandRunner,
    repo: Path,
    preservation: RecoverySeed,
    published_head: str,
    head_is_later: bool | None,
) -> PreservedDescendant | PreservedDescendantUnobservable | None:
    """Measure whether a same-or-newer preservation would be lost by a resume.

    A published head from an earlier run may legitimately resume over a later
    preservation, so it never spends the ancestry reads.  A same-run or later
    preservation is different: the comparison is the last chance to keep work
    committed after the published head from being silently abandoned.
    """
    tip = preservation.preservation_tip_sha or preservation.commit_sha
    if head_is_later is True:
        return None
    if head_is_later is None:
        return PreservedDescendantUnobservable(
            detail=(
                "publishing-run-unobservable: the published head and preserved ref could"
                " not be ordered by run, so the preserved-descendant comparison could not"
                " be taken"
            )
        )
    ancestry = runner.run(
        argv=["git", "merge-base", "--is-ancestor", published_head, tip],
        cwd=repo,
        timeout_seconds=120.0,
    )
    if ancestry.exit_code != 0:
        if ancestry.exit_code == 1:
            return None
        return PreservedDescendantUnobservable(
            detail=(
                "preserved-ancestry-unobservable: git merge-base could not establish"
                f" whether preserved ref {preservation.preservation_ref} at {tip} descends"
                f" from published head {published_head}"
            )
        )
    head_tree = _tree(runner=runner, repo=repo, commit=published_head)
    tip_tree = _tree(runner=runner, repo=repo, commit=tip)
    return (
        PreservedDescendantUnobservable(
            detail=(
                "preserved-tree-unobservable: git rev-parse could not compare the trees"
                f" of preserved ref {preservation.preservation_ref} at {tip} and published"
                f" head {published_head}"
            )
        )
        if head_tree is None or tip_tree is None
        else (
            None
            if head_tree == tip_tree
            else PreservedDescendant(
                preservation_ref=preservation.preservation_ref,
                preservation_tip=tip,
                published_head=published_head,
            )
        )
    )


def _tree(*, runner: CommandRunner, repo: Path, commit: str) -> str | None:
    """Read one commit tree, returning no answer when the object is unavailable."""
    result = runner.run(
        argv=["git", "rev-parse", "--verify", "--quiet", f"{commit}^{{tree}}"],
        cwd=repo,
        timeout_seconds=120.0,
    )
    return result.stdout.strip() if result.exit_code == 0 and result.stdout.strip() else None
