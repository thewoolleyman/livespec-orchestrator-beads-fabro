"""Fabro run invocation for the dispatcher loop."""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from time import sleep as _real_sleep

from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration import fix_loop_count
from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration_emit import (
    read_journal_records_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_gate import (
    pre_merge_runtime_gate,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    DispatchOutcome,
    PollPolicy,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    GithubTokenEnvRunner,
    JournalFile,
    ShellCommandRunner,
    WatchedFabroLauncher,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import heartbeat_path
from livespec_orchestrator_beads_fabro.commands._dispatcher_payload import (
    remove_workflow_payload,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_credential_lease import (
    revoke_proof_credentials,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "DispatchRunContext",
    "run_dispatch_with_watchdog",
]


@dataclass(frozen=True, kw_only=True)
class DispatchRunContext:
    args: argparse.Namespace
    repo: Path
    plan: DispatchPlan
    journal: JournalFile
    overlay_file: Path
    # The per-dispatch workflow payload (the rendered graph plus its
    # prompts). Torn down with the overlay when the run returns, so a
    # dispatch never leaves a stale rendered graph behind for the next one.
    payload_dir: Path | None = None
    token_supplier: Callable[[], str]
    # The dispatch id this run was minted under, carried through so the
    # watchdog's heartbeat probe can look beats up by the SAME id
    # `cc_otel_overlay_env` projected into the sandbox.
    dispatch_id: str | None = None
    # The DISPATCHED work-item (S6 / bd-ib-z2y4ca), carried so the pre-merge
    # runtime-convergence gate can read the criteria THIS dispatch was launched
    # with. It is the item rather than a pre-computed count because the
    # sanctioned parser is the one authority on that number, and a count
    # computed here would be a second reading of the same criteria.
    #
    # REQUIRED rather than defaulting to None, which is the whole point: an
    # optional item would let a context be built that silently skips the runtime
    # gate, and a gate that is skipped reads exactly like a gate that passed.
    # Required, the only way to reach a dispatch is to say which item it is for.
    item: WorkItem


def _pre_merge_gate_for(*, context: DispatchRunContext) -> Callable[..., DispatchOutcome | None]:
    """Bind this dispatch's pre-merge runtime gate to the item it was launched for."""
    return pre_merge_runtime_gate(
        repo=context.repo,
        item=context.item,
        dispatch_id=context.dispatch_id,
        fix_loop_count=fix_loop_count(
            records=read_journal_records_for(args=context.args, repo=context.repo),
            work_item_id=context.item.id,
        ),
        fix_loop_cap=context.plan.review_fix_visit_cap,
        journal=context.journal,
        runner=ShellCommandRunner(),
    )


def run_dispatch_with_watchdog(
    *,
    context: DispatchRunContext,
    run_dispatch_func: Callable[..., DispatchOutcome],
    fabro_launcher_type: Callable[..., WatchedFabroLauncher],
) -> tuple[float, DispatchOutcome]:
    started_at = time.monotonic()
    runner = GithubTokenEnvRunner(inner=ShellCommandRunner(), token=context.token_supplier)
    with ExitStack() as stack:
        # Registered FIRST so it runs LAST: a provider-minted proof credential is
        # revoked once the run has ended AND the overlay that carried it is gone.
        # Addressed by this dispatch's own id, which is the scope the mint used,
        # so no state has to survive the overlay materializer to reach here.
        _ = stack.callback(
            lambda: revoke_proof_credentials(
                repo=context.repo,
                scope=context.dispatch_id,
                runner=ShellCommandRunner(),
                journal=context.journal,
            )
        )
        _ = stack.callback(lambda: context.overlay_file.unlink(missing_ok=True))
        _ = stack.callback(lambda: remove_workflow_payload(payload_dir=context.payload_dir))
        outcome = run_dispatch_func(
            plan=context.plan,
            # Pillar 1 (first-class remint): the decorator re-resolves
            # GH_TOKEN from the caching provider before EVERY engine
            # subprocess, so the ~76-min merge-poll and the post-merge
            # git/janitor legs never ride an expired once-at-start token.
            runner=runner,
            journal=context.journal,
            sleep=_real_sleep,
            poll=PollPolicy(
                attempts=context.args.poll_attempts,
                interval_seconds=context.args.poll_interval_seconds,
            ),
            # The progress watchdog (work-item livespec-impl-beads-oyg):
            # runs `fabro run` while watching liveness and `fabro rm -f`-es
            # a sustained-no-progress stall (the 7us.6 silent-deadlock
            # backstop) — a distinct `stalled-no-progress` outcome that
            # h1p's `notify_terminal` alarms on. 29f.6 layers the
            # metrics-HEARTBEAT (the journal-sibling file the live receiver
            # writes) as the deferred-PRIMARY liveness signal over the
            # coarse wall-clock backstop; an absent/stale/malformed
            # heartbeat degrades to the wall-clock layer, never to NO
            # detection. The dispatch id rides along because the sink keys
            # every beat by it (`cc_otel_overlay_env` projects no run id),
            # so a probe without it can never match a beat.
            fabro_launcher=fabro_launcher_type(
                heartbeat_path=heartbeat_path(args=context.args, repo=context.repo),
                dispatch_id=context.dispatch_id,
            ),
            # The PRE-MERGE runtime-convergence gate (S6 / bd-ib-z2y4ca). It is
            # bound here, where the dispatched item, the dispatch id and the
            # rendered fix-loop cap are all in hand, and handed to the engine as
            # a callable so the engine never imports the gate module.
            #
            # The fix-loop count is this dispatch's own, derived from the
            # journal the engine has already been appending to — the same
            # poll/retry signal `fix_loop_count` reads for calibration. The
            # graph's visit counter lives inside the sandbox and no terminal
            # carries it, which is the limitation `_dispatcher_non_convergence_cap`
            # records; this is the host-observable stand-in, and naming it in the
            # journaled record is what keeps the substitution visible.
            pre_merge_gate=_pre_merge_gate_for(context=context),
        )
    return started_at, outcome
