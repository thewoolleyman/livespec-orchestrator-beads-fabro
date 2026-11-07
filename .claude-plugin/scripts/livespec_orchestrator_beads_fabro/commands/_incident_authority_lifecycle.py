"""The incident-authority lifecycle actions: repayment, regression reopen and correction.

`SPECIFICATION/contracts.md` section "Expedited incident lifecycle". Each action
is a thin adapter over a released library function, run against the exact
attempt the shared `--item`, `--attempt`, `--phase`, `--operation`,
`--generation` and `--owner` identity names:

- `enter-repayment` observes the named master run on the forge and calls
  `enter_repayment`, so the run's own completion and conclusion are the gate.
- `advance-repayment` calls `advance_repayment` for the named next phase.
- `reopen-regression` calls `reopen_for_regression`.
- `record-deferred-finding` calls `record_deferred_finding`.
- `record-revert-receipt` calls `record_revert_receipt`, the step that makes a
  corrected attempt eligible.
- `correct-attempt` calls `enter_corrected_attempt`.

Every JSON payload must be the canonical encoding (sorted keys, compact
separators) of exactly its record's fields; anything else is the named refusal
`incident-action-invalid-payload` and nothing is written.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import fields
from pathlib import Path
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
from livespec_orchestrator_beads_fabro.effects import parse_json
from livespec_orchestrator_beads_fabro.incident_normal_repayment import (
    MasterCiRun,
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
    "reopen-regression": ("attributed_json", "finding_json", "principal"),
    "record-deferred-finding": ("finding_json",),
    "record-revert-receipt": ("revert_receipt_json",),
    "correct-attempt": ("correction_json", "target_ref"),
}
INVALID_PAYLOAD = "incident-action-invalid-payload"
MASTER_CI_UNOBSERVABLE = "incident-repayment-master-ci-unobservable"
_RUN_FIELDS = "headSha,status,conclusion"
_COMPLETED = "completed"
_GH_TIMEOUT_SECONDS = 60.0
_SCALARS: dict[str, type] = {"str": str, "bool": bool}
_T = TypeVar("_T")

LifecycleReply = RepaymentEntry | RecoveryEntry | AuthorityRefusal
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


def observe_master_run(
    *, runner: CommandRunner, repo: Path, repository: str, run_id: str
) -> MasterCiRun | AuthorityRefusal:
    """The named master run exactly as the forge reports it now; unreadable is a refusal."""
    result = runner.run(
        argv=["gh", "run", "view", run_id, "--repo", repository, "--json", _RUN_FIELDS],
        cwd=repo,
        timeout_seconds=_GH_TIMEOUT_SECONDS,
    )
    raw = parse_json(text=result.stdout) if result.exit_code == 0 else None
    value = cast("dict[str, object]", raw) if isinstance(raw, dict) else {}
    head, status, conclusion = (value.get(k) for k in ("headSha", "status", "conclusion"))
    if not (isinstance(head, str) and isinstance(status, str) and isinstance(conclusion, str)):
        reason = result.stderr.strip() or "no headSha, status and conclusion in the reply"
        return AuthorityRefusal(code=MASTER_CI_UNOBSERVABLE, detail=f"run {run_id}: {reason}")
    return MasterCiRun(
        run_id=run_id,
        head=head,
        conclusion=conclusion or status,
        complete=status == _COMPLETED,
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


_HANDLERS: dict[str, _Handler] = {
    "enter-repayment": _enter,
    "advance-repayment": _advance,
    "reopen-regression": _reopen,
    "record-deferred-finding": _defer,
    "record-revert-receipt": _revert,
    "correct-attempt": _correct,
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


def lifecycle_body(*, result: RepaymentEntry | RecoveryEntry, body: dict[str, Any]) -> None:
    """Serialize the recorded attempt with its carrier exactly as the chain retains it."""
    reading = cast("dict[str, Any]", body["reading"])
    reading["attempt"] = attempt_record(attempt=result.reading.attempt)
