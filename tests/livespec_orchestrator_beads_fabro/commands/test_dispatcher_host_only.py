"""Tests for the Dispatcher's factory-safety refuse-to-sandbox routing gate.

Mechanizes the currently-manual routing rule (judgment-leaning OR touches
dispatcher self-machinery -> host sub-agent) AND prevents the proven
7us.6 hang class: a commit-hook self-machinery item mis-routed to a fabro
sandbox deadlocked the in-sandbox `git commit` (a 2.5h silent stall;
work-item livespec-impl-beads-uvd). The dispatcher RECOGNISES an explicit
`host-only` marker on the work-item and REFUSES to launch a fabro sandbox
for it, failing the dispatch with a clear actionable message so the
orchestrator host-routes the item instead.

The marker is the explicit contract carried in the only field-space the
`WorkItem` schema exposes without a cross-repo contracts.md change (the
mapped record drops unrecognised beads labels): a `host-only` / `host_only`
token in the item's title or description, recognised by the pure
`is_host_only_item` predicate exactly the way `item_sizing_warnings`
recognises its `multi-part/multi-RGR` marker — but as a HARD refuse, not a
warn. The refusal is routed as DATA (a `host-only-refused` DispatchOutcome),
never a launched run, so the in-sandbox/in-hook git commit can never
deadlock.

The integration tests share one `_RecordingRunDispatch` stand-in: the
refusal cases assert it was NEVER called (`calls == []`, proving no fabro
launch), and the ordinary-item case asserts it WAS called (an ordinary
item still dispatches) — so the stand-in's body is genuinely exercised.
"""

import json
import stat
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    host_only_refusal_detail,
    is_host_only_item,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

# --- canned fleet manifest (mirrors test_dispatcher.py's autouse fixture) ---

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
def fabro_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Hermetic C-mode dispatch environment (mirrors test_dispatcher.py)."""
    scratch = tmp_path_factory.mktemp("fabro-host-only")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
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


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="livespec-impl-beads-t1",
        type="task",
        status="ready",
        title="A ready task",
        description="Do the thing.",
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
        # Admission-eligible by default so a non-host-only item dispatches; the
        # host-only refusal is checked BEFORE admission, so a host-only item is
        # still routed away (never admitted) regardless of this policy.
        admission_policy="auto",
        acceptance_policy="ai-only",
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


def _stored() -> dict[str, WorkItem]:
    return materialize_work_items(records=read_work_items(path=_config()))


@dataclass(kw_only=True)
class _RecordingRunDispatch:
    """run_dispatch stand-in: records each call and returns a green outcome.

    Shared across the host-only refusal cases (which assert it was NEVER
    called — `calls == []` proves no fabro launch, the whole point) and
    the ordinary-item case (which asserts it WAS called). The single
    shared body is therefore genuinely exercised rather than dead.
    """

    calls: list[str] = field(default_factory=list)

    def __call__(self, **kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        # Touch the materialized overlay so this stand-in walks the same
        # provisioning/cleanup path the real green flow does.
        _ = plan.workflow_toml.read_text(encoding="utf-8")
        _ = stat.S_IMODE(plan.workflow_toml.stat().st_mode)
        self.calls.append(plan.work_item_id)
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="green",
            stage="done",
            pr_number=7,
            merge_sha="abc123",
            detail="merged",
        )


# ---------------------------------------------------------------------------
# Pure predicate: is_host_only_item
# ---------------------------------------------------------------------------


def test_is_host_only_item_false_for_ordinary_item() -> None:
    assert is_host_only_item(item=_item()) is False


def test_is_host_only_item_true_for_host_only_marker_in_title() -> None:
    item = _item(
        title="Refactor the dispatcher",
        factory_safety="mutates-host-machinery",
    )
    assert is_host_only_item(item=item) is True


def test_is_host_only_item_ignores_legacy_marker_prose_without_field() -> None:
    assert is_host_only_item(item=_item(description="Touches commit-hook. host_only.")) is False


def test_host_only_refusal_detail_is_actionable() -> None:
    detail = host_only_refusal_detail(item_id="livespec-impl-beads-uvd")
    assert "livespec-impl-beads-uvd" in detail
    assert "factory-safety" in detail
    assert "livespec-implementer dispatch path" not in detail
    # The orchestrator must learn it should HOST-ROUTE (a host sub-agent),
    # not retry the sandbox.
    assert "host" in detail.lower()
    assert "sub-agent" in detail or "host-route" in detail


# ---------------------------------------------------------------------------
# Integration: dispatch refuses a host-only item before any fabro launch
# ---------------------------------------------------------------------------


def test_dispatch_refuses_host_only_item_without_launching_fabro(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(
        description="Touch the commit-hook self-machinery.",
        factory_safety="mutates-host-machinery",
    )
    append_work_item(path=_config(), item=item)
    recording = _RecordingRunDispatch()
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", recording)
    exit_code = main(
        argv=[
            "dispatch",
            "--repo",
            str(repo),
            "--item",
            item.id,
            "--workflow",
            str(workflow),
            "--json",
        ]
    )
    # Non-zero exit so the orchestrator host-routes the item.
    assert exit_code == 1
    # run_dispatch (the fabro launch) was never reached — the whole point.
    assert recording.calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["status"] == "failed"
    assert payload[0]["stage"] == "host-only-refused"
    assert "factory-safety" in payload[0]["detail"]
    # The item is NOT closed — it stays open for host-routing.
    assert _stored()[item.id].status == "ready"


def test_dispatch_journals_host_only_refusal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(
        title="dispatcher self-machinery change",
        factory_safety="mutates-host-machinery",
    )
    append_work_item(path=_config(), item=item)
    recording = _RecordingRunDispatch()
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", recording)
    exit_code = main(
        argv=["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )
    assert exit_code == 1
    assert recording.calls == []
    journal_text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    outcome_record = next(
        json.loads(line)
        for line in journal_text.splitlines()
        if json.loads(line)["stage"] == "outcome"
    )
    assert outcome_record["outcome"]["stage"] == "host-only-refused"


def test_dispatch_does_not_refuse_ordinary_item(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guard against over-broad matching: an ordinary item still dispatches."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(description="A perfectly ordinary impl task, no markers.")
    append_work_item(path=_config(), item=item)
    recording = _RecordingRunDispatch()
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", recording)
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
    assert exit_code == 0
    assert recording.calls == [item.id]
