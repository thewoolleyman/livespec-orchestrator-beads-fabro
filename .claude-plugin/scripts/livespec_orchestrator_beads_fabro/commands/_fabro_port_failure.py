"""A failed Fabro run's failure block, classified, as `fabro inspect --json` reports it.

Split out of `_fabro_port_records` by cohesion: that module normalizes a run
LISTING or an `inspect` record into the shape livespec reads, while this one
answers the narrower question of WHY a run failed and whether retrying it could
possibly help. The provider spend-ceiling detection, the cause chain and the
permanent-category rewrite all serve that one question.

TWO BLOCK SHAPES REACH THIS READER, and no engine is named anywhere below,
because the discriminator is the block's own structure rather than a version
string a payload does not carry:

- a FLAT block keying `category` / `signature` / `causes` at its own top level,
  which is what the pinned 0.254 build's `checkpoint.failure` carries, and
- a NESTED block keying `{reason, detail: {message, category}}`, which BOTH
  builds carry at `conclusion.failure` — measured on 0.254 on 2026-08-20 (the
  six real payloads behind `test_fabro_port_inspect_list_shape`) and on the
  Petri-era 0.378.0-nightly.0 candidate on 2026-10-08 (research notes 006 and
  007 of `plan/fabro-currency`).

The Petri-era build drops `causes` and `signature` entirely, so there the
nested `detail` is the ONLY carrier of both the message and the category.
Reading the nested shape is therefore not an engine branch — it is the shape
both engines already emit, and the pinned build merely happened to ALSO be
readable through its flat checkpoint block, which is why the nested one went
unread for so long.

FAIL CLOSED ON A BLOCK THIS READER DOES NOT RECOGNIZE. A block yielding no
cause, no category and no signature returns `None` rather than an empty
`FabroFailureDetail`. The difference matters at the consumer: `None` says "this
record shows no classifiable failure", which the dispatcher treats as an
unclassified failure and routes conservatively, whereas a populated record
carrying three `None` fields would assert that the failure WAS classified and
found to be nothing in particular. A guess here is laundered into a retry
decision, which is why the unknown variant is refused instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._fabro_port_records import fabro_inspect_record
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "FabroFailureDetail",
    "fabro_failure_detail_from_payload",
]

# The category a PERMANENT failure is rewritten to. Fabro's own classifier
# labels these `transient_infra`, which is what makes them retryable; a failure
# that cannot succeed on retry is deterministic by definition.
_PERMANENT_CATEGORY = "deterministic"
_TRANSIENT_SIGNATURE_SEGMENT = "|transient_infra|"

# Provider usage / spend ceilings, which are PERMANENT for the remainder of the
# billing or rolling-usage window: retrying spends more of an allowance that is
# already gone, and only a human (or the clock) clears them.
#
# `codex_error_info: "usage_limit_exceeded"` is the machine-readable
# discriminator and is matched FIRST because it cannot drift with copy edits.
# The prose hints are the fallback for providers that ship no such field.
#
# MEASURED 2026-08-22 across the 53 failed runs on the hp factory: 13 carried a
# diagnosable cause chain, and 10 of those were Codex usage-limit refusals
# reading "You've hit your usage limit. Visit .../codex/settings/usage ... or
# try again at <date>", every one classified `transient_infra` and retried. An
# 11th was the Anthropic form, "You've hit your org's monthly spend limit". Both
# vendors surface here, so both hint families belong in one list.
#
# NOTE the "usage" infix: the phrase is "hit your USAGE limit", so a hint of
# "hit your limit" does NOT substring-match it. That exact near-miss is why the
# fabro-side fix on `fix/classify-provider-spend-limit-not-transient` would not
# have caught the Codex form even once merged.
_PROVIDER_USAGE_LIMIT_FIELD = '"codex_error_info": "usage_limit_exceeded"'
_PROVIDER_CODEX = "codex"
_PROVIDER_ANTHROPIC = "anthropic"

# WHICH VENDOR a matched ceiling belongs to. Detection above is vendor-agnostic
# by design, so the vendor has to be READ OFF the cause; a fixed label records
# an Anthropic ceiling under the Codex vendor, which then refuses the next
# dispatch citing an exhaustion that never happened while holding no record for
# the vendor that actually refused.
#
# TWO PASSES, most-decisive first. A vendor MARKER in the cause text wins,
# because both measured forms name their vendor outright: the Codex form carries
# `codex_error_info` and `https://chatgpt.com/codex/settings/usage`, and the
# Anthropic form carries `claude.ai/settings/usage`. The hint's own vendor is the
# fallback for a provider that names itself nowhere in the sentence, and it is
# assigned from the family each hint was measured in.
_PROVIDER_MARKERS: tuple[tuple[str, str], ...] = (
    ("codex", _PROVIDER_CODEX),
    ("chatgpt.com", _PROVIDER_CODEX),
    ("anthropic", _PROVIDER_ANTHROPIC),
    ("claude", _PROVIDER_ANTHROPIC),
)
_PROVIDER_USAGE_LIMIT_HINTS: tuple[tuple[str, str], ...] = (
    ("hit your usage limit", _PROVIDER_CODEX),
    ("monthly spend limit", _PROVIDER_ANTHROPIC),
    ("spend limit", _PROVIDER_ANTHROPIC),
    ("usage limit exceeded", _PROVIDER_CODEX),
)


@dataclass(frozen=True, kw_only=True)
class FabroFailureDetail:
    """Structured failure block surfaced by `fabro inspect --json`.

    `provider_usage_limit` is the typed consumer seam for the dispatch-admission
    gate: it says this run died because the model provider's usage or spend
    ceiling was reached, so launching another sandbox against the same
    credential cannot produce a line of work. It is carried as a flag rather
    than left for each consumer to re-match against `cause` text.

    `provider_usage_limit_provider` names WHICH vendor refused, and is the value
    an exhaustion record is labelled with. It is set from the same single
    classification that sets the flag, so the two cannot disagree: it is
    non-None exactly when the flag is True.
    """

    cause: str | None
    category: str | None
    signature: str | None
    provider_usage_limit: bool = False
    provider_usage_limit_provider: str | None = None


def fabro_failure_detail_from_payload(*, payload: object | None) -> FabroFailureDetail | None:
    record = fabro_inspect_record(payload=payload)
    if record is None:
        return None
    typed_payload = cast("dict[object, object]", record)
    blocks = _failure_blocks(value=typed_payload)
    # A block CARRYING CAUSES wins over an earlier one that only carries a
    # category, because the cause chain is where the provider payload lives.
    # Traversal order alone put a bare `{"category": ...}` block first on 2 of
    # the 10 measured usage-limit runs (2026-08-22), which hid the very cause
    # this parser exists to surface.
    for block in blocks:
        if block.get("causes"):
            detail = _failure_detail(block=block)
            if detail is not None:
                return detail
    for block in blocks:
        detail = _failure_detail(block=block)
        if detail is not None:
            return detail
    return None


def _failure_blocks(*, value: object) -> tuple[dict[object, object], ...]:
    blocks: list[dict[object, object]] = []
    if isinstance(value, dict):
        mapping = cast("dict[object, object]", value)
        raw_failure = mapping.get("failure")
        if isinstance(raw_failure, dict):
            blocks.append(cast("dict[object, object]", raw_failure))
        for nested in mapping.values():
            blocks.extend(_failure_blocks(value=nested))
    elif isinstance(value, list):
        values = cast("list[object]", value)
        for nested in values:
            blocks.extend(_failure_blocks(value=nested))
    return tuple(blocks)


def _nested_detail(*, block: dict[object, object]) -> dict[object, object]:
    """The block's own `detail` mapping, or an empty one when it carries none.

    An empty mapping rather than `None` keeps the two readers below single
    expressions: "no `detail` at all" and "a `detail` carrying neither key" are
    the same answer to the caller, and distinguishing them here would only move
    the branch outward without giving it anything to decide.
    """
    nested = block.get("detail")
    if isinstance(nested, dict):
        return cast("dict[object, object]", nested)
    return {}


def _failure_detail(*, block: dict[object, object]) -> FabroFailureDetail | None:
    causes = _cause_values(value=block.get("causes"))
    nested = _nested_detail(block=block)
    nested_message = _str_value(value=nested.get("message"))
    # The classifier scans the cause chain AND the nested message, because the
    # two engines put the same sentence in different places: the pinned build
    # carries a provider spend ceiling in `causes`, while the Petri-era build
    # drops `causes` entirely and leaves that sentence in `detail.message`. A
    # scan of `causes` alone reports a ceiling as an ordinary retryable failure
    # on that engine, and the admission gate then launches another sandbox
    # against an allowance that is already spent.
    classifiable = causes if nested_message is None else (*causes, nested_message)
    permanent_cause = _permanent_cause(causes=classifiable)
    # `_root_cause` keeps reading the CHAIN only — its outermost-first ordering
    # is a property of the chain, not of the nested block — so the nested
    # message is the fallback for the engine that has no chain to read.
    selected = permanent_cause or _root_cause(causes=causes) or nested_message
    cause = selected if selected is None else (_provider_message(text=selected) or selected)
    reclassified = permanent_cause is not None
    usage_limit_provider = _provider_usage_limit_provider(causes=classifiable)
    category = _failure_category(
        category=_str_value(value=block.get("category"))
        or _str_value(value=nested.get("category")),
        reclassified=reclassified,
    )
    signature = _failure_signature(
        signature=_str_value(value=block.get("signature")),
        reclassified=reclassified,
    )
    if cause is None and category is None and signature is None:
        return None
    return FabroFailureDetail(
        cause=cause,
        category=category,
        signature=signature,
        provider_usage_limit=usage_limit_provider is not None,
        provider_usage_limit_provider=usage_limit_provider,
    )


def _cause_values(*, value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    values = cast("list[object]", value)
    return tuple(text for item in values if (text := _str_value(value=item)) is not None)


def _root_cause(*, causes: tuple[str, ...]) -> str | None:
    """The INNERMOST cause — the root of the chain, not its outer wrapper.

    A fabro cause chain is ordered outermost-first, so the last element is the
    one carrying the provider payload. Taking `causes[0]` instead is what made
    every provider failure read as a bare "ACP protocol error".

    MEASURED 2026-08-22 over every failure block in the 53 failed runs on the hp
    factory: all 17 blocks carry EXACTLY two causes, `causes[0]` is the literal
    constant "ACP protocol error" in 17 of 17, and `causes[-1]` holds the real
    message every time. The outer element is a fixed wrapper that identifies the
    transport, not the fault.
    """
    return causes[-1] if causes else None


def _permanent_cause(*, causes: tuple[str, ...]) -> str | None:
    """The most specific cause in the chain that retrying CANNOT resolve."""
    for text in causes:
        if _is_remote_compaction_404(text=text) or _is_provider_usage_limit(text=text):
            return text
    return None


def _provider_usage_limit_provider(*, causes: tuple[str, ...]) -> str | None:
    """The vendor whose ceiling this chain reports, or None if it reports none."""
    for text in causes:
        provider = _usage_limit_provider(text=text)
        if provider is not None:
            return provider
    return None


def _provider_message(*, text: str) -> str | None:
    """The provider's own message, lifted out of an embedded JSON error payload.

    The raw cause reads `Internal error: {"spawned_at": "<a cargo path>",
    "data": {"message": "<the useful sentence>", ...}}`. Surfacing it verbatim
    leads with the cargo path and buries the sentence that names the ceiling and
    its reset time, so the embedded `data.message` is preferred when the payload
    parses. Returns None when there is no JSON object or no message inside it,
    and the caller keeps the raw text.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    parsed = parse_json(text=text[start : end + 1])
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return None
    data_raw: object = cast("dict[str, Any]", parsed).get("data")
    if not isinstance(data_raw, dict):
        return None
    return _str_value(value=cast("dict[str, Any]", data_raw).get("message"))


def _is_provider_usage_limit(*, text: str) -> bool:
    """Whether this cause is a provider usage / spend ceiling."""
    return _usage_limit_provider(text=text) is not None


def _usage_limit_provider(*, text: str) -> str | None:
    """The vendor whose ceiling this cause reports, or None if it is not one.

    The structured field is checked on the WHITESPACE-NORMALIZED text, because
    its value is a machine token rather than prose; the hint list is the prose
    fallback and is matched case-insensitively. Recognition and attribution are
    one step deliberately — a second, separate vendor pass could answer for a
    cause the first pass never matched, which is how a fixed label gets
    reintroduced by accident.
    """
    normalized = " ".join(text.split())
    lowered = normalized.lower()
    hinted = next(
        (provider for hint, provider in _PROVIDER_USAGE_LIMIT_HINTS if hint in lowered),
        None,
    )
    if _PROVIDER_USAGE_LIMIT_FIELD not in normalized and hinted is None:
        return None
    marked = next(
        (provider for marker, provider in _PROVIDER_MARKERS if marker in lowered),
        None,
    )
    return marked if marked is not None else hinted


def _is_remote_compaction_404(*, text: str) -> bool:
    lowered = text.lower()
    return (
        "error running remote compact task" in lowered
        and "404 not found" in lowered
        and "responses/compact" in lowered
    )


def _failure_category(*, category: str | None, reclassified: bool) -> str | None:
    if reclassified:
        return _PERMANENT_CATEGORY
    return category


def _failure_signature(*, signature: str | None, reclassified: bool) -> str | None:
    if not reclassified or signature is None:
        return signature
    return signature.replace(_TRANSIENT_SIGNATURE_SEGMENT, f"|{_PERMANENT_CATEGORY}|")


def _str_value(*, value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
