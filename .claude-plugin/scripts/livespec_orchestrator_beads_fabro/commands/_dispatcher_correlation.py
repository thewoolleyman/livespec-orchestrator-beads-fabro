"""The correlation identity one dispatch carries into the factory.

The dispatch span's trace and span ids are derived from the dispatch id
alone, because the `TRACEPARENT` a launch projects and the dispatch span
the Dispatcher emits have to name the SAME ids for the chain — dispatch
span, then server run, then worker run, then `run_turn` — to join into one
trace. Deriving both from one deterministic function is what makes that
equality STRUCTURAL: there is no clock, no counter and no randomness for
the two sites to disagree about, and re-deriving for the same dispatch id
reproduces the pair exactly. A shared mutable variable threaded between
the emitter and the launcher would hold only until a third caller appears.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

__all__: list[str] = [
    "CORRELATION_LABEL_KEYS",
    "SPAN_ID_DOMAIN",
    "SPAN_ID_HEX_DIGITS",
    "TRACE_ID_DOMAIN",
    "TRACE_ID_HEX_DIGITS",
    "DispatchCorrelation",
    "DispatchSpanIds",
    "correlation_attributes",
    "dispatch_span_ids",
    "dispatch_traceparent",
    "non_zero_hex",
]

# W3C widths for a trace id and a span id, in lowercase hexadecimal digits.
TRACE_ID_HEX_DIGITS = 32
SPAN_ID_HEX_DIGITS = 16

# The two hash domains. They differ so a span id cannot be a prefix of its
# own trace id: one digest truncated to both widths would make every span
# id a substring of its parent trace, which reads as a correlation
# coincidence to anyone debugging a join.
TRACE_ID_DOMAIN = "livespec.dispatch.trace"
SPAN_ID_DOMAIN = "livespec.dispatch.span"

# Traceparent version `00` with the sampled flag set, so the engine's
# extract keeps this span as the PARENT instead of starting the server run
# span as its own root. An unsampled flag would leave the join declared and
# the parent silently dropped.
_TRACEPARENT_VERSION = "00"
_TRACEPARENT_FLAGS = "01"


# The span-attribute names the three values carry, in the order every
# surface emits them. The SAME three names `_otel_scrub`'s forwarding
# allowlist and `_otel_enrich`'s correlation join already key on, so a
# dispatch span and a Fabro span describe one dispatch in one vocabulary.
CORRELATION_LABEL_KEYS: tuple[str, ...] = (
    "work.item.id",
    "livespec.dispatch.id",
    "livespec.dispatch.factory",
)


@dataclass(frozen=True, kw_only=True)
class DispatchCorrelation:
    """The three values one dispatch correlates every span of its run by."""

    work_item_id: str
    dispatch_id: str
    factory: str


@dataclass(frozen=True, kw_only=True)
class DispatchSpanIds:
    """One dispatch span's W3C identity, derived from its dispatch id."""

    trace_id: str
    span_id: str


def correlation_attributes(*, correlation: DispatchCorrelation) -> dict[str, str]:
    """The correlation values, keyed by their span-attribute name."""
    values = (correlation.work_item_id, correlation.dispatch_id, correlation.factory)
    return dict(zip(CORRELATION_LABEL_KEYS, values, strict=True))


def dispatch_span_ids(*, dispatch_id: str) -> DispatchSpanIds:
    """Derive one dispatch span's trace and span ids from the dispatch id."""
    return DispatchSpanIds(
        trace_id=_derived_hex(
            domain=TRACE_ID_DOMAIN,
            dispatch_id=dispatch_id,
            digits=TRACE_ID_HEX_DIGITS,
        ),
        span_id=_derived_hex(
            domain=SPAN_ID_DOMAIN,
            dispatch_id=dispatch_id,
            digits=SPAN_ID_HEX_DIGITS,
        ),
    )


def dispatch_traceparent(*, dispatch_id: str) -> str:
    """The W3C `traceparent` naming this dispatch's own span as the parent."""
    ids = dispatch_span_ids(dispatch_id=dispatch_id)
    return f"{_TRACEPARENT_VERSION}-{ids.trace_id}-{ids.span_id}-{_TRACEPARENT_FLAGS}"


def non_zero_hex(*, digits: str) -> str:
    """Return `digits`, or the deterministic stand-in for an all-zero id.

    W3C reserves the all-zero trace and span id as invalid, so a digest
    that truncated to zeros would ship an id a receiver drops silently.
    The stand-in keeps the width and is a constant edit, not a random
    value, so the substitution is itself re-derivable.
    """
    if digits.strip("0") != "":
        return digits
    return digits[:-1] + "1"


def _derived_hex(*, domain: str, dispatch_id: str, digits: int) -> str:
    digest = hashlib.sha256(f"{domain}:{dispatch_id}".encode()).hexdigest()
    return non_zero_hex(digits=digest[:digits])
