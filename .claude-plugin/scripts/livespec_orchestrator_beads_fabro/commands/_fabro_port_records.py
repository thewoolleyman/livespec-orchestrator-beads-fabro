"""Fabro response records owned by the dispatcher Fabro port."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._fabro_port_permanent_failure import (
    fabro_permanent_cause,
    fabro_provider_message,
    fabro_usage_limit_provider,
)
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "FabroFailureDetail",
    "FabroRunSummary",
    "fabro_failure_detail_from_payload",
    "fabro_inspect_record",
    "fabro_run_id_from_output",
    "fabro_run_summaries_from_payload",
    "fabro_run_summaries_from_stdout",
    "fabro_status_kind_from_payload",
]

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
_RUN_ID_RE = re.compile(r"Run:\s*([0-9A-Za-z-]+)")
_WORK_ITEM_RE = re.compile(r"^Work-item:\s*(\S+)", re.MULTILINE)
# The category a PERMANENT failure is rewritten to. Fabro's own classifier
# labels these `transient_infra`, which is what makes them retryable; a failure
# that cannot succeed on retry is deterministic by definition.
_PERMANENT_CATEGORY = "deterministic"
_TRANSIENT_SIGNATURE_SEGMENT = "|transient_infra|"


@dataclass(frozen=True, kw_only=True)
class FabroFailureDetail:
    """Structured failure block surfaced by `fabro inspect --json`.

    `provider_usage_limit` is the typed consumer seam for the dispatch-admission
    gate: it says this run died because the model provider's usage or spend
    ceiling was reached, so launching another sandbox against the same
    credential cannot produce a line of work. It is carried as a flag rather
    than left for each consumer to re-match against `cause` text.

    `provider_usage_limit_provider` names WHICH vendor refused, and is the value
    an exhaustion record is labelled with. It is set from the same single
    classification that sets the flag, so the two cannot disagree: it is
    non-None exactly when the flag is True.
    """

    cause: str | None
    category: str | None
    signature: str | None
    provider_usage_limit: bool = False
    provider_usage_limit_provider: str | None = None


@dataclass(frozen=True, kw_only=True)
class FabroRunSummary:
    """Run row from `fabro ps -a --json` that livespec code reads."""

    run_id: str
    status_kind: str | None
    goal: str | None
    total_usd_micros: int | None
    work_item_id: str | None = field(default=None, compare=False)


def fabro_run_id_from_output(*, output: str) -> str | None:
    plain = _ANSI_ESCAPE_RE.sub("", output)
    match = _RUN_ID_RE.search(plain)
    if match is None:
        return None
    return match.group(1)


def fabro_run_summaries_from_stdout(*, stdout: str) -> tuple[FabroRunSummary, ...]:
    parsed = parse_json(text=stdout)
    if isinstance(parsed, JsonParseFailure):
        return ()
    return fabro_run_summaries_from_payload(payload=parsed)


def fabro_run_summaries_from_payload(*, payload: object | None) -> tuple[FabroRunSummary, ...]:
    summaries: list[FabroRunSummary] = []
    for run in _runs(payload=payload):
        summary = _run_summary(run=run)
        if summary is not None:
            summaries.append(summary)
    return tuple(summaries)


def fabro_inspect_record(*, payload: object | None) -> dict[str, Any] | None:
    """Normalize an `inspect` payload to the single run record it describes.

    `fabro inspect <run> --json` returns a single-element LIST on the pinned
    build (0.254.0), not a bare mapping. Measured against six real payloads on
    2026-08-20. Mapping payloads are still accepted so a future shape change
    back to a bare object does not regress.
    """
    if isinstance(payload, dict):
        return cast("dict[str, Any]", payload)
    if isinstance(payload, list):
        for entry in cast("list[object]", payload):
            if isinstance(entry, dict):
                return cast("dict[str, Any]", entry)
    return None


def fabro_status_kind_from_payload(*, payload: object | None) -> str | None:
    record = fabro_inspect_record(payload=payload)
    if record is None:
        return None
    status_raw: object = record.get("status")
    if isinstance(status_raw, str):
        return status_raw
    if isinstance(status_raw, dict):
        kind_raw: object = cast("dict[str, Any]", status_raw).get("kind")
        if isinstance(kind_raw, str):
            return kind_raw
    return None


def fabro_failure_detail_from_payload(*, payload: object | None) -> FabroFailureDetail | None:
    record = fabro_inspect_record(payload=payload)
    if record is None:
        return None
    typed_payload = cast("dict[object, object]", record)
    blocks = _failure_blocks(value=typed_payload)
    # A block CARRYING CAUSES wins over an earlier one that only carries a
    # category, because the cause chain is where the provider payload lives.
    # Traversal order alone put a bare `{"category": ...}` block first on 2 of
    # the 10 measured usage-limit runs (2026-08-22), which hid the very cause
    # this parser exists to surface.
    for block in blocks:
        if block.get("causes"):
            detail = _failure_detail(block=block)
            if detail is not None:
                return detail
    for block in blocks:
        detail = _failure_detail(block=block)
        if detail is not None:
            return detail
    return None


def _runs(*, payload: object | None) -> list[object]:
    if isinstance(payload, list):
        return cast("list[object]", payload)
    if isinstance(payload, dict):
        runs_raw: object = cast("dict[str, Any]", payload).get("runs")
        if isinstance(runs_raw, list):
            return cast("list[object]", runs_raw)
    return []


def _run_summary(*, run: object) -> FabroRunSummary | None:
    if not isinstance(run, dict):
        return None
    record = cast("dict[str, Any]", run)
    run_id_raw: object = record.get("run_id")
    if not isinstance(run_id_raw, str) or run_id_raw == "":
        return None
    goal = _optional_str(value=record.get("goal"))
    return FabroRunSummary(
        run_id=run_id_raw,
        status_kind=fabro_status_kind_from_payload(payload=record),
        goal=goal,
        work_item_id=_work_item_id(goal=goal),
        total_usd_micros=_optional_int(value=record.get("total_usd_micros")),
    )


def _optional_str(*, value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(*, value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _work_item_id(*, goal: str | None) -> str | None:
    if goal is None:
        return None
    match = _WORK_ITEM_RE.search(goal)
    return None if match is None else match.group(1)


def _failure_blocks(*, value: object) -> tuple[dict[object, object], ...]:
    blocks: list[dict[object, object]] = []
    if isinstance(value, dict):
        mapping = cast("dict[object, object]", value)
        raw_failure = mapping.get("failure")
        if isinstance(raw_failure, dict):
            blocks.append(cast("dict[object, object]", raw_failure))
        for nested in mapping.values():
            blocks.extend(_failure_blocks(value=nested))
    elif isinstance(value, list):
        values = cast("list[object]", value)
        for nested in values:
            blocks.extend(_failure_blocks(value=nested))
    return tuple(blocks)


def _failure_detail(*, block: dict[object, object]) -> FabroFailureDetail | None:
    causes = _block_cause_texts(block=block)
    permanent_cause = fabro_permanent_cause(causes=causes)
    selected = permanent_cause or _root_cause(causes=causes)
    cause = selected if selected is None else (fabro_provider_message(text=selected) or selected)
    reclassified = permanent_cause is not None
    usage_limit_provider = fabro_usage_limit_provider(causes=causes)
    category = _failure_category(
        category=_str_value(value=block.get("category"))
        or _detail_text(block=block, key="category"),
        reclassified=reclassified,
    )
    signature = _failure_signature(
        signature=_str_value(value=block.get("signature")),
        reclassified=reclassified,
    )
    if cause is None and category is None and signature is None:
        return None
    return FabroFailureDetail(
        cause=cause,
        category=category,
        signature=signature,
        provider_usage_limit=usage_limit_provider is not None,
        provider_usage_limit_provider=usage_limit_provider,
    )


def _block_cause_texts(*, block: dict[object, object]) -> tuple[str, ...]:
    """Every cause text this block carries, as ONE chain for both engines.

    The classifiers that decide whether a failure is permanent and which vendor
    refused grade a CHAIN, and on the Petri-era engine there is no chain: the
    block carries one `detail.message`. Handing that message back as a
    one-element chain is what makes a provider ceiling reported by the candidate
    reach the same single classification pass the pinned engine's chain reaches
    — a second, parallel pass over the message would be a second place for the
    `transient_infra` rewrite and the vendor attribution to disagree, and both
    would produce a well-formed verdict while they did.

    The real chain WINS wherever it exists, for the reason `_detail_text`
    records: a 0.254 payload carries both, and its chain holds the provider
    payload the engine's own one-line summary does not.
    """
    causes = _cause_values(value=block.get("causes"))
    if causes:
        return causes
    message = _detail_text(block=block, key="message")
    return () if message is None else (message,)


def _detail_text(*, block: dict[object, object], key: str) -> str | None:
    """One text field of the block's nested `detail` object, or None.

    The pinned 0.254 engine carries its fault as a `causes` CHAIN. The Petri-era
    engine (v0.378.0-nightly.0, measured 2026-10-08) carries no chain at all:
    its block is `{reason, detail: {message, category}}`, and that one message
    is where a node's own stderr arrives — the ONLY channel the needs-human
    sentinel travels on that engine (research note 007, probes p2 and p6). The
    `detail` object is read as a UNIT, message and category together, because
    the engine writes it as one and reading half of it attributes a cause to a
    run while reporting no category for it.

    The chain still WINS wherever it exists, so nothing about the legacy
    reading changes: a 0.254 payload carries BOTH, and preferring the nested
    message would replace a two-element provider chain with the engine's own
    one-line summary.

    A `detail` that is not a mapping, or a field that is not text, yields None
    rather than a rendering of it: an unmeasured shape is an UNKNOWN variant,
    and the fail-closed answer is to read nothing from it. Stringifying it would
    put this parser's own rendering of a foreign payload where the engine's
    message belongs, and no consumer could tell the difference.
    """
    detail = block.get("detail")
    if not isinstance(detail, dict):
        return None
    return _str_value(value=cast("dict[object, object]", detail).get(key))


def _cause_values(*, value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    values = cast("list[object]", value)
    return tuple(text for item in values if (text := _str_value(value=item)) is not None)


def _root_cause(*, causes: tuple[str, ...]) -> str | None:
    """The INNERMOST cause — the root of the chain, not its outer wrapper.

    A fabro cause chain is ordered outermost-first, so the last element is the
    one carrying the provider payload. Taking `causes[0]` instead is what made
    every provider failure read as a bare "ACP protocol error".

    MEASURED 2026-08-22 over every failure block in the 53 failed runs on the hp
    factory: all 17 blocks carry EXACTLY two causes, `causes[0]` is the literal
    constant "ACP protocol error" in 17 of 17, and `causes[-1]` holds the real
    message every time. The outer element is a fixed wrapper that identifies the
    transport, not the fault.
    """
    return causes[-1] if causes else None


def _failure_category(*, category: str | None, reclassified: bool) -> str | None:
    if reclassified:
        return _PERMANENT_CATEGORY
    return category


def _failure_signature(*, signature: str | None, reclassified: bool) -> str | None:
    if not reclassified or signature is None:
        return signature
    return signature.replace(_TRANSIENT_SIGNATURE_SEGMENT, f"|{_PERMANENT_CATEGORY}|")


def _str_value(*, value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
