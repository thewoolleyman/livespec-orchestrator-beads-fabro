"""Tests for the named change that clears the retry guard, and what clears it for good.

FOUR CLAIMS ABOUT ONE RECORD, which is why they share a module. A `--because`
reason ADMITS an armed dispatch and is written to the item and to the journal; the
NEXT refusal reads that record back to say whether the reason changed anything; a
dispatch that MERGES writes the record that disarms the guard outright; and the
`drive` operator surface forwards the reason into the dispatcher argv it builds.
Each one is the record the one before it wrote.

THE REPEAT CLAUSE IS ASSERTED IN BOTH DIRECTIONS. A clause that fired whenever
any reason had been given would pass the positive case alone, so the negative
case moves the second signature to a DIFFERENT stage — a named change that
genuinely moved the failure, which is progress rather than a repeat — and asserts
the clause is absent.

THE DRIVE FORWARDING IS ASSERTED AS ONE ARGV ELEMENT, not as a substring of the
joined command line: the reason is operator prose carrying spaces, and a
transport that split it on whitespace would satisfy a substring assertion while
delivering a mangled reason and a stray positional to the Dispatcher.
"""

from __future__ import annotations

import argparse
import importlib
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands import drive
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._drive_impl_dispatch import (
    build_dispatcher_argv,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-named"
_REASON = "rebound the session from 0.187.0 to 0.196.1, which carries the checkpoint fix"
_COMMANDS_DIR = Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
_GUARD_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_retry_guard"
_RECORDS_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_retry_records"
_OUTCOME_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_retry_outcome"


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _guard() -> ModuleType:
    assert (_COMMANDS_DIR / "_dispatcher_retry_guard.py").is_file()
    return importlib.import_module(_GUARD_MODULE)


def _records() -> ModuleType:
    return importlib.import_module(_RECORDS_MODULE)


def _outcome_module() -> ModuleType:
    return importlib.import_module(_OUTCOME_MODULE)


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
    repo.mkdir(exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "livespec-impl-beads"}}}',
        encoding="utf-8",
    )
    return repo


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="Named change",
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


def _build() -> Any:
    return _records().ExecutingBuild(version="0.196.1", plugin_root="/cache/new")


def _seed(*, body: str) -> None:
    make_beads_client(config=_config()).add_comment(issue_id=_ITEM_ID, body=body)


def _signature_body(*, stage: str = "fabro-run", error_class: str = "deterministic") -> str:
    records = _records()
    return records.render_retry_record(
        record=records.RetryRecord(
            kind=records.REFUSAL_SIGNATURE_KIND,
            stage=stage,
            error_class=error_class,
            build=records.ExecutingBuild(version="0.187.0", plugin_root="/cache/old"),
            recorded_at="2026-10-13T23:20:01Z",
        )
    )


def _bodies() -> list[str]:
    return [
        str(comment["text"])
        for comment in make_beads_client(config=_config()).list_comments(issue_id=_ITEM_ID)
    ]


def _merged_outcome() -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM_ID,
        status="green",
        stage="done",
        pr_number=2850,
        merge_sha="e33bd78c00000000000000000000000000000000",
        detail="merged",
    )


def test_a_named_reason_admits_the_dispatch_and_is_written_to_the_item_and_the_journal(
    tmp_path: Path,
) -> None:
    guard = _guard()
    append_work_item(path=_config(), item=_item())
    _seed(body=_signature_body())
    journal = _RecordingJournal()

    refusal = guard.retry_discipline_refusal(
        args=argparse.Namespace(because=_REASON),
        repo=_repo(tmp_path),
        items=[_item()],
        journal=journal,
        build=_build(),
        now="2026-10-14T02:00:00Z",
    )

    assert refusal is None
    bodies = _bodies()
    assert "kind: named-change" in bodies[-1]
    assert f"reason: {_REASON}" in bodies[-1]
    assert "overrode-stage: fabro-run" in bodies[-1]
    assert "overrode-error-class: deterministic" in bodies[-1]
    assert journal.records[0]["stage"] == guard.RETRY_NAMED_CHANGE_STAGE
    assert journal.records[0]["reason"] == _REASON
    assert journal.records[0]["work_item_id"] == _ITEM_ID


def test_an_unarmed_item_records_no_named_change_for_a_reason_it_did_not_need(
    tmp_path: Path,
) -> None:
    guard = _guard()
    append_work_item(path=_config(), item=_item())

    refusal = guard.retry_discipline_refusal(
        args=argparse.Namespace(because=_REASON),
        repo=_repo(tmp_path),
        items=[_item()],
        journal=_RecordingJournal(),
        build=_build(),
    )

    assert refusal is None
    assert _bodies() == []


def test_a_reason_that_did_not_change_the_outcome_is_quoted_back_in_the_next_refusal(
    tmp_path: Path,
) -> None:
    guard = _guard()
    append_work_item(path=_config(), item=_item())
    _seed(body=_signature_body())
    _ = guard.retry_discipline_refusal(
        args=argparse.Namespace(because=_REASON),
        repo=_repo(tmp_path),
        items=[_item()],
        journal=_RecordingJournal(),
        build=_build(),
        now="2026-10-14T02:00:00Z",
    )
    _seed(body=_signature_body())

    refusal = guard.retry_discipline_refusal(
        args=argparse.Namespace(because=None),
        repo=_repo(tmp_path),
        items=[_item()],
        journal=_RecordingJournal(),
        build=_build(),
    )

    assert refusal is not None
    assert "previous reason did NOT change the outcome" in refusal
    assert f'"{_REASON}"' in refusal


def test_a_reason_that_moved_the_failure_is_not_reported_as_ineffective(
    tmp_path: Path,
) -> None:
    """A named change that landed at a DIFFERENT stage is progress, not a repeat."""
    guard = _guard()
    append_work_item(path=_config(), item=_item())
    _seed(body=_signature_body())
    _ = guard.retry_discipline_refusal(
        args=argparse.Namespace(because=_REASON),
        repo=_repo(tmp_path),
        items=[_item()],
        journal=_RecordingJournal(),
        build=_build(),
        now="2026-10-14T02:00:00Z",
    )
    _seed(body=_signature_body(stage="admission-held", error_class="unclassified"))

    refusal = guard.retry_discipline_refusal(
        args=argparse.Namespace(because=None),
        repo=_repo(tmp_path),
        items=[_item()],
        journal=_RecordingJournal(),
        build=_build(),
    )

    assert refusal is not None
    assert "refusing stage or admission: admission-held" in refusal
    assert "previous reason did NOT change the outcome" not in refusal


def test_two_consecutive_signatures_report_no_ineffective_reason(tmp_path: Path) -> None:
    guard = _guard()
    append_work_item(path=_config(), item=_item())
    _seed(body=_signature_body())
    _seed(body=_signature_body())

    refusal = guard.retry_discipline_refusal(
        args=argparse.Namespace(because=None),
        repo=_repo(tmp_path),
        items=[_item()],
        journal=_RecordingJournal(),
        build=_build(),
    )

    assert refusal is not None
    assert "previous reason did NOT change the outcome" not in refusal


def test_a_dispatch_that_merges_clears_the_guard_and_the_next_one_needs_no_reason(
    tmp_path: Path,
) -> None:
    guard = _guard()
    outcome_module = _outcome_module()
    append_work_item(path=_config(), item=_item())
    _seed(body=_signature_body())
    repo = _repo(tmp_path)
    journal = _RecordingJournal()

    outcome_module.record_retry_outcomes(
        repo=repo,
        outcomes=[_merged_outcome()],
        journal=journal,
        build=_build(),
        now="2026-10-14T03:00:00Z",
    )

    assert "kind: guard-cleared" in _bodies()[-1]
    assert journal.records[0]["stage"] == outcome_module.RETRY_CLEARED_STAGE
    assert (
        guard.retry_discipline_refusal(
            args=argparse.Namespace(because=None),
            repo=repo,
            items=[_item()],
            journal=_RecordingJournal(),
            build=_build(),
        )
        is None
    )


def test_the_drive_impl_argv_carries_the_reason_as_one_unchanged_argument() -> None:
    argv = build_dispatcher_argv(
        repo=Path("/repo"),
        dispatcher_bin=Path("/bin/dispatcher.py"),
        work_item_ref=_ITEM_ID,
        because=_REASON,
    )

    assert "--because" in argv
    assert argv[argv.index("--because") + 1] == _REASON


def test_the_drive_impl_argv_omits_the_flag_when_no_reason_is_given() -> None:
    assert "--because" not in build_dispatcher_argv(
        repo=Path("/repo"),
        dispatcher_bin=Path("/bin/dispatcher.py"),
        work_item_ref=_ITEM_ID,
    )


def test_drive_forwards_a_reason_through_the_impl_action_it_runs() -> None:
    recorded: list[tuple[str, ...]] = []

    def _runner(*, argv: tuple[str, ...], cwd: Path | None = None) -> Any:
        del cwd
        recorded.append(argv)
        return _CommandRun(argv=argv)

    result = drive.run_action(
        repo=Path("/repo"),
        action_id=f"impl:{_ITEM_ID}",
        runner=_runner,
        dispatcher_bin=Path("/bin/dispatcher.py"),
        because=_REASON,
    )

    assert result["status"] == "green"
    assert recorded[0][recorded[0].index("--because") + 1] == _REASON


def test_drive_refuses_a_reason_the_selected_action_cannot_deliver() -> None:
    result = drive.run_action(
        repo=Path("/repo"),
        action_id=f"resolve-blocked:{_ITEM_ID}:ready",
        because=_REASON,
    )

    assert result["status"] == "failed"
    assert "--because is accepted only by" in str(result["summary"])


@dataclass(frozen=True, kw_only=True)
class _CommandRun:
    argv: tuple[str, ...]
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
