"""A verified preservation ref of a run, found by a remote ref listing of origin.

`SPECIFICATION/contracts.md` section "Dispatcher progress watchdog" -> "The
whole-run wall budget": when the export cannot be read back, "the Dispatcher
MUST also list the refs on origin with a remote ref listing (`git ls-remote`,
never a local clone) and look for a *verified preservation ref* of the run: a
ref that names this run, namely `refs/heads/needs-human/<run-id>`,
`refs/heads/preserve/run-<run-id>`, a
`refs/livespec/preserved-publish/<work-item-id>/<commit-sha>` ref the Dispatcher
published for this run, or the run's latest preserved capture
`refs/livespec/wip/<work-item-id>/<run-id>/<n>`, whose commit's tree equals the
tree of the run branch's committed tip as the run's own record reports it. When
the run's record cannot report that tip, the run's latest preserved capture or
its needs-human ref qualifies on its own, because the run created each from the
run branch's tip." And: "A remote ref listing that cannot be taken is a failed
measurement of that poll, never evidence that no ref exists."

THREE ANSWERS, NOT TWO, and the third is the one that keeps the wall honest. A
verified ref releases the held cancel; an answered listing that holds none is
the one reading that means "no copy exists" and keeps the run; a listing or a
tree read that could not be taken is NEITHER, so it travels back as a named
failed measurement. Collapsing it onto the absence would let a flaky `ls-remote`
journal "no verified preservation ref" for a tree that is in fact on origin, and
collapsing it onto a verified ref would cancel a run whose work was never
confirmed -- the discarded-work path preserve-before-cancel exists to close.

THE LISTING HANDS BACK COMMIT IDS ONLY, so a tree comparison needs each commit's
tree, and a commit this clone has never fetched is fetched by id from origin
before its tree is read. Equal commit ids short-circuit the comparison: equal
commits have equal trees, so a ref at the run branch tip's own commit verifies
without a single tree read.

THE ORDER OF CANDIDATES IS FIXED -- the needs-human ref, the preserve ref, the
latest capture, then the preserved-publish refs by name -- rather than the order
the listing happened to print them in, so two polls over one origin name the same
ref. Only the needs-human ref and the latest capture qualify when the record
reports no tip: the clause names exactly those two, because the run cut each
from the run branch's tip, whereas a preserve ref or a preserved-publish ref says
nothing about THIS tip.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_refs import refs_by_name
from livespec_orchestrator_beads_fabro.commands._dispatcher_wip_capture_receipt import (
    latest_wip_capture,
)

__all__: list[str] = [
    "PreservationRefsUnobservable",
    "VerifiedPreservationRef",
    "verified_preservation_ref",
]

_REMOTE = "origin"
_GIT_TIMEOUT_SECONDS = 120.0
_WIP_REF_PREFIX = "refs/livespec/wip"
_PRESERVED_PUBLISH_REF_PREFIX = "refs/livespec/preserved-publish"


@dataclass(frozen=True, kw_only=True)
class VerifiedPreservationRef:
    """One ref on origin that holds the run's committed tree, and its commit id."""

    ref: str
    commit: str


@dataclass(frozen=True, kw_only=True)
class PreservationRefsUnobservable:
    """A listing or a tree read could not be taken, so absence is not confirmed."""

    detail: str


@dataclass(frozen=True, kw_only=True)
class _Candidate:
    """A ref of the run, and whether it qualifies when the tip cannot be compared."""

    found: VerifiedPreservationRef
    qualifies_alone: bool


def verified_preservation_ref(
    *,
    runner: CommandRunner,
    repo: Path,
    work_item_id: str,
    run_id: str,
    tip_commit: str | None,
) -> VerifiedPreservationRef | PreservationRefsUnobservable | None:
    """The ref on origin that holds this run's committed tree, if one is verified.

    None is an ANSWERED listing that holds no verified ref; an unobservable
    result is a measurement that could not be taken, which the caller carries
    onto the held record as a failed measurement rather than reading as None.
    """
    needs_human = f"refs/heads/needs-human/{run_id}"
    preserve = f"refs/heads/preserve/run-{run_id}"
    publish = f"{_PRESERVED_PUBLISH_REF_PREFIX}/{work_item_id}/"
    patterns = [
        needs_human,
        preserve,
        f"{publish}*",
        f"{_WIP_REF_PREFIX}/{work_item_id}/{run_id}/*",
    ]
    listing = runner.run(
        argv=["git", "ls-remote", _REMOTE, *patterns],
        cwd=repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if listing.exit_code != 0:
        return PreservationRefsUnobservable(
            detail=(
                f"git ls-remote {_REMOTE} exited {listing.exit_code}; whether origin holds a"
                " verified preservation ref of the run could not be established"
            )
        )
    refs = refs_by_name(stdout=listing.stdout)
    capture = latest_wip_capture(work_item_id=work_item_id, run_id=run_id, refs=refs)
    candidates = [
        *[
            _candidate(ref=ref, commit=refs[ref], alone=ref == needs_human)
            for ref in (needs_human, preserve)
            if ref in refs
        ],
        *(
            []
            if capture is None
            else [_candidate(ref=capture.ref, commit=capture.commit, alone=True)]
        ),
        *[
            _candidate(ref=ref, commit=refs[ref], alone=False)
            for ref in sorted(refs)
            if ref.startswith(publish)
        ],
    ]
    if tip_commit is None:
        return next((one.found for one in candidates if one.qualifies_alone), None)
    return _holding_the_tip_tree(
        runner=runner, repo=repo, candidates=candidates, tip_commit=tip_commit
    )


def _candidate(*, ref: str, commit: str, alone: bool) -> _Candidate:
    return _Candidate(found=VerifiedPreservationRef(ref=ref, commit=commit), qualifies_alone=alone)


def _holding_the_tip_tree(
    *,
    runner: CommandRunner,
    repo: Path,
    candidates: list[_Candidate],
    tip_commit: str,
) -> VerifiedPreservationRef | PreservationRefsUnobservable | None:
    """The first candidate whose tree equals the tip's, or why none could be shown."""
    for one in candidates:
        if one.found.commit == tip_commit:
            return one.found
    tip_tree = _tree(runner=runner, repo=repo, commit=tip_commit)
    if tip_tree is None:
        return PreservationRefsUnobservable(
            detail=(
                f"the tree of the run branch's committed tip {tip_commit} could not be read, so"
                " no ref of the run could be compared with it"
            )
        )
    unreadable: list[str] = []
    for one in candidates:
        tree = _tree(runner=runner, repo=repo, commit=one.found.commit)
        if tree is None:
            unreadable.append(one.found.ref)
        elif tree == tip_tree:
            return one.found
    if unreadable:
        return PreservationRefsUnobservable(
            detail=(
                f"the tree of {', '.join(unreadable)} could not be read, so whether origin holds"
                " a verified preservation ref of the run could not be established"
            )
        )
    return None


def _tree(*, runner: CommandRunner, repo: Path, commit: str) -> str | None:
    """One commit's tree id, fetching the commit by id when this clone lacks it."""
    read = ["git", "rev-parse", "--verify", "--quiet", f"{commit}^{{tree}}"]
    first = runner.run(argv=read, cwd=repo, timeout_seconds=_GIT_TIMEOUT_SECONDS)
    if first.exit_code == 0:
        return first.stdout.strip()
    fetched = runner.run(
        argv=["git", "fetch", "--quiet", _REMOTE, commit],
        cwd=repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if fetched.exit_code != 0:
        return None
    second = runner.run(argv=read, cwd=repo, timeout_seconds=_GIT_TIMEOUT_SECONDS)
    return second.stdout.strip() if second.exit_code == 0 else None
