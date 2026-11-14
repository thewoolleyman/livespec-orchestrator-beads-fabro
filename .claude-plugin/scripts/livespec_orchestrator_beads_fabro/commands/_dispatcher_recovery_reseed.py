"""The diff-apply reseed: one stale seed moved onto the default branch's tip.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work" → "A stale seed is re-seeded by
diff-applying its work onto the default branch's tip". The seed's WORK is its diff
against its merge base with the default branch, and the reseed applies that diff
to the tip's tree and records it as ONE commit whose only parent is the tip.

WHY A DIFF-APPLY AND NOT A REBASE, A CHERRY-PICK SEQUENCE OR A MERGE. The preserved
tree is whatever a dead run left, so its history is the run's checkpoint series and
carries nothing a later run needs; replaying that series commit by commit conflicts
on every checkpoint that touched a file the default branch also moved. One
three-way apply of the net diff conflicts only where the net work and the default
branch genuinely collide, which is the only conflict worth holding an item for.

THE SCRATCH CLONE IS OUTSIDE EVERY CHECKOUT AND EVERY SANDBOX, WITH HOOKS DISABLED.
The Dispatcher runs from a host primary checkout whose pre-push hook refuses every
push, and a reseed must publish a commit object the forge does not hold yet — so
the push runs from a throwaway repository nothing else reads. The reseed moves,
deletes and rewrites NO ref of the source seed, any needs-human ref, any
preservation ref or any checkout: its only write is the new reseed ref.

THE COMMIT IS REPRODUCIBLE. Its author and committer dates are the tip's own
committer date, so two passes reseeding one seed onto one tip record the SAME
commit and publish the SAME ref, instead of leaving a new ref behind per pass.

EVERY COMMAND THE REPRODUCTION CANNOT TAKE IS AN UNOBSERVABLE MEASUREMENT, never a
conflict and never a clean apply: the steps run through one loop with one failure
arm, so no step can be skipped, and the publication is confirmed by a remote read
before the reseed is reported done. Only an apply that left unmerged paths is a
conflict.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_preserved import SEED_REMOTE
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    RecoverySeed,
    ReseedConflict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling import observed_ref_commit

__all__: list[str] = [
    "RESEED_REF_PREFIX",
    "ReseedUnobservable",
    "SeedCarriesNoWork",
    "reseed",
]

RESEED_REF_PREFIX = "refs/livespec/reseed"

_TIMEOUT_SECONDS = 120.0
_FETCH_TIMEOUT_SECONDS = 900.0
_AUTHOR = "livespec-dispatcher"
_AUTHOR_EMAIL = "livespec-dispatcher@users.noreply.github.com"
_GIT = ("git", "-c", "core.hooksPath=/dev/null", "-c", "gc.auto=0")
_TIP_REF = "refs/reseed/tip"
_SEED_REF = "refs/reseed/seed"


@dataclass(frozen=True, kw_only=True)
class ReseedUnobservable:
    """A reseed command could not be taken, so no conflict or clean apply is claimed."""

    detail: str


@dataclass(frozen=True, kw_only=True)
class SeedCarriesNoWork:
    """The seed's tree is its merge base's tree, so there is nothing to apply."""


@dataclass(frozen=True, kw_only=True)
class _Step:
    """One command: a name its output is kept under, and its argv from earlier outputs."""

    name: str
    argv: Callable[[dict[str, str]], list[str]]
    in_repo: bool = False
    timeout_seconds: float = _TIMEOUT_SECONDS


def reseed(
    *,
    runner: CommandRunner,
    repo: Path,
    work_item_id: str,
    seed: RecoverySeed,
    branch: str,
    tip: str,
) -> RecoverySeed | SeedCarriesNoWork | ReseedConflict | ReseedUnobservable:
    """Move one seed onto `tip`: the reseeded seed, no work, a conflict, or unobservable."""
    with tempfile.TemporaryDirectory(prefix="livespec-reseed-") as root:
        scratch = Path(root) / "scratch"
        scratch.mkdir()
        run = _Run(runner=runner, repo=repo, scratch=scratch, patch=Path(root) / "seed.patch")
        measured = run.steps(steps=_measure_steps(seed=seed, branch=branch, tip=tip))
        if isinstance(measured, ReseedUnobservable):
            return measured
        if measured["seed_tree"] == measured["base_tree"]:
            return SeedCarriesNoWork()
        if measured["base"] == tip:
            return seed
        applied = run.apply(seed=seed, tip=tip, measured=measured)
        if isinstance(applied, ReseedUnobservable | ReseedConflict):
            return applied
        recorded = run.steps(
            steps=_record_steps(work_item_id=work_item_id, seed=seed, branch=branch, tip=tip),
            outputs=applied,
        )
        if isinstance(recorded, ReseedUnobservable):
            return recorded
        commit = recorded["commit"]
        ref = f"{RESEED_REF_PREFIX}/{work_item_id}/{commit}"
        return _confirmed(recorded=recorded, ref=ref, seed=seed, tip=tip)


@dataclass(frozen=True, kw_only=True)
class _Run:
    """The scratch clone one reseed works in, and the only place its commands run."""

    runner: CommandRunner
    repo: Path
    scratch: Path
    patch: Path

    def steps(
        self, *, steps: tuple[_Step, ...], outputs: dict[str, str] | None = None
    ) -> dict[str, str] | ReseedUnobservable:
        """Run each step in order; the first that exits non-zero ends the whole reseed."""
        kept = {} if outputs is None else dict(outputs)
        for step in steps:
            argv = [*_GIT, *step.argv(kept)]
            result = self.runner.run(
                argv=argv,
                cwd=self.repo if step.in_repo else self.scratch,
                timeout_seconds=step.timeout_seconds,
                env=_identity(date=kept.get("tip_date")),
            )
            if result.exit_code != 0:
                return ReseedUnobservable(
                    detail=(
                        f"{' '.join(argv)} exited {result.exit_code}: {result.stderr.strip()[:300]}"
                    )
                )
            kept[step.name] = result.stdout.strip()
        return kept

    def apply(
        self, *, seed: RecoverySeed, tip: str, measured: dict[str, str]
    ) -> dict[str, str] | ReseedUnobservable | ReseedConflict:
        """Three-way apply the seed's diff to the tip's tree; unmerged paths are the conflict."""
        prepared = self.steps(
            steps=(
                _Step(name="checkout", argv=lambda _o: ["checkout", "--quiet", "--detach", tip]),
                _Step(
                    name="tip_date",
                    argv=lambda _o: ["log", "-1", "--format=%cI", tip],
                ),
                _Step(
                    name="diff",
                    argv=lambda _o: [
                        "diff",
                        "--binary",
                        "--full-index",
                        f"--output={self.patch}",
                        measured["base"],
                        seed.commit_sha,
                    ],
                ),
            ),
            outputs=measured,
        )
        if isinstance(prepared, ReseedUnobservable):
            return prepared
        argv = [*_GIT, "apply", "--3way", "--index", str(self.patch)]
        result = self.runner.run(
            argv=argv, cwd=self.scratch, timeout_seconds=_TIMEOUT_SECONDS, env=_identity()
        )
        if result.exit_code == 0:
            return prepared
        unmerged = self.steps(
            steps=(
                _Step(
                    name="unmerged",
                    argv=lambda _o: ["diff", "--name-only", "--diff-filter=U", "-z"],
                ),
            ),
            outputs=prepared,
        )
        paths = (
            () if isinstance(unmerged, ReseedUnobservable) else _paths(text=unmerged["unmerged"])
        )
        if not paths:
            return ReseedUnobservable(
                detail=(
                    f"{' '.join(argv)} exited {result.exit_code} leaving no unmerged path: "
                    f"{result.stderr.strip()[:300]}"
                )
            )
        return ReseedConflict(
            seed_ref=seed.preservation_ref,
            seed_commit=seed.commit_sha,
            default_branch_tip=tip,
            paths=paths,
        )


def _paths(*, text: str) -> tuple[str, ...]:
    """The unique paths of one NUL-separated listing, sorted."""
    return tuple(sorted({one for one in text.split("\0") if one}))


def _identity(*, date: str | None = None) -> dict[str, str | None]:
    """The author and committer a reseed commit is recorded under, dated at the tip."""
    return {
        "GIT_AUTHOR_NAME": _AUTHOR,
        "GIT_AUTHOR_EMAIL": _AUTHOR_EMAIL,
        "GIT_COMMITTER_NAME": _AUTHOR,
        "GIT_COMMITTER_EMAIL": _AUTHOR_EMAIL,
        "GIT_AUTHOR_DATE": date,
        "GIT_COMMITTER_DATE": date,
    }


def _measure_steps(*, seed: RecoverySeed, branch: str, tip: str) -> tuple[_Step, ...]:
    """Fetch the seed and the tip, then read the merge base and the two trees."""
    return (
        _Step(name="url", argv=lambda _o: ["remote", "get-url", SEED_REMOTE], in_repo=True),
        _Step(name="init", argv=lambda _o: ["init", "--quiet"]),
        _Step(
            name="fetch",
            argv=lambda o: [
                "fetch",
                "--quiet",
                o["url"],
                f"+refs/heads/{branch}:{_TIP_REF}",
                f"+{seed.preservation_ref}:{_SEED_REF}",
            ],
            timeout_seconds=_FETCH_TIMEOUT_SECONDS,
        ),
        _Step(name="has_tip", argv=lambda _o: ["cat-file", "-e", f"{tip}^{{commit}}"]),
        _Step(name="has_seed", argv=lambda _o: ["cat-file", "-e", f"{seed.commit_sha}^{{commit}}"]),
        _Step(name="base", argv=lambda _o: ["merge-base", tip, seed.commit_sha]),
        _Step(name="seed_tree", argv=lambda _o: ["rev-parse", f"{seed.commit_sha}^{{tree}}"]),
        _Step(name="base_tree", argv=lambda o: ["rev-parse", f"{o['base']}^{{tree}}"]),
    )


def _record_steps(
    *, work_item_id: str, seed: RecoverySeed, branch: str, tip: str
) -> tuple[_Step, ...]:
    """Write the applied tree as one commit on the tip, publish it, and read it back."""
    subject = f"reseed {work_item_id} from {seed.preservation_ref} onto {branch}"
    trailers = (
        f"Livespec-Reseed-Source: {seed.preservation_ref} {seed.commit_sha}\n"
        f"Livespec-Reseed-Onto: {tip}"
    )
    return (
        _Step(name="tree", argv=lambda _o: ["write-tree"]),
        _Step(
            name="commit",
            argv=lambda o: ["commit-tree", o["tree"], "-p", tip, "-m", subject, "-m", trailers],
        ),
        _Step(
            name="push",
            argv=lambda o: [
                "push",
                "--quiet",
                o["url"],
                f"{o['commit']}:{RESEED_REF_PREFIX}/{work_item_id}/{o['commit']}",
            ],
        ),
        _Step(
            name="published",
            argv=lambda o: [
                "ls-remote",
                o["url"],
                f"{RESEED_REF_PREFIX}/{work_item_id}/{o['commit']}",
            ],
        ),
    )


def _confirmed(
    *, recorded: dict[str, str], ref: str, seed: RecoverySeed, tip: str
) -> RecoverySeed | ReseedUnobservable:
    """The reseeded seed once a remote read shows the reseed ref at the reseed commit."""
    commit = recorded["commit"]
    if observed_ref_commit(stdout=recorded["published"], ref=ref) != commit:
        return ReseedUnobservable(
            detail=f"a remote read did not show {ref} at {commit} after the reseed was pushed"
        )
    return replace(
        seed,
        commit_sha=commit,
        preservation_ref=ref,
        preservation_tip_sha=None,
        source_ref=seed.preservation_ref,
        source_commit=seed.commit_sha,
        default_branch_tip=tip,
    )
