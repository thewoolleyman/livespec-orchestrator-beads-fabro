"""`publish_draft` binds its run to the commit it pushed, on the pull request.

Binds work-item ``bd-ib-st4obs`` and the paragraph of `SPECIFICATION/contracts.md`
on a publication being bound to its run on the pull request. The
committed ``publish_draft`` script bytes run against a real throwaway origin; the
forge is the only doubled boundary, and the production publication-record program
posts through it, so what the forge double received is what a reader would parse.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_head import (
    PROOF_HEAD_PROGRAM_FILENAME,
    proof_head_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_record import (
    publication_pairs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_record_post import (
    PUBLICATION_RECORD_POST_PROGRAM_RELPATH,
    publication_record_post_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_merge import (
    RECORD_FILE_MERGE_PROGRAM_FILENAME,
    record_file_merge_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_regeneration import (
    RECORD_FILE_PROGRAM_FILENAME,
    record_file_program_source,
)

_WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)
_BRANCH = "feat/bd-ib-st4obs"
_RUN = "01M7PUBLICATIONRUN"
_BOT = "thewoolleyman-factory-bot[bot]"
_NODE = re.compile(r"^\s*publish_draft\s*\[(?P<body>.*?)^\s*\]", re.DOTALL | re.MULTILINE)
_SCRIPT = re.compile(r'script="(?P<value>(?:[^"\\]|\\.)*)"')
_FORGE = """#!/bin/sh
if test "$1 $2" = "pr comment"; then
  cat > "$FORGE_DIR/comment-$$"
  printf '%s\\n' "$3" > "$FORGE_DIR/comment-$$.number"
  if test -f "$FORGE_DIR/refuse-comments"; then echo 'the forge refused the comment' >&2; exit 1; fi
  exit 0
fi
if test "$1 $2" = "pr create"; then printf '%s\\n' 'https://github.test/o/r/pull/77'; exit 0; fi
if test "$1 $2" = "pr list" && test -f "$FORGE_DIR/existing"; then cat "$FORGE_DIR/existing"; exit 0; fi
exit 0
"""


@dataclass(frozen=True, kw_only=True)
class _Run:
    clone: Path
    forge: Path
    origin: Path


def _git(cwd: Path, *argv: str) -> str:
    done = subprocess.run(["git", *argv], cwd=str(cwd), check=True, text=True, capture_output=True)
    return done.stdout.strip()


def _commit(*, repo: Path, path: str, content: str) -> str:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(content, encoding="utf-8")
    _git(repo, "add", path)
    _git(repo, "commit", "-m", f"change {path}")
    return _git(repo, "rev-parse", "HEAD")


def _identify(*, repo: Path) -> None:
    _git(repo, "config", "user.name", "publication-record-test")
    _git(repo, "config", "user.email", "publication-record-test@example.invalid")


def _advanced_default(*, tmp_path: Path) -> _Run:
    """A run with its own work, while the default branch has since moved on."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "-b", "master", str(origin))
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-b", "master")
    _identify(repo=seed)
    _ = _commit(repo=seed, path="base.txt", content="base\n")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-u", "origin", "master")
    run = tmp_path / "run"
    _git(tmp_path, "clone", str(origin), str(run))
    _identify(repo=run)
    _git(run, "switch", "-c", "fabro/run/test")
    _ = _commit(repo=run, path="src/change.txt", content="run work\n")
    _git(run, "config", "livespec.factoryRunId", _RUN)
    _ = _commit(repo=seed, path="moved.txt", content="the default moved\n")
    _git(seed, "push", "origin", "master")
    forge = tmp_path / "forge"
    forge.mkdir()
    return _Run(clone=run, forge=forge, origin=origin)


def _script() -> str:
    block = _NODE.search(_WORKFLOW.read_text(encoding="utf-8"))
    assert block is not None
    attr = _SCRIPT.search(block.group("body"))
    assert attr is not None
    return (
        attr.group("value")
        .replace(r"\"", '"')
        .replace("{{ inputs.default_branch }}", "master")
        .replace("{{ inputs.sandbox_check_suite }}", "true")
        .replace("{{ inputs.conformance_hook_install }}", "")
    )


def _publish(
    *, tmp_path: Path, run: _Run, posting_program: bool = True, run_id: bool = True
) -> str:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    _ = gh.write_text(_FORGE, encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
    sleep = bin_dir / "sleep"
    _ = sleep.write_text("#!/bin/sh\n", encoding="utf-8")
    sleep.chmod(sleep.stat().st_mode | stat.S_IXUSR)
    plugins = tmp_path / "plugins"
    plugins.mkdir(exist_ok=True)
    _ = (plugins / PROOF_HEAD_PROGRAM_FILENAME).write_text(
        proof_head_program_source(), encoding="utf-8"
    )
    _ = (plugins / RECORD_FILE_MERGE_PROGRAM_FILENAME).write_text(
        record_file_merge_program_source(), encoding="utf-8"
    )
    _ = (plugins / RECORD_FILE_PROGRAM_FILENAME).write_text(
        record_file_program_source(), encoding="utf-8"
    )
    helpers = tmp_path / "gh-refresh"
    if posting_program:
        program = helpers / PUBLICATION_RECORD_POST_PROGRAM_RELPATH
        program.parent.mkdir(parents=True, exist_ok=True)
        _ = program.write_text(publication_record_post_program_source(), encoding="utf-8")
        program.chmod(0o755)
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE")
    }
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
            "FORGE_DIR": str(run.forge),
            "LIVESPEC_PUBLISH_BRANCH": _BRANCH,
            "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(plugins),
            "LIVESPEC_SANDBOX_GH_REFRESH_ROOT": str(helpers),
        }
    )
    if run_id:
        env["FABRO_RUN_ID"] = _RUN
    else:
        _ = env.pop("FABRO_RUN_ID", None)
    done = subprocess.run(
        ["sh", "-c", _script()],
        cwd=str(run.clone),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return done.stderr


def _comments(*, run: _Run) -> list[tuple[str, str]]:
    return [
        (
            path.read_text(encoding="utf-8"),
            path.with_name(path.name + ".number").read_text().strip(),
        )
        for path in sorted(run.forge.glob("comment-[0-9]*"))
        if not path.name.endswith(".number")
    ]


def _origin_tip(*, run: _Run) -> str:
    return _git(run.clone, "ls-remote", str(run.origin), f"refs/heads/{_BRANCH}").split()[0]


def test_a_publish_that_opens_the_draft_binds_the_run_to_the_commit_it_pushed(
    tmp_path: Path,
) -> None:
    """The refresh rebases the run first, so the pushed commit differs from the janitor's head."""
    run = _advanced_default(tmp_path=tmp_path)
    janitor_head = _git(run.clone, "rev-parse", "HEAD")

    stderr = _publish(tmp_path=tmp_path, run=run)

    pushed = _origin_tip(run=run)
    assert pushed != janitor_head, "the refresh left the janitor's head unchanged"
    ((body, number),) = _comments(run=run)
    assert number == "77"
    assert publication_pairs(
        comments=({"body": body, "author": {"login": _BOT}},), publication_identity=_BOT
    ) == ((pushed, _RUN),)
    assert "stage: publish_draft" in body.splitlines()
    assert "pull-request: 77" in body.splitlines()
    assert janitor_head not in body
    assert "LIVESPEC_PUBLICATION_RECORD_POSTED" in stderr


def test_a_publish_that_finds_the_pull_request_already_open_binds_to_that_one(
    tmp_path: Path,
) -> None:
    """The record lands on the pull request the stage found, not a new one."""
    run = _advanced_default(tmp_path=tmp_path)
    _ = (run.forge / "existing").write_text("88\n", encoding="utf-8")

    _ = _publish(tmp_path=tmp_path, run=run)

    ((body, number),) = _comments(run=run)
    assert number == "88"
    assert f"head: {_origin_tip(run=run)}" in body.splitlines()


def test_a_second_publish_that_moves_nothing_posts_no_record(tmp_path: Path) -> None:
    """The contract: a push that leaves the publish branch's tip unchanged posts no record."""
    run = _advanced_default(tmp_path=tmp_path)
    _ = (run.forge / "existing").write_text("88\n", encoding="utf-8")
    _ = _publish(tmp_path=tmp_path, run=run)
    assert len(_comments(run=run)) == 1

    stderr = _publish(tmp_path=tmp_path, run=run)

    assert len(_comments(run=run)) == 1
    assert "LIVESPEC_PUBLICATION_RECORD_SKIPPED" in stderr


def test_a_refused_comment_leaves_the_publication_succeeded_and_reports_why(
    tmp_path: Path,
) -> None:
    """Posting never changes the stage's outcome or the head it pushed."""
    run = _advanced_default(tmp_path=tmp_path)
    _ = (run.forge / "refuse-comments").write_text("", encoding="utf-8")

    stderr = _publish(tmp_path=tmp_path, run=run)

    pushed = _origin_tip(run=run)
    assert "LIVESPEC_PUBLISH_DRAFT_PUBLISHED" in stderr
    assert f"head={pushed}" in stderr
    assert "LIVESPEC_PUBLICATION_RECORD_FAILED" in stderr
    assert f"run={_RUN}" in stderr
    assert f"pushed={pushed}" in stderr
    assert "step=comment-post" in stderr


@pytest.mark.parametrize("run_id_source", ["environment", "git-config"])
def test_the_record_names_the_run_the_proof_records_name(
    tmp_path: Path, run_id_source: str
) -> None:
    """The run id is `$FABRO_RUN_ID`, else the dispatch id the clone's git config carries."""
    run = _advanced_default(tmp_path=tmp_path)
    if run_id_source == "git-config":
        _git(run.clone, "config", "livespec.factoryRunId", "01M7DISPATCHID")

    _ = _publish(tmp_path=tmp_path, run=run, run_id=run_id_source == "environment")

    ((body, _number),) = _comments(run=run)
    expected = _RUN if run_id_source == "environment" else "01M7DISPATCHID"
    assert f"run-id: {expected}" in body.splitlines()


def test_a_sandbox_without_the_program_still_publishes_and_reports_why(tmp_path: Path) -> None:
    """The helper's absence is reported in the stage's output and never raised."""
    run = _advanced_default(tmp_path=tmp_path)

    stderr = _publish(tmp_path=tmp_path, run=run, posting_program=False)

    assert "LIVESPEC_PUBLISH_DRAFT_PUBLISHED" in stderr
    assert "step=helper-absent" in stderr
    assert _comments(run=run) == []
