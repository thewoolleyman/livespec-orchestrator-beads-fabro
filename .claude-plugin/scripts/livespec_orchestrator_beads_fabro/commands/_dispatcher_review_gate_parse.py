"""Review-gate telemetry parser for Fabro JSONL events."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

__all__: list[str] = [
    "ReviewGateTelemetry",
    "parse_review_gate_events",
]

_REVIEW_CAP_VISITS = 3


@dataclass(frozen=True, kw_only=True)
class ReviewGateTelemetry:
    """Derived review-gate telemetry for one completed Fabro run."""

    verdict: str
    fix_rounds: int
    hit_cap: bool
    shipped_on_cap: bool


@dataclass(frozen=True, kw_only=True)
class _ReviewEdge:
    order_key: int
    to_node: str
    reason: str
    preferred_label: str | None


def parse_review_gate_events(*, events_jsonl: str) -> ReviewGateTelemetry:
    """Derive terminal review-gate attributes from `fabro events --json` JSONL."""
    review_edges = tuple(_review_edges(events_jsonl=events_jsonl))
    fix_rounds = sum(1 for edge in review_edges if edge.to_node == "review_fix")
    visit_count = len(review_edges)
    terminal_edge = max(review_edges, key=lambda edge: edge.order_key) if review_edges else None
    hit_cap = (
        terminal_edge is not None
        and terminal_edge.reason == "unconditional"
        and visit_count >= _REVIEW_CAP_VISITS
    )
    shipped_on_cap = terminal_edge is not None and hit_cap and terminal_edge.to_node == "pr"
    verdict = _terminal_verdict(edge=terminal_edge)
    return ReviewGateTelemetry(
        verdict=verdict,
        fix_rounds=fix_rounds,
        hit_cap=hit_cap,
        shipped_on_cap=shipped_on_cap,
    )


def _review_edges(*, events_jsonl: str) -> list[_ReviewEdge]:
    edges: list[_ReviewEdge] = []
    for index, line in enumerate(events_jsonl.splitlines()):
        parsed = _parse_line(line=line)
        if parsed is None or _event_name(event=parsed) != "edge.selected":
            continue
        properties = _properties(event=parsed)
        if properties.get("from_node") != "review":
            continue
        to_node = properties.get("to_node")
        reason = properties.get("reason")
        preferred_label = properties.get("preferred_label")
        if not isinstance(to_node, str) or not isinstance(reason, str):
            continue
        edges.append(
            _ReviewEdge(
                order_key=index,
                to_node=to_node,
                reason=reason,
                preferred_label=preferred_label if isinstance(preferred_label, str) else None,
            )
        )
    return edges


def _parse_line(*, line: str) -> dict[str, Any] | None:
    stripped = line.strip()
    if stripped == "":
        return None
    try:
        parsed_raw: object = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed_raw, dict):
        return None
    return cast("dict[str, Any]", parsed_raw)


def _event_name(*, event: dict[str, Any]) -> str | None:
    for key in ("event", "name", "event_name", "type"):
        value: object = event.get(key)
        if isinstance(value, str):
            return value
    return None


def _properties(*, event: dict[str, Any]) -> dict[str, object]:
    properties_raw: object = event.get("properties")
    if isinstance(properties_raw, dict):
        return cast("dict[str, object]", properties_raw)
    return event


def _terminal_verdict(*, edge: _ReviewEdge | None) -> str:
    if edge is None or edge.preferred_label not in {"approve", "fix"}:
        return "unknown"
    return edge.preferred_label
