"""Versioned process boundary for incident authority consumers in other projects."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    attempt_record,
    decode_attempt,
    unsupported_carrier,
)
from livespec_orchestrator_beads_fabro._incident_carrier import CARRIER_UNSUPPORTED
from livespec_orchestrator_beads_fabro._incident_genesis import (
    GENESIS_CAPABILITY_UNAVAILABLE,
    capability_unavailable,
    decode_genesis_request,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    resolve_claim_tokens,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._incident_authority_lifecycle import (
    LIFECYCLE_PAYLOADS,
    lifecycle_body,
    run_lifecycle_action,
)
from livespec_orchestrator_beads_fabro.commands._intake_valve_claim_writes import TakeoverWait
from livespec_orchestrator_beads_fabro.commands.incident_local_gate_lookup import (
    LocalGateLookup,
    read_local_gates,
)
from livespec_orchestrator_beads_fabro.commands.incident_local_gate_receipt import (
    LocalGateReceipt,
    read_receipt_stream,
    record_local_gates,
)
from livespec_orchestrator_beads_fabro.effects import parse_json
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    FilingReceipt,
    GenesisReceipt,
    IncidentReading,
    commit_incident_transition,
    decode_filing_request,
    file_incident,
    publish_incident_genesis,
    read_incident_authority,
)
from livespec_orchestrator_beads_fabro.incident_completion import IncidentCompletion
from livespec_orchestrator_beads_fabro.incident_normal_repayment import RepaymentEntry
from livespec_orchestrator_beads_fabro.incident_regression_recovery import RecoveryEntry
from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = ["main"]

_RECORD_GATES = "record-local-gates"
_Reply = (
    IncidentReading
    | AuthorityRefusal
    | LocalGateLookup
    | LocalGateReceipt
    | GenesisReceipt
    | FilingReceipt
    | RepaymentEntry
    | RecoveryEntry
    | IncidentCompletion
)

# Each writing action and the payload arguments it alone requires.
_ACTION_ARGUMENTS: dict[str, tuple[str, ...]] = {
    "commit-transition": ("successor_json",),
    _RECORD_GATES: ("receipt_json",),
    "read-local-gates": ("receipt_id",),
    "publish-genesis": ("genesis_json",),
    "file-incident": ("filing_json",),
    **LIFECYCLE_PAYLOADS,
}
_PAYLOAD_OWNERS = {
    field: tuple(action for action, owned in _ACTION_ARGUMENTS.items() if field in owned)
    for field in dict.fromkeys(field for owned in _ACTION_ARGUMENTS.values() for field in owned)
}
_ADVANCE = "advance-repayment"
_HISTORICAL = frozenset(("read-history", "commit-transition", *LIFECYCLE_PAYLOADS))
_FILING = "file-incident"
_IDENTITY = ("item", "attempt", "phase", "generation")
_TRANSITION_PENDING = "incident-genesis-claim-transition-pending"
_IDENTITY_RULE = "--item, --attempt, --phase and --generation: required unless file-incident"


def _check_receipt_source(*, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """A receipt has exactly one source, and only the action that records it takes one."""
    if args.action == _RECORD_GATES and (args.receipt_json is not None) == args.receipt_stdin:
        parser.error(f"{_RECORD_GATES} requires exactly one of --receipt-json or --receipt-stdin")
    if args.receipt_stdin and args.action != _RECORD_GATES:
        parser.error(f"--receipt-stdin is only valid for {_RECORD_GATES}")


def _parse(*, argv: Sequence[str] | None) -> argparse.Namespace:
    """Each action-only payload argument belongs to exactly one action."""
    parser = argparse.ArgumentParser(prog="incident-authority")
    _ = parser.add_argument("action", choices=(*_ACTION_ARGUMENTS, "read-current", "read-history"))
    for field in _PAYLOAD_OWNERS:
        _ = parser.add_argument("--" + field.replace("_", "-"))
    _ = parser.add_argument("--admission-complete", action="store_true")
    _ = parser.add_argument("--receipt-stdin", action="store_true")
    _ = parser.add_argument("--repo", required=True, type=Path)
    for name in ("repository", "operation", "owner"):
        _ = parser.add_argument(f"--{name}", required=True)
    for name in ("item", "attempt", "phase"):
        _ = parser.add_argument(f"--{name}")
    _ = parser.add_argument("--generation", type=int)
    args = parser.parse_args(argv)
    for field, owners in _PAYLOAD_OWNERS.items():
        if field == "receipt_json" and args.action == _RECORD_GATES:
            continue
        if (args.action in owners) != (getattr(args, field) is not None):
            flag = "--" + field.replace("_", "-")
            parser.error(f"{flag} is required by, and only valid for, {', '.join(owners)}")
    _check_receipt_source(parser=parser, args=args)
    if args.admission_complete and args.action != _ADVANCE:
        parser.error(f"--admission-complete is only valid for {_ADVANCE}")
    # A filing has no item identity yet; every other action names one exactly.
    if any((getattr(args, name) is None) != (args.action == _FILING) for name in _IDENTITY):
        parser.error(_IDENTITY_RULE)
    return args


def main(*, argv: Sequence[str] | None = None) -> int:
    """Print one schema-1 reply; an unverifiable identity exits 78, not normal mode."""
    args = _parse(argv=argv)
    if args.action == "publish-genesis":
        return _reply(result=_genesis(args=args), authorizes=False)
    if args.action == _FILING:
        return _reply(result=_filing(args=args), authorizes=False)
    client = make_beads_client(config=store_config(repo=args.repo))
    result = read_incident_authority(
        client=client,
        repository=args.repository,
        item_id=args.item,
        query={
            "attempt_id": args.attempt,
            "phase": args.phase,
            "operation_id": args.operation,
            "generation": args.generation,
            "owner": args.owner,
        },
        historical=args.action in _HISTORICAL,
    )
    if args.action == "commit-transition" and isinstance(result, IncidentReading):
        raw = parse_json(text=args.successor_json)
        successor = decode_attempt(value=raw)
        result = (
            commit_incident_transition(client=client, observed=result, successor=successor)
            if successor is not None
            and args.successor_json
            == json.dumps(attempt_record(attempt=successor), sort_keys=True, separators=(",", ":"))
            else AuthorityRefusal(
                code=CARRIER_UNSUPPORTED
                if unsupported_carrier(value=raw)
                else "incident-transition-invalid-successor",
                detail=args.item,
            )
        )
    if args.action == _RECORD_GATES and isinstance(result, IncidentReading):
        text = (
            read_receipt_stream(stream=sys.stdin.buffer)
            if args.receipt_stdin
            else args.receipt_json
        )
        result = record_local_gates(client=client, observed=result, text=text)
    if args.action == "read-local-gates" and isinstance(result, IncidentReading):
        result = read_local_gates(client=client, observed=result, receipt_id=args.receipt_id)
    if args.action in LIFECYCLE_PAYLOADS and isinstance(result, IncidentReading):
        result = run_lifecycle_action(
            args=args, client=client, reading=result, runner=ShellCommandRunner()
        )
    return _reply(result=result, authorizes=args.action == "read-current")


def _claim_tokens(*, repo: Path, detail: str) -> bool | AuthorityRefusal:
    """The committed cutover; unreadable is a capability refusal, never `false`."""
    setting = resolve_claim_tokens(cwd=repo)
    if not is_successful(setting):
        return AuthorityRefusal(
            code=GENESIS_CAPABILITY_UNAVAILABLE,
            detail=f"{detail}: committed dispatcher.claim_tokens is unreadable",
        )
    return unsafe_perform_io(setting.unwrap())


def _wait_out_transition() -> None:
    """A one-shot entry waits the protocol's takeover wait before its one retry."""
    TakeoverWait().wait_out()


def _genesis(*, args: argparse.Namespace) -> GenesisReceipt | AuthorityRefusal:
    """Bind the request; without the committed claim-token cutover, refuse with no client."""
    request = decode_genesis_request(
        text=args.genesis_json,
        repository=args.repository,
        item_id=args.item,
        operation_id=args.operation,
    )
    if request is None or (
        request.attempt.attempt_id,
        request.attempt.owner,
        request.attempt.generation,
        request.attempt.phase,
    ) != (args.attempt, args.owner, args.generation, args.phase):
        return AuthorityRefusal(code="incident-genesis-invalid-request", detail=args.item)
    cutover = _claim_tokens(repo=args.repo, detail=args.item)
    if isinstance(cutover, AuthorityRefusal):
        return cutover
    if not cutover:
        return capability_unavailable(request=request)
    client = make_beads_client(config=store_config(repo=args.repo))
    result = publish_incident_genesis(client=client, request=request, claim_tokens=True)
    if isinstance(result, AuthorityRefusal) and result.code == _TRANSITION_PENDING:
        _wait_out_transition()
        result = publish_incident_genesis(client=client, request=request, claim_tokens=True)
    return result


def _filing(*, args: argparse.Namespace) -> FilingReceipt | AuthorityRefusal:
    """File one identified incident under the exact principal and operation named."""
    request = decode_filing_request(text=args.filing_json)
    if request is None or (request.repository, request.operation_id, request.principal) != (
        args.repository,
        args.operation,
        args.owner,
    ):
        return AuthorityRefusal(code="incident-filing-invalid-request", detail=args.operation)
    cutover = _claim_tokens(repo=args.repo, detail=args.operation)
    if isinstance(cutover, AuthorityRefusal):
        return cutover
    config = store_config(repo=args.repo)
    return file_incident(
        client=make_beads_client(config=config),
        prefix=config.prefix,
        request=request,
        claim_tokens=cutover,
    )


def _without_walk_scope(*, value: object) -> object:
    """Leave out the operations a reading happened to walk.

    That set is the whole chain for a historical read and only the segment after the
    item's head hint for a current one, so the same committed reading would otherwise
    serialize differently when a retry recovers it.
    """
    if isinstance(value, dict):
        return {
            key: _without_walk_scope(value=item)
            for key, item in cast("dict[str, object]", value).items()
            if key != "operation_ids"
        }
    return value


def _result_body(*, result: _Reply) -> dict[str, object]:
    body = cast("dict[str, Any]", _without_walk_scope(value=asdict(result)))
    if isinstance(result, IncidentReading | GenesisReceipt):
        body["attempt"] = attempt_record(attempt=result.attempt)
    if isinstance(result, RepaymentEntry | RecoveryEntry | IncidentCompletion):
        lifecycle_body(result=result, body=body)
    return body


def _reply(*, result: _Reply, authorizes: bool) -> int:
    refused = isinstance(result, AuthorityRefusal)
    response: dict[str, object] = {
        "schema": 1,
        "status": "refused" if refused else "verified",
        "result": _result_body(result=result),
        "authorizes_current_effects": authorizes and not refused,
        "normal_factory_proof": False,
    }
    _ = write_stdout(text=json.dumps(response, sort_keys=True) + "\n")
    return 78 if refused else 0
