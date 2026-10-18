"""What a factory-read success retires at CANDIDATE scope, and what it must not.

Binds the two remaining sentences of `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority" → the hold-retirement routes: "a
later success by the exact candidate identity retires only its older candidate
record. A re-dispatched run that succeeds on a fallback candidate MUST NOT clear
the held primary, even when the whole run succeeds." Scenario 94's sub-scenario
"A later matching node execution expires only the matching record early" grades
both, and ends on exactly this clause: "And a re-dispatched run's success on a
fallback candidate does not clear the held primary."

THESE ARE CONTROLS, AND THEY WERE COMMITTED AS SUCH. The matching rule they
grade is `retired_by_success`, which predates this work and already decided both
scopes correctly; what was missing was any producer feeding it, and that is what
`test_acp_factory_success_retirement.py` binds with its own Red. So neither case
here could fail before that producer existed and neither can fail after it, by
design -- their value is that they pin the two consequences a later edit to the
producer could silently change, in the two directions that matter: a producer
that dropped `candidate_key` would make the first case retire nothing, and one
that broadened a confirmation's domain set would make the second clear a hold the
clause protects.

THE FALLBACK CASE IS ASSERTED TWICE, ON TWO HOLD SHAPES, because the clause can
be satisfied for the wrong reason on either one alone. With the fallback on its
OWN allowance -- the ordinary configuration -- a domain record on the primary's
allowance is untouched because the keys differ, which any key comparison gets
right. With the fallback SHARING the primary's allowance, the only thing keeping
the primary's record alive is that a CANDIDATE record yields to its exact
identity pair and to nothing else; a derivation that let a domain match stand in
for a candidate match passes the first leg and fails the second.

AND THE SECOND LEG IS DELIBERATELY NOT THE MIRROR CASE. A shared-allowance
fallback succeeding against a DOMAIN record on that allowance retires it, and
correctly: the account demonstrably works, which is what a domain record claims
it does not. That is why the primary is held at CANDIDATE scope in that leg --
the held thing has to be the entitlement, not the account.

Everything is HERMETIC: the factory reads arrive through an injected reader, no
port is constructed, nothing launches an adapter and nothing reaches a provider.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_NOW = "2026-10-16T12:00:00Z"
_OCCURRED_AT = "2026-10-16T11:49:00Z"
_EXPIRES_AT = "2026-10-16T12:04:00Z"

# The succeeding peer run: started after the observation, inside the window.
_RUN_ID = "01M4TNCCCCCCCCCCCCCCCCCCCC"
_STARTED_AT = "2026-10-16T11:55:00Z"
_WALL_TIME_MS = 60_000

_PEER_REPOSITORY = "livespec-console-beads-fabro"

_DOMAIN = "availability-domain"
_CANDIDATE = "candidate"

_SHARED_MANIFEST = """[workflow]
graph = "workflow.fabro"

[run.inputs]
implement_adapter = "adapter-primary"
"""

_GRAPH = """
    graph [stall_timeout="7200s"]
    start [shape=Mdiamond, label="Start"]
    exit  [shape=Msquare, label="Exit"]
    implement [backend="acp", acp.command="a", timeout="60s"]
    gate [shape=parallelogram, timeout="60s"]
    start -> implement
    implement -> gate
    gate -> exit [label="green", condition="outcome=succeeded"]
"""


class _Reader:
    """A factory run reader over one row and its per-run record."""

    def __init__(self, *, rows: tuple[Any, ...], payload: object) -> None:
        self._rows = rows
        self._payload = payload

    def list_runs(self, *, factory: str) -> tuple[Any, ...] | None:
        return self._rows if factory == "hp" else ()

    def inspect_payload(self, *, factory: str, run_id: str) -> object | None:
        return self._payload if (factory, run_id) == ("hp", _RUN_ID) else None


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _config(*, fallback_availability_key: str) -> str:
    """One `implement` chain whose fallback's allowance the caller chooses."""
    return json.dumps(
        {
            "livespec-orchestrator-beads-fabro": {
                "dispatcher": {
                    "default_factory": "hp",
                    "factories": {"hp": {"server": "https://hp.example.ts.net:32276"}},
                    "acp_nodes": {
                        "implement": {
                            "display_name": "Primary",
                            "candidate_key": "primary",
                            "availability_key": "codex",
                            "command": "adapter-primary",
                            "fallbacks": [
                                {
                                    "display_name": "Fallback",
                                    "candidate_key": "fallback",
                                    "availability_key": fallback_availability_key,
                                    "command": "adapter-fallback",
                                }
                            ],
                        }
                    },
                }
            }
        }
    )


def _repo(*, tmp_path: Path, fallback_availability_key: str) -> Path:
    """A repository declaring one factory and one two-candidate chain."""
    workflow = tmp_path / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    (workflow / "workflow.toml").write_text(_SHARED_MANIFEST, encoding="utf-8")
    (workflow / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")
    (tmp_path / ".livespec.jsonc").write_text(
        _config(fallback_availability_key=fallback_availability_key), encoding="utf-8"
    )
    return tmp_path


def _observation(
    *, observation_id: str, scope: str, hold_key: str, candidate_key: str | None
) -> dict[str, Any]:
    """One live v1 observation, as this repository's own journal carries it."""
    return {
        "stage": "acp-availability-observed",
        "schema_version": 1,
        "observation_id": observation_id,
        "scope": scope,
        "hold_key": hold_key,
        "candidate_key": candidate_key,
        "cause": "quota",
        "evidence_kind": "acp-failover-event",
        "evidence_id": observation_id,
        "occurred_at": _OCCURRED_AT,
        "expires_at": _EXPIRES_AT,
        "work_item_id": "bd-own-1",
        "node": "implement",
    }


def _journal(*, repo: Path, records: tuple[dict[str, Any], ...]) -> Path:
    path = repo / "journal.jsonl"
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    return path


def _row(*, availability_key: str, candidate_key: str) -> dict[str, Any]:
    """The succeeding run's own `fabro ps -a --json` row."""
    return {
        "run_id": _RUN_ID,
        "status": {"kind": "succeeded"},
        "goal": "Work-item: bd-peer-1\n",
        "repo_origin_url": f"https://github.com/thewoolleyman/{_PEER_REPOSITORY}",
        "labels": {
            "livespec.repository": _PEER_REPOSITORY,
            "livespec.acp.implement.availability": availability_key,
            "livespec.acp.implement.candidate": candidate_key,
        },
        "start_time": _STARTED_AT,
        "wall_time_ms": _WALL_TIME_MS,
    }


def _success_payload() -> list[dict[str, Any]]:
    """One `fabro inspect --json` record whose `implement` attempt SUCCEEDED."""
    return [
        {
            "run_id": _RUN_ID,
            "status": {"kind": "succeeded"},
            "checkpoint": {
                "current_node": "exit",
                "completed_nodes": ["setup", "implement", "gate", "exit"],
                "node_outcomes": {"implement": {"status": "succeeded"}},
            },
        }
    ]


def _verdict(
    *,
    repo: Path,
    records: tuple[dict[str, Any], ...],
    availability_key: str,
    candidate_key: str,
) -> Any:
    """One real admission evaluation against the declared factory."""
    rows = _module(name="_fabro_port_records").fabro_run_summaries_from_payload(
        payload=[_row(availability_key=availability_key, candidate_key=candidate_key)]
    )
    return _module(name="_dispatcher_acp_preflight").resolve_acp_preflight(
        repo=repo,
        journal_path=_journal(repo=repo, records=records),
        now_iso=_NOW,
        factory_runs=_Reader(rows=rows, payload=_success_payload()),
    )


def _candidate_keys(*, verdict: Any) -> list[str | None]:
    """The `implement` node's surviving candidates, in configured order."""
    return [
        None if candidate.identity is None else candidate.identity.candidate_key
        for candidate in verdict.node_preflight(node="implement").candidates
    ]


def test_a_success_by_the_exact_identity_retires_only_its_own_candidate_record(
    tmp_path: Path,
) -> None:
    """ "A later success by the exact candidate identity retires only its older
    candidate record."

    Two candidate records stand on the SAME allowance and differ only by the
    entitlement they name. The succeeding attempt ran the primary's pair, so
    the primary's record is expired early and the fallback's is untouched --
    and the fallback stays skipped, which is what makes "only" observable
    rather than merely consistent.
    """
    repo = _repo(tmp_path=tmp_path, fallback_availability_key="codex")
    records = (
        _observation(
            observation_id="acpobs-primary",
            scope=_CANDIDATE,
            hold_key="codex",
            candidate_key="primary",
        ),
        _observation(
            observation_id="acpobs-fallback",
            scope=_CANDIDATE,
            hold_key="codex",
            candidate_key="fallback",
        ),
    )

    verdict = _verdict(
        repo=repo, records=records, availability_key="codex", candidate_key="primary"
    )

    assert [hold.observation_id for hold in verdict.holds] == ["acpobs-fallback"]
    assert _candidate_keys(verdict=verdict) == ["primary"]


@pytest.mark.parametrize(
    ("fallback_availability_key", "scope", "hold_key"),
    [
        pytest.param("anthropic", _DOMAIN, "codex", id="fallback-on-its-own-allowance"),
        pytest.param("codex", _CANDIDATE, "codex", id="fallback-sharing-the-allowance"),
    ],
)
def test_a_fallback_success_leaves_the_held_primarys_record_live(
    tmp_path: Path, fallback_availability_key: str, scope: str, hold_key: str
) -> None:
    """ "A re-dispatched run that succeeds on a fallback candidate MUST NOT clear
    the held primary, even when the whole run succeeds."

    The run below succeeded outright -- its `implement` attempt is recorded
    `succeeded` and the record walks to the green terminal -- and it ran the
    FALLBACK. In both arms the primary's record survives, and the primary stays
    skipped while the fallback is the node's only selectable candidate, which is
    the selection the clause is protecting.
    """
    repo = _repo(tmp_path=tmp_path, fallback_availability_key=fallback_availability_key)
    records = (
        _observation(
            observation_id="acpobs-primary",
            scope=scope,
            hold_key=hold_key,
            candidate_key="primary" if scope == _CANDIDATE else None,
        ),
    )

    verdict = _verdict(
        repo=repo,
        records=records,
        availability_key=fallback_availability_key,
        candidate_key="fallback",
    )

    assert [hold.observation_id for hold in verdict.holds] == ["acpobs-primary"]
    assert _candidate_keys(verdict=verdict) == ["fallback"]
    assert verdict.viable is True
