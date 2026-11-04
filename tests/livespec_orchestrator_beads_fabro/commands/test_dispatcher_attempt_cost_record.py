"""The attempt-cost record: one per attempt, stably identified, priced or dark.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Cost follows every attempt": "For every run released under
'Provider-limit release and re-dispatch', and for every availability
confirmation turn, the Dispatcher MUST journal one attempt-cost record carrying
the attempt's token use and elapsed time per node attempt wherever the run
record exposes them, priced under the rules below, or marked cost-unobservable.
... Each run or probe cost observation MUST have a stable identity and MUST be
counted at most once across reconciliation and resume."

THE IDENTITY IS ASSERTED AS REPRODUCIBLE AND AS DISCRIMINATING, which are two
different claims and only the pair is worth anything. Reproducible alone is
satisfied by a constant, which would collapse two releases of one item onto one
observation and lose a real charge; discriminating alone is satisfied by a
counter or a clock, which would make every replay a second observation and
double-count the sequence the dedupe exists to protect.

THE PER-ATTEMPT ENTRIES ARE ASSERTED TO CARRY THE ENGINE'S OWN MEASUREMENT AND
TO STATE THE TWO FIGURES IT DOES NOT CARRY, rather than to omit them. An
omitted key is what a record from a build predating this clause looks like, so
a reader could not tell "this engine exposed no per-attempt usage" from "this
record was minted before per-attempt usage was recorded" -- and a zero would be
worse again, because zero is a MEASURED figure everywhere else in this tree.
"""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_fallback_event_types import AcpEventScan
from livespec_orchestrator_beads_fabro.commands._acp_fallback_events import scan_acp_events

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_MODULE = "_dispatcher_cost_attempts"
_MODULE_PATH = _COMMANDS / f"{_MODULE}.py"

_BASE = datetime(2026, 10, 12, 9, 0, 0, tzinfo=timezone.utc)
_OCCURRED_AT = "2026-10-12T09:10:00Z"
_WORK_ITEM = "bd-ib-a2rhtt"
_FACTORY = "hp"
_RUN = "01M5KYHK83PWS1TBKCB61Z67P2"
_NODE_ATTEMPT = "implement"


def _module() -> Any:
    """The module under test, reached in the test body.

    An in-body import rather than a top-level one, so a Red that has not yet
    grown the record surface fails on the assertion below instead of at
    collection -- a collection error proves unimportability, not that the
    behaviour is unimplemented.
    """
    assert _MODULE_PATH.is_file(), _MODULE_PATH
    return importlib.import_module(f"livespec_orchestrator_beads_fabro.commands.{_MODULE}")


def _instant(*, offset_ms: int) -> str:
    return (_BASE + timedelta(milliseconds=offset_ms)).isoformat().replace("+00:00", "Z")


def _start(*, index: int, offset_ms: int) -> dict[str, Any]:
    return {
        "type": "agent.acp.started",
        "node": _NODE_ATTEMPT,
        "node_visit": 1,
        "candidate_index": index,
        "occurred_at": _instant(offset_ms=offset_ms),
        "primary_generation": "gen-a",
    }


def _failover(*, durations_ms: list[int]) -> dict[str, Any]:
    return {
        "type": "agent.acp.failover",
        "schema_version": 1,
        "event_id": "ev-1",
        "occurred_at": _instant(offset_ms=0),
        "node": _NODE_ATTEMPT,
        "node_visit": 1,
        "engine_attempt": 1,
        "from": {
            "candidate_index": 0,
            "display_name": "display primary",
            "candidate_key": "claude-opus-5",
            "availability_key": "anthropic",
        },
        "to": {
            "candidate_index": 1,
            "display_name": "display fallback",
            "candidate_key": "gpt-5.4-mini",
            "availability_key": "codex",
        },
        "hold_key": "anthropic",
        "cause": "quota",
        "scope": "availability-domain",
        "primary_generation": "gen-a",
        "full_chain": "chain-1",
        "attempted_durations_ms": durations_ms,
    }


def _windows() -> tuple[Any, ...]:
    """Two attempts of one node visit, the first with a measured duration."""
    payload: list[dict[str, Any]] = [
        _start(index=0, offset_ms=0),
        _failover(durations_ms=[120_000]),
        _start(index=1, offset_ms=125_000),
    ]
    scan = scan_acp_events(payload=payload)
    assert isinstance(scan, AcpEventScan), scan
    from livespec_orchestrator_beads_fabro.commands._acp_attempt_windows import attempt_windows

    return attempt_windows(scan=scan)


def _record(*, usd_micros: int | None, windows: tuple[Any, ...] | None = None) -> Any:
    module = _module()
    return module.attempt_cost_record(  # pyright: ignore[reportAttributeAccessIssue]
        source=module.ATTEMPT_COST_RELEASED_RUN,  # pyright: ignore[reportAttributeAccessIssue]
        work_item_id=_WORK_ITEM,
        factory=_FACTORY,
        run_id=_RUN,
        node_attempt=_NODE_ATTEMPT,
        occurred_at=_OCCURRED_AT,
        windows=_windows() if windows is None else windows,
        usd_micros=usd_micros,
    )


def test_the_record_surface_exists() -> None:
    """The record, its stage, its two sources and its identity are published."""
    module = _module()
    for name in (
        "ATTEMPT_COST_STAGE",
        "ATTEMPT_COST_RELEASED_RUN",
        "ATTEMPT_COST_CONFIRMATION_TURN",
        "attempt_cost_identity",
        "attempt_cost_record",
    ):
        assert hasattr(module, name), name


def test_the_identity_reproduces_for_one_attempt_and_separates_every_other() -> None:
    """Stable across replays of one attempt, distinct across every field of it.

    Both halves in one test because neither is a property on its own: see the
    module docstring for what a constant and what a clock each satisfy.
    """
    module = _module()
    identity = module.attempt_cost_identity  # pyright: ignore[reportAttributeAccessIssue]
    base = dict(
        source=module.ATTEMPT_COST_RELEASED_RUN,  # pyright: ignore[reportAttributeAccessIssue]
        factory=_FACTORY,
        run_id=_RUN,
        node_attempt=_NODE_ATTEMPT,
    )
    assert identity(**base) == identity(**base)
    separated = [
        identity(**{**base, "source": module.ATTEMPT_COST_CONFIRMATION_TURN}),  # pyright: ignore[reportAttributeAccessIssue]
        identity(**{**base, "factory": "petri"}),
        identity(**{**base, "run_id": "01OTHERRUN"}),
        identity(**{**base, "node_attempt": "review"}),
        identity(**{**base, "run_id": None}),
    ]
    assert len(set(separated)) == len(separated), separated
    assert identity(**base) not in separated


def test_the_record_names_the_attempt_and_carries_the_engines_elapsed_measurement() -> None:
    """One entry per node attempt, carrying what the run record exposes."""
    module = _module()
    record = _record(usd_micros=None)
    assert record["stage"] == module.ATTEMPT_COST_STAGE  # pyright: ignore[reportAttributeAccessIssue]
    assert record["source"] == module.ATTEMPT_COST_RELEASED_RUN  # pyright: ignore[reportAttributeAccessIssue]
    assert record["work_item_id"] == _WORK_ITEM
    assert record["factory"] == _FACTORY
    assert record["run_id"] == _RUN
    assert record["node_attempt"] == _NODE_ATTEMPT
    assert record["occurred_at"] == _OCCURRED_AT
    assert record["observation_id"] == module.attempt_cost_identity(  # pyright: ignore[reportAttributeAccessIssue]
        source=module.ATTEMPT_COST_RELEASED_RUN,  # pyright: ignore[reportAttributeAccessIssue]
        factory=_FACTORY,
        run_id=_RUN,
        node_attempt=_NODE_ATTEMPT,
    )
    attempts = record["attempts"]
    assert isinstance(attempts, list)
    assert [(one["node"], one["node_visit"], one["candidate_index"]) for one in attempts] == [
        (_NODE_ATTEMPT, 1, 0),
        (_NODE_ATTEMPT, 1, 1),
    ]
    assert [one["elapsed_ms"] for one in attempts] == [120_000, None]


def test_every_entry_states_the_two_figures_the_run_record_does_not_expose() -> None:
    """Token use and a per-attempt price are stated absent, never omitted."""
    attempts = _record(usd_micros=4_200)["attempts"]
    assert isinstance(attempts, list)
    assert attempts
    for one in attempts:
        assert "token_use" in one, one
        assert one["token_use"] is None, one
        assert "usd_micros" in one, one
        assert one["usd_micros"] is None, one


def test_an_absent_engine_figure_marks_the_record_cost_unobservable() -> None:
    """No figure is unobservable; a figure -- including zero -- is priced."""
    dark = _record(usd_micros=None)
    assert dark["usd_micros"] is None
    assert dark["cost_observable"] is False
    priced = _record(usd_micros=4_200)
    assert priced["usd_micros"] == 4_200
    assert priced["cost_observable"] is True
    measured_zero = _record(usd_micros=0)
    assert measured_zero["usd_micros"] == 0
    assert measured_zero["cost_observable"] is True


def test_a_run_whose_record_exposes_no_attempt_carries_an_empty_attempt_list() -> None:
    """An empty list rather than an absent key: nobody exposed any attempt."""
    record = _record(usd_micros=None, windows=())
    assert record["attempts"] == []
    assert record["cost_observable"] is False
