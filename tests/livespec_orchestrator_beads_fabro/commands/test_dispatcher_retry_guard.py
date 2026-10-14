"""Tests for the pre-dispatch named-change retry guard.

THE UNARMED CASE IS THE POSITIVE CONTROL, and it is first for that reason:
without it a guard that refused every dispatch would satisfy every other case in
this module. Every armed case therefore sits beside a selection whose timeline
carries no signature and costs no refusal.

THE REFUSAL IS DRIVEN THROUGH THE REAL WALL in the case that claims "before any
Fabro run is created". The wall is the one sequence both dispatch paths run after
selection and before admission, so a refusal returning from it is a refusal that
reached no `admit_and_select`: nothing moved `ready -> active`, no assignee was
set and no run was launched. Asserting that against the guard function alone
would be asserting a return value, not a position.

THE SOURCE-MODULE COMPARISON IS ASSERTED IN ALL FOUR OF ITS OUTCOMES, with the
two builds' copies written as real files under two real roots. A clause that
reported "byte-identical" for an unread file would pass a single-case test, and
`UNDETERMINED` and "identical" support opposite conclusions about whether a
re-dispatch will meet the same decision.
"""

from __future__ import annotations

import argparse
import importlib
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands import dispatcher
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_pre_dispatch_wall import (
    pre_dispatch_wall_exit,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-guard"
_COMMANDS_DIR = Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_retry_guard"
_RECORDS_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_retry_records"
_REFUSAL_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_retry_refusal"
_ENGINE_MODULE = "scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_engine.py"
_EXIT_PRECONDITION_ERROR = 3


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _module() -> ModuleType:
    assert (_COMMANDS_DIR / "_dispatcher_retry_guard.py").is_file()
    return importlib.import_module(_MODULE_NAME)


def _records() -> ModuleType:
    return importlib.import_module(_RECORDS_MODULE_NAME)


def _refusal_module() -> ModuleType:
    assert (_COMMANDS_DIR / "_dispatcher_retry_refusal.py").is_file()
    return importlib.import_module(_REFUSAL_MODULE_NAME)


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
        title="Guarded item",
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


def _build(*, root: str) -> Any:
    return _records().ExecutingBuild(version="0.196.1", plugin_root=root)


def _seed_signature(*, stage: str = "fabro-run", plugin_root: str = "/cache/old") -> None:
    records = _records()
    make_beads_client(config=_config()).add_comment(
        issue_id=_ITEM_ID,
        body=records.render_retry_record(
            record=records.RetryRecord(
                kind=records.REFUSAL_SIGNATURE_KIND,
                stage=stage,
                error_class="deterministic",
                build=records.ExecutingBuild(version="0.187.0", plugin_root=plugin_root),
                recorded_at="2026-10-13T23:20:01Z",
            )
        ),
    )


def _args(*, because: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(because=because)


def _module_root(*, tmp_path: Path, name: str, payload: bytes) -> str:
    root = tmp_path / name
    target = root / _ENGINE_MODULE
    target.parent.mkdir(parents=True)
    _ = target.write_bytes(payload)
    return str(root)


def test_an_unarmed_item_costs_no_refusal(tmp_path: Path) -> None:
    module = _module()
    append_work_item(path=_config(), item=_item())
    journal = _RecordingJournal()

    refusal = module.retry_discipline_refusal(
        args=_args(),
        repo=_repo(tmp_path),
        items=[_item()],
        journal=journal,
        build=_build(root="/cache/new"),
    )

    assert refusal is None
    assert journal.records == []


def test_an_empty_selection_costs_no_read(tmp_path: Path) -> None:
    module = _module()

    assert (
        module.retry_discipline_refusal(
            args=_args(),
            repo=_repo(tmp_path),
            items=[],
            journal=_RecordingJournal(),
            build=_build(root="/cache/new"),
        )
        is None
    )


def test_a_comment_that_is_not_a_retry_record_leaves_the_guard_unarmed(tmp_path: Path) -> None:
    module = _module()
    append_work_item(path=_config(), item=_item())
    make_beads_client(config=_config()).add_comment(
        issue_id=_ITEM_ID, body="livespec-dispatch-factory: hp"
    )

    assert (
        module.retry_discipline_refusal(
            args=_args(),
            repo=_repo(tmp_path),
            items=[_item()],
            journal=_RecordingJournal(),
            build=_build(root="/cache/new"),
        )
        is None
    )


def test_a_recorded_signature_refuses_quoting_it_and_naming_the_because_argument(
    tmp_path: Path,
) -> None:
    module = _module()
    append_work_item(path=_config(), item=_item())
    _seed_signature()
    journal = _RecordingJournal()

    refusal = module.retry_discipline_refusal(
        args=_args(),
        repo=_repo(tmp_path),
        items=[_item()],
        journal=journal,
        build=_build(root="/cache/new"),
    )

    assert refusal is not None
    assert f"dispatch of {_ITEM_ID} refused" in refusal
    assert "most recent recorded dispatch outcome is a refusal signature" in refusal
    assert "refusing stage or admission: fabro-run" in refusal
    assert "error class: deterministic" in refusal
    assert "orchestrator build: 0.187.0" in refusal
    assert "recorded at: 2026-10-13T23:20:01Z" in refusal
    assert '--because "<what changed>"' in refusal
    assert journal.records[0]["stage"] == module.RETRY_REFUSED_STAGE
    assert journal.records[0]["refusing_stage"] == "fabro-run"
    assert journal.records[0]["blocking"] is True


def test_the_pre_dispatch_wall_refuses_an_armed_item_before_any_run_is_created(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    append_work_item(path=_config(), item=_item())
    _seed_signature()
    repo = _repo(tmp_path)

    exit_code = pre_dispatch_wall_exit(
        args=argparse.Namespace(
            because=None,
            repo=str(repo),
            workflow=None,
            workflow_name=None,
            factory=None,
            fabro_bin="fabro",
        ),
        repo=repo,
        items=[_item()],
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
    )

    assert exit_code == _EXIT_PRECONDITION_ERROR
    assert "most recent recorded dispatch outcome is a refusal signature" in capsys.readouterr().err


def test_a_whitespace_only_reason_is_refused_as_naming_no_change(tmp_path: Path) -> None:
    module = _module()

    refusal = module.retry_discipline_refusal(
        args=_args(because="   \t "),
        repo=_repo(tmp_path),
        items=[_item()],
        journal=_RecordingJournal(),
        build=_build(root="/cache/new"),
    )

    assert refusal is not None
    assert "empty reason" in refusal
    assert "must name what changed since the recorded failure" in refusal


def test_identical_module_copies_are_reported_as_byte_identical(tmp_path: Path) -> None:
    module = _module()
    append_work_item(path=_config(), item=_item())
    old = _module_root(tmp_path=tmp_path, name="old", payload=b"def gate(): ...\n")
    new = _module_root(tmp_path=tmp_path, name="new", payload=b"def gate(): ...\n")
    _seed_signature(plugin_root=old)

    refusal = module.retry_discipline_refusal(
        args=_args(),
        repo=_repo(tmp_path),
        items=[_item()],
        journal=_RecordingJournal(),
        build=_build(root=new),
    )

    assert refusal is not None
    assert f"copies of {_ENGINE_MODULE} are BYTE-IDENTICAL" in refusal


def test_differing_module_copies_are_reported_as_not_byte_identical(tmp_path: Path) -> None:
    module = _module()
    append_work_item(path=_config(), item=_item())
    old = _module_root(tmp_path=tmp_path, name="old", payload=b"def gate(): ...\n")
    new = _module_root(tmp_path=tmp_path, name="new", payload=b"def gate(): return 1\n")
    _seed_signature(plugin_root=old)

    refusal = module.retry_discipline_refusal(
        args=_args(),
        repo=_repo(tmp_path),
        items=[_item()],
        journal=_RecordingJournal(),
        build=_build(root=new),
    )

    assert refusal is not None
    assert f"copies of {_ENGINE_MODULE} are NOT byte-identical" in refusal


def test_an_unreadable_recording_copy_leaves_the_comparison_undetermined(tmp_path: Path) -> None:
    module = _module()
    append_work_item(path=_config(), item=_item())
    new = _module_root(tmp_path=tmp_path, name="new", payload=b"def gate(): ...\n")
    _seed_signature(plugin_root=str(tmp_path / "evicted"))

    refusal = module.retry_discipline_refusal(
        args=_args(),
        repo=_repo(tmp_path),
        items=[_item()],
        journal=_RecordingJournal(),
        build=_build(root=new),
    )

    assert refusal is not None
    assert "UNDETERMINED" in refusal
    assert "recording build's copy" in refusal


def test_a_stage_with_no_declared_module_leaves_the_comparison_undetermined(
    tmp_path: Path,
) -> None:
    module = _module()
    append_work_item(path=_config(), item=_item())
    _seed_signature(stage="some-stage-no-build-declares")

    refusal = module.retry_discipline_refusal(
        args=_args(),
        repo=_repo(tmp_path),
        items=[_item()],
        journal=_RecordingJournal(),
        build=_build(root="/cache/new"),
    )

    assert refusal is not None
    assert "names no source module this build can locate" in refusal


def test_an_unreadable_timeline_fails_closed(tmp_path: Path) -> None:
    module = _module()
    journal = _RecordingJournal()
    repo = tmp_path / "unconfigured"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text("{}", encoding="utf-8")

    refusal = module.retry_discipline_refusal(
        args=_args(),
        repo=repo,
        items=[_item()],
        journal=journal,
        build=_build(root="/cache/new"),
    )

    assert refusal is not None
    assert "UNDETERMINED" in refusal
    assert "fails closed" in refusal
    assert journal.records[0]["stage"] == module.RETRY_UNREADABLE_STAGE


def test_an_item_absent_from_the_tenant_has_a_readable_empty_timeline(tmp_path: Path) -> None:
    module = _module()

    assert (
        module.retry_discipline_refusal(
            args=_args(),
            repo=_repo(tmp_path),
            items=[_item()],
            journal=_RecordingJournal(),
            build=_build(root="/cache/new"),
        )
        is None
    )


def test_both_builds_unreadable_names_both_in_one_undetermined_clause() -> None:
    assert _refusal_module().module_identity_clause(
        module=_ENGINE_MODULE, recorded=None, executing=None
    ) == (
        "Source-module comparison: UNDETERMINED — the recording and executing "
        f"build's copy of {_ENGINE_MODULE} could not be read."
    )


def test_dispatch_loop_and_probe_accept_a_because_argument() -> None:
    parser = dispatcher._build_parser()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    for subcommand, extra in (("dispatch", []), ("loop", ["--budget", "1"]), ("probe", [])):
        args = parser.parse_args(
            [subcommand, "--repo", ".", "--item", _ITEM_ID, *extra, "--because", "a named change"]
        )
        assert args.because == "a named change"


def test_a_named_change_recorded_with_no_injected_instant_still_carries_one(
    tmp_path: Path,
) -> None:
    """The production clock is the default, and the record must never be undated.

    Every other named-change case injects an instant so its bytes are
    deterministic, which leaves the DEFAULT unexercised — and an undated record
    is one the next refusal quotes with an empty `recorded at` line.
    """
    module = _module()
    append_work_item(path=_config(), item=_item())
    _seed_signature()
    journal = _RecordingJournal()

    refusal = module.retry_discipline_refusal(
        args=_args(because="rebound the session"),
        repo=_repo(tmp_path),
        items=[_item()],
        journal=journal,
        build=_build(root="/cache/new"),
    )

    assert refusal is None
    assert journal.records[0]["stage"] == module.RETRY_NAMED_CHANGE_STAGE
    assert str(journal.records[0]["recorded_at"]).endswith("Z")
