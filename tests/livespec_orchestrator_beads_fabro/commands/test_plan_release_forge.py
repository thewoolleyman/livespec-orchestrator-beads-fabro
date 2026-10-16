"""The three authenticated forge reads the plan release rule makes.

Covers `_plan_release_forge`. Each read is driven through a stub runner, and each
one's ARGV is asserted on its own — the argv is the only thing that decides WHICH
repository the answer is about, and a stub that answers whatever it is asked
cannot tell a correct query from a plausible one.

WHY EVERY FAILURE ARM IS A `ForgeReadFailure` AND NEVER AN EMPTY ANSWER. The v148
plan-record clause reversed exactly that default: the retired read returned an
empty tag set on any failure, so an unreadable repository reported as one carrying
no release tag, which admits every record that states `release: none`. These cases
therefore assert the TYPE of each failing answer, not merely that it is not the
expected value.

WHY THE EXISTENCE PROBE IS GRADED ON THE FORGE'S OWN STATUS AND NOT ON THE EXIT
CODE. `gh api` exits 1 for a 404 — measured against the live forge — so an exit
code cannot tell "the forge reports this repository does not exist", which the
clause routes to the governed repository, from "the read failed", which the clause
rejects. The 404 case here therefore carries a NON-ZERO exit beside the forge's own
status line, which is what a build keying on the exit code fails against.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._plan_release_forge import (
    ForgeReadFailure,
    governed_repository_argv,
    governed_repository_identity,
    repository_exists,
    repository_probe_argv,
    repository_release_tags,
    repository_tags_argv,
)
from livespec_orchestrator_beads_fabro.commands._plan_release_repository import (
    ExplicitRepository,
)

_ROOT = Path("/governed")
_REPOSITORY = "thewoolleyman/livespec-dev-tooling"


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


def _runner(*, exit_code: int = 0, stdout: str = "", stderr: str = "") -> _Runner:
    return _Runner(result=CommandResult(exit_code=exit_code, stdout=stdout, stderr=stderr))


def test_the_tags_argv_asks_the_forge_remote_for_every_tag_the_repository_carries() -> None:
    # The repository is NAMED in the endpoint rather than left to `gh`'s
    # `{owner}`/`{repo}` placeholders: those resolve against the repository the
    # command runs in, which is the GOVERNED one, so a placeholder form would
    # answer about the governed repository for every record.
    assert repository_tags_argv(repository=_REPOSITORY) == [
        "gh",
        "api",
        "--method",
        "GET",
        f"repos/{_REPOSITORY}/tags",
        "--paginate",
        "-F",
        "per_page=100",
        "--jq",
        ".[].name",
    ]


def test_the_probe_argv_asks_only_for_the_repository_resource_status() -> None:
    assert repository_probe_argv(repository=_REPOSITORY) == [
        "gh",
        "api",
        "--include",
        "--method",
        "HEAD",
        f"repos/{_REPOSITORY}",
    ]


def test_the_governed_identity_argv_asks_the_checkouts_own_remote() -> None:
    assert governed_repository_argv() == [
        "gh",
        "repo",
        "view",
        "--json",
        "nameWithOwner",
        "--jq",
        ".nameWithOwner",
    ]


def test_a_successful_tags_read_reports_every_tag_the_forge_named() -> None:
    runner = _runner(stdout="v1.95.12\nv1.96.1\n\n  v1.96.2  \n")

    tags = repository_release_tags(repository=_REPOSITORY, project_root=_ROOT, runner=runner)

    assert tags == frozenset({"v1.95.12", "v1.96.1", "v1.96.2"})
    # The read runs FROM the governed checkout, which is where `gh` resolves the
    # forge host and the credential it authenticates with.
    assert runner.calls == [(tuple(repository_tags_argv(repository=_REPOSITORY)), _ROOT)]


def test_a_repository_the_forge_reports_no_tags_for_reports_an_empty_set() -> None:
    # An EMPTY set is a successful reading and means no release applies. It is the
    # one answer that must stay distinguishable from a failed read.
    tags = repository_release_tags(repository=_REPOSITORY, project_root=_ROOT, runner=_runner())

    assert tags == frozenset()


def test_a_failed_tags_read_is_a_failure_naming_the_repository_and_never_an_empty_set() -> None:
    runner = _runner(exit_code=1, stderr="gh: Bad credentials (HTTP 401)\nsecond line")

    tags = repository_release_tags(repository=_REPOSITORY, project_root=_ROOT, runner=runner)

    assert isinstance(tags, ForgeReadFailure)
    assert _REPOSITORY in tags.detail
    assert "Bad credentials" in tags.detail
    # One line of stderr: a multi-line diagnostic pasted into a refusal makes the
    # refusal unreadable at every surface that renders one.
    assert "second line" not in tags.detail


def test_a_tags_read_whose_stderr_is_silent_still_states_the_absence() -> None:
    tags = repository_release_tags(
        repository=_REPOSITORY, project_root=_ROOT, runner=_runner(exit_code=28)
    )

    assert isinstance(tags, ForgeReadFailure)
    # The absence is STATED rather than left blank, because a blank tail reads as
    # a truncation of the sentence it ends.
    assert tags.detail.strip().endswith("no diagnostic on stderr")


def test_a_probe_the_forge_answers_two_hundred_for_reports_the_repository_exists() -> None:
    runner = _runner(stdout="HTTP/2.0 200 OK\r\nContent-Type: application/json\r\n")

    exists = repository_exists(repository=_REPOSITORY, project_root=_ROOT, runner=runner)

    assert exists is True
    assert runner.calls == [(tuple(repository_probe_argv(repository=_REPOSITORY)), _ROOT)]


def test_a_probe_the_forge_answers_four_hundred_four_for_reports_no_such_repository() -> None:
    # The non-zero exit is the measured live behaviour: `gh api` exits 1 on a 404
    # while printing the forge's own status. A build keying on the exit code
    # reports this as a read failure and rejects a record the clause routes to the
    # governed repository.
    runner = _runner(exit_code=1, stdout="HTTP/2.0 404 Not Found\r\n", stderr="gh: HTTP 404")

    assert repository_exists(repository=_REPOSITORY, project_root=_ROOT, runner=runner) is False


def test_a_probe_that_was_redirected_is_graded_on_the_final_response() -> None:
    # A renamed repository answers 301 and `gh` follows it. The FINAL response is
    # the forge's answer about the repository as it now stands; grading the first
    # would report a live repository as neither existing nor absent.
    runner = _runner(stdout="HTTP/2.0 301 Moved Permanently\r\n\r\nHTTP/2.0 200 OK\r\n")

    assert repository_exists(repository=_REPOSITORY, project_root=_ROOT, runner=runner) is True


def test_a_probe_the_forge_answered_no_status_for_is_a_failure() -> None:
    runner = _runner(exit_code=1, stderr="dial tcp: lookup api.github.com: no such host")

    probed = repository_exists(repository=_REPOSITORY, project_root=_ROOT, runner=runner)

    assert isinstance(probed, ForgeReadFailure)
    assert _REPOSITORY in probed.detail
    assert "no such host" in probed.detail


def test_a_probe_answered_with_any_other_status_is_a_failure_naming_that_status() -> None:
    runner = _runner(exit_code=1, stdout="HTTP/2.0 403 Forbidden\r\n", stderr="gh: HTTP 403")

    probed = repository_exists(repository=_REPOSITORY, project_root=_ROOT, runner=runner)

    assert isinstance(probed, ForgeReadFailure)
    # Neither an existing repository nor an absent one: a credential the forge
    # will not accept for this repository is a read the gate could not take.
    assert "403" in probed.detail


def test_the_governed_identity_is_the_owner_and_repository_the_forge_names() -> None:
    runner = _runner(stdout="thewoolleyman/livespec\n")

    identity = governed_repository_identity(project_root=_ROOT, runner=runner)

    assert identity == ExplicitRepository(owner="thewoolleyman", repository="livespec")
    assert runner.calls == [(tuple(governed_repository_argv()), _ROOT)]


def test_a_checkout_whose_identity_the_forge_cannot_answer_is_a_failure() -> None:
    runner = _runner(exit_code=1, stderr="no git remotes found")

    identity = governed_repository_identity(project_root=_ROOT, runner=runner)

    assert isinstance(identity, ForgeReadFailure)
    # The clause requires the rejection to name the repository the gate tried to
    # read; with no identity to name, the checkout it tried to read it from is it.
    assert str(_ROOT) in identity.detail
    assert "no git remotes found" in identity.detail


@pytest.mark.parametrize(
    "answered",
    ["", "livespec", "/livespec", "thewoolleyman/"],
    ids=["blank", "no-separator", "empty-owner", "empty-repository"],
)
def test_an_identity_outside_the_forges_own_grammar_is_a_failure(answered: str) -> None:
    # A zero exit carrying an answer the reader cannot interpret must not reach
    # the tag read: `repos//tags` is a well-formed endpoint about nothing, so the
    # wrong population would be read and reported as the governed repository's.
    identity = governed_repository_identity(project_root=_ROOT, runner=_runner(stdout=answered))

    assert isinstance(identity, ForgeReadFailure)
    assert str(_ROOT) in identity.detail
