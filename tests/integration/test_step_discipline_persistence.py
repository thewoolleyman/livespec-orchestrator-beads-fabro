"""Integration-tier acceptance for cross-dispatch step discipline (v074, v087).

Drives the REAL `dispatcher.main(argv=["dispatch", ...])` CLI through the REAL
store/client seam against the in-memory `FakeBeadsClient`, with `run_dispatch`
replaced by a recording stand-in so no fabro run is launched. Only the
pre-dispatch gate's own command seam is stubbed, so each case exercises the
whole path an operator does: a journal carrying a degraded post-merge outcome
from a PREVIOUS dispatch, the governed repository's committed `.livespec.jsonc`
and justfile on disk, the exit code, whether a dispatch happened at all, and
what the journal says afterwards.

Four journeys: one per sanctioned exit from a degraded outcome, plus the
declared-recipe resolution v087 added beside them.

1. REFUSAL. The degradation stands and the repository still does not provide the
   integration point, so the next dispatch is refused at the pre-dispatch gate
   with exit 3, naming the missing integration point, the originating outcome
   record, the remedy, and WHICH resolution was attempted -- and no fabro run is
   created.
2. CLEARING RE-VERIFICATION. The repository now declares the hook-install
   recipe, so the pre-dispatch re-verification observes the integration point
   provided, journals a clearing record naming the step identifier and the
   record it clears, and the dispatch proceeds.
3. WAIVED PROCEED. The integration point is still absent, but a committed
   `dispatcher.step_waivers` entry names the step, so the dispatch proceeds and
   the journal records the proceed AS waived, with the waiver's owner.
4. DECLARED RECIPE. An adopter that provides its own hook-install recipe under
   `dispatcher.janitor_bootstrap.recipe` -- and no `just` recipe of ours at all
   -- is re-verified against the recipe IT declared, clears, and dispatches. It
   is the leg that proves the step is satisfiable by declaration rather than by
   adopting the fleet toolchain.

They are at this tier because the claim each makes is about whether a fabro run
is dispatched -- something only the whole CLI path can answer.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop, _dispatcher_step_gate
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_install_recipe import (
    JANITOR_BOOTSTRAP_KEY,
    integration_point,
    janitor_bootstrap_recipe_from_block,
    remedy,
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
_GRADEABLE_CRITERIA = (
    "The dispatcher refuses an ungradeable item before any run is created.\n"
    "The refusal names the work-item id and the resolved source.\n"
)

_EXIT_PRECONDITION_ERROR = 3
# The prose a degradation carries when the repository declared nothing: rendered
# from the resolver's own default rather than restated, so this fixture cannot
# drift from the convention it stands for.
_DEFAULT_RECIPE = janitor_bootstrap_recipe_from_block(block={})
_DEFAULT_INTEGRATION_POINT = integration_point(recipe=_DEFAULT_RECIPE)
_DEFAULT_REMEDY = remedy(recipe=_DEFAULT_RECIPE)
_ADOPTER_SCRIPT = "install-hooks.sh"
_ADOPTER_RECIPE = f"./{_ADOPTER_SCRIPT} --force"
_RESOLVED_BRANCH = "trunk"
_RUN_ID = "551122"
_DEGRADED_AT = "2026-08-27T09:00:00Z"
_DEGRADED_ITEM = "livespec-impl-beads-earlier"
_DEGRADED_REFERENCE = (
    f"stage=outcome at={_DEGRADED_AT} work_item_id={_DEGRADED_ITEM} step=janitor-bootstrap"
)


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    scratch = tmp_path_factory.mktemp("step-discipline-persistence")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_INVOKER", "session:step-discipline")
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
class _GreenPreflightRunner:
    """Both pre-dispatch preflights answering PASS, so only persistence decides."""

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

    def _answer(self, *, argv: list[str]) -> CommandResult:
        """First matching argv prefix wins; the empty prefix is the catch-all."""
        return next(
            result for prefix, result in _GREEN_ANSWERS if tuple(argv[: len(prefix)]) == prefix
        )


def _ok(*, stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


_RUN_LIST_PAYLOAD = json.dumps(
    [{"status": "completed", "conclusion": "success", "databaseId": _RUN_ID}]
)
_JOBS_PAYLOAD = json.dumps(
    {"jobs": [{"name": "ci-green", "conclusion": "success", "status": "completed"}]}
)

# Every command BOTH pre-dispatch preflights spawn, each answering PASS, so the
# only thing left to decide the dispatch is the persistence arm under test.
_GREEN_ANSWERS: tuple[tuple[tuple[str, ...], CommandResult], ...] = (
    (("git", "rev-parse", "--is-inside-work-tree"), _ok(stdout="true\n")),
    (("git", "symbolic-ref"), _ok(stdout=f"origin/{_RESOLVED_BRANCH}\n")),
    (("git", "for-each-ref"), _ok(stdout=f"origin/{_RESOLVED_BRANCH}\n")),
    (("git", "rev-parse"), _ok(stdout="abc1234\n")),
    (("git", "merge-base"), _ok()),
    (("gh", "run", "list"), _ok(stdout=_RUN_LIST_PAYLOAD)),
    (("gh", "run", "view"), _ok(stdout=_JOBS_PAYLOAD)),
    (("gh", "auth", "token"), _ok(stdout="secret\n")),
    ((), CommandResult(exit_code=1, stdout="", stderr="unscripted")),
)


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
            pr_number=11,
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
            id="livespec-impl-beads-s1",
            type="task",
            status="ready",
            title="A ready task",
            description="Do the thing.",
            origin="freeform",
            gap_id=None,
            rank="a2",
            assignee=None,
            depends_on=(),
            captured_at="2026-08-27T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
            admission_policy="auto",
            acceptance_policy="ai-only",
            acceptance_criteria=_GRADEABLE_CRITERIA,
        )
    )


def _degraded_journal_line() -> str:
    """The record a PREVIOUS dispatch left when the janitor bootstrap degraded."""
    return json.dumps(
        {
            "stage": "outcome",
            "at": _DEGRADED_AT,
            "invoker": "session:earlier",
            "invoker_source": "env",
            "outcome": {
                "work_item_id": _DEGRADED_ITEM,
                "status": "green",
                "stage": "janitor-env-degraded",
                "pr_number": 9,
                "merge_sha": "deadbee",
                "detail": "merged, but the post-merge janitor DID NOT RUN",
                "step": "janitor-bootstrap",
                "missing_integration_point": _DEFAULT_INTEGRATION_POINT,
                "remedy": _DEFAULT_REMEDY,
            },
        }
    )


def _repo(
    *,
    tmp_path: Path,
    dispatcher: str = "",
    justfile: str | None = None,
    adopter_script: bool = False,
) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"git_author": {"operator_name": "Chad Woolley", '
        '"operator_email": "thewoolleyman@gmail.com"}, '
        '"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}'
        f"{dispatcher}}}}}",
        encoding="utf-8",
    )
    if justfile is not None:
        _ = (repo / "justfile").write_text(justfile, encoding="utf-8")
    if adopter_script:
        script = repo / _ADOPTER_SCRIPT
        _ = script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        script.chmod(0o755)
    return repo


def _journal_records(*, journal: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines() if line]


def _dispatch(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dispatcher: str = "",
    justfile: str | None = None,
    adopter_script: bool = False,
) -> tuple[int, Path, _RecordingRunDispatch]:
    repo = _repo(
        tmp_path=tmp_path,
        dispatcher=dispatcher,
        justfile=justfile,
        adopter_script=adopter_script,
    )
    workflow = tmp_path / "workflow.toml"
    _ = workflow.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow.parent / "graph.toml").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    journal = tmp_path / "journal.jsonl"
    _ = journal.write_text(_degraded_journal_line() + "\n", encoding="utf-8")
    item = _item()
    append_work_item(path=_config(), item=item)
    recording = _RecordingRunDispatch()
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", recording)
    monkeypatch.setattr(
        _dispatcher_step_gate, "ShellCommandRunner", lambda: _GreenPreflightRunner()
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
            "--journal",
            str(journal),
            "--no-close-on-merge",
        ]
    )
    return exit_code, journal, recording


def test_a_standing_degraded_outcome_refuses_the_next_dispatch_with_exit_three(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, journal, recording = _dispatch(tmp_path=tmp_path, monkeypatch=monkeypatch)

    assert exit_code == _EXIT_PRECONDITION_ERROR
    assert recording.calls == []
    stderr = capsys.readouterr().err
    assert _DEFAULT_INTEGRATION_POINT in stderr
    assert _DEGRADED_REFERENCE in stderr
    assert "dispatcher.step_waivers" in stderr
    # The refusal says WHICH resolution it attempted and names the declaring key,
    # so "your recipe is missing" is distinguishable from "I looked for a recipe
    # you never declared".
    assert "Resolution attempted: default convention" in stderr
    assert JANITOR_BOOTSTRAP_KEY in stderr
    record = _journal_records(journal=journal)[-1]
    assert record["stage"] == "step-persistence-preflight"
    assert record["step"] == "janitor-bootstrap"
    assert record["missing_integration_point"] == _DEFAULT_INTEGRATION_POINT
    assert record["originating_outcome_record"] == _DEGRADED_REFERENCE
    assert record["remedy"] == _DEFAULT_REMEDY
    assert JANITOR_BOOTSTRAP_KEY in str(record["resolution_attempted"])


def test_a_re_verification_that_observes_the_integration_point_clears_and_proceeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exit_code, journal, recording = _dispatch(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        justfile="install-commit-refuse-hooks:\n    echo installed\n",
    )

    assert exit_code == 0
    assert recording.calls == ["livespec-impl-beads-s1"]
    clearing = [
        record for record in _journal_records(journal=journal) if record["stage"] == "step-clearing"
    ]
    assert len(clearing) == 1
    assert clearing[0]["step"] == "janitor-bootstrap"
    assert clearing[0]["status"] == "cleared"
    assert clearing[0]["clears_outcome_record"] == _DEGRADED_REFERENCE
    assert clearing[0]["clears_outcome_at"] == _DEGRADED_AT


def test_an_adopter_declaring_its_own_recipe_is_re_verified_against_that_recipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Satisfiable by DECLARATION: no justfile, no fleet recipe, and it still clears.

    The repository carries none of our toolchain -- there is no justfile at all,
    so the fleet convention could not resolve here -- and the degradation clears
    anyway, because the committed key redirected the re-verification onto the
    hook-install script this adopter actually ships.
    """
    exit_code, journal, recording = _dispatch(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        dispatcher=(
            ', "dispatcher": {"janitor_bootstrap": {"recipe": ' f'"{_ADOPTER_RECIPE}"' "}}"
        ),
        adopter_script=True,
    )

    assert exit_code == 0
    assert recording.calls == ["livespec-impl-beads-s1"]
    clearing = [
        record for record in _journal_records(journal=journal) if record["stage"] == "step-clearing"
    ]
    assert len(clearing) == 1
    assert clearing[0]["clears_outcome_record"] == _DEGRADED_REFERENCE


def test_an_adopter_whose_declared_recipe_is_absent_is_refused_naming_the_declaration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Declaration changes WHAT is looked for, never WHETHER absence refuses."""
    exit_code, _, recording = _dispatch(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        dispatcher=(
            ', "dispatcher": {"janitor_bootstrap": {"recipe": ' f'"{_ADOPTER_RECIPE}"' "}}"
        ),
    )

    assert exit_code == _EXIT_PRECONDITION_ERROR
    assert recording.calls == []
    stderr = capsys.readouterr().err
    assert "Resolution attempted: declared" in stderr
    assert _ADOPTER_RECIPE in stderr
    assert JANITOR_BOOTSTRAP_KEY in stderr


def test_a_committed_step_waiver_proceeds_and_journals_the_waiver_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exit_code, journal, recording = _dispatch(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        dispatcher=(
            ', "dispatcher": {"step_waivers": [{"step": "janitor-bootstrap", '
            '"owner": "release-engineering", '
            '"reason": "adopter is migrating its hook bootstrap"}]}'
        ),
    )

    assert exit_code == 0
    assert recording.calls == ["livespec-impl-beads-s1"]
    waived = [
        record
        for record in _journal_records(journal=journal)
        if record["stage"] == "step-waived-proceed"
    ]
    assert len(waived) == 1
    assert waived[0]["status"] == "waived"
    assert waived[0]["step"] == "janitor-bootstrap"
    assert waived[0]["waiver_owner"] == "release-engineering"
    assert waived[0]["declaring_key"] == "dispatcher.step_waivers"
