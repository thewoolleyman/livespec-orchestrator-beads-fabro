"""Scenario 171 through the Dispatcher, store, preflight, and journal seams.

The four journeys here deliberately drive ``dispatcher.main`` instead of the
waiting helper directly.  A pending default-branch run is only useful evidence
when the preflight keeps the item unclaimed, chooses a newer run on a later
poll, and writes the outcome the operator and later dispatches will read.
"""

from __future__ import annotations

import io
import json
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_loop,
    _dispatcher_step_gate,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_preflight_wait import (
    MasterCiWait,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_BRANCH = "trunk"
_WORKFLOW = "build.yml"
_JOB = "all-green"
_PRECONDITION_ERROR = 3
_WORKFLOW_TOML = '[workflow]\ngraph = "graph.toml"\n\n[run.environment]\nid = "fabro-sandbox"\n'
_GRAPH_TOML = (
    "digraph ImplementWorkItem {\n"
    '    graph [stall_timeout="7200s"]\n'
    '    implement [timeout="1800s"]\n'
    "}\n"
)
_FLEET_MANIFEST = '{"owner":"thewoolleyman","members":[{"repo":"repo","class":"impl-plugin"}]}'


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> object:
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path_factory.mktemp("scenario171")))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_INVOKER", "session:scenario171")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST,
    )
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass(kw_only=True)
class _Clock:
    elapsed: float = 0.0
    pauses: list[float] = field(default_factory=list)

    def now(self) -> float:
        return self.elapsed

    def sleep(self, seconds: float) -> None:
        self.pauses.append(seconds)
        self.elapsed += seconds


@dataclass(kw_only=True)
class _PreflightRunner:
    polls: list[list[dict[str, str]]]
    conclusions: dict[str, str]
    poll_index: int = 0
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
        self.calls.append(tuple(argv))
        if argv[:2] == ["git", "symbolic-ref"] or argv[:2] == ["git", "for-each-ref"]:
            answer = _ok(stdout=f"origin/{_BRANCH}\n")
        elif argv[:3] == ["git", "rev-parse", "--is-inside-work-tree"]:
            answer = _ok(stdout="true\n")
        elif argv[:2] == ["git", "rev-parse"]:
            answer = _ok(stdout="abc1234\n")
        elif argv[:2] == ["git", "merge-base"]:
            answer = _ok()
        elif argv[:3] == ["gh", "run", "list"]:
            answer = self._run_list()
        elif argv[:3] == ["gh", "run", "view"]:
            answer = self._run_view(run_id=argv[3])
        elif argv[:3] == ["gh", "auth", "token"]:
            answer = _ok(stdout="secret\n")
        else:
            answer = CommandResult(exit_code=1, stdout="", stderr="unscripted command")
        return answer

    def _run_list(self) -> CommandResult:
        index = min(self.poll_index, len(self.polls) - 1)
        self.poll_index += 1
        return _ok(stdout=json.dumps(self.polls[index]))

    def _run_view(self, *, run_id: str) -> CommandResult:
        return _ok(
            stdout=json.dumps(
                {
                    "jobs": [
                        {
                            "name": _JOB,
                            "status": "completed",
                            "conclusion": self.conclusions[run_id],
                        }
                    ]
                }
            )
        )

    def viewed_runs(self) -> list[str]:
        return [call[3] for call in self.calls if call[:3] == ("gh", "run", "view")]


@dataclass(kw_only=True)
class _RecordingRunDispatch:
    calls: list[str] = field(default_factory=list)

    def __call__(self, **kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        self.calls.append(plan.work_item_id)
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="green",
            stage="done",
            pr_number=7,
            merge_sha="abc123",
            detail="merged",
        )


def _ok(*, stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item() -> WorkItem:
    return replace(
        WorkItem(
            id="livespec-impl-beads-s171",
            type="task",
            status="ready",
            title="Scenario 171 dispatch fixture",
            description=(
                "Do the thing.\n\n## Definition of Done\n\n- The slice lands.\n\n"
                "References: ## Effective acceptance criteria\n"
            ),
            origin="freeform",
            gap_id=None,
            rank="a2",
            assignee=None,
            depends_on=(),
            captured_at="2026-10-25T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
            admission_policy="auto",
            acceptance_policy="ai-only",
            acceptance_criteria="The slice is verified green by the check suite.",
        )
    )


def _repo(*, tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    config = {
        "git_author": {
            "operator_name": "Chad Woolley",
            "operator_email": "thewoolleyman@gmail.com",
        },
        "livespec-orchestrator-beads-fabro": {
            "connection": {"prefix": "bd-ib"},
            "dispatcher": {"master_ci": {"workflow": _WORKFLOW, "job": _JOB}},
        },
    }
    _ = (repo / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")
    workflow = tmp_path / "workflow.toml"
    _ = workflow.write_text(_WORKFLOW_TOML, encoding="utf-8")
    _ = (tmp_path / "graph.toml").write_text(_GRAPH_TOML, encoding="utf-8")
    return repo, workflow


def _dispatch(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner: _PreflightRunner,
    bound_seconds: float,
) -> tuple[int, Path, _RecordingRunDispatch, _Clock, io.StringIO]:
    repo, workflow = _repo(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    clock = _Clock()
    progress = io.StringIO()
    wait = MasterCiWait(
        now=clock.now,
        sleep=clock.sleep,
        progress=progress,
        bound_seconds=bound_seconds,
    )
    recording = _RecordingRunDispatch()
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", recording)
    monkeypatch.setattr(_dispatcher_step_gate, "ShellCommandRunner", lambda: runner)
    monkeypatch.setattr(
        _dispatcher_step_gate,
        "master_ci_wait",
        lambda *, waived: _test_wait(waived=waived, wait=wait),
    )
    exit_code = main(
        argv=[
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            item.id,
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )
    return exit_code, repo, recording, clock, progress


def _master_ci_record(*, repo: Path) -> dict[str, object]:
    journal = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    records = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    matches = [record for record in records if record["stage"] == "master-ci-preflight"]
    assert len(matches) == 1
    return matches[0]


def _stored_item() -> dict[str, object]:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client.show_issue(issue_id="livespec-impl-beads-s171")


def test_scenario171_pending_master_ci_green_within_bound_dispatches_and_journals_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _PreflightRunner(
        polls=[
            [_run(run_id="green", status="in_progress")],
            [_run(run_id="green", status="completed")],
        ],
        conclusions={"green": "success"},
    )

    exit_code, repo, dispatched, clock, progress = _dispatch(
        tmp_path=tmp_path, monkeypatch=monkeypatch, runner=runner, bound_seconds=120.0
    )

    assert exit_code == 0
    assert dispatched.calls == ["livespec-impl-beads-s171"]
    assert clock.pauses == [60.0]
    assert "run green is in_progress" in progress.getvalue()
    record = _master_ci_record(repo=repo)
    assert record["status"] == "passed"
    assert record["reason"] == "master-ci-green"
    assert record["run_database_id"] == "green"
    assert runner.run(argv=["gh", "auth", "token"], cwd=repo, timeout_seconds=30.0).exit_code == 0
    assert runner.run(argv=["unplanned"], cwd=repo, timeout_seconds=30.0).exit_code == 1


def test_scenario171_pending_master_ci_red_within_bound_refuses_naming_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = _PreflightRunner(
        polls=[
            [_run(run_id="red", status="in_progress")],
            [_run(run_id="red", status="completed")],
        ],
        conclusions={"red": "failure"},
    )

    exit_code, repo, dispatched, clock, _progress = _dispatch(
        tmp_path=tmp_path, monkeypatch=monkeypatch, runner=runner, bound_seconds=120.0
    )

    assert exit_code == _PRECONDITION_ERROR
    assert dispatched.calls == []
    assert clock.pauses == [60.0]
    assert "red" in capsys.readouterr().err
    record = _master_ci_record(repo=repo)
    assert record["reason"] == "master-ci-red"
    assert record["run_database_id"] == "red"


def test_scenario171_newer_green_master_ci_run_replaces_wait_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _PreflightRunner(
        polls=[
            [_run(run_id="old", status="in_progress")],
            [_run(run_id="new", status="completed")],
        ],
        conclusions={"new": "success"},
    )

    exit_code, repo, dispatched, clock, progress = _dispatch(
        tmp_path=tmp_path, monkeypatch=monkeypatch, runner=runner, bound_seconds=120.0
    )

    assert exit_code == 0
    assert dispatched.calls == ["livespec-impl-beads-s171"]
    assert clock.pauses == [60.0]
    assert "run old is in_progress" in progress.getvalue()
    assert runner.viewed_runs() == ["new"]
    assert _master_ci_record(repo=repo)["run_database_id"] == "new"


def test_scenario171_pending_master_ci_expiry_defers_without_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = _PreflightRunner(
        polls=[[_run(run_id="pending", status="in_progress")]], conclusions={}
    )

    exit_code, repo, dispatched, clock, _progress = _dispatch(
        tmp_path=tmp_path, monkeypatch=monkeypatch, runner=runner, bound_seconds=120.0
    )

    assert exit_code == _PRECONDITION_ERROR
    assert dispatched.calls == []
    assert clock.pauses == [60.0, 60.0]
    assert _stored_item()["status"] == "ready"
    assert _stored_item()["assignee"] is None
    record = _master_ci_record(repo=repo)
    assert record["status"] == "deferred"
    assert record["reason"] == "master-ci-pending"
    operator_text = capsys.readouterr().err
    assert "still in_progress" in operator_text
    assert not operator_text.startswith("ERROR:")


def _run(*, run_id: str, status: str) -> dict[str, str]:
    return {"status": status, "conclusion": "success", "databaseId": run_id}


def _test_wait(*, waived: bool, wait: MasterCiWait) -> MasterCiWait:
    assert not waived
    return wait
