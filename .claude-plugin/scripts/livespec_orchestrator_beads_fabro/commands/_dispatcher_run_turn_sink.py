"""Persisted guard signal for Fabro `run_turn` Honeycomb egress.

The live OTLP receiver exports sandbox spans synchronously through the
Honeycomb exporter seam. This sink records only the cheap, non-secret fact
that a span named `run_turn` from the `fabro` dataset was accepted by that
exporter, indexed by the CORRELATION IDS that span carries.

THE INDEX IS PER-DISPATCH AND NOTHING ELSE. The sink used to also record a
global `fabro.run_turn` last-export key, because the 0.254 engine's
`run_turn` spans carried no correlation id at all and that key was the only
signal available. But the sink file is HOST-GLOBAL (one path per host, not
per repository), so that key is the last-export timestamp of whichever
dispatch exported most recently — and counting it as a hit satisfied the
check of every concurrent dispatch from one unrelated export, across
repositories. A Petri-era `run_turn` span carries the correlation pair, so
the attributable signal now exists and the unattributable one is gone: an
export reaching the sink with no correlation id is still ACCEPTED and still
recorded in the diagnostics, but it leaves no key any dispatch can match.
A factory whose engine emits nothing attributable is handled where it
belongs — by its `exports_run_turn_telemetry` declaration, which marks its
dispatches UNOBSERVABLE rather than letting a global key stand in for
evidence.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_run_turn_diagnostics import (
    RunTurnTraceRequest,
    record_run_turn_export_diagnostic,
    record_run_turn_trace_request,
    run_turn_diagnostic_has_export,
    run_turn_diagnostic_path,
)
from livespec_orchestrator_beads_fabro.commands._otel_scrub import scrub
from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    JsonParseFailure,
    attempt,
    parse_json,
)

__all__: list[str] = [
    "RunTurnSink",
    "run_turn_check_record",
]

_FABRO_DATASET = "fabro"
_RUN_TURN_SPAN = "run_turn"
_CORRELATION_KEYS = ("work.item.id", "livespec.dispatch.id")
_REASON_ACCEPTED = "accepted"
_REASON_DATASET = "dataset"
_REASON_SPAN_NAME = "span-name"


@dataclass(kw_only=True)
class RunTurnSink:
    """Persisted `{work-item/dispatch id -> last-export timestamp}` map."""

    path: Path
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def record_export(
        self,
        *,
        span: dict[str, object],
        resource_attrs: dict[str, str],
        dataset: str,
        at: float,
    ) -> bool:
        """Record one successful Honeycomb export of a Fabro `run_turn` span."""
        span_name = _span_name(span=span)
        if dataset != _FABRO_DATASET:
            self._record_diagnostic(
                reason=_REASON_DATASET,
                dataset=dataset,
                span_name=span_name,
                at=at,
            )
            return False
        if span_name != _RUN_TURN_SPAN:
            self._record_diagnostic(
                reason=_REASON_SPAN_NAME,
                dataset=dataset,
                span_name=span_name,
                at=at,
            )
            return False
        ids = _correlation_ids(span=span, resource_attrs=resource_attrs)
        with self._lock:
            exported = self._read()
            for key in ids:
                exported[key] = at
            written = self._write(exported=exported)
        self._record_diagnostic(
            reason=_REASON_ACCEPTED,
            dataset=dataset,
            span_name=span_name,
            at=at,
            write_failed=not written,
        )
        return True

    def has_export(
        self, *, keys: tuple[str, ...], exported_at_or_after: float | None = None
    ) -> bool:
        """True when one of THIS dispatch's correlation ids recorded an export.

        An empty candidate is skipped rather than looked up: a dispatch whose
        id could not be read from the journal carries `""`, and a lookup of it
        would match whatever an empty-string key happened to hold.
        """
        with self._lock:
            exported = self._read()
        return any(
            _is_fresh_export(at=exported.get(key), exported_at_or_after=exported_at_or_after)
            for key in keys
            if key != ""
        )

    def has_receiver_export(self, *, exported_at_or_after: float | None = None) -> bool:
        """True when `_handle_traces` observed a successful Fabro `run_turn` export."""
        with self._lock:
            return run_turn_diagnostic_has_export(
                path=run_turn_diagnostic_path(path=self.path),
                exported_at_or_after=exported_at_or_after,
            )

    def record_trace_request(self, *, request: RunTurnTraceRequest) -> None:
        """Persist one `_handle_traces` request diagnostic."""
        with self._lock:
            record_run_turn_trace_request(
                path=run_turn_diagnostic_path(path=self.path), request=request
            )

    def _read(self) -> dict[str, float]:
        if not self.path.is_file():
            return {}
        stored = attempt(
            action=lambda: self.path.read_text(encoding="utf-8"), exceptions=(OSError,)
        )
        if isinstance(stored, AttemptFailure):
            return {}
        raw = parse_json(text=stored)
        if isinstance(raw, JsonParseFailure) or not isinstance(raw, dict):
            return {}
        exported: dict[str, float] = {}
        for key, value in cast("dict[str, object]", raw).items():
            if isinstance(value, bool):
                continue
            if isinstance(value, int | float):
                exported[scrub(value=key)] = float(value)
        return exported

    def _write(self, *, exported: dict[str, float]) -> bool:
        text = json.dumps(exported, separators=(",", ":"), sort_keys=True)
        tmp = self.path.with_name(f"{self.path.name}.tmp")
        written = attempt(
            action=lambda: _write_atomic(path=self.path, tmp=tmp, text=text),
            exceptions=(OSError,),
        )
        return not isinstance(written, AttemptFailure)

    def _record_diagnostic(
        self,
        *,
        reason: str,
        dataset: str,
        span_name: str,
        at: float,
        write_failed: bool = False,
    ) -> None:
        with self._lock:
            record_run_turn_export_diagnostic(
                path=run_turn_diagnostic_path(path=self.path),
                reason=reason,
                dataset=dataset,
                span_name=span_name,
                at=at,
                write_failed=write_failed,
            )


def run_turn_check_record(
    *,
    sink: RunTurnSink,
    work_item_id: str,
    dispatch_id: str,
    started_at_epoch: float | None = None,
    observable: bool = True,
) -> dict[str, object]:
    """Build the post-dispatch telemetry assertion journal record.

    `run_turn_exported` is THIS dispatch's verdict and is earned on this
    dispatch's own correlation ids alone. `run_turn_receiver_observed` is the
    receiver's separate, unattributed fact — "some `run_turn` export
    succeeded since you started" — and the two are kept apart because that
    fact is true for every concurrent dispatch at once. It used to be OR-ed
    into the verdict, which discharged a second dispatch's check from the
    first dispatch's export; it rides beside the verdict now so an operator
    reading an absence can still tell "the receiver saw nothing at all"
    apart from "the receiver saw someone else's".
    """
    if not observable:
        return {
            "stage": "run-turn-telemetry-check",
            "work_item_id": work_item_id,
            "dispatch_id": dispatch_id,
            "run_turn_exported": False,
            "run_turn_observable": False,
            "run_turn_observation": "unobservable-remote-factory",
        }
    keys = (work_item_id, dispatch_id)
    return {
        "stage": "run-turn-telemetry-check",
        "work_item_id": work_item_id,
        "dispatch_id": dispatch_id,
        "run_turn_exported": sink.has_export(keys=keys, exported_at_or_after=started_at_epoch),
        "run_turn_receiver_observed": sink.has_receiver_export(
            exported_at_or_after=started_at_epoch
        ),
        "run_turn_observable": True,
    }


def _span_name(*, span: dict[str, object]) -> str:
    raw = span.get("name")
    if isinstance(raw, str):
        return raw
    return ""


def _is_fresh_export(*, at: float | None, exported_at_or_after: float | None) -> bool:
    if at is None:
        return False
    if exported_at_or_after is None:
        return True
    return at >= exported_at_or_after


def _correlation_ids(*, span: dict[str, object], resource_attrs: dict[str, str]) -> tuple[str, ...]:
    attrs = dict(resource_attrs)
    attrs.update(_span_string_attrs(span=span))
    ids: list[str] = []
    for key in _CORRELATION_KEYS:
        value = attrs.get(key)
        if value is not None and value != "" and value not in ids:
            ids.append(scrub(value=value))
    return tuple(ids)


def _span_string_attrs(*, span: dict[str, object]) -> dict[str, str]:
    raw_attrs = span.get("attributes")
    if not isinstance(raw_attrs, list):
        return {}
    attrs: dict[str, str] = {}
    for raw in cast("list[object]", raw_attrs):
        if not isinstance(raw, dict):
            continue
        entry = cast("dict[str, object]", raw)
        key = entry.get("key")
        value = entry.get("value")
        if not isinstance(key, str) or key not in _CORRELATION_KEYS:
            continue
        if not isinstance(value, dict):
            continue
        string_value = cast("dict[str, object]", value).get("stringValue")
        if isinstance(string_value, str):
            attrs[key] = string_value
    return attrs


def _write_atomic(*, path: Path, tmp: Path, text: str) -> None:
    _ = path.parent.mkdir(parents=True, exist_ok=True)
    _ = tmp.write_text(text, encoding="utf-8")
    _ = tmp.replace(path)
