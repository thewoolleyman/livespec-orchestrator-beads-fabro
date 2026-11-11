"""The run a pull request names does not keep a needs-human ref newer work outranks.

Routing partitions an item's refs by the run they carry and tries the latest run's
tier first. The latest run is the newest journaled run, else the run the pull
request record names. When that run holds a needs-human ref, the pre-fix selection
compared only the refs inside that tier, so an OLDER ref of the pull request's run
beat a NEWER needs-human ref of another earlier run of the item. The recovery
clause of `contracts.md` ranks needs-human refs the item's runs carry by committer
time, whichever identifier names them.

The fix is bounded by what the tiers already settle. A latest run that holds NO
needs-human ref still lets its work-in-progress capture outrank an earlier run's
ref (the precedence table in `test_dispatcher_recovery_seed_precedence` holds that
row), so the last test here pins that the widening applies only once the latest
run's own needs-human ref stands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_preserved import (
    NEEDS_HUMAN_REF_PREFIX,
    SEED_REMOTE,
    verified_preserved_seed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoverySeed

from tests.livespec_orchestrator_beads_fabro.commands._recovery_tip_reads import tip_read_answer

_ITEM_ID = "bd-ib-qshcwc"
_PR_RUN = "01M6PRRUNPRRUNPRRUNPRRUN00"
_OTHER_RUN = "01M6OTHERRUNOTHERRUNOTHER0"
_PR_COMMIT = "a1" * 20
_OTHER_COMMIT = "b2" * 20
_PR_REF = f"{NEEDS_HUMAN_REF_PREFIX}/{_PR_RUN}"
_OTHER_REF = f"{NEEDS_HUMAN_REF_PREFIX}/{_OTHER_RUN}"
_WIP_REF = f"refs/livespec/wip/{_ITEM_ID}/{_PR_RUN}/1"
_WIP_COMMIT = "c3" * 20
_OLD = 1_000
_NEW = 2_000


@dataclass(kw_only=True)
class _Runner:
    """A scripted origin: the listed refs, each tip's committer time, no tip descending."""

    refs: dict[str, str]
    times: dict[str, int]
    calls: list[str] = field(default_factory=list)

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
        self.calls.append(" ".join(argv))
        if argv[:3] == ["git", "ls-remote", SEED_REMOTE]:
            lines = [
                f"{commit}\t{ref}"
                for ref, commit in sorted(self.refs.items())
                if any(self._matches(ref=ref, pattern=pattern) for pattern in argv[3:])
            ]
            return CommandResult(exit_code=0, stdout="\n".join(lines), stderr="")
        if argv[:4] == ["git", "show", "-s", "--format=%H %ct"]:
            stdout = "".join(f"{commit} {self.times[commit]}\n" for commit in argv[4:])
            return CommandResult(exit_code=0, stdout=stdout, stderr="")
        if argv[:3] == ["git", "merge-base", "--is-ancestor"]:
            return CommandResult(exit_code=1, stdout="", stderr="")
        return tip_read_answer(argv=argv) or CommandResult(exit_code=0, stdout="", stderr="")

    @staticmethod
    def _matches(*, ref: str, pattern: str) -> bool:
        return (
            ref.startswith(pattern.removesuffix("*")) if pattern.endswith("*") else ref == pattern
        )


def _seed(*, runner: _Runner, journaled_run: str | None = None) -> object:
    journal: tuple[dict[str, object], ...] = (
        ()
        if journaled_run is None
        else ({"stage": "dispatch", "work_item_id": _ITEM_ID, "run_id": journaled_run},)
    )
    return verified_preserved_seed(
        runner=runner,
        repo=Path("/repo"),
        work_item_id=_ITEM_ID,
        earlier_run_ids=(_PR_RUN, _OTHER_RUN),
        journal_records=journal,
    )


def test_a_newer_ref_of_another_run_outranks_the_pull_request_runs_older_ref() -> None:
    runner = _Runner(
        refs={_PR_REF: _PR_COMMIT, _OTHER_REF: _OTHER_COMMIT},
        times={_PR_COMMIT: _OLD, _OTHER_COMMIT: _NEW},
    )

    assert _seed(runner=runner, journaled_run=_PR_RUN) == RecoverySeed(
        source_run_id=_OTHER_RUN,
        remote=SEED_REMOTE,
        commit_sha=_OTHER_COMMIT,
        preservation_ref=_OTHER_REF,
        passed_over_needs_human=((_PR_REF, _PR_COMMIT),),
    )


def test_the_same_holds_when_the_pull_request_run_is_only_the_leading_identifier() -> None:
    runner = _Runner(
        refs={_PR_REF: _PR_COMMIT, _OTHER_REF: _OTHER_COMMIT},
        times={_PR_COMMIT: _OLD, _OTHER_COMMIT: _NEW},
    )

    seed = _seed(runner=runner)

    assert isinstance(seed, RecoverySeed)
    assert seed.preservation_ref == _OTHER_REF


def test_the_pull_request_runs_ref_is_kept_when_it_is_the_newest() -> None:
    runner = _Runner(
        refs={_PR_REF: _PR_COMMIT, _OTHER_REF: _OTHER_COMMIT},
        times={_PR_COMMIT: _NEW, _OTHER_COMMIT: _OLD},
    )

    seed = _seed(runner=runner, journaled_run=_PR_RUN)

    assert isinstance(seed, RecoverySeed)
    assert seed.preservation_ref == _PR_REF
    assert seed.passed_over_needs_human == ((_OTHER_REF, _OTHER_COMMIT),)


def test_a_latest_run_holding_only_a_capture_still_outranks_an_earlier_runs_ref() -> None:
    runner = _Runner(
        refs={_OTHER_REF: _OTHER_COMMIT, f"{_WIP_REF}": _WIP_COMMIT},
        times={_OTHER_COMMIT: _NEW, _WIP_COMMIT: _OLD},
    )

    seed = _seed(runner=runner, journaled_run=_PR_RUN)

    assert isinstance(seed, RecoverySeed)
    assert seed.preservation_ref == _WIP_REF
    assert seed.passed_over_needs_human == ((_OTHER_REF, _OTHER_COMMIT),)
