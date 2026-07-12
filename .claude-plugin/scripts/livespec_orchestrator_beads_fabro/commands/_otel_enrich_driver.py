"""Host-side file-tail OTLP egress DRIVER — the production pump for the enrich stage.

The 29f.5 `EnrichStage` file-tail data plane (`_otel_enrich`) was built but
never DRIVEN: no production caller ran `forward_once`, so the per-journal host
span files the dispatcher + reflector write — `<base>-reflection-spans.jsonl`,
`<base>-reflector-oob-spans.jsonl`, `<base>-cost-report-spans.jsonl` — had ZERO
egress to Honeycomb (the `livespec-dispatcher` dataset stayed dark). This module
is that missing driver: a periodic background pump that tails each dispatch's
span files and forwards them, mirroring the live receiver's daemon-thread
lifecycle (`_otel_receive.OtelReceiver`). It is armed once per host at dispatch
entry (alongside `ensure_otel_receiver`), runs for the dispatch, and — critically
— FINAL-flushes at process exit via `atexit`, because the reflection / reflector
span files are written at dispatch END (after the last periodic poll), so a
dispatch that returns immediately after `reflect()` still egresses its host spans.

Posture (inherited from the `EnrichStage` it drives): fail-OPEN toward the
pipeline — `EnrichStage.forward_once` catches internally and never raises — so a
forward / export error never blocks or fails a dispatch (the dispatcher already
wrote the authoritative journal; egress is best-effort).
"""

from __future__ import annotations

import atexit
import threading
from dataclasses import dataclass, field

from livespec_orchestrator_beads_fabro.commands._otel_enrich import EnrichStage

__all__: list[str] = ["OtelEnrichDriver"]

# The committed poll cadence. A pass over an unchanged file is a cheap stat +
# zero-byte read (no export call), so a short cadence costs little; the final
# atexit flush is what guarantees the end-written reflection spans egress.
_DEFAULT_POLL_INTERVAL_SECONDS = 5.0
# Bounded thread join so `stop()` is deterministic and never wedges shutdown.
_JOIN_TIMEOUT_SECONDS = 5.0


@dataclass(kw_only=True)
class OtelEnrichDriver:
    """Periodic file-tail pump over the per-journal host span files.

    Holds one `EnrichStage` per host span-file kind (each with its own resumable
    byte-offset cursor and the SHARED Honeycomb exporter). `start()` spawns a
    daemon thread that runs `forward_all()` every `interval_seconds` — mirroring
    the live receiver's daemon thread — and registers `stop` with `atexit` so the
    end-written reflection spans still flush when the process exits right after
    `reflect()`. `stop()` signals the thread, joins it, and runs a FINAL
    `forward_all()`; it is idempotent (a second call, e.g. an explicit `stop()`
    after the atexit hook already ran, is a harmless no-op) and deterministic (it
    joins before the final flush, so no pass ever races another).
    """

    stages: tuple[EnrichStage, ...]
    interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)

    def start(self) -> None:
        """Spawn the periodic-tail daemon thread + register the exit flush (idempotent)."""
        if self._thread is not None:
            return
        _ = atexit.register(self.stop)
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
        self._thread = thread

    def stop(self) -> None:
        """Signal + join the thread, then run a FINAL flush (idempotent, deterministic)."""
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=_JOIN_TIMEOUT_SECONDS)
        self.forward_all()
        self._thread = None
        atexit.unregister(self.stop)

    def is_running(self) -> bool:
        """True once the daemon thread is live and before `stop()` clears it."""
        return self._thread is not None

    def forward_all(self) -> None:
        """Run one fail-open forward pass over every span-file stage.

        Each `forward_once` is fail-open (it catches internally and never
        raises), so one bad stage never stops the others and no forward error
        escapes toward a dispatch.
        """
        for stage in self.stages:
            _ = stage.forward_once()

    def _run(self) -> None:
        """Poll `forward_all()` until `stop()` sets the event (daemon-thread body).

        `Event.wait(timeout)` returns True the instant `stop()` sets the event
        (breaking the loop promptly) or False on timeout (drive one more pass).
        """
        while not self._stop.wait(timeout=self.interval_seconds):
            self.forward_all()
