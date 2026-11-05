"""Versioned process boundary for incident authority consumers in other projects."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

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
from livespec_orchestrator_beads_fabro.commands.incident_local_gate_lookup import (
    LocalGateLookup,
    read_local_gates,
)
from livespec_orchestrator_beads_fabro.commands.incident_local_gate_receipt import (
    LocalGateReceipt,
    record_local_gates,
)
from livespec_orchestrator_beads_fabro.effects import parse_json
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    GenesisReceipt,
    IncidentReading,
    commit_incident_transition,
    publish_incident_genesis,
    read_incident_authority,
)
from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = ["main"]


_ACTION_ARGUMENTS = {
    "commit-transition": "successor_json",
    "record-local-gates": "receipt_json",
    "read-local-gates": "receipt_id",
    "publish-genesis": "genesis_json",
}


def _parse(*, argv: Sequence[str] | None) -> argparse.Namespace:
    """Each action-only payload argument belongs to exactly one action."""
    parser = argparse.ArgumentParser(prog="incident-authority")
    _ = parser.add_argument(
        "action",
        choices=(
            "read-current",
            "read-history",
            "commit-transition",
            "record-local-gates",
            "read-local-gates",
            "publish-genesis",
        ),
    )
    _ = parser.add_argument("--genesis-json")
    _ = parser.add_argument("--successor-json")
    _ = parser.add_argument("--receipt-json")
    _ = parser.add_argument("--receipt-id")
    _ = parser.add_argument("--repo", required=True, type=Path)
    for name in ("repository", "item", "attempt", "phase", "operation", "owner"):
        _ = parser.add_argument(f"--{name}", required=True)
    _ = parser.add_argument("--generation", required=True, type=int)
    args = parser.parse_args(argv)
    for action, field in _ACTION_ARGUMENTS.items():
        if (args.action == action) != (getattr(args, field) is not None):
            flag = "--" + field.replace("_", "-")
            parser.error(f"{flag} is required by, and only valid for, {action}")
    return args


def main(*, argv: Sequence[str] | None = None) -> int:
    """Print one schema-1 reply; an unverifiable identity exits 78, not normal mode."""
    args = _parse(argv=argv)
    if args.action == "publish-genesis":
        return _reply(result=_genesis(args=args), authorizes=False)
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
        historical=args.action in {"read-history", "commit-transition"},
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
    if args.action == "record-local-gates" and isinstance(result, IncidentReading):
        result = record_local_gates(client=client, observed=result, text=args.receipt_json)
    if args.action == "read-local-gates" and isinstance(result, IncidentReading):
        result = read_local_gates(client=client, observed=result, receipt_id=args.receipt_id)
    return _reply(result=result, authorizes=args.action == "read-current")


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
    setting = resolve_claim_tokens(cwd=args.repo)
    if not is_successful(setting):
        return AuthorityRefusal(
            code=GENESIS_CAPABILITY_UNAVAILABLE,
            detail=f"{args.item}: committed dispatcher.claim_tokens is unreadable",
        )
    if not unsafe_perform_io(setting.unwrap()):
        return capability_unavailable(request=request)
    client = make_beads_client(config=store_config(repo=args.repo))
    return publish_incident_genesis(client=client, request=request, claim_tokens=True)


def _result_body(
    *,
    result: IncidentReading
    | AuthorityRefusal
    | LocalGateLookup
    | LocalGateReceipt
    | GenesisReceipt,
) -> dict[str, object]:
    body = asdict(result)
    if isinstance(result, IncidentReading | GenesisReceipt):
        body["attempt"] = attempt_record(attempt=result.attempt)
    return body


def _reply(
    *,
    result: IncidentReading
    | AuthorityRefusal
    | LocalGateLookup
    | LocalGateReceipt
    | GenesisReceipt,
    authorizes: bool,
) -> int:
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
