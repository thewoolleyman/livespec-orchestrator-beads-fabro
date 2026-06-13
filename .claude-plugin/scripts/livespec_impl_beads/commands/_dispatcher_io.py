"""Side-effect seams for the Dispatcher: subprocess runner + journal.

`ShellCommandRunner` is the production `CommandRunner`: it executes the
engine's argvs via `subprocess.run` with captured output and converts
timeouts into non-zero `CommandResult`s (the engine treats every failure
as routable data, so the runner never lets an expected failure escape as
an exception). The hermetic test tier exercises it with
`sys.executable -c` stubs, mirroring how `test_orchestrator` drives the
injected reference CLIs.

`WatchedFabroLauncher` is the production `FabroLauncher`: it runs `fabro
run` in a BACKGROUND thread (through the injected `CommandRunner`, which
blocks in the thread) while the FOREGROUND samples the run's liveness via
`fabro ps`/`fabro events` and `fabro rm -f`-es a confirmed sustained
stall (the coarse wall-clock progress watchdog, work-item
livespec-impl-beads-oyg — the 7us.6 silent-deadlock backstop). Like
`ShellCommandRunner` it is a production seam the hermetic unit tier does
NOT execute: the engine's stall branch is driven by injecting a fake
`FabroLauncher`, and the watchdog DECISION logic is unit-tested directly
in `_dispatcher_watchdog`. No test launches a real fabro run.

`JournalFile` is the structured iteration journal the Dispatcher
guidance requires (livespec non-functional-requirements.md
§"Orchestrator-internal Dispatcher guidance"): append-only JSONL, one
record per engine stage / loop event, machine-readable for post-hoc
audit. Appends are lock-serialized so parallel dispatch threads cannot
interleave lines.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from livespec_impl_beads.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
    FabroRunResult,
    JournalWriter,
)
from livespec_impl_beads.commands._dispatcher_heartbeat_probe import (
    HeartbeatLivenessProbe,
    LayeredLivenessProbe,
    heartbeat_lookup_keys,
)
from livespec_impl_beads.commands._dispatcher_plan import (
    DispatchPlan,
    fabro_events_argv,
    fabro_inspect_argv,
    fabro_ps_argv,
    fabro_rm_argv,
    fabro_run_argv,
    parse_running_run_id,
)
from livespec_impl_beads.commands._dispatcher_watchdog import (
    LivenessSample,
    StallVerdict,
    decide_stall,
    parse_last_event_epoch,
    resolve_stall_seconds,
)
from livespec_impl_beads.commands._otel_receive import HeartbeatSink

__all__: list[str] = [
    "JournalFile",
    "ShellCommandRunner",
    "WatchedFabroLauncher",
    "utc_now_iso",
]

# Engine-side timeouts mirrored here (the launcher owns the `fabro run`
# subprocess ceiling — bn4's coarse 15h timeout, which COEXISTS with the
# watchdog as defense in depth) and the short probe timeouts.
_FABRO_TIMEOUT_SECONDS = 54000.0
_FABRO_PROBE_TIMEOUT_SECONDS = 60.0
_FABRO_RM_TIMEOUT_SECONDS = 120.0

# How often the foreground watchdog samples liveness while `fabro run`
# runs in the background. 30s is fine-grained enough that a 25min default
# stall window accumulates ~50 samples, yet light on the host: ~83 fabro
# events per run, polled read-only, never near the rate limit.
_WATCHDOG_POLL_INTERVAL_SECONDS = 30.0


@dataclass(frozen=True, kw_only=True)
class ShellCommandRunner:
    """Production CommandRunner: subprocess.run with captured output."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
    ) -> CommandResult:
        try:
            completed = subprocess.run(  # noqa: S603 - argvs are Dispatcher-built, never shell
                argv,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                exit_code=124,
                stdout=_decode(raw=exc.stdout),
                stderr=_decode(raw=exc.stderr) + f"\ntimeout after {timeout_seconds}s",
            )
        return CommandResult(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


@dataclass(frozen=True, kw_only=True)
class _WallClockEventProbe:
    """The coarse wall-clock backstop expressed as a `LivenessProbe`.

    Wraps the pre-29f.6 inline reading: the max `fabro events` timestamp
    (with `fabro inspect`'s `updated_at` as a fallback) for `run_id`, or
    no signal when the run id has not resolved yet or both probes error.
    Pulled out as a `LivenessProbe` so `_WatchedFabroLauncher._sample` can
    compose it as the FALLBACK layer under the 29f.6 heartbeat primary.
    The `decide_stall` fail-safety contract is unchanged — a probe error
    is a no-signal sample, never a stall.
    """

    plan: DispatchPlan
    runner: CommandRunner
    run_id: str | None

    def sample(self, *, observed_at: float) -> LivenessSample:
        if self.run_id is None:
            return LivenessSample(last_event_epoch=None, observed_at=observed_at)
        events = self.runner.run(
            argv=fabro_events_argv(plan=self.plan, run_id=self.run_id),
            cwd=self.plan.repo,
            timeout_seconds=_FABRO_PROBE_TIMEOUT_SECONDS,
        )
        inspect = self.runner.run(
            argv=fabro_inspect_argv(plan=self.plan, run_id=self.run_id),
            cwd=self.plan.repo,
            timeout_seconds=_FABRO_PROBE_TIMEOUT_SECONDS,
        )
        events_json = events.stdout if events.exit_code == 0 else ""
        inspect_json = inspect.stdout if inspect.exit_code == 0 else ""
        epoch = parse_last_event_epoch(events_json=events_json, inspect_json=inspect_json)
        return LivenessSample(last_event_epoch=epoch, observed_at=observed_at)


@dataclass(frozen=True, kw_only=True)
class WatchedFabroLauncher:
    """Production FabroLauncher: `fabro run` + the coarse wall-clock watchdog.

    Runs `fabro run` in a daemon BACKGROUND thread (it blocks there
    through the injected `CommandRunner`), while the FOREGROUND samples
    the run's liveness on a fixed interval until either the run thread
    finishes OR the watchdog confirms a sustained-no-progress stall.

    Liveness signal (layered): the DEFERRED-PRIMARY signal (29f.6) is the
    29f metrics-HEARTBEAT — CC's metric export keeps advancing while a
    turn is genuinely alive even when ZERO spans/events are emitted (the
    7us.6 wedged-commit class), so it is a finer, earlier signal than the
    coarse event stream. When `heartbeat_path` is set the launcher layers
    a `HeartbeatLivenessProbe` over the coarse wall-clock probe as the
    PRIMARY, with the wall-clock probe as the PERMANENT fallback: an
    observability-pipeline outage degrades the watchdog to coarse
    detection, NEVER to NO detection. The coarse BACKSTOP reading is the
    run id discovered from `fabro ps -a --json` (the still-blocking `fabro
    run` output is unavailable until completion), then the max event
    timestamp from `fabro events <id> --json` (with `fabro inspect`'s
    `updated_at` as a fallback). Either layer's reading feeds the SAME
    `decide_stall`, which confirms a stall ONLY on the FULL stall window
    of genuinely-absent activity.

    Fail-safety (load-bearing): a probe failure — `fabro ps` / `fabro
    events` / `fabro inspect` errors or is unreachable, the run id is not
    discoverable yet, or the heartbeat file is missing / malformed — is
    "no signal", recorded as a sample with NO timestamp, which
    `decide_stall` skips. A flaky probe can therefore NEVER kill a healthy
    run; only the full window of present-but-frozen timestamps trips it.
    On a confirmed stall the run is `fabro rm -f`-ed and `stalled_run_id`
    is set; otherwise the launcher waits for the run thread and returns
    its `CommandResult` (exit-code routing unchanged).

    `sleep` and `clock` are injectable (default `time.sleep` /
    `time.monotonic`) so the hermetic tier drives the watch loop
    deterministically with a controllable clock and instant polls — no
    real wall-clock wait, no global monkeypatching of `time`.
    `heartbeat_path` is the journal-sibling heartbeat file the live
    receiver writes (None disables the heartbeat layer, leaving the pure
    wall-clock backstop — the pre-29f.6 behavior).
    """

    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    heartbeat_path: Path | None = None

    def launch(
        self,
        *,
        plan: DispatchPlan,
        runner: CommandRunner,
        journal: JournalWriter,
    ) -> FabroRunResult:
        holder: dict[str, CommandResult] = {}

        def _run_fabro() -> None:
            holder["result"] = runner.run(
                argv=fabro_run_argv(plan=plan),
                cwd=plan.repo,
                timeout_seconds=_FABRO_TIMEOUT_SECONDS,
            )

        thread = threading.Thread(target=_run_fabro, name=f"fabro-run-{plan.work_item_id}")
        thread.daemon = True
        thread.start()
        stalled_run_id = self._watch(plan=plan, runner=runner, journal=journal, thread=thread)
        if stalled_run_id is not None:
            # The `fabro rm -f` makes the backgrounded `fabro run` return;
            # join with a bounded grace so a wedged process cannot pin the
            # dispatch (it is a daemon thread regardless).
            thread.join(timeout=_FABRO_RM_TIMEOUT_SECONDS)
            return FabroRunResult(
                command=holder.get(
                    "result",
                    CommandResult(exit_code=124, stdout="", stderr="cancelled by stall watchdog"),
                ),
                stalled_run_id=stalled_run_id,
            )
        thread.join()
        return FabroRunResult(command=holder["result"])

    def _watch(
        self,
        *,
        plan: DispatchPlan,
        runner: CommandRunner,
        journal: JournalWriter,
        thread: threading.Thread,
    ) -> str | None:
        """Sample liveness until the run finishes or a stall is confirmed.

        `known_run_id` latches the most-recently-resolved run id so a
        transient `fabro ps` failure on the deciding poll does not lose
        the run we must cancel — a stall can only be CONFIRMED from
        timestamped samples, which require a run id to have resolved at
        least once, so `known_run_id` is always set by the time a STALLED
        verdict appears.
        """
        stall_seconds = resolve_stall_seconds()
        samples: list[LivenessSample] = []
        known_run_id: str | None = None
        while thread.is_alive():
            self.sleep(_WATCHDOG_POLL_INTERVAL_SECONDS)
            run_id = self._discover_run_id(plan=plan, runner=runner)
            known_run_id = run_id if run_id is not None else known_run_id
            samples.append(self._sample(plan=plan, runner=runner, run_id=run_id))
            if known_run_id is None:
                # No run resolved yet -> no timestamped sample can exist ->
                # no stall is decidable; keep waiting (a never-resolving
                # `fabro ps` is "no signal", never a stall).
                continue
            if decide_stall(samples=tuple(samples), stall_seconds=stall_seconds) is (
                StallVerdict.STALLED
            ):
                self._cancel(plan=plan, runner=runner, journal=journal, run_id=known_run_id)
                return known_run_id
        return None

    def _discover_run_id(self, *, plan: DispatchPlan, runner: CommandRunner) -> str | None:
        ps = runner.run(
            argv=fabro_ps_argv(plan=plan),
            cwd=plan.repo,
            timeout_seconds=_FABRO_PROBE_TIMEOUT_SECONDS,
        )
        if ps.exit_code != 0:
            return None
        return parse_running_run_id(ps_json=ps.stdout, work_item_id=plan.work_item_id)

    def _sample(
        self,
        *,
        plan: DispatchPlan,
        runner: CommandRunner,
        run_id: str | None,
    ) -> LivenessSample:
        """Take one layered liveness reading: heartbeat PRIMARY, wall-clock backstop.

        When `heartbeat_path` is set the 29f.6 metrics-heartbeat is the
        deferred-PRIMARY signal: a `HeartbeatLivenessProbe` is layered over
        the coarse wall-clock probe, so a fresh heartbeat (finer, earlier)
        wins and a stale/absent/malformed heartbeat falls THROUGH to the
        wall-clock backstop — degrade to coarse detection, never to NO
        detection. With no `heartbeat_path` the pure wall-clock probe runs
        (the pre-29f.6 behavior). Both layers share the SAME `observed_at`
        so `decide_stall`'s observed-span math is consistent.
        """
        observed_at = self.clock()
        wall_clock = _WallClockEventProbe(plan=plan, runner=runner, run_id=run_id)
        if self.heartbeat_path is None:
            return wall_clock.sample(observed_at=observed_at)
        heartbeat = HeartbeatLivenessProbe(
            sink=HeartbeatSink(path=self.heartbeat_path),
            keys=heartbeat_lookup_keys(work_item_id=plan.work_item_id, run_id=run_id),
        )
        layered = LayeredLivenessProbe(primary=heartbeat, fallback=wall_clock)
        return layered.sample(observed_at=observed_at)

    def _cancel(
        self,
        *,
        plan: DispatchPlan,
        runner: CommandRunner,
        journal: JournalWriter,
        run_id: str,
    ) -> None:
        rm = runner.run(
            argv=fabro_rm_argv(plan=plan, run_id=run_id),
            cwd=plan.repo,
            timeout_seconds=_FABRO_RM_TIMEOUT_SECONDS,
        )
        journal.append(
            record={
                "work_item_id": plan.work_item_id,
                "stage": "watchdog-stall-cancel",
                "run_id": run_id,
                "rm_exit_code": rm.exit_code,
            }
        )


@dataclass(frozen=True, kw_only=True)
class JournalFile:
    """Append-only JSONL journal; thread-safe across parallel dispatches."""

    path: Path
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def append(self, *, record: dict[str, object]) -> None:
        stamped: dict[str, object] = {"at": utc_now_iso(), **record}
        line = json.dumps(stamped, sort_keys=True) + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                _ = handle.write(line)


def utc_now_iso() -> str:
    """Current UTC time in ISO-8601 with seconds precision."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _decode(*, raw: object) -> str:
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        return raw
    return ""
