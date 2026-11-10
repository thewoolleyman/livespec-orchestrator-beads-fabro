"""A needs-human ref that carries no work is listed as passed over, never taken as a seed.

`SPECIFICATION/contracts.md`, in the clause on how a needs-human tree is
recognised by the run it carries, says a needs-human ref CARRIES NO WORK when its
tip commit's tree is identical to the tree of the tip's merge base with the
default branch, that routing MUST NOT take such a ref as a seed and MUST NOT let
it outrank any other ref, published head or capture, and that each one is listed
in the route record's `passed_over_needs_human` with the reason `no-change`. A
comparison that cannot be taken is the unobservable-measurement hold, and is read
neither as a change nor as the absence of one.

WHY EVERY CASE STANDS A REF WITH WORK BESIDE, OR UNDER, THE EMPTY ONE. The empty
ref is the NEWEST tip in each case, so the committer-time ranking would take it:
a build that ignored the rule picks a well-formed, wrong seed whose tree is the
default branch's own. The control case stands a ref with work alone and asserts it
is still taken, so the rule cannot pass by refusing every needs-human ref.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_preserved import (
    NEEDS_HUMAN_REF_PREFIX,
    SEED_REMOTE,
    PreservedWorkAbsent,
    PreservedWorkUnobservable,
    verified_preserved_seed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_records import (
    recovery_route_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    RecoveryLoss,
    RecoverySeed,
)

_ITEM_ID = "bd-ib-qshcwc"
_WORKED_RUN = "01M6VR76ZQN2AAAAAAAAAAAAAA"
_EMPTY_RUN = "01M72QJ9P6GA24F9Y7S4E8WFJT"

_WORKED_REF = f"{NEEDS_HUMAN_REF_PREFIX}/{_WORKED_RUN}"
_EMPTY_REF = f"{NEEDS_HUMAN_REF_PREFIX}/{_EMPTY_RUN}"
_WORKED_COMMIT = "a1" * 20
_EMPTY_COMMIT = "b2" * 20
_BASE_COMMIT = "c3" * 20
_BASE_TREE = "d4" * 20
_WORKED_TREE = "e5" * 20

_WIP_PREFIX = f"refs/livespec/wip/{_ITEM_ID}/{_EMPTY_RUN}"
_WIP_COMMIT = "f6" * 20


@dataclass(kw_only=True)
class _Runner:
    """A scripted origin and object store; an unscripted argv answers a blank success."""

    refs: dict[str, str]
    trees: dict[str, str]
    wip: dict[str, str] = field(default_factory=dict[str, str])
    unreadable_trees: bool = False
    calls: list[list[str]] = field(default_factory=list[list[str]])

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        self.calls.append(argv)
        exit_code, stdout = self._answer(argv=argv)
        return CommandResult(exit_code=exit_code, stdout=stdout, stderr="")

    def _answer(self, *, argv: list[str]) -> tuple[int, str]:
        answers = {
            "ls-remote": self._listing,
            "symbolic-ref": lambda _: (0, "origin/master\n"),
            "merge-base": lambda a: (1, "")
            if a[2] == "--is-ancestor"
            else (0, f"{_BASE_COMMIT}\n"),
            "rev-parse": self._trees_of,
            "show": lambda a: (0, "\n".join(f"{c} {_TIMES[c]}" for c in a[4:])),
        }
        return answers.get(argv[1], lambda _: (0, ""))(argv)

    def _listing(self, argv: list[str]) -> tuple[int, str]:
        listed = {
            f"{NEEDS_HUMAN_REF_PREFIX}/*": self.refs,
            f"refs/livespec/wip/{_ITEM_ID}/{_EMPTY_RUN}/*": self.wip,
        }
        return 0, "\n".join(f"{c}\t{r}" for r, c in listed.get(argv[3], {}).items())

    def _trees_of(self, argv: list[str]) -> tuple[int, str]:
        if self.unreadable_trees:
            return 128, ""
        return 0, "\n".join(self.trees[one.removesuffix("^{tree}")] for one in argv[2:]) + "\n"


_TIMES = {_WORKED_COMMIT: 100, _EMPTY_COMMIT: 200}


def _trees() -> dict[str, str]:
    return {
        _WORKED_COMMIT: _WORKED_TREE,
        _EMPTY_COMMIT: _BASE_TREE,
        _BASE_COMMIT: _BASE_TREE,
    }


def _seed(*, runner: _Runner, run_ids: tuple[str, ...] = (_EMPTY_RUN, _WORKED_RUN)):
    return verified_preserved_seed(
        runner=runner,
        repo=Path("/repo"),
        work_item_id=_ITEM_ID,
        earlier_run_ids=run_ids,
        journal_records=(),
    )


def test_a_ref_with_work_alone_is_still_taken() -> None:
    runner = _Runner(refs={_WORKED_REF: _WORKED_COMMIT}, trees=_trees())

    found = _seed(runner=runner)

    assert isinstance(found, RecoverySeed)
    assert found.preservation_ref == _WORKED_REF
    assert found.commit_sha == _WORKED_COMMIT


def test_the_newest_ref_carrying_no_work_is_not_the_seed_and_is_listed_as_no_change() -> None:
    runner = _Runner(refs={_WORKED_REF: _WORKED_COMMIT, _EMPTY_REF: _EMPTY_COMMIT}, trees=_trees())

    found = _seed(runner=runner)

    assert isinstance(found, RecoverySeed)
    assert found.preservation_ref == _WORKED_REF
    assert found.commit_sha == _WORKED_COMMIT
    assert found.passed_over_needs_human == ()
    assert found.no_change_needs_human == ((_EMPTY_REF, _EMPTY_COMMIT),)
    assert ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"] in runner.calls


def test_a_ref_carrying_no_work_does_not_outrank_a_capture() -> None:
    runner = _Runner(
        refs={_EMPTY_REF: _EMPTY_COMMIT},
        trees=_trees(),
        wip={f"{_WIP_PREFIX}/1": _WIP_COMMIT},
    )

    found = _seed(runner=runner)

    assert isinstance(found, RecoverySeed)
    assert found.preservation_ref == f"{_WIP_PREFIX}/1"
    assert found.commit_sha == _WIP_COMMIT
    assert found.no_change_needs_human == ((_EMPTY_REF, _EMPTY_COMMIT),)


def test_only_refs_carrying_no_work_and_nothing_else_preserved_is_confirmed_absence() -> None:
    runner = _Runner(refs={_EMPTY_REF: _EMPTY_COMMIT}, trees=_trees())

    found = _seed(runner=runner)

    assert isinstance(found, PreservedWorkAbsent)
    assert found.no_change_needs_human == ((_EMPTY_REF, _EMPTY_COMMIT),)


def test_a_tree_comparison_that_cannot_be_taken_is_unobservable() -> None:
    runner = _Runner(
        refs={_WORKED_REF: _WORKED_COMMIT, _EMPTY_REF: _EMPTY_COMMIT},
        trees=_trees(),
        unreadable_trees=True,
    )

    found = _seed(runner=runner)

    assert isinstance(found, PreservedWorkUnobservable)
    assert "could not be established" in found.detail


def test_the_route_record_names_each_ref_with_its_commit_and_reason() -> None:
    seed = RecoverySeed(
        source_run_id=_WORKED_RUN,
        remote=SEED_REMOTE,
        commit_sha=_WORKED_COMMIT,
        preservation_ref=_WORKED_REF,
        passed_over_needs_human=(("refs/heads/needs-human/older", "9" * 40),),
        no_change_needs_human=((_EMPTY_REF, _EMPTY_COMMIT),),
    )
    loss = RecoveryLoss(
        source_run_id=_EMPTY_RUN,
        sources_asked=("needs-human-terminal-tree",),
        no_change_needs_human=((_EMPTY_REF, _EMPTY_COMMIT),),
    )

    seeded = recovery_route_record(work_item_id=_ITEM_ID, route="seeded", seed=seed)
    fresh = recovery_route_record(work_item_id=_ITEM_ID, route="fresh", loss=loss)

    assert seeded["passed_over_needs_human"] == [
        {"ref": "refs/heads/needs-human/older", "commit": "9" * 40, "reason": "not-taken"},
        {"ref": _EMPTY_REF, "commit": _EMPTY_COMMIT, "reason": "no-change"},
    ]
    assert fresh["passed_over_needs_human"] == [
        {"ref": _EMPTY_REF, "commit": _EMPTY_COMMIT, "reason": "no-change"}
    ]
