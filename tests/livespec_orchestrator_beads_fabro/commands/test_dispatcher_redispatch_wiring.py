"""The wall row, the spend-last ordering, the drain filter and the recording command."""

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_loop_candidates,
    _dispatcher_pre_dispatch_wall,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_redispatch_recovery_command as command,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_pre_dispatch_wall import (
    pre_dispatch_wall_exit,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import _build_parser
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError

_QUIET_ROWS = (
    "out_of_enum_factory_safety_refusal",
    "implementation_pr_override_refusal",
    "acp_node_override_refusal",
    "app_reach_refusal",
    "fabro_currency_refusal",
    "pre_dispatch_criteria_refusal",
    "dod_judgement_refusal",
    "definition_of_done_workflow_refusal",
    "spec_change_tier_refusal",
    "proof_assets_refusal_for_items",
    "proof_credentials_refusal_for_items",
)


def _quiet_wall(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every row but the progress row passes; the headroom row records that it ran."""
    reached: list[str] = []
    for name in _QUIET_ROWS:
        monkeypatch.setattr(_dispatcher_pre_dispatch_wall, name, lambda **_: None)
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall,
        "session_headroom_screen_refusal",
        lambda **_: reached.append("session-headroom") or None,
    )
    monkeypatch.setattr(_dispatcher_pre_dispatch_wall, "credential_wrapper_text", lambda **_: "")
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall,
        "selection_credential_requirement",
        lambda **_: _dispatcher_pre_dispatch_wall.WorkflowFaultDeferral(message="not under test"),
    )
    return reached


def _wall(tmp_path: Path) -> int | None:
    return pre_dispatch_wall_exit(
        args=argparse.Namespace(workflow_name=None),
        repo=tmp_path,
        items=[],
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
    )


def test_the_progress_refusal_precedes_the_rows_that_spend_a_provider_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refused item exits before the headroom screen, and nothing is spent."""
    reached = _quiet_wall(monkeypatch)
    spent: list[Any] = []
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall, "redispatch_progress_refusal", lambda **_: "no progress"
    )
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall,
        "consume_authorized_recoveries",
        lambda **kwargs: spent.append(kwargs),
    )
    assert _wall(tmp_path) == EXIT_PRECONDITION_ERROR
    assert reached == []
    assert spent == []


def test_the_wall_spends_an_admitted_recovery_only_when_every_row_passed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate's authorization list is the one the wall spends, and only at the end."""
    reached = _quiet_wall(monkeypatch)
    spent: list[Any] = []

    def admit(*, authorized: list[tuple[str, str]], **_: object) -> None:
        authorized.append(("bd-ib-x", "rec-1"))

    monkeypatch.setattr(_dispatcher_pre_dispatch_wall, "redispatch_progress_refusal", admit)
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall,
        "consume_authorized_recoveries",
        lambda *, repo, authorized: spent.append((repo, list(authorized))),
    )
    assert _wall(tmp_path) is None
    assert reached == ["session-headroom"]
    assert spent == [(tmp_path, [("bd-ib-x", "rec-1")])]

    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall, "proof_assets_refusal_for_items", lambda **_: "later row"
    )
    spent.clear()
    assert _wall(tmp_path) == EXIT_PRECONDITION_ERROR
    assert spent == []


def test_the_drain_filters_refused_rows_only_when_it_has_a_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pass handed a journal applies the gate's filter; one handed none does not."""
    calls: list[Any] = []

    def fake_filter(*, items: Any, repo: Path, journal: Any) -> list[str]:
        calls.append((list(items), repo, journal))
        return ["kept"]

    monkeypatch.setattr(_dispatcher_loop_candidates, "redispatch_unrefused_candidates", fake_filter)
    args = argparse.Namespace(items=None, workflow_name=None)
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    assert _dispatcher_loop_candidates.candidates(args=args, items=[], repo=tmp_path) == []
    assert calls == []
    kept = _dispatcher_loop_candidates.candidates(
        args=args,
        items=[],
        repo=tmp_path,
        journal=journal,
    )
    assert kept == ["kept"]
    assert calls == [([], tmp_path, journal)]


def _argv(**overrides: str) -> list[str]:
    fields = {
        "--repo": "/repo",
        "--item": "bd-ib-x",
        "--attempt-id": "rec-1",
        "--diagnosis": "stale fixture",
        "--operation": "dispatch --item bd-ib-x",
        "--execution-evidence": "receipt-1",
    }
    fields.update(overrides)
    argv = ["record-redispatch-recovery", "--prior-run", "r1", "--prior-run", "r2"]
    for flag, value in fields.items():
        argv.extend((flag, value))
    return argv


def _command(
    monkeypatch: pytest.MonkeyPatch, *, existing: tuple[str, ...] = (), **overrides: str
) -> tuple[int, list[tuple[str, str]], str]:
    written: list[tuple[str, str]] = []
    out: list[str] = []
    monkeypatch.setattr(command, "store_config", lambda **_: "config")
    monkeypatch.setattr(
        command,
        "read_work_item_comments",
        lambda **_: tuple(SimpleNamespace(text=text) for text in existing),
    )
    monkeypatch.setattr(
        command,
        "append_work_item_comment",
        lambda *, work_item_id, body, **_: written.append((work_item_id, body)),
    )
    monkeypatch.setattr(command, "write_stderr", lambda *, text: out.append(text))
    monkeypatch.setattr(command, "write_stdout", lambda *, text: out.append(text))
    args = _build_parser().parse_args(_argv(**overrides))
    return command.run_record_redispatch_recovery_command(args=args), written, "".join(out)


def test_the_command_records_a_typed_recovery_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    """A complete, fresh attempt is appended to the item's comments."""
    code, written, out = _command(monkeypatch)
    assert code == 0
    assert out == "recorded redispatch recovery attempt rec-1\n"
    assert len(written) == 1
    assert written[0][0] == "bd-ib-x"
    assert '"prior_run_ids": ["r1", "r2"]' in written[0][1]


@pytest.mark.parametrize(
    ("overrides", "needle"),
    [
        ({"--diagnosis": "  "}, "requires measured diagnosis"),
        ({"--operation": "go {{ now }}"}, "template opener"),
        ({"--attempt-id": "rec-1", "--execution-evidence": ""}, "requires execution evidence"),
    ],
)
def test_the_command_refuses_incomplete_or_unwritable_attempts(
    monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str], needle: str
) -> None:
    """Nothing is written for prose-only or template-bearing records."""
    code, written, out = _command(monkeypatch, **overrides)
    assert code == EXIT_PRECONDITION_ERROR
    assert written == []
    assert needle in out


def test_the_command_refuses_empty_prior_runs_and_reused_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blank run ids and an id already recorded or spent are refused."""
    args = _build_parser().parse_args([*_argv(), "--prior-run", " "])
    monkeypatch.setattr(command, "store_config", lambda **_: "config")
    out: list[str] = []
    monkeypatch.setattr(command, "write_stderr", lambda *, text: out.append(text))
    assert command.run_record_redispatch_recovery_command(args=args) == EXIT_PRECONDITION_ERROR
    assert "non-empty prior run ids" in "".join(out)

    recorded = 'livespec-redispatch-recovery-attempt\n{"attempt_id": "rec-1", "prior_run_ids": [], "diagnosis": "d", "operation": "o", "execution_evidence": "e"}'
    spent = 'livespec-redispatch-recovery-consumed\n{"attempt_id": "rec-1"}'
    for existing in ((recorded,), (spent,)):
        code, written, text = _command(monkeypatch, existing=existing)
        assert code == EXIT_PRECONDITION_ERROR
        assert written == []
        assert "already used" in text


def test_the_command_reports_an_unreadable_ledger(monkeypatch: pytest.MonkeyPatch) -> None:
    """A ledger read fault refuses instead of writing blind."""
    _ = _command(monkeypatch)

    def boom(**_: object) -> tuple[()]:
        raise BeadsCommandError(command="bd comments", exit_code=1, stderr="down")

    monkeypatch.setattr(command, "read_work_item_comments", boom)
    out: list[str] = []
    monkeypatch.setattr(command, "write_stderr", lambda *, text: out.append(text))
    args = _build_parser().parse_args(_argv())
    assert command.run_record_redispatch_recovery_command(args=args) == EXIT_PRECONDITION_ERROR
    assert "could not be read" in "".join(out)
