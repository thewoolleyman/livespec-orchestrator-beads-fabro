"""A run-owned workflow edit is preserved and reported, never published."""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan

_WORKFLOW = Path(".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro")
_PUBLISH_BRANCH = "feat/bd-ib-qustjx"
_RUN_ID = "01WORKFLOWPERMISSION"
_WORKFLOW_PATH = ".github/workflows/run-owned.yml"
_SCRIPT = re.compile(r'script="(?P<value>(?:[^"\\]|\\.)*)"')


def _git(cwd: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *argv],
        cwd=str(cwd),
        check=True,
        text=True,
        capture_output=True,
    )


def _node_script(*, node: str) -> str:
    text = _WORKFLOW.read_text(encoding="utf-8")
    block = re.search(
        rf"^\s*{node}\s*\[(?P<body>.*?)^\s*\]",
        text,
        re.DOTALL | re.MULTILINE,
    )
    assert block is not None
    attr = _SCRIPT.search(block.group("body"))
    assert attr is not None
    return re.sub(r"\\(?P<escaped>.)", r"\g<escaped>", attr.group("value")).replace(
        "{{ inputs.default_branch }}", "master"
    )


def _sandbox(*, tmp_path: Path) -> tuple[Path, Path]:
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "-b", "master", str(origin))
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-b", "master")
    _git(work, "config", "user.name", "workflow-refusal-test")
    _git(work, "config", "user.email", "workflow-refusal-test@example.invalid")
    (work / "base.txt").write_text("base\n", encoding="utf-8")
    _git(work, "add", "base.txt")
    _git(work, "commit", "-m", "base")
    _git(work, "remote", "add", "origin", str(origin))
    _git(work, "push", "-u", "origin", "master")
    _git(work, "switch", "-c", "fabro/run/workflow-refusal")
    target = work / _WORKFLOW_PATH
    target.parent.mkdir(parents=True)
    target.write_text("name: run-owned\n", encoding="utf-8")
    _git(work, "add", _WORKFLOW_PATH)
    _git(work, "commit", "-m", "run changes workflow")
    return work, origin


def _gh_double(*, tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        'if test "$1 $2" = "pr create"; then : > "$GH_DRAFT_CREATED"; fi\n'
        "exit 0\n",
        encoding="utf-8",
    )
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
    return bin_dir


def _env(*, tmp_path: Path) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE")
    }
    env.update(
        {
            "PATH": f"{_gh_double(tmp_path=tmp_path)}{os.pathsep}{env.get('PATH', '')}",
            "GH_DRAFT_CREATED": str(tmp_path / "draft-created"),
            "LIVESPEC_GIT_AUTHOR_NAME": "Workflow Refusal Test",
            "LIVESPEC_GIT_AUTHOR_EMAIL": "workflow-refusal-test@example.invalid",
            "LIVESPEC_PUBLISH_BRANCH": _PUBLISH_BRANCH,
        }
    )
    return env


def _plan(*, repo: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=repo,
        work_item_id="bd-ib-qustjx",
        branch=_PUBLISH_BRANCH,
        workflow_toml=repo / "workflow.toml",
        goal_file=repo / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name="hp",
        fabro_factory_server=None,
        fabro_factory_dev_token=None,
        janitor=("just", "check"),
        janitor_checkout=repo / ".janitor",
        janitor_core_checkout=repo / ".janitor" / ".livespec-core",
        janitor_core_repo_url="https://github.com/thewoolleyman/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="succeeded",
    )


def test_run_owned_workflow_edit_is_preserved_and_blocks_with_its_permission_reason(
    tmp_path: Path,
) -> None:
    work, origin = _sandbox(tmp_path=tmp_path)
    env = _env(tmp_path=tmp_path)

    publish = subprocess.run(
        ["sh", "-c", _node_script(node="publish_draft")],
        cwd=str(work),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert publish.returncode != 0
    assert _WORKFLOW_PATH in publish.stderr
    assert "GitHub App" in publish.stderr
    assert "workflows permission" in publish.stderr
    assert _git(work, "ls-remote", "origin", f"refs/heads/{_PUBLISH_BRANCH}").stdout == ""
    assert not (tmp_path / "draft-created").exists()

    terminal = subprocess.run(
        ["sh", "-c", _node_script(node="needs_human")],
        cwd=str(work),
        env=env,
        text=True,
        capture_output=True,
        input=f"{_RUN_ID}\n",
        check=False,
    )
    assert terminal.returncode != 0
    assert _WORKFLOW_PATH in terminal.stderr
    assert "workflows permission" in terminal.stderr
    preserved = _git(
        origin, "for-each-ref", "--format=%(refname)", f"refs/heads/needs-human/{_RUN_ID}"
    ).stdout.strip()
    assert preserved == f"refs/heads/needs-human/{_RUN_ID}"

    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(repo=work),
        run_id=_RUN_ID,
        inspect=None,
        exit_code=1,
        stderr=f"{publish.stderr}\n{terminal.stderr}",
    )
    assert outcome is not None
    assert outcome.status == "blocked"
    assert _WORKFLOW_PATH in outcome.detail
    assert "workflows permission" in outcome.detail
