"""Which Fabro failures retrying cannot resolve, and which vendor refused.

Cut out of `_fabro_port_records.py`, whose remaining concern is run identity,
status and the failure block itself. This module answers the narrower question
the failure block is INTERPRETED through: is this cause one that a retry cannot
clear, which vendor's ceiling does it report, and what did the provider itself
say inside its embedded payload.

Every entry point takes already-extracted text — a cause chain, or one cause —
so the module is pure and has no opinion about which engine's payload shape the
text was read out of. That is what lets the same classification serve both the
legacy `causes` chain and the Petri-era `failure.detail.message`.
"""

from __future__ import annotations

from typing import Any, cast

from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "fabro_permanent_cause",
    "fabro_provider_message",
    "fabro_usage_limit_provider",
]

# Provider usage / spend ceilings, which are PERMANENT for the remainder of the
# billing or rolling-usage window: retrying spends more of an allowance that is
# already gone, and only a human (or the clock) clears them.
#
# Codex's own error-info field is the machine-readable discriminator and is
# matched FIRST because it cannot drift with copy edits. The prose hints are the
# fallback for providers that ship no such field, and for the engine form that
# preserves only the failure message text.
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

# Codex's structured usage-limit token, as a (field name, value) PAIR per
# measured spelling. Both spellings the pinned adapters emit are recognised:
# the October payload carries the camelCase form while the August one carried
# the snake_case form, and the contract requires both.
#
# IT IS A FIELD LOOKUP, NEVER A BYTE STRING. The previous form compared the
# literal bytes `"codex_error_info": "usage_limit_exceeded"` against the
# whitespace-collapsed cause, which recognised exactly ONE serialization of ONE
# spelling: the camelCase payload could not match at all, and a serializer that
# emitted no space after the colon, or ordered the field before `message`,
# defeated it on the spelling it did know. Both of those are well-formed
# payloads carrying the same token, so the byte match was reporting a
# serialization difference as the absence of a ceiling.
#
# THE VALUE IS THE TOKEN, so the pair is checked together: `codex_error_info`
# also carries non-ceiling values, and keying on the field name alone would
# claim every Codex error that happens to populate it.
_CODEX_USAGE_LIMIT_FIELDS: tuple[tuple[str, str], ...] = (
    ("codexErrorInfo", "usageLimitExceeded"),
    ("codex_error_info", "usage_limit_exceeded"),
)
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

# EACH HINT IS A CONJUNCTION, never a single phrase, because two of the
# measured forms are only identifiable by a PAIR of literals: "You've hit your
# limit" alone is the prefix of several innocent sentences, and "spend limit"
# alone says nothing about whose allowance it was. The contract fixes the set
# (`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
# priority"): a newly measured form is added by a committed change here, never
# by loosening one of these literals into a broader match.
#
# THE MEASURED SET, each with the vendor the form was measured in:
#
# - `hit your session limit` -- Claude's five-hour session ceiling. Measured
#   2026-08-23, 2026-09-09 (twice) and 2026-10-09 as "You've hit your session
#   limit - resets 3:40am (UTC)", arriving with a structured `errorKind` of
#   `rate_limit`. Every one was classified `transient_infra` with NO provider
#   attributed, because no hint named it.
# - `hit your limit` plus `resets` -- the Petri-era Anthropic wording, where
#   the structured payload is gone and only the message text survives.
#   Measured as "You've hit your limit - resets Jul 31, 5am (UTC)"
#   (`plan/fabro-currency/research/004-acp-spend-limit-evidence.json`, mode
#   `usage-cap`). `resets` is load-bearing: it is what distinguishes a spent
#   allowance from a sentence that merely opens the same way.
# - `hit your weekly limit` -- Anthropic's weekly ceiling, measured on
#   2026-10-18 as "You've hit your weekly limit · resets Oct 23, 3pm (UTC)".
# - `hit your usage limit` -- the Codex form, measured ten times in the
#   2026-08-22 sweep below. Claude emits the same sentence, which is why
#   vendor attribution is a separate pass rather than read off the hint.
# - `org` plus `spend limit` -- the organisation spend ceiling, measured as
#   "You've hit your org's monthly spend limit - ask your admin to raise it at
#   claude.ai/settings/usage" (same evidence file, mode `monthly-cap`).
# - `usage limit exceeded` -- the Codex prose form of its structured token.
#
# The last two entries are the PRE-v127 broader hints, kept so nothing that
# used to be recognised stops being: they are strictly wider than the measured
# organisation form and sit after it so the measured conjunction is what
# matches the measured sentence.
_PROVIDER_USAGE_LIMIT_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("hit your session limit",), _PROVIDER_ANTHROPIC),
    (("hit your weekly limit",), _PROVIDER_ANTHROPIC),
    (("hit your limit", "resets"), _PROVIDER_ANTHROPIC),
    (("hit your usage limit",), _PROVIDER_CODEX),
    (("org", "spend limit"), _PROVIDER_ANTHROPIC),
    (("usage limit exceeded",), _PROVIDER_CODEX),
    (("monthly spend limit",), _PROVIDER_ANTHROPIC),
    (("spend limit",), _PROVIDER_ANTHROPIC),
)


def fabro_permanent_cause(*, causes: tuple[str, ...]) -> str | None:
    """The most specific cause in the chain that retrying CANNOT resolve."""
    for text in causes:
        if _is_remote_compaction_404(text=text) or _is_provider_usage_limit(text=text):
            return text
    return None


def fabro_usage_limit_provider(*, causes: tuple[str, ...]) -> str | None:
    """The vendor whose ceiling this chain reports, or None if it reports none."""
    for text in causes:
        provider = _usage_limit_provider(text=text)
        if provider is not None:
            return provider
    return None


def fabro_provider_message(*, text: str) -> str | None:
    """The provider's own message, lifted out of an embedded JSON error payload.

    The raw cause reads `Internal error: {"spawned_at": "<a cargo path>",
    "data": {"message": "<the useful sentence>", ...}}`. Surfacing it verbatim
    leads with the cargo path and buries the sentence that names the ceiling and
    its reset time, so the embedded `data.message` is preferred when the payload
    parses. Returns None when there is no JSON object or no message inside it,
    and the caller keeps the raw text.
    """
    payload = _embedded_object(text=text)
    if payload is None:
        return None
    data_raw: object = payload.get("data")
    if not isinstance(data_raw, dict):
        return None
    message: object = cast("dict[str, Any]", data_raw).get("message")
    if not isinstance(message, str):
        return None
    return message.strip() or None


def _is_provider_usage_limit(*, text: str) -> bool:
    """Whether this cause is a provider usage / spend ceiling."""
    return _usage_limit_provider(text=text) is not None


def _usage_limit_provider(*, text: str) -> str | None:
    """The vendor whose ceiling this cause reports, or None if it is not one.

    The structured token is read out of the PARSED payload, because it is a
    machine field rather than prose; the hint conjunctions are the prose
    fallback and are matched on the whitespace-normalized, case-folded text.
    Recognition and attribution are one step deliberately — a second, separate
    vendor pass could answer for a cause the first pass never matched, which is
    how a fixed label gets reintroduced by accident.
    """
    lowered = " ".join(text.split()).lower()
    hinted = next(
        (
            provider
            for literals, provider in _PROVIDER_USAGE_LIMIT_HINTS
            if all(literal in lowered for literal in literals)
        ),
        None,
    )
    if not _codex_structured_usage_limit(text=text) and hinted is None:
        return None
    marked = next(
        (provider for marker, provider in _PROVIDER_MARKERS if marker in lowered),
        None,
    )
    return marked if marked is not None else hinted


def _codex_structured_usage_limit(*, text: str) -> bool:
    """Whether an embedded payload carries Codex's usage-limit field."""
    payload = _embedded_object(text=text)
    return payload is not None and _carries_usage_limit_field(value=payload)


def _carries_usage_limit_field(*, value: object) -> bool:
    """Whether this parsed object, or an object nested in it, carries the field.

    The measured payload nests the field one level down, under `data`, so the
    walk follows OBJECT values rather than reading a fixed path: a serializer
    that moved the field up to the top level, or down one more level, carries
    the same token and should read the same way. It deliberately does NOT
    descend into arrays — no measured payload puts the field inside one, and an
    unmeasured shape is not guessed at.
    """
    if not isinstance(value, dict):
        return False
    mapping = cast("dict[str, Any]", value)
    if any(mapping.get(field) == token for field, token in _CODEX_USAGE_LIMIT_FIELDS):
        return True
    return any(_carries_usage_limit_field(value=nested) for nested in mapping.values())


def _embedded_object(*, text: str) -> dict[str, Any] | None:
    """The outermost embedded JSON object this cause text carries, parsed.

    Returns None when the text carries no brace pair, when what the braces
    enclose does not parse, or when it parses to something other than an
    object. Both readers above need the same parse, and they must agree: a
    cause whose payload the structured reader could parse while the message
    reader could not would surface a vendor's raw cargo-path text beside a
    typed verdict derived from inside it.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    parsed = parse_json(text=text[start : end + 1])
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return None
    return cast("dict[str, Any]", parsed)


def _is_remote_compaction_404(*, text: str) -> bool:
    lowered = text.lower()
    return (
        "error running remote compact task" in lowered
        and "404 not found" in lowered
        and "responses/compact" in lowered
    )
