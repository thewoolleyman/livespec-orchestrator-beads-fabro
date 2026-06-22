"""Tests for the minimal orchestrate operator surface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands.orchestrate import (
    CommandRun,
    build_dispatcher_argv,
    main,
    plan_actions,
    run_action,
)


class _Runner:
    def __init__(self, *, results: list[CommandRun]) -> None:
        self.results = results
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> CommandRun:
        self.calls.append(argv)
        _ = cwd
        return self.results.pop(0)


def _ok(payload: object, *, argv: tuple[str, ...] = ("cmd",)) -> CommandRun:
    return CommandRun(argv=argv, returncode=0, stdout=json.dumps(payload), stderr="")


def test_plan_actions_composes_spec_and_impl_next_candidates(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(
        results=[
            _ok(
                {
                    "candidates": [
                        {
                            "action": "revise",
                            "urgency": "high",
                            "reason": "pending proposal",
                            "target": "proposed_changes/a.md",
                        }
                    ]
                }
            ),
            _ok(
                {
                    "candidates": [
                        {
                            "action": "implement",
                            "work_item_ref": "bd-ib-123",
                            "urgency": "medium",
                            "reason": "ready item",
                        }
                    ]
                }
            ),
        ]
    )

    plan = plan_actions(repo=repo, runner=runner)

    assert [action["id"] for action in plan["actions"]] == [
        "spec:revise:0",
        "impl:bd-ib-123",
    ]
    assert plan["summary"] == {
        "spec_actions": 1,
        "impl_actions": 1,
        "total_actions": 2,
    }
    assert plan["actions"][0]["handoff"] == "/livespec:revise --spec-target SPECIFICATION/"
    assert plan["actions"][1]["factory_safe"] is True


def test_plan_actions_surfaces_spec_only_candidates(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(
        results=[
            _ok({"candidates": [{"action": "critique", "urgency": "low", "reason": "hygiene"}]}),
            _ok({"candidates": []}),
        ]
    )

    plan = plan_actions(repo=repo, runner=runner)

    assert [action["kind"] for action in plan["actions"]] == ["spec"]
    assert plan["summary"]["impl_actions"] == 0


def test_build_dispatcher_argv_uses_shadow_loop_for_selected_impl_item(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    dispatcher_bin = tmp_path / "dispatcher.py"

    argv = build_dispatcher_argv(
        repo=repo,
        dispatcher_bin=dispatcher_bin,
        work_item_ref="bd-ib-123",
    )

    assert argv == (
        "python3",
        str(dispatcher_bin),
        "loop",
        "--repo",
        str(repo),
        "--budget",
        "1",
        "--parallel",
        "1",
        "--mode",
        "shadow",
        "--item",
        "bd-ib-123",
        "--json",
    )


def test_run_action_dispatches_selected_impl_item(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    dispatcher_bin = tmp_path / "dispatcher.py"
    runner = _Runner(results=[_ok([{"work_item_id": "bd-ib-123", "status": "green"}])])

    result = run_action(
        repo=repo,
        action_id="impl:bd-ib-123",
        runner=runner,
        dispatcher_bin=dispatcher_bin,
    )

    assert result["status"] == "green"
    assert result["kind"] == "impl"
    assert result["work_item_ref"] == "bd-ib-123"
    assert runner.calls == [
        build_dispatcher_argv(
            repo=repo,
            dispatcher_bin=dispatcher_bin,
            work_item_ref="bd-ib-123",
        )
    ]


def test_run_action_surfaces_spec_actions_as_human_handoff(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(results=[])

    result = run_action(repo=repo, action_id="spec:revise:0", runner=runner)

    assert result["status"] == "human-gated"
    assert result["handoff"] == "/livespec:revise --spec-target SPECIFICATION/"
    assert runner.calls == []


def test_main_plan_emits_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = _Runner(results=[_ok({"candidates": []}), _ok({"candidates": []})])

    exit_code = main(["plan", "--repo", str(repo), "--json"], runner=runner)

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["actions"] == []
