"""A declaration that does not satisfy this build's schema version refuses, completely.

Binds `SPECIFICATION/scenarios.md` Scenario 101: a governed repository whose
declaration satisfies neither of two graded points is refused as a pre-dispatch
precondition error, and the refusal enumerates BOTH in one message rather than
one broken dispatch at a time. It is driven through the REAL
`dispatcher.main(argv=["dispatch", ...])` CLI against the in-memory
`FakeBeadsClient`, so what is measured is the exit code an operator sees, the
message they read, the journal record left behind, and -- the claim only the
whole CLI path can make -- that no factory run was created.

THE DEFECTS ARE INJECTED INTO EACH FIXTURE'S OWN DECLARATION. A hand-written
defective config would be a third repository nobody governs; taking the
committed fleet-member and adopter declarations and writing two unusable values
into them keeps the two legs the two legs, so the refusal is asserted against a
member resting on fleet defaults AND against an adopter that declares every
point through the schema. Both must earn the SAME refusal, because the pass
grades what a repository wrote and neither fixture wrote these.

THE CONTROL IS THE SAME INVOCATION ON THE PRISTINE DECLARATION, and it is what
makes the refusal evidence rather than a pass that refuses everything. It
discriminates by JOURNAL STAGE rather than by exit code: the refused run records
`schema-validation` and never reaches the master-CI preflight, while the
admitted one records `master-ci-preflight` and no `schema-validation` at all. An
exit code alone could not tell the two apart, since every pre-dispatch
precondition error shares one.

THE CONTROL SCRIPTS THE FORGE AND ZEROES THE WAIT. Reaching the master-CI
preflight means reaching its forge reads and its bounded wait, and left alone
those are the PATH `gh` stand-in and the production 1800-second wait on the real
clock. The stand-in's default answer names the fleet-default aggregate job, so
the adopter -- which declares its own -- read as a run carrying no verdict and
the control sat out the whole bound (1800.1 s, bd-ib-fgblbv). So the control
answers every `gh` read itself, green at the pipeline each fixture actually
resolves; hands the step a zero bound whose sleep returns at once, so a reading
that ever does pend defers instead of waiting; and asserts the specific journaled
pass and that the PATH `gh` was never spawned.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_step_gate
from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_preflight_refusals import (
    STAGE as MASTER_CI_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ci_preflight_wait import (
    MasterCiWait,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_declaration import (
    PLUGIN_BLOCK,
    declaration_from_config_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_schema import (
    COMPAT_CORE_REPO_KEY,
    INTEGRATION_CONTRACT_SCHEMA_VERSION,
    MERGE_MODE_KEY,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_validation import (
    SCHEMA_VALIDATION_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import (
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main

from tests.conftest import ScriptedGh
from tests.integration.governed_repo_fixtures import GovernedRepo, over_both_fixtures

_EXIT_PRECONDITION_ERROR = 3
_ITEM_ID = "bd-ib-scenario101"
# The scripted forge's answers. The branch is deliberately not the temp root's
# own `master`, so a pass proves the lookup used the RESOLVED default branch.
_FORGE_BRANCH = "trunk"
_GREEN_RUN_ID = "101"

_COMMITTED_WORKFLOW_TOML = (
    '[workflow]\ngraph = "graph.toml"\n\n[run.environment]\nid = "fabro-sandbox"\n'
)
_MINIMAL_GRAPH = 'digraph ImplementWorkItem {\n    implement [\n        timeout="1800s"\n    ]\n}\n'
_FLEET_MANIFEST_TEXT = (
    '{"owner": "thewoolleyman", "members": [{"repo": "repo", "class": "impl-plugin"}]}'
)

# The two points written UNUSABLE into each fixture's declaration. One hangs off
# the plugin block and one off the `dispatcher` block, so the enumeration is
# shown to cross the two committed blocks rather than listing one family twice.
_INJECTED_DEFECTS: Mapping[str, Mapping[str, object]] = {
    "compat": {"core_repo": None},
    "dispatcher": {"merge_mode": "fast-forward"},
}
_DEFECTIVE_KEYS = (COMPAT_CORE_REPO_KEY, MERGE_MODE_KEY)


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    scratch = tmp_path_factory.mktemp("schema-validation-refusal")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_INVOKER", "session:schema-validation-refusal")
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
class _ScriptedForgeRunner:
    """The master-CI read seam: every `gh` read answered here, every `git` read real.

    Only the forge is scripted. The source-checkout preflight's `git` reads still
    run for real against the hermetic temp-root checkout, so the control keeps
    exercising every step it reaches on the way to the master-CI preflight. The
    forge answers green ONLY for the workflow, branch and aggregate job the
    fixture resolves; any other `gh` argv is recorded and answered unscripted.
    """

    workflow: str
    job: str
    delegate: ShellCommandRunner = field(default_factory=ShellCommandRunner)
    gh_calls: list[tuple[str, ...]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        if argv[:1] != ["gh"]:
            return self.delegate.run(
                argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env, stdin=stdin
            )
        self.gh_calls.append(tuple(argv))
        return self._forge(argv=tuple(argv[1:]))

    def _forge(self, *, argv: tuple[str, ...]) -> CommandResult:
        listing = (
            "run",
            "list",
            "--branch",
            _FORGE_BRANCH,
            "--limit",
            "1",
            "--workflow",
            self.workflow,
            "--json",
            "status,conclusion,databaseId",
        )
        if argv[:2] == ("repo", "view") and "defaultBranchRef" in argv:
            return _ok(stdout=f"{_FORGE_BRANCH}\n")
        if argv == listing:
            run = {"status": "completed", "conclusion": "success", "databaseId": _GREEN_RUN_ID}
            return _ok(stdout=json.dumps([run]))
        if argv == ("run", "view", _GREEN_RUN_ID, "--json", "jobs"):
            job = {"name": self.job, "status": "completed", "conclusion": "success"}
            return _ok(stdout=json.dumps({"jobs": [job]}))
        return CommandResult(exit_code=1, stdout="", stderr="unscripted forge read")


def _ok(*, stdout: str) -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _config_text(*, governed: GovernedRepo, defective: bool) -> str:
    """This fixture's own declaration as a dispatchable config, optionally unusable.

    `connection` is added because a dispatch target has to name its tenant and
    the seam fixtures are declaration-only; nothing else about the committed
    fixture is touched, so the defective and pristine legs differ in exactly the
    two values under test.
    """
    declaration = dict(declaration_from_config_text(config_text=governed.config_text))
    declaration["connection"] = {"prefix": "bd-ib"}
    if defective:
        for block, defects in _INJECTED_DEFECTS.items():
            written = dict(cast("dict[str, object]", declaration.get(block, {})))
            written.update(defects)
            declaration[block] = written
    return json.dumps({PLUGIN_BLOCK: declaration})


def _target_repo(*, tmp_path: Path, governed: GovernedRepo, defective: bool) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        _config_text(governed=governed, defective=defective), encoding="utf-8"
    )
    workflow = tmp_path / "workflow.toml"
    _ = workflow.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (tmp_path / "graph.toml").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    return repo, workflow


def _dispatch(*, repo: Path, workflow: Path) -> int:
    return main(
        argv=[
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            _ITEM_ID,
            "--workflow",
            str(workflow),
            "--no-close-on-merge",
        ]
    )


def _journal_stages(*, repo: Path) -> list[str]:
    path = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return [str(record["stage"]) for record in records]


def _stage_record(*, repo: Path, stage: str) -> dict[str, object]:
    path = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    graded = [record for record in records if record["stage"] == stage]
    assert len(graded) == 1
    return cast("dict[str, object]", graded[0])


def _schema_record(*, repo: Path) -> dict[str, object]:
    return _stage_record(repo=repo, stage=SCHEMA_VALIDATION_STAGE)


@over_both_fixtures
def test_a_declaration_that_satisfies_neither_point_refuses_enumerating_both(
    governed: GovernedRepo,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Exit 3, both points in ONE message, journaled, and no run created."""
    repo, workflow = _target_repo(tmp_path=tmp_path, governed=governed, defective=True)

    exit_code = _dispatch(repo=repo, workflow=workflow)

    assert exit_code == _EXIT_PRECONDITION_ERROR
    stderr = capsys.readouterr().err
    refusals = [line for line in stderr.splitlines() if line.startswith("ERROR: refusing")]
    assert len(refusals) == 1
    assert str(INTEGRATION_CONTRACT_SCHEMA_VERSION) in stderr
    for key in _DEFECTIVE_KEYS:
        assert f"`{key}`" in stderr
    record = _schema_record(repo=repo)
    assert record["outcome"] == "refused"
    assert [defect["key"] for defect in cast("list[dict[str, str]]", record["defects"])] == list(
        _DEFECTIVE_KEYS
    )
    # Refused BEFORE admission and before every later preflight, so the whole
    # journal is that one refusal: no run was created and nothing was claimed.
    assert _journal_stages(repo=repo) == [SCHEMA_VALIDATION_STAGE]


@over_both_fixtures
def test_the_committed_declaration_passes_the_same_grading_unchanged(
    governed: GovernedRepo,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    scripted_gh: ScriptedGh,
) -> None:
    """The control: the pass admits what the two fixtures actually declare.

    Discriminated by journal STAGE, not by exit code: the dispatch stops later
    for want of a seeded work-item, and the point being proved is that it got
    PAST the grading -- reaching the master-CI preflight, and recording no
    schema-validation refusal on the way. The preflight it reaches reads a
    scripted forge under a zero wait bound, and its journaled pass names the
    pipeline this fixture resolves.
    """
    repo, workflow = _target_repo(tmp_path=tmp_path, governed=governed, defective=False)
    declared_workflow, declared_job = governed.master_ci
    forge = _ScriptedForgeRunner(workflow=declared_workflow, job=declared_job)
    pauses: list[float] = []
    waits: list[bool] = []

    def _zero_wait(*, waived: bool) -> MasterCiWait:
        waits.append(waived)
        return MasterCiWait(sleep=pauses.append, bound_seconds=0.0)

    monkeypatch.setattr(_dispatcher_step_gate, "ShellCommandRunner", lambda: forge)
    monkeypatch.setattr(_dispatcher_step_gate, "master_ci_wait", _zero_wait)

    _ = _dispatch(repo=repo, workflow=workflow)

    assert "ERROR: refusing to dispatch" not in capsys.readouterr().err
    stages = _journal_stages(repo=repo)
    assert SCHEMA_VALIDATION_STAGE not in stages
    assert MASTER_CI_STAGE in stages
    master_ci = _stage_record(repo=repo, stage=MASTER_CI_STAGE)
    assert master_ci["status"] == "passed"
    assert master_ci["reason"] == "master-ci-green"
    assert master_ci["workflow"] == declared_workflow
    assert master_ci["aggregate_job"] == declared_job
    assert master_ci["branch"] == _FORGE_BRANCH
    assert master_ci["run_database_id"] == _GREEN_RUN_ID
    # The zero-bound wait was the one the step used, and it never paused.
    assert waits == [False]
    assert pauses == []
    # The run reads went through the scripted seam, once each, and no `gh`
    # process was spawned for them or for anything else.
    assert [call[1:3] for call in forge.gh_calls if call[1] == "run"] == [
        ("run", "list"),
        ("run", "view"),
    ]
    assert scripted_gh.argv_lines() == []
