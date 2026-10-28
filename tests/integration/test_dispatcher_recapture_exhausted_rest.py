"""A run ended by recapture exhaustion rests at needs-human, not at needs-regroom.

Work-item `bd-ib-iy4cd4`. Run `01M5YH9P9REX` for `bd-ib-yzk2h2` reached
`recapture_route` at its third recapture verdict and ended at the `non_converged`
terminal, which the Dispatcher read as a janitor fix-loop non-convergence and
bounced to `backlog`. The fault was a proof record failing the record grammar,
which a proof-capture rider repairs, so the bounce spent maintainer attention on
a recoverable item.

The terminal's cause line now carries `LIVESPEC_RECAPTURE_EXHAUSTED` and the
recurring proof-record findings when the recapture cap fired. These cases carry
that line through the REAL terminal mapper and the REAL `dispatcher.main`
dispatch over the in-memory tenant, with only `run_dispatch` stood in, and read
the ledger rather than the exit code: a bounce and a needs-human rest both exit 1.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NON_CONVERGED_MARKER,
    DispatchPlan,
    is_non_convergence_outcome,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_RECAPTURE_MARKER = "LIVESPEC_RECAPTURE_EXHAUSTED"
_ITEM_ID = "livespec-impl-beads-slice1"
_RUN = "01M5YH9P9REXTESTRUN"
_FINDING = "[BLOCKING] (proof-record) step 3 contains > outside single quotes"
_RECAPTURE_LINE = (
    f"{_RECAPTURE_MARKER}: recapture cap reached (review ended with a recapture verdict "
    f"3 times; the cap is two laps); recurring proof-record findings: {_FINDING}; "
    "the captured Proof of Done record never converged, so it is routed to a human "
    "for proof-record repair"
)
_JANITOR_LINE = (
    f"{NON_CONVERGED_MARKER}: janitor fix-loop cap hit without converging; "
    "routing back to the Dispatcher for needs-regroom"
)

_FLEET_MANIFEST_TEXT = (
    "// .livespec-fleet-manifest.jsonc — canned test copy\n"
    "{\n"
    '  "owner": "thewoolleyman",\n'
    '  "members": [\n'
    '    { "repo": "livespec", "class": "core" },\n'
    '    { "repo": "repo", "class": "impl-plugin" }\n'
    "  ]\n"
    "}\n"
)
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


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    scratch = tmp_path_factory.mktemp("fabro-recapture-exhausted")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    for _ntfy_env in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(_ntfy_env, raising=False)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )
    reset_fake_singleton()
    yield
    reset_fake_singleton()


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
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="A dispatched slice",
        description=(
            "Implement the slice.\n"
            "\n"
            "## Definition of Done\n"
            "\n"
            "- The dispatched slice lands its change.\n"
            "\n"
            "References: ## Effective acceptance criteria\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-06-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="The dispatched slice is verified green by the check suite.",
    )


def _stored() -> WorkItem:
    return materialize_work_items(records=read_work_items(path=_config()))[_ITEM_ID]


def _plan(*, tmp_path: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=tmp_path,
        work_item_id=_ITEM_ID,
        branch=f"feat/{_ITEM_ID}",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name="petri",
        fabro_factory_server="https://petri.example:32276",
        fabro_factory_dev_token=None,
        janitor=None,
        janitor_checkout=tmp_path / ".janitor",
        janitor_core_checkout=tmp_path / ".janitor" / ".livespec-core",
        janitor_core_repo_url="https://github.com/thewoolleyman/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="succeeded",
    )


def _terminal(*, tmp_path: Path, stderr: str, events: object = None) -> DispatchOutcome:
    """The outcome the production terminal mapper builds from a run's client output."""
    inspect = (
        None
        if events is None
        else FabroInspectResult(
            command=CommandResult(exit_code=0, stdout="", stderr=""),
            payload=None,
            status_kind="failed",
            failure=None,
            events_payload=events,
        )
    )
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(tmp_path=tmp_path),
        run_id=_RUN,
        inspect=inspect,
        exit_code=1,
        stderr=stderr,
    )
    assert outcome is not None
    return outcome


def _repo_with_workflow(*, tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"git_author": {"operator_name": "Chad Woolley", '
        '"operator_email": "thewoolleyman@gmail.com"}, '
        '"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    workflow = tmp_path / "workflow.toml"
    _ = workflow.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow.parent / "graph.toml").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    return repo, workflow


def _returning(outcome: DispatchOutcome) -> Callable[..., DispatchOutcome]:
    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        return replace(outcome, work_item_id=plan.work_item_id)

    return _run_dispatch


def _dispatch(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: DispatchOutcome
) -> tuple[int, Path]:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _returning(outcome))
    exit_code = main(
        argv=["dispatch", "--repo", str(repo), "--item", _ITEM_ID, "--workflow", str(workflow)]
    )
    return exit_code, repo


def _journal_stages(*, repo: Path) -> list[object]:
    text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    return [json.loads(line).get("stage") for line in text.splitlines()]


def test_the_terminal_mapper_reads_the_recapture_line_as_a_needs_human_ending(
    tmp_path: Path,
) -> None:
    """Assertion 2: the outcome is `blocked`, carries the line, and is not a bounce trigger."""
    outcome = _terminal(tmp_path=tmp_path, stderr=f"{_RECAPTURE_LINE}\n")

    assert (outcome.status, outcome.stage) == ("blocked", "fabro-run")
    assert outcome.needs_human_reason == _RECAPTURE_LINE
    assert _FINDING in outcome.detail
    assert f"resolve-blocked:{_ITEM_ID}:ready" in outcome.detail
    assert "needs-regroom" not in outcome.detail
    assert not is_non_convergence_outcome(outcome=outcome)


def test_the_terminal_mapper_reads_the_recapture_line_from_the_terminal_stage_record(
    tmp_path: Path,
) -> None:
    """The terminal's emitted output can reach the Dispatcher only on the stage record."""
    events = [
        {
            "event": "stage.failed",
            "node_id": "non_converged",
            "failure": {"message": f"script exited with status 1\n{_RECAPTURE_LINE}"},
        }
    ]

    outcome = _terminal(tmp_path=tmp_path, stderr="", events=events)

    assert outcome.status == "blocked"
    assert outcome.needs_human_reason == _RECAPTURE_LINE


def test_the_janitor_line_is_still_a_failed_non_convergence_outcome(tmp_path: Path) -> None:
    """Assertion 3: a janitor cap ending keeps its status and its bounce trigger."""
    outcome = _terminal(tmp_path=tmp_path, stderr=f"{_JANITOR_LINE}\n")

    assert outcome.status == "failed"
    assert is_non_convergence_outcome(outcome=outcome)


def test_a_failed_outcome_carrying_the_recapture_line_is_never_a_bounce_trigger() -> None:
    """The predicate itself declines, so no path can bounce a recapture ending."""
    outcome = DispatchOutcome(
        work_item_id=_ITEM_ID,
        status="failed",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail=f"{_RECAPTURE_LINE}\n{NON_CONVERGED_MARKER}",
    )

    assert not is_non_convergence_outcome(outcome=outcome)


def test_a_recapture_exhausted_dispatch_rests_the_item_blocked_with_a_cause_comment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assertion 2: blocked / needs-human, a comment naming the marker and the findings."""
    outcome = _terminal(tmp_path=tmp_path, stderr=f"{_RECAPTURE_LINE}\n")

    exit_code, repo = _dispatch(tmp_path=tmp_path, monkeypatch=monkeypatch, outcome=outcome)

    assert exit_code != 0
    stored = _stored()
    assert (stored.status, stored.blocked_reason) == ("blocked", "needs-human")
    comments = [one.text for one in read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)]
    assert any(_RECAPTURE_MARKER in text and _FINDING in text for text in comments), comments
    stages = _journal_stages(repo=repo)
    assert "needs-human-blocked" in stages
    assert "non-convergence-bounce" not in stages


def test_a_janitor_cap_dispatch_is_still_bounced_to_backlog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assertion 3: the existing routing, unchanged, beside the recapture case."""
    outcome = _terminal(tmp_path=tmp_path, stderr=f"{_JANITOR_LINE}\n")

    exit_code, repo = _dispatch(tmp_path=tmp_path, monkeypatch=monkeypatch, outcome=outcome)

    assert exit_code != 0
    assert _stored().status == "backlog"
    stages = _journal_stages(repo=repo)
    assert "non-convergence-bounce" in stages
    assert "needs-human-blocked" not in stages
