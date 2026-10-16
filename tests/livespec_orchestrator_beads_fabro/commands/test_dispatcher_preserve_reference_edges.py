"""Edge coverage for Fabro preserve-by-reference comments."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_selection
from livespec_orchestrator_beads_fabro.commands import _dispatcher_preserve_reference as preserve
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.errors import (
    ConnectionPrefixMissingError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)
    # An in-memory journal has no file, and `None` is the honest answer
    # for it: the credential-identity read on the mint path asks this
    # journal where its own history lives, and a double that recorded
    # nothing on disk has none to offer.
    path: Path | None = None

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _FailingDumpRunner:
    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = argv
        _ = cwd
        _ = timeout_seconds
        _ = env
        _ = stdin
        return CommandResult(exit_code=2, stdout="", stderr="run storage not found")


@dataclass(kw_only=True)
class _PermissionDumpRunner:
    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = argv
        _ = cwd
        _ = timeout_seconds
        _ = env
        _ = stdin
        raise PermissionError("artifact is unreadable")


class _BrokenClient:
    bodies: list[str]

    def __init__(self, *, bodies: list[str]) -> None:
        self.bodies = bodies

    def add_comment(self, *, issue_id: str, body: str) -> None:
        self.bodies.append(body)
        raise WorkItemNotFoundError(item_id=issue_id)


_BROKEN_BODIES: list[str] = []


def _broken_client(*, config: StoreConfig) -> _BrokenClient:
    _ = config
    return _BrokenClient(bodies=_BROKEN_BODIES)


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
        id="bd-ib-preserve-edge",
        type="task",
        status="active",
        title="Preserve failed work",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-08-23T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _outcome(*, run_id: str | None = "01M0RUN") -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-preserve-edge",
        status="failed",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="terminal",
        fabro_run_id=run_id,
    )


def _args(*, server: str | None = "https://factory.example.test") -> argparse.Namespace:
    return argparse.Namespace(
        fabro_bin="fabro",
        fabro_factory_target=FactoryTarget(name="hp", server=server, dev_token=None),
    )


def test_missing_run_id_records_journal_without_pointer_comment(tmp_path: Path) -> None:
    append_work_item(path=_config(), item=_item())
    journal = _RecordingJournal()

    preserve.preserve_checkpointed_work_reference(
        args=_args(),
        repo=_repo(tmp_path),
        item=_item(),
        outcome=_outcome(run_id=None),
        journal=journal,
    )

    assert make_beads_client(config=_config()).list_comments(issue_id=_item().id) == []
    assert journal.records == [
        {
            "stage": "preserve-by-reference-skipped",
            "work_item_id": _item().id,
            "reason": "missing-run-or-server",
            "run_id": None,
            "factory_server_url": "https://factory.example.test",
        }
    ]


def test_dump_failure_writes_resolve_failure_comment(tmp_path: Path) -> None:
    append_work_item(path=_config(), item=_item())

    preserve.preserve_checkpointed_work_reference(
        args=_args(),
        repo=_repo(tmp_path),
        item=_item(),
        outcome=_outcome(),
        journal=_RecordingJournal(),
        runner=_FailingDumpRunner(),
    )

    body = str(make_beads_client(config=_config()).list_comments(issue_id=_item().id)[-1]["text"])
    assert "artifact: fabro dump failed with exit code 2" in body
    assert "stderr: run storage not found" in body
    assert "byte size: (not recorded; dump failed)" in body
    assert "sha256: (not recorded; dump failed)" in body
    assert "treat the reference as dangling" in body


def test_comment_write_failure_is_journaled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal = _RecordingJournal()
    _BROKEN_BODIES.clear()
    monkeypatch.setattr(preserve, "make_beads_client", _broken_client)

    preserve.preserve_checkpointed_work_reference(
        args=_args(),
        repo=_repo(tmp_path),
        item=_item(),
        outcome=_outcome(),
        journal=journal,
        runner=_FailingDumpRunner(),
    )

    record = journal.records[-1]
    assert record["stage"] == "preserve-by-reference-error"
    assert record["work_item_id"] == _item().id
    assert record["reason"] == "WorkItemNotFoundError"
    assert record["run_id"] == "01M0RUN"
    assert record["factory_server_url"] == "https://factory.example.test"
    assert record["artifact_digest"] == "(not recorded; dump failed)"
    assert record["pointer_body"] == _BROKEN_BODIES[-1]
    assert "fabro dump failed with exit code 2" in str(record["pointer_body"])


def test_store_config_failure_is_journaled_without_fake_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal = _RecordingJournal()
    append_work_item(path=_config(), item=_item())

    def fail_store_config(*, repo: Path) -> StoreConfig:
        _ = repo
        raise ConnectionPrefixMissingError

    monkeypatch.setattr(preserve, "store_config", fail_store_config)

    preserve.preserve_checkpointed_work_reference(
        args=_args(),
        repo=tmp_path,
        item=_item(),
        outcome=_outcome(),
        journal=journal,
        runner=_FailingDumpRunner(),
    )

    assert make_beads_client(config=_config()).list_comments(issue_id=_item().id) == []
    record = journal.records[-1]
    assert record["stage"] == "preserve-by-reference-error"
    assert record["reason"] == "ConnectionPrefixMissingError"
    assert record["run_id"] == "01M0RUN"
    assert record["factory_server_url"] == "https://factory.example.test"
    assert "fabro dump failed with exit code 2" in str(record["pointer_body"])


def test_dump_os_error_is_journaled_and_swallowed(tmp_path: Path) -> None:
    journal = _RecordingJournal()

    preserve.preserve_checkpointed_work_reference(
        args=_args(),
        repo=_repo(tmp_path),
        item=_item(),
        outcome=_outcome(),
        journal=journal,
        runner=_PermissionDumpRunner(),
    )

    record = journal.records[-1]
    assert record["stage"] == "preserve-by-reference-error"
    assert record["reason"] == "PermissionError"
    assert record["run_id"] == "01M0RUN"
    assert record["factory_server_url"] == "https://factory.example.test"
    assert "artifact is unreadable" in str(record["pointer_body"])


def test_post_run_dispositions_continue_after_preserve_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal = _RecordingJournal()
    calls: list[str] = []

    def broken_preserve(**kwargs: object) -> None:
        _ = kwargs
        calls.append("preserve")
        raise PermissionError("preserve crashed")

    def needs_human(**kwargs: object) -> None:
        _ = kwargs
        calls.append("needs-human")

    def non_convergence(**kwargs: object) -> None:
        _ = kwargs
        calls.append("non-convergence")

    monkeypatch.setattr(
        _dispatcher_loop_selection,
        "preserve_checkpointed_work_reference",
        broken_preserve,
    )
    monkeypatch.setattr(_dispatcher_loop_selection, "escalate_needs_human_block", needs_human)
    monkeypatch.setattr(
        _dispatcher_loop_selection,
        "bounce_non_convergence_to_backlog",
        non_convergence,
    )
    monkeypatch.setattr(_dispatcher_loop_selection, "emit_calibration", lambda **_: None)
    monkeypatch.setattr(
        _dispatcher_loop_selection,
        "record_provider_exhaustion_if_observed",
        lambda **_: None,
    )

    _dispatcher_loop_selection.post_run_dispositions(
        args=_args(),
        repo=tmp_path,
        item=_item(),
        outcome=_outcome(),
        journal=journal,
        wall_clock_seconds=1.0,
        dispatch_context_size=1,
        token_supplier=lambda: "token",
    )

    assert calls == ["preserve", "needs-human", "non-convergence"]


def test_configured_repo_store_config_is_used_for_resolvable_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    append_work_item(path=_config(), item=_item())

    preserve.preserve_checkpointed_work_reference(
        args=_args(),
        repo=repo,
        item=_item(),
        outcome=_outcome(),
        journal=_RecordingJournal(),
        runner=_FailingDumpRunner(),
    )

    body = str(make_beads_client(config=_config()).list_comments(issue_id=_item().id)[-1]["text"])
    assert "factory server url: https://factory.example.test" in body
