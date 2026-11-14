"""The incident-authority lifecycle actions: repayment, regression reopen and correction.

`SPECIFICATION/contracts.md` section "Expedited incident lifecycle". Each action
is a thin adapter over a released library function, run against the exact
attempt the shared `--item`, `--attempt`, `--phase`, `--operation`,
`--generation` and `--owner` identity names:

- `record-merge` reads the merged repair PR the chain names and its landed
  history from the forge and git and records `master-observation`
  (`record_merge`).
- `enter-repayment` observes the named master run on the forge and calls
  `enter_repayment`, so the run's own completion and conclusion are the gate.
- `advance-repayment` calls `advance_repayment` for the named next phase.
- `bind-repayment-acceptance` reads the merged repayment PR and its landed
  history from the forge and git and records the `pr-bound`
  `repayment-acceptance` successor (`bind_repayment_acceptance`), the binding
  `advance-repayment` cannot make.
- `reopen-regression` calls `reopen_for_regression`.
- `record-deferred-finding` calls `record_deferred_finding`.
- `record-revert-receipt` calls `record_revert_receipt`, the step that makes a
  corrected attempt eligible.
- `correct-attempt` calls `enter_corrected_attempt`.
- `correct-unmerged-attempt` reads the bound repair PR and the named failed run
  from the forge and calls `enter_unmerged_correction`
  (`correct_unmerged_action`): the corrected attempt for a repair whose
  expedited PR closed unmerged after a retained fast check failed on its head.
- `complete-incident` observes the bound repayment PR and the named master run
  on the forge, scans that run head's tree for the incident marker, takes the
  rest as one canonical operator attestation and calls `complete_incident`; a
  completion that records nothing is the refusal `incident-completion-outstanding`
  naming every obligation.

Every JSON payload must be the canonical encoding (sorted keys, compact
separators) of exactly its record's fields; anything else is the named refusal
`incident-action-invalid-payload` and nothing is written.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._incident_authority_payload import attempt_record
from livespec_orchestrator_beads_fabro._incident_authority_types import IncidentReading
from livespec_orchestrator_beads_fabro.commands._incident_authority_completion import (
    MASTER_CI_UNOBSERVABLE,
    observe_master_run,
)
from livespec_orchestrator_beads_fabro.commands._incident_authority_lifecycle_handlers import (
    LIFECYCLE_HANDLERS,
    LIFECYCLE_PAYLOADS,
    LifecycleReply,
)
from livespec_orchestrator_beads_fabro.incident_completion import IncidentCompletion
from livespec_orchestrator_beads_fabro.incident_drill_close import DrillClose
from livespec_orchestrator_beads_fabro.incident_normal_repayment import RepaymentEntry
from livespec_orchestrator_beads_fabro.incident_regression_recovery import RecoveryEntry

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandRunner

__all__: list[str] = [
    "LIFECYCLE_PAYLOADS",
    "MASTER_CI_UNOBSERVABLE",
    "LifecycleReply",
    "lifecycle_body",
    "observe_master_run",
    "run_lifecycle_action",
]


def run_lifecycle_action(
    *,
    args: argparse.Namespace,
    client: BeadsClient,
    reading: IncidentReading,
    runner: CommandRunner,
) -> LifecycleReply:
    """Run the one lifecycle action `args.action` names against the observed attempt."""
    handler = LIFECYCLE_HANDLERS[args.action]
    return handler(args=args, client=client, reading=reading, runner=runner)


def lifecycle_body(
    *,
    result: RepaymentEntry | RecoveryEntry | IncidentCompletion | DrillClose,
    body: dict[str, Any],
) -> None:
    """Serialize the recorded attempt with its carrier exactly as the chain retains it.

    A completion that recovered an earlier `closed` carries no reading.
    """
    if result.reading is None:
        return
    reading = cast("dict[str, Any]", body["reading"])
    reading["attempt"] = attempt_record(attempt=result.reading.attempt)
