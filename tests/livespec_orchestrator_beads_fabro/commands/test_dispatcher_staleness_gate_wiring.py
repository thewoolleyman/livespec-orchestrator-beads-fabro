"""Side-effect coverage for the dispatcher staleness gate."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_selection
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_staleness_gate import (
    apply_dispatcher_staleness_gate,
    dispatcher_staleness_decision,
    latest_release_ref_argv,
    master_ref_argv,
    release_comparison_argv,
    unreleased_dispatcher_commits_argv,
)

_RELEASE_SHA = "9532efb793bc1d2c3a4b5c6d7e8f901234567890"
_MASTER_SHA = "8eb81fae1234567890abcdefabcdefabcdefabcd"


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
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env)
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


def test_apply_gate_records_ambient_lag_without_a_precondition_exit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The `dispatcher-staleness-refused` record this gate used to write is gone.

    Its exit-3 return is now reachable ONLY through a committed
    `dispatcher.minimum_release` floor, so a build behind the live release head
    journals a non-blocking record and dispatch continues.
    """
    cache_root = tmp_path / "b6e4012cafed"
    cache_root.mkdir()
    journal = _Journal()
    runner = _Runner(
        results={
            latest_release_ref_argv(): _ls_remote(ref="refs/heads/release", sha=_RELEASE_SHA),
            master_ref_argv(): _ls_remote(ref="refs/heads/master", sha=_RELEASE_SHA),
            release_comparison_argv(
                release_sha=_RELEASE_SHA,
                build_id="b6e4012cafed",
            ): CommandResult(exit_code=0, stdout="behind\n", stderr=""),
        }
    )

    exit_code = apply_dispatcher_staleness_gate(
        plugin_root=cache_root,
        journal=journal,
        runner=runner,
        cwd=tmp_path,
    )

    assert exit_code is None
    assert journal.records == [
        {
            "stage": "dispatcher-staleness-warning",
            "detail": journal.records[0]["detail"],
            "blocking": False,
        }
    ]
    assert "b6e4012cafed" in str(journal.records[0]["detail"])
    assert "b6e4012cafed" in capsys.readouterr().err


def test_apply_gate_records_warning_and_proceeds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cache_root = tmp_path / _RELEASE_SHA[:12]
    cache_root.mkdir()
    journal = _Journal()
    runner = _Runner(
        results={
            latest_release_ref_argv(): _ls_remote(ref="refs/heads/release", sha=_RELEASE_SHA),
            master_ref_argv(): _ls_remote(ref="refs/heads/master", sha=_MASTER_SHA),
            unreleased_dispatcher_commits_argv(
                release_sha=_RELEASE_SHA,
                master_sha=_MASTER_SHA,
            ): CommandResult(exit_code=1, stdout="", stderr="no local refs"),
        }
    )

    exit_code = apply_dispatcher_staleness_gate(
        plugin_root=cache_root,
        journal=journal,
        runner=runner,
        cwd=tmp_path,
    )

    assert exit_code is None
    assert journal.records == [
        {
            "stage": "dispatcher-staleness-warning",
            "detail": journal.records[0]["detail"],
            "blocking": False,
        }
    ]
    assert _MASTER_SHA[:12] in str(journal.records[0]["detail"])
    assert "a release must be cut before this code takes effect" in capsys.readouterr().err


def test_git_checkout_head_matching_release_proceeds_without_warning(tmp_path: Path) -> None:
    plugin_root = tmp_path / "checkout"
    plugin_root.mkdir()
    runner = _Runner(
        results={
            latest_release_ref_argv(): _ls_remote(ref="refs/heads/release", sha=_RELEASE_SHA),
            (
                "git",
                "-C",
                str(plugin_root),
                "rev-parse",
                "HEAD",
            ): CommandResult(exit_code=0, stdout=f"{_RELEASE_SHA}\n", stderr=""),
            master_ref_argv(): _ls_remote(ref="refs/heads/master", sha=_RELEASE_SHA),
        }
    )

    decision = dispatcher_staleness_decision(plugin_root=plugin_root, runner=runner, cwd=tmp_path)

    assert decision.refusal is None
    assert decision.warnings == ()


def test_unknown_short_cache_name_warns_and_proceeds_without_network(tmp_path: Path) -> None:
    """An unestablishable build identity NEVER refuses (bd-ib-n7ce4n deadlock case)."""
    plugin_root = tmp_path / "short"
    plugin_root.mkdir()
    runner = _Runner(
        results={
            latest_release_ref_argv(): _ls_remote(ref="refs/heads/release", sha=_RELEASE_SHA),
            master_ref_argv(): _ls_remote(ref="refs/heads/master", sha=_RELEASE_SHA),
        }
    )

    decision = dispatcher_staleness_decision(plugin_root=plugin_root, runner=runner, cwd=tmp_path)

    assert decision.refusal is None
    assert len(decision.warnings) == 1
    assert "could not establish the executing build identity" in decision.warnings[0].detail
    assert latest_release_ref_argv() not in runner.calls
    assert master_ref_argv() not in runner.calls


def test_prepare_returns_none_when_staleness_gate_refuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    workflow = repo / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("[workflow]\n", encoding="utf-8")
    monkeypatch.setattr(
        _dispatcher_loop_selection,
        "apply_dispatcher_staleness_gate",
        lambda **_: 3,
    )

    prepared = _dispatcher_loop_selection.prepare(
        args=argparse.Namespace(workflow=str(workflow), journal=None, repo=str(repo)),
        repo=repo,
    )

    assert prepared is None
