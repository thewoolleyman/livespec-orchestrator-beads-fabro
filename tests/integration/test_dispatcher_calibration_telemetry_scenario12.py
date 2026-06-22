"""Integration-tier acceptance for the Dispatcher's calibration telemetry.

Binds SPECIFICATION/scenarios.md "Scenario 12 — Dispatcher emits calibration
telemetry" and the contracts.md §"Dispatcher grooming behavior" clause:

    The Dispatcher MUST emit calibration telemetry: an outcome signal plus
    mechanical size proxies recorded on the EXISTING Dispatcher journal (the
    journal → Honeycomb leg already designed in the operability preconditions),
    with NO new always-on service.

This is the top-of-pyramid behavior journey for the calibration telemetry
(work-item livespec-impl-beads-yfsv4j, gap-ajq7ynr4): it drives the real
`dispatcher.main(["dispatch", ...])` CLI through the REAL store/client seam
against the in-memory `FakeBeadsClient` (the hermetic CI backend), with
`run_dispatch` replaced by a stand-in that returns a terminal outcome. The test
then reads the SAME on-disk Dispatcher journal back (the user-observable
artifact at `tmp/fabro-dispatch-journal.jsonl`, the surface the mechanical
reflection leg → Honeycomb egress reads) and proves the dispatch wrote a single
`calibration` stage record carrying the outcome SIGNAL plus the mechanical SIZE
PROXIES, that an unobservable proxy is recorded as `None` (absent, never falsely
zero), and that no new always-on service was started (the only journal is the
EXISTING one, and the dispatch process terminates with a verdict).

The hermetic green outcome carries NO PR number, so the `gh pr view` diff-size
probe short-circuits to `None` (no network IO) — the calibration stage stays a
pure read against the in-memory tenant and the on-disk journal. Per the heading
taxonomy's pyramid-tier requirement (livespec/SPECIFICATION/constraints.md
§"Heading taxonomy"), this binds at the integration tier, never a unit-tier
test.
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration import (
    build_calibration_record,
    calibration_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_FLEET_MANIFEST_TEXT = (
    "// fleet-manifest.jsonc — canned test copy\n"
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

# The exact field set the spec's two enumerated lists require on the
# calibration record (contracts.md §"Dispatcher grooming behavior" /
# §"Calibration telemetry and the single Fabro tweak"). The journal record
# carries `stage` plus these, one sibling key each.
_OUTCOME_SIGNAL_FIELDS = (
    "converged",
    "fix_loop_count",
    "outcome_class",
    "wall_clock_seconds",
    "token_cost_micros",
    "bounced_to_regroom",
)
_SIZE_PROXY_FIELDS = (
    "acceptance_count",
    "merged_pr_diff_size",
    "dependency_fan_out",
    "spec_surface_touched",
    "dispatch_context_size",
    "archetype",
    "repo",
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
    scratch = tmp_path_factory.mktemp("fabro-calibration")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setenv("GH_TOKEN", "test-github-token")
    # `main()` resolves its store config internally; forcing the fake toggle is
    # the only seam that flips the dispatcher onto the in-memory tenant.
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    # The dispatcher's fail-open terminal-failure alarm POSTs to ntfy on a
    # non-green outcome; scrub the topic so a calibration test never fires a
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


def _green_no_pr(*, work_item_id: str) -> DispatchOutcome:
    """A converged terminal that never opened a PR.

    No PR number means the `gh pr view` diff-size probe short-circuits to
    `None` — the calibration stage stays a pure read with no network IO,
    keeping the journey hermetic while still exercising a green-converged
    calibration record.
    """
    return DispatchOutcome(
        work_item_id=work_item_id,
        status="green",
        stage="done",
        pr_number=None,
        merge_sha=None,
        detail="merged, post-merge janitor green",
    )


def _stand_in_returning(
    outcome: DispatchOutcome,
) -> Callable[..., DispatchOutcome]:
    """Build a `run_dispatch` stand-in returning `outcome` (rewriting its id)."""

    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        return replace(outcome, work_item_id=plan.work_item_id)

    return _run_dispatch


def _journal_records(*, repo: Path) -> list[dict[str, object]]:
    """Read the on-disk Dispatcher journal back as a list of records."""
    journal_path = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    text = journal_path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _calibration_record(*, repo: Path) -> dict[str, object]:
    """The single `calibration` stage record from the on-disk journal."""
    records = _journal_records(repo=repo)
    calibration = [record for record in records if record.get("stage") == "calibration"]
    assert len(calibration) == 1, f"expected exactly one calibration record, got {len(calibration)}"
    return calibration[0]


# ---------------------------------------------------------------------------
# Scenario 12: a terminal run writes outcome + size proxies onto the journal.
# ---------------------------------------------------------------------------


def test_terminal_run_journals_calibration_outcome_and_size_proxies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dispatched slice reaching a terminal outcome writes one calibration record.

    Drives the real dispatch CLI to a green terminal and reads the EXISTING
    journal back: it carries exactly one `calibration` stage record bearing
    the full outcome SIGNAL plus the mechanical SIZE PROXIES (Scenario 12's
    two `Then` clauses).
    """
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(
        dispatcher, "run_dispatch", _stand_in_returning(_green_no_pr(work_item_id=item.id))
    )

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
    record = _calibration_record(repo=repo)
    # The record rides on the EXISTING journal as a `calibration` stage, keyed
    # by the dispatched item (the per-item correlation key the egress leg reads).
    assert record["stage"] == "calibration"
    assert record["work_item_id"] == item.id
    # Outcome signal — every enumerated field is present, and a green terminal
    # reads as converged, in the green outcome class, with no regroom bounce.
    for signal_field in _OUTCOME_SIGNAL_FIELDS:
        assert signal_field in record, f"missing outcome-signal field {signal_field!r}"
    assert record["converged"] is True
    assert record["outcome_class"] == "green"
    assert record["bounced_to_regroom"] is False
    assert record["fix_loop_count"] == 0
    # Mechanical size proxies — every enumerated field is present and the
    # schema-derived ones reflect this item.
    for proxy_field in _SIZE_PROXY_FIELDS:
        assert proxy_field in record, f"missing size-proxy field {proxy_field!r}"
    assert record["dependency_fan_out"] == 0
    assert record["spec_surface_touched"] is False
    assert record["archetype"] == item.type
    assert record["repo"] == repo.name
    assert isinstance(record["dispatch_context_size"], int)
    assert record["dispatch_context_size"] > 0


def test_unobservable_proxy_is_journaled_as_none_not_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unobservable proxy rides as `null` (absent), never a false zero.

    With no merged PR and no CC cost telemetry, the merged-PR diff size and the
    token cost are not observable for this dispatch — they MUST be journaled as
    `None` so the analysis pass treats them as missing data, never as zero.
    """
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(
        dispatcher, "run_dispatch", _stand_in_returning(_green_no_pr(work_item_id=item.id))
    )

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
    record = _calibration_record(repo=repo)
    # The keys EXIST (the spec enumerates them) but their value is null —
    # absent, distinct from a measured zero.
    assert "merged_pr_diff_size" in record
    assert record["merged_pr_diff_size"] is None
    assert "token_cost_micros" in record
    assert record["token_cost_micros"] is None


def test_calibration_rides_the_existing_journal_with_no_new_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The calibration record rides the EXISTING journal; no new service is started.

    Scenario 12's third `Then`: no new always-on service is introduced. The
    only journal the dispatch writes is the existing `tmp/fabro-dispatch-journal.jsonl`,
    the calibration record sits in-stream beside the ordinary `dispatch-id` /
    `outcome` records, and the process reaches a terminal verdict (it does not
    block on a long-lived service).
    """
    repo, workflow = _repo_with_workflow(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    monkeypatch.setattr(
        dispatcher, "run_dispatch", _stand_in_returning(_green_no_pr(work_item_id=item.id))
    )

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

    # The dispatch reached a terminal verdict (no service kept the process open).
    assert exit_code == 0
    records = _journal_records(repo=repo)
    stages = [record.get("stage") for record in records]
    # The calibration record sits IN the existing journal, in-stream beside the
    # ordinary dispatch records and AFTER the terminal `outcome` — proving it
    # reuses the established surface rather than a new sink.
    assert "calibration" in stages
    assert "outcome" in stages
    assert stages.index("outcome") < stages.index("calibration")
    # No calibration-error fail-open record was written: the stage succeeded.
    assert "calibration-error" not in stages
    # The calibration telemetry rode the EXISTING dispatch journal — it created
    # no calibration-named sink of its own. The only artifacts under tmp/ are the
    # established dispatch-journal pipeline files (the dispatch journal plus its
    # mechanical-reflection spans sidecar, both part of the pre-existing journal
    # → Honeycomb leg); nothing names a calibration service.
    journal_dir = repo / "tmp"
    journal_files = sorted(p.name for p in journal_dir.iterdir() if p.is_file())
    assert "fabro-dispatch-journal.jsonl" in journal_files
    assert all(name.startswith("fabro-dispatch-journal") for name in journal_files), journal_files
    assert not any("calibration" in name for name in journal_files), journal_files


def test_non_convergence_terminal_marks_bounced_to_regroom(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-convergence terminal records `bounced_to_regroom` true on the signal.

    The outcome signal's `bounced_to_regroom` is the mechanical
    "non-convergence routed back to needs-regroom" flag — a
    `stalled-no-progress` terminal reads as a bounce, distinguishing the
    too-big signal from an ordinary green or failed run.
    """
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
    monkeypatch.setattr(dispatcher, "run_dispatch", _stand_in_returning(stalled))

    exit_code = main(
        ["dispatch", "--repo", str(repo), "--item", item.id, "--workflow", str(workflow)]
    )

    # Non-green terminal -> non-zero exit, but the calibration record is still
    # emitted (the verdict is final; calibration is a post-verdict stage).
    assert exit_code == 1
    record = _calibration_record(repo=repo)
    assert record["converged"] is False
    assert record["bounced_to_regroom"] is True
    assert record["outcome_class"] == "stalled-no-progress:fabro-run"


# ---------------------------------------------------------------------------
# Pure builder ↔ journal-record shape: the journaled keys are exactly the
# enumerated calibration fields (no nesting), so the egress leg can promote
# each to a span attribute. This pins the spec's "one sibling key each" shape
# the integration journey reads back.
# ---------------------------------------------------------------------------


def test_journal_record_keys_are_the_enumerated_calibration_fields() -> None:
    record = build_calibration_record(
        item=_item(),
        outcome=_green_no_pr(work_item_id="livespec-impl-beads-slice1"),
        repo_name="repo",
        journal_records=(),
        wall_clock_seconds=12.5,
        token_cost_micros=None,
        dispatch_context_size=4096,
        merged_pr_diff_size=None,
    )
    journaled = calibration_journal_record(record=record)
    expected_keys = {"stage", "work_item_id", *_OUTCOME_SIGNAL_FIELDS, *_SIZE_PROXY_FIELDS}
    assert set(journaled.keys()) == expected_keys
    assert journaled["stage"] == "calibration"
    # Every value is a flat scalar or None (no nested map) — the OTLP enrich
    # stage promotes each sibling key to a span attribute directly.
    for value in journaled.values():
        assert value is None or isinstance(value, str | int | float | bool)
