"""Tests for the dispatch correlation identity the factory is handed.

Three values travel with every dispatch — the work-item id, the dispatch id
and the factory name. The engine copies them off `fabro run --label
KEY=VALUE` onto its server run span, the worker run span and every
`run_turn` span, and it parents the server run span on the caller's
`TRACEPARENT`. These tests cover the host half: which values are passable,
the `--label` argv they produce, the dispatch span the traceparent names,
and that the span rides the Dispatcher's existing OTLP export path.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

_CORRELATION_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_correlation.py"
)
_CORRELATION_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_correlation"
_SPAN_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
    "/_dispatcher_dispatch_span.py"
)
_SPAN_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_span"


def _correlation_module() -> Any:
    assert _CORRELATION_PATH.is_file()
    return importlib.import_module(_CORRELATION_MODULE)


def _span_module() -> Any:
    assert _SPAN_PATH.is_file()
    return importlib.import_module(_SPAN_MODULE)


def test_dispatch_span_ids_are_domain_separated_sha256_truncations() -> None:
    """The two ids derive from the dispatch id by domain-separated SHA-256."""
    module = _correlation_module()
    dispatch_id = "01M4N4V6SEEKVVP88ST0CASGCP"

    ids = module.dispatch_span_ids(dispatch_id=dispatch_id)

    assert module.TRACE_ID_DOMAIN != module.SPAN_ID_DOMAIN
    assert module.TRACE_ID_HEX_DIGITS == 32
    assert module.SPAN_ID_HEX_DIGITS == 16
    assert (
        ids.trace_id
        == hashlib.sha256(f"{module.TRACE_ID_DOMAIN}:{dispatch_id}".encode()).hexdigest()[
            : module.TRACE_ID_HEX_DIGITS
        ]
    )
    assert (
        ids.span_id
        == hashlib.sha256(f"{module.SPAN_ID_DOMAIN}:{dispatch_id}".encode()).hexdigest()[
            : module.SPAN_ID_HEX_DIGITS
        ]
    )
    assert ids.trace_id == ids.trace_id.lower()
    assert ids.span_id == ids.span_id.lower()
    # The deterministic non-zero fallback: W3C reserves the all-zero id as
    # invalid, so a digest that truncated to zeros must not ship as-is, and
    # the stand-in must itself be re-derivable rather than random.
    assert module.non_zero_hex(digits="0" * module.SPAN_ID_HEX_DIGITS) == "0" * 15 + "1"
    assert module.non_zero_hex(digits="0" * module.TRACE_ID_HEX_DIGITS) == "0" * 31 + "1"
    assert module.non_zero_hex(digits=ids.span_id) == ids.span_id


def test_dispatch_span_ids_and_traceparent_re_derive_identically() -> None:
    """Re-deriving for one dispatch id reproduces the same trace and span id."""
    module = _correlation_module()
    dispatch_id = "01M4M5AAW9WVT71KNYMSHPWS3E"
    other_dispatch_id = "01M4MRW0XYDR82M1WHNJYTCNN3"

    # Both derivation surfaces have to agree, because the launch projects a
    # traceparent while the emitter renders a span and the two must name one
    # identity; a surface missing here is a surface nothing holds in lockstep.
    assert "dispatch_traceparent" in module.__all__
    first = module.dispatch_span_ids(dispatch_id=dispatch_id)
    second = module.dispatch_span_ids(dispatch_id=dispatch_id)

    assert (first.trace_id, first.span_id) == (second.trace_id, second.span_id)
    assert module.dispatch_traceparent(dispatch_id=dispatch_id) == module.dispatch_traceparent(
        dispatch_id=dispatch_id
    )
    assert (
        module.dispatch_traceparent(dispatch_id=dispatch_id)
        == f"00-{first.trace_id}-{first.span_id}-01"
    )
    assert module.dispatch_span_ids(dispatch_id=other_dispatch_id) != first


def test_dispatch_span_carries_the_three_correlation_attributes() -> None:
    """The emitted span names the dispatch by all three correlation values."""
    span_module = _span_module()
    correlation_module = _correlation_module()
    correlation = correlation_module.DispatchCorrelation(
        work_item_id="bd-ib-5jvgfr",
        dispatch_id="01M4N4V6SEEKVVP88ST0CASGCP",
        factory="hp",
    )

    payload = json.loads(span_module.dispatch_request_line(correlation=correlation, now_ns=7))
    span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    attributes = {entry["key"]: entry["value"]["stringValue"] for entry in span["attributes"]}

    assert attributes == {
        "work.item.id": "bd-ib-5jvgfr",
        "livespec.dispatch.id": "01M4N4V6SEEKVVP88ST0CASGCP",
        "livespec.dispatch.factory": "hp",
    }
    # The span the traceparent will name, so its identity has to BE the
    # derived pair rather than a second identity that merely looks like one.
    ids = correlation_module.dispatch_span_ids(dispatch_id=correlation.dispatch_id)
    assert span["traceId"] == ids.trace_id
    assert span["spanId"] == ids.span_id
    assert span["name"] == span_module.DISPATCH_SPAN_NAME
    assert span["startTimeUnixNano"] == "7"


def test_an_invocation_that_minted_no_dispatch_id_correlates_by_nothing(
    tmp_path: Path,
) -> None:
    """No dispatch id means no correlation and no span, not a partial one."""
    span_module = _span_module()
    correlation_module = _correlation_module()
    spans_path = tmp_path / "nested" / "dispatch-spans.jsonl"

    correlation = correlation_module.dispatch_correlation(
        work_item_id="bd-ib-5jvgfr",
        dispatch_id=None,
        factory="hp",
    )

    assert correlation is None
    span_module.emit_dispatch_span(correlation=correlation, spans_path=spans_path, now_ns=3)
    # Not merely empty: the file is never created, so a reader cannot mistake
    # "this invocation emitted nothing" for "this invocation emitted zero spans".
    assert not spans_path.exists()
    assert not spans_path.parent.exists()


def test_identifier_shaped_admits_exactly_the_engines_byte_set() -> None:
    """The restated admission rule, one case per way a value can fail it."""
    module = _correlation_module()
    limit = module.IDENTIFIER_MAX_BYTES

    assert limit == 128
    # Passable: ASCII letters, ASCII digits, and the four extra bytes.
    for passable in ("bd-ib-5jvgfr", "01M4N4V6SEEKVVP88ST0CASGCP", "hp", "a.b_c:d-9", "x" * limit):
        assert module.is_identifier_shaped(value=passable) is True, passable
    # Refused: empty, over the byte limit, an ASCII byte outside the set,
    # and a non-ASCII character. Each is a DIFFERENT arm of the rule, so a
    # single bad-value case could pass while the others silently did not.
    for refused in ("", "x" * (limit + 1), "not a factory name", "bang!", "café"):
        assert module.is_identifier_shaped(value=refused) is False, refused
    # The limit is BYTES, not characters: this is 64 two-byte characters,
    # under the character limit and over the byte limit. A character-counting
    # rule would admit it and the engine would refuse the whole run.
    assert len("é" * 64) <= limit
    assert module.is_identifier_shaped(value="é" * 64) is False
