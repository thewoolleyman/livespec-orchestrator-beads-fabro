"""Top-of-pyramid post-merge janitor execution coverage."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
    FabroRunResult,
    JournalWriter,
    PollPolicy,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    build_plan,
    janitor_checkout_path,
)


@dataclass(frozen=True, kw_only=True)
class _MergedFabroLauncher:
    def launch(
        self,
        *,
        plan: DispatchPlan,
        runner: CommandRunner,
        journal: JournalWriter,
    ) -> FabroRunResult:
        _ = (plan, runner, journal)
        return FabroRunResult(command=CommandResult(exit_code=0, stdout="fabro done", stderr=""))


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def test_real_post_merge_janitor_provisions_livespec_core(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = _target_repo(tmp_path=tmp_path)
    core_remote = _core_remote(tmp_path=tmp_path)
    tool_bin = _tool_bin(tmp_path=tmp_path)
    git_config = tmp_path / "gitconfig"
    git_config.write_text(
        f'[url "file://{core_remote}"]\n'
        "    insteadOf = https://github.com/thewoolleyman/livespec.git\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PATH", f"{tool_bin}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(git_config))
    monkeypatch.setenv("TEST_MERGE_SHA", _head(repo=target))
    monkeypatch.delenv("LIVESPEC_CORE_PLUGIN_ROOT", raising=False)

    runner = ShellCommandRunner()
    unprovisioned = runner.run(
        argv=["mise", "exec", "--", "just", "check"],
        cwd=target,
        timeout_seconds=120.0,
    )
    assert unprovisioned.exit_code != 0
    assert "livespec CORE plugin not reachable" in unprovisioned.stderr

    plan = build_plan(
        repo=target,
        work_item_id="bd-ib-cyv",
        workflow_toml=target / "workflow.toml",
        goal_file=target / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=janitor_checkout_path(repo=target, work_item_id="bd-ib-cyv"),
    )
    journal = _RecordingJournal()
    outcome = run_dispatch(
        plan=plan,
        runner=runner,
        journal=journal,
        sleep=lambda _: None,
        poll=PollPolicy(attempts=1, interval_seconds=0.0),
        fabro_launcher=_MergedFabroLauncher(),
    )

    assert (outcome.status, outcome.stage) == ("green", "done"), outcome.detail
    stages = [record["stage"] for record in journal.records]
    assert "janitor-core-provision" in stages
    assert "janitor-post-merge" in stages


def _target_repo(*, tmp_path: Path) -> Path:
    source = Path(__file__).resolve().parents[2] / "orchestrator-image" / "e2e-skeleton"
    target = tmp_path / "target"
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    with (target / "justfile").open("a", encoding="utf-8") as handle:
        _ = handle.write("\ninstall-commit-refuse-hooks:\n    @just bootstrap\n")
    _git(target, "init", "-b", "master")
    _git(target, "config", "user.email", "janitor-test@example.invalid")
    _git(target, "config", "user.name", "Janitor Test")
    _git(target, "add", ".")
    _git(target, "commit", "-m", "seed")
    remote = tmp_path / "target-origin.git"
    _git(tmp_path, "init", "--bare", str(remote))
    _git(target, "remote", "add", "origin", str(remote))
    _git(target, "push", "-u", "origin", "master")
    return target


def _core_remote(*, tmp_path: Path) -> Path:
    core = tmp_path / "core"
    plugin_bin = core / ".claude-plugin" / "scripts" / "bin"
    plugin_bin.mkdir(parents=True)
    (plugin_bin / "doctor_static.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    _git(core, "init", "-b", "master")
    _git(core, "config", "user.email", "janitor-test@example.invalid")
    _git(core, "config", "user.name", "Janitor Test")
    _git(core, "add", ".")
    _git(core, "commit", "-m", "seed core")
    remote = tmp_path / "livespec-core.git"
    _git(tmp_path, "init", "--bare", str(remote))
    _git(core, "remote", "add", "origin", str(remote))
    _git(core, "push", "-u", "origin", "master")
    return remote


def _tool_bin(*, tmp_path: Path) -> Path:
    tool_bin = tmp_path / "bin"
    tool_bin.mkdir()
    _write_executable(
        path=tool_bin / "gh",
        text=(
            "#!/usr/bin/env python3\n"
            "import json, os\n"
            "print(json.dumps({\n"
            "    'number': 104,\n"
            "    'state': 'MERGED',\n"
            "    'autoMergeRequest': None,\n"
            "    'mergeStateStatus': 'CLEAN',\n"
            "    'mergeCommit': {'oid': os.environ['TEST_MERGE_SHA']},\n"
            "}))\n"
        ),
    )
    _write_executable(
        path=tool_bin / "mise",
        text=(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'if [ "${1:-}" = trust ]; then exit 0; fi\n'
            'if [ "${1:-}" = exec ] && [ "${2:-}" = -- ]; then shift 2; exec "$@"; fi\n'
            'exec "$@"\n'
        ),
    )
    _write_executable(
        path=tool_bin / "uv",
        text=(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'if [ "${1:-}" = run ]; then shift; exec python3 -m "$@"; fi\n'
            'exec python3 -m "$@"\n'
        ),
    )
    return tool_bin


def _write_executable(*, path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _head(*, repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _git(cwd: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *argv],
        cwd=str(cwd),
        check=True,
        text=True,
        capture_output=True,
    )
