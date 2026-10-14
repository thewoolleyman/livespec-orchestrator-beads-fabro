"""Tests for the retry-discipline record a dispatch's own ending earns.

TWO CLAIMS THAT ONLY MEAN SOMETHING TOGETHER. A `failed` outcome must leave a
refusal signature on the item's ledger, and a `capacity-deferred` outcome must
leave NOTHING. Either alone is satisfied by a recorder that is wrong in one
direction: a writer that signed every outcome passes the first, and a writer
that signed none passes the second. The pair is what pins the filter, which is
why they are asserted in one module rather than split.

THE ASSERTION IS READ BACK OFF THE LEDGER, not off a return value, because the
record's whole purpose is to outlive the process that wrote it — the journal
lives in the `tmp/` tree of whichever host ran the dispatch, so a journal-only
signature is invisible to the next dispatch from any other clone. The read uses
`list_comments` and indexes `text`: `bd show --json` carries no comments at all,
and `body` / `content` are not the key, so either mistake reports a written
record as a lost one.

THE BUILD IDENTITY IS INJECTED in every case but the two that assert the
resolution itself, so the asserted bytes do not depend on which plugin root the
suite happens to run under.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-retry"
_NOW = "2026-10-14T01:02:03Z"
_COMMANDS_DIR = Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_retry_outcome"
_RECORDS_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_retry_records"


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _module() -> ModuleType:
    assert (_COMMANDS_DIR / "_dispatcher_retry_outcome.py").is_file()
    return importlib.import_module(_MODULE_NAME)


def _records() -> ModuleType:
    assert (_COMMANDS_DIR / "_dispatcher_retry_records.py").is_file()
    return importlib.import_module(_RECORDS_MODULE_NAME)


def _build() -> Any:
    return _records().ExecutingBuild(version="0.196.1", plugin_root="/plugins/cache/0196")


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "livespec-impl-beads"}}}',
        encoding="utf-8",
    )
    return repo


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="active",
        title="Retry discipline",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-14T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _outcome(
    *,
    status: str,
    stage: str = "fabro-run",
    category: str | None = None,
    step: str | None = None,
) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM_ID,
        status=status,
        stage=stage,
        pr_number=None,
        merge_sha=None,
        detail="terminal",
        step=step,
        fabro_failure_category=category,
    )


def _bodies() -> list[str]:
    return [
        str(comment["text"])
        for comment in make_beads_client(config=_config()).list_comments(issue_id=_ITEM_ID)
    ]


def test_failed_outcome_writes_a_refusal_signature_naming_stage_class_build_and_instant(
    tmp_path: Path,
) -> None:
    module = _module()
    append_work_item(path=_config(), item=_item())
    journal = _RecordingJournal()

    module.record_retry_outcomes(
        repo=_repo(tmp_path),
        outcomes=[_outcome(status="failed", category="deterministic")],
        journal=journal,
        build=_build(),
        now=_NOW,
    )

    bodies = _bodies()
    assert len(bodies) == 1
    assert "livespec-dispatch-retry-discipline" in bodies[0]
    assert "kind: refusal-signature" in bodies[0]
    assert "stage: fabro-run" in bodies[0]
    assert "error-class: deterministic" in bodies[0]
    assert "build-version: 0.196.1" in bodies[0]
    assert "plugin-root: /plugins/cache/0196" in bodies[0]
    assert f"recorded-at: {_NOW}" in bodies[0]
    assert journal.records[0]["stage"] == module.RETRY_SIGNATURE_STAGE
    assert journal.records[0]["refusing_stage"] == "fabro-run"
    assert journal.records[0]["error_class"] == "deterministic"


def test_admission_held_refusal_is_signed_under_its_admission_stage(tmp_path: Path) -> None:
    module = _module()
    append_work_item(path=_config(), item=_item())
    journal = _RecordingJournal()

    module.record_retry_outcomes(
        repo=_repo(tmp_path),
        outcomes=[_outcome(status="failed", stage="admission-held")],
        journal=journal,
        build=_build(),
        now=_NOW,
    )

    bodies = _bodies()
    assert "stage: admission-held" in bodies[0]
    assert "error-class: unclassified" in bodies[0]


def test_degraded_step_supplies_the_error_class_when_no_engine_category_was_recorded(
    tmp_path: Path,
) -> None:
    module = _module()
    append_work_item(path=_config(), item=_item())
    journal = _RecordingJournal()

    module.record_retry_outcomes(
        repo=_repo(tmp_path),
        outcomes=[_outcome(status="failed", stage="janitor-post-merge", step="hook-install")],
        journal=journal,
        build=_build(),
        now=_NOW,
    )

    assert "error-class: hook-install" in _bodies()[0]


def test_capacity_deferral_writes_no_refusal_signature(tmp_path: Path) -> None:
    module = _module()
    append_work_item(path=_config(), item=_item())
    journal = _RecordingJournal()

    module.record_retry_outcomes(
        repo=_repo(tmp_path),
        outcomes=[_outcome(status="capacity-deferred", stage="capacity-deferred")],
        journal=journal,
        build=_build(),
        now=_NOW,
    )

    assert _bodies() == []
    assert journal.records == []


def test_an_unwritable_ledger_is_journaled_rather_than_raised(tmp_path: Path) -> None:
    module = _module()
    journal = _RecordingJournal()

    module.record_retry_outcomes(
        repo=_repo(tmp_path),
        outcomes=[_outcome(status="failed")],
        journal=journal,
        build=_build(),
        now=_NOW,
    )

    assert journal.records[0]["stage"] == module.RETRY_WRITE_FAILED_STAGE
    assert journal.records[0]["reason"] == "BeadsMappingError"


def test_the_executing_build_reports_the_installed_manifest_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    root = tmp_path / "cache" / "build"
    root.mkdir(parents=True)
    _ = (root / "plugin.json").write_text('{"version": "9.9.9"}', encoding="utf-8")
    monkeypatch.setattr(module, "plugin_root", lambda: root)

    build = module.executing_build()

    assert build.version == "9.9.9"
    assert build.plugin_root == str(root)


def test_an_unparseable_manifest_reports_an_unknown_build_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    monkeypatch.setattr(module, "plugin_root", lambda: tmp_path / "absent")

    assert module.executing_build().version == _records().UNKNOWN_BUILD_VERSION


def test_the_resolved_build_is_used_when_no_caller_injects_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    append_work_item(path=_config(), item=_item())
    journal = _RecordingJournal()
    root = tmp_path / "resolved"
    root.mkdir()
    _ = (root / "plugin.json").write_text('{"version": "1.2.3"}', encoding="utf-8")
    monkeypatch.setattr(module, "plugin_root", lambda: root)

    module.record_retry_outcomes(
        repo=_repo(tmp_path),
        outcomes=[_outcome(status="failed")],
        journal=journal,
    )

    assert "build-version: 1.2.3" in _bodies()[0]
    assert journal.records[0]["recorded_at"] != ""
