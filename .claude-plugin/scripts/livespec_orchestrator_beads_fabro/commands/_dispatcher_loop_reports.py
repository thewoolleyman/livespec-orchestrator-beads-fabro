"""What a finished dispatch tells the outside world about the run that just ended.

Split out of `_dispatcher_loop` because it is a different concern from driving a dispatch:
everything here runs AFTER the run is terminal and none of it can change the outcome. The
loop assembles and launches; this reports.

TWO AUDIENCES, ONE ORDER. The credential authority is told how ITS credential fared, and
the review-gate span emitter is told what the run's own events showed. The credential
report goes first because an `authentication` classification makes the credential suspect
immediately, and the sooner that lands the smaller the window in which the next dispatch
can be handed the same dead account; span emission has no such urgency.

NEITHER REPORT MAY TURN A COMPLETED DISPATCH INTO A FAILURE. The credential report's
refusal is returned as data by the manager client and deliberately DISCARDED here — the
run's outcome was decided before either call, and a credential authority that cannot be
reached is not a property of the work. That is why this function returns nothing.

THE CREDENTIAL RECEIPTS ARE A LIST AND NOT AN OPTIONAL. An empty list is what a dispatch
that refused BEFORE provisioning leaves behind, and it is the shape the materializer's
receipt sink produces naturally. Reading it here rather than at the sink keeps the sink a
plain `list.append` the caller can hand over without a wrapper.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_failure_report import (
    report_run_failure,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_manager import (
    CredentialManagerClient,
    CredentialReceipt,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_id_journal import (
    DispatchJournalIdentity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    GithubTokenEnvRunner,
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import spans_path
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan_build import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_review_gate import (
    ReviewGateEmission,
    emit_review_gate_from_fabro_events,
)

__all__: list[str] = [
    "emit_post_run_reports",
]


def emit_post_run_reports(  # noqa: PLR0913 — kw-only post-run reporter; each argument names one independent input the two reports need, and bundling them would invent a record that exists only to be unpacked here.
    *,
    args: argparse.Namespace,
    repo: Path,
    plan: DispatchPlan,
    journal: JournalFile,
    outcome: DispatchOutcome,
    identity: DispatchJournalIdentity,
    work_item_id: str,
    token_supplier: Callable[[], str],
    credential_manager: CredentialManagerClient,
    receipts: list[CredentialReceipt],
    now_epoch: float,
) -> None:
    """Report the finished run to the credential authority and the review-gate emitter."""
    # The report carries the run and record identities plus one classification and NO
    # credential bytes. A refusal is surfaced by the manager client as data and dropped
    # here: the dispatch has already finished, and a report it could not deliver is not
    # a property of the work.
    _ = report_run_failure(
        manager=credential_manager,
        receipt=receipts[0] if receipts else None,
        consumer_run_id=identity.dispatch_id,
        outcome=outcome,
        occurred_at_epoch=now_epoch,
    )
    emit_review_gate_from_fabro_events(
        emission=ReviewGateEmission(
            plan=plan,
            runner=GithubTokenEnvRunner(inner=ShellCommandRunner(), token=token_supplier),
            journal=journal,
            spans_path=spans_path(args=args, repo=repo),
            work_item_id=work_item_id,
            dispatch_id=identity.dispatch_id,
            run_id=outcome.fabro_run_id,
            dispatch_factory=identity.dispatch_factory,
        )
    )
