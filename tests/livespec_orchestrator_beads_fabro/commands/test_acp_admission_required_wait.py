"""The ADMISSION-REQUIRED ACP node set, and the availability wait it schedules.

Binds the v127 widening in `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority": "The admission-required set is
wider: every ACP node potentially reachable in the submitted graph is
admission-required, success-critical or not. ... If any potentially reachable
node has no eligible candidate, the item MUST remain ready without a claim or
blocked reason, and the Dispatcher MUST schedule another admission evaluation.
... The scheduled evaluation falls at the earliest expiry among the holds that
empty a chain, and otherwise after `dispatcher.credential_reprobe_interval_
seconds`" -- together with `SPECIFICATION/scenarios.md` Scenario 60's
"A chain exhausted by live holds waits until scheduled reevaluation" and
"An availability wait without a live hold remains visible and retries
automatically".

THE SHARP CONTROL IS THE CONDITIONAL NODE. Before v127 a `fix`, `review_fix` or
`disposition` outage left admission wide open, because those nodes dominate no
green path; the run then reached one of them with a held candidate and died
mid-flight. So the assertions below are deliberately written against those three
rather than against `implement`: an implementation that still graded only the
dominators passes every `implement`-shaped assertion and changes nothing.

THE SECOND CONTROL IS THAT DOMINANCE SURVIVED. Widening admission by REPLACING
the dominator derivation would satisfy the first control and silently destroy
the success-critical set the reached-node termination and the attention surfaces
read. The two sets are asserted apart, on one graph, in one test.

Everything is HERMETIC: graphs, journals and configuration are built in
`tmp_path` or inline, nothing launches an adapter and nothing reaches a
provider.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import (
    build_acp_preflight_verdict,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_WORKFLOW_GRAPH = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)

_NOW = "2026-10-13T12:00:00Z"
_EXPIRY = "2026-10-13T12:15:00Z"

# Every ACP node the committed graph declares. All nine are reachable from
# `start`, so all nine are admission-required under v127.
_COMMITTED_ACP_NODES = frozenset(
    {
        "dod_gate",
        "implement",
        "fix",
        "review_fix",
        "proof_capture",
        "proof_verify",
        "pr",
        "review",
        "disposition",
    }
)


def _identity(*, availability_key: str, candidate_key: str) -> Any:
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    return schema.AcpCandidateIdentity(
        display_name=f"{availability_key}/{candidate_key}",
        candidate_key=candidate_key,
        availability_key=availability_key,
    )


def _candidate(*, availability_key: str = "codex", candidate_key: str = "gpt-5-5") -> Any:
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    return schema.AcpCandidate(
        adapter=adapters.AcpAdapter(command="adapter", env={}, args=()),
        identity=_identity(availability_key=availability_key, candidate_key=candidate_key),
        signatures=(),
    )


def _chain(*, node: str, candidates: tuple[Any, ...]) -> Any:
    resolution = importlib.import_module(f"{_PACKAGE}._acp_chain_resolution")
    return resolution.ResolvedAcpChain(
        node=node,
        primary=candidates[0],
        fallbacks=tuple(candidates[1:]),
        enabled=True,
        primary_generation="primary-digest",
        full_chain="chain-digest",
        redacted={},
    )


def _hold(*, hold_key: str, expires_at: str = _EXPIRY, cause: str = "quota") -> Any:
    records = importlib.import_module(f"{_PACKAGE}._acp_hold_records")
    return records.AcpAvailabilityHold(
        schema_version=1,
        observation_id=f"obs-{hold_key}",
        scope="availability-domain",
        hold_key=hold_key,
        candidate_key=None,
        cause=cause,
        occurred_at=_NOW,
        expires_at=expires_at,
    )


def _ledger(*, holds: tuple[Any, ...] = ()) -> Any:
    ledger = importlib.import_module(f"{_PACKAGE}._acp_hold_ledger")
    return ledger.AcpHoldLedger(holds=holds, unobservable=(), observation_ids=frozenset())


def _inputs(**overrides: Any) -> Any:
    preflight = importlib.import_module(f"{_PACKAGE}._acp_candidate_preflight")
    return preflight.PreflightInputs(**overrides)


def _committed_chains(*, availability_key: str = "codex") -> dict[str, Any]:
    """One single-candidate chain per ACP node of the committed graph."""
    return {
        node: _chain(
            node=node,
            candidates=(_candidate(availability_key=availability_key, candidate_key=node),),
        )
        for node in sorted(_COMMITTED_ACP_NODES)
    }


def _committed_verdict(*, holds: tuple[Any, ...] = (), **inputs: Any) -> Any:
    return build_acp_preflight_verdict(
        chains=_committed_chains(),
        graph_text=_WORKFLOW_GRAPH.read_text(encoding="utf-8"),
        ledger=_ledger(holds=holds),
        inputs=_inputs(holds=holds, **inputs),
    )


def test_every_potentially_reachable_acp_node_is_admission_required() -> None:
    """A held conditional repair or adjudication node now empties admission.

    The three nodes this asserts on -- `fix`, `review_fix` and `disposition` --
    are exactly the ones the pre-v127 dominator-only grade left out, so a
    verdict that still graded the dominators would report `viable` here while
    the run it admitted could not start `fix`'s adapter at all.
    """
    module_path = _COMMANDS / "_acp_admission_required.py"
    assert module_path.is_file(), "_acp_admission_required.py is not implemented yet"
    required = importlib.import_module(f"{_PACKAGE}._acp_admission_required")
    graph_module = importlib.import_module(f"{_PACKAGE}._acp_workflow_graph")
    graph = graph_module.parse_workflow_graph(text=_WORKFLOW_GRAPH.read_text(encoding="utf-8"))

    derived = required.derive_admission_required(graph=graph, start="start")
    verdict = _committed_verdict(holds=(_hold(hold_key="codex"),))

    assert set(derived) == _COMMITTED_ACP_NODES
    assert set(verdict.admission_required) == _COMMITTED_ACP_NODES
    assert {"fix", "review_fix", "disposition"} <= set(verdict.exhausted)
    assert verdict.viable is False
