"""OTEL receiver wiring and janitor argv parsing for the Dispatcher."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_pricing import (
    DEFAULT_DISPATCH_COST_MODEL_ENV,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_sink import CostSink
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
    cost_sink_path,
    heartbeat_path,
)
from livespec_orchestrator_beads_fabro.commands._otel_receive import (
    HeartbeatSink,
    OtelReceiver,
    StartableServer,
    ensure_receiver_started,
    resolve_receiver_config,
)
from livespec_orchestrator_beads_fabro.io import write_stderr

__all__: list[str] = [
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


def parse_janitor(*, raw: str | None) -> tuple[tuple[str, ...] | None, bool]:
    """Parse the --janitor JSON-argv flag; (argv-or-None, parse-ok)."""
    if raw is None:
        return None, True
    try:
        parsed_raw: object = json.loads(raw)
    except json.JSONDecodeError:
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
