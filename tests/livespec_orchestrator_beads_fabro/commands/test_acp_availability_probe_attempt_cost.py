"""Every confirmation turn yields one attempt-cost record, charged to one item.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Cost follows every attempt": "For every run released under
'Provider-limit release and re-dispatch', and for every availability
confirmation turn, the Dispatcher MUST journal one attempt-cost record ...
priced under the rules below, or marked cost-unobservable. ... A shared
availability probe MUST NOT be charged in full to multiple items."

EVERY ENDING YIELDS ONE, which is the breadth an implementation narrows. A
record written only for the turn that CONFIRMED makes the spend of every
refused, exited, cancelled and terminated turn invisible -- and those are the
turns a chain waiting out an outage actually produces, so the narrow reading
loses exactly the spend an operator is asking about.

THE ONE ITEM IS ASSERTED ON THE RECORD ITSELF, because that is the whole of the
mechanism: a confirmation turn establishes availability every peer then benefits
from, and nothing downstream divides a charge -- the sequence fold selects by
the item the record names, so a record naming two items, or none, is the only
way one spend becomes several.

THE REFACTOR THAT MADE ROOM IS ASSERTED AS A SINGLE ACCOUNT. Reading one ended
probe run moved into its own module because the run module was at its file LLOC
ceiling; what matters afterwards is that there is still exactly ONE reading of
an ended run, so the run module is asserted to compose the new entry point
rather than to carry a second copy of it.
"""

from __future__ import annotations

import ast
import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_attempts import (
    ATTEMPT_COST_CONFIRMATION_TURN,
    ATTEMPT_COST_STAGE,
    attempt_cost_identity,
)

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_READING_MODULE = "_acp_availability_probe_reading"
_READING_PATH = _COMMANDS / f"{_READING_MODULE}.py"
_RUN_PATH = _COMMANDS / "_acp_availability_probe_run.py"

_RUN_ID = "01M5PROBE00000000000000000"
_NOW = "2026-10-20T12:30:00Z"
_ITEM = "bd-ib-a2rhtt"
_PEER = "bd-ib-peer"
_FACTORY = "hp"
_PROBE_COST_MICROS = 11

_FACTORIES_CONFIG = """{
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "default_factory": "hp",
      "factories": {
        "hp": {"server": "https://hp.example.ts.net:32276"}
      }
    }
  }
}
"""


@dataclass(kw_only=True)
class _Command:
    exit_code: int
    stdout: str
    stderr: str = ""


@dataclass(kw_only=True)
class _Engine:
    """A fabro runner whose every per-verb answer the case supplies."""

    launch_exit_code: int = 0
    launch_stdout: str = f"Run: {_RUN_ID}\n"
    rm_exit_code: int = 0
    inspect_stdout: str = "[]"
    events_stdout: str = "[]"
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> _Command:
        self.calls.append(list(argv))
        _ = (cwd, timeout_seconds, env)
        if "--version" in argv:
            return _Command(exit_code=0, stdout="fabro 0.254.0 (8869e88 2026-10-01)\n")
        if "inspect" in argv:
            return _Command(exit_code=0, stdout=self.inspect_stdout)
        if "events" in argv:
            return _Command(exit_code=0, stdout=self.events_stdout)
        if "rm" in argv:
            return _Command(exit_code=self.rm_exit_code, stdout="")
        return _Command(exit_code=self.launch_exit_code, stdout=self.launch_stdout)


def _records() -> Any:
    return importlib.import_module(f"{_PACKAGE}._acp_availability_probe_records")


def _candidate() -> Any:
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    return schema.AcpCandidate(
        adapter=adapters.AcpAdapter(command="claude-code-acp"),
        identity=schema.AcpCandidateIdentity(
            display_name="Claude Opus 5",
            candidate_key="claude-opus-5-high",
            availability_key="anthropic",
        ),
    )


def _probe_node() -> str:
    probe = importlib.import_module(f"{_PACKAGE}._acp_availability_probe")
    return str(probe.AVAILABILITY_PROBE_NODE)


def _confirmed_inspect() -> str:
    probe = importlib.import_module(f"{_PACKAGE}._acp_availability_probe")
    return json.dumps(
        [
            {
                "run_id": _RUN_ID,
                "status": {"kind": "succeeded"},
                "total_usd_micros": _PROBE_COST_MICROS,
                "checkpoints": [
                    {"node_outcomes": {probe.AVAILABILITY_PROBE_NODE: {"status": "succeeded"}}}
                ],
            }
        ]
    )


def _probe(*, tmp_path: Path, engine: _Engine, work_item_id: str = _ITEM) -> Any:
    _ = (tmp_path / ".livespec.jsonc").write_text(_FACTORIES_CONFIG, encoding="utf-8")
    module = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_run")
    return module.run_availability_probe(
        repo=tmp_path,
        candidate=_candidate(),
        builtin=True,
        work_item_id=work_item_id,
        observation_ids=(),
        now_iso=_NOW,
        timeout_seconds=120,
        runner=engine,
    )


def _record(*, cost_usd_micros: int | None, work_item_id: str = _ITEM) -> dict[str, object]:
    built = _records().probe_attempt_cost_record(
        work_item_id=work_item_id,
        occurred_at=_NOW,
        factory=_FACTORY,
        run_id=_RUN_ID,
        cost_usd_micros=cost_usd_micros,
    )
    assert isinstance(built, dict), built
    return built


def test_the_confirmation_turns_attempt_cost_record_surface_exists() -> None:
    """The record builder, and the one reading the refactor cut out."""
    assert hasattr(_records(), "probe_attempt_cost_record"), dir(_records())
    assert _READING_PATH.is_file(), _READING_PATH
    reading = importlib.import_module(f"{_PACKAGE}.{_READING_MODULE}")
    assert hasattr(reading, "probe_run_observation"), dir(reading)


def test_the_run_module_composes_the_one_ended_run_reading() -> None:
    """One account of reading an ended run, not two that can disagree.

    Asserted through the import graph rather than as text, because a second
    copy of the reading would still mention the names it reads and a text scan
    cannot tell a call from a comment.
    """
    tree = ast.parse(_RUN_PATH.read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert f"{_PACKAGE}.{_READING_MODULE}" in imported, sorted(imported)


def test_the_record_names_the_confirmation_turn_and_exactly_one_item() -> None:
    """The source, the probe's node attempt, its identity, and the one charge."""
    record = _record(cost_usd_micros=_PROBE_COST_MICROS)
    assert record["stage"] == ATTEMPT_COST_STAGE
    assert record["source"] == ATTEMPT_COST_CONFIRMATION_TURN
    assert record["work_item_id"] == _ITEM
    assert record["node_attempt"] == _probe_node()
    assert record["factory"] == _FACTORY
    assert record["run_id"] == _RUN_ID
    assert record["observation_id"] == attempt_cost_identity(
        source=ATTEMPT_COST_CONFIRMATION_TURN,
        factory=_FACTORY,
        run_id=_RUN_ID,
        node_attempt=_probe_node(),
    )
    assert record["usd_micros"] == _PROBE_COST_MICROS
    assert record["cost_observable"] is True


def test_a_confirmation_shared_by_several_items_is_charged_to_one_of_them() -> None:
    """Two items' records of ONE turn carry one identity and different charges.

    The identity is the turn's own, so a sequence fold that counted both would
    be counting one spend twice -- and the item field is what keeps each fold
    seeing only the record it is charged by.
    """
    charged = _record(cost_usd_micros=_PROBE_COST_MICROS)
    peer = _record(cost_usd_micros=_PROBE_COST_MICROS, work_item_id=_PEER)
    assert charged["observation_id"] == peer["observation_id"]
    assert charged["work_item_id"] != peer["work_item_id"]


def test_a_turn_the_engine_reported_no_figure_for_is_cost_unobservable() -> None:
    """The ORDINARY answer on this fleet, stated rather than inferred."""
    record = _record(cost_usd_micros=None)
    assert record["usd_micros"] is None
    assert record["cost_observable"] is False


@dataclass(frozen=True, kw_only=True)
class _Ending:
    """One confirmation-turn ending, and the figure its record must carry.

    A case object rather than parametrized scalars, because two of them are
    booleans and a boolean parameter position says nothing about which question
    it answers. The timed-out arms spell their exit code through the run
    module's own exported constant rather than a literal beside it, which is
    resolved in the test body because the constant is the runner's own mapping
    of a timeout and a literal here could drift away from it.
    """

    inspect_stdout: str = "[]"
    launch_timed_out: bool = False
    run_id_readable: bool = True
    expect_usd_micros: int | None = None


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            _Ending(inspect_stdout=_confirmed_inspect(), expect_usd_micros=_PROBE_COST_MICROS),
            id="confirmed",
        ),
        pytest.param(_Ending(), id="process-exit"),
        pytest.param(_Ending(launch_timed_out=True), id="timed-out-and-reaped"),
        pytest.param(
            _Ending(launch_timed_out=True, run_id_readable=False), id="timed-out-unnameable"
        ),
    ],
)
def test_every_ending_yields_exactly_one_attempt_cost_record(tmp_path: Path, case: _Ending) -> None:
    """Including the endings that confirm nothing, which still spend.

    The two timed-out arms are not one case repeated: a turn this Dispatcher
    REAPED and one whose run it could not even name both spent an allowance,
    and the second is the arm where every other field of the record is absent
    -- so a builder that skipped the record when it had no run to describe
    would lose exactly the spend nobody else can account for.
    """
    module = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_run")
    engine = _Engine(
        inspect_stdout=case.inspect_stdout,
        launch_exit_code=module.PROBE_LAUNCH_TIMEOUT_EXIT_CODE if case.launch_timed_out else 0,
        launch_stdout=_Engine.launch_stdout
        if case.run_id_readable
        else "the launch printed no run id\n",
    )
    result = _probe(tmp_path=tmp_path, engine=engine)
    assert not isinstance(result, str), result
    record = result.attempt_cost_record
    assert record["stage"] == ATTEMPT_COST_STAGE
    assert record["source"] == ATTEMPT_COST_CONFIRMATION_TURN
    assert record["work_item_id"] == _ITEM
    assert record["occurred_at"] == _NOW
    assert record["factory"] == _FACTORY
    assert record["run_id"] == result.run_id
    assert (record["run_id"] is None) is not case.run_id_readable
    assert record["usd_micros"] == case.expect_usd_micros
    assert record["cost_observable"] is (case.expect_usd_micros is not None)
