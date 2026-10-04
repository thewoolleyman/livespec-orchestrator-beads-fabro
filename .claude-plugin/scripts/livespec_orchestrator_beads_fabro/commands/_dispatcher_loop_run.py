"""Fabro run invocation for the dispatcher loop."""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from time import sleep as _real_sleep

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
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_credential_providers import (
    ProofCredentialLease,
    revoke_proof_credential_lease,
)

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
    # This dispatch's minted proof credentials. Revoked with the overlay when the
    # run returns, so the credential's two lifetimes — the local file holding its
    # value and the grant living at the provider — end at the same moment. `None`
    # is the ordinary case: a repository that declared none, or only names no
    # provider manages, leases nothing.
    proof_credential_lease: ProofCredentialLease | None = None


def run_dispatch_with_watchdog(
    *,
    context: DispatchRunContext,
    run_dispatch_func: Callable[..., DispatchOutcome],
    fabro_launcher_type: Callable[..., WatchedFabroLauncher],
) -> tuple[float, DispatchOutcome]:
    started_at = time.monotonic()
    runner = GithubTokenEnvRunner(inner=ShellCommandRunner(), token=context.token_supplier)
    with ExitStack() as stack:
        _ = stack.callback(lambda: context.overlay_file.unlink(missing_ok=True))
        _ = stack.callback(lambda: remove_workflow_payload(payload_dir=context.payload_dir))
        # Registered LAST, so the stack unwinds it FIRST: the provider-side grant
        # is withdrawn the moment the run returns, before the local overlay and
        # payload are swept. The callback is unconditional and the `None` case is
        # handled inside, because a teardown that had to test the lease first
        # would be a teardown that could be skipped — and the runs most likely to
        # skip it are the ones that failed partway through, which are exactly the
        # ones leaving a live credential behind.
        _ = stack.callback(
            lambda: revoke_proof_credential_lease(
                lease=context.proof_credential_lease,
                journal=context.journal,
                work_item_id=context.plan.work_item_id,
            )
        )
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
        )
    return started_at, outcome
