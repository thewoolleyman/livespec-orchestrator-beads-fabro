"""Typed seams and results shared by Dispatcher execution and reconciliation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance import (
    BaseAdvancedAfterArming,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan

__all__: list[str] = [
    "CommandResult",
    "CommandRunner",
    "DispatchOutcome",
    "FabroLauncher",
    "FabroRunResult",
    "JournalWriter",
    "PollPolicy",
    "SleepFn",
]


@dataclass(frozen=True, kw_only=True)
class CommandResult:
    """Outcome of one subprocess invocation across the runner seam."""

    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True, kw_only=True)
class FabroRunResult:
    """Outcome of the watched `fabro run` foreground stage.

    `command` preserves the raw `fabro run` client result. After a stream
    disconnect, the bound run's inspected terminal state governs routing;
    the client exit code alone does not establish a run failure.
    `stalled_run_id` is set ONLY when the coarse wall-clock watchdog
    confirmed a sustained-no-progress stall and `fabro rm -f`-ed the run
    (the 7us.6 hang class) — the engine then short-circuits to a distinct
    `stalled-no-progress` outcome. None means the watchdog never tripped
    (the normal path, including a clean probe-failure-but-healthy run:
    fail-safe, a flaky probe is NOT a stall).
    `abandoned_run_id` is set when the launcher reaped a queued/running run
    whose work-item is already no longer dispatchable.
    """

    command: CommandResult
    run_id: str | None = None
    stalled_run_id: str | None = None
    abandoned_run_id: str | None = None
    abandoned_item_status: str | None = None


@dataclass(frozen=True, kw_only=True)
class DispatchOutcome:
    """Terminal report for one dispatched work-item.

    `status` is one of `green` / `failed` / `blocked` (blocked = the run's
    `needs_human` terminal fired and the item rests at blocked / needs-human
    in the ledger; surfaced to a human, never treated as a failure, never
    auto-resolved). A `run-unobservable` result reports exhausted visibility
    retries while the bound run may still be alive; its active claim is retained.

    `step` / `missing_integration_point` / `remedy` are the STRUCTURED half
    of a degraded post-merge outcome: the stable step identifier from the
    closed vocabulary, the required integration point the governed
    repository did not provide, and how to provide it. They are fields
    rather than prose inside `detail` because the NEXT dispatch's
    pre-dispatch gate has to match on them -- free prose describing the
    same failure cannot be matched against a waiver entry, nor against the
    re-verification that clears the refusal. They are None on every outcome
    that is not a degraded step outcome.

    `dead_implementer_condition` is the governing condition of a
    dead-implementer truncation, carried as a typed field rather than left for
    each consumer to re-match against `detail` prose — the same seam rationale
    as `provider_usage_limit`. It is None on every run whose implementer
    changed the worktree, which is every ordinary run.

    `provider_usage_limit_provider` names the vendor that refused, read off this
    run's own failure. It is what an exhaustion record is labelled with, and it
    is carried rather than assumed because the detection behind
    `provider_usage_limit` fires for either vendor.

    `verdict` is the POST-MERGE ACCEPTANCE verdict, and it is None on every
    outcome that never reached the acceptance valve. The parking-verdict clause of
    `SPECIFICATION/contracts.md` requires the dispatch result to report it beside
    `stage` and `status`, which is why it rides here rather than being left for a
    consumer to recover from the journal: the journal lives in the `tmp/` tree of
    whichever host ran the dispatch, and the result is what an operator and an
    exit code see.

    `needs_human_kind` is `_fabro_causal_stage`'s verdict about WHICH of the
    three needs-human endings this was, carried as a typed field for the same
    seam reason as `dead_implementer_condition` above. The escalation that has
    to route its own operator guidance runs long after the terminal mapper, and
    the only other way to reach the verdict there is to re-match the rendered
    `detail` prose — which is precisely what this field set exists to stop every
    consumer from doing. It is None on every outcome built by a caller with no
    verdict to report, which is every non-Fabro blocked path, and that absence
    routes to the wording those callers always had rather than to one of the
    three attributed arms.

    `needs_human_stages` is the stage or stages that verdict attributed the
    ending to, and it is NOT `stage` above: `stage` is the DISPATCHER's own
    phase, which is `fabro-run` for every Fabro terminal, while this is the
    failed node inside the run — `pr`, `implement`. Both are needed and neither
    substitutes for the other. It is None rather than empty for an ending with
    no attribution, so the same null-drop that hides the verdict hides it too;
    an empty list would assert that the verdict found no stages, which is a
    different claim from the verdict never having been taken at all.

    `needs_human_reason` is the REASON the terminal node itself printed, and it
    is the other half of `needs_human_stages` rather than a duplicate of it: the
    stage comes from the ENGINE's outcome map and the reason from the SANDBOX,
    so neither can supply the other and an operator triaging the ending reads
    both. It rides here because the durable ledger record is appended long after
    the run's output has scrolled away — it has the outcome and not the text —
    and because a second parse of that text would be a second implementation of
    the one rule `needs_human_terminal_reason` owns. It is None for a terminal
    that printed no reason, which is a different fact from a terminal that
    printed an empty one; both arrive here as None because the distinction is
    not one any reader of this field acts on.
    """

    work_item_id: str
    status: str
    stage: str
    verdict: str | None = None
    pr_number: int | None
    merge_sha: str | None
    detail: str
    step: str | None = None
    missing_integration_point: str | None = None
    remedy: str | None = None
    fabro_run_id: str | None = None
    fabro_failure_cause: str | None = None
    fabro_failure_category: str | None = None
    fabro_failure_signature: str | None = None
    provider_usage_limit: bool = False
    provider_usage_limit_provider: str | None = None
    dead_implementer_condition: str | None = None
    needs_human_kind: str | None = None
    needs_human_stages: tuple[str, ...] | None = None
    needs_human_reason: str | None = None
    base_advanced: BaseAdvancedAfterArming | None = None


SleepFn = Callable[[float], None]


class JournalWriter(Protocol):
    """Append-one-record seam for the structured iteration journal."""

    def append(self, *, record: dict[str, object]) -> None:
        """Persist one journal record."""
        ...


class CommandRunner(Protocol):
    """The single subprocess seam the engine executes argvs through."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        """Run argv in cwd, returning the completed result (never raising
        for non-zero exits; timeouts surface as non-zero results)."""
        ...


@dataclass(frozen=True, kw_only=True)
class PollPolicy:
    """Bounded merge-confirmation polling (an unbounded loop is a defect)."""

    attempts: int
    interval_seconds: float


class FabroLauncher(Protocol):
    """Seam that runs `fabro run` to completion with a progress watchdog.

    Production is `_dispatcher_io.WatchedFabroLauncher`: it runs `fabro
    run` while the coarse wall-clock watchdog samples the event stream and
    `fabro rm -f`-es a confirmed stall. `SynchronousFabroLauncher` is the
    no-watchdog default (a plain `runner.run`, used where the watchdog is
    not wired and by the legacy hermetic engine tests). The DEFERRED 29f
    metrics-heartbeat primary becomes a third launcher feeding the same
    `decide_stall` — see `_dispatcher_watchdog`.
    """

    def launch(
        self,
        *,
        plan: DispatchPlan,
        runner: CommandRunner,
        journal: JournalWriter,
    ) -> FabroRunResult:
        """Run `fabro run` for `plan`, watching liveness; return the result."""
        ...
