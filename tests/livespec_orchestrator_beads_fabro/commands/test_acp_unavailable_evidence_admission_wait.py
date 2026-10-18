"""An unavailable evidence source waits under its own governing condition.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -- "An unreadable or incomplete evidence source is unavailable, not an
empty hold set. The Dispatcher MUST surface that condition and retry observation
on a bounded cadence. ... it MUST NOT treat an unobserved candidate as confirmed
unheld" -- together with that section's rest state, "the item MUST remain ready
without a claim or blocked reason", and section "Provider spend containment" ->
"No silent containment", which requires the refusal to carry the governing
condition, the admission-required node and the scheduled reevaluation instant.
Scenario 127's "An unreadable availability source never becomes an empty hold
set" grades it.

THE WHOLE CHAIN IS DRIVEN, FROM THE FACTORY READ TO THE LEDGER ROW, because
every link in it was separately plausible and the join was what did not exist.
The factory read already surfaced the unreadable record, the candidate filter
already knew how to skip an unconfirmed candidate, and the refusal already knew
how to name a governing condition -- and a dispatch still went out as though the
unread run had held nothing. So the verdict here is the REAL
`resolve_acp_preflight`, not a hand-built value: a hand-built verdict satisfies
every assertion below while saying nothing about the path a dispatch takes.

THE ENTITLEMENTS COME OFF THE RUN'S OWN LABELS, AND THERE ARE TWO OF THEM. A
run whose per-run record cannot be read does not say WHICH of its nodes'
attempts failed, so every entitlement it recorded is left unconfirmed -- which
is why the peer run below carries labels for two nodes and why that is what
empties a two-candidate chain. A reader that took one node's label would leave
the fallback selectable and dispatch into a provider whose state it never
observed.

THE REST STATE IS ASSERTED THROUGH THE STORE AND THE LOCK, NOT THROUGH THE
RETURNED OUTCOME, exactly as `test_acp_containment_refusal_record` asserts it: a
refused row looks identical from its outcome whichever condition refused it, and
"without a claim" is a claim about writes that did NOT happen.

THE CONTROL IS THE SAME REPOSITORY, THE SAME RUN AND THE SAME LABELS, with the
per-run record READABLE and carrying an ordinary transport fault. It is what
makes the positive case able to fail for the right reason: without it, a filter
that refused this chain for any other reason -- a mis-ordered chain, an
unreadable adapter -- would satisfy every assertion above.

EVERY DISPATCHER MODULE IS REACHED THROUGH `_commands`, WHICH PRIMES
`_dispatcher_engine` FIRST, and that is a collectability requirement rather than
a style choice. `_dispatcher_acp_preflight` and `_dispatcher_engine` are
mutually recursive at import time, so a top-level import of the preflight module
raises `ImportError` whenever this file is the first thing loaded -- which is
exactly how the Red moment runs one staged test file. A Red that dies at
COLLECTION proves only unimportability, never that the behaviour is
unimplemented.
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_COMMANDS = "livespec_orchestrator_beads_fabro.commands"


def _commands(*, name: str) -> Any:
    """One command module, with the import cycle's entry point primed first."""
    _ = import_module(f"{_COMMANDS}._dispatcher_engine")
    return import_module(f"{_COMMANDS}.{name}")


_ITEM_ID = "bd-unobserved"
_NOW = "2026-10-16T12:00:00Z"

# Deliberately NOT the 300-second default: a resolver that never read the
# repository's own key would still produce a well-formed instant, just the
# wrong one.
_INTERVAL = 900
_NOW_PLUS_INTERVAL = "2026-10-16T12:15:00Z"
_NOW_PLUS_DEFAULT = "2026-10-16T12:05:00Z"

# The exact token the contract spells for this condition, written as a literal
# here rather than imported, so the refusal is bound to the ratified word
# instead of to whatever the module happens to call it.
_UNAVAILABLE_EVIDENCE = "unavailable-availability-evidence"

_RUN_ID = "01M4TN6V5M5WSRA57JENX0MVXW"
_PEER_REPOSITORY = "livespec-console-beads-fabro"

# A run that STARTED five minutes before `now` and ran for one, so its attempt
# occurred four minutes ago -- inside the fifteen-minute hold window.
_STARTED_AT = "2026-10-16T11:55:00Z"
_WALL_TIME_MS = 60_000

# BOTH entitlements this repository's `implement` chain can run, recorded by a
# peer repository's run across its own two ACP nodes.
_LABELS: dict[str, str] = {
    "livespec.repository": _PEER_REPOSITORY,
    "livespec.acp.implement.availability": "codex",
    "livespec.acp.implement.candidate": "primary",
    "livespec.acp.review.availability": "anthropic",
    "livespec.acp.review.candidate": "fallback",
}

_TRANSPORT_CAUSE = "connection reset by peer"

_CHAIN_MANIFEST = """[workflow]
graph = "workflow.fabro"

[run.inputs]
implement_adapter = "adapter-primary"
"""

_CHAIN_GRAPH = """
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
    """A factory run reader whose per-run read may be made unreadable."""

    def __init__(self, *, rows: tuple[Any, ...], payload: object | None) -> None:
        self._rows = rows
        self._payload = payload

    def list_runs(self, *, factory: str) -> tuple[Any, ...] | None:
        return self._rows if factory == "hp" else ()

    def inspect_payload(self, *, factory: str, run_id: str) -> object | None:
        return self._payload if (factory, run_id) == ("hp", _RUN_ID) else None


def _store_config(*, repo_root: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo_root,
    )


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="Waiting on an unobserved availability source",
        description="## Definition of Done\n\n- The product waits.\n",
        origin="freeform",
        gap_id=None,
        rank="a4",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-16T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
        admission_policy="auto",
    )


def _config_document() -> dict[str, Any]:
    """The repository's committed configuration: connection, factories, chain."""
    return {
        "livespec-orchestrator-beads-fabro": {
            "connection": {
                "tenant": "livespec-impl-beads",
                "prefix": "livespec-impl-beads",
                "server_user": "livespec-impl-beads",
                "database": "livespec-impl-beads",
                "bd_path": "bd",
                "fake": True,
            },
            "dispatcher": {
                "credential_reprobe_interval_seconds": _INTERVAL,
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
                                "availability_key": "anthropic",
                                "command": "adapter-fallback",
                            }
                        ],
                    }
                },
            },
        }
    }


def _repo(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, StoreConfig]:
    """A governed repository with one ready item, one factory and one chain."""
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    repo = tmp_path / "repo"
    workflow = repo / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    (workflow / "workflow.toml").write_text(_CHAIN_MANIFEST, encoding="utf-8")
    (workflow / "workflow.fabro").write_text(_CHAIN_GRAPH, encoding="utf-8")
    (repo / ".livespec.jsonc").write_text(json.dumps(_config_document()), encoding="utf-8")
    config = _store_config(repo_root=repo)
    append_work_item(path=config, item=_item())
    monkeypatch.setattr(
        f"{_COMMANDS}._dispatcher_admission_eligibility.utc_now_iso",
        lambda: _NOW,
    )
    return repo, config


def _rows() -> tuple[Any, ...]:
    """One measured `fabro ps -a --json` row, failed inside the hold window."""
    records = _commands(name="_fabro_port_records")
    return records.fabro_run_summaries_from_payload(
        payload=[
            {
                "run_id": _RUN_ID,
                "status": {"kind": "failed"},
                "goal": "Work-item: bd-peer-1\n",
                "repo_origin_url": f"https://github.com/thewoolleyman/{_PEER_REPOSITORY}",
                "labels": dict(_LABELS),
                "start_time": _STARTED_AT,
                "wall_time_ms": _WALL_TIME_MS,
            }
        ]
    )


def _transport_fault_payload() -> list[dict[str, Any]]:
    """One readable `fabro inspect --json` record of an ordinary fault."""
    return [
        {
            "run_id": _RUN_ID,
            "status": {"kind": "failed"},
            "checkpoint": {
                "current_node": "needs_human",
                "completed_nodes": ["setup", "implement"],
                "node_outcomes": {
                    "implement": {
                        "status": "failed",
                        "failure": {
                            "category": "transient_infra",
                            "signature": "implement|transient_infra|acp turn failed",
                            "causes": ["ACP protocol error", _TRANSPORT_CAUSE],
                        },
                    }
                },
            },
        }
    ]


def _verdict(*, repo: Path, payload: object | None) -> Any:
    """One real admission evaluation against the declared factory."""
    return _commands(name="_dispatcher_acp_preflight").resolve_acp_preflight(
        repo=repo,
        journal_path=None,
        now_iso=_NOW,
        factory_runs=_Reader(rows=_rows(), payload=payload),
    )


def _journal(*, repo: Path) -> Any:
    """The dispatch journal this pass appends to."""
    return _commands(name="_dispatcher_io").JournalFile(path=repo / "journal.jsonl")


def _admission(*, repo: Path, verdict: Any, journal: Any) -> tuple[list[WorkItem], list[Any]]:
    """One eligibility pass over the single ready row."""
    return _commands(name="_dispatcher_admission_eligibility").filter_eligible_candidates(
        repo=repo, preflight=verdict, candidates=[_item()], journal=journal
    )


def _refusal_records(*, journal: Any) -> list[dict[str, Any]]:
    stage = _commands(name="_dispatcher_acp_preflight").ACP_PREFLIGHT_REFUSAL_STAGE
    if not journal.path.is_file():
        return []
    lines = journal.path.read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines if line]
    return [record for record in records if record.get("stage") == stage]


def _lock_path(*, repo: Path) -> Path:
    """Where a claimed dispatch would have left its lock."""
    return _commands(name="_dispatcher_dispatch_lock").dispatch_lock_path(
        repo=repo, work_item_id=_ITEM_ID
    )


def _reread(*, config: StoreConfig) -> WorkItem:
    return materialize_work_items(records=read_work_items(path=config))[_ITEM_ID]


def test_an_unreadable_run_record_leaves_the_item_ready_under_its_own_condition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The join this item exists to make, end to end.

    The peer run failed inside the hold window and its per-run record cannot be
    read, so neither of this repository's `implement` candidates is confirmed
    unheld. The chain empties, the item is refused BEFORE any claim, and the
    refusal names the ratified condition and a bounded reevaluation instant
    taken from committed configuration.
    """
    repo, config = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    journal = _journal(repo=repo)

    verdict = _verdict(repo=repo, payload=None)

    assert verdict.viable is False, "an unread run record is still read as an empty hold set"
    assert verdict.exhausted == ("implement",)
    assert verdict.node_preflight(node="implement").candidates == ()
    assert [skip.reason for skip in verdict.node_preflight(node="implement").skipped] == [
        _UNAVAILABLE_EVIDENCE,
        _UNAVAILABLE_EVIDENCE,
    ]

    admittable, refused = _admission(repo=repo, verdict=verdict, journal=journal)

    assert admittable == []
    assert [outcome.work_item_id for outcome in refused] == [_ITEM_ID]
    record = _refusal_records(journal=journal)[0]
    assert record["governing_condition"] == _UNAVAILABLE_EVIDENCE
    assert record["admission_required_node"] == "implement"
    assert record["scheduled_reevaluation_at"] == _NOW_PLUS_INTERVAL
    assert record["scheduled_reevaluation_at"] != _NOW_PLUS_DEFAULT
    assert record["unobservable_observations"] == 1
    # "It MUST NOT invent a hold identity or expiry": nothing was observed.
    assert record["governing_hold_observations"] == []
    # "The item MUST remain ready without a claim or blocked reason", read back
    # off the ledger because the forbidden writes are writes that did NOT happen.
    row = _reread(config=config)
    assert row.status == "ready"
    assert row.blocked_reason is None
    assert row.assignee is None
    assert _lock_path(repo=repo).exists() is False


def test_the_same_run_read_successfully_admits_the_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: the same repository, run and labels, with the record READABLE.

    Its recorded cause is an ordinary transport fault, so the read is complete
    and says nothing about either provider. Without this case, a filter that
    emptied this chain for any other reason would satisfy every assertion in
    the case above.
    """
    repo, config = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    journal = _journal(repo=repo)

    verdict = _verdict(repo=repo, payload=_transport_fault_payload())

    assert verdict.viable is True
    assert verdict.unobservable == ()
    assert [
        candidate.identity.candidate_key
        for candidate in verdict.node_preflight(node="implement").candidates
    ] == ["primary", "fallback"]

    admittable, refused = _admission(repo=repo, verdict=verdict, journal=journal)

    assert [item.id for item in admittable] == [_ITEM_ID]
    assert refused == []
    assert _refusal_records(journal=journal) == []
    assert _reread(config=config).status == "ready"
