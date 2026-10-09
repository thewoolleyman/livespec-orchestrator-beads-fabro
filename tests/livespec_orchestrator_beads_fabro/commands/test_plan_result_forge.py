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
    OBSERVATION_UNOBSERVABLE,
    OBSERVATION_UNSATISFIED,
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


def test_a_different_state_is_unsatisfied_and_reports_the_state_it_read() -> None:
    runner = _runner(stdout='{"state": "OPEN", "updatedAt": "2026-10-08T09:00:00Z"}')
    observation = observe_pull_request_state(
        repository=_REPOSITORY,
        target=PullRequestStateTarget(number=9, state="MERGED"),
        runner=runner,
        now=_NOW,
    )
    assert observation is not None
    assert observation.status == OBSERVATION_UNSATISFIED
    assert observation.evidence == "forge pull request #9 state OPEN at 2026-10-08T09:00:00Z"
    assert "not the expected MERGED" in observation.detail


def test_a_failed_malformed_or_incomplete_state_read_is_unobservable() -> None:
    """Six ways the forge can answer without answering the question.

    A non-zero exit, output that is not JSON at all, JSON that is not an object,
    and a payload missing either field. Each must be unobservable rather than a
    confident negative, and each names the forge as the failed source. The
    incomplete-payload cases are the ones most easily left out: a reader that
    defaulted the missing timestamp would publish an evidence identity nobody can
    look up, and one that defaulted the missing state would invent a verdict.
    """
    for runner in (
        _runner(exit_code=4),
        _runner(stdout="not json at all"),
        _runner(stdout='["MERGED"]'),
        _runner(stdout='{"updatedAt": "2026-10-08T09:00:00Z"}'),
        _runner(stdout='{"state": "", "updatedAt": "2026-10-08T09:00:00Z"}'),
        _runner(stdout='{"state": "MERGED"}'),
    ):
        observation = observe_pull_request_state(
            repository=_REPOSITORY,
            target=PullRequestStateTarget(number=9, state="MERGED"),
            runner=runner,
            now=_NOW,
        )
        assert observation.status == OBSERVATION_UNOBSERVABLE
        assert observation.source == SOURCE_FORGE
        assert observation.evidence == ""


def test_a_state_outside_the_forge_vocabulary_is_unobservable() -> None:
    """A malformed state value is MALFORMED EVIDENCE, never a confident negative.

    The clause requires malformed evidence to be `unobservable`. A payload whose
    state is not one the forge can report says nothing about where the pull
    request stands, so comparing it against the requested state manufactures a
    negative out of a value the reader could not interpret — and `unsatisfied`
    there leaves the obligation looking measured and unmet rather than unread,
    which are the two readings the clause most needs kept apart.
    """
    for state in ("INVALID", "42", "OPENED"):
        observation = observe_pull_request_state(
            repository=_REPOSITORY,
            target=PullRequestStateTarget(number=9, state="OPEN"),
            runner=_runner(stdout=f'{{"state": "{state}", "updatedAt": "2026-10-08T09:00:00Z"}}'),
            now=_NOW,
        )
        assert observation.status == OBSERVATION_UNOBSERVABLE
        assert observation.source == SOURCE_FORGE
        assert observation.evidence == ""


def test_every_state_the_forge_can_report_still_reaches_a_verdict() -> None:
    """The positive control on the vocabulary: narrowing it must not blind the read.

    A malformed-state refusal is only correct while the states the forge ACTUALLY
    reports still reach a verdict. Without this control the refusal above is
    equally consistent with a vocabulary so narrow that every real read is
    unobservable — the instrument-aimed-at-nothing failure, which reports clean.
    """
    for state, expected in (
        ("OPEN", OBSERVATION_SATISFIED),
        ("CLOSED", OBSERVATION_UNSATISFIED),
        ("MERGED", OBSERVATION_UNSATISFIED),
    ):
        observation = observe_pull_request_state(
            repository=_REPOSITORY,
            target=PullRequestStateTarget(number=9, state="OPEN"),
            runner=_runner(stdout=f'{{"state": "{state}", "updatedAt": "2026-10-08T09:00:00Z"}}'),
            now=_NOW,
        )
        assert observation.status == expected


def test_a_blank_state_observation_timestamp_is_unobservable() -> None:
    """The timestamp is HALF the evidence identity, so a blank one is not evidence.

    The clause requires every observation to carry a source evidence identity, and
    for this kind that identity is the forge state together with its timestamp. A
    payload whose `updatedAt` is empty was accepted as satisfaction, publishing an
    evidence line that trails off after `at ` and names no forge observation
    anyone can look up.
    """
    for updated in ("", "   "):
        observation = observe_pull_request_state(
            repository=_REPOSITORY,
            target=PullRequestStateTarget(number=9, state="OPEN"),
            runner=_runner(stdout=f'{{"state": "OPEN", "updatedAt": "{updated}"}}'),
            now=_NOW,
        )
        assert observation.status == OBSERVATION_UNOBSERVABLE
        assert observation.source == SOURCE_FORGE
        assert observation.evidence == ""


def test_a_failed_state_read_names_the_first_line_of_its_diagnostic() -> None:
    """One line of stderr, and a STATED absence when there is none.

    A diagnostic that pasted a multi-line stderr into an observation would make
    the observation unreadable wherever one is rendered; a blank tail would read
    as a truncated sentence rather than as a command that said nothing.
    """
    noisy = _Runner(
        result=CommandResult(
            exit_code=4, stdout="", stderr="gh: authentication required\nrun gh auth login\n"
        )
    )
    observation = observe_pull_request_state(
        repository=_REPOSITORY,
        target=PullRequestStateTarget(number=9, state="MERGED"),
        runner=noisy,
        now=_NOW,
    )
    assert "gh: authentication required" in observation.detail
    assert "run gh auth login" not in observation.detail
    silent = observe_pull_request_state(
        repository=_REPOSITORY,
        target=PullRequestStateTarget(number=9, state="MERGED"),
        runner=_runner(exit_code=1),
        now=_NOW,
    )
    assert "no diagnostic on stderr" in silent.detail


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


def test_a_different_remote_blob_is_unsatisfied() -> None:
    """The remote answered, and the object it named is not the requested one."""
    observation = observe_file_on_branch(
        repository=_REPOSITORY,
        target=FileOnBranchTarget(branch="master", path="a/b.md", blob=_BLOB),
        runner=_runner(stdout="1111111111111111111111111111111111111111\n"),
        now=_NOW,
    )
    assert observation is not None
    assert observation.status == OBSERVATION_UNSATISFIED
    assert (
        observation.evidence == "git blob 1111111111111111111111111111111111111111 at master:a/b.md"
    )
    assert f"not the expected {_BLOB}" in observation.detail


def test_an_absent_or_unreadable_blob_is_unobservable_and_not_a_mismatch() -> None:
    """A blank answer is NOT a mismatch, and neither is a failed read.

    The forge returns an empty body for a path it cannot resolve at that ref, so
    treating blank as a differing object would publish a confident negative about
    a path the read never reached — which the clause forbids outright. The source
    named is the Git object rather than the forge, because that is the evidence
    the reading rests on and the thing a retry has to reach.
    """
    for runner in (_runner(stdout="\n"), _runner(exit_code=1)):
        observation = observe_file_on_branch(
            repository=_REPOSITORY,
            target=FileOnBranchTarget(branch="master", path="a/b.md", blob=_BLOB),
            runner=runner,
            now=_NOW,
        )
        assert observation.status == OBSERVATION_UNOBSERVABLE
        assert observation.source == SOURCE_GIT_OBJECT
        assert observation.evidence == ""


def test_an_answer_that_is_not_an_object_identity_is_unobservable() -> None:
    """`null` is the shape this failed in, and it read as a DIFFERING object.

    `gh api --jq .sha` prints the literal `null` when the payload carries no
    `sha`. That is four characters rather than none, so it cleared the blank arm
    above and fell through to the mismatch arm, publishing a confident negative
    about an object identity the read never obtained — the clause's forbidden
    direction, reached by a value that merely was not empty.

    The uppercase case is here because it is what makes the VERBATIM comparison
    sound. The forge renders a blob id as forty lowercase hex digits and nothing
    else, so any other rendering is a value this reader cannot assume it
    understands; admitting one while comparing verbatim would report a matching
    object as a mismatch.
    """
    for stdout in ("null\n", "not-a-sha\n", f"{_BLOB[:39]}\n", f"{_BLOB}0\n", f"{_BLOB.upper()}\n"):
        observation = observe_file_on_branch(
            repository=_REPOSITORY,
            target=FileOnBranchTarget(branch="master", path="a/b.md", blob=_BLOB),
            runner=_runner(stdout=stdout),
            now=_NOW,
        )
        assert observation.status == OBSERVATION_UNOBSERVABLE
        assert observation.source == SOURCE_GIT_OBJECT
        assert observation.evidence == ""
