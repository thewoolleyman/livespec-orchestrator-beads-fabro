"""Tests for the two forge adapters: pull-request state and the remote blob.

The argv each adapter issues is asserted on its own, because it is the only thing
that decides WHICH repository and WHICH ref the answer is about — and a stub that
answers whatever it is asked cannot tell a correct query from a plausible one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._plan_result_forge import (
    blob_argv,
    observe_file_on_branch,
    observe_pull_request_state,
    pull_request_state_argv,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_SATISFIED,
    SOURCE_FORGE,
    SOURCE_GIT_OBJECT,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_repository import ResultRepository
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import (
    FileOnBranchTarget,
    PullRequestStateTarget,
)

_REPOSITORY = ResultRepository(name="repo", clone=Path("/clone"))
_NOW = "2026-10-08T12:00:00Z"
_BLOB = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


@dataclass(kw_only=True)
class _Runner:
    result: CommandResult
    calls: list[tuple[tuple[str, ...], Path]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del timeout_seconds, env, stdin
        self.calls.append((tuple(argv), cwd))
        return self.result


def _runner(*, exit_code: int = 0, stdout: str = "") -> _Runner:
    return _Runner(result=CommandResult(exit_code=exit_code, stdout=stdout, stderr=""))


def test_the_state_argv_asks_for_the_state_and_its_last_update() -> None:
    """The timestamp is requested WITH the state, in one read.

    The clause asks for a forge state and timestamp as one evidence identity, and
    a second read for the timestamp could observe a different state than the one
    the verdict rests on.
    """
    assert pull_request_state_argv(number=9) == [
        "gh",
        "pr",
        "view",
        "9",
        "--json",
        "state,updatedAt",
    ]


def test_the_blob_argv_names_the_path_at_the_requested_ref() -> None:
    """The ref is in the query, which is what makes the answer about that branch."""
    assert blob_argv(branch="master", path="a/b.md") == [
        "gh",
        "api",
        "repos/{owner}/{repo}/contents/a/b.md?ref=master",
        "--jq",
        ".sha",
    ]


def test_a_matching_state_is_satisfied_and_runs_from_the_named_clone() -> None:
    runner = _runner(stdout='{"state": "MERGED", "updatedAt": "2026-10-08T09:00:00Z"}')
    observation = observe_pull_request_state(
        repository=_REPOSITORY,
        target=PullRequestStateTarget(number=9, state="merged"),
        runner=runner,
        now=_NOW,
    )
    assert observation is not None
    assert observation.status == OBSERVATION_SATISFIED
    assert observation.source == SOURCE_FORGE
    assert observation.evidence == "forge pull request #9 state MERGED at 2026-10-08T09:00:00Z"
    assert runner.calls[0][1] == Path("/clone")


def test_a_different_state_is_not_satisfied() -> None:
    runner = _runner(stdout='{"state": "OPEN", "updatedAt": "2026-10-08T09:00:00Z"}')
    assert (
        observe_pull_request_state(
            repository=_REPOSITORY,
            target=PullRequestStateTarget(number=9, state="MERGED"),
            runner=runner,
            now=_NOW,
        )
        is None
    )


def test_a_failed_malformed_or_incomplete_state_read_is_not_satisfied() -> None:
    """Three ways the forge can answer without answering the question.

    A non-zero exit, output that is not JSON at all, and a payload missing either
    field. The last is the one most easily left out: a reader that defaulted the
    missing timestamp would publish an evidence identity nobody can look up.
    """
    for runner in (
        _runner(exit_code=4),
        _runner(stdout="not json at all"),
        _runner(stdout='["MERGED"]'),
        _runner(stdout='{"updatedAt": "2026-10-08T09:00:00Z"}'),
        _runner(stdout='{"state": "", "updatedAt": "2026-10-08T09:00:00Z"}'),
        _runner(stdout='{"state": "MERGED"}'),
    ):
        assert (
            observe_pull_request_state(
                repository=_REPOSITORY,
                target=PullRequestStateTarget(number=9, state="MERGED"),
                runner=runner,
                now=_NOW,
            )
            is None
        )


def test_a_matching_remote_blob_is_satisfied_and_cites_the_git_object() -> None:
    observation = observe_file_on_branch(
        repository=_REPOSITORY,
        target=FileOnBranchTarget(branch="master", path="a/b.md", blob=_BLOB),
        runner=_runner(stdout=f"{_BLOB}\n"),
        now=_NOW,
    )
    assert observation is not None
    assert observation.status == OBSERVATION_SATISFIED
    assert observation.source == SOURCE_GIT_OBJECT
    assert observation.evidence == f"git blob {_BLOB} at master:a/b.md"
    assert "no local checkout was consulted" in observation.detail


def test_a_different_absent_or_unreadable_blob_is_not_satisfied() -> None:
    """A blank answer is NOT a mismatch, and neither is a failed read.

    The forge returns an empty body for a path it cannot resolve, so treating
    blank as a mismatch would report a confident negative about a path the read
    never reached.
    """
    for runner in (
        _runner(stdout="1111111111111111111111111111111111111111\n"),
        _runner(stdout="\n"),
        _runner(exit_code=1),
    ):
        assert (
            observe_file_on_branch(
                repository=_REPOSITORY,
                target=FileOnBranchTarget(branch="master", path="a/b.md", blob=_BLOB),
                runner=runner,
                now=_NOW,
            )
            is None
        )
