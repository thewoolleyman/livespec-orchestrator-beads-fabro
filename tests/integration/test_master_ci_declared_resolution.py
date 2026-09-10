"""Integration-tier acceptance for declared master-CI pipeline resolution (v074).

Drives the REAL `dispatcher.main(argv=["dispatch", ...])` CLI through the REAL
store/client seam against the in-memory `FakeBeadsClient`, with `run_dispatch`
replaced by a recording stand-in so no fabro run is launched. Only the
preflight's own command seam is stubbed, so a case exercises the whole path an
operator does: the committed `.livespec.jsonc` on disk, the resolution it feeds,
the argv the lookup actually spawns with, the exit code, and the journal.

Five journeys, one per ratified branch of the clause: a DECLARED pipeline that
is green proceeds with the pass journaled; the same declaration red refuses
naming the run; the run lookup targets the RESOLVED default branch rather than
any shipped literal; an undeclared repository resolves the default convention
unchanged; and a pipeline that cannot be resolved refuses naming the attempted
resolution, the declaring key, and the remedy including the step-waiver escape.

A sixth journey guards the seam between the fourth and the fifth, where the two
readings are one keystroke apart: a repository whose declaration is PRESENT but
unusable must reach the fifth outcome, never the fourth. It is at this tier
because the thing being proved is that no fabro run is dispatched -- a claim
only the whole CLI path can make.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop, _dispatcher_step_gate
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_COMMITTED_WORKFLOW_TOML = (
    '[workflow]\ngraph = "graph.toml"\n\n[run.environment]\nid = "fabro-sandbox"\n'
)
_MINIMAL_GRAPH = (
    "digraph ImplementWorkItem {\n"
    "    graph [\n"
    '        stall_timeout="7200s"\n'
    "    ]\n"
    "\n"
    "    implement [\n"
    '        timeout="1800s"\n'
    "    ]\n"
    "}\n"
)
_FLEET_MANIFEST_TEXT = (
    '{"owner": "thewoolleyman", "members": [{"repo": "repo", "class": "impl-plugin"}]}'
)

_EXIT_PRECONDITION_ERROR = 3
_RESOLVED_BRANCH = "trunk"
_RUN_ID = "778899"
_WAIVER_TOKEN = "dispatcher.step_waivers"


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    scratch = tmp_path_factory.mktemp("master-ci-declared-resolution")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_INVOKER", "session:master-ci-resolution")
    for _ntfy_env in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(_ntfy_env, raising=False)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands."
        "_dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass(kw_only=True)
class _PreflightRunner:
    """The preamble's whole command seam: the source-checkout git reads and `gh`.

    The two pre-dispatch preflights share one injected runner because they share
    one gate: the source-checkout step runs first and is fail-closed, so a
    runner that answered only the `gh` calls would refuse every case here before
    the master-CI lookup it exists to exercise ever ran.
    """

    workflow: str
    job: str
    job_conclusion: str = "success"
    run_list_exit: int = 0
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
        return self._answer(argv=argv)

    def argvs_for(self, *, prefix: tuple[str, ...]) -> list[tuple[str, ...]]:
        """Every recorded argv starting with `prefix`, in call order."""
        return [call for call in self.calls if call[: len(prefix)] == prefix]

    def _answer(self, *, argv: list[str]) -> CommandResult:
        """First matching argv prefix wins; an unscripted argv answers a failure."""
        answers: tuple[tuple[tuple[str, ...], Callable[[], CommandResult]], ...] = (
            (("git", "symbolic-ref"), lambda: _ok(stdout=f"origin/{_RESOLVED_BRANCH}\n")),
            (("git", "rev-parse", "--is-inside-work-tree"), lambda: _ok(stdout="true\n")),
            (("git", "for-each-ref"), lambda: _ok(stdout=f"origin/{_RESOLVED_BRANCH}\n")),
            (("git", "rev-parse"), lambda: _ok(stdout="abc1234\n")),
            (("git", "merge-base"), _ok),
            (("gh", "run", "list"), self._run_list),
            (("gh", "run", "view"), lambda: _ok(stdout=self._jobs())),
            (("gh", "auth", "token"), lambda: _ok(stdout="secret\n")),
            # The empty prefix matches any argv: the catch-all for an
            # unscripted command, kept last so nothing else is shadowed.
            ((), lambda: CommandResult(exit_code=1, stdout="", stderr="unscripted")),
        )
        return next(answer() for prefix, answer in answers if tuple(argv[: len(prefix)]) == prefix)

    def _run_list(self) -> CommandResult:
        if self.run_list_exit != 0:
            return CommandResult(
                exit_code=self.run_list_exit,
                stdout="",
                stderr=f"could not find any workflows named {self.workflow}\n",
            )
        payload = json.dumps(
            [{"status": "completed", "conclusion": "success", "databaseId": _RUN_ID}]
        )
        return CommandResult(exit_code=0, stdout=payload, stderr="")

    def _jobs(self) -> str:
        return json.dumps(
            {"jobs": [{"name": self.job, "conclusion": self.job_conclusion, "status": "completed"}]}
        )


def _ok(*, stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


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
            id="livespec-impl-beads-m1",
            type="task",
            status="ready",
            title="A ready task",
            description="Do the thing.",
            origin="freeform",
            gap_id=None,
            rank="a2",
            assignee=None,
            depends_on=(),
            captured_at="2026-08-26T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
            admission_policy="auto",
            acceptance_policy="ai-only",
            # A dispatchable fixture carries gradeable criteria: the entry-to-`ready`
            # and pre-dispatch walls (the effective-acceptance-criteria clause of contracts.md)
            # refuse an AI-dispositive item whose effective criteria parse to zero
            # gradeable assertions.
            acceptance_criteria="The dispatched slice is verified green by the check suite.",
        )
    )


def _repo(*, tmp_path: Path, declaration: str = "") -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"git_author": {"operator_name": "Chad Woolley", '
        '"operator_email": "thewoolleyman@gmail.com"}, '
        '"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}'
        f"{declaration}}}}}",
        encoding="utf-8",
    )
    workflow = tmp_path / "workflow.toml"
    _ = workflow.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow.parent / "graph.toml").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    return repo, workflow


def _declaration(*, workflow: str, job: str) -> str:
    return f', "dispatcher": {{"master_ci": {{"workflow": "{workflow}", "job": "{job}"}}}}'


def _journal_records(*, repo: Path) -> list[dict[str, object]]:
    path = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _master_ci_record(*, repo: Path) -> dict[str, object]:
    records = [
        record for record in _journal_records(repo=repo) if record["stage"] == "master-ci-preflight"
    ]
    assert len(records) == 1
    return records[0]


def _dispatch(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner: _PreflightRunner,
    declaration: str = "",
) -> tuple[int, Path, _RecordingRunDispatch]:
    repo, workflow = _repo(tmp_path=tmp_path, declaration=declaration)
    item = _item()
    append_work_item(path=_config(), item=item)
    recording = _RecordingRunDispatch()
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", recording)
    monkeypatch.setattr(_dispatcher_step_gate, "ShellCommandRunner", lambda: runner)
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
    return exit_code, repo, recording


def test_a_declared_green_pipeline_proceeds_with_the_pass_journaled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _PreflightRunner(workflow="build.yml", job="all-green")

    exit_code, repo, recording = _dispatch(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        runner=runner,
        declaration=_declaration(workflow="build.yml", job="all-green"),
    )

    assert exit_code == 0
    assert recording.calls == ["livespec-impl-beads-m1"]
    record = _master_ci_record(repo=repo)
    assert record["status"] == "passed"
    assert record["workflow"] == "build.yml"
    assert record["aggregate_job"] == "all-green"
    assert record["pipeline_resolution"] == "declared"
    assert record["declaring_key"] == "dispatcher.master_ci"
    assert record["run_database_id"] == _RUN_ID


def test_a_declared_red_pipeline_refuses_naming_the_red_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = _PreflightRunner(workflow="build.yml", job="all-green", job_conclusion="failure")

    exit_code, repo, recording = _dispatch(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        runner=runner,
        declaration=_declaration(workflow="build.yml", job="all-green"),
    )

    assert exit_code == _EXIT_PRECONDITION_ERROR
    assert recording.calls == []
    stderr = capsys.readouterr().err
    assert _RUN_ID in stderr
    assert "all-green" in stderr
    record = _master_ci_record(repo=repo)
    assert record["reason"] == "master-ci-red"
    assert record["run_database_id"] == _RUN_ID


def test_the_run_lookup_targets_the_resolved_default_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _PreflightRunner(workflow="build.yml", job="all-green")

    exit_code, repo, _ = _dispatch(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        runner=runner,
        declaration=_declaration(workflow="build.yml", job="all-green"),
    )

    assert exit_code == 0
    lookups = runner.argvs_for(prefix=("gh", "run", "list"))
    assert len(lookups) == 1
    lookup = lookups[0]
    assert "--branch" in lookup
    assert lookup[lookup.index("--branch") + 1] == _RESOLVED_BRANCH
    assert _master_ci_record(repo=repo)["branch"] == _RESOLVED_BRANCH


def test_an_undeclared_repository_resolves_the_default_convention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _PreflightRunner(workflow="CI", job="ci-green")

    exit_code, repo, _ = _dispatch(tmp_path=tmp_path, monkeypatch=monkeypatch, runner=runner)

    assert exit_code == 0
    lookups = runner.argvs_for(prefix=("gh", "run", "list"))
    assert len(lookups) == 1
    assert lookups[0][lookups[0].index("--workflow") + 1] == "CI"
    record = _master_ci_record(repo=repo)
    assert record["workflow"] == "CI"
    assert record["aggregate_job"] == "ci-green"
    assert record["pipeline_resolution"] == "default"


def test_a_present_but_unusable_declaration_refuses_the_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A half-declaration is refused, not completed from the default convention.

    The runner answers a green `CI`/`ci-green` pipeline, so the retired fallback
    would have defaulted the missing `job`, proven THAT green, and launched the
    run. `recording.calls == []` is what rules that out.
    """
    runner = _PreflightRunner(workflow="CI", job="ci-green")

    exit_code, repo, recording = _dispatch(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        runner=runner,
        declaration=', "dispatcher": {"master_ci": {"workflow": "build.yml"}}',
    )

    assert exit_code == _EXIT_PRECONDITION_ERROR
    assert recording.calls == []
    assert runner.argvs_for(prefix=("gh", "run", "list")) == []
    stderr = capsys.readouterr().err
    assert "dispatcher.master_ci.job" in stderr
    assert _WAIVER_TOKEN in stderr
    record = _master_ci_record(repo=repo)
    assert record["reason"] == "master-ci-unprovable"
    assert record["pipeline_resolution"] == "declared"
    assert record["workflow"] == "<unresolved>"


def test_an_unresolvable_pipeline_refuses_naming_resolution_key_and_waiver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = _PreflightRunner(workflow="build.yml", job="all-green", run_list_exit=1)

    exit_code, repo, recording = _dispatch(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        runner=runner,
        declaration=_declaration(workflow="build.yml", job="all-green"),
    )

    assert exit_code == _EXIT_PRECONDITION_ERROR
    assert recording.calls == []
    stderr = capsys.readouterr().err
    assert "Resolution attempted: declared" in stderr
    assert "dispatcher.master_ci" in stderr
    assert _WAIVER_TOKEN in stderr
    record = _master_ci_record(repo=repo)
    assert record["reason"] == "master-ci-unprovable"
    assert _WAIVER_TOKEN in str(record["remedy"])
