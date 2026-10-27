"""Input-token accounting for one host Definition-of-Done candidate.

Host judge CLIs may repeat a request's usage in several transcript records and
may emit an aggregate total too.  The budget is over requests, so a request id
is counted once and an aggregate replaces rather than supplements request
reports.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

__all__: list[str] = [
    "HOST_JUDGEMENT_INPUT_LIMIT",
    "INPUT_USAGE_COMPLETE",
    "INPUT_USAGE_UNREPORTED",
    "CandidateInputUsage",
    "candidate_input_usage",
]

HOST_JUDGEMENT_INPUT_LIMIT = 100_000
INPUT_USAGE_COMPLETE = "complete"
INPUT_USAGE_UNREPORTED = "unreported"
_INPUT_KEYS = (
    "input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "cache_write_input_tokens",
    "cached_input_tokens",
)


@dataclass(frozen=True, kw_only=True)
class CandidateInputUsage:
    """The candidate-reported total and whether it is available."""

    total_tokens: int | None
    status: str

    @property
    def reached_limit(self) -> bool:
        """Whether accepting this candidate's verdict is forbidden."""
        return self.total_tokens is not None and self.total_tokens >= HOST_JUDGEMENT_INPUT_LIMIT


def candidate_input_usage(*, output: str) -> CandidateInputUsage:
    """Read JSON-line reports, deduplicating each named request."""
    requests: dict[str, int] = {}
    aggregates: list[int] = []
    for line in output.splitlines():
        report = _json_object(line=line)
        if report is None:
            continue
        usage = _usage_in(report=report)
        tokens = None if usage is None else _input_tokens(usage=usage)
        if tokens is None:
            continue
        request_id = _request_id(report=report)
        if request_id is None:
            aggregates.append(tokens)
        else:
            requests[request_id] = tokens
    if aggregates:
        return CandidateInputUsage(total_tokens=max(aggregates), status=INPUT_USAGE_COMPLETE)
    if requests:
        return CandidateInputUsage(total_tokens=sum(requests.values()), status=INPUT_USAGE_COMPLETE)
    return CandidateInputUsage(total_tokens=None, status=INPUT_USAGE_UNREPORTED)


def _json_object(*, line: str) -> Mapping[str, object] | None:
    try:
        decoded: object = json.loads(line)
    except ValueError:
        return None
    return cast("Mapping[str, object]", decoded) if isinstance(decoded, dict) else None


def _usage_in(*, report: Mapping[str, object]) -> Mapping[str, object] | None:
    direct = report.get("usage")
    if isinstance(direct, dict):
        return cast("Mapping[str, object]", direct)
    raw_message = report.get("message")
    if not isinstance(raw_message, Mapping):
        return None
    message = cast("Mapping[str, object]", raw_message)
    nested = message.get("usage")
    return cast("Mapping[str, object]", nested) if isinstance(nested, dict) else None


def _request_id(*, report: Mapping[str, object]) -> str | None:
    direct = report.get("request_id")
    if isinstance(direct, str) and direct:
        return direct
    raw_message = report.get("message")
    if not isinstance(raw_message, Mapping):
        return None
    message = cast("Mapping[str, object]", raw_message)
    nested = message.get("id")
    return nested if isinstance(nested, str) and nested else None


def _input_tokens(*, usage: Mapping[str, object]) -> int | None:
    values = [usage[key] for key in _INPUT_KEYS if key in usage]
    if not values or not all(_is_token_count(value=value) for value in values):
        return None
    return sum(cast("int", value) for value in values)


def _is_token_count(*, value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
