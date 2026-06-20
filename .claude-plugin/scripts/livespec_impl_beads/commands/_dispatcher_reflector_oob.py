"""Out-of-band LLM reflector — the last consumer leg of the 29f pipeline.

This is the holistic, LLM-driven reviewer (loop-reflection-gate
best-practices §3 option (c); telemetry-pipeline-architecture.md §4.1) —
the consumer the mechanical 29f.2 stage (`_dispatcher_reflection`) hands
off to. It is SEPARATE from that mechanical stage: `_dispatcher_reflection`
journals a `reflection-file-handoff` and explicitly DEFERS ledger filing to
"the out-of-band reflector"; this module IS that reflector. It runs AFTER
the verdict is computed and immutable, fail-OPEN (never raises, never
changes an exit code), time-boxed, and behind a default-OFF env lever.

What it does, end to end:

  1. **Trigger** (best-practices §3 option (c)): fired as a 5th post-verdict
     stage in a fire-and-forget DAEMON thread, gated behind
     `LIVESPEC_REFLECTOR_OOB` (off|observe|file, default OFF — a real
     `claude -p` must NEVER auto-run on every dispatch; opt-in only). The
     multi-task cron/timer (§3 "cross-loop ... every N waves") is DEFERRED;
     this lands the minimal post-verdict trigger.

  2. **Reflector runtime** (best-practices §7 decision 9): a plain headless
     `claude -p` invocation — NOT a fabro workflow (a fabro run would make
     reflector runs themselves reflection subjects: a recursion hazard). It
     reads the already-scrubbed pass evidence from the hosted Honeycomb MCP
     (`mcp.honeycomb.io`) via a generated `--mcp-config` temp file, authed
     with `HONEYCOMB_MCP_API_KEY_LIVESPEC`. The reflector emits a STRUCTURED
     JSON findings list this module parses (`ReflectorFinding`).

  3. **Dedup-first issue filing** (best-practices §5.2, decision 6): the
     fingerprint is `sha256(category | stage-or-node | repo |
     normalized-subject)[:12]` — NEVER raw message text. Before filing, the
     open items carrying the `fingerprint:<hex>` label are queried: PRESENT
     → comment-bump (append occurrence evidence via the net-new
     `add_comment` verb); ABSENT → file; closed-with-`reflection-mute` →
     never re-file (digest only). At most `_MAX_NEW_ITEMS_PER_PASS` (3) NEW
     items per pass. Severity→priority: `critical`=P1 + banner; `warn`=P2/P3
     item only at ≥2 occurrences across waves; `info`=digest only.

  4. **Lessons — human-ratified via PR** (best-practices §7 decision 10): the
     reflector PROPOSES a lesson by opening a PR that edits the committed
     `lessons.md`; the human ratifies by MERGING that PR. The reflector
     NEVER auto-injects unratified lessons; the brief-injection consumer
     reads only the merged file. The git-branch/commit/push/`gh pr create`
     mechanism lives behind the injectable `LessonsProposer` seam (the test
     tier injects `RecordingLessonsProposer`; no real PR is ever opened in a
     test).

  5. **Verdict spans** (best-practices §1.2; telemetry §4.1): one
     `gen_ai.evaluation.result` span per finding, parented to the dispatch
     span, appended to the local spans file the host-local enrich stage
     forwards — the ESTABLISHED egress path, not a new one.

  6. **Scrub on every export** (decision 9 / telemetry §3.4): every span,
     issue body, and lesson text this module EXPORTS passes through the
     shared `_otel_scrub` (`attr` / `scrub` — fail-CLOSED on the
     credential-bearing-URL shape). Honeycomb data the reflector READS is
     already scrubbed by the enrich stage; anything written back is scrubbed
     again here.

  7. **Human summary echo** (best-practices §5.3): findings echo into the
     human summary on STDERR (the diagnostics channel where the mechanical
     stage's summary, sizing-warn, ledger, and janitor notices already go);
     stdout stays the machine outcomes array.

Auto-trip + time-box mirror the mechanical stage: after
`_AUTO_TRIP_THRESHOLD` (3) CONSECUTIVE errors the stage disables itself for
the rest of the process; the whole pass is bounded by
`_REFLECTOR_BUDGET_SECONDS`.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, cast

from livespec_impl_beads._beads_client import BeadsClient, IssueDraft, make_beads_client
from livespec_impl_beads._ids import new_work_item_id
from livespec_impl_beads.commands._config import resolve_store_config
from livespec_impl_beads.commands._dispatcher_engine import CommandResult, CommandRunner
from livespec_impl_beads.commands._otel_scrub import attr as _attr
from livespec_impl_beads.commands._otel_scrub import scrub as _scrub
from livespec_impl_beads.types import StoreConfig

__all__: list[str] = [
    "GitPrLessonsProposer",
    "LessonProposal",
    "LessonsProposer",
    "RecordingLessonsProposer",
    "ReflectorFinding",
    "ReflectorReport",
    "build_mcp_config",
    "claude_reflector_argv",
    "fingerprint",
    "parse_findings",
    "reset_auto_trip",
    "resolve_claude_path",
    "resolve_claude_timeout_seconds",
    "resolve_mode",
    "resolve_reflector_budget_seconds",
    "resolve_strict_mcp",
    "run_reflector_oob",
    "severity_priority",
]

# ---------------------------------------------------------------------------
# Levers + constants (NAMES of env vars, never secrets).
# ---------------------------------------------------------------------------

# The trigger lever (always wired). Default OFF so a real `claude -p` never
# fires on a plain dispatch; opt-in to `observe` (run + summary + spans, no
# ledger writes) or `file` (additionally dedup-file items + propose lessons).
_REFLECTOR_ENV = "LIVESPEC_REFLECTOR_OOB"
_MODE_OFF = "off"
_MODE_OBSERVE = "observe"
_MODE_FILE = "file"
_DEFAULT_MODE = _MODE_OFF

# The hosted Honeycomb MCP read endpoint + its management/MCP key env var
# (CONFIRMED present in the host env). Mirrors `_HONEYCOMB_INGEST_KEY_ENV`
# on the egress side — this is the SEPARATE read key, never the ingest key.
# The endpoint is the `/mcp` path, NOT the bare host: live probes show
# `https://mcp.honeycomb.io` → HTTP 404, while `https://mcp.honeycomb.io/mcp`
# is the served MCP endpoint (the same URL the working honeycomb plugin uses).
# The EU region variant is `https://mcp.eu1.honeycomb.io/mcp`.
_HONEYCOMB_MCP_KEY_ENV = "HONEYCOMB_MCP_API_KEY_LIVESPEC"
_HONEYCOMB_MCP_URL = "https://mcp.honeycomb.io/mcp"
_HONEYCOMB_MCP_SERVER_NAME = "honeycomb"

# The headless `claude -p` tool-permission scope (29f.8 gap 4). A headless
# `claude -p` defaults to NO tool permission, so without this the reflector's
# `--mcp-config` honeycomb server is never callable unattended and the review
# produces nothing. `mcp__<server>` grants every tool on that ONE configured
# MCP server (the minimal grant — NOT `--dangerously-skip-permissions`, which
# would also unlock Bash/Edit/etc. the reflector must never touch).
_HONEYCOMB_MCP_TOOL_SCOPE = f"mcp__{_HONEYCOMB_MCP_SERVER_NAME}"

# Default headless model for the reflector. The single-strong-judge review
# (best-practices §1.1) runs as one `claude -p` call; `LIVESPEC_REFLECTOR_MODEL`
# overrides the model if a different judge is wanted.
_REFLECTOR_MODEL_ENV = "LIVESPEC_REFLECTOR_MODEL"
_DEFAULT_REFLECTOR_MODEL = "claude-opus-4-8"

# Mechanical auto-trip + time-box (best-practices §6), mirroring the
# mechanical stage so a flapping reflector self-disables for the process.
_AUTO_TRIP_THRESHOLD = 3

# Time-box defaults (29f.8 gap 1). The session-8 live proof clocked a real
# reference-anchored Honeycomb review at ~371s (17 tool calls); the pre-29f.8
# 90s ceiling ALWAYS timed out, was reaped as a non-zero result, and fail-softed
# to 0 findings — the reflector silently did nothing in production. The claude
# subprocess ceiling is raised to 600s (margin over the observed 371s, and
# larger telemetry windows take longer), and the stage budget sits ABOVE it so
# the `claude -p` subprocess timeout (not the budget `_check_budget`) is the
# tripwire on a hung judge. Both are env-overridable via the resolvers below.
_DEFAULT_CLAUDE_TIMEOUT_SECONDS = 600.0
_DEFAULT_REFLECTOR_BUDGET_SECONDS = 660.0
_BUDGET_EXCEEDED_MESSAGE = "out-of-band reflector exceeded its scan time budget"

# Env levers (always wired; NAMES only, never secrets) tuning the time-box.
# An unset / unparseable value falls back to the committed default rather than
# crashing the fail-open stage (mirrors `_dispatcher_cost._resolve_cap`).
_CLAUDE_TIMEOUT_ENV = "LIVESPEC_REFLECTOR_CLAUDE_TIMEOUT_SECONDS"
_REFLECTOR_BUDGET_ENV = "LIVESPEC_REFLECTOR_BUDGET_SECONDS"

# Module-level back-compat aliases (the committed defaults). Kept so existing
# call sites / tests that read the constant still resolve, but the live values
# now flow through the env resolvers below.
_CLAUDE_TIMEOUT_SECONDS = _DEFAULT_CLAUDE_TIMEOUT_SECONDS
_REFLECTOR_BUDGET_SECONDS = _DEFAULT_REFLECTOR_BUDGET_SECONDS

# `claude` PATH resolution (29f.8 gap 3). Under `with-livespec-env.sh` the
# bash PATH is minimal (no `~/.local/bin`, where `claude` lives), so a bare
# `claude` argv[0] fail-opens with `FileNotFoundError: 'claude'` and the
# reflector silently does nothing. Resolution order: the explicit absolute-path
# env override → `shutil.which` → the conventional `~/.local/bin/claude` →
# bare `"claude"` (last-resort, lets the runner surface the FileNotFoundError).
_CLAUDE_PATH_ENV = "LIVESPEC_REFLECTOR_CLAUDE_PATH"
_CLAUDE_LOCAL_BIN_FALLBACK = "~/.local/bin/claude"

# Strict-MCP isolation lever (29f.8 follow-up). DEFAULT = strict ON: the
# headless judge loads ONLY the `--mcp-config` hosted honeycomb server (the
# durable API-key path proven working in PR #49) and IGNORES any ambient OAuth
# honeycomb plugin, whose token can expire unattended and silently blind the
# reflector. An explicit falsey value (`off` / `false` / `0` / `no`, case- and
# whitespace-insensitive) is the opt-out escape hatch that restores the prior
# behavior (ambient plugins allowed). Mirrors the always-wired env-lever shape
# of the other resolvers; NAME only, never a secret.
_STRICT_MCP_ENV = "LIVESPEC_REFLECTOR_STRICT_MCP"
_STRICT_MCP_FALSEY = frozenset({"off", "false", "0", "no"})

# Dedup-first filing constants (best-practices §5.2 / decision 6).
_MAX_NEW_ITEMS_PER_PASS = 3
_WARN_MIN_OCCURRENCES = 2  # `warn` only files at ≥2 occurrences across waves.
_FINGERPRINT_HEX_LEN = 12

# Severity → bd priority (best-practices §5.2). P1 critical, P2 warn, P4 info.
_PRIORITY_CRITICAL = 1
_PRIORITY_WARN = 2
_PRIORITY_INFO = 4

# Filing labels (best-practices §5.1). `reflection` marks the origin;
# `fingerprint:<hex>` is the dedup key; `reflection-mute` is honored (never
# minted here) on a closed item to suppress re-filing.
_LABEL_REFLECTION = "reflection"
_LABEL_FINGERPRINT_PREFIX = "fingerprint:"
_LABEL_REFLECTION_MUTE = "reflection-mute"

# OTLP verdict-span identity (the `gen_ai.evaluation.result` semconv slot,
# best-practices §1.2). One ExportTraceServiceRequest per line — the family
# capture format the enrich stage forwards.
_OTLP_SERVICE_NAME = "livespec-dispatcher"
_OTLP_SERVICE_NAMESPACE = "livespec-family"
_OTLP_SCOPE_NAME = "livespec.dispatcher.reflector"
_OTLP_SCOPE_VERSION = "0.1.0"
_EVAL_SPAN_NAME = "gen_ai.evaluation.result"
_SPAN_KIND_INTERNAL = 1


# ---------------------------------------------------------------------------
# Process-scoped auto-trip state (mirrors `_dispatcher_reflection`).
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class _AutoTripState:
    """Process-scoped mechanical auto-trip counter (mutable holder)."""

    consecutive_errors: int = 0
    tripped: bool = False


_AUTO_TRIP = _AutoTripState()


def reset_auto_trip() -> None:
    """Reset the process-level auto-trip state (test isolation seam)."""
    _AUTO_TRIP.consecutive_errors = 0
    _AUTO_TRIP.tripped = False


# ---------------------------------------------------------------------------
# Data shapes.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class ReflectorFinding:
    """One finding from the LLM reflector's structured JSON output.

    `category` is a stable, message-free key (so the fingerprint never
    churns on message text). `stage` is the stage-or-node the finding is
    about. `severity` is `critical` / `warn` / `info`. `subject` is the
    one-line human summary. `detail` is the narrative + evidence links.
    `occurrences` is the reflector's count of contributing runs across the
    sampled window (drives the `warn` ≥2 gate). `work_item_id` correlates
    the verdict span to the dispatch span (`GROUP BY work.item.id`).
    `score` / `label` are the eval verdict (0.0-1.0 + pass/fail).
    """

    category: str
    stage: str
    severity: str
    subject: str
    detail: str
    occurrences: int
    work_item_id: str | None
    score: float
    label: str


@dataclass(frozen=True, kw_only=True)
class ReflectorReport:
    """The reflector's full pass: parsed findings + filing disposition."""

    mode: str
    repo: str
    findings: tuple[ReflectorFinding, ...]
    filed: tuple[str, ...]
    bumped: tuple[str, ...]
    muted: tuple[str, ...]
    digested: tuple[str, ...]
    lesson_proposed: bool


@dataclass(frozen=True, kw_only=True)
class LessonProposal:
    """A proposed Reflexion-style lesson, opened as a PR for human ratify."""

    title: str
    body: str


# ---------------------------------------------------------------------------
# Lessons-via-PR seam (best-practices §7 decision 10).
# ---------------------------------------------------------------------------


class LessonsProposer(Protocol):
    """Seam for proposing a lesson by OPENING A PR that edits `lessons.md`.

    Production wires a git-branch + commit + push + `gh pr create` impl
    (kept behind the `CommandRunner` subprocess seam); the hermetic test
    tier injects `RecordingLessonsProposer` so NO real PR is ever opened in
    a test. The human ratifies a lesson by MERGING the PR — only merged
    lessons (the committed `lessons.md`) inject into briefs; the reflector
    never auto-injects an unratified lesson.
    """

    def propose(self, *, proposal: LessonProposal, repo: Path) -> str | None:
        """Open a PR proposing the lesson; return the PR URL/ref or None."""
        ...


@dataclass(kw_only=True)
class RecordingLessonsProposer:
    """Test-double `LessonsProposer`: records proposals, opens NO real PR."""

    proposals: list[LessonProposal] = field(default_factory=list)
    pr_ref: str | None = "https://example.invalid/pr/0"

    def propose(self, *, proposal: LessonProposal, repo: Path) -> str | None:
        _ = repo
        self.proposals.append(proposal)
        return self.pr_ref


# ---------------------------------------------------------------------------
# Pure helpers: mode, fingerprint, severity, argv, mcp-config, parsing.
# ---------------------------------------------------------------------------


def resolve_mode(*, raw: str | None) -> str:
    """Resolve the `LIVESPEC_REFLECTOR_OOB` lever to a known mode.

    Default is OFF (unlike the mechanical stage's `observe`): a real
    `claude -p` is expensive + side-effectful, so the out-of-band reflector
    is strictly opt-in. Only the explicit `observe` / `file` values arm it.
    """
    if raw == _MODE_OBSERVE:
        return _MODE_OBSERVE
    if raw == _MODE_FILE:
        return _MODE_FILE
    return _MODE_OFF


def _resolve_positive_float(*, environ: dict[str, str], name: str, default: float) -> float:
    """Resolve a positive-float env lever, falling back on absent/bad/≤0 values.

    Mirrors `_dispatcher_cost._resolve_cap`: an unset, empty, unparseable, or
    non-positive value reads as the committed default rather than crashing the
    fail-open stage (a 0/negative time-box would be a self-inflicted hang).
    """
    raw = environ.get(name, "")
    if raw == "":
        return default
    try:
        parsed = float(raw)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def resolve_claude_timeout_seconds(*, environ: dict[str, str]) -> float:
    """The `claude -p` subprocess ceiling: env override or the 600s default.

    Raised from the silently-fatal 90s (29f.8 gap 1): a real review took ~371s,
    so 90s ALWAYS timed out + fail-softed to 0 findings. Operators tune larger
    telemetry windows via `LIVESPEC_REFLECTOR_CLAUDE_TIMEOUT_SECONDS`. The
    fallback reads the module `_CLAUDE_TIMEOUT_SECONDS` alias (which is the
    committed default) so a test that monkeypatches it still flows through.
    """
    return _resolve_positive_float(
        environ=environ, name=_CLAUDE_TIMEOUT_ENV, default=_CLAUDE_TIMEOUT_SECONDS
    )


def resolve_reflector_budget_seconds(*, environ: dict[str, str]) -> float:
    """The whole-pass stage budget: env override or the 660s default.

    Sits ABOVE the claude subprocess ceiling so the subprocess timeout (not the
    `_check_budget` deadline) is the tripwire on a hung judge — the budget only
    bounds the post-claude filing/span work. Tuned via
    `LIVESPEC_REFLECTOR_BUDGET_SECONDS`. The fallback reads the module
    `_REFLECTOR_BUDGET_SECONDS` alias (the committed default) so a test that
    monkeypatches it still flows through.
    """
    return _resolve_positive_float(
        environ=environ, name=_REFLECTOR_BUDGET_ENV, default=_REFLECTOR_BUDGET_SECONDS
    )


def resolve_claude_path(*, environ: dict[str, str]) -> str:
    """Resolve the `claude` executable for the host dispatcher (29f.8 gap 3).

    Under `with-livespec-env.sh` the bash PATH is minimal (no `~/.local/bin`),
    so a bare `claude` argv[0] fail-opens with `FileNotFoundError: 'claude'`
    and the reflector silently does nothing. Resolution order: the explicit
    `LIVESPEC_REFLECTOR_CLAUDE_PATH` override → `shutil.which("claude")` → the
    conventional `~/.local/bin/claude` (only if it exists) → bare `"claude"`
    (last resort; lets the runner surface the FileNotFoundError honestly).
    """
    override = environ.get(_CLAUDE_PATH_ENV, "").strip()
    if override:
        return override
    found = shutil.which("claude")
    if found is not None:
        return found
    local_bin = Path(_CLAUDE_LOCAL_BIN_FALLBACK).expanduser()
    if local_bin.is_file():
        return str(local_bin)
    return "claude"


def resolve_strict_mcp(*, environ: dict[str, str]) -> bool:
    """Whether the headless judge runs with `--strict-mcp-config` (29f.8 follow-up).

    DEFAULT = strict ON: an unset (or empty) `LIVESPEC_REFLECTOR_STRICT_MCP`
    reads as `True`, so the judge loads ONLY the `--mcp-config` hosted
    Honeycomb server (the durable API-key path) and never falls back to an
    ambient OAuth honeycomb plugin whose token can expire unattended. An
    explicit falsey value (`off` / `false` / `0` / `no`, case- and
    whitespace-insensitive) is the opt-out escape hatch that restores the
    prior ambient-plugin-permitted behavior. Any other value keeps strict on.
    Mirrors the tolerant, always-wired shape of the other env resolvers.
    """
    return environ.get(_STRICT_MCP_ENV, "").strip().lower() not in _STRICT_MCP_FALSEY


def fingerprint(*, category: str, stage: str, repo: str, subject: str) -> str:
    """`sha256(category | stage-or-node | repo | normalized-subject)[:12]`.

    Keys off stable structure, NEVER raw message text (best-practices
    §5.2): the subject is normalized (lowercased, whitespace-collapsed) so
    incidental churn does not fork the fingerprint.
    """
    normalized = " ".join(subject.lower().split())
    material = f"{category}|{stage}|{repo}|{normalized}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:_FINGERPRINT_HEX_LEN]


def severity_priority(*, severity: str) -> int:
    """Map a finding severity onto a bd priority (best-practices §5.2)."""
    if severity == "critical":
        return _PRIORITY_CRITICAL
    if severity == "warn":
        return _PRIORITY_WARN
    return _PRIORITY_INFO


def build_mcp_config(*, api_key: str) -> dict[str, object]:
    """Build the `--mcp-config` JSON wiring the hosted Honeycomb MCP server.

    The reflector reads the already-scrubbed pass evidence from the hosted
    Honeycomb MCP at `https://mcp.honeycomb.io/mcp` over HTTP (the `/mcp`
    path — the bare host 404s; the EU region variant is
    `https://mcp.eu1.honeycomb.io/mcp`, not currently wired).

    Auth contract (Honeycomb headless-agent docs): the `Authorization:
    Bearer <key>` value MUST be a Honeycomb API key in the `<KEY_ID>:
    <SECRET_KEY>` composite form (a team-owner-generated key), scoped to
    "Model Context Protocol (Read)" + "Environments (Read)". A team-member
    key, or a key missing those scopes, fails the MCP handshake. The key
    VALUE flows only into the generated temp config (probe-only hygiene:
    never echoed, never journaled, never put on a span).
    """
    return {
        "mcpServers": {
            _HONEYCOMB_MCP_SERVER_NAME: {
                "type": "http",
                "url": _HONEYCOMB_MCP_URL,
                "headers": {"Authorization": f"Bearer {api_key}"},
            }
        }
    }


def claude_reflector_argv(
    *,
    prompt: str,
    mcp_config_path: Path,
    model: str,
    claude_path: str = "claude",
    strict_mcp: bool = True,
) -> list[str]:
    """Build the headless `claude -p` argv (best-practices §7 decision 9).

    A plain headless invocation — NOT a fabro run (recursion hazard). The
    prompt drives the reference-anchored single-strong-judge review; the
    MCP config grants read-only Honeycomb access; `--output-format json`
    yields a machine envelope the runtime parses.

    `claude_path` is the resolved executable (29f.8 gap 3): under the env
    wrapper's minimal PATH a bare `claude` is not found, so the host dispatcher
    passes an absolute path. `--allowedTools` scopes headless tool permission to
    the ONE configured honeycomb MCP server (29f.8 gap 4): a headless `claude -p`
    grants no tools by default, so without this the MCP review can call nothing
    and produces an empty pass. The scope is `mcp__<server>` — the minimal grant
    (every honeycomb tool, nothing else), NOT `--dangerously-skip-permissions`.

    `strict_mcp` (29f.8 follow-up; default `True`): when set, appends
    `--strict-mcp-config` so claude loads ONLY the `--mcp-config` honeycomb
    server and IGNORES any ambient OAuth honeycomb plugin (whose token can
    expire unattended and silently blind the reflector). The opt-out
    (`strict_mcp=False`) omits the flag, restoring the prior ambient-permitted
    behavior. The resolved value is threaded in by `run_claude_reflector`
    (via `resolve_strict_mcp`), mirroring how `claude_path` is threaded.
    """
    strict_flag = ["--strict-mcp-config"] if strict_mcp else []
    return [
        claude_path,
        "-p",
        prompt,
        "--mcp-config",
        str(mcp_config_path),
        "--allowedTools",
        _HONEYCOMB_MCP_TOOL_SCOPE,
        "--model",
        model,
        "--output-format",
        "json",
        *strict_flag,
    ]


def parse_findings(*, raw: str) -> tuple[ReflectorFinding, ...]:
    """Parse the reflector's structured-JSON output into `ReflectorFinding`s.

    Accepts either a bare findings array, or a `{"findings": [...]}`
    envelope, or the `claude -p --output-format json` wrapper whose
    `result` field carries the model's text (which itself holds the JSON).
    Malformed entries are skipped fail-soft (an LLM that emits one bad
    object must not blind the whole pass); a wholly-unparseable body yields
    no findings rather than raising.
    """
    payload = _coerce_findings_payload(raw=raw)
    findings: list[ReflectorFinding] = []
    for entry in payload:
        parsed = _parse_one_finding(entry=entry)
        if parsed is not None:
            findings.append(parsed)
    return tuple(findings)


def _coerce_findings_payload(*, raw: str) -> list[object]:
    text = raw.strip()
    if not text:
        return []
    try:
        top: object = json.loads(text)
    except json.JSONDecodeError:
        return []
    return _extract_findings_list(top=top)


def _extract_findings_list(*, top: object) -> list[object]:
    if isinstance(top, list):
        return list(cast("list[object]", top))
    if isinstance(top, dict):
        obj = cast("dict[str, object]", top)
        direct = obj.get("findings")
        if isinstance(direct, list):
            return list(cast("list[object]", direct))
        # `claude -p --output-format json` wraps the model text in `result`.
        result = obj.get("result")
        if isinstance(result, str):
            return _coerce_findings_payload(raw=result)
    return []


def _parse_one_finding(*, entry: object) -> ReflectorFinding | None:
    if not isinstance(entry, dict):
        return None
    obj = cast("dict[str, object]", entry)
    category = _str_field(obj=obj, key="category")
    severity = _str_field(obj=obj, key="severity")
    subject = _str_field(obj=obj, key="subject")
    if category is None or severity is None or subject is None:
        return None
    return ReflectorFinding(
        category=category,
        stage=_str_field(obj=obj, key="stage") or "",
        severity=severity,
        subject=subject,
        detail=_str_field(obj=obj, key="detail") or "",
        occurrences=_int_field(obj=obj, key="occurrences", default=1),
        work_item_id=_str_field(obj=obj, key="work_item_id"),
        score=_float_field(obj=obj, key="score", default=0.0),
        label=_str_field(obj=obj, key="label") or "",
    )


def _str_field(*, obj: dict[str, object], key: str) -> str | None:
    value = obj.get(key)
    return value if isinstance(value, str) else None


def _int_field(*, obj: dict[str, object], key: str, default: int) -> int:
    value = obj.get(key)
    if isinstance(value, bool):
        return default
    return value if isinstance(value, int) else default


def _float_field(*, obj: dict[str, object], key: str, default: float) -> float:
    value = obj.get(key)
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float):
        return float(value)
    return default


# ---------------------------------------------------------------------------
# Production seams: the real `claude -p` reflector + the real lessons PR.
# ---------------------------------------------------------------------------


def run_claude_reflector(
    *,
    runner: CommandRunner,
    prompt: str,
    repo: Path,
    api_key: str,
    model: str,
) -> CommandResult:
    """Invoke the headless `claude -p` reflector through the subprocess seam.

    Writes the `--mcp-config` to a throwaway temp file (the key VALUE never
    leaves this function except into that file), runs `claude -p` through
    the injected `CommandRunner` (so the hermetic tier injects a fake and
    NO real `claude -p` / MCP call ever fires in a test), and cleans the
    temp file up afterward. A non-zero / timeout result surfaces as data,
    never an exception (the runner contract).
    """
    config = build_mcp_config(api_key=api_key)
    handle = tempfile.NamedTemporaryFile(  # noqa: SIM115 - cleaned in finally
        mode="w", suffix="-honeycomb-mcp.json", delete=False, encoding="utf-8"
    )
    config_path = Path(handle.name)
    claude_path = resolve_claude_path(environ=dict(os.environ))
    timeout_seconds = resolve_claude_timeout_seconds(environ=dict(os.environ))
    strict_mcp = resolve_strict_mcp(environ=dict(os.environ))
    try:
        json.dump(config, handle)
        handle.close()
        return runner.run(
            argv=claude_reflector_argv(
                prompt=prompt,
                mcp_config_path=config_path,
                model=model,
                claude_path=claude_path,
                strict_mcp=strict_mcp,
            ),
            cwd=repo,
            timeout_seconds=timeout_seconds,
        )
    finally:
        config_path.unlink(missing_ok=True)


@dataclass(kw_only=True)
class GitPrLessonsProposer:
    """Production `LessonsProposer`: branch + commit + push + `gh pr create`.

    Every git/gh effect crosses the injected `CommandRunner` seam, so this
    is exercised in production but NEVER run in a test (the hermetic tier
    injects `RecordingLessonsProposer`). The proposal edits the committed
    `lessons.md`; the human ratifies by MERGING the PR — only merged
    lessons inject into briefs.
    """

    runner: CommandRunner
    lessons_path: Path = Path("research/loop-reflection-gate/lessons.md")
    branch_prefix: str = "reflector-lesson"

    def propose(self, *, proposal: LessonProposal, repo: Path) -> str | None:
        # Real git/gh effects; the unit tier injects the recording double,
        # and no test opens a real PR (the self-machinery hang-guard).
        return self._propose_impl(proposal=proposal, repo=repo)  # pragma: no cover

    def _propose_impl(  # pragma: no cover
        self, *, proposal: LessonProposal, repo: Path
    ) -> str | None:
        slug = fingerprint(category=proposal.title, stage="", repo=str(repo), subject=proposal.body)
        branch = f"{self.branch_prefix}-{slug}"
        target = repo / self.lessons_path
        existing = target.read_text(encoding="utf-8") if target.is_file() else ""
        scrubbed = _scrub(value=proposal.body)
        _ = target.write_text(existing + "\n" + scrubbed + "\n", encoding="utf-8")
        steps: list[list[str]] = [
            ["git", "-C", str(repo), "checkout", "-b", branch],
            ["git", "-C", str(repo), "add", str(self.lessons_path)],
            ["git", "-C", str(repo), "commit", "-m", f"docs(lessons): {proposal.title}"],
            ["git", "-C", str(repo), "push", "-u", "origin", branch],
        ]
        for argv in steps:
            result = self.runner.run(argv=argv, cwd=repo, timeout_seconds=_CLAUDE_TIMEOUT_SECONDS)
            if result.exit_code != 0:
                return None
        pr = self.runner.run(
            argv=["gh", "pr", "create", "--fill", "--head", branch],
            cwd=repo,
            timeout_seconds=_CLAUDE_TIMEOUT_SECONDS,
        )
        return pr.stdout.strip() if pr.exit_code == 0 else None


# ---------------------------------------------------------------------------
# Journal seam (mirrors `_dispatcher_reflection.JournalWriter`).
# ---------------------------------------------------------------------------


class JournalWriter(Protocol):
    """Append-one-record seam."""

    def append(self, *, record: dict[str, object]) -> None:
        """Persist one journal record."""
        ...


# ---------------------------------------------------------------------------
# The fail-open entry point fired by the dispatcher in a daemon thread.
# ---------------------------------------------------------------------------


def run_reflector_oob(
    *,
    repo: Path,
    journal: JournalWriter,
    spans_path: Path,
    runner: CommandRunner,
    lessons_proposer: LessonsProposer,
) -> None:
    """Run the fail-open out-of-band reflector pass (the daemon-thread body).

    NEVER raises and NEVER returns a verdict-relevant value: the caller has
    already computed + emitted the exit code. Honors the
    `LIVESPEC_REFLECTOR_OOB` lever, the process-level auto-trip, and the
    time-box. Any error is caught, journaled as `reflector-oob-error`, and
    counted toward the auto-trip — it never propagates out of the thread.
    """
    mode = resolve_mode(raw=os.environ.get(_REFLECTOR_ENV))
    if mode == _MODE_OFF or _AUTO_TRIP.tripped:
        return
    api_key = os.environ.get(_HONEYCOMB_MCP_KEY_ENV, "")
    if not api_key:
        journal.append(
            record={
                "stage": "reflector-oob-skipped",
                "reason": f"no {_HONEYCOMB_MCP_KEY_ENV} in env",
            }
        )
        return
    deadline = time.monotonic() + resolve_reflector_budget_seconds(environ=dict(os.environ))
    try:
        report = _run_pass(
            repo=repo,
            journal=journal,
            spans_path=spans_path,
            runner=runner,
            lessons_proposer=lessons_proposer,
            mode=mode,
            api_key=api_key,
            deadline=deadline,
        )
    except Exception as exc:
        _record_error(journal=journal, exc=exc)
        return
    _emit_summary(report=report)
    _AUTO_TRIP.consecutive_errors = 0


def _run_pass(  # noqa: PLR0913 - kw-only fail-open stage; each is an independent seam input.
    *,
    repo: Path,
    journal: JournalWriter,
    spans_path: Path,
    runner: CommandRunner,
    lessons_proposer: LessonsProposer,
    mode: str,
    api_key: str,
    deadline: float,
) -> ReflectorReport:
    """The scan-file-emit body (wrapped fail-open by `run_reflector_oob`)."""
    model = os.environ.get(_REFLECTOR_MODEL_ENV, "").strip() or _DEFAULT_REFLECTOR_MODEL
    result = run_claude_reflector(
        runner=runner, prompt=_reflector_prompt(repo=repo), repo=repo, api_key=api_key, model=model
    )
    _check_budget(deadline=deadline)
    findings = parse_findings(raw=result.stdout)
    _emit_spans(findings=findings, spans_path=spans_path)
    _check_budget(deadline=deadline)
    if mode == _MODE_OBSERVE:
        journal.append(
            record={"stage": "reflector-oob", "mode": mode, "finding_count": len(findings)}
        )
        return ReflectorReport(
            mode=mode,
            repo=str(repo),
            findings=findings,
            filed=(),
            bumped=(),
            muted=(),
            digested=tuple(f.category for f in findings),
            lesson_proposed=False,
        )
    return _file_findings(
        repo=repo,
        journal=journal,
        findings=findings,
        lessons_proposer=lessons_proposer,
        mode=mode,
        deadline=deadline,
    )


def _file_findings(
    *,
    repo: Path,
    journal: JournalWriter,
    findings: tuple[ReflectorFinding, ...],
    lessons_proposer: LessonsProposer,
    mode: str,
    deadline: float,
) -> ReflectorReport:
    """Dedup-first ledger filing (best-practices §5.2): file/bump/mute/digest."""
    client = _make_client(repo=repo)
    index = _label_index(client=client)
    disposition = _Disposition()
    new_count = 0
    for finding in findings:
        _check_budget(deadline=deadline)
        new_count = _dispose_one(
            finding=finding,
            repo=repo,
            client=client,
            index=index,
            disposition=disposition,
            new_count=new_count,
            journal=journal,
        )
    lesson_proposed = _maybe_propose_lesson(
        findings=findings, repo=repo, proposer=lessons_proposer, journal=journal
    )
    journal.append(
        record={
            "stage": "reflector-oob",
            "mode": mode,
            "finding_count": len(findings),
            "filed": list(disposition.filed),
            "bumped": list(disposition.bumped),
            "muted": list(disposition.muted),
            "digested": list(disposition.digested),
        }
    )
    return ReflectorReport(
        mode=mode,
        repo=str(repo),
        findings=findings,
        filed=tuple(disposition.filed),
        bumped=tuple(disposition.bumped),
        muted=tuple(disposition.muted),
        digested=tuple(disposition.digested),
        lesson_proposed=lesson_proposed,
    )


@dataclass(kw_only=True)
class _Disposition:
    """Accumulates the per-pass filing disposition (filed/bumped/muted/digest)."""

    filed: list[str] = field(default_factory=list)
    bumped: list[str] = field(default_factory=list)
    muted: list[str] = field(default_factory=list)
    digested: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class _OpenItem:
    """The minimal open-item facts the dedup index needs per fingerprint."""

    issue_id: str
    closed: bool
    muted: bool


def _dispose_one(  # noqa: PLR0913 - kw-only inner dispatcher; each arg is an independent collaborator.
    *,
    finding: ReflectorFinding,
    repo: Path,
    client: BeadsClient,
    index: dict[str, _OpenItem],
    disposition: _Disposition,
    new_count: int,
    journal: JournalWriter,
) -> int:
    """Dispose ONE finding per the lifecycle; return the updated new-item count."""
    fp = fingerprint(
        category=finding.category, stage=finding.stage, repo=str(repo), subject=finding.subject
    )
    existing = index.get(fp)
    if existing is not None and existing.muted:
        disposition.muted.append(fp)
        return new_count
    if existing is not None and not existing.closed:
        client.add_comment(issue_id=existing.issue_id, body=_bump_body(finding=finding))
        disposition.bumped.append(existing.issue_id)
        return new_count
    if not _should_file(finding=finding):
        disposition.digested.append(fp)
        return new_count
    if new_count >= _MAX_NEW_ITEMS_PER_PASS:
        disposition.digested.append(fp)
        return new_count
    issue_id = _file_new(finding=finding, fingerprint_hex=fp, client=client, repo=repo)
    disposition.filed.append(issue_id)
    journal.append(record={"stage": "reflector-oob-filed", "issue_id": issue_id, "fingerprint": fp})
    return new_count + 1


def _should_file(*, finding: ReflectorFinding) -> bool:
    """Severity gate (best-practices §5.2): info=digest; warn needs ≥2; critical always."""
    if finding.severity == "info":
        return False
    if finding.severity == "warn":
        return finding.occurrences >= _WARN_MIN_OCCURRENCES
    return finding.severity == "critical"


def _file_new(
    *, finding: ReflectorFinding, fingerprint_hex: str, client: BeadsClient, repo: Path
) -> str:
    """File a NEW reflection work-item carrying the dedup + reflection labels.

    Filed directly through `create_issue(IssueDraft)` (rather than the
    `WorkItem` → `append_work_item` path, which derives a FIXED label set
    and cannot carry the arbitrary `reflection` / `fingerprint:<hex>`
    labels). The body is scrubbed before it crosses the seam.
    """
    _ = repo
    config = _store_config(repo=repo)
    title = f"[reflection] {finding.category}: {_scrub(value=finding.subject)}"
    body = _scrub(value=finding.detail) if finding.detail else _scrub(value=finding.subject)
    issue_id = new_work_item_id(prefix=config.prefix)
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=issue_id,
            issue_type="bug" if finding.severity == "critical" else "task",
            title=title,
            description=body,
            priority=severity_priority(severity=finding.severity),
            assignee=None,
            created_at=_now_iso(),
            labels=[_LABEL_REFLECTION, f"{_LABEL_FINGERPRINT_PREFIX}{fingerprint_hex}"],
            metadata={},
            spec_id=None,
            parent_id=None,
        )
    )
    return issue_id


def _bump_body(*, finding: ReflectorFinding) -> str:
    """The scrubbed comment-bump body appended to a recurring item's ledger."""
    note = (
        f"reflection recurrence (x{finding.occurrences}): {finding.subject} "
        f"[severity={finding.severity}, score={finding.score:.2f}, label={finding.label}]"
    )
    return _scrub(value=note)


def _maybe_propose_lesson(
    *,
    findings: tuple[ReflectorFinding, ...],
    repo: Path,
    proposer: LessonsProposer,
    journal: JournalWriter,
) -> bool:
    """Propose ONE lesson-PR per pass when a critical finding warrants it.

    The reflector PROPOSES (opens a PR editing `lessons.md`); the human
    RATIFIES by merging it. We only propose for a critical, high-confidence
    finding (a verdict-integrity lesson) so the PR queue stays signal — the
    seam guarantees no real PR is opened in tests.
    """
    critical = [f for f in findings if f.severity == "critical"]
    if not critical:
        return False
    top = critical[0]
    proposal = LessonProposal(
        title=f"reflection lesson: {top.category}",
        body=_scrub(value=f"- {top.subject}\n\n  {top.detail}".strip()),
    )
    pr_ref = proposer.propose(proposal=proposal, repo=repo)
    journal.append(
        record={
            "stage": "reflector-oob-lesson-proposed",
            "pr_ref": pr_ref,
            "category": top.category,
        }
    )
    return True


# ---------------------------------------------------------------------------
# Store + dedup index helpers.
# ---------------------------------------------------------------------------


def _make_client(*, repo: Path) -> BeadsClient:
    return make_beads_client(config=_store_config(repo=repo))


def _store_config(*, repo: Path) -> StoreConfig:
    return resolve_store_config(cwd=repo, work_items_arg=None)


def _label_index(*, client: BeadsClient) -> dict[str, _OpenItem]:
    """Index every issue carrying a `fingerprint:<hex>` label by its hex key.

    A closed item with the `reflection-mute` label suppresses re-filing; an
    open item is the comment-bump target. The newest record per fingerprint
    wins (last-writer): the reflector files at most one item per fingerprint.
    """
    index: dict[str, _OpenItem] = {}
    for record in client.list_issues():
        labels = _record_labels(record=record)
        hex_key = _fingerprint_label_value(labels=labels)
        if hex_key is None:
            continue
        status = record.get("status")
        closed = status == "closed"
        muted = _LABEL_REFLECTION_MUTE in labels
        issue_id = record.get("id")
        if isinstance(issue_id, str):
            index[hex_key] = _OpenItem(issue_id=issue_id, closed=closed, muted=muted)
    return index


def _record_labels(*, record: dict[str, object]) -> list[str]:
    raw = record.get("labels")
    if not isinstance(raw, list):
        return []
    return [label for label in cast("list[object]", raw) if isinstance(label, str)]


def _fingerprint_label_value(*, labels: list[str]) -> str | None:
    for label in labels:
        if label.startswith(_LABEL_FINGERPRINT_PREFIX):
            return label[len(_LABEL_FINGERPRINT_PREFIX) :]
    return None


# ---------------------------------------------------------------------------
# Verdict spans + human summary + fail-open bookkeeping.
# ---------------------------------------------------------------------------


def _emit_spans(*, findings: tuple[ReflectorFinding, ...], spans_path: Path) -> None:
    """Append one `gen_ai.evaluation.result` span per finding to the spans file.

    Each verdict span is PARENTED to the dispatch span via the finding's
    `work.item.id` correlation (the established local-span-file → enrich
    egress path the host-local stage forwards — NOT a new path). Credential
    hygiene: every attribute crosses the shared scrub via `_attr`; only
    scalar verdict fields ship.
    """
    if not findings:
        return
    now_ns = time.time_ns()
    spans: list[dict[str, object]] = []
    for index, finding in enumerate(findings):
        eval_attrs: dict[str, object] = {
            "gen_ai.evaluation.name": finding.category,
            "gen_ai.evaluation.score": str(finding.score),
            "gen_ai.evaluation.label": finding.label,
            "gen_ai.evaluation.severity": finding.severity,
            "livespec.reflection.finding.category": finding.category,
            "livespec.reflection.finding.severity": finding.severity,
            "livespec.reflection.finding.count": finding.occurrences,
        }
        if finding.work_item_id is not None:
            eval_attrs["work.item.id"] = finding.work_item_id
        spans.append(
            _build_span(
                name=_EVAL_SPAN_NAME,
                span_id=f"reflector-eval-{index}",
                attrs=eval_attrs,
                parent_id=_dispatch_parent_id(work_item_id=finding.work_item_id),
                start_ns=now_ns,
                end_ns=now_ns,
            )
        )
    line = _request_line(spans=spans)
    spans_path.parent.mkdir(parents=True, exist_ok=True)
    with spans_path.open("a", encoding="utf-8") as handle:
        _ = handle.write(line + "\n")


def _dispatch_parent_id(*, work_item_id: str | None) -> str | None:
    """Derive the dispatch span id to parent the verdict span under.

    The dispatch span is keyed by `work.item.id`; an un-correlated finding
    (no work-item id) becomes a root verdict span rather than mis-parenting.
    """
    if work_item_id is None:
        return None
    return f"dispatch-{work_item_id}"


def _emit_summary(*, report: ReflectorReport) -> None:
    """Echo the reflector findings into the human summary on STDERR.

    stdout stays the machine outcomes array (the existing bare-array JSON
    contract); the reflector summary rides stderr, where the mechanical
    stage's summary / sizing-warn / ledger / janitor diagnostics already go
    (best-practices §5.3). Filed items also surface in the next `next` rank.
    """
    header = (
        f"reflector-oob ({report.mode}): {len(report.findings)} finding(s) — "
        f"{len(report.filed)} filed, {len(report.bumped)} bumped, "
        f"{len(report.muted)} muted, {len(report.digested)} digest-only"
    )
    lines = [header]
    for finding in report.findings:
        lines.append(f"reflector-oob [{finding.severity}] {finding.category}: {finding.subject}")
    if report.lesson_proposed:
        lines.append("reflector-oob: proposed a lesson via PR (merge to ratify)")
    _ = sys.stderr.write("\n".join(lines) + "\n")


def _record_error(*, journal: JournalWriter, exc: Exception) -> None:
    """Journal a reflector error fail-open and advance the auto-trip counter."""
    _AUTO_TRIP.consecutive_errors += 1
    reason = f"{type(exc).__name__}: {exc}"
    journal.append(record={"stage": "reflector-oob-error", "reason": reason})
    _ = sys.stderr.write(f"WARN: out-of-band reflector error (fail-open): {reason}\n")
    if _AUTO_TRIP.consecutive_errors >= _AUTO_TRIP_THRESHOLD:
        _AUTO_TRIP.tripped = True
        journal.append(
            record={
                "stage": "reflector-oob-tripped",
                "consecutive_errors": _AUTO_TRIP.consecutive_errors,
                "threshold": _AUTO_TRIP_THRESHOLD,
            }
        )


def _check_budget(*, deadline: float) -> None:
    if time.monotonic() > deadline:
        raise TimeoutError(_BUDGET_EXCEEDED_MESSAGE)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _reflector_prompt(*, repo: Path) -> str:
    """The reference-anchored single-strong-judge review prompt (§1.1).

    Instructs the judge to query Honeycomb GROUPed BY `work.item.id`,
    sample all `failed`/`blocked` runs + top-k latency/cost outliers + ~10%
    green as a control, and emit a STRUCTURED JSON findings list this
    module parses. The prompt is static text (no secret, no env value).
    """
    return (
        "You are the out-of-band reflector for the livespec dispatcher loop in "
        f"repo {repo.name}. Using the Honeycomb MCP tools, review the recent "
        "dispatch evidence: query GROUP BY work.item.id; sample ALL failed and "
        "blocked runs, the top-k latency and cost outliers, and ~10% of green "
        "runs as a control. Act as a single strong judge against the loop's "
        "reference behavior. Emit ONLY a JSON object of the shape "
        '{"findings": [{"category": str, "stage": str, "severity": '
        '"critical"|"warn"|"info", "subject": str, "detail": str, '
        '"occurrences": int, "work_item_id": str|null, "score": number, '
        '"label": str}]}. Never include credentials, tokens, or remote URLs '
        "with embedded credentials in any field."
    )


def _build_span(
    *,
    name: str,
    span_id: str,
    attrs: dict[str, object],
    parent_id: str | None,
    start_ns: int,
    end_ns: int,
) -> dict[str, object]:
    span: dict[str, object] = {
        "traceId": _hex_id(key="reflector-trace", nbytes=16),
        "spanId": _hex_id(key=span_id, nbytes=8),
        "name": name,
        "kind": _SPAN_KIND_INTERNAL,
        "startTimeUnixNano": str(start_ns),
        "endTimeUnixNano": str(end_ns),
        "attributes": [_attr(key=k, value=v) for k, v in attrs.items()],
    }
    if parent_id is not None:
        span["parentSpanId"] = _hex_id(key=parent_id, nbytes=8)
    return span


def _hex_id(*, key: str, nbytes: int) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[: nbytes * 2]


def _request_line(*, spans: list[dict[str, object]]) -> str:
    request: dict[str, object] = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": _OTLP_SERVICE_NAME}},
                        {
                            "key": "service.namespace",
                            "value": {"stringValue": _OTLP_SERVICE_NAMESPACE},
                        },
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": _OTLP_SCOPE_NAME, "version": _OTLP_SCOPE_VERSION},
                        "spans": spans,
                    }
                ],
            }
        ]
    }
    return json.dumps(request, separators=(",", ":"), sort_keys=True)
