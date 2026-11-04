"""Versioned process boundary for incident authority consumers in other projects."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._incident_authority_payload import decode_attempt
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.effects import parse_json
from livespec_orchestrator_beads_fabro.incident_authority import (
    AuthorityRefusal,
    IncidentReading,
    commit_incident_transition,
    read_incident_authority,
)
from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = ["main"]


def main(*, argv: Sequence[str] | None = None) -> int:
    """Print one schema-1 reply; an unverifiable identity exits 78, not normal mode."""
    parser = argparse.ArgumentParser(prog="incident-authority")
    _ = parser.add_argument("action", choices=("read-current", "read-history", "commit-transition"))
    _ = parser.add_argument("--successor-json")
    _ = parser.add_argument("--repo", required=True, type=Path)
    for name in ("repository", "item", "attempt", "phase", "operation", "owner"):
        _ = parser.add_argument(f"--{name}", required=True)
    _ = parser.add_argument("--generation", required=True, type=int)
    args = parser.parse_args(argv)
    if args.action == "commit-transition" and args.successor_json is None:
        parser.error("commit-transition requires --successor-json")
    if args.action != "commit-transition" and args.successor_json is not None:
        parser.error("--successor-json is only valid for commit-transition")
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
        historical=args.action != "read-current",
    )
    if args.action == "commit-transition" and isinstance(result, IncidentReading):
        successor = decode_attempt(value=parse_json(text=args.successor_json))
        result = (
            commit_incident_transition(client=client, observed=result, successor=successor)
            if successor is not None
            and args.successor_json
            == json.dumps(asdict(successor), sort_keys=True, separators=(",", ":"))
            else AuthorityRefusal(code="incident-transition-invalid-successor", detail=args.item)
        )
    response: dict[str, object] = {
        "schema": 1,
        "status": "refused" if isinstance(result, AuthorityRefusal) else "verified",
        "result": asdict(result),
        "authorizes_current_effects": args.action == "read-current"
        and not isinstance(result, AuthorityRefusal),
        "normal_factory_proof": False,
    }
    _ = write_stdout(text=json.dumps(response, sort_keys=True) + "\n")
    return 78 if isinstance(result, AuthorityRefusal) else 0
