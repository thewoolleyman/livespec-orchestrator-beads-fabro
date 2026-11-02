"""Coverage for the concluded-green-ancestor master-CI lookup."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_pipeline_view import (
    MasterCiPipeline,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_preflight_ancestors import (
    green_ancestor,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_REPO = Path("/repo")
_PIPELINE = MasterCiPipeline(workflow="CI", job="ci-green", resolution="default", defect=None)


@dataclass(kw_only=True)
class _Runner:
    answers: dict[tuple[str, ...], CommandResult]
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        key = tuple(argv)
        self.calls.append(key)
        return self.answers.get(key, CommandResult(exit_code=1, stdout="", stderr="unscripted"))


def _result(*, exit_code: int = 0, stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=exit_code, stdout=stdout, stderr="")


def _recent(*, payload: object, exit_code: int = 0) -> tuple[tuple[str, ...], CommandResult]:
    return (
        (
            "gh",
            "run",
            "list",
            "--branch",
            "trunk",
            "--limit",
            "100",
            "--workflow",
            "CI",
            "--json",
            "databaseId,headSha,status,conclusion,createdAt",
        ),
        _result(exit_code=exit_code, stdout=json.dumps(payload)),
    )


def _run(
    *, run_id: int = 2, head: str = "green", created: str = "2026-11-02T07:00:00Z"
) -> dict[str, object]:
    return {"databaseId": run_id, "headSha": head, "status": "completed", "createdAt": created}


def _view(
    *, run_id: int = 2, conclusion: str | None = "success", exit_code: int = 0
) -> tuple[tuple[str, ...], CommandResult]:
    jobs: list[object] = (
        [] if conclusion is None else [{"name": "ci-green", "conclusion": conclusion}]
    )
    return (
        ("gh", "run", "view", str(run_id), "--json", "jobs"),
        _result(exit_code=exit_code, stdout=json.dumps({"jobs": jobs})),
    )


def _compare(*, status: str = "ahead", exit_code: int = 0) -> tuple[tuple[str, ...], CommandResult]:
    return (
        ("gh", "api", "repos/{owner}/{repo}/compare/green...trunk", "--jq", ".status"),
        _result(exit_code=exit_code, stdout=status),
    )


def _answer(*pairs: tuple[tuple[str, ...], CommandResult]) -> _Runner:
    return _Runner(answers=dict(pairs))


def _read(*, runner: _Runner) -> tuple[str, str] | None:
    return green_ancestor(
        repo=_REPO, runner=runner, pipeline=_PIPELINE, branch="trunk", pending_run_id="303"
    )


def test_the_newest_green_ancestor_is_selected_by_creation_time() -> None:
    runner = _answer(
        _recent(
            payload=[
                _run(run_id=2, created="2026-11-02T07:00:00Z"),
                _run(run_id=3, head="old", created="2026-11-02T06:00:00Z"),
            ]
        ),
        _view(),
        _compare(),
    )

    assert _read(runner=runner) == ("2", "green")


@pytest.mark.parametrize(
    ("recent", "view", "comparison"),
    [
        (_recent(payload=[]), None, None),
        (_recent(payload=[], exit_code=1), None, None),
        (_recent(payload={}), None, None),
        (_recent(payload=["bad"]), None, None),
        (
            (_recent(payload=[])[0], _result(stdout="not json")),
            None,
            None,
        ),
        (_recent(payload=[{"createdAt": ""}]), None, None),
        (_recent(payload=[_run()]), _view(exit_code=1), None),
        (
            _recent(payload=[_run()]),
            (("gh", "run", "view", "2", "--json", "jobs"), _result(stdout="[]")),
            None,
        ),
        (
            _recent(payload=[_run()]),
            (("gh", "run", "view", "2", "--json", "jobs"), _result(stdout="not json")),
            None,
        ),
        (_recent(payload=[_run()]), _view(conclusion=None), None),
        (_recent(payload=[_run()]), _view(conclusion="cancelled"), None),
        (_recent(payload=[_run()]), _view(conclusion="failure"), None),
        (_recent(payload=[_run()]), _view(), _compare(status="behind")),
        (_recent(payload=[_run()]), _view(), _compare(status="unknown")),
        (_recent(payload=[_run()]), _view(), _compare(exit_code=1)),
    ],
)
def test_unusable_or_non_green_ancestor_evidence_never_passes(
    recent: tuple[tuple[str, ...], CommandResult],
    view: tuple[tuple[str, ...], CommandResult] | None,
    comparison: tuple[tuple[str, ...], CommandResult] | None,
) -> None:
    pairs = [recent]
    if view is not None:
        pairs.append(view)
    if comparison is not None:
        pairs.append(comparison)

    assert _read(runner=_answer(*pairs)) is None
