"""Conservative evidence classification for a failed workflow job.

This leaf owns the committed pattern set which distinguishes runner failures
from product failures.  The rerun module owns forge reads and side effects.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

__all__: list[str] = ["FailedJobClassification", "classify_failed_job"]

_TEARDOWN_STEP_MARKERS: tuple[str, ...] = ("post ", "cleanup", "stop container")
_TEARDOWN_LOG_MARKERS: tuple[str, ...] = (
    "custom container implementation failed",
    "container implementation failed",
    "runner failed to start",
)
_OOM_MARKERS: tuple[str, ...] = (
    "out of memory",
    "oom-kill",
    "oom killed",
    "exceeded its memory limit",
    "exceeded memory limit",
)
_TIMEOUT_MARKERS: tuple[str, ...] = (
    "exceeded the maximum execution time",
    "maximum execution time",
    "job exceeded the maximum execution time",
)


@dataclass(frozen=True, kw_only=True)
class FailedJobClassification:
    """One conservative attribution and the evidence that established it."""

    kind: str
    evidence: tuple[str, ...]


def classify_failed_job(*, job: Mapping[str, object], log: str) -> FailedJobClassification:
    """Classify one failed job, preferring explicit kill/timeout evidence.

    A pytest assertion does not override an OOM kill or a job timeout: those
    are infrastructure observations even when they interrupt the test runner.
    With no matching infrastructure evidence the answer remains unattributed.
    """
    combined = "\n".join((_string(value=job.get("conclusion")), log))
    if evidence := _matched_log_evidence(text=combined, markers=_OOM_MARKERS, label="oom-kill"):
        return FailedJobClassification(kind="oom-kill", evidence=evidence)
    if evidence := _matched_log_evidence(
        text=combined,
        markers=_TIMEOUT_MARKERS,
        label="job-timeout",
    ):
        return FailedJobClassification(kind="job-timeout", evidence=evidence)
    failed_steps = _failed_teardown_steps(job=job)
    teardown_log = _matched_log_evidence(
        text=log,
        markers=_TEARDOWN_LOG_MARKERS,
        label="log",
    )
    if failed_steps and _all_non_teardown_steps_succeeded(job=job):
        evidence = (f"failed teardown steps: {', '.join(failed_steps)}", *teardown_log)
        return FailedJobClassification(kind="runner-teardown", evidence=evidence)
    if teardown_log and _all_non_teardown_steps_succeeded(job=job):
        return FailedJobClassification(kind="runner-teardown", evidence=teardown_log)
    return FailedJobClassification(kind="unattributed", evidence=())


def _matched_log_evidence(*, text: str, markers: tuple[str, ...], label: str) -> tuple[str, ...]:
    matched = tuple(marker for marker in markers if marker in text.lower())
    if not matched:
        return ()
    if label == "log":
        return (f"log: {text.strip()}",)
    return tuple(f"{label}: {marker}" for marker in matched)


def _failed_teardown_steps(*, job: Mapping[str, object]) -> tuple[str, ...]:
    return tuple(
        name
        for step in _steps(job=job)
        for name in [_string(value=step.get("name"))]
        if _is_failed(step=step) and _is_teardown_step(name=name)
    )


def _all_non_teardown_steps_succeeded(*, job: Mapping[str, object]) -> bool:
    return all(
        _is_teardown_step(name=_string(value=step.get("name"))) or _is_succeeded(step=step)
        for step in _steps(job=job)
    )


def _steps(*, job: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    raw = job.get("steps")
    if not isinstance(raw, list):
        return ()
    values = cast("list[object]", raw)
    return tuple(
        cast("Mapping[str, object]", value) for value in values if isinstance(value, Mapping)
    )


def _is_teardown_step(*, name: str) -> bool:
    return any(marker in name.lower() for marker in _TEARDOWN_STEP_MARKERS)


def _is_failed(*, step: Mapping[str, object]) -> bool:
    return _string(value=step.get("conclusion")).lower() in {"failure", "cancelled", "timed_out"}


def _is_succeeded(*, step: Mapping[str, object]) -> bool:
    return _string(value=step.get("conclusion")).lower() in {"success", "skipped"}


def _string(*, value: object) -> str:
    return value if isinstance(value, str) else ""
