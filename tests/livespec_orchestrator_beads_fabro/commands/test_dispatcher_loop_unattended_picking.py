"""The loop command decides unattended picking from the admission verdict alone.

Binds the second Definition-of-Done assertion of work-item `bd-ib-qm6r1`, the
v127 retirement recorded in `SPECIFICATION/contracts.md` — cited at FILE level,
because a heading-level citation rots the moment the heading is reworded. That
revision deleted the rule that an unresolved projection-failure fact stops
unattended picking, so the posture value the loop consulted has no remaining
clause to realize and its module is removed rather than left standing with its
one caller gone.

THE ABSENCE IS ASSERTED THREE WAYS, because each catches a different half-done
retirement. The module FILE is gone, so no later caller can import it back. The
module is unimportable, which is what a stale `__pycache__` or a re-export shim
would otherwise hide. And the loop command's own source names neither the
posture nor its stop-picking rule, which is the one instrument that would catch
a gate re-expressed inline under a different spelling.

THE BEHAVIOURAL CONTROL IS THE INVERSE OF THE TEST THIS REPLACES. The deleted
`test_the_unattended_drain_stops_before_reaching_the_dispatch_wave` asserted
that an unattended pass over a journal holding one of these facts never reached
the dispatch wave; the case below asserts that it DOES, over a journal holding
the same record. Without it, the three absences above are equally consistent
with a build that moved the same gate somewhere this module cannot see.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_loop_command,
    _dispatcher_pre_dispatch_wall,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import invoker_from_args
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_POSTURE_MODULE = "_acp_projection_posture"
_LOOP_MODULE = "_dispatcher_loop_command"

# Every spelling the retired gate reached the loop command through, plus the
# two journal stages it wrote. A gate re-expressed inline would have to carry
# one of them to mean anything to an operator reading the journal.
_RETIRED_NAMES: tuple[str, ...] = (
    "acp_projection_posture",
    _POSTURE_MODULE,
    "stop_picking",
    "acp-projection-picking-stopped",
    "acp-projection-warning-surfaced",
)

_RUN_ID = "01M59F19ZP2HA6YD7JZ4M1QSE2"
_REPO_NAME = "livespec-orchestrator-beads-fabro"


def _failure_record() -> dict[str, object]:
    """One `acp-projection-failure` line as the retired writer appended it.

    Transcribed rather than built: the writer is retired, so composing the
    record through its own builder would bind this case to a module whose
    deletion is the point.
    """
    return {
        "at": "2026-10-19T09:58:07Z",
        "invoker": "machine:dispatcher",
        "invoker_source": "fallback",
        "stage": "acp-projection-failure",
        "fact_id": f"hygiene:model-fallback-projection:{_REPO_NAME}:{_RUN_ID}:implement",
        "repo": _REPO_NAME,
        "run_id": _RUN_ID,
        "node": "implement",
        "factory_name": "petri",
        "factory_server_url": "https://gmktec.perch-rudd.ts.net:32276",
        "reason": "timed-out",
        "exit_code": 124,
    }


def test_the_posture_module_file_is_gone() -> None:
    """No caller can import a stop-picking gate that has no module."""
    assert not (_COMMANDS / f"{_POSTURE_MODULE}.py").is_file()


def test_the_posture_module_is_unimportable() -> None:
    """The file's absence is not a stale bytecode cache still answering for it."""
    assert importlib.util.find_spec(f"{_PACKAGE}.{_POSTURE_MODULE}") is None


def test_the_loop_commands_source_names_no_posture_and_no_stop_picking_rule() -> None:
    """A gate re-expressed inline would still have to spell one of these."""
    source = (_COMMANDS / f"{_LOOP_MODULE}.py").read_text(encoding="utf-8")
    assert [name for name in _RETIRED_NAMES if name in source] == []


def _loop_args(*, repo: Path, journal: Path) -> argparse.Namespace:
    """An UNATTENDED pass: `--item` is empty, which is what `items=None` means."""
    return argparse.Namespace(
        repo=str(repo),
        journal=str(journal),
        items=None,
        budget=1,
        as_json=False,
        dry_run=False,
        skip_ledger_check=True,
        workflow_name=None,
    )


def _journal_holding_a_failure_fact(*, tmp_path: Path) -> Path:
    path = tmp_path / "tmp" / "fabro-dispatch-journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(_failure_record(), sort_keys=True) + "\n", encoding="utf-8")
    return path


def _stub_loop_around_selection(
    *, monkeypatch: pytest.MonkeyPatch, args: argparse.Namespace, waves: list[int]
) -> None:
    """Stub every loop seam that leaves the process, leaving the pass itself live.

    The journal is the PRODUCTION `JournalFile` over the fixture's own path, so
    a pass that wrote a record about its posture would really append one and
    the assertion below reads the file rather than a stub's memory.
    """
    journal = JournalFile(path=Path(args.journal), identity=invoker_from_args(args=args))
    module = _dispatcher_loop_command
    monkeypatch.setattr(module, "dispatch_preamble", lambda **_kwargs: (None, None))
    monkeypatch.setattr(module, "arm_otel_egress", lambda **_kwargs: None)
    monkeypatch.setattr(module, "prepare", lambda **_kwargs: ([], journal))
    monkeypatch.setattr(module, "journal_path", lambda **_kwargs: journal.path)
    monkeypatch.setattr(module, "requested_items_preflight_error", lambda **_kwargs: None)
    monkeypatch.setattr(module, "candidates", lambda **_kwargs: [])
    # The criteria wall lives in the SHARED pre-dispatch wall both dispatch
    # paths run, not in the drain's own module; stub it where it is defined.
    monkeypatch.setattr(
        _dispatcher_pre_dispatch_wall, "pre_dispatch_criteria_refusal", lambda **_kwargs: None
    )
    monkeypatch.setattr(module, "dispatch_loop_wave", lambda **_kwargs: waves.append(1) or [])


def test_an_unattended_pass_reaches_the_dispatch_wave_over_such_a_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The inverse of the retired gate's own case: the pass proceeds, silently."""
    path = _journal_holding_a_failure_fact(tmp_path=tmp_path)
    args = _loop_args(repo=tmp_path, journal=path)
    waves: list[int] = []
    _stub_loop_around_selection(monkeypatch=monkeypatch, args=args, waves=waves)

    code = _dispatcher_loop_command.run_loop_command(args=args)

    assert (code, waves) == (0, [1])
    # Silently: the retired gate's whole operator surface was a warning on
    # stderr plus one journal record, so a gate that had merely stopped acting
    # would still leave one of the two behind.
    assert capsys.readouterr().err == ""
    stages = [
        json.loads(line).get("stage")
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert stages == ["acp-projection-failure"]
