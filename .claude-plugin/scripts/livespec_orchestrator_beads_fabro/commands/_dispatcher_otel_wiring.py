"""OTEL receiver wiring and janitor argv parsing for the Dispatcher."""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._config import (
    FactoryTarget,
    resolve_fabro_factory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_pricing import (
    DEFAULT_DISPATCH_COST_MODEL_ENV,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_sink import CostSink
from livespec_orchestrator_beads_fabro.commands._dispatcher_otel_endpoint import (
    TailnetHostResolver,
    resolve_receiver_host,
    shell_tailnet_host,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
    calibration_spans_path,
    cost_report_spans_path,
    cost_sink_path,
    heartbeat_path,
    reflector_oob_spans_path,
    run_turn_sink_path,
    spans_path,
    tdd_order_sink_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_projection import (
    SANDBOX_OTEL_ENDPOINT_ENV_VAR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_turn_diagnostics import (
    run_turn_diagnostic_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_turn_sink import RunTurnSink
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_order_sink import TddOrderSink
from livespec_orchestrator_beads_fabro.commands._otel_receive import (
    HeartbeatSink,
    OtelReceiver,
    ReceiverConfig,
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


def _build_otel_receiver(
    *, args: argparse.Namespace, repo: Path, config: ReceiverConfig
) -> StartableServer:
    """Build (but do NOT start) the single host-local live OTLP receiver.

    Binds the addr/port `_receiver_config_for` resolved for this dispatch,
    wires the SHARED 29f.5 Honeycomb egress exporter (ingest-only
    key from env), points the metrics heartbeat at the journal-sibling
    file, and points the efj CC-token cost sink at its sibling
    `<base>-otel-cost.json` (the derived-cost seam the y0m spend cap
    reads), with the fallback pricing model resolved from
    `LIVESPEC_DISPATCH_COST_MODEL`. Imported lazily so the egress transport
    is only pulled in when a dispatch actually arms the receiver.

    The TDD order sink is wired the same way (plan slice S3): the sandbox
    order guard POSTs one decision span per product-write verdict to this
    receiver, and the sink accrues them per dispatch so calibration reads the
    refusal count and the first-write head state out of process.
    """
    from livespec_orchestrator_beads_fabro.commands._otel_enrich import HoneycombHttpExporter

    exporter = HoneycombHttpExporter(ingest_key=os.environ.get(_HONEYCOMB_INGEST_KEY_ENV, ""))
    heartbeat = HeartbeatSink(path=heartbeat_path(args=args, repo=repo))
    cost = CostSink(path=cost_sink_path(args=args, repo=repo))
    run_turn_path = run_turn_sink_path(args=args, repo=repo)
    run_turn = RunTurnSink(path=run_turn_path)
    default_model = os.environ.get(DEFAULT_DISPATCH_COST_MODEL_ENV, "").strip() or None
    return OtelReceiver(
        config=config,
        exporter=exporter,
        heartbeat=heartbeat,
        cost=cost,
        tdd_order=TddOrderSink(path=tdd_order_sink_path(args=args, repo=repo)),
        run_turn=run_turn,
        run_turn_diagnostics_path=run_turn_diagnostic_path(path=run_turn_path),
        default_model=default_model,
    )


def ensure_otel_receiver(
    *,
    args: argparse.Namespace,
    repo: Path,
    holder: dict[str, object] | None = None,
    factory: Callable[[], StartableServer] | None = None,
    tailnet_resolver: TailnetHostResolver | None = None,
) -> StartableServer | None:
    """Idempotently start the single shared live OTLP receiver (29f.7 E1).

    Called at dispatch entry. Fail-OPEN: a receiver start failure NEVER
    blocks or fails a dispatch (the dispatcher already wrote the
    authoritative journal; egress is best-effort). `holder` + `factory` are
    injectable for the hermetic test tier (so no real socket binds in a
    test); production uses the module-level holder + the real factory.
    `tailnet_resolver` is the third injection point: it supplies this host's
    own tailnet address for a remote-factory dispatch, so the hermetic tier
    resolves one without shelling out to `tailscale`.
    """
    target_holder = _OTEL_RECEIVER_HOLDER if holder is None else holder
    config = _receiver_config_for(args=args, repo=repo, tailnet_resolver=tailnet_resolver)
    resolved_factory = (
        (lambda: _build_otel_receiver(args=args, repo=repo, config=config))
        if factory is None
        else factory
    )
    server = ensure_receiver_started(holder=target_holder, factory=resolved_factory)
    if server is None and factory is None:
        server = _ensure_fallback_otel_receiver(
            args=args, repo=repo, holder=target_holder, config=config
        )
    _project_owned_receiver_endpoint(server=server)
    return server


def _dispatch_factory_target(*, args: argparse.Namespace, repo: Path) -> FactoryTarget:
    """The factory target this dispatch runs its sandbox on.

    `dispatch_preamble` pins `fabro_factory_target` before either entrypoint
    arms egress, so the config fallback covers arming reached OUTSIDE that
    preamble rather than the routine path — and it resolves the same way the
    preamble would, so the two never disagree about which host runs the work.
    """
    pinned = getattr(args, "fabro_factory_target", None)
    if isinstance(pinned, FactoryTarget):
        return pinned
    return resolve_fabro_factory(cwd=repo)


def _receiver_config_for(
    *,
    args: argparse.Namespace,
    repo: Path,
    tailnet_resolver: TailnetHostResolver | None,
) -> ReceiverConfig:
    """Resolve the addr/port this dispatch's receiver binds AND advertises.

    The port stays exactly what the `LIVESPEC_OTEL_RECEIVER_*` levers say. Only
    the HOST moves, and only for a remote-factory dispatch, whose sandbox
    cannot reach the Docker-bridge literal those levers default to.
    """
    environ = dict(os.environ)
    configured = resolve_receiver_config(environ=environ)
    host = resolve_receiver_host(
        factory=_dispatch_factory_target(args=args, repo=repo),
        bridge_host=configured.host,
        environ=environ,
        resolver=(
            partial(shell_tailnet_host, cwd=repo) if tailnet_resolver is None else tailnet_resolver
        ),
    )
    return ReceiverConfig(host=host, port=configured.port)


def _ensure_fallback_otel_receiver(
    *,
    args: argparse.Namespace,
    repo: Path,
    holder: dict[str, object],
    config: ReceiverConfig,
) -> StartableServer | None:
    fallback = ReceiverConfig(host=config.host, port=0)
    return ensure_receiver_started(
        holder=holder,
        factory=lambda: _build_otel_receiver(args=args, repo=repo, config=fallback),
    )


def _project_owned_receiver_endpoint(*, server: StartableServer | None) -> None:
    """Tell the sandbox where to post, using the address the receiver BOUND.

    Reading the host back off `server.config` is what keeps the two halves in
    lockstep: whatever `_receiver_config_for` decided to bind is exactly what
    gets advertised, so a remote-factory dispatch can never advertise an
    address the receiver is not listening on.
    """
    if not isinstance(server, OtelReceiver):
        return
    if server.bound_port <= 0:
        return
    os.environ[SANDBOX_OTEL_ENDPOINT_ENV_VAR] = f"http://{server.config.host}:{server.bound_port}"


def _driver_span_paths(*, args: argparse.Namespace, repo: Path) -> tuple[Path, ...]:
    """The per-journal host span files the enrich driver tails (29f.5).

    Each is a journal sibling written by a distinct host emitter: the
    mechanical-reflection stage (`-reflection-spans.jsonl`), the out-of-band
    reflector (`-reflector-oob-spans.jsonl`), and report mode
    (`-cost-report-spans.jsonl`), and calibration
    (`-calibration-spans.jsonl`). All four ride the SAME file-tail -> enrich
    egress path, so the driver covers every host span-file kind.

    The 2026-06-14 dispatch-outcome span stop is a SEPARATE gap, not this one.
    Stated explicitly because assuming it is the same is the cheap answer and
    the wrong one. Calibration's was a PROMOTION gap: the records were being
    produced (245 of them in the live journal) and nothing tailed them into
    egress, which is what adding the fourth path above fixes. The
    dispatch-outcome columns (`detail`, `exit_code`, `dispatcher.stages`,
    `dispatcher.final_stage`) stopped for a different reason -- NOTHING EMITS
    THEM. Measured over this tree with positive controls: `EnrichStage` 26 hits
    and `_driver_span_paths` 2, so the search reaches the right population;
    `dispatcher.stages` and `dispatcher.final_stage` return 0 hits in any `.py`,
    and the span name `"dispatcher.dispatch"` appears 0 times in plugin code
    against 2 in `test_otel_enrich.py`, where the tests synthesise such a span as
    fixture INPUT. So the enrich leg is ready to carry that span and no producer
    hands it one. Promoting calibration therefore cannot restore those columns;
    the dispatch-outcome gap sits upstream of egress and needs its own emitter.
    """
    return (
        spans_path(args=args, repo=repo),
        reflector_oob_spans_path(args=args, repo=repo),
        cost_report_spans_path(args=args, repo=repo),
        calibration_spans_path(args=args, repo=repo),
    )


def _build_otel_enrich_driver(*, args: argparse.Namespace, repo: Path) -> StartableServer:
    """Build (but do NOT start) the single host-local file-tail enrich driver.

    Wires one 29f.5 `EnrichStage` per host span-file kind over the SHARED
    Honeycomb egress exporter (the ingest-only key from env; the same fail-soft
    `.get(..., "")` the receiver factory uses, so a missing key never crashes the
    fail-open arming). The `HoneycombHttpExporter` is frozen/immutable, so one
    instance is safely shared across the four stages. Imported lazily so the
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
