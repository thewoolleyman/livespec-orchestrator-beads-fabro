"""Non-secret diagnostics for Fabro `run_turn` export observation."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from livespec_orchestrator_beads_fabro.commands._otel_scrub import scrub
from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    JsonParseFailure,
    attempt,
    parse_json,
)

__all__: list[str] = [
    "RunTurnTraceRequest",
    "read_run_turn_diagnostic",
    "record_run_turn_export_diagnostic",
    "record_run_turn_receiver_diagnostic",
    "record_run_turn_trace_request",
    "run_turn_diagnostic_path",
    "successful_run_turn_export_count",
]

_DIAGNOSTIC_SUFFIX = "-diagnostics.json"
_REASON_ACCEPTED = "accepted"

_LOGGER = logging.getLogger(__name__)


class TraceRequestRecorder(Protocol):
    def record_trace_request(self, *, request: RunTurnTraceRequest) -> None:
        """Persist one `_handle_traces` request diagnostic."""
        ...


@dataclass(frozen=True, kw_only=True)
class RunTurnTraceRequest:
    """The `_handle_traces` counters for one OTLP request."""

    ingested_spans: int
    enriched_spans: int
    dataset_batch_sizes: dict[str, int]
    export_results: dict[str, bool]
    run_turn_sink_missing: bool
    successful_run_turn_exports: int
    at: float


def record_run_turn_receiver_diagnostic(
    *,
    sink: TraceRequestRecorder | None,
    diagnostics_path: Path | None,
    request: RunTurnTraceRequest,
) -> None:
    request = _with_sink_state(request=request, run_turn_sink_missing=sink is None)
    if sink is None:
        if diagnostics_path is not None:
            record_run_turn_trace_request(path=diagnostics_path, request=request)
        return
    sink.record_trace_request(request=request)


def successful_run_turn_export_count(
    *,
    dataset: str,
    records: Iterable[tuple[dict[str, object], dict[str, str]]],
) -> int:
    if dataset != "fabro":
        return 0
    return sum(1 for span, _resource_attrs in records if span.get("name") == "run_turn")


def run_turn_diagnostic_path(*, path: Path) -> Path:
    return path.with_name(f"{path.stem}{_DIAGNOSTIC_SUFFIX}")


def read_run_turn_diagnostic(*, path: Path) -> dict[str, object]:
    diagnostic = _empty_diagnostic()
    if not path.is_file():
        return diagnostic
    stored = attempt(action=lambda: path.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(stored, AttemptFailure):
        return diagnostic
    raw = parse_json(text=stored)
    if isinstance(raw, JsonParseFailure) or not isinstance(raw, dict):
        return diagnostic
    parsed = cast("dict[str, object]", raw)
    diagnostic["accepted"] = _int_value(raw=parsed.get("accepted"))
    diagnostic["rejected"] = _rejected_counts(raw=parsed.get("rejected"))
    diagnostic["write_failures"] = _int_value(raw=parsed.get("write_failures"))
    if isinstance(parsed.get("last"), dict):
        diagnostic["last"] = parsed["last"]
    if isinstance(parsed.get("receiver"), dict):
        diagnostic["receiver"] = _receiver_diagnostic(raw=parsed["receiver"])
    return diagnostic


def record_run_turn_export_diagnostic(
    *,
    path: Path,
    reason: str,
    dataset: str,
    span_name: str,
    at: float,
    write_failed: bool = False,
) -> None:
    diagnostic = read_run_turn_diagnostic(path=path)
    if reason == _REASON_ACCEPTED:
        diagnostic["accepted"] = _int_value(raw=diagnostic.get("accepted")) + 1
    else:
        rejected = _rejected_counts(raw=diagnostic.get("rejected"))
        rejected[reason] = rejected.get(reason, 0) + 1
        diagnostic["rejected"] = rejected
    if write_failed:
        diagnostic["write_failures"] = _int_value(raw=diagnostic.get("write_failures")) + 1
    else:
        _ = diagnostic.setdefault("write_failures", 0)
    diagnostic["last"] = {
        "at": at,
        "dataset": scrub(value=dataset),
        "reason": reason,
        "span_name": scrub(value=span_name),
    }
    _write_run_turn_diagnostic(path=path, diagnostic=diagnostic)


def record_run_turn_trace_request(*, path: Path, request: RunTurnTraceRequest) -> None:
    diagnostic = read_run_turn_diagnostic(path=path)
    receiver = _receiver_diagnostic(raw=diagnostic.get("receiver"))
    receiver["requests"] = _int_value(raw=receiver.get("requests")) + 1
    receiver["ingested_spans"] = (
        _int_value(raw=receiver.get("ingested_spans")) + request.ingested_spans
    )
    receiver["enriched_spans"] = (
        _int_value(raw=receiver.get("enriched_spans")) + request.enriched_spans
    )
    receiver["successful_run_turn_exports"] = (
        _int_value(raw=receiver.get("successful_run_turn_exports"))
        + request.successful_run_turn_exports
    )
    if request.run_turn_sink_missing:
        receiver["run_turn_sink_missing"] = (
            _int_value(raw=receiver.get("run_turn_sink_missing")) + 1
        )
    else:
        _ = receiver.setdefault("run_turn_sink_missing", 0)
    for exported in request.export_results.values():
        key = "export_successes" if exported else "export_failures"
        receiver[key] = _int_value(raw=receiver.get(key)) + 1
    receiver["last"] = {
        "dataset_batch_sizes": _scrub_int_map(values=request.dataset_batch_sizes),
        "enriched_spans": request.enriched_spans,
        "export_results": _scrub_bool_map(values=request.export_results),
        "ingested_spans": request.ingested_spans,
        "run_turn_sink_missing": request.run_turn_sink_missing,
        "successful_run_turn_exports": request.successful_run_turn_exports,
    }
    if request.successful_run_turn_exports > 0:
        receiver["last_successful_run_turn_export_at"] = request.at
    diagnostic["receiver"] = receiver
    _write_run_turn_diagnostic(path=path, diagnostic=diagnostic)


def _empty_diagnostic() -> dict[str, object]:
    return {
        "accepted": 0,
        "rejected": {},
        "write_failures": 0,
    }


def _with_sink_state(
    *, request: RunTurnTraceRequest, run_turn_sink_missing: bool
) -> RunTurnTraceRequest:
    return RunTurnTraceRequest(
        ingested_spans=request.ingested_spans,
        enriched_spans=request.enriched_spans,
        dataset_batch_sizes=request.dataset_batch_sizes,
        export_results=request.export_results,
        run_turn_sink_missing=run_turn_sink_missing,
        successful_run_turn_exports=request.successful_run_turn_exports,
        at=request.at,
    )


def _receiver_diagnostic(*, raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        return {}
    return dict(cast("dict[str, object]", raw))


def _write_run_turn_diagnostic(*, path: Path, diagnostic: dict[str, object]) -> None:
    text = json.dumps(diagnostic, separators=(",", ":"), sort_keys=True)
    tmp = path.with_name(f"{path.name}.tmp")
    written = attempt(
        action=lambda: _write_atomic(path=path, tmp=tmp, text=text),
        exceptions=(OSError,),
    )
    if isinstance(written, AttemptFailure):
        _LOGGER.warning("run_turn export diagnostic write failed: path=%s", path)


def _int_value(*, raw: object) -> int:
    if isinstance(raw, bool):
        return 0
    if isinstance(raw, int):
        return raw
    return 0


def _rejected_counts(*, raw: object) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    counts: dict[str, int] = {}
    for key, value in cast("dict[str, object]", raw).items():
        counts[key] = _int_value(raw=value)
    return counts


def _scrub_int_map(*, values: dict[str, int]) -> dict[str, int]:
    return {scrub(value=key): value for key, value in values.items()}


def _scrub_bool_map(*, values: dict[str, bool]) -> dict[str, bool]:
    return {scrub(value=key): value for key, value in values.items()}


def _write_atomic(*, path: Path, tmp: Path, text: str) -> None:
    _ = path.parent.mkdir(parents=True, exist_ok=True)
    _ = tmp.write_text(text, encoding="utf-8")
    _ = tmp.replace(path)
