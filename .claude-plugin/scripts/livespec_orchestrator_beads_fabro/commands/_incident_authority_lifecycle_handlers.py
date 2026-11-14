"""The per-verb handlers of the incident-authority lifecycle actions.

`SPECIFICATION/contracts.md` section "Expedited incident lifecycle". Each handler
is a thin adapter over a released library function; `_incident_authority_lifecycle`
documents the verbs and owns the dispatch (`run_lifecycle_action`). This module holds
the payload arguments each verb alone requires, the handler for each verb, and the
`LIFECYCLE_HANDLERS` map from verb to handler.
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro.commands._incident_authority_binding import (
    bind_repayment_acceptance,
)
from livespec_orchestrator_beads_fabro.commands._incident_authority_completion import (
    complete_action,
    observe_master_run,
)
from livespec_orchestrator_beads_fabro.commands._incident_authority_decode import (
    decode_attributed_attempt,
    decode_record,
    invalid_payload,
)
from livespec_orchestrator_beads_fabro.commands._incident_authority_drill_close import (
    run_drill_close,
)
from livespec_orchestrator_beads_fabro.commands._incident_authority_merge import record_merge
from livespec_orchestrator_beads_fabro.commands._incident_authority_unmerged import (
    correct_unmerged_action,
)
from livespec_orchestrator_beads_fabro.commands._incident_rollback_conflict import (
    RollbackConflict,
    RollbackResolution,
    record_rollback_conflict,
    resolve_rollback_conflict,
)
from livespec_orchestrator_beads_fabro.incident_completion import IncidentCompletion
from livespec_orchestrator_beads_fabro.incident_drill_close import DrillClose
from livespec_orchestrator_beads_fabro.incident_normal_repayment import (
    RepaymentEntry,
    advance_repayment,
    enter_repayment,
)
from livespec_orchestrator_beads_fabro.incident_regression_recovery import (
    Correction,
    Finding,
    RecoveryEntry,
    RevertReceipt,
    enter_corrected_attempt,
    record_deferred_finding,
    record_revert_receipt,
    reopen_for_regression,
)
from livespec_orchestrator_beads_fabro.incident_repayment_recovery import (
    recover_repayment_phases,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandRunner

__all__: list[str] = [
    "LIFECYCLE_HANDLERS",
    "LIFECYCLE_PAYLOADS",
    "LifecycleReply",
]

# Each lifecycle action and the payload arguments it alone requires.
LIFECYCLE_PAYLOADS: dict[str, tuple[str, ...]] = {
    "record-merge": (),
    "enter-repayment": ("master_run", "target_ref"),
    "advance-repayment": ("to_phase",),
    "recover-repayment-phases": (),
    "bind-repayment-acceptance": ("pr",),
    "reopen-regression": ("attributed_json", "finding_json", "principal"),
    "record-deferred-finding": ("finding_json",),
    "record-revert-receipt": ("revert_receipt_json",),
    "record-rollback-conflict": ("rollback_conflict_json",),
    "resolve-rollback-conflict": ("rollback_resolution_json",),
    "correct-attempt": ("correction_json", "target_ref"),
    "correct-unmerged-attempt": ("correction_json", "target_ref", "failed_run"),
    "complete-incident": ("master_run", "completion_json"),
    "drill-close": (),
}
_PR_NUMBER = re.compile(r"[1-9][0-9]*")

LifecycleReply = RepaymentEntry | RecoveryEntry | IncidentCompletion | DrillClose | AuthorityRefusal
_Handler = Callable[..., LifecycleReply]


def _record_merge(
    *,
    args: argparse.Namespace,
    client: BeadsClient,
    reading: IncidentReading,
    runner: CommandRunner,
) -> LifecycleReply:
    return record_merge(
        client=client, reading=reading, runner=runner, repo=args.repo, repository=args.repository
    )


def _enter(
    *,
    args: argparse.Namespace,
    client: BeadsClient,
    reading: IncidentReading,
    runner: CommandRunner,
) -> LifecycleReply:
    master_ci = observe_master_run(
        runner=runner, repo=args.repo, repository=args.repository, run_id=args.master_run
    )
    if isinstance(master_ci, AuthorityRefusal):
        return master_ci
    return enter_repayment(
        client=client, reading=reading, master_ci=master_ci, target_ref=args.target_ref
    )


def _advance(
    *, args: argparse.Namespace, client: BeadsClient, reading: IncidentReading, **_: object
) -> LifecycleReply:
    return advance_repayment(
        client=client,
        reading=reading,
        phase=args.to_phase,
        admission_complete=args.admission_complete,
    )


def _recover(*, client: BeadsClient, reading: IncidentReading, **_: object) -> LifecycleReply:
    return recover_repayment_phases(client=client, reading=reading)


def _bind(
    *,
    args: argparse.Namespace,
    client: BeadsClient,
    reading: IncidentReading,
    runner: CommandRunner,
) -> LifecycleReply:
    if _PR_NUMBER.fullmatch(args.pr) is None:
        return invalid_payload(flag="--pr", detail="not a positive pull request number")
    return bind_repayment_acceptance(
        client=client,
        reading=reading,
        runner=runner,
        repo=args.repo,
        repository=args.repository,
        pr_number=int(args.pr),
    )


def _reopen(
    *, args: argparse.Namespace, client: BeadsClient, reading: IncidentReading, **_: object
) -> LifecycleReply:
    attributed = decode_attributed_attempt(text=args.attributed_json)
    if isinstance(attributed, AuthorityRefusal):
        return attributed
    finding = decode_record(text=args.finding_json, shape=Finding, flag="--finding-json")
    if isinstance(finding, AuthorityRefusal):
        return finding
    return reopen_for_regression(
        client=client,
        reading=reading,
        attributed=attributed,
        finding=finding,
        owner=args.principal,
    )


def _defer(
    *, args: argparse.Namespace, client: BeadsClient, reading: IncidentReading, **_: object
) -> LifecycleReply:
    finding = decode_record(text=args.finding_json, shape=Finding, flag="--finding-json")
    if isinstance(finding, AuthorityRefusal):
        return finding
    return record_deferred_finding(client=client, reading=reading, finding=finding)


def _revert(
    *, args: argparse.Namespace, client: BeadsClient, reading: IncidentReading, **_: object
) -> LifecycleReply:
    receipt = decode_record(
        text=args.revert_receipt_json, shape=RevertReceipt, flag="--revert-receipt-json"
    )
    if isinstance(receipt, AuthorityRefusal):
        return receipt
    return record_revert_receipt(client=client, reading=reading, receipt=receipt)


def _rollback_conflict(
    *, args: argparse.Namespace, client: BeadsClient, reading: IncidentReading, **_: object
) -> LifecycleReply:
    conflict = decode_record(
        text=args.rollback_conflict_json,
        shape=RollbackConflict,
        flag="--rollback-conflict-json",
    )
    if isinstance(conflict, AuthorityRefusal):
        return conflict
    return record_rollback_conflict(client=client, reading=reading, conflict=conflict)


def _resolve_rollback_conflict(
    *, args: argparse.Namespace, client: BeadsClient, reading: IncidentReading, **_: object
) -> LifecycleReply:
    resolution = decode_record(
        text=args.rollback_resolution_json,
        shape=RollbackResolution,
        flag="--rollback-resolution-json",
    )
    if isinstance(resolution, AuthorityRefusal):
        return resolution
    return resolve_rollback_conflict(client=client, reading=reading, resolution=resolution)


def _correct(
    *, args: argparse.Namespace, client: BeadsClient, reading: IncidentReading, **_: object
) -> LifecycleReply:
    correction = decode_record(
        text=args.correction_json, shape=Correction, flag="--correction-json"
    )
    if isinstance(correction, AuthorityRefusal):
        return correction
    return enter_corrected_attempt(
        client=client, reading=reading, correction=correction, target_ref=args.target_ref
    )


LIFECYCLE_HANDLERS: dict[str, _Handler] = {
    "record-merge": _record_merge,
    "enter-repayment": _enter,
    "advance-repayment": _advance,
    "recover-repayment-phases": _recover,
    "bind-repayment-acceptance": _bind,
    "reopen-regression": _reopen,
    "record-deferred-finding": _defer,
    "record-revert-receipt": _revert,
    "record-rollback-conflict": _rollback_conflict,
    "resolve-rollback-conflict": _resolve_rollback_conflict,
    "correct-attempt": _correct,
    "correct-unmerged-attempt": correct_unmerged_action,
    "complete-incident": complete_action,
    "drill-close": run_drill_close,
}
