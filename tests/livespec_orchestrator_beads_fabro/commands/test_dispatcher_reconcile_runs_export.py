"""Tests for export-before-terminate and its read-back verification."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands import _dispatcher_reconcile_runs_export as export
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserve_reference_body import (
    PRESERVE_POINTER_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_join import OrphanRun
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError

_SERVER = "https://hp.example:32276"


@dataclass(kw_only=True)
class _FakeLedger:
    """A comment-only ledger seam that RECORDS the verbs it was asked for."""

    comments: list[dict[str, Any]] = field(default_factory=list)
    verbs: list[str] = field(default_factory=list)
    read_back: bool = True
    raise_on_add: bool = False
    raise_on_list: bool = False

    def list_comments(self, *, issue_id: str) -> list[dict[str, Any]]:
        self.verbs.append(f"list_comments:{issue_id}")
        if self.raise_on_list:
            raise BeadsCommandError(command="bd comments", exit_code=1, stderr="denied")
        return list(self.comments)

    def add_comment(self, *, issue_id: str, body: str) -> None:
        self.verbs.append(f"add_comment:{issue_id}")
        if self.raise_on_add:
            raise BeadsCommandError(command="bd comment", exit_code=1, stderr="denied")
        if self.read_back:
            self.comments.append({"id": 42, "text": body})


@dataclass(kw_only=True)
class _DumpRunner:
    exit_code: int = 0
    calls: list[list[str]] = field(default_factory=list)

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
        self.calls.append(argv)
        return CommandResult(exit_code=self.exit_code, stdout="", stderr="")


def test_a_pointer_is_written_then_read_back_through_the_text_key(tmp_path: Path) -> None:
    ledger = _FakeLedger()

    outcome = export.export_orphan_reference(
        orphan=_orphan(work_item_status="closed"),
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_DumpRunner(),
        ledger=ledger,
    )

    assert outcome.exported is True
    assert outcome.comment_id == "42"
    assert outcome.journal_body is None
    assert ledger.verbs == [
        "list_comments:bd-ib-orphan",
        "add_comment:bd-ib-orphan",
        "list_comments:bd-ib-orphan",
    ]
    assert ledger.comments[0]["text"].startswith(PRESERVE_POINTER_MARKER)


def test_an_existing_pointer_for_the_same_run_is_located_not_rewritten(tmp_path: Path) -> None:
    ledger = _FakeLedger(
        comments=[
            {"id": "c-1", "text": "an ordinary comment"},
            {"text": 7},
            {"id": "c-2", "text": _pointer_body(run_id="01OTHER")},
            {"text": _pointer_body(run_id="01ORPHAN")},
        ]
    )

    outcome = export.export_orphan_reference(
        orphan=_orphan(work_item_status="closed"),
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_DumpRunner(),
        ledger=ledger,
    )

    assert outcome.exported is True
    assert outcome.comment_id == "(no comment id reported by bd comments)"
    assert ledger.verbs == ["list_comments:bd-ib-orphan"]


def test_a_read_back_that_does_not_find_the_pointer_refuses_the_export(tmp_path: Path) -> None:
    ledger = _FakeLedger(read_back=False)

    outcome = export.export_orphan_reference(
        orphan=_orphan(work_item_status="closed"),
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_DumpRunner(),
        ledger=ledger,
    )

    assert outcome.exported is False
    assert outcome.comment_id is None
    assert "did not read back" in outcome.detail


def test_a_ledger_error_on_any_leg_refuses_the_export(tmp_path: Path) -> None:
    listing_failed = export.export_orphan_reference(
        orphan=_orphan(work_item_status="closed"),
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_DumpRunner(),
        ledger=_FakeLedger(raise_on_list=True),
    )
    writing_failed = export.export_orphan_reference(
        orphan=_orphan(work_item_status="closed"),
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_DumpRunner(),
        ledger=_FakeLedger(raise_on_add=True),
    )

    assert listing_failed.exported is False
    assert "could not read the preserve-by-reference comment" in listing_failed.detail
    assert writing_failed.exported is False
    assert "could not write the preserve-by-reference comment" in writing_failed.detail


def test_a_read_back_that_errors_after_a_successful_write_refuses(tmp_path: Path) -> None:
    ledger = _RaiseOnSecondList()

    outcome = export.export_orphan_reference(
        orphan=_orphan(work_item_status="closed"),
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_DumpRunner(),
        ledger=ledger,
    )

    assert outcome.exported is False
    assert "could not read back the preserve-by-reference comment" in outcome.detail


def test_an_item_missing_orphan_preserves_its_pointer_for_the_journal(tmp_path: Path) -> None:
    ledger = _FakeLedger()

    outcome = export.export_orphan_reference(
        orphan=_orphan(work_item_status=None),
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_DumpRunner(),
        ledger=ledger,
    )

    assert outcome.exported is True
    assert outcome.comment_id is None
    assert outcome.journal_body is not None
    assert outcome.journal_body.startswith(PRESERVE_POINTER_MARKER)
    assert ledger.verbs == []


def test_a_failed_dump_refuses_an_orphan_export_before_termination(tmp_path: Path) -> None:
    ledger = _FakeLedger()

    outcome = export.export_orphan_reference(
        orphan=_orphan(work_item_status="closed"),
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_DumpRunner(exit_code=124),
        ledger=ledger,
    )

    assert outcome.exported is False
    assert outcome.comment_id is None
    assert outcome.journal_body is None
    assert outcome.detail == "fabro dump failed with exit code 124"
    assert ledger.comments == []


def test_an_export_that_raises_an_os_error_refuses(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    def _explode(**_: object) -> None:
        raise OSError("no space left on device")

    monkeypatch.setattr(export, "pointer_record_for_run", _explode)

    outcome = export.export_orphan_reference(
        orphan=_orphan(work_item_status="closed"),
        repo=tmp_path,
        fabro_bin="fabro",
        runner=_DumpRunner(),
        ledger=_FakeLedger(),
    )

    assert outcome.exported is False
    assert "fabro export failed with OSError" in outcome.detail


@dataclass(kw_only=True)
class _RaiseOnSecondList:
    listed: int = 0
    comments: list[dict[str, Any]] = field(default_factory=list)

    def list_comments(self, *, issue_id: str) -> list[dict[str, Any]]:
        _ = issue_id
        self.listed += 1
        if self.listed > 1:
            raise BeadsCommandError(command="bd comments", exit_code=1, stderr="denied")
        return list(self.comments)

    def add_comment(self, *, issue_id: str, body: str) -> None:
        _ = (issue_id, body)


def _orphan(*, work_item_status: str | None) -> OrphanRun:
    return OrphanRun(
        run_id="01ORPHAN",
        factory_name="hp",
        factory_server_url=_SERVER,
        status_kind="blocked",
        work_item_id="bd-ib-orphan",
        work_item_status=work_item_status,
        orphan_reason="item-not-active",
    )


def _pointer_body(*, run_id: str) -> str:
    return "\n".join(
        [
            PRESERVE_POINTER_MARKER,
            "",
            f"run id: {run_id}",
            f"factory server url: {_SERVER}",
        ]
    )
