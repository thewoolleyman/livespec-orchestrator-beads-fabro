"""Shared fail-closed credential-scrub + OTLP attribute discipline (29f E1).

Single source of truth for the family's OTel egress hygiene, lifted out
of `_dispatcher_reflection` so the SAME policy is reused by the reflection
emitter AND the host-local enrich/scrub stage (`_otel_enrich`). Per
`loop-reflection-gate/telemetry-pipeline-architecture.md` §3.4
(decision 9) and `cc-otel-gap-analysis.md` §3.6, every span that egresses
toward Honeycomb passes through this discipline:

1. **Allowlist, not denylist.** Only named scalar attributes
   (ids / counts / statuses / durations / token + cost numbers) are
   forwarded — never "everything minus a denylist". `is_allowed_attr`
   is the single allowlist gate; `ATTRIBUTE_ALLOWLIST` is the named set
   (including the efj rider's `cost_usd` + token-count keys so a
   downstream cap can sum per-run cost — they are scalar numbers and
   scrub-safe).
2. **Fail-CLOSED on credential shape.** Any attribute value matching the
   credential-bearing-URL shape `scheme://user:secret@host` is REJECTED
   wholesale (replaced with a redaction marker), never partially shipped
   — a scrub miss must fail closed. Truncation is NOT scrubbing.
3. **No env values, no remote URLs.** Git remote URLs in this fleet embed
   PATs (`https://x-access-token:<PAT>@github.com/...`); the allowlist
   excludes URL-bearing attributes and the regex is the second line of
   defense.

This module is PURE (no I/O, no env reads) and stdlib-only — `scrub`,
`attr`, and `is_allowed_attr` are deterministic functions over their
inputs, amenable to direct + property-based testing.
"""

from __future__ import annotations

import re

__all__: list[str] = [
    "ATTRIBUTE_ALLOWLIST",
    "ATTR_MAX_LEN",
    "CREDENTIAL_URL_RE",
    "REDACTION_MARKER",
    "attr",
    "is_allowed_attr",
    "scrub",
]

# Max forwarded length for a string attribute value (defense against an
# unexpectedly large scalar). Truncation applies ONLY after the
# credential-shape check has passed — truncation is not scrubbing.
ATTR_MAX_LEN = 300

REDACTION_MARKER = "[redacted-credential-shaped-value]"

# Defense-in-depth: reject any attribute value that looks like a
# credential-bearing URL (`scheme://user:secret@host`) rather than
# redacting a substring — a scrub miss must fail closed
# (cc-otel-gap-analysis.md §3.6).
CREDENTIAL_URL_RE = re.compile(r"[a-zA-Z0-9_-]+:[^@\s/]+@")

# The forwarded-attribute allowlist (NOT a denylist). Every key here is a
# scalar id / count / status / duration / token+cost number that is safe
# to egress. A correlation triple (work.item.id / livespec.dispatch.id /
# fabro.run_id), plus the CC-native cost + token scalars the efj spend-cap
# reads THROUGH this pipeline (per the user-ratified 2026-06-13 rider).
# Anything not named here is DROPPED by the enrich stage before egress.
ATTRIBUTE_ALLOWLIST: frozenset[str] = frozenset(
    {
        # Correlation triple (§3.3) — stamped uniformly on every forwarded span.
        "work.item.id",
        "livespec.dispatch.id",
        "fabro.run_id",
        # CC session correlation (native; backfilled by the join map).
        "session.id",
        # Reflection stage scalars (already shipped by _dispatcher_reflection).
        "livespec.reflection.mode",
        "livespec.reflection.item_count",
        "livespec.reflection.green_count",
        "livespec.reflection.failed_count",
        "livespec.reflection.blocked_count",
        "livespec.reflection.green_streak",
        "livespec.reflection.finding_count",
        "livespec.reflection.finding.category",
        "livespec.reflection.finding.severity",
        "livespec.reflection.finding.count",
        "livespec.reflection.finding.subject",
        # Dispatcher / stage host-truth scalars (ids, statuses, exit codes).
        "livespec.stage",
        "livespec.outcome",
        "exit_code",
        "pr_number",
        "git.commit.sha",
        "git.branch",
        "repo",
        "agent.id",
        "ci.run_id",
        # CC-native per-API-call cost + token scalars (efj rider 2026-06-13):
        # scalar numbers, scrub-safe; kept so the efj cost sink sums
        # per-dispatch token usage by the correlation key and DERIVES the
        # per-run cost (`cost_usd` is corroboration when present; CC emits
        # cost only as a metric, so the host prices the tokens). `model`
        # selects the price table row; `request_id` is the per-API-call
        # dedup key the cost sink counts each call once by (efj wiring).
        "cost_usd",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
        "duration_ms",
        "model",
        "request_id",
        # Report-mode derived per-dispatch cost span (LIVESPEC_COST_MODE=report):
        # the API-equivalent cost observability signal the dispatcher emits at
        # loop exit so Honeycomb can query per-dispatch spend WITHOUT enforcing
        # it. All scalar numbers / a stable model-basis label, scrub-safe.
        "livespec.cost.usd_micros",
        "livespec.cost.usd",
        "livespec.cost.input_tokens",
        "livespec.cost.output_tokens",
        "livespec.cost.cache_creation_tokens",
        "livespec.cost.cache_read_tokens",
        "livespec.cost.model_basis",
        "livespec.cost.model_resolved",
        "livespec.cost.mode",
        "livespec.cost.observable",
        "livespec.cost.session_usd_micros",
    }
)


def is_allowed_attr(*, key: str) -> bool:
    """True iff `key` is an allowlisted scalar attribute safe to forward.

    The enrich stage drops any attribute whose key is not named in
    `ATTRIBUTE_ALLOWLIST` — allowlist, never denylist (§3.4 rule 1).
    """
    return key in ATTRIBUTE_ALLOWLIST


def scrub(*, value: str) -> str:
    """Fail-closed credential scrub: reject (do not redact) a token-URL value.

    A value matching the credential-URL shape is replaced WHOLESALE with
    `REDACTION_MARKER` rather than shipped partially (§3.4 rule 2). A
    plain value is passed through, truncated to `ATTR_MAX_LEN` — and that
    truncation runs ONLY on a value that already cleared the credential
    check, since truncation is not scrubbing.
    """
    if CREDENTIAL_URL_RE.search(value) is not None:
        return REDACTION_MARKER
    return value[:ATTR_MAX_LEN]


def attr(*, key: str, value: object) -> dict[str, object]:
    """Build one OTLP/HTTP-JSON attribute entry, scrubbing string values.

    Booleans and ints ship as `boolValue` / `intValue` (scalar, no scrub
    needed); everything else is stringified and run through `scrub`. The
    `bool` branch precedes `int` because `bool` is an `int` subclass in
    Python and must NOT be coerced to `intValue`.
    """
    if isinstance(value, bool):
        return {"key": key, "value": {"boolValue": value}}
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": str(value)}}
    text = scrub(value=str(value))
    return {"key": key, "value": {"stringValue": text}}
