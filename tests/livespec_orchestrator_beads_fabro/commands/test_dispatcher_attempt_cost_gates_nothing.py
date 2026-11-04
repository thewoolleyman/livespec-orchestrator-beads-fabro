"""An attempt-cost record observes and gates nothing — structurally, not by care.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Cost follows every attempt": "Attempt-cost records are
observations only and never yield a gate verdict; terminally unsuccessful runs
otherwise retain the existing no-gate posture." And Scenario 45's own line: "a
provider-limit-released run still yields its attempt-cost observation / And the
Dispatcher does not refuse on that observation's account."

THE STRICTEST POSTURE IS WHAT IS DRIVEN, because a weaker one proves nothing. In
`report` mode the gate refuses nothing at all, so a record that DID gate would
be invisible there; every case below runs `enforce` on an UNATTENDED drain,
which is the one combination in which the gate genuinely refuses -- and the
green control at the bottom shows it refusing, so the absences above it are
about the released run's status rather than about a gate that had stopped
working.

THE IMPORT GRAPH IS ASSERTED OVER A STATED SCOPE, which is the only instrument
that can see a verdict re-expressed somewhere this file does not look. "The
record gates nothing" is a claim about what the record's own modules can
REACH: a module that cannot import a gate cannot produce a verdict, whatever
its fields are called, and a per-field assertion would keep passing after a
later edit grew one.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost import (
    COST_MODE_ENFORCE,
    gate_wave,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_attempts import (
    ATTEMPT_COST_RELEASED_RUN,
    ATTEMPT_COST_STAGE,
    attempt_cost_identity,
    attempt_cost_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_sequence import (
    attempt_cost_observations,
    sequence_cost,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_outcome import (
    PROVIDER_LIMIT_RELEASE_STATUS,
)

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)

# The record's own two modules: what renders one, and what folds a sequence of
# them. The scope this file asserts its absence claim over.
_RECORD_MODULES = ("_dispatcher_cost_attempts", "_dispatcher_cost_sequence")

# Every module that can produce a cost GATE verdict. A record module reaching
# any of them could refuse a dispatch.
_GATE_MODULES = ("_dispatcher_cost", "_dispatcher_cost_gate", "_dispatcher_cost_wave")

_ITEM = "bd-ib-observes"
_FACTORY = "hp"
_RUN = "01RELEASEDRUNOFANITEM"


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)

    def of_stage(self, *, stage: str) -> list[dict[str, object]]:
        return [one for one in self.records if one.get("stage") == stage]


def _outcome(*, status: str) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM,
        status=status,
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="",
        fabro_run_id=_RUN,
    )


def _ps_json() -> str:
    """A listing in which this item's run IS resolvable, so the gate can act.

    The goal text carries the attribution's own `Work-item: <id>` form; a run
    the attribution cannot place is journaled as a SKIPPED gate, which is a
    different absence from the one this file is about.
    """
    return json.dumps([{"run_id": _RUN, "goal": f"Work-item: {_ITEM}", "total_usd_micros": None}])


def _released_attempt_cost() -> dict[str, object]:
    return attempt_cost_record(
        source=ATTEMPT_COST_RELEASED_RUN,
        work_item_id=_ITEM,
        factory=_FACTORY,
        run_id=_RUN,
        node_attempt="implement",
        occurred_at="2026-10-12T09:10:00Z",
        windows=(),
        usd_micros=None,
    )


def _gated(*, status: str, journal: _RecordingJournal) -> tuple[str, ...]:
    """The strictest posture: `enforce`, on an unattended drain."""
    return gate_wave(
        unattended=True,
        outcomes=(_outcome(status=status),),
        ps_json=_ps_json(),
        journal=journal,
        environ={},
        cost_mode=COST_MODE_ENFORCE,
    )


def test_a_released_runs_attempt_cost_record_yields_no_gate_verdict() -> None:
    """Scenario 45's own line: the observation lands, the Dispatcher does not refuse."""
    journal = _RecordingJournal()
    journal.append(record=_released_attempt_cost())

    refusals = _gated(status=PROVIDER_LIMIT_RELEASE_STATUS, journal=journal)

    assert refusals == ()
    assert journal.of_stage(stage="cost-gate") == []
    assert journal.of_stage(stage="cost-gate-skipped") == []
    observed = journal.of_stage(stage=ATTEMPT_COST_STAGE)
    assert len(observed) == 1
    assert observed[0]["observation_id"] == attempt_cost_identity(
        source=ATTEMPT_COST_RELEASED_RUN,
        factory=_FACTORY,
        run_id=_RUN,
        node_attempt="implement",
    )


def test_the_gate_is_live_in_the_same_posture_a_released_run_passes_through() -> None:
    """The control: a green run with an unobservable cost DOES refuse here.

    Without it, every absence above is equally consistent with a gate that had
    stopped deriving verdicts at all.
    """
    journal = _RecordingJournal()
    journal.append(record=_released_attempt_cost())

    refusals = _gated(status="green", journal=journal)

    assert refusals == (_ITEM,)
    gated = journal.of_stage(stage="cost-gate")
    assert len(gated) == 1
    assert gated[0]["refuse"] is True


def test_attempt_cost_rows_already_in_the_journal_do_not_move_the_gates_verdict() -> None:
    """The records are inert input: the same wave gates the same way without them."""
    bare = _RecordingJournal()
    carrying = _RecordingJournal()
    carrying.append(record=_released_attempt_cost())

    bare_refusals = _gated(status="green", journal=bare)
    carrying_refusals = _gated(status="green", journal=carrying)

    assert bare_refusals == carrying_refusals
    assert bare.of_stage(stage="cost-gate") == carrying.of_stage(stage="cost-gate")


def test_the_sequence_fold_returns_cost_fields_and_no_verdict() -> None:
    """A value with costs on it, carrying no refusal, severity or disposition."""
    cost = sequence_cost(
        observations=attempt_cost_observations(
            records=(_released_attempt_cost(),), work_item_id=_ITEM
        ),
        final_run_usd_micros=4_000,
    )
    for forbidden in ("refuse", "severity", "verdict", "decision", "disposition"):
        assert not hasattr(cost, forbidden), forbidden


@pytest.mark.parametrize("module_name", _RECORD_MODULES)
def test_no_record_module_can_reach_a_cost_gate(module_name: str) -> None:
    """A module that cannot import a gate cannot produce a verdict."""
    tree = ast.parse((_COMMANDS / f"{module_name}.py").read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    reachable = {f"{_PACKAGE}.{one}" for one in _GATE_MODULES}
    assert imported & reachable == set(), sorted(imported & reachable)


def test_the_gate_modules_named_above_really_are_the_gate() -> None:
    """The positive control for the scope the absence is asserted over.

    An absence over a population that does not contain the thing is no
    evidence, so each named module is checked to exist and to carry the gate's
    own entry point or its record stage.
    """
    sources = {one: (_COMMANDS / f"{one}.py").read_text(encoding="utf-8") for one in _GATE_MODULES}
    assert all(sources.values()), sorted(sources)
    assert "cost-gate" in sources["_dispatcher_cost_wave"]
    assert "def gate_wave" in sources["_dispatcher_cost"]
    assert "def cost_gate_after_verdict" in sources["_dispatcher_cost_gate"]
