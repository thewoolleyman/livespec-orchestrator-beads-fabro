"""Effects for the ended-run WIP-capture receipt."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands import _dispatcher_wip_capture_receipt as receipt
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM = "bd-ib-xdhe5z"
_RUN = "01RUN"


@pytest.fixture(autouse=True)
def _tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list[dict[str, object]])

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _Runner:
    stdout: str = ""
    exit_code: int = 0

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env, stdin)
        return CommandResult(exit_code=self.exit_code, stdout=self.stdout, stderr="refused")


@dataclass(kw_only=True)
class _BrokenJournal:
    def append(self, *, record: dict[str, object]) -> None:
        _ = record
        raise OSError


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="test",
        prefix="bd-ib",
        server_user="test",
        database="test",
        bd_path="bd",
        fake=True,
    )


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="bug",
        status="active",
        title="Receipt WIP captures",
        description="Record lost run work.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-11-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _repo(*, tmp_path: Path) -> Path:
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro":{"connection":{"prefix":"bd-ib"}}}',
        encoding="utf-8",
    )
    append_work_item(path=_config(), item=_item())
    return tmp_path


def _comments() -> list[str]:
    return [one.text for one in read_work_item_comments(path=_config(), work_item_id=_ITEM)]


def test_a_capture_is_named_once_even_when_the_ending_is_recorded_twice(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = _Journal()
    ref = f"refs/livespec/wip/{_ITEM}/{_RUN}/3"
    runner = _Runner(stdout=f"{'c' * 40}\t{ref}\n{'b' * 40}\trefs/livespec/wip/{_ITEM}/{_RUN}/2\n")

    receipt.record_wip_capture_receipt(
        repo=repo, work_item_id=_ITEM, run_id=_RUN, factory="petri", journal=journal, runner=runner
    )
    receipt.record_wip_capture_receipt(
        repo=repo, work_item_id=_ITEM, run_id=_RUN, factory="petri", journal=journal, runner=runner
    )

    comments = _comments()
    assert len(comments) == 1
    assert ref in comments[0]
    assert "commit id: " + "c" * 40 in comments[0]
    assert journal.records == []


def test_non_numeric_refs_are_not_captures() -> None:
    assert (
        receipt.latest_wip_capture(
            work_item_id=_ITEM,
            run_id=_RUN,
            refs={f"refs/livespec/wip/{_ITEM}/{_RUN}/not-a-capture": "c" * 40},
        )
        is None
    )


def test_no_capture_and_an_unreadable_forge_are_distinct_receipts(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = _Journal()
    receipt.record_wip_capture_receipt(
        repo=repo,
        work_item_id=_ITEM,
        run_id=_RUN,
        factory="petri",
        journal=journal,
        runner=_Runner(),
    )
    receipt.record_wip_capture_receipt(
        repo=repo,
        work_item_id=_ITEM,
        run_id="01UNREAD",
        factory="petri",
        journal=journal,
        runner=_Runner(exit_code=1),
    )

    comments = _comments()
    assert "the run has no work-in-progress ref" in comments[0]
    assert "work-in-progress preservation could not be determined" in comments[1]
    assert journal.records == []


def test_a_comment_refusal_and_template_opener_do_not_stop_the_ending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = _Journal()

    def _refuse(*, path: StoreConfig, work_item_id: str, body: str) -> None:
        _ = (path, work_item_id, body)
        raise OSError

    monkeypatch.setattr(receipt, "append_work_item_comment", _refuse)
    receipt.record_wip_capture_receipt(
        repo=repo,
        work_item_id=_ITEM,
        run_id=_RUN,
        factory="petri",
        journal=journal,
        runner=_Runner(),
    )
    receipt.record_wip_capture_receipt(
        repo=repo,
        work_item_id=_ITEM,
        run_id="01OPEN",
        factory="{{ unsafe }}",
        journal=journal,
        runner=_Runner(),
    )
    receipt.record_wip_capture_receipt(
        repo=repo,
        work_item_id=_ITEM,
        run_id="01BROKEN",
        factory="{{ unsafe }}",
        journal=_BrokenJournal(),
        runner=_Runner(),
    )

    assert [one["reason"] for one in journal.records] == ["template-opener"]


def test_an_unreadable_comment_list_still_allows_the_fail_soft_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = _Journal()

    def _unreadable(*, path: StoreConfig, work_item_id: str) -> list[object]:
        _ = (path, work_item_id)
        raise OSError

    monkeypatch.setattr(receipt, "read_work_item_comments", _unreadable)
    monkeypatch.setattr(receipt, "ShellCommandRunner", lambda: _Runner())
    receipt.record_wip_capture_receipt(
        repo=repo, work_item_id=_ITEM, run_id=_RUN, factory="petri", journal=journal
    )

    assert journal.records == []


def test_an_unconfigured_ledger_and_unwritable_journal_cannot_block_the_ending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro":{"connection":{}}}', encoding="utf-8"
    )
    monkeypatch.setattr(receipt, "ShellCommandRunner", lambda: _Runner())

    receipt.record_wip_capture_receipt(
        repo=tmp_path,
        work_item_id=_ITEM,
        run_id=_RUN,
        factory="petri",
        journal=_BrokenJournal(),
    )
