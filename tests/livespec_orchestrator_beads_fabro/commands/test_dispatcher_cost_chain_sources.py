"""Where a chain attempt's price comes from, and what happens when it cannot be read.

The sibling `test_dispatcher_cost_chain.py` binds the POSTURE -- that an
unpriceable chain reaches the existing fail-closed gate as an absent cost. This
module binds the two things that decide WHETHER it is priceable: the
per-candidate explicit table the dispatch target committed, and the fail-soft
behaviour of the configuration read that supplies it.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Cost follows every attempt in a successful fallback run":
"Pricing resolves through the model catalog entry the candidate's identity
names first ... and a per-candidate explicit table second."

THE TABLE IS LOOKED UP BY NODE AS WELL AS BY INDEX, and that is the assertion
worth having here. Two nodes of one run may declare different chains, so a
table keyed on the candidate index alone would price one node's attempt at
another node's rate -- a wrong number with no symptom. The fixture therefore
declares DIFFERENT prices for the same index under two nodes.

EVERY FAIL-SOFT ARM FAILS TOWARD DARK, never toward the shipped snapshot. A
configuration this repository cannot read is not a configuration whose
overrides can be assumed away: pricing attempts against the built-in catalog
when the operator's own catalog is unreadable produces a number, reports it as
an observation, and is wrong in whichever direction the override went.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_chain import (
    chain_costs,
    run_chain_cost,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_gate import derived_costs
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_sink import CostSink
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import cost_sink_path

_BASE = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)
_BASE_MS = int(_BASE.timestamp() * 1000)
_WORK_ITEM = "bd-ib-tmgt7v"
_SECOND_WORK_ITEM = "bd-ib-tmgt7v.2"
_RUN_ID = "01M3WTPHJ0Y9TA263R3A4YCQN1"
_FACTORY = FactoryTarget(name="hp", server="https://factory.example:32276", dev_token=None)

# A model the shipped catalog does NOT price, so the only route to a price for
# it is the per-candidate explicit table under test.
_VENDOR_MODEL = "vendor-model"

# Distinct per-million input rates, one per (node, candidate) slot, so the
# derived total names exactly which slot's table was consulted.
_IMPLEMENT_PRIMARY_RATE = 11.0
_IMPLEMENT_FALLBACK_RATE = 23.0
_REVIEW_PRIMARY_RATE = 47.0
_MILLION = 1_000_000


@dataclass(kw_only=True)
class _ScriptedRunner:
    events_stdout: str = "[]"
    calls: list[list[str]] = field(default_factory=list)

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        # Every invocation this module drives is the server-qualified events
        # read; `argv` is recorded so a test can say so rather than assume it.
        del cwd, timeout_seconds
        self.calls.append(argv)
        return CommandResult(exit_code=0, stdout=self.events_stdout, stderr="")


def _instant(*, offset_ms: int) -> str:
    return (_BASE + timedelta(milliseconds=offset_ms)).isoformat().replace("+00:00", "Z")


def _identity(*, index: int, key: str) -> dict[str, Any]:
    return {
        "candidate_index": index,
        "display_name": f"display {key}",
        "candidate_key": key,
        "availability_key": "codex",
    }


def _start(*, index: int, offset_ms: int, node: str = "implement") -> dict[str, Any]:
    return {
        "type": "agent.acp.started",
        "node": node,
        "node_visit": 1,
        "candidate_index": index,
        "occurred_at": _instant(offset_ms=offset_ms),
        "primary_generation": "gen-a",
    }


def _failover(*, node: str = "implement") -> dict[str, Any]:
    return {
        "type": "agent.acp.failover",
        "schema_version": 1,
        "event_id": f"ev-{node}",
        "occurred_at": _instant(offset_ms=120_000),
        "node": node,
        "node_visit": 1,
        "engine_attempt": 1,
        "from": _identity(index=0, key="primary"),
        "to": _identity(index=1, key="fallback"),
        "hold_key": "codex",
        "cause": "quota",
        "scope": "availability-domain",
        "primary_generation": "gen-a",
        "full_chain": "chain-1",
        "attempted_durations_ms": [120_000],
    }


def _two_node_events() -> str:
    """`implement` failing over to its fallback, then a `review` primary."""
    return json.dumps(
        [
            _start(index=0, offset_ms=0),
            _failover(),
            _start(index=1, offset_ms=125_000),
            _start(index=0, offset_ms=300_000, node="review"),
        ]
    )


def _pricing(*, rate: float) -> dict[str, object]:
    """A complete all-or-none table for `_VENDOR_MODEL` at one input rate."""
    return {
        "model": _VENDOR_MODEL,
        "input_usd_per_million": rate,
        "output_usd_per_million": 0.0,
        "cache_write_usd_per_million": 0.0,
        "cache_read_usd_per_million": 0.0,
    }


def _manual_candidate(*, rate: float) -> dict[str, object]:
    """A manual-form fallback candidate carrying only its own price table."""
    return {
        "command": "adapter",
        "args": ["literal"],
        "display_name": "fallback adapter",
        "candidate_key": "fallback-adapter",
        "availability_key": "vendor-domain",
        "pricing": _pricing(rate=rate),
    }


def _write_config(*, repo: Path, acp_nodes: dict[str, object]) -> None:
    (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": {"acp_nodes": acp_nodes}}}),
        encoding="utf-8",
    )


def _chained_config(*, repo: Path) -> None:
    """Two nodes, each declaring its own candidate price tables at distinct rates."""
    _write_config(
        repo=repo,
        acp_nodes={
            "implement": {
                "display_name": "implement primary",
                "candidate_key": "implement-primary",
                "availability_key": "vendor-domain",
                "pricing": _pricing(rate=_IMPLEMENT_PRIMARY_RATE),
                "fallbacks": [_manual_candidate(rate=_IMPLEMENT_FALLBACK_RATE)],
            },
            "review": {
                "display_name": "review primary",
                "candidate_key": "review-primary",
                "availability_key": "vendor-domain",
                "pricing": _pricing(rate=_REVIEW_PRIMARY_RATE),
            },
        },
    )


def _attr(*, key: str, string_value: str | None = None, int_value: int | None = None) -> Any:
    if int_value is not None:
        return {"key": key, "value": {"intValue": str(int_value)}}
    return {"key": key, "value": {"stringValue": "" if string_value is None else string_value}}


def _cc_span(
    *,
    request_id: str,
    started_at_ms: int | None,
    node_id: str = "implement",
    work_item_id: str = _WORK_ITEM,
) -> dict[str, object]:
    span: dict[str, object] = {
        "name": "claude_code.llm_request",
        "spanId": f"span-{request_id}",
        "attributes": [
            _attr(key="model", string_value=_VENDOR_MODEL),
            _attr(key="input_tokens", int_value=_MILLION),
            _attr(key="output_tokens", int_value=0),
            _attr(key="cache_creation_tokens", int_value=0),
            _attr(key="cache_read_tokens", int_value=0),
            _attr(key="work.item.id", string_value=work_item_id),
            _attr(key="request_id", string_value=request_id),
            _attr(key="node_id", string_value=node_id),
        ],
    }
    if started_at_ms is not None:
        span["startTimeUnixNano"] = str(started_at_ms * 1_000_000)
    return span


def _args(*, journal_path: Path) -> argparse.Namespace:
    return argparse.Namespace(items=None, fabro_bin="fabro", journal=str(journal_path))


def _green(*, work_item_id: str = _WORK_ITEM) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=work_item_id,
        status="green",
        stage="done",
        pr_number=7,
        merge_sha="abc123",
        detail="merged",
        fabro_run_id=_RUN_ID,
    )


def test_each_candidate_s_own_table_prices_its_own_attempt(tmp_path: Path) -> None:
    """Candidate zero takes the chain's table; candidate one takes its fallback's.

    Three calls, one per slot, at 11.0 / 23.0 / 47.0 USD per million input over
    1M tokens each: 81_000_000 micro-USD. Every slot has a distinct rate, so
    this one number says each attempt was priced from its OWN candidate's
    table -- including the review node, whose candidate zero shares an index
    with implement's.
    """
    _chained_config(repo=tmp_path)
    args = _args(journal_path=tmp_path / "journal.jsonl")
    sink = CostSink(path=cost_sink_path(args=args, repo=tmp_path))
    sink.accumulate_span(span=_cc_span(request_id="req-0", started_at_ms=_BASE_MS + 10_000))
    sink.accumulate_span(span=_cc_span(request_id="req-1", started_at_ms=_BASE_MS + 130_000))
    sink.accumulate_span(
        span=_cc_span(request_id="req-2", started_at_ms=_BASE_MS + 310_000, node_id="review")
    )

    cost = run_chain_cost(
        repo=tmp_path,
        work_item_id=_WORK_ITEM,
        run_id=_RUN_ID,
        sink=sink,
        factory=_FACTORY,
        runner=_ScriptedRunner(events_stdout=_two_node_events()),
    )

    assert cost is not None
    expected = _IMPLEMENT_PRIMARY_RATE + _IMPLEMENT_FALLBACK_RATE + _REVIEW_PRIMARY_RATE
    assert cost.usd_micros == round(expected * _MILLION)


def test_an_unplaceable_call_cannot_borrow_a_candidate_s_table(tmp_path: Path) -> None:
    """A call no window placed has no candidate, so only the catalog may price it.

    The catalog does not carry `_VENDOR_MODEL`, so the honest result is dark.
    Reaching for the implement node's table instead would price a call nobody
    can attribute at a rate only an attributed call is entitled to.
    """
    _chained_config(repo=tmp_path)
    args = _args(journal_path=tmp_path / "journal.jsonl")
    sink = CostSink(path=cost_sink_path(args=args, repo=tmp_path))
    sink.accumulate_span(span=_cc_span(request_id="req-old", started_at_ms=None))

    cost = run_chain_cost(
        repo=tmp_path,
        work_item_id=_WORK_ITEM,
        run_id=_RUN_ID,
        sink=sink,
        factory=_FACTORY,
        runner=_ScriptedRunner(events_stdout=_two_node_events()),
    )

    assert cost is not None
    assert cost.usd_micros is None


def test_an_attempt_of_a_node_the_configuration_does_not_describe_is_dark(
    tmp_path: Path,
) -> None:
    """A chain the committed configuration no longer declares yields no table.

    The run's events record a `review` node; the configuration declares only
    `implement`. Falling back to the nearest declared table would price a
    review attempt at an implement rate.
    """
    _write_config(
        repo=tmp_path,
        acp_nodes={
            "implement": {
                "display_name": "implement primary",
                "candidate_key": "implement-primary",
                "availability_key": "vendor-domain",
                "pricing": _pricing(rate=_IMPLEMENT_PRIMARY_RATE),
            }
        },
    )
    args = _args(journal_path=tmp_path / "journal.jsonl")
    sink = CostSink(path=cost_sink_path(args=args, repo=tmp_path))
    sink.accumulate_span(
        span=_cc_span(request_id="req-2", started_at_ms=_BASE_MS + 310_000, node_id="review")
    )

    cost = run_chain_cost(
        repo=tmp_path,
        work_item_id=_WORK_ITEM,
        run_id=_RUN_ID,
        sink=sink,
        factory=_FACTORY,
        runner=_ScriptedRunner(events_stdout=_two_node_events()),
    )

    assert cost is not None
    assert cost.usd_micros is None


def test_an_attempt_past_the_configured_chain_s_end_is_dark(tmp_path: Path) -> None:
    """Candidate one of a chain declaring no fallbacks has no table of its own.

    The configured chain has shrunk since the run executed. The honest answer
    is no table rather than the primary's, which is a different candidate's
    price.
    """
    _write_config(
        repo=tmp_path,
        acp_nodes={
            "implement": {
                "display_name": "implement primary",
                "candidate_key": "implement-primary",
                "availability_key": "vendor-domain",
                "pricing": _pricing(rate=_IMPLEMENT_PRIMARY_RATE),
            }
        },
    )
    args = _args(journal_path=tmp_path / "journal.jsonl")
    sink = CostSink(path=cost_sink_path(args=args, repo=tmp_path))
    sink.accumulate_span(span=_cc_span(request_id="req-1", started_at_ms=_BASE_MS + 130_000))

    cost = run_chain_cost(
        repo=tmp_path,
        work_item_id=_WORK_ITEM,
        run_id=_RUN_ID,
        sink=sink,
        factory=_FACTORY,
        runner=_ScriptedRunner(events_stdout=_two_node_events()),
    )

    assert cost is not None
    assert cost.usd_micros is None


def test_a_refused_configuration_prices_nothing_rather_than_using_the_snapshot(
    tmp_path: Path,
) -> None:
    """An unreadable catalog override fails toward dark, not toward built-in prices.

    The model-catalog override here is refused (an unknown entry key), and the
    attempt's emitted identity IS one the shipped snapshot prices. So an
    implementation that substituted the snapshot would produce a confident
    number, and it would be a number about a catalog this repository
    deliberately overrode.
    """
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {
                        "model_catalog": {
                            "anthropic/claude-opus-5": {"not_a_catalog_entry_key": True}
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    args = _args(journal_path=tmp_path / "journal.jsonl")
    sink = CostSink(path=cost_sink_path(args=args, repo=tmp_path))
    span = _cc_span(request_id="req-0", started_at_ms=_BASE_MS + 10_000)
    attributes = span["attributes"]
    assert isinstance(attributes, list)
    attributes[0] = _attr(key="model", string_value="claude-opus-5")
    sink.accumulate_span(span=span)

    cost = run_chain_cost(
        repo=tmp_path,
        work_item_id=_WORK_ITEM,
        run_id=_RUN_ID,
        sink=sink,
        factory=_FACTORY,
        runner=_ScriptedRunner(events_stdout=_two_node_events()),
    )

    assert cost is not None
    assert cost.usd_micros is None


def test_a_configuration_read_that_raises_prices_nothing_and_does_not_propagate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cost path runs AFTER the verdict, so it degrades rather than raising.

    Driven by making the configuration read raise, because no committed bytes
    reach this arm -- and a fail-soft wrapper nothing exercises is a wrapper
    nobody knows works.
    """

    def _explode(**_: object) -> object:
        raise OSError("the configuration file went away")

    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_cost_chain"
        ".resolve_acp_catalogs_for",
        _explode,
    )
    _chained_config(repo=tmp_path)
    args = _args(journal_path=tmp_path / "journal.jsonl")
    sink = CostSink(path=cost_sink_path(args=args, repo=tmp_path))
    sink.accumulate_span(span=_cc_span(request_id="req-0", started_at_ms=_BASE_MS + 10_000))

    cost = run_chain_cost(
        repo=tmp_path,
        work_item_id=_WORK_ITEM,
        run_id=_RUN_ID,
        sink=sink,
        factory=_FACTORY,
        runner=_ScriptedRunner(events_stdout=_two_node_events()),
    )

    assert cost is not None
    assert cost.usd_micros is None


def test_a_refused_node_chain_still_leaves_the_catalog_able_to_price(
    tmp_path: Path,
) -> None:
    """An `acp_nodes` table the chain parser refuses costs the tables, not the catalog.

    The two sources are independent: a chain the parser cannot read means no
    per-candidate table, and the catalog still prices whatever its own entries
    name. `claude-opus-5` at 5.00 per million input over 1M tokens is
    5_000_000 micro-USD.
    """
    _write_config(repo=tmp_path, acp_nodes={"implement": {"unknown_candidate_key": True}})
    args = _args(journal_path=tmp_path / "journal.jsonl")
    sink = CostSink(path=cost_sink_path(args=args, repo=tmp_path))
    span = _cc_span(request_id="req-0", started_at_ms=_BASE_MS + 10_000)
    attributes = span["attributes"]
    assert isinstance(attributes, list)
    attributes[0] = _attr(key="model", string_value="claude-opus-5")
    sink.accumulate_span(span=span)

    cost = run_chain_cost(
        repo=tmp_path,
        work_item_id=_WORK_ITEM,
        run_id=_RUN_ID,
        sink=sink,
        factory=_FACTORY,
        runner=_ScriptedRunner(events_stdout=_two_node_events()),
    )

    assert cost is not None
    assert cost.usd_micros == 5_000_000


def test_a_wave_keeps_the_outcome_whose_run_yielded_a_chain_and_skips_the_other(
    tmp_path: Path,
) -> None:
    """One wave, two green outcomes: only the one with usage gets a chain cost.

    The second item accrued no telemetry, so its chain cost is absent and the
    sink's own aggregate decides for it -- the mixed wave that proves the
    per-item skip does not abandon the rest of the wave.
    """
    _chained_config(repo=tmp_path)
    args = _args(journal_path=tmp_path / "journal.jsonl")
    sink = CostSink(path=cost_sink_path(args=args, repo=tmp_path))
    sink.accumulate_span(span=_cc_span(request_id="req-0", started_at_ms=_BASE_MS + 10_000))

    costs = chain_costs(
        repo=tmp_path,
        outcomes=(_green(), _green(work_item_id=_SECOND_WORK_ITEM)),
        sink=sink,
        runner=_ScriptedRunner(events_stdout=_two_node_events()),
        factory_of=lambda **_: _FACTORY,
    )

    assert set(costs) == {_WORK_ITEM}


def test_a_priceable_chain_total_is_what_the_gate_gates_on(tmp_path: Path) -> None:
    """The observable arm of the derived-cost map: the chain's total, not the sink's.

    The sink's own aggregate for this span is a DEFAULT-priced number, because
    `_VENDOR_MODEL` is in no built-in table; the chain's is the operator's
    declared 11.00 per million. The two differ, so this assertion is only
    satisfiable by reading the chain.
    """
    _chained_config(repo=tmp_path)
    args = _args(journal_path=tmp_path / "journal.jsonl")
    sink = CostSink(path=cost_sink_path(args=args, repo=tmp_path))
    sink.accumulate_span(span=_cc_span(request_id="req-0", started_at_ms=_BASE_MS + 10_000))
    chains = chain_costs(
        repo=tmp_path,
        outcomes=(_green(),),
        sink=sink,
        runner=_ScriptedRunner(events_stdout=_two_node_events()),
        factory_of=lambda **_: _FACTORY,
    )
    expected = round(_IMPLEMENT_PRIMARY_RATE * _MILLION)
    assert sink.usd_micros(key=_WORK_ITEM) != expected

    derived = derived_costs(args=args, repo=tmp_path, outcomes=[_green()], chains=chains)

    assert derived[_WORK_ITEM] == expected
