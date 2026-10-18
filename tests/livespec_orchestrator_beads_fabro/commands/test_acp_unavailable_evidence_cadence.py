"""An unavailable availability-evidence source is retried on a bounded cadence.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "An unreadable or incomplete evidence source is unavailable, not an
empty hold set. The Dispatcher MUST surface that condition and retry
observation on a bounded cadence." Scenario 127's "An unreadable availability
source never becomes an empty hold set" grades it.

THE THREE VERBS THE CLAUSE NAMES ARE ASSERTED SEPARATELY, because the first two
were already delivered and only the third was not. "Reported as unavailable" is
the reason token the read records, "surfaced" is that entry riding the verdict
every consumer reads, and "retried on a bounded cadence" is the scheduled
reevaluation instant. A test asserting only the first two passes against a build
that schedules nothing at all, which is exactly the state this module was
written against.

THE CONTROL IS A FULLY READABLE FACTORY, and it is what makes the positive case
able to fail for the right reason. Without it, a derivation that scheduled a
cadence retry on EVERY evaluation -- including every healthy one -- would
satisfy the positive assertion while turning the bounded cadence into an
unconditional one. Its row is a FAILED run inside the hold window carrying an
ordinary transport fault, which is the healthy read that costs the most: the
listing is read, the per-run record is read, and what the records say is that
nothing about a provider happened. A control built from a stale row would
report the same empty answer while never reaching a per-run read at all.

Everything is HERMETIC: the factory reads arrive through an injected reader, no
port is constructed, nothing launches an adapter and nothing reaches a provider.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_NOW = "2026-10-16T12:00:00Z"
# `_NOW` advanced by the ratified `credential_reprobe_interval_seconds`
# default, spelled rather than computed so the expected value cannot be
# produced by the same arithmetic the implementation uses.
_NOW_PLUS_CADENCE = "2026-10-16T12:05:00Z"

_RUN_ID = "01M4TN6V5M5WSRA57JENX0MVXW"
_PEER_REPOSITORY = "livespec-console-beads-fabro"

# A run that STARTED five minutes before `now` and ran for one, so its attempt
# occurred four minutes ago -- inside the fifteen-minute hold window, which is
# what makes the control spend a per-run read rather than skipping one.
_STARTED_AT = "2026-10-16T11:55:00Z"
_WALL_TIME_MS = 60_000

# An ordinary transport fault, which is NOT an eligible availability cause.
_TRANSPORT_CAUSE = "connection reset by peer"

_CHAIN_CONFIG = """{
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "default_factory": "hp",
      "factories": {
        "hp": {"server": "https://hp.example.ts.net:32276"},
        "vps": {"server": "https://vps.example.ts.net:32276"}
      },
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


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


@dataclass(kw_only=True)
class _Reader:
    """A factory run reader that answers `None` for an unreadable listing."""

    rows: dict[str, tuple[Any, ...] | None] = field(default_factory=dict)
    payloads: dict[tuple[str, str], object | None] = field(default_factory=dict)

    def list_runs(self, *, factory: str) -> tuple[Any, ...] | None:
        return self.rows.get(factory, ())

    def inspect_payload(self, *, factory: str, run_id: str) -> object | None:
        return self.payloads.get((factory, run_id))


def _rows(*, payload: list[dict[str, Any]]) -> tuple[Any, ...]:
    """Run rows as the port's own projection of a `fabro ps -a --json` payload."""
    records = _module(name="_fabro_port_records")
    return records.fabro_run_summaries_from_payload(payload=payload)


def _failed_row() -> dict[str, Any]:
    """One measured `fabro ps -a --json` row, failed inside the hold window."""
    return {
        "run_id": _RUN_ID,
        "status": {"kind": "failed"},
        "goal": "Work-item: bd-peer-1\n",
        "repo_origin_url": f"https://github.com/thewoolleyman/{_PEER_REPOSITORY}",
        "labels": {
            "livespec.repository": _PEER_REPOSITORY,
            "livespec.acp.implement.availability": "codex",
            "livespec.acp.implement.candidate": "primary",
        },
        "start_time": _STARTED_AT,
        "wall_time_ms": _WALL_TIME_MS,
    }


def _transport_fault_payload() -> list[dict[str, Any]]:
    """One measured `fabro inspect --json` record of an ordinary fault."""
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


def _chain_repo(*, tmp_path: Path) -> Path:
    """A repository declaring two participating factories and one ACP chain."""
    workflow = tmp_path / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    (workflow / "workflow.toml").write_text(_CHAIN_MANIFEST, encoding="utf-8")
    (workflow / "workflow.fabro").write_text(_CHAIN_GRAPH, encoding="utf-8")
    (tmp_path / ".livespec.jsonc").write_text(_CHAIN_CONFIG, encoding="utf-8")
    return tmp_path


def _resolved(*, repo: Path, reader: Any) -> tuple[Any, Any]:
    """One admission evaluation's verdict and the wait it schedules."""
    preflight = _module(name="_dispatcher_acp_preflight")
    verdict = preflight.resolve_acp_preflight(
        repo=repo, journal_path=None, now_iso=_NOW, factory_runs=reader
    )
    return verdict, preflight.resolve_availability_wait(repo=repo, verdict=verdict, now_iso=_NOW)


def test_an_unreadable_factory_source_is_surfaced_and_retried_on_the_bounded_cadence(
    tmp_path: Path,
) -> None:
    """The clause's third verb, which neither of the first two implies.

    Both declared factories refuse their listing, so NOTHING is known about
    what either holds. The verdict stays viable -- the clause's "It MAY
    continue with candidates whose availability evidence is independently
    complete" -- and what it must additionally do is schedule the next look.
    """
    evidence = _module(name="_acp_factory_hold_evidence")
    wait_module = _module(name="_acp_availability_wait")
    repo = _chain_repo(tmp_path=tmp_path)

    verdict, wait = _resolved(repo=repo, reader=_Reader(rows={"hp": None, "vps": None}))

    assert wait is not None, "an unavailable evidence source schedules no reevaluation yet"
    assert wait.reevaluate_at == _NOW_PLUS_CADENCE
    assert wait.governing_condition == wait_module.UNAVAILABLE_EVIDENCE
    assert wait.unobservable_observations == 2
    # No chain emptied, so there is no admission-required node lacking a
    # candidate -- and the clause forbids inventing a hold identity or expiry.
    assert wait.node is None
    assert wait.nodes == ()
    assert wait.holds == ()
    # The first two verbs, asserted beside the third so the three cannot be
    # confused for one another.
    assert verdict.viable is True
    assert [entry["reason"] for entry in verdict.unobservable] == [
        evidence.LISTING_UNREADABLE,
        evidence.LISTING_UNREADABLE,
    ]


def test_a_fully_readable_factory_source_schedules_no_cadence_retry(tmp_path: Path) -> None:
    """The control: a healthy read must not schedule a retry of its own.

    Without this case, a derivation that scheduled `now + cadence` on every
    admission evaluation would satisfy the positive case above while making the
    bounded cadence unconditional -- a busy reevaluation loop in place of a
    bounded retry.

    The row is a FAILED run inside the hold window whose recorded cause is an
    ordinary transport fault, so this read spends BOTH factory reads and
    derives nothing. A control built from a row outside the window would reach
    no per-run read at all, and would then report the same empty answer whether
    or not the per-run read works.
    """
    repo = _chain_repo(tmp_path=tmp_path)
    reader = _Reader(
        rows={"hp": _rows(payload=[_failed_row()]), "vps": ()},
        payloads={("hp", _RUN_ID): _transport_fault_payload()},
    )

    verdict, wait = _resolved(repo=repo, reader=reader)

    assert verdict.viable is True
    assert verdict.unobservable == ()
    assert wait is None
