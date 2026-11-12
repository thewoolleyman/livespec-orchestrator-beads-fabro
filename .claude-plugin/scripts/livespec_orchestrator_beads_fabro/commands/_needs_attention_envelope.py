"""Consumer-side tolerant parse of the needs-attention machine envelope.

The needs-attention machine-envelope contract in `SPECIFICATION/contracts.md`
states the per-item field stability and consumer-tolerance posture: the field
guarantees hold PER ITEM, so a consumer MUST be able to skip an item it cannot
parse —
malformed fields, or an unknown `kind` it chooses not to render — while consuming
the REST of the envelope and surfacing what it skipped. A consumer whose parse
discards the WHOLE envelope on one bad item is non-conforming; one malformed item
blinding the entire inbox is the failure mode the posture exists to forbid. That
posture binds this repository's OWN consuming surfaces, which is why the operator
Markdown surface reads the wire envelope through this module rather than reading
the in-memory composition it was built from.

Two boundaries are deliberately different here, and conflating them is the easy
mistake. A malformed ITEM costs that item and nothing else. A payload that is not
JSON at all, or that carries no `attention` array, has no items to salvage — the
tolerance posture is about one bad item among good ones, so refusing an
unreadable envelope wholesale is conformance rather than a violation. Both cases
surface; neither is silent.

`kind` is an OPEN string set on the wire because wire evolution is additive, so
an unrecognized `kind` is a WELL-FORMED item here and is rendered generically. It
is never a skip reason — a consumer that skipped it would go blind on precisely
the new fact classes a release was shipped to announce.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import cast

from livespec_runtime.attention_item import AttentionItem

from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "ConsumedEnvelope",
    "ConsumedItem",
    "SkippedEntry",
    "parse_envelope",
    "render_envelope_markdown",
    "render_json",
    "render_markdown",
]

# The `kind` values this consumer renders with its own shape. Anything else is
# still a well-formed item; it is annotated with its kind so an operator can see
# a fact class this build predates rather than silently not see it.
_RENDERED_KINDS = frozenset(
    (
        "human-valve",
        "impl",
        "spec",
        "plan",
        "hygiene",
        "internal",
        "host-only",
    )
)
# `urgency` is a CLOSED set on the wire: the additive-evolution clause admits new
# fields and new `kind` values, and nothing else. An unrecognized urgency is a
# malformed field, so it skips-and-surfaces.
_URGENCIES = frozenset(("high", "medium", "low"))
_WHOLE_ENVELOPE_POSITION = -1


@dataclass(frozen=True, slots=True, kw_only=True)
class ConsumedItem:
    """One well-formed envelope item, flattened to what this consumer renders."""

    id: str
    kind: str
    urgency: str
    summary: str
    repo: str
    handoff_kind: str
    handoff_command: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SkippedEntry:
    """One entry the consumer could not parse, kept visible instead of dropped."""

    position: int
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ConsumedEnvelope:
    """The outcome of a tolerant parse: what was consumed, and what was skipped."""

    items: tuple[ConsumedItem, ...]
    skipped: tuple[SkippedEntry, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class _Rejected:
    """Why one entry could not be parsed into a `ConsumedItem`."""

    reason: str


def parse_envelope(*, envelope: str) -> ConsumedEnvelope:
    """Parse an envelope per-item, skipping and surfacing what will not parse."""
    payload = parse_json(text=envelope)
    if isinstance(payload, JsonParseFailure):
        return _unreadable(reason="envelope is not valid JSON")
    entries = _attention_entries(payload=payload)
    if entries is None:
        return _unreadable(reason='envelope carries no "attention" array')
    items: list[ConsumedItem] = []
    skipped: list[SkippedEntry] = []
    for position, entry in enumerate(entries):
        parsed = _consumed_item(entry=entry)
        if isinstance(parsed, _Rejected):
            skipped.append(SkippedEntry(position=position, reason=parsed.reason))
        else:
            items.append(parsed)
    return ConsumedEnvelope(items=tuple(items), skipped=tuple(skipped))


def render_envelope_markdown(*, envelope: str) -> str:
    """Render an envelope for an operator, surfacing every skipped entry."""
    consumed = parse_envelope(envelope=envelope)
    if not consumed.items and not consumed.skipped:
        return "No attention items.\n"
    lines: list[str] = ["# Needs Attention", ""]
    lines.extend(line for item in consumed.items for line in _item_lines(item=item))
    if consumed.skipped:
        lines.extend(["## Skipped malformed items", ""])
        lines.extend(_skipped_line(entry=entry) for entry in consumed.skipped)
    return "\n".join(lines) + "\n"


def render_json(*, attention: list[AttentionItem]) -> str:
    """Serialize the producer's attention facts into its wire envelope."""
    return (
        json.dumps({"attention": [asdict(item) for item in attention]}, indent=2, sort_keys=True)
        + "\n"
    )


def render_markdown(*, attention: list[AttentionItem]) -> str:
    """Render the producer's own wire envelope through the tolerant consumer."""
    return render_envelope_markdown(envelope=render_json(attention=attention))


def _item_lines(*, item: ConsumedItem) -> list[str]:
    kind_note = "" if item.kind in _RENDERED_KINDS else f" (kind `{item.kind}`)"
    return [
        f"- `{item.id}` [{item.urgency}]{kind_note} {item.summary}",
        f"  - Handoff: `{item.handoff_command}`",
    ]


def _skipped_line(*, entry: SkippedEntry) -> str:
    if entry.position == _WHOLE_ENVELOPE_POSITION:
        return f"- envelope: {entry.reason}"
    return f"- item {entry.position}: {entry.reason}"


def _unreadable(*, reason: str) -> ConsumedEnvelope:
    return ConsumedEnvelope(
        items=(),
        skipped=(SkippedEntry(position=_WHOLE_ENVELOPE_POSITION, reason=reason),),
    )


def _attention_entries(*, payload: object) -> list[object] | None:
    if not isinstance(payload, dict):
        return None
    entries = cast("dict[str, object]", payload).get("attention")
    if not isinstance(entries, list):
        return None
    return list(cast("list[object]", entries))


def _consumed_item(*, entry: object) -> ConsumedItem | _Rejected:
    if not isinstance(entry, dict):
        return _Rejected(reason="entry is not a JSON object")
    obj = cast("dict[str, object]", entry)
    scalars = _scalar_fields(obj=obj)
    if isinstance(scalars, _Rejected):
        return scalars
    identifier, kind, urgency, summary = scalars
    repo = _nested_str(obj=obj, key="source_ref", field="repo")
    if repo is None:
        return _Rejected(reason="missing or malformed `source_ref.repo`")
    handoff_kind = _nested_str(obj=obj, key="handoff", field="kind")
    handoff_command = _nested_str(obj=obj, key="handoff", field="command")
    if handoff_kind is None or handoff_command is None:
        return _Rejected(reason="missing or malformed `handoff.kind` / `handoff.command`")
    return ConsumedItem(
        id=identifier,
        kind=kind,
        urgency=urgency,
        summary=summary,
        repo=repo,
        handoff_kind=handoff_kind,
        handoff_command=handoff_command,
    )


def _scalar_fields(*, obj: dict[str, object]) -> tuple[str, str, str, str] | _Rejected:
    identifier = _str_field(obj=obj, key="id")
    kind = _str_field(obj=obj, key="kind")
    summary = _str_field(obj=obj, key="summary")
    if identifier is None or kind is None or summary is None:
        return _Rejected(reason="missing or malformed `id` / `kind` / `summary`")
    urgency = _str_field(obj=obj, key="urgency")
    if urgency is None or urgency not in _URGENCIES:
        return _Rejected(reason="`urgency` is outside the closed high/medium/low set")
    return (identifier, kind, urgency, summary)


def _str_field(*, obj: dict[str, object], key: str) -> str | None:
    value = obj.get(key)
    return value if isinstance(value, str) else None


def _nested_str(*, obj: dict[str, object], key: str, field: str) -> str | None:
    nested = obj.get(key)
    if not isinstance(nested, dict):
        return None
    return _str_field(obj=cast("dict[str, object]", nested), key=field)
