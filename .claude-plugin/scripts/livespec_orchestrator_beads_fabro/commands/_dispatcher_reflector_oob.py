from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._reflector_acp_chain import (
    resolve_dod_gate_candidates,
)
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
from livespec_orchestrator_beads_fabro.commands._reflector_runtime import resolve_mode
from livespec_orchestrator_beads_fabro.commands._reflector_runtime import (
    run_pass as _run_pass,
)
from livespec_orchestrator_beads_fabro.commands._reflector_spans import (
    emit_summary as _emit_summary,
)
from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    FloatParseFailure,
    attempt,
    parse_float,
)
from livespec_orchestrator_beads_fabro.io import write_stderr

__all__: list[str] = [
    "GitPrLessonsProposer",
    "LessonProposal",
    "LessonsProposer",
    "RecordingLessonsProposer",
    "ReflectorFinding",
    "ReflectorReport",
    "fingerprint",
    "parse_findings",
    "reset_auto_trip",
    "resolve_mode",
    "resolve_reflector_budget_seconds",
    "run_reflector_oob",
    "severity_priority",
]

# ---------------------------------------------------------------------------
# Levers + constants (NAMES of env vars, never secrets).
# ---------------------------------------------------------------------------

# The trigger lever (always wired). Default OFF so a real ACP judgement never
# fires on a plain dispatch; opt-in to `observe` (run + summary + spans, no
# ledger writes) or `file` (additionally dedup-file items + propose lessons).
_REFLECTOR_ENV = "LIVESPEC_REFLECTOR_OOB"
_MODE_OFF = "off"

# Mechanical auto-trip + time-box (best-practices §6), mirroring the
# mechanical stage so a flapping reflector self-disables for the process.
_AUTO_TRIP_THRESHOLD = 3

# Time-box defaults (29f.8 gap 1). The stage budget bounds an entire candidate
# chain, while each candidate invocation carries its own timeout.
_DEFAULT_REFLECTOR_BUDGET_SECONDS = 660.0
_BUDGET_EXCEEDED_MESSAGE = "out-of-band reflector exceeded its scan time budget"

# Env levers (always wired; NAMES only, never secrets) tuning the time-box.
# An unset / unparseable value falls back to the committed default rather than
# crashing the fail-open stage (mirrors `_dispatcher_cost._resolve_cap`).
_REFLECTOR_BUDGET_ENV = "LIVESPEC_REFLECTOR_BUDGET_SECONDS"

# Module-level back-compat aliases (the committed defaults). Kept so existing
# call sites / tests that read the constant still resolve, but the live values
# now flow through the env resolvers below.
_REFLECTOR_BUDGET_SECONDS = _DEFAULT_REFLECTOR_BUDGET_SECONDS

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
    parsed = parse_float(text=raw)
    if isinstance(parsed, FloatParseFailure):
        return default
    return parsed if parsed > 0 else default


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
    candidates = resolve_dod_gate_candidates(repo=repo)
    deadline = time.monotonic() + resolve_reflector_budget_seconds(environ=dict(os.environ))
    reflected = attempt(
        action=lambda: _run_pass(
            repo=repo,
            journal=journal,
            spans_path=spans_path,
            runner=runner,
            lessons_proposer=lessons_proposer,
            mode=mode,
            candidates=candidates,
            deadline=deadline,
        ),
        exceptions=(OSError, RuntimeError, TimeoutError),
    )
    if isinstance(reflected, AttemptFailure):
        _record_error(journal=journal, exc=reflected.error)
        return
    report = reflected
    if report is not None:
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
