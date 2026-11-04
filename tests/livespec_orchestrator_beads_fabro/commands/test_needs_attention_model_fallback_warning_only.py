"""The model-fallback attention lane composes the warning fact and nothing else.

Binds the fourth Definition-of-Done assertion of work-item `bd-ib-qm6r1` against
`SPECIFICATION/contracts.md` — cited at FILE level, because a heading-level
citation rots the moment the heading is reworded. v127 deleted the
`hygiene:model-fallback-projection` fact along with the `agent.acp.failover`
projection that minted it, leaving the section naming exactly one fact for this
lane: "one aggregate attention fact per repository/node with id
`hygiene:model-fallback:<repo>:<node>`".

THE JOURNAL CARRIES BOTH KINDS OF RECORD, which is what makes the case able to
fail. A fixture holding only the warning would be satisfied by a lane that
composed nothing at all from the retired record because no such record was
there to compose from; this one holds a retired projection-failure line beside
the warning, so the lane must read past it.

AND THE WARNING ROW IS ASSERTED IN FULL BESIDE THAT ABSENCE. "Composes only the
warning fact" is satisfied just as well by a lane that composes nothing, so the
surviving row's id, kind, source reference and executable handoff are checked in
the same breath as the retired one's absence.

THE CLEARANCE VALVE GOES WITH THE FACT IT CLEARED. A valve whose only subject is
a retired fact can refuse every invocation and nothing else; leaving it
registered would leave an operator a documented command that cannot succeed, and
leaving its module importable would leave the refusal one subparser line from
returning.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._needs_attention_model_fallback import (
    model_fallback_items,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main as dispatcher_main

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_CLEAR_MODULE = "_acp_projection_clear"
_CLEAR_SUBCOMMAND = "clear-model-fallback-projection"

_REPO_NAME = "livespec-orchestrator-beads-fabro"
_RUN_ID = "01M3R750MNDHENDYKY5MBKRYXJ"
_HP_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_OCCURRED = "2026-09-12T12:00:00Z"
_NODE = "implement"

_RETIRED_FACT_ID = f"hygiene:model-fallback-projection:{_REPO_NAME}:{_RUN_ID}:{_NODE}"
_WARNING_FACT_ID = f"hygiene:model-fallback:{_REPO_NAME}:{_NODE}"


def _retired_projection_line() -> dict[str, Any]:
    """An `acp-projection-failure` line as the retired writer appended it.

    Transcribed, because the writer and its record builder are both retired:
    building it through them would bind this case to code that is gone.
    """
    return {
        "at": _OCCURRED,
        "invoker": "machine:dispatcher",
        "stage": "acp-projection-failure",
        "fact_id": _RETIRED_FACT_ID,
        "repo": _REPO_NAME,
        "run_id": _RUN_ID,
        "node": _NODE,
        "factory_name": "hp",
        "factory_server_url": _HP_SERVER,
        "reason": "timed-out",
        "exit_code": 124,
    }


def _warning_line() -> dict[str, Any]:
    """One `acp-model-fallback-observed` line: the fact this lane still composes."""
    return {
        "at": _OCCURRED,
        "invoker": "machine:dispatcher",
        "stage": "acp-model-fallback-observed",
        "schema_version": 1,
        "warning_id": "acpwarn-live",
        "node": _NODE,
        "occurred_at": _OCCURRED,
        "candidate_display_name": "GLM ACP Agent GLM 5.1",
        "candidate_key": "glm-5-1",
        "availability_key": "codex",
        "hold_key": "codex",
        "cause": "quota",
        "scope": "availability-domain",
        "primary_generation": "gen-a",
        "full_chain": "chain-1",
        "event_id": "ev-live",
        "candidate_index": 1,
        "work_item_id": "bd-ib-qm6r1",
    }


def _journal(*, tmp_path: Path, records: tuple[dict[str, Any], ...]) -> Path:
    path = tmp_path / "tmp" / "fabro-dispatch-journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8"
    )
    return path


def test_the_lane_composes_the_warning_row_and_no_projection_row(tmp_path: Path) -> None:
    """One journal, both records, one row — and it is the surviving fact's."""
    _ = _journal(tmp_path=tmp_path, records=(_retired_projection_line(), _warning_line()))

    rows = model_fallback_items(project_root=tmp_path, repo=_REPO_NAME)

    assert [row.id for row in rows] == [_WARNING_FACT_ID]
    [row] = rows
    assert (row.kind, row.urgency) == ("hygiene", "medium")
    assert row.source_ref.repo == _REPO_NAME
    assert row.source_ref.path == "tmp/fabro-dispatch-journal.jsonl"
    assert row.source_ref.work_item == "bd-ib-qm6r1"
    assert row.handoff.kind == "shell"
    assert "acp-model-fallback" in row.handoff.command
    assert _NODE in row.handoff.command
    assert "GLM ACP Agent GLM 5.1" in row.summary


def test_a_journal_holding_only_retired_projection_records_composes_no_rows(
    tmp_path: Path,
) -> None:
    """The absence on its own, so the row above cannot be masking a retired one."""
    _ = _journal(tmp_path=tmp_path, records=(_retired_projection_line(),))

    assert model_fallback_items(project_root=tmp_path, repo=_REPO_NAME) == []


def test_the_clearance_valve_module_file_is_gone() -> None:
    """A valve whose only subject is retired can refuse and nothing else."""
    assert not (_COMMANDS / f"{_CLEAR_MODULE}.py").is_file()


def test_the_clearance_valve_module_is_unimportable() -> None:
    """The file's absence is not a stale bytecode cache still answering."""
    assert importlib.util.find_spec(f"{_PACKAGE}.{_CLEAR_MODULE}") is None


def test_the_dispatcher_registers_no_clearance_subcommand() -> None:
    """An operator is left no documented command that cannot succeed."""
    with pytest.raises(SystemExit) as refused:
        _ = dispatcher_main(argv=[_CLEAR_SUBCOMMAND, "--fact-id", "x", "--reason", "y"])

    assert refused.value.code == 2


def test_the_two_sibling_clearance_valves_are_untouched(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The control: this retirement removes ONE valve, not the family.

    The legacy provider-exhaustion valve and the typed availability-hold valve
    retire records that still exist, so a build that had removed the whole
    clearance family would satisfy every absence above. Read off the help text
    an operator reads, which is the surface that advertises a subcommand.
    """
    with pytest.raises(SystemExit) as helped:
        _ = dispatcher_main(argv=["--help"])
    usage = capsys.readouterr().out

    assert helped.value.code == 0
    assert "clear-provider-exhaustion" in usage
    assert "clear-acp-availability-hold" in usage
    assert _CLEAR_SUBCOMMAND not in usage
