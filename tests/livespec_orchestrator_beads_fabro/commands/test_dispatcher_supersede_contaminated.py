"""End-to-end coverage for the contaminated-item successor command."""

from __future__ import annotations

import argparse
import importlib
import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Protocol, cast

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    EDGE_BLOCKS,
    EDGE_PARENT_CHILD,
    EDGE_SUPERSEDES,
    BeadsClient,
    BeadsRecord,
    make_beads_client,
)
from livespec_orchestrator_beads_fabro._store_comments import WorkItemComment
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem, WorkItemStatus
from returns.io import IOFailure, IOSuccess


def _module_path() -> Path:
    return Path(
        ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_supersede_contaminated.py"
    )


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="supersede-test",
        prefix="bd-ib",
        server_user="supersede-test",
        database="supersede-test",
        bd_path="bd",
        fake=True,
    )


def _item(*, item_id: str, status: WorkItemStatus = "ready", title: str = "poisoned") -> WorkItem:
    return WorkItem(
        id=item_id,
        type="bug",
        status=status,
        title=title,
        description="description",
        origin="freeform",
        gap_id=None,
        rank="b3b",
        assignee="old-owner",
        depends_on=({"kind": "local", "work_item_id": "bd-ib-prerequisite"},),
        captured_at="2026-11-13T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        acceptance_criteria="accept this",
        notes="operator note",
    )


class _Subject(Protocol):
    store_config: Callable[..., StoreConfig]
    read_work_item_comments: Callable[..., tuple[WorkItemComment, ...]]
    file_captured_work_item: Callable[..., object]
    new_work_item_id: Callable[..., str]
    utc_now_iso: Callable[[], str]
    _copy_labels: Callable[..., None]

    def run_supersede_contaminated_command(self, *, args: argparse.Namespace) -> int: ...


def _subject() -> _Subject:
    assert _module_path().is_file()
    return cast(
        _Subject,
        importlib.import_module(
            "livespec_orchestrator_beads_fabro.commands._dispatcher_supersede_contaminated"
        ),
    )


def _args(*, tmp_path: Path, item_id: str = "bd-ib-old") -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(tmp_path),
        item=item_id,
        reason="append-only forensic evidence",
        journal=str(tmp_path / "journal.jsonl"),
        invoker="operator:alice",
    )


def _edges(*, raw: BeadsRecord) -> list[BeadsRecord]:
    edges = raw["dependencies"]
    assert isinstance(edges, list)
    return cast("list[BeadsRecord]", edges)


def _assert_capture(*, captured: list[tuple[WorkItem, str | None]], old: WorkItem) -> None:
    successor, parent = captured[0]
    assert successor.title == old.title
    assert successor.type == old.type
    assert successor.rank == old.rank
    assert successor.description == old.description
    assert successor.acceptance_criteria == old.acceptance_criteria
    assert successor.notes == old.notes
    assert parent == "bd-ib-parent"


def _assert_successor(*, client: BeadsClient, config: StoreConfig, old: WorkItem) -> WorkItem:
    records = {item.id: item for item in read_work_items(path=config)}
    assert records[old.id].status == "done"
    assert records[old.id].resolution == "duplicate"
    assert records[old.id].superseded_by == "bd-ib-new"
    successor = records["bd-ib-new"]
    assert successor.depends_on == old.depends_on
    successor_raw = client.show_issue(issue_id=successor.id)
    assert "keep:this" in successor_raw["labels"]
    assert not any(
        label.startswith(("lifecycle:", "claim:", "dispatch-record:"))
        for label in successor_raw["labels"]
    )
    assert {edge["type"] for edge in _edges(raw=successor_raw)} == {
        EDGE_BLOCKS,
        EDGE_PARENT_CHILD,
        EDGE_SUPERSEDES,
    }
    assert {edge["depends_on_id"] for edge in _edges(raw=successor_raw)} == {
        "bd-ib-prerequisite",
        "bd-ib-parent",
        old.id,
    }
    dependent_edges = _edges(raw=client.show_issue(issue_id="bd-ib-dependent"))
    assert any(edge["depends_on_id"] == successor.id for edge in dependent_edges)
    assert not any(edge["depends_on_id"] == old.id for edge in dependent_edges)
    return successor


def _assert_comments_and_journal(
    *, client: BeadsClient, old: WorkItem, successor: WorkItem, tmp_path: Path
) -> None:
    copied: list[str] = []
    for comment in client.list_comments(issue_id=successor.id):
        text = comment["text"]
        assert isinstance(text, str)
        copied.append(text)
    assert copied[0].splitlines()[:2] == [
        "FOR implement ONLY:",
        "Superseded from bd-ib-old comment rider-1 created 2026-11-13T01:00:00Z.",
    ]
    assert "{{" not in copied[0] and copied[0].endswith("retain [[ raw diagnostic")
    assert "⟦" not in copied[0]
    assert copied[1].endswith("clean instruction")
    assert all(not text.startswith("livespec-") for text in copied)
    assert "receipt-3" in copied[-1] and old.id in copied[-1]
    assert "append-only forensic evidence" in copied[-1]
    original_text = client.list_comments(issue_id=old.id)[0]["text"]
    assert isinstance(original_text, str)
    assert successor.id in original_text
    record = json.loads((tmp_path / "journal.jsonl").read_text(encoding="utf-8"))
    assert record["stage"] == "supersede-contaminated"
    assert record["original_id"] == old.id and record["successor_id"] == successor.id
    assert record["reason"] == "append-only forensic evidence"
    assert record["instant"] == "2026-11-14T00:00:00Z"
    assert record["invoker"] == "operator:alice"


def _failed_copy_labels(**kwargs: object) -> None:
    _ = kwargs
    raise BeadsCommandError(command="bd update", exit_code=1, stderr="down")


def _wire_success(
    *,
    client: BeadsClient,
    comments: tuple[WorkItemComment, ...],
    config: StoreConfig,
    captured: list[tuple[WorkItem, str | None]],
    monkeypatch: pytest.MonkeyPatch,
    subject: _Subject,
) -> None:
    def capture(
        *, path: StoreConfig, item: WorkItem, checklist: object, plan_parent_id: str | None
    ) -> object:
        _ = checklist
        captured.append((item, plan_parent_id))
        append_work_item(path=path, item=item)
        if plan_parent_id is not None:
            client.add_dependency(
                from_id=item.id, to_id=plan_parent_id, edge_type=EDGE_PARENT_CHILD
            )
        return IOSuccess("ready")

    def configured_store(*, repo: Path) -> StoreConfig:
        _ = repo
        return config

    def source_comments(*, path: StoreConfig, work_item_id: str) -> tuple[WorkItemComment, ...]:
        _ = (path, work_item_id)
        return comments

    def successor_id(*, prefix: str) -> str:
        assert prefix == "bd-ib"
        return "bd-ib-new"

    monkeypatch.setattr(subject, "store_config", configured_store)
    monkeypatch.setattr(subject, "read_work_item_comments", source_comments)
    monkeypatch.setattr(subject, "file_captured_work_item", capture)
    monkeypatch.setattr(subject, "new_work_item_id", successor_id)
    monkeypatch.setattr(subject, "utc_now_iso", lambda: "2026-11-14T00:00:00Z")


def _assert_missing_item(
    *, subject: _Subject, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert subject.run_supersede_contaminated_command(args=_args(tmp_path=tmp_path)) == 3
    assert "not in the tenant" in capsys.readouterr().err


def _assert_capture_failure(
    *,
    monkeypatch: pytest.MonkeyPatch,
    subject: _Subject,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    poisoned = (WorkItemComment(text="{{ proof", author=None, created_at=None),)

    def source_comments(*, path: StoreConfig, work_item_id: str) -> tuple[WorkItemComment, ...]:
        _ = (path, work_item_id)
        return poisoned

    def successor_id(*, prefix: str) -> str:
        assert prefix == "bd-ib"
        return "bd-ib-new"

    def failed_capture(**kwargs: object) -> object:
        _ = kwargs
        return IOFailure(Exception("nope"))

    monkeypatch.setattr(subject, "read_work_item_comments", source_comments)
    monkeypatch.setattr(subject, "new_work_item_id", successor_id)
    monkeypatch.setattr(subject, "file_captured_work_item", failed_capture)
    assert subject.run_supersede_contaminated_command(args=_args(tmp_path=tmp_path)) == 1
    assert "successor bd-ib-new failed at capture filing" in capsys.readouterr().err


def test_supersession_files_a_safe_equivalent_successor_and_repoints_dependents(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The public command preserves work while leaving immutable records behind."""
    subject = _subject()
    config = _config()
    old = _item(item_id="bd-ib-old")
    append_work_item(path=config, item=_item(item_id="bd-ib-prerequisite"))
    append_work_item(path=config, item=old)
    append_work_item(path=config, item=_item(item_id="bd-ib-dependent"))
    append_work_item(path=config, item=_item(item_id="bd-ib-parent"))
    client = make_beads_client(config=config)
    client.add_dependency(from_id="bd-ib-dependent", to_id=old.id, edge_type=EDGE_BLOCKS)
    client.add_dependency(from_id=old.id, to_id="bd-ib-parent", edge_type=EDGE_PARENT_CHILD)
    client.update_issue(
        issue_id=old.id,
        add_labels=["keep:this", "lifecycle:active", "claim:token", "dispatch-record:run"],
    )
    comments = (
        WorkItemComment(
            text="FOR implement ONLY:\nretain {{ raw diagnostic",
            author="operator",
            created_at="2026-11-13T01:00:00Z",
            comment_id="rider-1",
        ),
        WorkItemComment(
            text="clean instruction",
            author="operator",
            created_at="2026-11-13T02:00:00Z",
            comment_id="rider-2",
        ),
        WorkItemComment(
            text="livespec-dispatch-record: receipt",
            author="dispatcher",
            created_at="2026-11-13T03:00:00Z",
            comment_id="receipt-3",
        ),
        WorkItemComment(
            text="livespec-dispatch-record: id unavailable",
            author="dispatcher",
            created_at="2026-11-13T03:00:01Z",
            comment_id=None,
        ),
    )
    captured: list[tuple[WorkItem, str | None]] = []
    _wire_success(
        client=client,
        comments=comments,
        config=config,
        captured=captured,
        monkeypatch=monkeypatch,
        subject=subject,
    )

    assert subject.run_supersede_contaminated_command(args=_args(tmp_path=tmp_path)) == 0
    _assert_capture(captured=captured, old=old)
    successor = _assert_successor(client=client, config=config, old=old)
    _assert_comments_and_journal(client=client, old=old, successor=successor, tmp_path=tmp_path)


@pytest.mark.parametrize(
    ("item", "comments", "expected"),
    [
        (_item(item_id="bd-ib-old", status="done"), (), "closed"),
        (_item(item_id="bd-ib-old", title="{{ title"), (), "title"),
        (_item(item_id="bd-ib-old"), (), "no poisoned ledger comments"),
    ],
)
def test_preconditions_refuse_without_writes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    item: WorkItem,
    comments: tuple[WorkItemComment, ...],
    expected: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Closed, field-poisoned, and clean items cannot enter the mutation path."""
    subject = _subject()
    config = _config()
    append_work_item(path=config, item=item)
    before = make_beads_client(config=config).list_issues()

    def configured_store(*, repo: Path) -> StoreConfig:
        _ = repo
        return config

    def source_comments(*, path: StoreConfig, work_item_id: str) -> tuple[WorkItemComment, ...]:
        _ = (path, work_item_id)
        return comments

    monkeypatch.setattr(subject, "store_config", configured_store)
    monkeypatch.setattr(subject, "read_work_item_comments", source_comments)

    assert subject.run_supersede_contaminated_command(args=_args(tmp_path=tmp_path)) == 3
    assert expected in capsys.readouterr().err
    assert make_beads_client(config=config).list_issues() == before


def test_successor_without_a_plan_parent_keeps_the_capture_parent_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A poisoned independent item does not invent a parent edge."""
    subject = _subject()
    config = _config()
    old = _item(item_id="bd-ib-old")
    append_work_item(path=config, item=old)
    captured: list[tuple[WorkItem, str | None]] = []
    _wire_success(
        client=make_beads_client(config=config),
        comments=(WorkItemComment(text="{{ diagnostic", author=None, created_at=None),),
        config=config,
        captured=captured,
        monkeypatch=monkeypatch,
        subject=subject,
    )

    assert subject.run_supersede_contaminated_command(args=_args(tmp_path=tmp_path)) == 0
    assert captured[0][1] is None


def test_mutation_helpers_ignore_unusable_ledger_values() -> None:
    """Malformed labels and dependency rows are safely ignored."""
    _ = _subject()
    from livespec_orchestrator_beads_fabro.commands._dispatcher_supersede_mutations import (
        copy_labels,
        parent_id,
        replace_inbound_blocks,
    )

    client = make_beads_client(config=_config())
    assert parent_id(record=cast("BeadsRecord", {})) is None
    copy_labels(
        client=client,
        raw=cast("BeadsRecord", {"labels": "not-a-list"}),
        successor_id="bd-ib-successor",
    )
    copy_labels(
        client=client,
        raw=cast("BeadsRecord", {"labels": ["lifecycle:active"]}),
        successor_id="bd-ib-successor",
    )
    malformed = cast(
        BeadsClient,
        SimpleNamespace(
            list_issues=lambda: [cast("BeadsRecord", {"id": None, "dependencies": []})],
            remove_dependency=lambda **_: None,
            add_dependency=lambda **_: None,
        ),
    )
    replace_inbound_blocks(
        client=malformed,
        original_id="bd-ib-old",
        successor_id="bd-ib-successor",
    )


def test_operator_valve_parser_registration_is_owned_by_argument_declarations() -> None:
    """The thin dispatcher delegates this cohesive parser group."""
    _ = _subject()
    from livespec_orchestrator_beads_fabro.commands._dispatcher_operator_valve_arguments import (
        add_operator_valve_subcommands,
    )

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="subcommand")
    add_operator_valve_subcommands(add_parser=subparsers.add_parser)

    assert set(subparsers.choices) == {
        "clear-acp-availability-hold",
        "clear-provider-exhaustion",
        "fresh-ruling",
        "supersede-contaminated",
    }


def test_missing_item_and_capture_or_post_filing_failures_leave_original_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every failure reports the successor when one has been filed."""
    subject = _subject()
    config = _config()

    def configured_store(*, repo: Path) -> StoreConfig:
        _ = repo
        return config

    def no_comments(*, path: StoreConfig, work_item_id: str) -> tuple[WorkItemComment, ...]:
        _ = (path, work_item_id)
        return ()

    monkeypatch.setattr(subject, "store_config", configured_store)
    monkeypatch.setattr(subject, "read_work_item_comments", no_comments)
    _assert_missing_item(subject=subject, tmp_path=tmp_path, capsys=capsys)

    old = _item(item_id="bd-ib-old")
    append_work_item(path=config, item=old)
    assert subject.run_supersede_contaminated_command(args=_args(tmp_path=tmp_path)) == 3
    assert "no poisoned ledger comments" in capsys.readouterr().err
    _assert_capture_failure(
        monkeypatch=monkeypatch,
        subject=subject,
        tmp_path=tmp_path,
        capsys=capsys,
    )

    def capture(*, path: StoreConfig, item: WorkItem, **_: object) -> object:
        append_work_item(path=path, item=item)
        return IOSuccess("ready")

    monkeypatch.setattr(subject, "file_captured_work_item", capture)
    monkeypatch.setattr(
        subject,
        "_copy_labels",
        _failed_copy_labels,
    )
    assert subject.run_supersede_contaminated_command(args=_args(tmp_path=tmp_path)) == 1
    assert "successor bd-ib-new failed at" in capsys.readouterr().err
    records = {record.id: record for record in read_work_items(path=config)}
    assert records[old.id].status == "ready"
    assert "bd-ib-new" in records
