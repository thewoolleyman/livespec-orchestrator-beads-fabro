"""A later matching success read from the factory records retires its hold.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "Bounded expiry, later matching execution, and operator clearance
are the only hold-retirement routes. ... A node attempt that starts after a
domain observation and succeeds against the same hold key retires only that
older domain record". Scenario 94's sub-scenario "A later matching node
execution expires only the matching record early" grades it: "When a node
attempt begins after the observation and succeeds against the same domain or
exact candidate identity, then only the matching older record is expired even
though its recorded expiry has not been reached."

THE EVIDENCE IS READ FROM THE FACTORY, NOT FROM THIS REPOSITORY'S JOURNAL, and
that is the whole of what was missing. The retirement DECISION already existed
and was already correct; nothing produced a successful attempt for it to decide
on, because the host-wide read passed over every row that was not failed. So the
successes here come off a PEER repository's run, and the record they retire is
this repository's own journalled one -- a join no amount of journal folding can
make.

THE WORD "ONLY" IS WHAT THE FIXTURE IS BUILT AROUND. Two unexpired domain
records stand when the pass begins, on two different allowances, and the
succeeding attempt matches exactly one of them. A retirement that cleared the
ledger, or that keyed on the run rather than on the hold key, satisfies every
assertion about the matched record and fails on the untouched one.

TWO CONTROLS, EACH ABLE TO FAIL ON ITS OWN. Without the succeeding run at all,
both records stand and the chain is exhausted -- which is what shows the
retirement is what changed the answer rather than the fixture's shape. And with
the succeeding run STARTED BEFORE the observation, nothing is retired: "an
attempt already running when the outage was seen proves nothing about it", and a
derivation ignoring the start instant passes the positive case while clearing a
live outage on the evidence of a run that predates it.

Everything is HERMETIC: the factory reads arrive through an injected reader, no
port is constructed, nothing launches an adapter and nothing reaches a provider.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_NOW = "2026-10-16T12:00:00Z"

# The FAILED peer run: started 11:48, ran one minute, so its attempt occurred
# at 11:49 -- eleven minutes ago, inside the fifteen-minute hold window.
_FAILED_RUN_ID = "01M4TN6V5M5WSRA57JENX0MVXW"
_FAILED_START = "2026-10-16T11:48:00Z"
_OCCURRED_AT = "2026-10-16T11:49:00Z"
_EXPIRES_AT = "2026-10-16T12:04:00Z"

# The LATER peer run, started after that observation and inside the window.
_LATER_RUN_ID = "01M4TNAAAAAAAAAAAAAAAAAAAA"
_LATER_START = "2026-10-16T11:55:00Z"

# The SAME run, started BEFORE the observation: still inside the window, so it
# is read and graded, and it must retire nothing.
_EARLIER_START = "2026-10-16T11:47:00Z"

_WALL_TIME_MS = 60_000

_PEER_REPOSITORY = "livespec-console-beads-fabro"

# MEASURED 2026-08-22 across the ten Codex ceiling refusals on hp.
_CEILING_CAUSE = "You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage"
_TURN_CAPACITY = "Selected model is at capacity. Please try a different model."

# This repository's OWN journalled record, on the FALLBACK's allowance. It is
# what makes "only" assertable: the succeeding attempt spends `codex` and must
# leave this one exactly as it found it.
_JOURNALLED_FALLBACK_HOLD: dict[str, Any] = {
    "stage": "acp-availability-observed",
    "schema_version": 1,
    "observation_id": "acpobs-journalled-fallback",
    "scope": "availability-domain",
    "hold_key": "anthropic",
    "candidate_key": None,
    "cause": "quota",
    "evidence_kind": "acp-failover-event",
    "evidence_id": "evt-1",
    "occurred_at": _OCCURRED_AT,
    "expires_at": _EXPIRES_AT,
    "work_item_id": "bd-own-1",
    "node": "implement",
}

_CHAIN_CONFIG = """{
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
              "availability_key": "anthropic",
              "command": "adapter-fallback"
            }
          ]
        }
      }
    }
  }
}
"""

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
    """A factory run reader over a fixed row set and per-run record map."""

    def __init__(self, *, rows: tuple[Any, ...], payloads: dict[str, object]) -> None:
        self._rows = rows
        self._payloads = payloads

    def list_runs(self, *, factory: str) -> tuple[Any, ...] | None:
        return self._rows if factory == "hp" else ()

    def inspect_payload(self, *, factory: str, run_id: str) -> object | None:
        return self._payloads.get(run_id) if factory == "hp" else None


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _labels(*, availability_key: str, candidate_key: str) -> dict[str, str]:
    """The entitlement labels a dispatch stamps on its own run."""
    return {
        "livespec.repository": _PEER_REPOSITORY,
        "livespec.acp.implement.availability": availability_key,
        "livespec.acp.implement.candidate": candidate_key,
    }


def _row(
    *,
    run_id: str,
    status: str,
    start_time: str,
    availability_key: str = "codex",
    candidate_key: str = "primary",
) -> dict[str, Any]:
    """One measured `fabro ps -a --json` row, in the engine's own shape."""
    return {
        "run_id": run_id,
        "status": {"kind": status},
        "goal": "Work-item: bd-peer-1\n",
        "repo_origin_url": f"https://github.com/thewoolleyman/{_PEER_REPOSITORY}",
        "labels": _labels(availability_key=availability_key, candidate_key=candidate_key),
        "start_time": start_time,
        "wall_time_ms": _WALL_TIME_MS,
    }


def _rows(*, payload: list[dict[str, Any]]) -> tuple[Any, ...]:
    """Run rows as the port's own projection of a `fabro ps -a --json` payload."""
    return _module(name="_fabro_port_records").fabro_run_summaries_from_payload(payload=payload)


def _ceiling_payload() -> list[dict[str, Any]]:
    """One `fabro inspect --json` record whose `implement` attempt hit a ceiling."""
    return [
        {
            "run_id": _FAILED_RUN_ID,
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
                            "causes": ["ACP protocol error", _CEILING_CAUSE],
                        },
                    },
                    "needs_human": {
                        "status": "failed",
                        "failure": {
                            "category": "deterministic",
                            "signature": "needs_human|deterministic|script failed",
                            "causes": ["stage needs_human failed with no outgoing fail edge"],
                        },
                    },
                },
            },
        }
    ]


def _success_payload(
    *, output: str | None = None, response: str | None = None
) -> list[dict[str, Any]]:
    """One `fabro inspect --json` record whose `implement` attempt SUCCEEDED."""
    attempt: dict[str, str] = {"status": "succeeded"}
    if output is not None:
        attempt["output"] = output
    if response is not None:
        attempt["response"] = response
    return [
        {
            "run_id": _LATER_RUN_ID,
            "status": {"kind": "succeeded"},
            "checkpoint": {
                "current_node": "exit",
                "completed_nodes": ["setup", "implement", "gate", "exit"],
                "node_outcomes": {
                    "implement": attempt,
                    "gate": {"status": "succeeded"},
                },
            },
        }
    ]


def _repo(*, tmp_path: Path) -> Path:
    """A repository declaring one factory and one two-candidate chain."""
    workflow = tmp_path / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    (workflow / "workflow.toml").write_text(_CHAIN_MANIFEST, encoding="utf-8")
    (workflow / "workflow.fabro").write_text(_CHAIN_GRAPH, encoding="utf-8")
    (tmp_path / ".livespec.jsonc").write_text(_CHAIN_CONFIG, encoding="utf-8")
    return tmp_path


def _journal(*, repo: Path) -> Path:
    """This repository's own journal, carrying the fallback's live record."""
    path = repo / "journal.jsonl"
    path.write_text(json.dumps(_JOURNALLED_FALLBACK_HOLD) + "\n", encoding="utf-8")
    return path


def _verdict(*, repo: Path, rows: list[dict[str, Any]], payloads: dict[str, object]) -> Any:
    """One real admission evaluation against the declared factory."""
    return _module(name="_dispatcher_acp_preflight").resolve_acp_preflight(
        repo=repo,
        journal_path=_journal(repo=repo),
        now_iso=_NOW,
        factory_runs=_Reader(rows=_rows(payload=rows), payloads=payloads),
    )


def _candidate_keys(*, verdict: Any) -> list[str | None]:
    """The `implement` node's surviving candidates, in configured order."""
    return [
        None if candidate.identity is None else candidate.identity.candidate_key
        for candidate in verdict.node_preflight(node="implement").candidates
    ]


def _failed_row() -> dict[str, Any]:
    return _row(run_id=_FAILED_RUN_ID, status="failed", start_time=_FAILED_START)


def _later_row(*, start_time: str) -> dict[str, Any]:
    return _row(run_id=_LATER_RUN_ID, status="succeeded", start_time=start_time)


def _payloads() -> dict[str, object]:
    return {
        _FAILED_RUN_ID: _ceiling_payload(),
        _LATER_RUN_ID: _success_payload(output="ordinary successful review"),
    }


def test_a_succeeded_capacity_turn_does_not_retire_its_live_candidate_hold(
    tmp_path: Path,
) -> None:
    """A refusal recorded as success is failure evidence, not retirement evidence."""
    repo = _repo(tmp_path=tmp_path)

    verdict = _verdict(
        repo=repo,
        rows=[_failed_row(), _later_row(start_time=_LATER_START)],
        payloads={
            _FAILED_RUN_ID: _ceiling_payload(),
            _LATER_RUN_ID: _success_payload(response=_TURN_CAPACITY),
        },
    )

    assert _candidate_keys(verdict=verdict) == []


def test_a_later_factory_read_success_retires_only_its_matching_domain_record(
    tmp_path: Path,
) -> None:
    """The matched record goes; the one on the other allowance stays.

    Two unexpired domain records stand when this pass begins -- `codex`, derived
    from the peer run that hit a ceiling, and `anthropic`, journalled by this
    repository. The later peer run succeeded on `codex`, so the `codex` record
    is expired early and the primary is selectable again, while the `anthropic`
    record is untouched and still skips the fallback.
    """
    repo = _repo(tmp_path=tmp_path)

    verdict = _verdict(
        repo=repo,
        rows=[_failed_row(), _later_row(start_time=_LATER_START)],
        payloads=_payloads(),
    )

    assert [hold.hold_key for hold in verdict.holds] == [
        "anthropic"
    ], "the matching domain record was not retired by the later success"
    assert _candidate_keys(verdict=verdict) == ["primary"]
    assert verdict.viable is True


def test_without_the_later_success_both_records_stand_and_the_chain_empties(
    tmp_path: Path,
) -> None:
    """The control: the same fixture minus the succeeding run.

    Without it, a derivation that simply dropped every derived record would
    satisfy the case above while retiring holds nothing had falsified.
    """
    repo = _repo(tmp_path=tmp_path)

    verdict = _verdict(repo=repo, rows=[_failed_row()], payloads=_payloads())

    assert sorted(hold.hold_key for hold in verdict.holds) == ["anthropic", "codex"]
    assert _candidate_keys(verdict=verdict) == []
    assert verdict.viable is False


def test_a_success_that_started_before_the_observation_retires_nothing(
    tmp_path: Path,
) -> None:
    """ "An attempt already running when the outage was seen proves nothing."

    The run is identical in every other respect -- same id, same entitlement,
    same succeeded node, still inside the hold window so it is read and graded
    -- and it began two minutes BEFORE the attempt that spent the allowance.
    """
    repo = _repo(tmp_path=tmp_path)

    verdict = _verdict(
        repo=repo,
        rows=[_failed_row(), _later_row(start_time=_EARLIER_START)],
        payloads=_payloads(),
    )

    assert sorted(hold.hold_key for hold in verdict.holds) == ["anthropic", "codex"]
    assert _candidate_keys(verdict=verdict) == []
