"""Resolving ONE admission evaluation's Codex headroom reading.

The Codex clause reuses the Claude clause's two dials and its at-most-once
discipline: "For each distinct projected Codex credential per admission
evaluation, the Dispatcher MUST issue exactly one bounded usage read ... and MUST
reuse that one reading across every node and candidate sharing the credential."

THE MEMO LIVES IN THE RETURNED CALLABLE, built once per admission evaluation, so
"at most once" is a property of the value every node is filtered against and two
concurrent evaluations cannot share one another's reading.

THE CREDENTIAL IS READ AT READ TIME, not at build time: the clause asks for the
snapshot the dispatch would project, and the projection reads the host file, so
taking it when the first covered candidate needs it keeps the two readings of
one file from diverging -- and an evaluation assessing no Codex candidate issues
no request at all.

BASELINES ARE READ PER WINDOW LENGTH from this provider's own journal stage, for
this credential only, so a reading of one window is never a baseline for another.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._acp_codex_headroom import (
    CODEX_HEADROOM_STAGE,
    CodexHeadroomReading,
)
from livespec_orchestrator_beads_fabro.commands._acp_codex_headroom_projection import (
    assessed_codex_reading,
    codex_projection_attempted,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_drain import (
    SessionHeadroomBaseline,
    SessionHeadroomPriorReading,
    baseline_assessment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth import read_host_codex_auth
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_headroom_io import (
    read_projected_codex_headroom,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)

__all__: list[str] = [
    "codex_headroom_source",
    "codex_window_baseline",
]


def codex_headroom_source(
    *,
    now_iso: str,
    journal_path: Path | None,
    floor_percent: int,
    horizon_minutes: int,
    read: Callable[..., CodexHeadroomReading] = read_projected_codex_headroom,
    auth: Callable[[], str | None] = read_host_codex_auth,
) -> Callable[[], CodexHeadroomReading]:
    """A memoized, fully assessed Codex reading for this evaluation."""
    taken: list[CodexHeadroomReading] = []

    def read_once() -> CodexHeadroomReading:
        if not taken:
            reading = read(auth_json=auth(), observed_at=now_iso)
            taken.append(
                _assessed(
                    reading=reading,
                    journal_path=journal_path,
                    floor_percent=floor_percent,
                    horizon_minutes=horizon_minutes,
                    now_iso=now_iso,
                )
            )
        return taken[0]

    return read_once


def codex_window_baseline(
    *, journal_path: Path | None, credential_identity: str, window_seconds: int, now_iso: str
) -> SessionHeadroomBaseline | None:
    """The earliest in-window prior reading of ONE credential's ONE window length."""
    if journal_path is None or not journal_path.is_file():
        return None
    return baseline_assessment(
        priors=_priors(
            records=read_journal_records(journal_path=journal_path),
            credential_identity=credential_identity,
            window_seconds=window_seconds,
        ),
        now_iso=now_iso,
    )


def _assessed(
    *,
    reading: CodexHeadroomReading,
    journal_path: Path | None,
    floor_percent: int,
    horizon_minutes: int,
    now_iso: str,
) -> CodexHeadroomReading:
    """The reading carrying its projection results.

    THE NOT-ATTEMPTED TEST RUNS BEFORE THE JOURNAL READ: a reading the floor or
    the provider already settled spends no file read to establish an absence.
    """
    baselines: dict[int, SessionHeadroomBaseline] = {}
    if codex_projection_attempted(reading=reading, floor_percent=floor_percent):
        for window in reading.windows:
            baseline = codex_window_baseline(
                journal_path=journal_path,
                credential_identity=reading.credential_identity,
                window_seconds=window.limit_window_seconds,
                now_iso=now_iso,
            )
            if baseline is not None:
                baselines[window.limit_window_seconds] = baseline
    return assessed_codex_reading(
        reading=reading,
        baselines=baselines,
        floor_percent=floor_percent,
        horizon_minutes=horizon_minutes,
    )


def _priors(
    *, records: tuple[dict[str, object], ...], credential_identity: str, window_seconds: int
) -> tuple[SessionHeadroomPriorReading, ...]:
    priors: list[SessionHeadroomPriorReading] = []
    for record in records:
        if record.get("stage") != CODEX_HEADROOM_STAGE:
            continue
        for assessment in _entries(value=record.get("assessments")):
            fields = _fields(value=assessment)
            if fields.get("credential_identity") != credential_identity:
                continue
            for window in _entries(value=fields.get("windows")):
                prior = _prior(
                    observed_at=fields.get("observed_at"),
                    window=_fields(value=window),
                    window_seconds=window_seconds,
                )
                if prior is not None:
                    priors.append(prior)
    return tuple(priors)


def _prior(
    *, observed_at: object, window: dict[str, object], window_seconds: int
) -> SessionHeadroomPriorReading | None:
    used = window.get("used_percent")
    if window.get("limit_window_seconds") != window_seconds or not isinstance(observed_at, str):
        return None
    if isinstance(used, bool) or not isinstance(used, int | float):
        return None
    return SessionHeadroomPriorReading(utilization_percent=float(used), observed_at=observed_at)


def _fields(*, value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in cast("dict[object, object]", value).items()}


def _entries(*, value: object) -> list[object]:
    if not isinstance(value, list):
        return []
    return list(cast("list[object]", value))
