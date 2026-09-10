"""Operator-author enforcement for every Fabro dispatch workflow."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import (
    GitAuthor,
    GitAuthorPolicy,
    read_dispatch_git_author,
    workflow_git_author_error,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_materialize import (
    MaterializationRefusal,
    materialize_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)

_ROOT = Path(__file__).resolve().parents[3]
_RESERVED_DIR = _ROOT / ".claude-plugin/.fabro/workflows/implement-work-item"
_GROOM_DIR = _ROOT / ".fabro/workflows/groom-work-item"
_WORKFLOW_DIRS = (_RESERVED_DIR, _GROOM_DIR)
_OPERATOR = GitAuthor(name="Chad Woolley", email="thewoolleyman@gmail.com")
_WORKER_TOKEN = "operator-worker-token"
_TRANSPORT_TOKEN = "transport-app-token"
_MECHANICAL_AUTHORS = {
    GitAuthor(
        name="livespec-pr-bot[bot]",
        email="livespec-pr-bot[bot]@users.noreply.github.com",
    ),
    GitAuthor(
        name="livespec-pr-bot[bot]",
        email="283469463+livespec-pr-bot[bot]@users.noreply.github.com",
    ),
    GitAuthor(
        name="thewoolleyman-factory-bot[bot]",
        email="thewoolleyman-factory-bot[bot]@users.noreply.github.com",
    ),
    GitAuthor(
        name="thewoolleyman-factory-bot[bot]",
        email="283469463+thewoolleyman-factory-bot[bot]@users.noreply.github.com",
    ),
}


class _RecordingJournal:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _write_config(*, repo: Path, git_author: object) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"git_author": git_author}), encoding="utf-8"
    )


def _render_workflow(*, directory: Path, author: GitAuthor) -> str:
    rendered = render_run_config_overlay(
        committed_text=(directory / "workflow.toml").read_text(encoding="utf-8"),
        workflow_dir=directory,
        token=_WORKER_TOKEN,
        github_token=_TRANSPORT_TOKEN,
        siblings=None,
        git_author=author,
    )
    assert rendered is not None
    return rendered


def _needs_human_script(*, workflow: Path) -> str:
    matches = [
        line.strip().removeprefix("script=")
        for line in workflow.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("script=") and "LIVESPEC_NEEDS_HUMAN_PRESERVED" in line
    ]
    assert len(matches) == 1
    script = json.loads(matches[0])
    assert isinstance(script, str)
    return script


def _git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_repository_declares_operator_and_preserves_mechanical_author_classifications() -> None:
    policy = read_dispatch_git_author(repo=_ROOT)

    assert isinstance(policy, GitAuthorPolicy)
    assert policy.operator == _OPERATOR
    assert set(policy.mechanical_authors) == _MECHANICAL_AUTHORS


@pytest.mark.parametrize(
    "git_author",
    [
        None,
        {},
        {"operator_name": "", "operator_email": "operator@example.com"},
        {"operator_name": "Operator", "operator_email": ""},
        {
            "operator_name": "Operator",
            "operator_email": "operator@example.com",
            "unexpected": "identity",
        },
        {
            "operator_name": "Operator",
            "operator_email": "operator@example.com",
            "mechanical_authors": [{"name": "Release Bot"}],
        },
    ],
)
def test_missing_or_malformed_operator_author_is_refused(
    tmp_path: Path, git_author: object
) -> None:
    repo = tmp_path / "repo"
    _write_config(repo=repo, git_author=git_author)

    refusal = read_dispatch_git_author(repo=repo)

    assert isinstance(refusal, str)
    assert "git_author" in refusal
    assert ".livespec.jsonc" in refusal


def test_transport_credentials_never_replace_the_declared_operator_author(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    _write_config(
        repo=repo,
        git_author={
            "operator_name": _OPERATOR.name,
            "operator_email": _OPERATOR.email,
            "mechanical_authors": [
                {"name": author.name, "email": author.email}
                for author in sorted(_MECHANICAL_AUTHORS, key=lambda pair: pair.email)
            ],
        },
    )
    monkeypatch.setenv("GITHUB_ACTOR", "thewoolleyman-factory-bot[bot]")

    policy = read_dispatch_git_author(repo=repo)

    assert isinstance(policy, GitAuthorPolicy)
    assert policy.operator == _OPERATOR
    assert policy.operator not in policy.mechanical_authors


def test_dispatch_materialization_refuses_before_payload_without_an_operator_author(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    journal = _RecordingJournal()

    result = materialize_dispatch(
        args=argparse.Namespace(
            workflow=str(_RESERVED_DIR / "workflow.toml"),
            workflow_name=None,
            repo=str(repo),
            acp_node=None,
        ),
        repo=repo,
        work_item_id="bd-ib-author",
        journal=journal,
    )

    assert isinstance(result, MaterializationRefusal)
    assert result.stage == "git-author"
    assert "git_author" in result.detail
    assert journal.records == []


def test_a_committed_workflow_author_may_match_but_cannot_conflict() -> None:
    matching = (
        "[run.git.author]\n"
        f"name = {json.dumps(_OPERATOR.name)}\n"
        f"email = {json.dumps(_OPERATOR.email)}\n"
    )
    conflicting = '[run.git.author]\nname = "Fabro"\nemail = "noreply@fabro.sh"\n'

    assert workflow_git_author_error(committed_text=matching, author=_OPERATOR) is None
    refusal = workflow_git_author_error(committed_text=conflicting, author=_OPERATOR)
    assert isinstance(refusal, str)
    assert "conflicts" in refusal
    assert "noreply@fabro.sh" in refusal
    assert _OPERATOR.email in refusal


@pytest.mark.parametrize("directory", _WORKFLOW_DIRS, ids=("implementation", "grooming"))
def test_every_reserved_or_registered_workflow_projects_the_run_author_for_all_fabro_commits(
    directory: Path,
) -> None:
    """Fabro uses the run author for worker, checkpoint, and metadata commits."""
    rendered = _render_workflow(directory=directory, author=_OPERATOR)
    author_section = rendered.split("[run.git.author]", 1)[1].split("[", 1)[0]

    assert rendered.count("[run.git.author]") == 1
    assert f"name = {json.dumps(_OPERATOR.name)}" in author_section
    assert f"email = {json.dumps(_OPERATOR.email)}" in author_section
    assert "transport-app-token" not in author_section
    assert "operator-worker-token" not in author_section
    assert f"LIVESPEC_GIT_AUTHOR_NAME = {json.dumps(_OPERATOR.name)}" in rendered
    assert f"LIVESPEC_GIT_AUTHOR_EMAIL = {json.dumps(_OPERATOR.email)}" in rendered
    assert "\nGIT_AUTHOR_NAME = " not in rendered
    assert "\nGIT_AUTHOR_EMAIL = " not in rendered


@pytest.mark.parametrize("directory", _WORKFLOW_DIRS, ids=("implementation", "grooming"))
def test_needs_human_commit_forces_the_resolved_author_but_preserves_committer_identity(
    tmp_path: Path, directory: Path
) -> None:
    bare = tmp_path / "origin.git"
    repo = tmp_path / "repo"
    _ = _git("init", "--bare", "--initial-branch=master", str(bare))
    _ = _git("init", "--initial-branch=master", str(repo))
    _ = _git("remote", "add", "origin", str(bare), cwd=repo)
    _ = (repo / "work.txt").write_text("preserve me\n", encoding="utf-8")
    script = _needs_human_script(workflow=directory / "workflow.fabro")
    env = {
        **os.environ,
        "FABRO_RUN_ID": "01AUTHOR",
        "LIVESPEC_GIT_AUTHOR_NAME": _OPERATOR.name,
        "LIVESPEC_GIT_AUTHOR_EMAIL": _OPERATOR.email,
        "GIT_AUTHOR_NAME": "Stale Fabro",
        "GIT_AUTHOR_EMAIL": "noreply@fabro.sh",
        "GIT_COMMITTER_NAME": "Transport Bot",
        "GIT_COMMITTER_EMAIL": "transport@example.com",
    }

    completed = subprocess.run(["bash", "-c", script], cwd=repo, env=env, check=False)

    assert completed.returncode == 1
    identity = _git(
        "--git-dir",
        str(bare),
        "show",
        "-s",
        "--format=%an <%ae>|%cn <%ce>",
        "refs/heads/needs-human/01AUTHOR",
    )
    assert identity == (
        f"{_OPERATOR.name} <{_OPERATOR.email}>|Transport Bot <transport@example.com>"
    )
    assert "fabro@livespec.invalid" not in script
