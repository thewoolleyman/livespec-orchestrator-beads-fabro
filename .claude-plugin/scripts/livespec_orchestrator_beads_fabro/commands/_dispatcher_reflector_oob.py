from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._reflector_filing import (
    ReflectorReport,
    fingerprint,
    severity_priority,
)
from livespec_orchestrator_beads_fabro.commands._reflector_findings_parse import (
    ReflectorFinding,
    parse_findings,
)
from livespec_orchestrator_beads_fabro.commands._reflector_lessons import (
    GitPrLessonsProposer,
    LessonProposal,
    LessonsProposer,
    RecordingLessonsProposer,
)
from livespec_orchestrator_beads_fabro.commands._reflector_runtime import (
    build_mcp_config,
    claude_reflector_argv,
    resolve_claude_timeout_seconds,
    resolve_mode,
    resolve_strict_mcp,
)
from livespec_orchestrator_beads_fabro.commands._reflector_runtime import (
    run_pass as _run_pass,
)
from livespec_orchestrator_beads_fabro.commands._reflector_spans import (
    emit_summary as _emit_summary,
)
from livespec_orchestrator_beads_fabro.io import write_stderr

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

# The hosted Honeycomb MCP read endpoint + its management/MCP key env var
# (CONFIRMED present in the host env). Mirrors `_HONEYCOMB_INGEST_KEY_ENV`
# on the egress side — this is the SEPARATE read key, never the ingest key.
# The endpoint is the `/mcp` path, NOT the bare host: live probes show
# `https://mcp.honeycomb.io` → HTTP 404, while `https://mcp.honeycomb.io/mcp`
# is the served MCP endpoint (the same URL the working honeycomb plugin uses).
# The EU region variant is `https://mcp.eu1.honeycomb.io/mcp`.
_HONEYCOMB_MCP_KEY_ENV = "HONEYCOMB_MCP_API_KEY_LIVESPEC"

# The headless `claude -p` tool-permission scope (29f.8 gap 4). A headless
# `claude -p` defaults to NO tool permission, so without this the reflector's
# `--mcp-config` honeycomb server is never callable unattended and the review
# produces nothing. `mcp__<server>` grants every tool on that ONE configured
# MCP server (the minimal grant — NOT `--dangerously-skip-permissions`, which
# would also unlock Bash/Edit/etc. the reflector must never touch).

# Default headless model for the reflector. The single-strong-judge review
# (best-practices §1.1) runs as one `claude -p` call; `LIVESPEC_REFLECTOR_MODEL`
# overrides the model if a different judge is wanted.

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
_DEFAULT_REFLECTOR_BUDGET_SECONDS = 660.0
_BUDGET_EXCEEDED_MESSAGE = "out-of-band reflector exceeded its scan time budget"

# Env levers (always wired; NAMES only, never secrets) tuning the time-box.
# An unset / unparseable value falls back to the committed default rather than
# crashing the fail-open stage (mirrors `_dispatcher_cost._resolve_cap`).
_REFLECTOR_BUDGET_ENV = "LIVESPEC_REFLECTOR_BUDGET_SECONDS"
_CLAUDE_PATH_ENV = "LIVESPEC_REFLECTOR_CLAUDE_PATH"
_CLAUDE_LOCAL_BIN_FALLBACK = "~/.local/bin/claude"

# Module-level back-compat aliases (the committed defaults). Kept so existing
# call sites / tests that read the constant still resolve, but the live values
# now flow through the env resolvers below.
_REFLECTOR_BUDGET_SECONDS = _DEFAULT_REFLECTOR_BUDGET_SECONDS

# `claude` PATH resolution (29f.8 gap 3). Under `with-livespec-env.sh` the
# bash PATH is minimal (no `~/.local/bin`, where `claude` lives), so a bare
# `claude` argv[0] fail-opens with `FileNotFoundError: 'claude'` and the
# reflector silently does nothing. Resolution order: the explicit absolute-path
# env override → `shutil.which` → the conventional `~/.local/bin/claude` →
# bare `"claude"` (last-resort, lets the runner surface the FileNotFoundError).

# Strict-MCP isolation lever (29f.8 follow-up). DEFAULT = strict ON: the
# headless judge loads ONLY the `--mcp-config` hosted honeycomb server (the
# durable API-key path proven working in PR #49) and IGNORES any ambient OAuth
# honeycomb plugin, whose token can expire unattended and silently blind the
# reflector. An explicit falsey value (`off` / `false` / `0` / `no`, case- and
# whitespace-insensitive) is the opt-out escape hatch that restores the prior
# behavior (ambient plugins allowed). Mirrors the always-wired env-lever shape
# of the other resolvers; NAME only, never a secret.

# Dedup-first filing constants (best-practices §5.2 / decision 6).

# Severity → bd priority (best-practices §5.2). P1 critical, P2 warn, P4 info.

# Filing labels (best-practices §5.1). `reflection` marks the origin;
# `fingerprint:<hex>` is the dedup key; `reflection-mute` is honored (never
# minted here) on a closed item to suppress re-filing.

# OTLP verdict-span identity (the `gen_ai.evaluation.result` semconv slot,
# best-practices §1.2). One ExportTraceServiceRequest per line — the family
# capture format the enrich stage forwards.


# ---------------------------------------------------------------------------
# Process-scoped auto-trip state (mirrors `_dispatcher_reflection`).
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class _AutoTripState:
    consecutive_errors: int = 0
    tripped: bool = False


_AUTO_TRIP = _AutoTripState()


def reset_auto_trip() -> None:
    _AUTO_TRIP.consecutive_errors = 0
    _AUTO_TRIP.tripped = False


# ---------------------------------------------------------------------------
# Data shapes.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Pure helpers: mode, fingerprint, severity, argv, mcp-config, parsing.
# ---------------------------------------------------------------------------


def _resolve_positive_float(*, environ: dict[str, str], name: str, default: float) -> float:
    raw = environ.get(name, "")
    if raw == "":
        return default
    try:
        parsed = float(raw)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def resolve_claude_path(*, environ: dict[str, str]) -> str:
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


def resolve_reflector_budget_seconds(*, environ: dict[str, str]) -> float:
    return _resolve_positive_float(
        environ=environ, name=_REFLECTOR_BUDGET_ENV, default=_REFLECTOR_BUDGET_SECONDS
    )


# ---------------------------------------------------------------------------
# Journal seam (mirrors `_dispatcher_reflection.JournalWriter`).
# ---------------------------------------------------------------------------


class JournalWriter(Protocol):
    def append(self, *, record: dict[str, object]) -> None: ...


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


def _record_error(*, journal: JournalWriter, exc: Exception) -> None:
    _AUTO_TRIP.consecutive_errors += 1
    reason = f"{type(exc).__name__}: {exc}"
    journal.append(record={"stage": "reflector-oob-error", "reason": reason})
    _ = write_stderr(text=f"WARN: out-of-band reflector error (fail-open): {reason}\n")
    if _AUTO_TRIP.consecutive_errors >= _AUTO_TRIP_THRESHOLD:
        _AUTO_TRIP.tripped = True
        journal.append(
            record={
                "stage": "reflector-oob-tripped",
                "consecutive_errors": _AUTO_TRIP.consecutive_errors,
                "threshold": _AUTO_TRIP_THRESHOLD,
            }
        )
