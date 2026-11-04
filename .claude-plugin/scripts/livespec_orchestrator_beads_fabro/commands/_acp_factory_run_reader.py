"""Production factory-native reader for host-wide ACP availability evidence."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, cast

from livespec_orchestrator_beads_fabro.commands._config import (
    resolve_fabro_bin,
    resolve_fabro_factory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_bin import (
    factory_fabro_bin,
)

# The LEAF, not the `_dispatcher_io` aggregate that re-exports it. Overflow
# selection reads a candidate factory through this reader, and the ledger
# resolution it serves is inside `_dispatcher_io`'s own import closure — so the
# aggregate would close the cycle `_dispatcher_shell_runner` exists to break.
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import (
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._fabro_port_compressed import (
    CompressedUrllibTransport,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpTransport
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    FabroRunSummary,
    fabro_inspect_record,
    scheduler_max_concurrent_runs_from_payload,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroRunner

__all__: list[str] = [
    "EVIDENCE_READ_UNANSWERED_STAGE",
    "READ_ONLY_FABRO_VERBS",
    "FactoryRunReader",
]

_READ_TIMEOUT_SECONDS = 60.0

# THE RUN-RECORD READ IS BOUNDED, COMPRESSED AND RETRIED (bd-ib-fhmpik). One
# failed petri run's 10.4 MB record could not be read inside the engine CLI's
# fixed 30 s, so the scan reported it unreadable and that one row blanked every
# Anthropic and Codex candidate fleet-wide for 13 minutes. The server's state
# route returns the same record, and with gzip it arrived in 0.92 s. Each
# attempt is bounded well inside the CLI's 30 s, and an attempt that gets no
# answer is taken again once in the same evaluation before the run is reported
# unreadable: "An unreadable or incomplete evidence source is unavailable",
# and a single slow transfer should not be the thing that makes it so.
_STATE_READ_TIMEOUT_SECONDS = 20.0
_STATE_READ_ATTEMPTS = 2

# The journal stage each unanswered record-read attempt is recorded under.
EVIDENCE_READ_UNANSWERED_STAGE = "acp-evidence-read-unanswered"

# The engine verbs this reader may spend, as a DECLARATION rather than as a
# property of whichever methods happen to exist.
#
# The idle-factory clause requires snapshot composition to observe the
# factory-native availability evidence and forbids it to "execute credential
# probes, availability confirmation turns, or mutations" -- and a snapshot
# composes this reader, so every verb below is one an awareness surface spends
# on an operator's behalf. A `run` submission IS the availability confirmation
# turn that clause names; `auth` and `secret` write host and server credential
# state; `rm` destroys a run. None of them is reachable from the three methods
# here, and the point of naming the admitted set is that a future method
# reaching past it fails a check rather than quietly widening what composing
# an attention snapshot does.
#
# DECLARED HERE rather than in the test that grades it, because a verb set
# spelled in a test is one copy of the rule compared against another copy of
# the same transcription: both would agree after a new method left the set.
READ_ONLY_FABRO_VERBS: tuple[str, ...] = ("inspect", "ps", "settings")


class _JournalWriter(Protocol):
    def append(self, *, record: dict[str, object]) -> None:
        """Persist one journal record."""
        ...


@dataclass(frozen=True, kw_only=True)
class FactoryRunReader:
    """Read declared factories through the Dispatcher Fabro-port facade.

    Every read resolves the named factory from the target repository's
    ``dispatcher.factories`` table. A missing server is unreadable rather than
    a reason to let Fabro select its local default server.
    """

    repo: Path
    runner: FabroRunner = field(default_factory=ShellCommandRunner)
    http_transport: FabroHttpTransport = field(default_factory=CompressedUrllibTransport)
    journal: _JournalWriter | None = None
    clock: Callable[[], float] = field(default=time.monotonic)

    def list_runs(self, *, factory: str) -> tuple[FabroRunSummary, ...] | None:
        """Return the declared factory's parsed run rows, or ``None`` if unreadable."""
        port = self._port(factory=factory)
        if port is None:
            return None
        result = port.ps(timeout_seconds=_READ_TIMEOUT_SECONDS)
        if result.command.exit_code != 0 or not _ps_payload(payload=result.payload):
            return None
        return result.runs

    def scheduler_max_concurrent_runs(self, *, factory: str) -> int | None:
        """One declared factory's own scheduler ceiling, or ``None`` if unreadable.

        ``None`` is the UNANSWERED reading and never a ceiling of nothing — the
        same line ``list_runs`` draws beside it. Overflow selection turns an
        unanswered ceiling into "this candidate has no free slot", which is the
        fail-closed direction its clause names; a zero would be a ceiling the
        server genuinely reported.
        """
        port = self._port(factory=factory)
        if port is None:
            return None
        result = port.settings(timeout_seconds=_READ_TIMEOUT_SECONDS)
        if result.command.exit_code != 0:
            return None
        return scheduler_max_concurrent_runs_from_payload(payload=result.payload)

    def inspect_payload(self, *, factory: str, run_id: str) -> object | None:
        """Return one declared factory's run record, or ``None`` if unreadable.

        The server's state route is asked first, compressed and bounded, and
        an attempt that gets NO answer is journaled and taken once more. A
        server that ANSWERS with a refusal -- a build without the route, or a
        credential it declines -- is not retried: the engine CLI's `inspect`
        is then the read, exactly as it was before the state route was used.
        """
        port = self._port(factory=factory)
        if port is None:
            return None
        server_api = port.server_api()
        for attempt_number in range(1, _STATE_READ_ATTEMPTS + 1):
            started = self.clock()
            state = server_api.run_state(run_id=run_id, timeout_seconds=_STATE_READ_TIMEOUT_SECONDS)
            record = fabro_inspect_record(payload=state.payload) if state.succeeded else None
            if record is not None:
                return _inspect_shaped(record=record, run_id=run_id)
            if state.status != 0:
                return self._cli_inspect(port=port, run_id=run_id)
            self._journal_unanswered(
                factory=factory,
                run_id=run_id,
                attempt_number=attempt_number,
                elapsed=self.clock() - started,
                error=state.error,
            )
        return None

    def _journal_unanswered(
        self,
        *,
        factory: str,
        run_id: str,
        attempt_number: int,
        elapsed: float,
        error: str | None,
    ) -> None:
        if self.journal is None:
            return
        self.journal.append(
            record={
                "stage": EVIDENCE_READ_UNANSWERED_STAGE,
                "factory": factory,
                "run_id": run_id,
                "attempt": attempt_number,
                "elapsed_seconds": round(elapsed, 3),
                "error": error,
            }
        )

    def _cli_inspect(self, *, port: FabroPort, run_id: str) -> object | None:
        result = port.inspect(run_id=run_id, timeout_seconds=_READ_TIMEOUT_SECONDS)
        if result.command.exit_code != 0 or fabro_inspect_record(payload=result.payload) is None:
            return None
        return result.payload

    def _port(self, *, factory: str) -> FabroPort | None:
        target = resolve_fabro_factory(cwd=self.repo, factory=factory)
        if target.server is None:
            return None
        return FabroPort(
            fabro_bin=factory_fabro_bin(factory=target, fallback=resolve_fabro_bin(cwd=self.repo)),
            target=FabroTarget(server_url=target.server, dev_token=target.dev_token),
            runner=self.runner,
            cwd=self.repo,
            http=self.http_transport,
        )


def _inspect_shaped(*, record: dict[str, Any], run_id: str) -> dict[str, Any]:
    """The state route's record in the shape `fabro inspect --json` prints.

    The route carries the same conclusion, status and stages, but no `run_id`
    and no top-level `checkpoint`: its checkpoints are a list, each wrapping
    its state. The inspect shape's `checkpoint` is the newest of them, and the
    clearance reader reads it there, so it is supplied rather than letting one
    grader see a different record from the read it used to take.
    """
    shaped = dict(record)
    shaped.setdefault("run_id", run_id)
    entries: object = record.get("checkpoints")
    if "checkpoint" not in shaped and isinstance(entries, list) and entries:
        newest: object = cast("list[object]", entries)[-1]
        if isinstance(newest, dict):
            shaped["checkpoint"] = cast("dict[str, Any]", newest).get("checkpoint")
    return shaped


def _ps_payload(*, payload: object | None) -> bool:
    """Whether a parsed ``fabro ps --json`` payload has its documented shape."""
    if isinstance(payload, list):
        return True
    if not isinstance(payload, dict):
        return False
    return isinstance(cast("dict[str, object]", payload).get("runs"), list)
