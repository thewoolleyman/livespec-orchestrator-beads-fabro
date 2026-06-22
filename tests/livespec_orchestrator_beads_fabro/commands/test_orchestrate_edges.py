"""Edge coverage for the orchestrate command supervisor."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import orchestrate
from livespec_orchestrator_beads_fabro.commands.orchestrate import CommandRun


class _Runner:
    def __init__(self, *, results: list[CommandRun]) -> None:
        self.results = results
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> CommandRun:
        self.calls.append(argv)
        _ = cwd
        return self.results.pop(0)


@dataclass(frozen=True, kw_only=True)
class _Completed:
    returncode: int
    stdout: str
    stderr: str


def _run(*, stdout: str, returncode: int = 0, stderr: str = "") -> CommandRun:
    return CommandRun(argv=("cmd",), returncode=returncode, stdout=stdout, stderr=stderr)


def test_plan_records_failed_next_sources(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(
        results=[
            _run(stdout="", returncode=3, stderr="spec failed"),
            _run(stdout="", returncode=2, stderr="impl failed"),
        ]
    )

    plan = orchestrate.plan_actions(repo=repo, runner=runner)

    assert plan["actions"] == []
    assert plan["sources"]["spec_next"]["status"] == "failed"
    assert plan["sources"]["spec_next"]["stderr"] == "spec failed"
    assert plan["sources"]["impl_next"]["status"] == "failed"


def test_plan_records_malformed_next_outputs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(
        results=[
            _run(stdout="not json"),
            _run(stdout=json.dumps({"candidates": "not-a-list"})),
        ]
    )

    plan = orchestrate.plan_actions(repo=repo, runner=runner)

    assert plan["actions"] == []
    assert plan["sources"]["spec_next"]["stderr"] == "next output was not a JSON object"
    assert plan["sources"]["impl_next"]["stderr"] == "next output did not include candidates[]"


def test_plan_uses_explicit_next_bins(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    spec_bin = tmp_path / "spec-next.py"
    impl_bin = tmp_path / "impl-next.py"
    runner = _Runner(
        results=[
            _run(stdout=json.dumps({"candidates": []})),
            _run(stdout=json.dumps({"candidates": []})),
        ]
    )

    _ = orchestrate.plan_actions(
        repo=repo,
        runner=runner,
        spec_next_bin=spec_bin,
        impl_next_bin=impl_bin,
    )

    assert runner.calls[0][1] == str(spec_bin)
    assert runner.calls[1][1] == str(impl_bin)


def test_plan_uses_spec_next_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    spec_bin = tmp_path / "env-spec-next.py"
    monkeypatch.setenv("LIVESPEC_SPEC_NEXT_BIN", str(spec_bin))
    runner = _Runner(
        results=[
            _run(stdout=json.dumps({"candidates": []})),
            _run(stdout=json.dumps({"candidates": []})),
        ]
    )

    _ = orchestrate.plan_actions(repo=repo, runner=runner)

    assert runner.calls[0][1] == str(spec_bin)


def test_run_action_rejects_unknown_action(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = orchestrate.run_action(repo=repo, action_id="bogus", runner=_Runner(results=[]))

    assert result["status"] == "failed"
    assert result["kind"] == "unknown"


def test_run_action_defaults_spec_handoff_when_action_missing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = orchestrate.run_action(repo=repo, action_id="spec:", runner=_Runner(results=[]))

    assert result["handoff"] == "/livespec:next --spec-target SPECIFICATION/"


def test_run_action_reports_blocked_dispatch_with_default_dispatcher(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(results=[_run(stdout=json.dumps([{"status": "blocked"}]), returncode=1)])

    result = orchestrate.run_action(repo=repo, action_id="impl:bd-ib-123", runner=runner)

    assert result["status"] == "blocked"
    assert "human-gated blocked" in result["summary"]
    assert runner.calls[0][1].endswith("/bin/dispatcher.py")


def test_run_action_falls_back_to_failed_for_bad_dispatch_output(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(results=[_run(stdout="not json", returncode=1)])

    result = orchestrate.run_action(repo=repo, action_id="impl:bd-ib-123", runner=runner)

    assert result["status"] == "failed"
    assert "did not report green" in result["summary"]


def test_run_action_falls_back_to_green_for_missing_status(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(results=[_run(stdout=json.dumps([{}]))])

    result = orchestrate.run_action(repo=repo, action_id="impl:bd-ib-123", runner=runner)

    assert result["status"] == "green"


def test_run_action_ignores_non_dict_dispatch_entries(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(results=[_run(stdout=json.dumps([1]), returncode=1)])

    result = orchestrate.run_action(repo=repo, action_id="impl:bd-ib-123", runner=runner)

    assert result["status"] == "failed"


def test_main_missing_repo_returns_precondition(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "missing"

    exit_code = orchestrate.main(["plan", "--repo", str(missing), "--json"])

    assert exit_code == 3
    assert "does not exist" in capsys.readouterr().err


def test_main_plan_human_output_lists_actions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(
        results=[
            _run(stdout=json.dumps({"candidates": []})),
            _run(
                stdout=json.dumps(
                    {"candidates": [{"work_item_ref": "bd-ib-123", "reason": "ready"}]}
                )
            ),
        ]
    )

    exit_code = orchestrate.main(["plan", "--repo", str(repo)], runner=runner)

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "impl:bd-ib-123"


def test_main_plan_human_output_handles_empty_plan(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(
        results=[
            _run(stdout=json.dumps({"candidates": []})),
            _run(stdout=json.dumps({"candidates": []})),
        ]
    )

    exit_code = orchestrate.main(["plan", "--repo", str(repo)], runner=runner)

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "No actions ready."


def test_main_run_returns_exit_failure_for_failed_dispatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(results=[_run(stdout="not json", returncode=1)])

    exit_code = orchestrate.main(
        ["run", "--repo", str(repo), "--action", "impl:bd-ib-123"],
        runner=runner,
    )

    assert exit_code == 1
    assert "did not report green" in capsys.readouterr().out


def test_main_run_json_returns_success_for_human_gated_spec(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    exit_code = orchestrate.main(
        ["run", "--repo", str(repo), "--action", "spec:unknown:0", "--json"],
        runner=_Runner(results=[]),
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["handoff"] == (
        "/livespec:next --spec-target SPECIFICATION/"
    )


def test_plan_without_injected_runner_uses_subprocess_runner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    calls: list[tuple[object, ...]] = []

    def fake_run(*args: object, **kwargs: object) -> _Completed:
        calls.append(args)
        assert kwargs["cwd"] == repo
        assert kwargs["check"] is False
        assert kwargs["capture_output"] is True
        return _Completed(returncode=0, stdout=json.dumps({"candidates": []}), stderr="")

    monkeypatch.setattr(orchestrate.subprocess, "run", fake_run)

    plan = orchestrate.plan_actions(repo=repo)

    assert plan["actions"] == []
    assert len(calls) == 2
