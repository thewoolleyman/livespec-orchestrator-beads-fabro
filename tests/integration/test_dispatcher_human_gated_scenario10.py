"""Integration-tier acceptance for the Dispatcher's human-gated refusal.

Binds SPECIFICATION/scenarios.md "Scenario 10 — Dispatcher refuses a
human-gated item" and the contracts.md clause:

    The Dispatcher MUST refuse to auto-dispatch a `human-gated` (spec-change)
    item — it surfaces it for the maintainer instead.

This is the top-of-pyramid behavior journey for the Dispatcher's human-gated
gate: it drives the real `dispatcher.main(["dispatch", ...])` CLI through the
REAL store/client seam against the in-memory `FakeBeadsClient` (the hermetic CI
backend), with `run_dispatch` replaced by a recording stand-in so the test can
prove NO fabro run was launched for a human-gated item. The marker rides in the
work-item's title/description — the only field-space the `WorkItem` schema
exposes without a cross-repo contracts.md change (the mapped beads record drops
unrecognised labels), the same encoding the sibling `host-only` gate uses.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import dispatcher
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    human_gated_surface_detail,
    is_human_gated_item,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
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
    """Hermetic C-mode dispatch environment + fresh in-memory tenant per case.

    This directory has no shared conftest, so the test owns its backend
    isolation: every case starts against an empty in-memory tenant and the
    singleton is dropped afterwards so nothing leaks between cases.
    """
    scratch = tmp_path_factory.mktemp("fabro-human-gated")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setenv("GH_TOKEN", "test-github-token")
    # `main()` resolves its store config internally; forcing the fake toggle is
    # the only seam that flips the dispatcher onto the in-memory tenant.
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    # The dispatcher's fail-open terminal-failure alarm POSTs to ntfy on a
    # non-green outcome; scrub the topic so a surface/bounce test never fires a
    # real network request (the host carries a live topic).
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
    """A hermetic connection descriptor — `fake=True` selects the in-memory backend."""
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

    The human-gated case asserts it was NEVER called (`calls == []` proves no
    fabro launch — the whole point); the ordinary-item case asserts it WAS
    called, so the single shared body is genuinely exercised.
    """

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


# ---------------------------------------------------------------------------
# Pure predicate: is_human_gated_item
# ---------------------------------------------------------------------------


def test_is_human_gated_item_false_for_ordinary_item() -> None:
    assert is_human_gated_item(item=_item()) is False


def test_is_human_gated_item_true_for_marker_in_title() -> None:
    assert is_human_gated_item(item=_item(title="[human-gated] revise the spec")) is True


def test_is_human_gated_item_true_for_underscore_marker_in_description() -> None:
    assert is_human_gated_item(item=_item(description="Spec change. human_gated.")) is True


def test_is_human_gated_item_is_case_insensitive() -> None:
    assert is_human_gated_item(item=_item(description="Autonomy tier: HUMAN-GATED")) is True


def test_is_human_gated_item_does_not_match_substring_of_other_words() -> None:
    assert is_human_gated_item(item=_item(description="superhuman-gatedness nonsense")) is False
    assert (
        is_human_gated_item(item=_item(description="a human gated the release manually")) is False
    )


def test_human_gated_surface_detail_is_actionable() -> None:
    detail = human_gated_surface_detail(item_id="livespec-impl-beads-spec1")
    assert "livespec-impl-beads-spec1" in detail
    assert "human-gated" in detail
    # The maintainer must learn it should be SURFACED (driven by hand), not
    # auto-dispatched to the factory.
    assert "maintainer" in detail.lower()
    assert "propose-change" in detail


# ---------------------------------------------------------------------------
# Scenario 10: a human-gated slice is surfaced rather than dispatched.
# ---------------------------------------------------------------------------


def test_dispatch_surfaces_human_gated_item_without_launching_fabro(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(
        title="Revise the §Boundary rule",
        description="Spec-change slice, autonomy tier human-gated.",
    )
    append_work_item(path=_config(), item=item)
    recording = _RecordingRunDispatch()
    monkeypatch.setattr(dispatcher, "run_dispatch", recording)

    exit_code = main(
        [
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

    # Non-zero exit so the maintainer's eyes are required.
    assert exit_code == 1
    # run_dispatch (the fabro launch) was never reached — spec change never
    # reaches the factory.
    assert recording.calls == []
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["status"] == "failed"
    assert payload[0]["stage"] == "human-gated-surfaced"
    assert "human-gated" in payload[0]["detail"]
    # The item is NOT closed — it stays open for the maintainer to drive.
    assert _stored()[item.id].status == "ready"


def test_dispatch_journals_human_gated_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(title="human-gated spec-change slice")
    append_work_item(path=_config(), item=item)
    recording = _RecordingRunDispatch()
    monkeypatch.setattr(dispatcher, "run_dispatch", recording)

    exit_code = main(
        ["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )

    assert exit_code == 1
    assert recording.calls == []
    journal_text = (repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    outcome_record = next(
        json.loads(line)
        for line in journal_text.splitlines()
        if json.loads(line)["stage"] == "outcome"
    )
    assert outcome_record["outcome"]["stage"] == "human-gated-surfaced"


def test_dispatch_does_not_surface_ordinary_item(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guard against over-broad matching: an ordinary item still dispatches."""
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item(description="A perfectly ordinary impl task, no markers.")
    append_work_item(path=_config(), item=item)
    recording = _RecordingRunDispatch()
    monkeypatch.setattr(dispatcher, "run_dispatch", recording)

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
    assert recording.calls == [item.id]
