"""Integration-tier acceptance for the Dispatcher's non-convergence bounce.

Binds SPECIFICATION/scenarios.md "Scenario 11 — Dispatcher bounces a
non-converging slice to needs-regroom" and the contracts.md clause:

    On factory NON-CONVERGENCE (a dispatched slice that will not converge
    through the janitor gate) the Dispatcher MUST mark the item `needs-regroom`
    and SURFACE it (escalate-don't-drop), never infinite-retry.

This is the top-of-pyramid behavior journey: it drives the real
`dispatcher.main(["dispatch", ...])` CLI through the REAL store/client seam
against the in-memory `FakeBeadsClient` (the hermetic CI backend), with
`run_dispatch` replaced by a stand-in that returns a non-convergence terminal.
The test then reads the tenant back through the SAME `livespec_orchestrator_beads_fabro.regroom`
primitive the Dispatcher uses, proving the bounced item carries the
`needs-regroom` label (marked, never dropped) and that an ordinary failure /
green run does NOT bounce.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import dispatcher
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NON_CONVERGED_MARKER,
    DispatchPlan,
    is_non_convergence_outcome,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.regroom import is_needs_regroom
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

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


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    """Hermetic C-mode dispatch environment + fresh in-memory tenant per case."""
    scratch = tmp_path_factory.mktemp("fabro-non-convergence")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setenv("GH_TOKEN", "test-github-token")
    # `main()` resolves its store config internally; forcing the fake toggle is
    # the only seam that flips the dispatcher onto the in-memory tenant.
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    # The dispatcher's fail-open terminal-failure alarm POSTs to ntfy on a
    # non-green outcome; scrub the topic so a bounce test never fires a real
    # network request (the host carries a live topic).
    for _ntfy_env in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(_ntfy_env, raising=False)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands.dispatcher._fetch_fleet_manifest_text",
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


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="livespec-impl-beads-slice1",
        type="task",
        status="open",
        title="A dispatched slice",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        priority=2,
        assignee=None,
        depends_on=(),
        captured_at="2026-06-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    return replace(base, **overrides)


def _repo_with_workflow(*, tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    # The dispatcher resolves the tenant connection via
    # resolve_store_config(cwd=repo), which REQUIRES an explicit
    # connection.prefix (decoupled from the tenant DB name); a real governed
    # repo always carries one, so the hermetic repo mirrors that.
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    workflow = tmp_path / "workflow.toml"
    _ = workflow.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    return repo, workflow


def _outcome_returning(
    outcome: DispatchOutcome,
) -> Callable[..., DispatchOutcome]:
    """Build a `run_dispatch` stand-in returning `outcome` (rewriting its id)."""

    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        return replace(outcome, work_item_id=plan.work_item_id)

    return _run_dispatch


# ---------------------------------------------------------------------------
# Pure predicate: is_non_convergence_outcome
# ---------------------------------------------------------------------------


def _terminal(*, status: str, stage: str, detail: str = "") -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="livespec-impl-beads-slice1",
        status=status,
        stage=stage,
        pr_number=None,
        merge_sha=None,
        detail=detail,
    )


def test_non_convergence_true_for_stalled_no_progress() -> None:
    assert is_non_convergence_outcome(
        outcome=_terminal(status="stalled-no-progress", stage="fabro-run")
    )


def test_non_convergence_true_for_dot_marker_in_failed_detail() -> None:
    detail = f"some output\n{NON_CONVERGED_MARKER}: fix-loop cap hit without converging"
    assert is_non_convergence_outcome(
        outcome=_terminal(status="failed", stage="fabro-run", detail=detail)
    )


def test_non_convergence_false_for_ordinary_failed() -> None:
    assert not is_non_convergence_outcome(
        outcome=_terminal(status="failed", stage="pr-view", detail="no PR found for branch")
    )


def test_non_convergence_false_for_blocked() -> None:
    # A `blocked` human-gate park is NOT non-convergence (an implement/pr
    # failure parked the run; it is not the fix-loop-cap non-converged exit).
    assert not is_non_convergence_outcome(
        outcome=_terminal(status="blocked", stage="fabro-run", detail=NON_CONVERGED_MARKER)
    )


def test_non_convergence_false_for_green() -> None:
    assert not is_non_convergence_outcome(outcome=_terminal(status="green", stage="done"))


# ---------------------------------------------------------------------------
# Scenario 11: a non-converging slice is marked needs-regroom and surfaced.
# ---------------------------------------------------------------------------


def test_dispatch_bounces_stalled_slice_to_needs_regroom(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    stalled = DispatchOutcome(
        work_item_id=item.id,
        status="stalled-no-progress",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="run made no progress for the full stall window",
    )
    monkeypatch.setattr(dispatcher, "run_dispatch", _outcome_returning(stalled))

    exit_code = main(
        ["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow), "--json"]
    )

    # Non-green terminal -> non-zero exit (the maintainer's eyes are required).
    assert exit_code == 1
    # The slice was marked needs-regroom through the SAME primitive the
    # intake / groom paths use — escalate-don't-drop, not infinite-retry.
    assert is_needs_regroom(path=_config(), item_id=item.id) is True
    # And surfaced to stderr.
    err = capsys.readouterr().err
    assert "needs-regroom" in err
    assert item.id in err


def test_dispatch_bounces_dot_non_converged_slice_to_needs_regroom(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    non_converged = DispatchOutcome(
        work_item_id=item.id,
        status="failed",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail=f"{NON_CONVERGED_MARKER}: fix-loop cap hit; routed back to the Dispatcher",
    )
    monkeypatch.setattr(dispatcher, "run_dispatch", _outcome_returning(non_converged))

    exit_code = main(
        ["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )

    assert exit_code == 1
    assert is_needs_regroom(path=_config(), item_id=item.id) is True
    # The bounce is journaled (the escalation is observable).
    journal_text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    stages = [json.loads(line).get("stage") for line in journal_text.splitlines()]
    assert "non-convergence-bounce" in stages


def test_dispatch_does_not_bounce_ordinary_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A one-off failure (not non-convergence) is NOT bounced to needs-regroom."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    ordinary = DispatchOutcome(
        work_item_id=item.id,
        status="failed",
        stage="pr-view",
        pr_number=None,
        merge_sha=None,
        detail="no PR found for branch",
    )
    monkeypatch.setattr(dispatcher, "run_dispatch", _outcome_returning(ordinary))

    exit_code = main(
        ["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )

    assert exit_code == 1
    assert is_needs_regroom(path=_config(), item_id=item.id) is False


def test_dispatch_does_not_bounce_green_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A converged (green) run is never bounced to needs-regroom."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    green = DispatchOutcome(
        work_item_id=item.id,
        status="green",
        stage="done",
        pr_number=7,
        merge_sha="abc123",
        detail="merged, post-merge janitor green",
    )
    monkeypatch.setattr(dispatcher, "run_dispatch", _outcome_returning(green))

    exit_code = main(
        [
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

    assert exit_code == 0
    assert is_needs_regroom(path=_config(), item_id=item.id) is False
