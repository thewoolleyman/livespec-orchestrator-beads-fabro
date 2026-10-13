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

import pytest
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

# The dominators of the committed graph's green terminal -- the set
# `derive_success_critical` must keep returning, unchanged by the widening.
# `fix`, `review_fix` and `disposition` are absent: a run that never goes Red
# reaches `exit` without any of them.
_COMMITTED_DOMINATORS = frozenset(
    {"dod_gate", "implement", "proof_capture", "proof_verify", "pr", "review"}
)

_NOW = "2026-10-13T12:00:00Z"
_EXPIRY = "2026-10-13T12:15:00Z"
_EARLIER_EXPIRY = "2026-10-13T12:05:00Z"
_REPROBE_SECONDS = 300
_NOW_PLUS_REPROBE = "2026-10-13T12:05:00Z"

# A graph carrying exactly the two shapes the wait derivation needs: one ACP
# node that dominates the green terminal and one that only sits on a Red path.
# Both are reachable, so both are admission-required.
_MINIMAL_GRAPH = """
    graph [stall_timeout="7200s"]
    start [shape=Mdiamond, label="Start"]
    exit  [shape=Msquare, label="Exit"]
    implement [backend="acp", acp.command="a", timeout="60s"]
    fix [backend="acp", acp.command="b", timeout="60s"]
    gate [shape=parallelogram, timeout="60s"]
    start -> implement
    implement -> gate
    gate -> exit [label="green", condition="outcome=succeeded"]
    gate -> fix [label="red"]
    fix -> gate
"""

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


def _waits() -> Any:
    """The wait module, proving its file exists first.

    The existence assertion runs BEFORE the import so an unimplemented slice
    fails on a genuine assertion rather than on a `ModuleNotFoundError`, which
    proves only unimportability and says nothing about the behaviour.
    """
    module_path = _COMMANDS / "_acp_availability_wait.py"
    assert module_path.is_file(), "_acp_availability_wait.py is not implemented yet"
    return importlib.import_module(f"{_PACKAGE}._acp_availability_wait")


def _minimal_verdict(*, chains: dict[str, Any], holds: tuple[Any, ...] = (), **inputs: Any) -> Any:
    """A verdict over `_MINIMAL_GRAPH`, whose ACP nodes are `implement` and `fix`."""
    return build_acp_preflight_verdict(
        chains=chains,
        graph_text=_MINIMAL_GRAPH,
        ledger=_ledger(holds=holds),
        inputs=_inputs(holds=holds, **inputs),
    )


def _single(*, node: str, availability_key: str = "codex") -> Any:
    return _chain(
        node=node,
        candidates=(_candidate(availability_key=availability_key, candidate_key=node),),
    )


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


def test_the_dominator_derivation_still_returns_the_narrower_success_critical_set() -> None:
    """The widening ADDED a derivation; it did not widen the existing one.

    This is the control on the obvious wrong way to satisfy its sibling above:
    make `derive_success_critical` return the reachable set. That passes every
    admission assertion in this module and silently destroys the dominator set
    the reached-node termination and the attention surfaces read -- `fix` would
    then report as a node no green path can avoid, which is false of the graph
    and would make a held `fix` indistinguishable from a held `implement` at
    every surface that tells those two apart.

    So the two sets are asserted APART, on ONE graph, in ONE verdict: the
    dominators exactly, the reachable set exactly, and the strict-subset
    relation between them. A derivation that collapsed them in either direction
    fails at least one of the three.
    """
    graph_module = importlib.import_module(f"{_PACKAGE}._acp_workflow_graph")
    critical_module = importlib.import_module(f"{_PACKAGE}._acp_success_critical")
    graph = graph_module.parse_workflow_graph(text=_WORKFLOW_GRAPH.read_text(encoding="utf-8"))

    critical = critical_module.derive_success_critical(graph=graph)
    verdict = _committed_verdict()

    assert set(critical.nodes) == _COMMITTED_DOMINATORS
    assert critical.start == "start"
    assert critical.green_terminal == "exit"
    assert set(verdict.success_critical) == _COMMITTED_DOMINATORS
    assert _COMMITTED_DOMINATORS < _COMMITTED_ACP_NODES
    assert {"fix", "review_fix", "disposition"} == _COMMITTED_ACP_NODES - _COMMITTED_DOMINATORS


def test_the_scheduled_instant_is_the_earliest_expiry_among_the_emptying_holds() -> None:
    """Earliest, across EVERY emptied chain -- not the first one encountered.

    The two holds are deliberately ordered against the graph: `implement` is
    declared first and is held until 12:15, while `fix` is declared second and
    is held only until 12:05. A derivation that took the first exhausted node's
    own expiry would schedule 12:15 and leave the item waiting ten minutes past
    the moment it became dispatchable again -- a plausible instant, in the
    right format, that no reader could tell from the correct one.
    """
    waits = _waits()
    held = (
        _hold(hold_key="codex", expires_at=_EXPIRY),
        _hold(hold_key="anthropic", expires_at=_EARLIER_EXPIRY),
    )
    verdict = _minimal_verdict(
        chains={
            "implement": _single(node="implement", availability_key="codex"),
            "fix": _single(node="fix", availability_key="anthropic"),
        },
        holds=held,
    )

    wait = waits.schedule_availability_wait(
        verdict=verdict, now_iso=_NOW, reprobe_interval_seconds=_REPROBE_SECONDS
    )

    assert verdict.exhausted == ("implement", "fix")
    assert wait.nodes == ("implement", "fix")
    assert wait.governing_condition == waits.LIVE_HOLD_CONDITION
    assert wait.scheduled_at == _EARLIER_EXPIRY
    assert wait.hold_expiries == (_EARLIER_EXPIRY, _EXPIRY)


def test_a_healthy_fallback_nodes_own_skips_do_not_schedule_the_wait() -> None:
    """Only the holds that EMPTIED a chain decide when the item is next looked at.

    `implement` keeps an eligible fallback, so it is holding nothing back, and
    its held primary carries the EARLIER expiry; `fix` is wholly held and
    lapses later. A derivation that collected every skip in the verdict would
    schedule the wait at `implement`'s primary expiry -- an instant at which
    `fix` is still held, so the next pass refuses again and the schedule the
    record reported was never true. The ordering is deliberate: with the
    expiries the other way round the wrong derivation returns the right answer.
    """
    waits = _waits()
    held = (
        _hold(hold_key="codex", expires_at=_EARLIER_EXPIRY),
        _hold(hold_key="anthropic", expires_at=_EXPIRY),
    )
    verdict = _minimal_verdict(
        chains={
            "implement": _chain(
                node="implement",
                candidates=(
                    _candidate(availability_key="codex", candidate_key="primary"),
                    _candidate(availability_key="openrouter", candidate_key="fallback"),
                ),
            ),
            "fix": _single(node="fix", availability_key="anthropic"),
        },
        holds=held,
    )

    wait = waits.schedule_availability_wait(
        verdict=verdict, now_iso=_NOW, reprobe_interval_seconds=_REPROBE_SECONDS
    )

    assert verdict.exhausted == ("fix",)
    assert wait.nodes == ("fix",)
    assert wait.governing_condition == waits.LIVE_HOLD_CONDITION
    assert wait.scheduled_at == _EXPIRY
    assert wait.hold_expiries == (_EXPIRY,)


def test_a_chain_emptied_with_no_governing_hold_waits_the_reprobe_interval() -> None:
    """The "otherwise" arm: no hold governs, so the committed dial does.

    An ephemeral credential-probe skip mints no record and carries no expiry,
    so there is no hold instant to wait for. The record must still name a
    condition and an instant without INVENTING a hold identity or expiry --
    Scenario 60's "when no hold governs the refusal, the record names the
    outstanding confirmation, unavailable evidence source, or admission-time
    credential-probe skip without inventing a hold identity or expiry".
    """
    waits = _waits()
    candidate_preflight = importlib.import_module(f"{_PACKAGE}._acp_candidate_preflight")
    verdict = _minimal_verdict(
        chains={"implement": _single(node="implement"), "fix": _single(node="fix")},
        probe=lambda _key: "exhausted",
    )

    wait = waits.schedule_availability_wait(
        verdict=verdict, now_iso=_NOW, reprobe_interval_seconds=_REPROBE_SECONDS
    )

    assert wait.governing_condition == candidate_preflight.PROBE_SKIP
    assert wait.scheduled_at == _NOW_PLUS_REPROBE
    assert wait.hold_expiries == ()


def test_a_legacy_provider_record_that_empties_a_chain_supplies_its_own_expiry() -> None:
    """A legacy record is a hold too, so its expiry schedules the wait.

    Scenario 60's "A legacy provider record remains effective during migration"
    makes the legacy blanket exhaust an admission-required chain, and its
    sibling "A chain exhausted by live holds waits until scheduled
    reevaluation" says the wait falls at "the earliest expiry among the
    covering holds" -- current or legacy. Reading only TYPED expiries would
    quietly route every legacy-governed wait onto the reprobe interval, which
    is the "otherwise" arm reached while a hold does in fact govern.
    """
    waits = _waits()
    verdict = _minimal_verdict(
        chains={"implement": _single(node="implement"), "fix": _single(node="fix")},
        legacy_provider_expiries={"codex": _EARLIER_EXPIRY},
        builtin_pairs=frozenset({("codex", "implement"), ("codex", "fix")}),
    )

    wait = waits.schedule_availability_wait(
        verdict=verdict, now_iso=_NOW, reprobe_interval_seconds=_REPROBE_SECONDS
    )

    assert verdict.exhausted == ("implement", "fix")
    assert wait.governing_condition == waits.LIVE_HOLD_CONDITION
    assert wait.scheduled_at == _EARLIER_EXPIRY
    assert wait.hold_expiries == (_EARLIER_EXPIRY,)


def test_a_viable_verdict_schedules_no_wait_at_all() -> None:
    """Nothing is waiting, so there is no instant to name.

    The positive control for the three cases above: a derivation that always
    returned a wait would satisfy every one of them while parking a healthy
    repository on a schedule nothing asked for.
    """
    waits = _waits()
    verdict = _minimal_verdict(
        chains={"implement": _single(node="implement"), "fix": _single(node="fix")}
    )

    assert verdict.viable is True
    assert (
        waits.schedule_availability_wait(
            verdict=verdict, now_iso=_NOW, reprobe_interval_seconds=_REPROBE_SECONDS
        )
        is None
    )


def test_an_unreadable_evaluation_clock_raises_rather_than_naming_an_instant() -> None:
    """A bug, raised -- never an invented instant and never `now` itself.

    The clock is the Dispatcher's own `utc_now_iso()`, so an unparseable value
    is a bug rather than an expected error. Both soft alternatives are worse
    than raising: falling back to `now` schedules an immediate retry, which is
    the busy loop the clause forbids, and omitting the instant leaves the
    refusal record without the one field an operator reads to learn when the
    item moves again.
    """
    waits = _waits()
    verdict = _minimal_verdict(
        chains={"implement": _single(node="implement"), "fix": _single(node="fix")},
        probe=lambda _key: "exhausted",
    )

    with pytest.raises(ValueError, match="not an ISO-8601 instant"):
        _ = waits.schedule_availability_wait(
            verdict=verdict, now_iso="not-an-instant", reprobe_interval_seconds=_REPROBE_SECONDS
        )
