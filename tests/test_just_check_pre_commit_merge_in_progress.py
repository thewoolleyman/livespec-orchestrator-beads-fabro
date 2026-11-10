"""A merge in progress reaches the evidence-writing aggregate in the local pre-commit.

`dev-tooling/just-check-pre-commit.sh` picks its branch from HEAD's trailers and
the staged paths.  A janitor refresh merge staging product code onto a run whose
HEAD carries Red-only trailers would take a Green-amend branch, which records no
same-tree evidence, so the merge commit's suite-green leg ran the full suite a
second time.  While a merge is in progress the script must skip those branches,
as `red_green_replay`'s own merge routing does, and run the full aggregate that
writes the evidence.  A merge staging no `.py` stays on the doc-only path.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PRE_COMMIT_SCRIPT = _REPO_ROOT / "dev-tooling" / "just-check-pre-commit.sh"
_RED_TRAILER = "TDD-Red-Test-File-Checksum: deadbeef"
_IMPL = ".claude-plugin/scripts/widget.py"
_WORKFLOW = ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"


def _git(*, repo: Path, arguments: list[str]) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        capture_output=True,
        check=True,
        text=True,
    )
    return completed.stdout.strip()


def _write(*, repo: Path, path: str, text: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(text, encoding="utf-8")


def _red_only_head_repository(
    *, tmp_path: Path, merging: bool
) -> tuple[Path, dict[str, str], Path]:
    """A run whose HEAD is an open Red that changed a test, with staged non-test changes."""
    repo = tmp_path / "repository"
    repo.mkdir(parents=True)
    _ = _git(repo=repo, arguments=["init", "--quiet"])
    _ = _git(repo=repo, arguments=["config", "user.name", "Test User"])
    _ = _git(repo=repo, arguments=["config", "user.email", "test@example.invalid"])
    _write(repo=repo, path=_IMPL, text="VALUE = 0\n")
    _write(repo=repo, path=_WORKFLOW, text="digraph {}\n")
    _write(repo=repo, path="tests/test_widget.py", text="def test_value() -> None: ...\n")
    _ = _git(repo=repo, arguments=["add", "."])
    _ = _git(repo=repo, arguments=["commit", "--quiet", "-m", "baseline"])
    _write(repo=repo, path="tests/test_widget.py", text="def test_value() -> None:\n    assert 1\n")
    _ = _git(repo=repo, arguments=["add", "tests/test_widget.py"])
    _ = _git(
        repo=repo,
        arguments=["commit", "--quiet", "-m", "feat: red\n\n" + _RED_TRAILER],
    )
    if merging:
        head = _git(repo=repo, arguments=["rev-parse", "HEAD"])
        _write(repo=repo, path=".git/MERGE_HEAD", text=head + "\n")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in {
        "uv": """#!/usr/bin/env bash
printf 'uv %s\\n' "$*" >> "$FAKE_LOG"
case "$*" in
  *"pre_commit_delegate run"*) exit 75 ;;
esac
""",
        "just": """#!/usr/bin/env bash
printf 'just %s\\n' "$*" >> "$FAKE_LOG"
""",
    }.items():
        tool = bin_dir / name
        _ = tool.write_text(body, encoding="utf-8")
        _ = tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "calls.log"
    return (
        repo,
        {
            **{key: value for key, value in os.environ.items() if key != "SKIP_TARGETS"},
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "FAKE_LOG": str(log),
        },
        log,
    )


def _run(*, repo: Path, env: dict[str, str], log: Path) -> list[str]:
    completed = subprocess.run(
        ["bash", str(_PRE_COMMIT_SCRIPT)],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def test_a_merge_staging_product_python_runs_the_evidence_writing_aggregate(
    *, tmp_path: Path
) -> None:
    repo, env, log = _red_only_head_repository(tmp_path=tmp_path, merging=True)
    _write(repo=repo, path=_IMPL, text="VALUE = 1\n")
    _ = _git(repo=repo, arguments=["add", _IMPL])

    calls = _run(repo=repo, env=env, log=log)

    assert "just check-skipping check-codex-skill-picker" in calls
    assert not any("check-red-green-replay" in call for call in calls)
    assert not any("check-staged-precheck" in call for call in calls)
    assert any("green_token write-pre-commit pre-commit-aggregate:" in call for call in calls)


def test_a_merge_staging_the_workflow_graph_alone_stays_on_the_doc_only_path(
    *, tmp_path: Path
) -> None:
    repo, env, log = _red_only_head_repository(tmp_path=tmp_path, merging=True)
    _write(repo=repo, path=_WORKFLOW, text="digraph { a }\n")
    _ = _git(repo=repo, arguments=["add", _WORKFLOW])

    calls = _run(repo=repo, env=env, log=log)

    assert "just check-pre-commit-doc-only" in calls
    assert not any("check-staged-precheck" in call for call in calls)
    assert not any("green_token write-pre-commit" in call for call in calls)


def test_the_same_staged_change_without_a_merge_keeps_the_green_amend_branch(
    *, tmp_path: Path
) -> None:
    repo, env, log = _red_only_head_repository(tmp_path=tmp_path, merging=False)
    _write(repo=repo, path=_IMPL, text="VALUE = 1\n")
    _ = _git(repo=repo, arguments=["add", _IMPL])

    calls = _run(repo=repo, env=env, log=log)

    assert "just check-staged-precheck" in calls
    assert "just check-skipping check-red-green-replay check-codex-skill-picker" in calls
    assert not any("green_token write-pre-commit" in call for call in calls)
