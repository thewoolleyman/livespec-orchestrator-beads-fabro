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
    message: object = cast("dict[str, Any]", data_raw).get("message")
    if not isinstance(message, str):
        return None
    return message.strip() or None


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
