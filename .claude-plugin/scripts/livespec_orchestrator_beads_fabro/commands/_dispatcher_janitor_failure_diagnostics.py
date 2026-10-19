"""Failure attribution from a post-merge janitor aggregate's complete output."""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__: list[str] = [
    "JanitorFailureDiagnosis",
    "janitor_failure_diagnosis",
]

_SUMMARY = re.compile(
    "".join(
        (
            r"^Failed targets \((?P<count>[1-9][0-9]*)\):[^\S\r\n]*\r?\n",
            r"(?P<rows>(?:[ \t]+-[ \t]+[^\r\n]+(?:\r?\n|$))+)",
        )
    ),
    re.MULTILINE,
)
_TARGET = re.compile(r"^[ \t]+-[ \t]+(?P<target>\S(?:.*\S)?)\s*$")
_OBSERVATION_LIMIT = 2000


@dataclass(frozen=True, kw_only=True)
class JanitorFailureDiagnosis:
    """The reportable diagnosis derived from both complete captured streams."""

    detail: str
    failed_targets: tuple[str, ...]


def janitor_failure_diagnosis(*, stdout: str, stderr: str) -> JanitorFailureDiagnosis:
    """Prefer the aggregate's structured target list to an unrelated stream tail."""
    targets = _failed_targets(text=stdout) or _failed_targets(text=stderr)
    if targets:
        rendered = "\n".join(
            [f"Failed targets ({len(targets)}):", *(f"  - {target}" for target in targets)]
        )
        return JanitorFailureDiagnosis(
            detail=rendered,
            failed_targets=targets,
        )
    return JanitorFailureDiagnosis(
        detail=(
            "No structured Failed targets summary was emitted.\n"
            f"stdout observation (bounded): {_tail(text=stdout) or '<empty>'}\n"
            f"stderr observation (bounded): {_tail(text=stderr) or '<empty>'}"
        ),
        failed_targets=(),
    )


def _failed_targets(*, text: str) -> tuple[str, ...]:
    summaries = tuple(_SUMMARY.finditer(text))
    if not summaries:
        return ()
    summary = summaries[-1]
    return tuple(
        match.group("target")
        for row in summary.group("rows").splitlines()
        if (match := _TARGET.fullmatch(row)) is not None
    )


def _tail(*, text: str) -> str:
    stripped = text.strip()
    if len(stripped) <= _OBSERVATION_LIMIT:
        return stripped
    return stripped[-_OBSERVATION_LIMIT:]
