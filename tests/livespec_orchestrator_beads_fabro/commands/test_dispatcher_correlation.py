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
from pathlib import Path
from typing import Any

_CORRELATION_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_correlation.py"
)
_CORRELATION_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_correlation"


def _correlation_module() -> Any:
    assert _CORRELATION_PATH.is_file()
    return importlib.import_module(_CORRELATION_MODULE)


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
