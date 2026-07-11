"""Mechanical, fail-open loop-exit reflection stage (NO LLM).

Per the loop-reflection-gate epic decisions (loop-reflection-gate/
best-practices-and-design.md §3 option (b), §6;
cc-otel-gap-analysis.md §1.6 + §3.5), this stage
runs AFTER the loop's exit code / verdict has been computed in
`dispatcher._run_loop_command` (and the single-dispatch sibling). It is a
purely DETERMINISTIC scan of the wave's `DispatchOutcome`s plus the
append-only journal — there is NO LLM call anywhere in this stage; the
LLM-driven holistic reviewer is fully out-of-band and is NOT part of
this module.

The load-bearing invariant, copied from the OTel error-handling contract
(best-practices §1.5 / §6): **REFLECTION NEVER CHANGES A DISPATCH
VERDICT.** The exit code is computed by the caller BEFORE `reflect` runs;
nothing here flows back into the outcomes, the ledger close path, or the
returned exit code. Every reflection error is caught, journaled as a
`reflection-error` record, and is otherwise a no-op — it never blocks
loop exit.

Always-wired behavior lever (best-practices §6 "one self-documenting
lever, always wired", per the family carve-out-as-severity-lever
discipline): `LIVESPEC_REFLECTION` with three values —

  * `off`     — the stage does nothing (still WIRED + always called; the
                lever is the ONE knob, never a silent skip).
  * `observe` — DEFAULT: scan the wave, emit a human reflection summary
                on stderr (the loop summary's diagnostic channel, where
                sizing-warn / ledger / janitor notices already go), emit
                OTLP spans to the spans file, and journal a `reflection`
                record.
  * `file`    — additionally journal a `reflection-file-handoff` record
                naming the findings, so the documented out-of-band
                reflector (which owns the dedup-first ledger filing per
                best-practices §5) picks them up. This stage does NOT
                write the ledger itself: ledger filing is the out-of-band
                reflector's responsibility (best-practices §3 option (c),
                §5.1) and the minimal loop-exit context here deliberately
                holds no store handle, so `file` scopes to the documented
                hand-off rather than inventing a new ledger-write path.

The default is `observe` exactly as best-practices §6 pins it
("default `observe` until the mechanical tier proves quiet, then
`file`").

Auto-trip (best-practices §6): after `_AUTO_TRIP_THRESHOLD` (3)
CONSECUTIVE reflection errors within one process, the stage disables
itself for the rest of the process (degrades to `off`) and journals a
`reflection-tripped` record. A purely mechanical consecutive-error
counter — no LLM. A successful pass resets the counter.

Time-box (best-practices §6): the scan is bounded by
`_REFLECTION_BUDGET_SECONDS` (~60s). If the deadline is exceeded
mid-scan the stage bails fail-open (journals `reflection-error` with a
budget-exceeded reason) rather than delaying loop exit further.

Credential hygiene (cc-otel-gap-analysis.md §3.6): the OTLP emission
ships only finding NAMES, counts, ids, and statuses — never an
environment-variable value, never a remote URL (which in this fleet can
embed a PAT). The emitter uses an allowlist of scalar attributes, never
"everything"; a defense-in-depth regex rejects any attribute value that
looks like a credential-bearing URL.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    items_with_retries,
    items_with_sizing_warn,
    items_with_timeout,
    trailing_green_streak,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_runner import (
    RunReflectionConfig,
    run_reflection,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_spans import (
    join_ids,
    stage_summary,
)
from livespec_orchestrator_beads_fabro.io import write_stderr

__all__: list[str] = [
    "ReflectionFinding",
    "ReflectionReport",
    "reflect",
    "reset_auto_trip",
    "resolve_mode",
    "scan_outcomes",
]

# The behavior lever (always wired). The NAME of an env var, not a secret.
_REFLECTION_ENV = "LIVESPEC_REFLECTION"
_MODE_OFF = "off"
_MODE_OBSERVE = "observe"
_MODE_FILE = "file"
_DEFAULT_MODE = _MODE_OBSERVE

# Mechanical auto-trip: N consecutive reflection-errors degrade the stage
# to `off` for the rest of the process (best-practices §6).
_AUTO_TRIP_THRESHOLD = 3

# Hard time-box for the whole mechanical scan (best-practices §6, ~60s).
_REFLECTION_BUDGET_SECONDS = 60.0
_BUDGET_EXCEEDED_MESSAGE = "reflection exceeded its mechanical scan time budget"

# The `file`-mode hand-off note (best-practices §5.1 / §3 option (c)): the
# dedup-first ledger filing belongs to the out-of-band reflector, which
# holds the store handle; this loop-exit stage only names the findings.
_FILE_HANDOFF_NOTE = (
    "out-of-band reflector to file/dedup these per best-practices §5; "
    "this loop-exit stage holds no store handle"
)


@dataclass(kw_only=True)
class _AutoTripState:
    """Process-scoped mechanical auto-trip counter.

    A mutable holder (NOT module globals) so the stage can update it
    without a `global` statement (PLW0603), matching the `_FAKE_HOLDER`
    pattern in `_beads_client`. The dispatcher runs one-shot per loop, so
    this is per-process by construction; `reset_auto_trip` clears it for
    hermetic test isolation.
    """

    consecutive_errors: int = 0
    tripped: bool = False


_AUTO_TRIP = _AutoTripState()


class JournalWriter(Protocol):
    """Append-one-record seam (mirrors `_dispatcher_engine.JournalWriter`)."""

    def append(self, *, record: dict[str, object]) -> None:
        """Persist one journal record."""
        ...


@dataclass(frozen=True, kw_only=True)
class ReflectionFinding:
    """One mechanical finding from the wave scan.

    `category` is a stable, message-free key (so a future dedup
    fingerprint keys off it, never churning message text —
    best-practices §5.2). `count` is the number of contributing items /
    occurrences. `severity` is `critical` / `warn` / `info`
    (best-practices §5.2). `subject` is a one-line human summary.
    """

    category: str
    severity: str
    count: int
    subject: str


@dataclass(frozen=True, kw_only=True)
class ReflectionReport:
    """The mechanical scan result for one wave (no LLM)."""

    mode: str
    item_count: int
    green_count: int
    failed_count: int
    blocked_count: int
    green_streak: int
    findings: tuple[ReflectionFinding, ...]


def reset_auto_trip() -> None:
    """Reset the process-level auto-trip state (test isolation seam)."""
    _AUTO_TRIP.consecutive_errors = 0
    _AUTO_TRIP.tripped = False


def resolve_mode(*, raw: str | None) -> str:
    """Resolve the `LIVESPEC_REFLECTION` lever to a known mode.

    An unset, empty, or unrecognized value resolves to the `observe`
    default (best-practices §6) — the lever is always wired and never
    silently disables the stage; only the explicit `off` value does.
    """
    if raw == _MODE_OFF:
        return _MODE_OFF
    if raw == _MODE_FILE:
        return _MODE_FILE
    return _DEFAULT_MODE


def scan_outcomes(
    *,
    outcomes: tuple[DispatchOutcome, ...],
    records: tuple[dict[str, object], ...],
    mode: str,
) -> ReflectionReport:
    """Mechanically scan the wave's outcomes + journal records (NO LLM).

    Pure function: classifies the verdict mix, derives the trailing
    green streak, and clusters the pass — timeouts (exit 124),
    retries (repeated stages per item), env-degraded janitor outcomes,
    sizing warnings (bn4), and any blocked items — into stable-key
    findings. `mode` is recorded on the report for the summary + spans.
    """
    green = tuple(o for o in outcomes if o.status == "green")
    failed = tuple(o for o in outcomes if o.status == "failed")
    blocked = tuple(o for o in outcomes if o.status == "blocked")
    findings: list[ReflectionFinding] = []

    degraded = tuple(o for o in green if o.stage == "janitor-env-degraded")
    if degraded:
        findings.append(
            ReflectionFinding(
                category="janitor-env-degraded",
                severity="warn",
                count=len(degraded),
                subject="merged green but the post-merge janitor could not run (host env)",
            )
        )
    if failed:
        findings.append(
            ReflectionFinding(
                category="failed-cluster",
                severity="warn",
                count=len(failed),
                subject=f"items failed at: {stage_summary(outcomes=failed)}",
            )
        )
    if blocked:
        findings.append(
            ReflectionFinding(
                category="blocked-at-human-gate",
                severity="warn",
                count=len(blocked),
                subject="items parked at the in-loop human gate (need an operator)",
            )
        )

    timeout_items = items_with_timeout(records=records)
    if timeout_items:
        findings.append(
            ReflectionFinding(
                category="stage-timeout",
                severity="warn",
                count=len(timeout_items),
                subject=f"stage timeouts (exit 124) for: {join_ids(ids=timeout_items)}",
            )
        )
    retry_items = items_with_retries(records=records)
    if retry_items:
        findings.append(
            ReflectionFinding(
                category="stage-retry",
                severity="info",
                count=len(retry_items),
                subject=f"repeated-stage activity (poll/retry) for: {join_ids(ids=retry_items)}",
            )
        )
    sizing_items = items_with_sizing_warn(records=records)
    if sizing_items:
        findings.append(
            ReflectionFinding(
                category="sizing-warn",
                severity="info",
                count=len(sizing_items),
                subject=f"item-sizing warnings (bn4) for: {join_ids(ids=sizing_items)}",
            )
        )

    return ReflectionReport(
        mode=mode,
        item_count=len(outcomes),
        green_count=len(green),
        failed_count=len(failed),
        blocked_count=len(blocked),
        green_streak=trailing_green_streak(outcomes=outcomes),
        findings=tuple(findings),
    )


def reflect(
    *,
    outcomes: list[DispatchOutcome],
    journal: JournalWriter,
    journal_path: Path,
    spans_path: Path,
) -> None:
    """Run the fail-open mechanical reflection stage at loop exit.

    NEVER raises and NEVER returns a verdict-relevant value: the caller
    has already computed the exit code. Honors the `LIVESPEC_REFLECTION`
    lever, the process-level auto-trip, and the ~60s time-box. Any error
    is caught, journaled as `reflection-error`, and counted toward the
    auto-trip — it does not propagate. `journal_path` is the on-disk
    JSONL the loop has already flushed (the scan's read surface);
    `journal` is the append seam for the reflection record(s).
    """
    mode = resolve_mode(raw=os.environ.get(_REFLECTION_ENV))
    if mode == _MODE_OFF or _AUTO_TRIP.tripped:
        return
    deadline = time.monotonic() + _REFLECTION_BUDGET_SECONDS
    try:
        run_reflection(
            outcomes=tuple(outcomes),
            journal=journal,
            scan=scan_outcomes,
            config=RunReflectionConfig(
                journal_path=journal_path,
                mode=mode,
                spans_path=spans_path,
                deadline=deadline,
                file_handoff_note=_FILE_HANDOFF_NOTE,
                budget_exceeded_message=_BUDGET_EXCEEDED_MESSAGE,
            ),
        )
    except Exception as exc:
        # Fail-open supervisor: reflection must never escape and never
        # change the verdict (best-practices §6). A broad catch is the
        # whole point — any error is journaled and counted, not raised.
        _record_reflection_error(journal=journal, exc=exc)
        return
    _AUTO_TRIP.consecutive_errors = 0


def _record_reflection_error(*, journal: JournalWriter, exc: Exception) -> None:
    """Journal a reflection error fail-open and advance the auto-trip counter.

    Increments the consecutive-error counter and, on reaching the
    threshold, flips the process-level trip so the stage degrades to
    `off` for the rest of the process. NEVER re-raises.
    """
    _AUTO_TRIP.consecutive_errors += 1
    reason = f"{type(exc).__name__}: {exc}"
    journal.append(record={"stage": "reflection-error", "reason": reason})
    _ = write_stderr(text=f"WARN: reflection error (fail-open, verdict unchanged): {reason}\n")
    if _AUTO_TRIP.consecutive_errors >= _AUTO_TRIP_THRESHOLD:
        _AUTO_TRIP.tripped = True
        journal.append(
            record={
                "stage": "reflection-tripped",
                "consecutive_errors": _AUTO_TRIP.consecutive_errors,
                "threshold": _AUTO_TRIP_THRESHOLD,
            }
        )
        trip_msg = (
            f"WARN: reflection auto-tripped after {_AUTO_TRIP.consecutive_errors} consecutive "
            "errors; disabled for the rest of this process (cycle LIVESPEC_REFLECTION)\n"
        )
        _ = write_stderr(text=trip_msg)
