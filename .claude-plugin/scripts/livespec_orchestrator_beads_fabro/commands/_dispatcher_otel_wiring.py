"""OTEL receiver wiring and janitor argv parsing for the Dispatcher."""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_pricing import (
    DEFAULT_DISPATCH_COST_MODEL_ENV,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_sink import CostSink
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
    cost_report_spans_path,
    cost_sink_path,
    heartbeat_path,
    reflector_oob_spans_path,
    spans_path,
)
from livespec_orchestrator_beads_fabro.commands._otel_receive import (
    HeartbeatSink,
    OtelReceiver,
    StartableServer,
    ensure_receiver_started,
    resolve_receiver_config,
)
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json
from livespec_orchestrator_beads_fabro.io import write_stderr

__all__: list[str] = [
    "arm_otel_egress",
    "ensure_otel_enrich_driver",
    "ensure_otel_receiver",
    "parse_janitor",
]

# The ingest-only Honeycomb key (write-only; the management/MCP key never
# touches this egress path, per telemetry-pipeline-architecture.md §3.4).
# An env-var NAME, not a secret value.
_HONEYCOMB_INGEST_KEY_ENV = "HONEYCOMB_INGEST_KEY_LIVESPEC"

# Process-level holder for the single shared live OTLP receiver (29f.7 E1).
# `ensure_receiver_started` keeps ONE receiver per host across concurrent
# dispatches in this dict — NOT one per dispatch (that would collide on the
# bound port). Module-scoped state, started fail-open at dispatch entry.
_OTEL_RECEIVER_HOLDER: dict[str, object] = {}

# Sibling holder for the single shared file-tail enrich DRIVER (29f.5). Same
# single-instance-per-host discipline as the receiver holder above: one driver
# tails the per-journal span files across concurrent dispatches, started
# fail-open at dispatch entry via the SAME `ensure_receiver_started` supervisor.
_OTEL_ENRICH_DRIVER_HOLDER: dict[str, object] = {}


def _build_otel_receiver(*, args: argparse.Namespace, repo: Path) -> StartableServer:
    """Build (but do NOT start) the single host-local live OTLP receiver.

    Resolves the bound loopback addr/port from the `LIVESPEC_OTEL_RECEIVER_*`
    levers, wires the SHARED 29f.5 Honeycomb egress exporter (ingest-only
    key from env), points the metrics heartbeat at the journal-sibling
    file, and points the efj CC-token cost sink at its sibling
    `<base>-otel-cost.json` (the derived-cost seam the y0m spend cap
    reads), with the fallback pricing model resolved from
    `LIVESPEC_DISPATCH_COST_MODEL`. Imported lazily so the egress transport
    is only pulled in when a dispatch actually arms the receiver.
    """
    from livespec_orchestrator_beads_fabro.commands._otel_enrich import HoneycombHttpExporter

    config = resolve_receiver_config(environ=dict(os.environ))
    exporter = HoneycombHttpExporter(ingest_key=os.environ.get(_HONEYCOMB_INGEST_KEY_ENV, ""))
    heartbeat = HeartbeatSink(path=heartbeat_path(args=args, repo=repo))
    cost = CostSink(path=cost_sink_path(args=args, repo=repo))
    default_model = os.environ.get(DEFAULT_DISPATCH_COST_MODEL_ENV, "").strip() or None
    return OtelReceiver(
        config=config,
        exporter=exporter,
        heartbeat=heartbeat,
        cost=cost,
        default_model=default_model,
    )


def ensure_otel_receiver(
    *,
    args: argparse.Namespace,
    repo: Path,
    holder: dict[str, object] | None = None,
    factory: Callable[[], StartableServer] | None = None,
) -> StartableServer | None:
    """Idempotently start the single shared live OTLP receiver (29f.7 E1).

    Called at dispatch entry. Fail-OPEN: a receiver start failure NEVER
    blocks or fails a dispatch (the dispatcher already wrote the
    authoritative journal; egress is best-effort). `holder` + `factory` are
    injectable for the hermetic test tier (so no real socket binds in a
    test); production uses the module-level holder + the real factory.
    """
    target_holder = _OTEL_RECEIVER_HOLDER if holder is None else holder
    resolved_factory = (
        (lambda: _build_otel_receiver(args=args, repo=repo)) if factory is None else factory
    )
    return ensure_receiver_started(holder=target_holder, factory=resolved_factory)


def _driver_span_paths(*, args: argparse.Namespace, repo: Path) -> tuple[Path, ...]:
    """The three per-journal host span files the enrich driver tails (29f.5).

    Each is a journal sibling written by a distinct host emitter: the
    mechanical-reflection stage (`-reflection-spans.jsonl`), the out-of-band
    reflector (`-reflector-oob-spans.jsonl`), and report mode
    (`-cost-report-spans.jsonl`). All three ride the SAME file-tail -> enrich
    egress path, so the driver covers every host span-file kind.
    """
    return (
        spans_path(args=args, repo=repo),
        reflector_oob_spans_path(args=args, repo=repo),
        cost_report_spans_path(args=args, repo=repo),
    )


def _build_otel_enrich_driver(*, args: argparse.Namespace, repo: Path) -> StartableServer:
    """Build (but do NOT start) the single host-local file-tail enrich driver.

    Wires one 29f.5 `EnrichStage` per host span-file kind over the SHARED
    Honeycomb egress exporter (the ingest-only key from env; the same fail-soft
    `.get(..., "")` the receiver factory uses, so a missing key never crashes the
    fail-open arming). The `HoneycombHttpExporter` is frozen/immutable, so one
    instance is safely shared across the three stages. Imported lazily so the
    egress transport is only pulled in when a dispatch actually arms the driver.
    """
    from livespec_orchestrator_beads_fabro.commands._otel_enrich import (
        EnrichStage,
        HoneycombHttpExporter,
    )
    from livespec_orchestrator_beads_fabro.commands._otel_enrich_driver import OtelEnrichDriver

    exporter = HoneycombHttpExporter(ingest_key=os.environ.get(_HONEYCOMB_INGEST_KEY_ENV, ""))
    stages = tuple(
        EnrichStage(spans_path=path, exporter=exporter)
        for path in _driver_span_paths(args=args, repo=repo)
    )
    return OtelEnrichDriver(stages=stages)


def ensure_otel_enrich_driver(
    *,
    args: argparse.Namespace,
    repo: Path,
    holder: dict[str, object] | None = None,
    factory: Callable[[], StartableServer] | None = None,
) -> StartableServer | None:
    """Idempotently start the single shared file-tail enrich driver (29f.5).

    Called at dispatch entry alongside `ensure_otel_receiver`, and reuses the
    SAME single-instance-fail-open supervisor (`ensure_receiver_started`, whose
    `StartableServer` contract `OtelEnrichDriver` satisfies). Fail-OPEN: a driver
    start failure NEVER blocks or fails a dispatch. `holder` + `factory` are
    injectable for the hermetic test tier; production uses the module-level
    holder + the real factory.
    """
    target_holder = _OTEL_ENRICH_DRIVER_HOLDER if holder is None else holder
    resolved_factory = (
        (lambda: _build_otel_enrich_driver(args=args, repo=repo)) if factory is None else factory
    )
    return ensure_receiver_started(holder=target_holder, factory=resolved_factory)


def arm_otel_egress(*, args: argparse.Namespace, repo: Path) -> None:
    """Arm BOTH host-side OTel egress planes at dispatch entry (fail-open).

    The receiver ingests the sandbox's live Claude-Code OTel; the file-tail
    driver forwards the host span files the dispatcher + reflector write. Both
    are single-instance-per-host and fail-open (a start failure NEVER blocks a
    dispatch), so the two dispatch entrypoints (`dispatch` / `loop`) arm the
    whole egress plane through this one call.
    """
    _ = ensure_otel_receiver(args=args, repo=repo)
    _ = ensure_otel_enrich_driver(args=args, repo=repo)


def parse_janitor(*, raw: str | None) -> tuple[tuple[str, ...] | None, bool]:
    """Parse the --janitor JSON-argv flag; (argv-or-None, parse-ok)."""
    if raw is None:
        return None, True
    parsed_raw = parse_json(text=raw)
    if isinstance(parsed_raw, JsonParseFailure):
        parsed_raw = None
    if not isinstance(parsed_raw, list):
        _ = write_stderr(text="ERROR: --janitor must be a JSON array of strings\n")
        return None, False
    parts: list[str] = []
    for part in cast("list[object]", parsed_raw):
        if not isinstance(part, str):
            _ = write_stderr(text="ERROR: --janitor must be a JSON array of strings\n")
            return None, False
        parts.append(part)
    return tuple(parts), True
