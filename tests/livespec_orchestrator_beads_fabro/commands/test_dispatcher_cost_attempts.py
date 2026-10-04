"""A fallback run's cost: every attempt attributed, every attempt summed.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Cost follows every attempt in a successful fallback run": "Token
use and elapsed time MUST be attributed and summed per candidate attempt,
including failed attempts before the successful fallback."

THE FAILED ATTEMPT IS THE WHOLE POINT, so every fixture below prices the two
candidates DIFFERENTLY. A chain whose candidates shared a price would sum the
same whether the failed attempt was counted once, twice, or not at all -- so
the expected totals here are arithmetic only the correct attribution can
produce.

THE SINGLE-CANDIDATE CONTROL IS PINNED AGAINST THE SHIPPED PATH, NOT AGAINST A
TRANSCRIBED NUMBER. "A single-candidate run is priced exactly as before this
change" is asserted by comparing the per-attempt total to `CostSink.usd_micros`
-- the accumulator the legacy host-OTLP path reads -- on the same observations.
A hand-written expected total would pass against a per-attempt path that had
quietly stopped agreeing with the one every dispatch in this fleet uses today.

NOTHING IS EVER DROPPED, which is the other failure direction. An observation
the events cannot place -- a legacy sink record with no recorded instant, or one
whose node names no window -- still reaches the total. Dropping it would
under-report a real cost while leaving a well-formed observation behind.
"""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._acp_attempt_price import attempt_price
from livespec_orchestrator_beads_fabro.commands._acp_attempt_windows import attempt_windows
from livespec_orchestrator_beads_fabro.commands._acp_candidate_pricing import AcpCandidatePricing
from livespec_orchestrator_beads_fabro.commands._acp_fallback_event_types import AcpEventScan
from livespec_orchestrator_beads_fabro.commands._acp_fallback_events import scan_acp_events
from livespec_orchestrator_beads_fabro.commands._acp_model_entry import AcpModelEntry
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_pricing import ModelPrice
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_sink import CostSink

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_MODULE = "_dispatcher_cost_attempts"
_MODULE_PATH = _COMMANDS / f"{_MODULE}.py"

_BASE = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)
_BASE_MS = int(_BASE.timestamp() * 1000)
_WORK_ITEM = "bd-ib-tmgt7v"

# The failed primary and the successful fallback, priced an order of magnitude
# apart so any mis-attribution between them shows up in the total. The expected
# BASE rates are written out; the two cache rates are checked as multiples of
# the input rate rather than transcribed, because a derived float (0.75 x 0.10)
# is not the decimal a reader would write and a transcribed one would fail on
# the last bit for a reason that has nothing to do with the contract.
_PRIMARY_MODEL = "claude-opus-5"
_FALLBACK_MODEL = "gpt-5.4-mini"
_PRIMARY_BASE = (5.0, 25.0)
_FALLBACK_BASE = (0.75, 4.5)
_CACHE_WRITE_MULTIPLE = 1.25
_CACHE_READ_MULTIPLE = 0.10


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


def _failover(*, durations_ms: list[int]) -> dict[str, Any]:
    return {
        "type": "agent.acp.failover",
        "schema_version": 1,
        "event_id": "ev-1",
        "occurred_at": _instant(offset_ms=0),
        "node": "implement",
        "node_visit": 1,
        "engine_attempt": 1,
        "from": _identity(index=0, key=_PRIMARY_MODEL),
        "to": _identity(index=1, key=_FALLBACK_MODEL),
        "hold_key": "codex",
        "cause": "quota",
        "scope": "availability-domain",
        "primary_generation": "gen-a",
        "full_chain": "chain-1",
        "attempted_durations_ms": durations_ms,
    }


def _windows(*, payload: list[dict[str, Any]]) -> tuple[Any, ...]:
    scan = scan_acp_events(payload=payload)
    assert isinstance(scan, AcpEventScan), scan
    return attempt_windows(scan=scan)


def _chain_payload() -> list[dict[str, Any]]:
    """A node visit whose primary failed at 120s and whose fallback then won."""
    return [
        _start(index=0, offset_ms=0),
        _failover(durations_ms=[120_000]),
        _start(index=1, offset_ms=125_000),
    ]


def _catalog() -> dict[str, AcpModelEntry]:
    """A catalog pricing both candidates, built from the shipped base rates."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._acp_model_catalog"
    )
    return dict(module.builtin_model_catalog())  # pyright: ignore[reportAttributeAccessIssue]


def _pricer(
    *,
    catalog: dict[str, AcpModelEntry] | None = None,
    tables: dict[int, AcpCandidatePricing] | None = None,
) -> Any:
    """A pricer closing over a catalog and per-candidate explicit tables."""
    resolved_catalog = _catalog() if catalog is None else catalog
    resolved_tables = {} if tables is None else tables

    def price(*, node: str | None, candidate_index: int | None, identity: str) -> ModelPrice | None:
        # `node` is part of the pricer contract because two nodes of one run may
        # declare different chains; every fixture here drives a single node, so
        # the index alone selects the table.
        del node
        return attempt_price(
            raw_model=identity,
            catalog=resolved_catalog,
            candidate_pricing=None
            if candidate_index is None
            else resolved_tables.get(candidate_index),
        )

    return price


def _observation(
    *,
    dedup_key: str,
    identity: str | None,
    input_tokens: int,
    started_at_ms: int | None,
    node_id: str | None = "implement",
) -> Any:
    """One recorded API call, through an in-body import of the new module."""
    assert _MODULE_PATH.is_file(), _MODULE_PATH
    module = importlib.import_module(f"livespec_orchestrator_beads_fabro.commands.{_MODULE}")
    tokens = module.TokenVector(  # pyright: ignore[reportAttributeAccessIssue]
        input=input_tokens, output=0, cache_write=0, cache_read=0
    )
    return module.CostObservation(  # pyright: ignore[reportAttributeAccessIssue]
        dedup_key=dedup_key,
        started_at_ms=started_at_ms,
        model_identity=identity,
        tokens=tokens,
        node_id=node_id,
    )


def _chain_cost(*, observations: tuple[Any, ...], windows: tuple[Any, ...], pricer: Any) -> Any:
    module = importlib.import_module(f"livespec_orchestrator_beads_fabro.commands.{_MODULE}")
    return module.chain_cost(  # pyright: ignore[reportAttributeAccessIssue]
        observations=observations, windows=windows, price_of=pricer
    )


def _attr(*, key: str, string_value: str | None = None, int_value: int | None = None) -> Any:
    if int_value is not None:
        return {"key": key, "value": {"intValue": str(int_value)}}
    return {"key": key, "value": {"stringValue": "" if string_value is None else string_value}}


def _cc_span(*, request_id: str, model: str, input_tokens: int, started_at_ms: int) -> Any:
    """A synthetic CC per-API-call span carrying a start instant and a model."""
    return {
        "name": "claude_code.llm_request",
        "spanId": f"span-{request_id}",
        "startTimeUnixNano": str(started_at_ms * 1_000_000),
        "attributes": [
            _attr(key="model", string_value=model),
            _attr(key="input_tokens", int_value=input_tokens),
            _attr(key="output_tokens", int_value=0),
            _attr(key="cache_creation_tokens", int_value=0),
            _attr(key="cache_read_tokens", int_value=0),
            _attr(key="work.item.id", string_value=_WORK_ITEM),
            _attr(key="request_id", string_value=request_id),
            _attr(key="node_id", string_value="implement"),
        ],
    }


def test_the_sink_records_each_call_s_start_instant_and_emitted_identity(
    tmp_path: Path,
) -> None:
    """Attribution needs a WHEN and a WHAT per call, so the sink must persist both.

    The cost gate reads the sink OUT OF PROCESS, after the run, so a record
    that kept only a derived micro-USD cannot be re-attributed to an attempt
    window however good the window is.
    """
    sink = CostSink(path=tmp_path / "cost.json")
    sink.accumulate_span(
        span=_cc_span(
            request_id="req-a",
            model=f"{_PRIMARY_MODEL}-20260101",
            input_tokens=1_000_000,
            started_at_ms=_BASE_MS + 10_000,
        )
    )

    observations = sink.observations(key=_WORK_ITEM)

    assert observations is not None
    assert len(observations) == 1
    assert observations[0].started_at_ms == _BASE_MS + 10_000
    assert observations[0].model_identity == _PRIMARY_MODEL
    assert observations[0].tokens.input == 1_000_000
    assert observations[0].node_id == "implement"


def test_the_sink_reports_no_observations_for_a_key_that_never_accrued(
    tmp_path: Path,
) -> None:
    """An unaccrued key reads as absent, which is the unobservable condition."""
    sink = CostSink(path=tmp_path / "cost.json")

    assert sink.observations(key=_WORK_ITEM) is None


def test_a_legacy_record_reads_back_with_no_instant_and_no_identity(
    tmp_path: Path,
) -> None:
    """A record written before this change is read, not discarded.

    The sink file migrates in place, so a dispatch straddling the change has
    records of both shapes. The old ones carry usage and no position.
    """
    path = tmp_path / "cost.json"
    path.write_text(
        '{"bd-ib-tmgt7v": {"req-old": {"usd_micros": 42, "input": 7}}}', encoding="utf-8"
    )

    observations = CostSink(path=path).observations(key=_WORK_ITEM)

    assert observations is not None
    assert observations[0].started_at_ms is None
    assert observations[0].model_identity is None
    assert observations[0].tokens.input == 7


def test_a_successful_fallback_run_sums_both_attempts() -> None:
    """Every attempt counts: the failed primary's usage AND the winner's.

    1M input tokens on the primary at 5.00/MTok is 5_000_000 micro-USD; 1M on
    the fallback at 0.75/MTok is 750_000. The total can only be 5_750_000 if
    the failed attempt was counted exactly once at its OWN price.
    """
    cost = _chain_cost(
        observations=(
            _observation(
                dedup_key="req-a",
                identity=_PRIMARY_MODEL,
                input_tokens=1_000_000,
                started_at_ms=_BASE_MS + 10_000,
            ),
            _observation(
                dedup_key="req-b",
                identity=_FALLBACK_MODEL,
                input_tokens=1_000_000,
                started_at_ms=_BASE_MS + 130_000,
            ),
        ),
        windows=_windows(payload=_chain_payload()),
        pricer=_pricer(),
    )

    assert cost.usd_micros == 5_750_000
    assert cost.model_resolved is True


def test_each_attempt_is_reported_with_its_own_candidate_index_and_elapsed_time() -> None:
    """The per-attempt breakdown carries the engine's own measurement of each.

    The primary's 120_000 ms is the failover event's measurement; the winner
    has none, because no transition away from it was ever recorded.
    """
    cost = _chain_cost(
        observations=(
            _observation(
                dedup_key="req-a",
                identity=_PRIMARY_MODEL,
                input_tokens=1_000_000,
                started_at_ms=_BASE_MS + 10_000,
            ),
            _observation(
                dedup_key="req-b",
                identity=_FALLBACK_MODEL,
                input_tokens=1_000_000,
                started_at_ms=_BASE_MS + 130_000,
            ),
        ),
        windows=_windows(payload=_chain_payload()),
        pricer=_pricer(),
    )

    reported = tuple(
        (attempt.candidate_index, attempt.identity, attempt.elapsed_ms, attempt.usd_micros)
        for attempt in cost.attempts
    )
    assert reported == (
        (0, _PRIMARY_MODEL, 120_000, 5_000_000),
        (1, _FALLBACK_MODEL, None, 750_000),
    )


def test_a_call_inside_the_failed_window_is_priced_at_the_failed_candidate() -> None:
    """The window decides the candidate, and the candidate decides the table.

    Both calls below emit the SAME identity, so a reader that priced by
    identity alone could not tell them apart -- and the per-candidate explicit
    tables here disagree by a factor of ten, so the total names which window
    each call landed in.
    """
    tables = {
        0: AcpCandidatePricing(
            model="shared-model",
            input_usd_per_million=100.0,
            output_usd_per_million=0.0,
            cache_write_usd_per_million=0.0,
            cache_read_usd_per_million=0.0,
        ),
        1: AcpCandidatePricing(
            model="shared-model",
            input_usd_per_million=10.0,
            output_usd_per_million=0.0,
            cache_write_usd_per_million=0.0,
            cache_read_usd_per_million=0.0,
        ),
    }

    cost = _chain_cost(
        observations=(
            _observation(
                dedup_key="req-a",
                identity="shared-model",
                input_tokens=1_000_000,
                started_at_ms=_BASE_MS + 10_000,
            ),
            _observation(
                dedup_key="req-b",
                identity="shared-model",
                input_tokens=1_000_000,
                started_at_ms=_BASE_MS + 130_000,
            ),
        ),
        windows=_windows(payload=_chain_payload()),
        pricer=_pricer(catalog={}, tables=tables),
    )

    assert cost.usd_micros == 110_000_000


def test_a_call_in_the_teardown_gap_is_attributed_to_the_attempt_that_preceded_it() -> None:
    """A call between one attempt's measured end and the next's start is not lost.

    The primary's window closes at 120_000 ms and the fallback starts at
    125_000; this call lands at 122_000, inside neither. It belongs to the
    attempt that was most recently running, and the alternative -- dropping it
    -- silently under-reports a real charge.
    """
    cost = _chain_cost(
        observations=(
            _observation(
                dedup_key="req-gap",
                identity=_PRIMARY_MODEL,
                input_tokens=1_000_000,
                started_at_ms=_BASE_MS + 122_000,
            ),
        ),
        windows=_windows(payload=_chain_payload()),
        pricer=_pricer(),
    )

    assert cost.usd_micros == 5_000_000
    assert tuple(attempt.candidate_index for attempt in cost.attempts) == (0,)


def test_a_call_before_every_window_is_attributed_to_the_earliest_attempt() -> None:
    """A call whose instant precedes the first recorded start still counts.

    Clock skew between the sandbox's CC process and the engine's event stream
    is real, and a call that lands microseconds before the first start is the
    primary's work by every other piece of evidence.
    """
    cost = _chain_cost(
        observations=(
            _observation(
                dedup_key="req-early",
                identity=_PRIMARY_MODEL,
                input_tokens=1_000_000,
                started_at_ms=_BASE_MS - 5_000,
            ),
        ),
        windows=_windows(payload=_chain_payload()),
        pricer=_pricer(),
    )

    assert cost.usd_micros == 5_000_000
    assert cost.attempts[0].candidate_index == 0


def test_an_unplaceable_call_counts_without_being_attributed_to_a_candidate() -> None:
    """A record with no instant reaches the total and names no candidate index.

    Guessing a candidate for it would be a confident wrong attribution; the
    honest report is "counted, unplaced", which is what a `None` candidate
    index says.
    """
    cost = _chain_cost(
        observations=(
            _observation(
                dedup_key="req-old",
                identity=_PRIMARY_MODEL,
                input_tokens=1_000_000,
                started_at_ms=None,
            ),
        ),
        windows=_windows(payload=_chain_payload()),
        pricer=_pricer(),
    )

    assert cost.usd_micros == 5_000_000
    assert cost.attempts[0].candidate_index is None


def test_a_call_from_another_node_is_not_attributed_to_this_node_s_attempts() -> None:
    """`node_id` scopes attribution; a call from a node with no windows still counts."""
    cost = _chain_cost(
        observations=(
            _observation(
                dedup_key="req-review",
                identity=_PRIMARY_MODEL,
                input_tokens=1_000_000,
                started_at_ms=_BASE_MS + 10_000,
                node_id="review",
            ),
        ),
        windows=_windows(payload=_chain_payload()),
        pricer=_pricer(),
    )

    assert cost.usd_micros == 5_000_000
    assert cost.attempts[0].candidate_index is None


def test_a_call_is_attributed_within_its_own_node_s_windows() -> None:
    """Two nodes, two chains: each call lands on a window of its own node."""
    payload = [
        *_chain_payload(),
        _start(index=0, offset_ms=10_000, node="review"),
    ]

    cost = _chain_cost(
        observations=(
            _observation(
                dedup_key="req-review",
                identity=_FALLBACK_MODEL,
                input_tokens=1_000_000,
                started_at_ms=_BASE_MS + 130_000,
                node_id="review",
            ),
        ),
        windows=_windows(payload=payload),
        pricer=_pricer(),
    )

    assert cost.attempts[0].node == "review"
    assert cost.attempts[0].candidate_index == 0


def test_a_single_candidate_chain_totals_exactly_what_the_shipped_sink_reports(
    tmp_path: Path,
) -> None:
    """ "A single-candidate run is priced exactly as before this change."

    Pinned against `CostSink.usd_micros` -- the accumulator every dispatch in
    this fleet reads today -- on the same spans, rather than against a
    transcribed total. The three spans carry a mixed four-category vector so
    the agreement covers every rate rather than just the input one.
    """
    sink = CostSink(path=tmp_path / "cost.json")
    for index, tokens in enumerate((5244, 3748, 47620)):
        sink.accumulate_span(
            span=_cc_span(
                request_id=f"req-{index}",
                model=f"{_PRIMARY_MODEL}-20260101",
                input_tokens=tokens,
                started_at_ms=_BASE_MS + 1_000 * index,
            )
        )
    observations = sink.observations(key=_WORK_ITEM)
    assert observations is not None

    cost = _chain_cost(
        observations=observations,
        windows=_windows(payload=[_start(index=0, offset_ms=0)]),
        pricer=_pricer(),
    )

    assert cost.usd_micros == sink.usd_micros(key=_WORK_ITEM)
    assert cost.usd_micros is not None
    assert cost.usd_micros > 0


def test_a_run_with_no_windows_still_sums_its_observations() -> None:
    """An empty window set is not an empty cost.

    A node whose engine emitted no `agent.acp.started` records -- a pre-chain
    build, or a stream the read could not place -- has usage all the same, and
    that usage is the run's cost with no candidate attribution attached.
    """
    cost = _chain_cost(
        observations=(
            _observation(
                dedup_key="req-a",
                identity=_PRIMARY_MODEL,
                input_tokens=1_000_000,
                started_at_ms=_BASE_MS,
            ),
        ),
        windows=(),
        pricer=_pricer(),
    )

    assert cost.usd_micros == 5_000_000
    assert cost.attempts[0].candidate_index is None


def test_two_calls_in_one_attempt_sum_into_that_attempt() -> None:
    """One attempt makes many API calls; the attempt reports their sum once."""
    cost = _chain_cost(
        observations=(
            _observation(
                dedup_key="req-a",
                identity=_PRIMARY_MODEL,
                input_tokens=600_000,
                started_at_ms=_BASE_MS + 10_000,
            ),
            _observation(
                dedup_key="req-b",
                identity=_PRIMARY_MODEL,
                input_tokens=400_000,
                started_at_ms=_BASE_MS + 20_000,
            ),
        ),
        windows=_windows(payload=_chain_payload()),
        pricer=_pricer(),
    )

    assert len(cost.attempts) == 1
    assert cost.attempts[0].tokens.input == 1_000_000
    assert cost.usd_micros == 5_000_000


def test_no_observations_at_all_is_an_unobservable_cost() -> None:
    """Nothing accrued is the dark condition, reported as such rather than as zero."""
    cost = _chain_cost(
        observations=(), windows=_windows(payload=_chain_payload()), pricer=_pricer()
    )

    assert cost.usd_micros is None
    assert cost.attempts == ()


def test_the_priced_identities_name_every_model_that_was_charged() -> None:
    """Both candidates' identities are named, in a stable order."""
    cost = _chain_cost(
        observations=(
            _observation(
                dedup_key="req-a",
                identity=_PRIMARY_MODEL,
                input_tokens=1_000_000,
                started_at_ms=_BASE_MS + 10_000,
            ),
            _observation(
                dedup_key="req-b",
                identity=_FALLBACK_MODEL,
                input_tokens=1_000_000,
                started_at_ms=_BASE_MS + 130_000,
            ),
        ),
        windows=_windows(payload=_chain_payload()),
        pricer=_pricer(),
    )

    assert cost.priced_identities == (_PRIMARY_MODEL, _FALLBACK_MODEL)


@pytest.mark.parametrize(
    ("model", "base"),
    [(_PRIMARY_MODEL, _PRIMARY_BASE), (_FALLBACK_MODEL, _FALLBACK_BASE)],
)
def test_the_shipped_catalog_prices_both_candidates_of_this_chain(
    *, model: str, base: tuple[float, float]
) -> None:
    """A control on the fixtures: both prices come from committed bytes.

    Every total above is only meaningful if the two models really are priced
    the way this module assumes. This checks the assumption against the shipped
    catalog rather than restating it.
    """
    price = attempt_price(raw_model=model, catalog=_catalog(), candidate_pricing=None)

    assert price is not None, model
    assert price.input == base[0]
    assert price.output == base[1]
    assert price.cache_write == pytest.approx(base[0] * _CACHE_WRITE_MULTIPLE)
    assert price.cache_read == pytest.approx(base[0] * _CACHE_READ_MULTIPLE)
