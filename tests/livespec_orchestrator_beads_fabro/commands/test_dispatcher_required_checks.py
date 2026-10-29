"""Tests for the forge read of which checks a pull request requires."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_required_checks import (
    parse_required_check_names,
    required_check_names,
    required_check_names_argv,
)

_DECLARED_CONFIG = '{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}'


@dataclass(kw_only=True)
class _Runner:
    result: CommandResult
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        assert timeout_seconds > 0
        assert cwd.is_absolute()
        assert env is None
        self.calls.append(argv)
        return self.result


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _answer(*, nodes: object) -> str:
    rollup = {"contexts": {"nodes": nodes}}
    pull_request = {"commits": {"nodes": [{"commit": {"statusCheckRollup": rollup}}]}}
    return json.dumps({"data": {"repository": {"pullRequest": pull_request}}})


def test_argv_asks_the_forge_for_is_required_of_this_pull_request() -> None:
    argv = required_check_names_argv(number=3913)

    assert argv[:3] == ["gh", "api", "graphql"]
    assert "number=3913" in argv
    assert "owner=:owner" in argv
    assert "name=:repo" in argv
    assert any("isRequired(pullRequestNumber: $number)" in part for part in argv)


def test_parse_returns_only_the_contexts_flagged_required() -> None:
    nodes = [
        {"__typename": "CheckRun", "name": "ci-green", "isRequired": True},
        {"__typename": "CheckRun", "name": "check-lint (root)", "isRequired": False},
        {"__typename": "StatusContext", "context": "legacy/status", "isRequired": True},
        {"__typename": "CheckRun", "name": "", "isRequired": True},
        {"__typename": "CheckRun", "isRequired": True},
        "not-a-node",
    ]

    assert parse_required_check_names(stdout=_answer(nodes=nodes)) == frozenset(
        {"ci-green", "legacy/status"}
    )


def test_parse_reports_an_empty_set_when_nothing_is_required() -> None:
    assert parse_required_check_names(stdout=_answer(nodes=[])) == frozenset()


def test_parse_reports_none_for_every_unexpected_shape() -> None:
    assert parse_required_check_names(stdout="not json") is None
    assert parse_required_check_names(stdout="[]") is None
    assert parse_required_check_names(stdout=json.dumps({"data": None})) is None
    no_commits = {"data": {"repository": {"pullRequest": {"commits": {"nodes": []}}}}}
    assert parse_required_check_names(stdout=json.dumps(no_commits)) is None
    no_rollup = {"data": {"repository": {"pullRequest": {"commits": {"nodes": [{"commit": {}}]}}}}}
    assert parse_required_check_names(stdout=json.dumps(no_rollup)) is None
    assert parse_required_check_names(stdout=_answer(nodes="oops")) is None


def _plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id="x-1",
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        config_text=_DECLARED_CONFIG,
        default_branch="master",
    )


def test_required_check_names_journals_the_read_and_returns_the_names(tmp_path: Path) -> None:
    runner = _Runner(
        result=CommandResult(
            exit_code=0,
            stdout=_answer(nodes=[{"name": "ci-green", "isRequired": True}]),
            stderr="",
        )
    )
    journal = _Journal()

    names = required_check_names(
        plan=_plan(repo=tmp_path), number=7, runner=runner, journal=journal
    )

    assert names == frozenset({"ci-green"})
    assert runner.calls[0][:3] == ["gh", "api", "graphql"]
    assert [record["stage"] for record in journal.records] == ["required-checks"]


def test_required_check_names_is_none_when_the_forge_read_fails(tmp_path: Path) -> None:
    runner = _Runner(result=CommandResult(exit_code=1, stdout="", stderr="boom"))

    names = required_check_names(
        plan=_plan(repo=tmp_path), number=7, runner=runner, journal=_Journal()
    )

    assert names is None
