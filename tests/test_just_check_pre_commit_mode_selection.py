"""Regression tests for `dev-tooling/just-check-pre-commit.sh` mode selection.

The Red-mode arm exists so the FIRST step of the Red-Green-Replay ritual can
land: a commit staging exactly one failing test file and zero impl. Any gate in
that arm that EXECUTES the staged test therefore refuses the very commit the arm
is built to admit. `check-check-coverage-incremental` is such a gate — it is
vacuous on a fresh branch, but on a branch already carrying impl commits its
incremental scope pulls in the branch's impl files and runs their tests,
including the staged Red test, which fails by design (work-item bd-ib-c4sfpr).

The Green-amend arm is the control: coverage is exactly what must run once the
impl is staged, so that arm must NOT skip the incremental gate.

`check-master-ci-green` is a separate, ENVIRONMENTAL refusal, and it is keyed on
the checkout rather than on the staged shape: inside a Fabro sandbox — a fresh
full clone carrying the resolved sandbox-exemption marker — master CI re-queues
on every merge, so the gate is frequently red-or-running through no fault of the
staged tree and refuses the sandbox's own Red and Green commits (work-item
bd-ib-hot3g6). A checkout WITHOUT that marker is the control: it must still run
the gate exactly as before.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "dev-tooling" / "just-check-pre-commit.sh"
_INCREMENTAL_GATE = "check-check-coverage-incremental"
_MASTER_CI_GATE = "check-master-ci-green"
_SANDBOX_EXEMPT_MARKER = "livespec.sandboxExempt"
_RED_TRAILER = "TDD-Red-Test-File-Checksum: deadbeef"


def _run(
    *,
    argv: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    run_env = os.environ.copy()
    if env is not None:
        run_env.update(env)
    return subprocess.run(
        argv,
        cwd=cwd,
        env=run_env,
        check=False,
        capture_output=True,
        text=True,
    )


def _install_fake_just(*, repo: Path) -> Path:
    """Put a `just` on PATH that records its argv instead of running the aggregate."""
    bin_dir = repo / "fake-bin"
    bin_dir.mkdir()
    fake_just = bin_dir / "just"
    fake_just.write_text(
        '#!/usr/bin/env bash\nset -uo pipefail\nprintf "%s\\n" "$*" >> just.log\n',
        encoding="utf-8",
    )
    fake_just.chmod(fake_just.stat().st_mode | stat.S_IXUSR)
    return bin_dir


def _init_repo(*, tmp_path: Path, baseline_message: str) -> tuple[Path, dict[str, str]]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(argv=["git", "init"], cwd=repo)
    _run(argv=["git", "config", "user.email", "test@example.com"], cwd=repo)
    _run(argv=["git", "config", "user.name", "Test User"], cwd=repo)
    (repo / "tests").mkdir()
    (repo / "tests" / "test_placeholder.py").write_text("", encoding="utf-8")
    impl_dir = repo / ".claude-plugin" / "scripts"
    impl_dir.mkdir(parents=True)
    (impl_dir / "widget.py").write_text("", encoding="utf-8")
    _run(argv=["git", "add", "."], cwd=repo)
    baseline = _run(argv=["git", "commit", "-m", baseline_message], cwd=repo)
    assert baseline.returncode == 0, baseline.stderr
    fake_bin = _install_fake_just(repo=repo)
    return repo, {"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"}


def _stage(*, repo: Path, relative_path: str, body: str) -> None:
    (repo / relative_path).write_text(body, encoding="utf-8")
    _run(argv=["git", "add", relative_path], cwd=repo)


def _invoke_pre_commit(*, repo: Path, env: dict[str, str]) -> str:
    result = _run(argv=["bash", str(_SCRIPT)], cwd=repo, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    return (repo / "just.log").read_text(encoding="utf-8").strip()


def test_red_mode_arm_skips_the_incremental_coverage_gate(*, tmp_path: Path) -> None:
    repo, env = _init_repo(tmp_path=tmp_path, baseline_message="baseline")
    _stage(repo=repo, relative_path="tests/test_placeholder.py", body="def test_red(): assert 0\n")

    invocation = _invoke_pre_commit(repo=repo, env=env)

    assert invocation.split() == [
        "check-skipping",
        "check-coverage",
        "check-per-file-coverage",
        _INCREMENTAL_GATE,
        "check-codex-skill-picker",
    ]


def test_green_amend_arm_still_runs_the_incremental_coverage_gate(*, tmp_path: Path) -> None:
    repo, env = _init_repo(tmp_path=tmp_path, baseline_message=f"fix: red\n\n{_RED_TRAILER}\n")
    _stage(repo=repo, relative_path=".claude-plugin/scripts/widget.py", body="VALUE = 1\n")

    invocation = _invoke_pre_commit(repo=repo, env=env)

    assert invocation.split() == [
        "check-skipping",
        "check-red-green-replay",
        "check-codex-skill-picker",
    ]
    assert _INCREMENTAL_GATE not in invocation


def _declare_sandbox_exempt(*, repo: Path) -> None:
    """Set the resolved sandbox-exemption marker the way the sandbox prepare step does."""
    result = _run(argv=["git", "config", "--bool", _SANDBOX_EXEMPT_MARKER, "true"], cwd=repo)
    assert result.returncode == 0, result.stderr


def test_sandbox_exempt_red_mode_arm_skips_the_master_ci_green_gate(*, tmp_path: Path) -> None:
    repo, env = _init_repo(tmp_path=tmp_path, baseline_message="baseline")
    _declare_sandbox_exempt(repo=repo)
    _stage(repo=repo, relative_path="tests/test_placeholder.py", body="def test_red(): assert 0\n")

    invocation = _invoke_pre_commit(repo=repo, env=env)

    assert invocation.split() == [
        "check-skipping",
        "check-coverage",
        "check-per-file-coverage",
        _INCREMENTAL_GATE,
        "check-codex-skill-picker",
        _MASTER_CI_GATE,
    ]


def test_sandbox_exempt_green_amend_arm_skips_the_master_ci_green_gate(*, tmp_path: Path) -> None:
    repo, env = _init_repo(tmp_path=tmp_path, baseline_message=f"fix: red\n\n{_RED_TRAILER}\n")
    _declare_sandbox_exempt(repo=repo)
    _stage(repo=repo, relative_path=".claude-plugin/scripts/widget.py", body="VALUE = 1\n")

    invocation = _invoke_pre_commit(repo=repo, env=env)

    assert invocation.split() == [
        "check-skipping",
        "check-red-green-replay",
        "check-codex-skill-picker",
        _MASTER_CI_GATE,
    ]


def test_sandbox_exempt_full_arm_skips_the_master_ci_green_gate(*, tmp_path: Path) -> None:
    repo, env = _init_repo(tmp_path=tmp_path, baseline_message="baseline")
    _declare_sandbox_exempt(repo=repo)
    _stage(repo=repo, relative_path="tests/test_placeholder.py", body="def test_green(): pass\n")
    _stage(repo=repo, relative_path=".claude-plugin/scripts/widget.py", body="VALUE = 1\n")

    invocation = _invoke_pre_commit(repo=repo, env=env)

    assert invocation.split() == [
        "check-skipping",
        "check-codex-skill-picker",
        _MASTER_CI_GATE,
    ]


def test_checkout_without_the_marker_still_runs_the_master_ci_green_gate(*, tmp_path: Path) -> None:
    repo, env = _init_repo(tmp_path=tmp_path, baseline_message="baseline")
    _stage(repo=repo, relative_path="tests/test_placeholder.py", body="def test_green(): pass\n")
    _stage(repo=repo, relative_path=".claude-plugin/scripts/widget.py", body="VALUE = 1\n")

    invocation = _invoke_pre_commit(repo=repo, env=env)

    assert invocation.split() == [
        "check-skipping",
        "check-codex-skill-picker",
    ]
    assert _MASTER_CI_GATE not in invocation
