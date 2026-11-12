"""Scenario 313's host-side scheduled-workflow breakage pass."""

from __future__ import annotations

import json
import os
import subprocess
from importlib import import_module
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from returns.io import IOFailure, IOSuccess

_ROOT = Path(__file__).resolve().parents[3]
_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_breakage_pass"
_MODULE_PATH = (
    _ROOT
    / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_breakage_pass.py"
)
_SERVICE_DIR = _ROOT / "orchestrator-image/services/breakage-pass"


class _Runner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.latest_run: dict[str, object] | None = {
            "id": 42,
            "conclusion": "failure",
            "head_sha": "abc123",
            "html_url": "https://github.example/runs/42",
        }
        self.jobs: list[dict[str, object]] = [
            {
                "id": 7,
                "name": "check-types",
                "conclusion": "failure",
                "steps": [{"name": "Run tests", "conclusion": "failure"}],
            },
            {
                "id": 8,
                "name": "check-coverage",
                "conclusion": "failure",
                "steps": [{"name": "Check coverage", "conclusion": "failure"}],
            },
            {"id": 9, "name": "green", "conclusion": "success", "steps": []},
        ]
        self.logs = {
            "7": "setup\nFAILED tests/test_types.py::test_contract\ntests/test_types.py::test_edge FAILED",
            "8": "coverage below threshold",
        }
        self.failure: str | None = None

    def run(
        self, *, argv: list[str], cwd: Path, timeout_seconds: float, **_: object
    ) -> CommandResult:
        _ = (cwd, timeout_seconds)
        self.calls.append(argv)
        endpoint = argv[-1]
        if self.failure is not None and self.failure in endpoint:
            return CommandResult(exit_code=1, stdout="", stderr="unreadable")
        if "/runs?" in endpoint:
            return _result({"workflow_runs": [] if self.latest_run is None else [self.latest_run]})
        if "/jobs?" in endpoint:
            return _result({"jobs": self.jobs})
        if endpoint.endswith("/logs"):
            return _result(self.logs[endpoint.split("/")[-2]])
        raise AssertionError(argv)


class _Client:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def list_issues(self) -> list[dict[str, object]]:
        return self.records

    def update_issue(self, *, issue_id: str, **changes: object) -> None:
        self.records.append(
            {
                "id": issue_id,
                "metadata": changes["metadata"],
                "labels": changes["add_labels"],
            }
        )


def _result(payload: object) -> CommandResult:
    return CommandResult(exit_code=0, stdout=json.dumps(payload), stderr="")


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="test",
        prefix="bd-ib",
        server_user="test",
        database="test",
        bd_path="bd",
        fake=True,
        repo_root=Path(),
    )


def _configured_pass(*, monkeypatch: Any) -> tuple[Any, _Runner, _Client, list[WorkItem]]:
    breakage = import_module(_MODULE)
    runner = _Runner()
    client = _Client()
    filed: list[WorkItem] = []
    identifiers = iter(("bd-ib-types", "bd-ib-coverage"))
    monkeypatch.setattr(
        breakage,
        "dispatcher_block",
        lambda **_: {"breakage_workflows": ["ci-root-uid.yml"]},
    )
    monkeypatch.setattr(breakage, "resolve_default_branch", lambda **_: "master")
    monkeypatch.setattr(breakage, "resolve_store_config", lambda **_: _config())
    monkeypatch.setattr(breakage, "make_beads_client", lambda **_: client)
    monkeypatch.setattr(
        breakage,
        "file_captured_work_item",
        lambda **kwargs: filed.append(kwargs["item"]) or IOSuccess("ready"),
    )
    monkeypatch.setattr(breakage, "new_work_item_id", lambda **_: next(identifiers))
    monkeypatch.setattr(breakage, "utc_now_iso", lambda: "2026-11-12T00:00:00Z")
    return breakage, runner, client, filed


def test_a_failed_run_files_per_job_with_log_tests_then_deduplicates(
    monkeypatch: Any,
) -> None:
    """A cached pass files every failed job once, including its test evidence."""
    assert _MODULE_PATH.is_file()
    breakage, runner, client, filed = _configured_pass(monkeypatch=monkeypatch)

    first = breakage.breakage_pass(repo=Path(), runner=runner)

    assert first.exit_code == 0
    assert first.lines == ("ci-root-uid.yml run 42: filed bd-ib-types, bd-ib-coverage",)
    assert [item.title for item in filed] == [
        "CI breakage: ci-root-uid.yml — check-types",
        "CI breakage: ci-root-uid.yml — check-coverage",
    ]
    assert "https://github.example/runs/42" in filed[0].description
    assert "abc123" in filed[0].description
    assert "tests/test_types.py::test_contract" in filed[0].description
    assert "tests/test_types.py::test_edge" in filed[0].description
    assert "No failing test named; failing step: Check coverage" in filed[1].description
    assert [record["metadata"] for record in client.records] == [
        {"breakage_key": "ci-root-uid.yml:check-types:abc123"},
        {"breakage_key": "ci-root-uid.yml:check-coverage:abc123"},
    ]
    assert all(call[:3] == ["gh", "api", "--cache"] for call in runner.calls)

    repeated = breakage.breakage_pass(repo=Path(), runner=runner)
    assert runner.latest_run is not None
    runner.latest_run["conclusion"] = "success"
    green = breakage.breakage_pass(repo=Path(), runner=runner)

    assert repeated.lines == ("ci-root-uid.yml run 42: already-filed bd-ib-types, bd-ib-coverage",)
    assert green.lines == ("ci-root-uid.yml run 42: green",)
    assert len(filed) == 2


def test_unreadable_and_empty_workflow_reads_never_file_items(monkeypatch: Any) -> None:
    """Read failures are visible, while an empty completed-run list is benign."""
    assert _MODULE_PATH.is_file()
    breakage, runner, _, filed = _configured_pass(monkeypatch=monkeypatch)
    runner.latest_run = None

    no_run = breakage.breakage_pass(repo=Path(), runner=runner)

    assert no_run.exit_code == 0
    assert no_run.lines == ("ci-root-uid.yml: no-completed-run",)
    runner.latest_run = {
        "id": 42,
        "conclusion": "failure",
        "head_sha": "abc123",
        "html_url": "https://github.example/runs/42",
    }
    runner.failure = "/logs"
    unreadable = breakage.breakage_pass(repo=Path(), runner=runner)

    assert unreadable.exit_code == 1
    assert unreadable.lines == ("ci-root-uid.yml run 42: unreadable workflow job log",)
    assert filed == []


def test_the_pass_refuses_every_unreadable_or_unfileable_input(monkeypatch: Any) -> None:
    """The ledger is untouched when config, forge, intake, or prose cannot be trusted."""
    assert _MODULE_PATH.is_file()
    breakage, runner, _, filed = _configured_pass(monkeypatch=monkeypatch)
    monkeypatch.setattr(breakage, "dispatcher_block", lambda **_: {"breakage_workflows": "no"})
    assert breakage.breakage_pass(repo=Path(), runner=runner).exit_code == 1
    monkeypatch.setattr(breakage, "dispatcher_block", lambda **_: {"breakage_workflows": []})
    assert breakage.breakage_pass(repo=Path(), runner=runner).lines == ()
    monkeypatch.setattr(
        breakage, "dispatcher_block", lambda **_: {"breakage_workflows": ["ci-root-uid.yml"]}
    )
    monkeypatch.setattr(breakage, "resolve_default_branch", lambda **_: None)
    assert "default branch" in breakage.breakage_pass(repo=Path(), runner=runner).lines[0]
    monkeypatch.setattr(breakage, "resolve_default_branch", lambda **_: "master")
    runner.failure = "/runs?"
    assert "workflow runs" in breakage.breakage_pass(repo=Path(), runner=runner).lines[0]
    runner.failure = None
    assert runner.latest_run is not None
    runner.latest_run["conclusion"] = "cancelled"
    assert "not-concluded cancelled" in breakage.breakage_pass(repo=Path(), runner=runner).lines[0]
    runner.latest_run["conclusion"] = "failure"
    runner.jobs = [{"id": None, "name": "bad", "conclusion": "failure", "steps": []}]
    assert "workflow job fields" in breakage.breakage_pass(repo=Path(), runner=runner).lines[0]
    runner.jobs = [{"id": 7, "name": "{{ unsafe }}", "conclusion": "failure", "steps": []}]
    assert "template opener present" in breakage.breakage_pass(repo=Path(), runner=runner).lines[0]
    assert filed == []


def test_the_pass_refuses_a_bad_ledger_or_failed_intake(monkeypatch: Any) -> None:
    """A broken dedupe read or intake route cannot become a partial filing."""
    assert _MODULE_PATH.is_file()
    breakage, runner, _, filed = _configured_pass(monkeypatch=monkeypatch)

    class _UnreadableClient:
        def list_issues(self) -> list[dict[str, object]]:
            raise BeadsCommandError(command="bd", exit_code=1, stderr="down")

    monkeypatch.setattr(breakage, "make_beads_client", lambda **_: _UnreadableClient())
    assert "unreadable ledger" in breakage.breakage_pass(repo=Path(), runner=runner).lines[0]
    _, runner, _, filed = _configured_pass(monkeypatch=monkeypatch)
    runner.jobs = [{"id": 7, "name": "check-types", "conclusion": "failure", "steps": []}]
    monkeypatch.setattr(breakage, "file_captured_work_item", lambda **_: IOFailure("refused"))
    outcome = breakage.breakage_pass(repo=Path(), runner=runner)

    assert outcome.exit_code == 1
    assert "intake could not route" in outcome.lines[0]
    assert filed == []


def test_the_host_timer_installs_a_half_hour_journaled_breakage_pass(tmp_path: Path) -> None:
    """The host installer provisions the cadence and lets systemd retain verdicts."""
    assert (_SERVICE_DIR / "install.sh").is_file()
    assert (_SERVICE_DIR / "breakage-pass.service").is_file()
    timer = (_SERVICE_DIR / "breakage-pass.timer").read_text(encoding="utf-8")
    assert "OnUnitActiveSec=30min" in timer
    assert "Unit=breakage-pass.service" in timer
    assert "Persistent=true" in timer
    assert '"breakage_workflows": ["ci-root-uid.yml"]' in (_ROOT / ".livespec.jsonc").read_text(
        encoding="utf-8"
    )
    wrapper = tmp_path / "with-livespec-env.sh"
    _ = wrapper.write_text('#!/bin/sh\nexec "$@"\n', encoding="utf-8")
    wrapper.chmod(0o755)
    repo = tmp_path / "repo"
    repo.mkdir()

    completed = subprocess.run(
        [str(_SERVICE_DIR / "install.sh"), "--repo", str(repo), "--user", "fabro"],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "DRY_RUN": "1",
            "LIVESPEC_ENV_WRAPPER": str(wrapper),
            "UNIT_DIR": str(tmp_path / "units"),
        },
    )

    assert completed.returncode == 0, completed.stderr
    service = (tmp_path / "units" / "breakage-pass.service").read_text(encoding="utf-8")
    assert service.startswith("[Unit]")
    assert f"ExecStart={wrapper} -- " in service
    assert "dispatcher.py breakage-pass --repo" in service
    assert "StandardOutput=journal" in service
