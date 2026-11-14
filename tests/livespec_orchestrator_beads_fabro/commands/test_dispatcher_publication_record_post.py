"""The materialized program that posts a run's publication record.

The program is stdlib-only Python the Dispatcher lands beside the push credential
helper, so each case EXECUTES its shipped bytes against a stand-in `gh` and then
reads what it posted back through the production reader, which is what makes
"writer and reader agree on the format" an observation rather than a promise.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_gh_refresh_helpers import (
    gh_refresh_helpers,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_record import (
    PUBLICATION_RECORD_FIELDS,
    PUBLICATION_RECORD_MARKER,
    publication_pairs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_record_post import (
    PUBLICATION_RECORD_POST_PROGRAM_RELPATH,
    publication_record_post_program_source,
)

_BOT = "thewoolleyman-factory-bot[bot]"
_RUN = "01M7PUBLICATIONRUN"
_HEAD = "a" * 40
_PREVIOUS = "b" * 40
_BRANCH = "feat/bd-ib-st4obs"
_GH_STUB = r"""#!%(python)s
import json, os, sys

state_path = os.environ["FAKE_FORGE"]
with open(state_path) as handle:
    state = json.load(handle)
argv = sys.argv[1:]
state["calls"].append(argv)
if argv[:2] == ["pr", "comment"]:
    state["bodies"].append(sys.stdin.read())
    with open(state_path, "w") as handle:
        json.dump(state, handle)
    if state["comment_fails"]:
        sys.stderr.write("the forge refused the comment\n")
        sys.exit(1)
    sys.exit(0)
with open(state_path, "w") as handle:
    json.dump(state, handle)
if argv[:2] == ["pr", "list"]:
    if state["list_fails"]:
        sys.stderr.write("the forge could not list\n")
        sys.exit(1)
    print(state["listed"])
    sys.exit(0)
sys.exit(2)
"""


@dataclass(frozen=True, kw_only=True)
class _Posted:
    result: subprocess.CompletedProcess[str]
    bodies: tuple[str, ...]
    calls: tuple[tuple[str, ...], ...]


def _post(
    *,
    tmp_path: Path,
    argv: list[str],
    comment_fails: bool = False,
    list_fails: bool = False,
    listed: str = "",
    forge_on_path: bool = True,
) -> _Posted:
    program = tmp_path / "post_publication_record"
    _ = program.write_text(publication_record_post_program_source(), encoding="utf-8")
    program.chmod(program.stat().st_mode | stat.S_IXUSR)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "gh"
    _ = stub.write_text(_GH_STUB % {"python": sys.executable}, encoding="utf-8")
    stub.chmod(0o755)
    forge = tmp_path / "forge.json"
    _ = forge.write_text(
        json.dumps(
            {
                "bodies": [],
                "calls": [],
                "comment_fails": comment_fails,
                "list_fails": list_fails,
                "listed": listed,
            }
        ),
        encoding="utf-8",
    )
    env = {
        "PATH": f"{bin_dir}{os.pathsep}/usr/bin" if forge_on_path else str(tmp_path / "empty"),
        "FAKE_FORGE": str(forge),
    }
    result = subprocess.run(
        [sys.executable, str(program), *argv],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    state = json.loads(forge.read_text(encoding="utf-8"))
    return _Posted(
        result=result,
        bodies=tuple(state["bodies"]),
        calls=tuple(tuple(call) for call in state["calls"]),
    )


def _argv(
    *,
    head: str = _HEAD,
    previous: str = _PREVIOUS,
    pull_request: str = "4515",
    run: str = _RUN,
    stage: str = "publish_draft",
) -> list[str]:
    return [
        "--stage",
        stage,
        "--head",
        head,
        "--previous-tip",
        previous,
        "--pull-request",
        pull_request,
        "--branch",
        _BRANCH,
        "--run-id",
        run,
    ]


def test_a_moved_publish_branch_posts_one_record_naming_the_pushed_head(tmp_path: Path) -> None:
    """The comment is on the named pull request and the production reader binds it."""
    posted = _post(tmp_path=tmp_path, argv=_argv())

    assert posted.result.returncode == 0, posted.result.stderr
    assert posted.calls == (("pr", "comment", "4515", "--body-file", "-"),)
    (body,) = posted.bodies
    lines = body.splitlines()
    assert lines[0] == PUBLICATION_RECORD_MARKER
    assert [line.split(":", maxsplit=1)[0] for line in lines[1:]] == list(PUBLICATION_RECORD_FIELDS)
    assert "run-id: " + _RUN in lines
    assert "stage: publish_draft" in lines
    assert "pull-request: 4515" in lines
    assert publication_pairs(
        comments=({"body": body, "author": {"login": _BOT}},), publication_identity=_BOT
    ) == ((_HEAD, _RUN),)
    assert "LIVESPEC_PUBLICATION_RECORD_POSTED" in posted.result.stderr


def test_the_record_names_the_head_it_is_passed_and_never_the_previous_tip(
    tmp_path: Path,
) -> None:
    """A push that created its own commit is bound to that commit, not to an older head."""
    created = "c" * 40
    posted = _post(tmp_path=tmp_path, argv=_argv(head=created))

    (body,) = posted.bodies
    assert f"head: {created}" in body.splitlines()
    assert _PREVIOUS not in body
    assert _HEAD not in body


def test_a_push_that_left_the_tip_unchanged_posts_no_record(tmp_path: Path) -> None:
    """The contract: an unchanged tip posts nothing, and says so."""
    posted = _post(tmp_path=tmp_path, argv=_argv(previous=_HEAD))

    assert posted.result.returncode == 0
    assert posted.calls == ()
    assert "LIVESPEC_PUBLICATION_RECORD_SKIPPED" in posted.result.stderr


def test_a_first_publication_with_no_previous_tip_posts_a_record(tmp_path: Path) -> None:
    """A branch origin did not hold has no previous tip, so every head is new."""
    posted = _post(tmp_path=tmp_path, argv=_argv(previous=""))

    assert len(posted.bodies) == 1


def test_a_missing_pull_request_number_is_resolved_from_the_publish_branch(
    tmp_path: Path,
) -> None:
    """`pr_refresh` passes no number: the open pull request of the branch is found."""
    posted = _post(tmp_path=tmp_path, argv=_argv(pull_request="", stage="pr_refresh"), listed="77")

    assert posted.calls[0][:4] == ("pr", "list", "--head", _BRANCH)
    assert posted.calls[1] == ("pr", "comment", "77", "--body-file", "-")
    assert "pull-request: 77" in posted.bodies[0].splitlines()
    assert "stage: pr_refresh" in posted.bodies[0].splitlines()


def test_a_leading_hash_on_the_pull_request_number_is_dropped(tmp_path: Path) -> None:
    """A caller echoing `#4515` still posts to pull request 4515."""
    posted = _post(tmp_path=tmp_path, argv=_argv(pull_request="#4515"))

    assert posted.calls == (("pr", "comment", "4515", "--body-file", "-"),)


@pytest.mark.parametrize(
    ("kwargs", "step"),
    [
        ({"run": ""}, "run-id"),
        ({"head": "abc"}, "pushed-head"),
    ],
)
def test_an_unusable_input_reports_the_run_the_commit_and_the_step(
    tmp_path: Path, kwargs: dict[str, str], step: str
) -> None:
    """Failure is reported in the stage's own output and never changes its exit code."""
    posted = _post(tmp_path=tmp_path, argv=_argv(**kwargs))

    assert posted.result.returncode == 0
    assert posted.calls == ()
    assert "LIVESPEC_PUBLICATION_RECORD_FAILED" in posted.result.stderr
    assert f"step={step}" in posted.result.stderr


def test_a_failed_comment_post_is_reported_and_does_not_fail_the_stage(tmp_path: Path) -> None:
    """The run, the pushed commit and the failed step are named; the exit code is 0."""
    posted = _post(tmp_path=tmp_path, argv=_argv(), comment_fails=True)

    assert posted.result.returncode == 0
    assert f"run={_RUN}" in posted.result.stderr
    assert f"pushed={_HEAD}" in posted.result.stderr
    assert "step=comment-post" in posted.result.stderr
    assert "the forge refused the comment" in posted.result.stderr


def test_a_failed_pull_request_lookup_is_reported_and_posts_nothing(tmp_path: Path) -> None:
    """An unreadable forge posts nothing and names the lookup as the failed step."""
    posted = _post(tmp_path=tmp_path, argv=_argv(pull_request=""), list_fails=True)

    assert posted.result.returncode == 0
    assert "step=pull-request-lookup" in posted.result.stderr
    assert "the forge could not list" in posted.result.stderr
    assert posted.bodies == ()


def test_a_branch_with_no_open_pull_request_is_reported(tmp_path: Path) -> None:
    """An empty lookup is a failed step too, naming the branch."""
    posted = _post(tmp_path=tmp_path, argv=_argv(pull_request=""), listed="")

    assert posted.result.returncode == 0
    assert "step=pull-request-lookup" in posted.result.stderr
    assert _BRANCH in posted.result.stderr


def test_an_absent_forge_client_is_reported_rather_than_raised(tmp_path: Path) -> None:
    """A bug-class failure inside the program is still the stage's exit code 0."""
    posted = _post(tmp_path=tmp_path, argv=_argv(), forge_on_path=False)

    assert posted.result.returncode == 0
    assert "step=unexpected-error" in posted.result.stderr
    assert "FileNotFoundError" in posted.result.stderr


def test_the_program_is_a_digest_verified_gh_refresh_helper_beside_the_push_program() -> None:
    """The Dispatcher materializes it where the stages look for it."""
    helpers = {helper.name: helper for helper in gh_refresh_helpers(scripts_root=_SCRIPTS_ROOT)}

    posting = helpers["gh-post-publication-record"]
    assert posting.path == PUBLICATION_RECORD_POST_PROGRAM_RELPATH
    assert posting.path == "bin/post_publication_record"
    assert posting.mode == 0o755
    assert posting.compose() == publication_record_post_program_source().encode("utf-8")
    assert helpers["gh-push-origin"].path.rsplit("/", maxsplit=1)[0] == "bin"


_SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / ".claude-plugin" / "scripts"
