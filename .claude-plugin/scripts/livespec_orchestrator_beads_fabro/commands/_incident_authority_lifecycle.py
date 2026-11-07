"""The incident-authority lifecycle actions: repayment, regression reopen and correction.

`SPECIFICATION/contracts.md` section "Expedited incident lifecycle". Each action
is a thin adapter over a released library function, run against the exact
attempt the shared `--item`, `--attempt`, `--phase`, `--operation`,
`--generation` and `--owner` identity names:

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
import json
import re
from collections.abc import Callable
from dataclasses import fields
from typing import TYPE_CHECKING, Any, TypeVar, cast

from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    attempt_record,
    decode_attempt,
)
from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro.commands._incident_authority_binding import (
    bind_repayment_acceptance,
)
from livespec_orchestrator_beads_fabro.commands._incident_authority_completion import (
    ATTESTATION_FIELDS,
    MASTER_CI_UNOBSERVABLE,
    CompletionRequest,
    complete_from_forge,
    decode_attestation,
    observe_master_run,
)
from livespec_orchestrator_beads_fabro.effects import parse_json
from livespec_orchestrator_beads_fabro.incident_completion import IncidentCompletion
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

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandRunner

__all__: list[str] = [
    "INVALID_PAYLOAD",
    "LIFECYCLE_PAYLOADS",
    "MASTER_CI_UNOBSERVABLE",
    "LifecycleReply",
    "lifecycle_body",
    "observe_master_run",
    "run_lifecycle_action",
]

# Each lifecycle action and the payload arguments it alone requires.
LIFECYCLE_PAYLOADS: dict[str, tuple[str, ...]] = {
    "enter-repayment": ("master_run", "target_ref"),
    "advance-repayment": ("to_phase",),
    "bind-repayment-acceptance": ("pr",),
    "reopen-regression": ("attributed_json", "finding_json", "principal"),
    "record-deferred-finding": ("finding_json",),
    "record-revert-receipt": ("revert_receipt_json",),
    "correct-attempt": ("correction_json", "target_ref"),
    "complete-incident": ("master_run", "completion_json"),
}
INVALID_PAYLOAD = "incident-action-invalid-payload"
_SCALARS: dict[str, type] = {"str": str, "bool": bool}
_T = TypeVar("_T")
_PR_NUMBER = re.compile(r"[1-9][0-9]*")

LifecycleReply = RepaymentEntry | RecoveryEntry | IncidentCompletion | AuthorityRefusal
_Handler = Callable[..., LifecycleReply]


def _invalid(*, flag: str, detail: str) -> AuthorityRefusal:
    return AuthorityRefusal(code=INVALID_PAYLOAD, detail=f"{flag}: {detail}")


def _canonical(*, value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _record(*, text: str, shape: type[_T], flag: str) -> _T | AuthorityRefusal:
    """Decode exactly one record of `shape` from its canonical JSON, or refuse."""
    raw = parse_json(text=text)
    names = {field.name: _SCALARS.get(str(field.type)) for field in fields(cast("Any", shape))}
    value = cast("dict[str, object]", raw) if isinstance(raw, dict) else None
    if value is None or text != _canonical(value=value):
        return _invalid(flag=flag, detail="not one canonical JSON object")
    if set(value) != set(names) or any(type(value[k]) is not t for k, t in names.items()):
        return _invalid(flag=flag, detail=f"needs exactly {sorted(names)} with their types")
    return shape(**value)


def _attempt(*, text: str) -> IncidentAttempt | AuthorityRefusal:
    """The attributed attempt in its canonical record bytes; the library re-reads the chain."""
    raw = parse_json(text=text)
    attempt = decode_attempt(value=raw)
    if attempt is None or text != _canonical(value=attempt_record(attempt=attempt)):
        return _invalid(flag="--attributed-json", detail="not one canonical attempt record")
    return attempt


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


def _bind(
    *,
    args: argparse.Namespace,
    client: BeadsClient,
    reading: IncidentReading,
    runner: CommandRunner,
) -> LifecycleReply:
    if _PR_NUMBER.fullmatch(args.pr) is None:
        return _invalid(flag="--pr", detail="not a positive pull request number")
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
    attributed = _attempt(text=args.attributed_json)
    if isinstance(attributed, AuthorityRefusal):
        return attributed
    finding = _record(text=args.finding_json, shape=Finding, flag="--finding-json")
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
    finding = _record(text=args.finding_json, shape=Finding, flag="--finding-json")
    if isinstance(finding, AuthorityRefusal):
        return finding
    return record_deferred_finding(client=client, reading=reading, finding=finding)


def _revert(
    *, args: argparse.Namespace, client: BeadsClient, reading: IncidentReading, **_: object
) -> LifecycleReply:
    receipt = _record(
        text=args.revert_receipt_json, shape=RevertReceipt, flag="--revert-receipt-json"
    )
    if isinstance(receipt, AuthorityRefusal):
        return receipt
    return record_revert_receipt(client=client, reading=reading, receipt=receipt)


def _correct(
    *, args: argparse.Namespace, client: BeadsClient, reading: IncidentReading, **_: object
) -> LifecycleReply:
    correction = _record(text=args.correction_json, shape=Correction, flag="--correction-json")
    if isinstance(correction, AuthorityRefusal):
        return correction
    return enter_corrected_attempt(
        client=client, reading=reading, correction=correction, target_ref=args.target_ref
    )


def _complete(
    *,
    args: argparse.Namespace,
    client: BeadsClient,
    reading: IncidentReading,
    runner: CommandRunner,
) -> LifecycleReply:
    """Decode the attestation, then gather the forge and tree evidence and complete."""
    attestation = decode_attestation(text=args.completion_json)
    if attestation is None:
        detail = f"needs exactly {list(ATTESTATION_FIELDS)} as one canonical JSON object"
        return _invalid(flag="--completion-json", detail=detail)
    return complete_from_forge(
        client=client,
        reading=reading,
        runner=runner,
        repo=args.repo,
        repository=args.repository,
        completion=CompletionRequest(run_id=args.master_run, attestation=attestation),
    )


_HANDLERS: dict[str, _Handler] = {
    "enter-repayment": _enter,
    "advance-repayment": _advance,
    "bind-repayment-acceptance": _bind,
    "reopen-regression": _reopen,
    "record-deferred-finding": _defer,
    "record-revert-receipt": _revert,
    "correct-attempt": _correct,
    "complete-incident": _complete,
}


def run_lifecycle_action(
    *,
    args: argparse.Namespace,
    client: BeadsClient,
    reading: IncidentReading,
    runner: CommandRunner,
) -> LifecycleReply:
    """Run the one lifecycle action `args.action` names against the observed attempt."""
    handler = _HANDLERS[args.action]
    return handler(args=args, client=client, reading=reading, runner=runner)


def lifecycle_body(
    *, result: RepaymentEntry | RecoveryEntry | IncidentCompletion, body: dict[str, Any]
) -> None:
    """Serialize the recorded attempt with its carrier exactly as the chain retains it.

    A completion that recovered an earlier `closed` carries no reading.
    """
    if result.reading is None:
        return
    reading = cast("dict[str, Any]", body["reading"])
    reading["attempt"] = attempt_record(attempt=result.reading.attempt)
