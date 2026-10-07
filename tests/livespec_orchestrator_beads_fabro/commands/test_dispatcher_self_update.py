"""Tests for release-triggered self-update + canary.

The retired self-merge detector is deliberately absent from this test surface.
The load-bearing safety property remains: a newer released artifact is canaried,
a passing canary surfaces that restart is due, and a failing canary keeps
last-known-good and alarms a human.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_self_update as self_update_module
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_self_update import (
    SELF_UPDATE_BREACH_CLASS,
    CanaryVerdict,
    PromotionDecision,
    canary_self_check_argv,
    canary_verdict,
    candidate_dispatcher_bin,
    promotion_decision,
    self_update_after_verdict,
)


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _QueueRunner:
    results: list[CommandResult]
    seen_argv: list[list[str]] = field(default_factory=list)
    seen_envs: list[dict[str, str] | None] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds)
        self.seen_argv.append(list(argv))
        self.seen_envs.append(env)
        return self.results.pop(0)


@dataclass(kw_only=True)
class _RaisingRunner:
    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env)
        raise RuntimeError("canary subprocess blew up")


@dataclass(kw_only=True)
class _RecordingPoster:
    bodies: list[str] = field(default_factory=list)

    def post(self, *, url: str, body: str, title: str, timeout_seconds: float) -> bool:
        _ = (url, title, timeout_seconds)
        self.bodies.append(body)
        return True


def _outcome(*, status: str, pr_number: int | None = 42) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="livespec-impl-beads-ddu",
        status=status,
        stage="done",
        pr_number=pr_number,
        merge_sha="feed01",
        detail="x",
    )


def _release_update_decision() -> object:
    assert hasattr(self_update_module, "release_update_decision")
    return self_update_module.release_update_decision


def _self_update_after_release() -> object:
    assert hasattr(self_update_module, "self_update_after_release")
    return self_update_module.self_update_after_release


def test_release_update_decision_detects_newer_released_artifact() -> None:
    decision = _release_update_decision()(
        running_release="0.49.5",
        available_release="0.49.6",
    )
    assert decision.update_required is True
    assert "0.49.5" in decision.reason
    assert "0.49.6" in decision.reason


def test_release_update_decision_skips_when_running_release_is_current() -> None:
    decision = _release_update_decision()(
        running_release="0.49.6",
        available_release="0.49.6",
    )
    assert decision.update_required is False
    assert "running release is current" in decision.reason


def test_release_update_decision_records_undetermined_available_release() -> None:
    decision = _release_update_decision()(
        running_release="0.49.6",
        available_release=None,
    )
    assert decision.update_required is False
    assert "available release could not be determined" in decision.reason


def test_release_update_decision_records_undetermined_running_release() -> None:
    decision = _release_update_decision()(
        running_release=None,
        available_release="0.49.6",
    )
    assert decision.update_required is False
    assert "running release could not be determined" in decision.reason


def test_canary_self_check_argv_runs_candidate_ledger_check_against_scratch() -> None:
    argv = canary_self_check_argv(
        candidate_bin="/pin/candidate/bin/dispatcher.py",
        scratch_root="/tmp/canary-scratch",
    )
    assert argv == [
        "python3",
        "/pin/candidate/bin/dispatcher.py",
        "ledger-check",
        "--project-root",
        "/tmp/canary-scratch",
        "--json",
    ]
    assert "fabro" not in argv
    assert "run" not in argv


def test_canary_verdict_pass_on_clean_exit() -> None:
    assert CanaryVerdict.PASS.value == "pass"
    assert canary_verdict(exit_code=0) is CanaryVerdict.PASS


def test_canary_verdict_fail_on_nonzero_exit() -> None:
    assert CanaryVerdict.FAIL.value == "fail"
    assert canary_verdict(exit_code=1) is CanaryVerdict.FAIL


def test_canary_verdict_fail_on_timeout_exit() -> None:
    assert canary_verdict(exit_code=124) is CanaryVerdict.FAIL


def test_promotion_decision_promotes_on_pass_without_alarm() -> None:
    decision = promotion_decision(verdict=CanaryVerdict.PASS)
    assert decision == PromotionDecision(
        promote=False,
        alarm=True,
        reason=decision.reason,
    )
    assert decision.promote is False
    assert decision.alarm is True
    assert "restart is due" in decision.reason


def test_promotion_decision_keeps_and_alarms_on_fail() -> None:
    decision = promotion_decision(verdict=CanaryVerdict.FAIL)
    assert decision.promote is False
    assert decision.alarm is True


def test_candidate_dispatcher_bin_points_at_the_released_payload_bin_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.delenv("LIVESPEC_INSTALLED_PLUGIN_ROOT", raising=False)
    assert (
        candidate_dispatcher_bin().as_posix().endswith(".claude-plugin/scripts/bin/dispatcher.py")
    )


def test_after_release_alarms_restart_due_on_passing_canary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_NTFY_DISPATCHER_TOPIC", "livespec-dispatcher-test")
    journal = _RecordingJournal()
    poster = _RecordingPoster()
    runner = _QueueRunner(
        results=[
            CommandResult(exit_code=0, stdout="[]", stderr=""),
        ],
    )
    _self_update_after_release()(
        work_item_id="livespec-impl-beads-ddu",
        candidate_bin="/pin/candidate/bin/dispatcher.py",
        scratch_root="/tmp/canary-scratch",
        repo=Path("/data/projects/livespec-orchestrator-beads-fabro"),
        journal=journal,
        runner=runner,
        poster=poster,
    )
    assert runner.seen_argv[-1] == canary_self_check_argv(
        candidate_bin="/pin/candidate/bin/dispatcher.py",
        scratch_root="/tmp/canary-scratch",
    )
    stages = [record["stage"] for record in journal.records]
    assert "self-update-restart-due" in stages
    assert "self-update-promoted" not in stages
    assert len(poster.bodies) == 1
    assert "livespec-impl-beads-ddu" in poster.bodies[0]


def test_after_release_keeps_last_known_good_and_alarms_on_failing_canary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_NTFY_DISPATCHER_TOPIC", "livespec-dispatcher-test")
    journal = _RecordingJournal()
    poster = _RecordingPoster()
    runner = _QueueRunner(
        results=[
            CommandResult(exit_code=1, stdout="", stderr="boom"),
        ],
    )
    _self_update_after_release()(
        work_item_id="livespec-impl-beads-ddu",
        candidate_bin="/pin/candidate/bin/dispatcher.py",
        scratch_root="/tmp/canary-scratch",
        repo=Path("/data/projects/livespec-orchestrator-beads-fabro"),
        journal=journal,
        runner=runner,
        poster=poster,
    )
    stages = [record["stage"] for record in journal.records]
    assert "self-update-kept-last-known-good" in stages
    assert "self-update-promoted" not in stages
    assert len(poster.bodies) == 1
    body = poster.bodies[0]
    assert "livespec-impl-beads-ddu" in body
    assert SELF_UPDATE_BREACH_CLASS in body
    assert "/pin/candidate" not in body
    assert "boom" not in body


def test_after_release_is_fail_open_when_the_canary_runner_raises() -> None:
    journal = _RecordingJournal()
    _self_update_after_release()(
        work_item_id="livespec-impl-beads-ddu",
        candidate_bin="/pin/candidate/bin/dispatcher.py",
        scratch_root="/tmp/canary-scratch",
        repo=Path("/data/projects/livespec-orchestrator-beads-fabro"),
        journal=journal,
        runner=_RaisingRunner(),
        poster=_RecordingPoster(),
    )
    assert [record["stage"] for record in journal.records] == ["self-update-error"]


def test_after_verdict_skips_when_no_green_outcomes() -> None:
    journal = _RecordingJournal()
    runner = _QueueRunner(results=[])
    self_update_after_verdict(
        outcomes=[_outcome(status="failed")],
        repo=Path("/repo"),
        journal=journal,
        runner=runner,
        poster=_RecordingPoster(),
    )
    assert runner.seen_argv == []
    assert journal.records == []


def test_after_verdict_uses_release_comparison_not_pr_file_detection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The retired detector is gone: no `gh pr view`, and no in-process promote.

    Sibling of `test_after_verdict_canaries_and_alarms_restart_due_by_default`.
    This one guards the DELETED surface; that one guards against INERTNESS.
    """
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "plugin.json").write_text('{"version": "99.99.99"}', encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin))
    journal = _RecordingJournal()
    runner = _QueueRunner(
        results=[
            CommandResult(exit_code=0, stdout="", stderr=""),
        ]
    )
    self_update_after_verdict(
        outcomes=[_outcome(status="green")],
        repo=Path("/repo"),
        journal=journal,
        runner=runner,
        poster=_RecordingPoster(),
    )

    assert all(argv[:3] != ["gh", "pr", "view"] for argv in runner.seen_argv)
    assert runner.seen_argv[-1] == canary_self_check_argv(
        candidate_bin=str(candidate_dispatcher_bin()),
        scratch_root=runner.seen_argv[-1][4],
    )
    stages = [record["stage"] for record in journal.records]
    assert "self-update-restart-due" in stages
    assert "self-update-promoted" not in stages


def test_after_verdict_canaries_and_alarms_restart_due_by_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """With NO running_release argument, the canary fires and restart-due alarms.

    The default path must not be inert: `running_release` is left at its
    import-time default, so this exercises what production actually runs.
    Asserts `self-update-skipped` is ABSENT — the previous version of this test
    asserted it was PRESENT, encoding the inert behavior as the contract.
    """
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "plugin.json").write_text('{"version": "99.99.99"}', encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin))
    monkeypatch.setenv("CLAUDE_NTFY_DISPATCHER_TOPIC", "livespec-dispatcher-test")
    journal = _RecordingJournal()
    runner = _QueueRunner(results=[CommandResult(exit_code=0, stdout="", stderr="")])
    expected_argv = canary_self_check_argv(
        candidate_bin=str(candidate_dispatcher_bin()),
        scratch_root="placeholder",
    )
    self_update_after_verdict(
        outcomes=[_outcome(status="green")],
        repo=Path("/repo"),
        journal=journal,
        runner=runner,
        poster=_RecordingPoster(),
    )
    assert runner.seen_argv != []
    observed = runner.seen_argv[-1]
    expected_argv[4] = observed[4]
    assert observed == expected_argv
    stages = [record["stage"] for record in journal.records]
    assert "self-update-restart-due" in stages
    assert "self-update-skipped" not in stages


def test_after_verdict_records_undetermined_release_distinctly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path / "missing-plugin"))
    journal = _RecordingJournal()
    runner = _QueueRunner(results=[])
    self_update_after_verdict(
        outcomes=[_outcome(status="green")],
        repo=Path("/repo"),
        journal=journal,
        runner=runner,
        poster=_RecordingPoster(),
    )
    assert runner.seen_argv == []
    assert [record["stage"] for record in journal.records] == ["self-update-release-undetermined"]
    assert "available release could not be determined" in str(journal.records[0]["reason"])


def test_running_release_env_seam_is_absent_from_the_tree() -> None:
    token = "LIVESPEC_DISPATCHER_" + "RUNNING_RELEASE"
    root = Path(__file__).resolve().parents[3]
    matches = [
        path
        for path in root.rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and "__pycache__" not in path.parts
        and ".pytest_cache" not in path.parts
        and ".mypy_cache" not in path.parts
        and token in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert matches == []
