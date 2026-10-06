"""Wiring of the registered-install currency finding into the staleness gate (bd-ib-h3mm)."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_selection
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_staleness_gate import (
    CURRENCY_UNDETERMINED_STAGE,
    MINIMUM_RELEASE_REFUSED_STAGE,
    REGISTERED_INSTALL_LAG_STAGE,
    apply_dispatcher_staleness_gate,
    dispatcher_staleness_decision,
    latest_release_ref_argv,
    master_ref_argv,
)

_RELEASE_SHA = "9532efb793bc1d2c3a4b5c6d7e8f901234567890"
_PLUGIN_KEY = "livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"


@dataclass(kw_only=True)
class _Runner:
    results: dict[tuple[str, ...], CommandResult]
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        key = tuple(argv)
        self.calls.append(key)
        return self.results.get(key, CommandResult(exit_code=1, stdout="", stderr="missing"))


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _ls_remote(*, ref: str, sha: str) -> CommandResult:
    return CommandResult(exit_code=0, stdout=f"{sha}\t{ref}\n", stderr="")


def _current_release_runner() -> _Runner:
    return _Runner(
        results={
            latest_release_ref_argv(): _ls_remote(ref="refs/heads/release", sha=_RELEASE_SHA),
            master_ref_argv(): _ls_remote(ref="refs/heads/master", sha=_RELEASE_SHA),
        }
    )


def _build(*, root: Path, version: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _ = (root / "plugin.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    return root


def _registry(*, tmp_path: Path, repo: Path, registered: Path) -> Path:
    record = tmp_path / "installed_plugins.json"
    _ = record.write_text(
        json.dumps(
            {"plugins": {_PLUGIN_KEY: [{"projectPath": str(repo), "installPath": str(registered)}]}}
        ),
        encoding="utf-8",
    )
    return record


def test_gate_journals_registered_install_lag_without_refusing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The stale-session finding rides the gate as a NON-BLOCKING record of its own stage."""
    executing = _build(root=tmp_path / _RELEASE_SHA[:12], version="0.124.1")
    registered = _build(root=tmp_path / "6edebb0b0c50", version="0.129.1")
    record = _registry(tmp_path=tmp_path, repo=tmp_path, registered=registered)
    journal = _Journal()

    exit_code = apply_dispatcher_staleness_gate(
        plugin_root=executing,
        executing_payload=executing,
        journal=journal,
        runner=_current_release_runner(),
        cwd=tmp_path,
        install_record=record,
    )

    assert exit_code is None
    assert [record["stage"] for record in journal.records] == [REGISTERED_INSTALL_LAG_STAGE]
    assert journal.records[0]["blocking"] is False
    assert "Restart the session" in str(journal.records[0]["detail"])
    assert "0.124.1" in capsys.readouterr().err


def test_registered_install_warning_follows_the_ambient_release_warnings(tmp_path: Path) -> None:
    executing = _build(root=tmp_path / "b6e4012cafed", version="0.124.1")
    registered = _build(root=tmp_path / "6edebb0b0c50", version="0.129.1")
    record = _registry(tmp_path=tmp_path, repo=tmp_path, registered=registered)

    decision = dispatcher_staleness_decision(
        plugin_root=executing,
        executing_payload=executing,
        runner=_current_release_runner(),
        cwd=tmp_path,
        install_record=record,
    )

    assert decision.refusal is None
    assert [warning.stage for warning in decision.warnings] == [
        "dispatcher-staleness-warning",
        REGISTERED_INSTALL_LAG_STAGE,
    ]


def test_unreadable_registry_is_journaled_undetermined(tmp_path: Path) -> None:
    executing = _build(root=tmp_path / _RELEASE_SHA[:12], version="0.124.1")

    decision = dispatcher_staleness_decision(
        plugin_root=executing,
        executing_payload=executing,
        runner=_current_release_runner(),
        cwd=tmp_path,
        install_record=tmp_path / "absent.json",
    )

    assert decision.refusal is None
    assert [warning.stage for warning in decision.warnings] == [CURRENCY_UNDETERMINED_STAGE]
    assert "no registered install" in decision.warnings[0].detail


def test_current_registered_install_adds_nothing(tmp_path: Path) -> None:
    executing = _build(root=tmp_path / _RELEASE_SHA[:12], version="0.129.1")
    record = _registry(tmp_path=tmp_path, repo=tmp_path, registered=executing)

    decision = dispatcher_staleness_decision(
        plugin_root=executing,
        executing_payload=executing,
        runner=_current_release_runner(),
        cwd=tmp_path,
        install_record=record,
    )

    assert decision.warnings == ()


def test_without_an_install_record_the_registry_is_not_consulted(tmp_path: Path) -> None:
    executing = _build(root=tmp_path / _RELEASE_SHA[:12], version="0.124.1")

    decision = dispatcher_staleness_decision(
        plugin_root=executing, runner=_current_release_runner(), cwd=tmp_path
    )

    assert decision.warnings == ()


def test_a_floor_refusal_is_returned_before_the_registry_is_read(tmp_path: Path) -> None:
    executing = _build(root=tmp_path / _RELEASE_SHA[:12], version="0.124.1")
    registered = _build(root=tmp_path / "6edebb0b0c50", version="0.129.1")
    record = _registry(tmp_path=tmp_path, repo=tmp_path, registered=registered)
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {"livespec-orchestrator-beads-fabro": {"dispatcher": {"minimum_release": "0.129.0"}}}
        ),
        encoding="utf-8",
    )

    decision = dispatcher_staleness_decision(
        plugin_root=executing,
        executing_payload=executing,
        runner=_current_release_runner(),
        cwd=tmp_path,
        install_record=record,
    )

    assert decision.refusal is not None
    assert decision.refusal.stage == MINIMUM_RELEASE_REFUSED_STAGE
    assert decision.warnings == ()


def test_prepare_passes_the_host_install_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    workflow = repo / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"
    workflow.parent.mkdir(parents=True)
    _ = workflow.write_text("[workflow]\n", encoding="utf-8")
    seen: dict[str, object] = {}

    def _capture(**kwargs: object) -> int:
        seen.update(kwargs)
        return 3

    monkeypatch.setattr(_dispatcher_loop_selection, "apply_dispatcher_staleness_gate", _capture)

    prepared = _dispatcher_loop_selection.prepare(
        args=argparse.Namespace(workflow=str(workflow), journal=None, repo=str(repo)),
        repo=repo,
    )

    assert prepared is None
    install_record = seen["install_record"]
    assert isinstance(install_record, Path)
    assert install_record.name == "installed_plugins.json"
    assert install_record.parent.name == "plugins"
