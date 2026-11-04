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
    "INPUT_USAGE_PARTIAL",
    "INPUT_USAGE_UNREPORTED",
    "CandidateInputUsage",
    "candidate_input_usage",
    "candidate_reply",
]

HOST_JUDGEMENT_INPUT_LIMIT = 100_000
INPUT_USAGE_COMPLETE = "complete"
# Some request the transcript NAMES never reported its input, so the figure is a
# LOWER BOUND on what the candidate consumed rather than the consumption itself.
# It is a third marking rather than an absence because the two readings a reader
# must not confuse are both a plain integer below the bound: `complete` is the
# candidate's input, `partial` is as much of it as the transcript could account
# for, and recording the second as the first understates the very use the bound
# is measured against.
INPUT_USAGE_PARTIAL = "partial"
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
    """Read JSON-line reports, deduplicating each named request.

    A request the transcript NAMES but never accounts for leaves the total
    `partial`, which is why an unreadable report is noted against its request id
    rather than skipped: the id is the only evidence that a request happened at
    all, so dropping the record loses the one fact that distinguishes a complete
    total from a short one.

    An AGGREGATE is `complete` whatever else the transcript omitted, because such
    a report states the candidate's whole input directly and so answers the
    question the per-request sum is only reconstructing.
    """
    requests: dict[str, int] = {}
    unaccounted: set[str] = set()
    aggregates: list[int] = []
    for line in output.splitlines():
        report = _json_object(line=line)
        if report is None:
            continue
        usage = _usage_in(report=report)
        tokens = None if usage is None else _input_tokens(usage=usage)
        request_id = _request_id(report=report)
        if tokens is None:
            if request_id is not None:
                unaccounted.add(request_id)
            continue
        if request_id is None:
            aggregates.append(tokens)
        else:
            requests[request_id] = tokens
    if aggregates:
        return CandidateInputUsage(total_tokens=max(aggregates), status=INPUT_USAGE_COMPLETE)
    if not requests:
        return CandidateInputUsage(total_tokens=None, status=INPUT_USAGE_UNREPORTED)
    return CandidateInputUsage(
        total_tokens=sum(requests.values()),
        # A request counted on ANY of its records is accounted for: a host judge
        # announces a request before it can know its usage, so the same id
        # arrives first without counts and later with them. Treating any
        # countless record as a gap would mark every ordinary transcript
        # partial, which retires the marking by making it mean nothing.
        status=(INPUT_USAGE_PARTIAL if unaccounted - requests.keys() else INPUT_USAGE_COMPLETE),
    )


def candidate_reply(*, output: str) -> str:
    """The reply a candidate's usage-reporting transcript carries.

    A candidate asked to report usage emits a JSON-line transcript instead of the
    bare reply: Claude's streaming JSON ends in a `result` record holding the
    reply text, and Codex's JSON events carry it in the last completed
    `agent_message`. The LAST such record wins, because a transcript may carry an
    earlier message that a later one supersedes. Output with no such record is
    returned unchanged, which is what keeps a candidate that was not asked to
    stream reading exactly as it did.
    """
    reply: str | None = None
    for line in output.splitlines():
        report = _json_object(line=line)
        text = None if report is None else _reply_in(report=report)
        if text is not None:
            reply = text
    return output if reply is None else reply


def _reply_in(*, report: Mapping[str, object]) -> str | None:
    kind = report.get("type")
    if kind == "result":
        result = report.get("result")
        return result if isinstance(result, str) else None
    item = report.get("item")
    if kind != "item.completed" or not isinstance(item, Mapping):
        return None
    message = cast("Mapping[str, object]", item)
    text = message.get("text")
    return text if message.get("type") == "agent_message" and isinstance(text, str) else None


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
