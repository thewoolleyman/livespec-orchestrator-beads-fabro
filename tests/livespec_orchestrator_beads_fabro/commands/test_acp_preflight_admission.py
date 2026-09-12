"""Success-critical ACP preflight: filtering, derivation, admission, attention.

Binds the S3 half of `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority" -- the per-node candidate
preflight, the success-critical derivation from green-terminal dominators, the
one verdict admission / rework admission / wait attention / idle-factory all
consume, and the typed termination a REACHED empty chain produces -- together
with the Scenario 127 scenario that governs them, "Only an exhausted
success-critical chain refuses admission".

FIVE CONTROLS CARRY MOST OF THE WEIGHT, because each is a claim an
almost-correct implementation gets backwards:

- The success-critical set is the DOMINATORS of the green terminal, not the
  nodes on some green path. `fix` and `review_fix` sit on real green paths and
  must NOT be admission-required; a derivation that walked one path would
  include them and would then park healthy work on a conditional node's outage.
- A locally unusable PRIMARY with a viable fallback leaves the chain viable. A
  preflight that refused on the primary alone passes every single-candidate
  test and defeats the entire feature.
- A credential is assessed at most ONCE per evaluation. A per-candidate probe
  returns two answers for one credential and cannot be told apart from a
  correct one by counting skips -- only by counting probe calls.
- An unknown `schema_version` is neither interpreted NOR ignored. Both wrong
  answers look like "no hold", so the control asserts the record is carried.
- The no-fallback path is a TOTAL no-op. Every other assertion here would pass
  on an implementation that quietly refused a repository using no chains.

Everything is HERMETIC: graphs and journals are built in `tmp_path` or inline,
nothing launches an adapter and nothing reaches a provider.
"""

from __future__ import annotations

import argparse
import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

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

_NEW_MODULES = (
    "_acp_workflow_graph",
    "_acp_success_critical",
    "_acp_candidate_preflight",
    "_acp_preflight_verdict",
    "_acp_reached_termination",
    "_dispatcher_acp_preflight",
)

_NOW = "2026-09-12T12:00:00Z"

# A minimal graph carrying every shape the derivation reads: one start, one
# green terminal, one ACP node dominating it, and one ACP node that does not.
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


def _modules() -> dict[str, Any]:
    """Import the slice's modules, proving each file exists first."""
    for name in _NEW_MODULES:
        assert (_COMMANDS / f"{name}.py").is_file(), f"{name}.py is not implemented yet"
    return {name: importlib.import_module(f"{_PACKAGE}.{name}") for name in _NEW_MODULES}


@dataclass(kw_only=True)
class _MemoryJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _identity(*, availability_key: str, candidate_key: str) -> Any:
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    return schema.AcpCandidateIdentity(
        display_name=f"{availability_key}/{candidate_key}",
        candidate_key=candidate_key,
        availability_key=availability_key,
    )


def _candidate(
    *,
    availability_key: str | None = "codex",
    candidate_key: str = "gpt-5-5",
    signatures: tuple[Any, ...] = (),
) -> Any:
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    identity = (
        None
        if availability_key is None
        else _identity(availability_key=availability_key, candidate_key=candidate_key)
    )
    return schema.AcpCandidate(
        adapter=adapters.AcpAdapter(command="adapter", env={}, args=()),
        identity=identity,
        signatures=signatures,
    )


def _domain_signature(*, hold_key: str) -> Any:
    signatures = importlib.import_module(f"{_PACKAGE}._acp_candidate_signatures")
    return signatures.AcpAvailabilitySignature(
        source="protocol.message",
        cause="quota",
        scope="availability-domain",
        all_literals=("usage limit",),
        hold_key=hold_key,
    )


def _chain(*, node: str, candidates: tuple[Any, ...], enabled: bool = True) -> Any:
    resolution = importlib.import_module(f"{_PACKAGE}._acp_chain_resolution")
    return resolution.ResolvedAcpChain(
        node=node,
        primary=candidates[0],
        fallbacks=tuple(candidates[1:]),
        enabled=enabled,
        primary_generation="primary-digest",
        full_chain="chain-digest",
        redacted={},
    )


def _hold(
    *,
    scope: str,
    hold_key: str,
    candidate_key: str | None = None,
    cause: str = "quota",
) -> Any:
    records = importlib.import_module(f"{_PACKAGE}._acp_hold_records")
    return records.AcpAvailabilityHold(
        schema_version=1,
        observation_id="obs-1",
        scope=scope,
        hold_key=hold_key,
        candidate_key=candidate_key,
        cause=cause,
        occurred_at=_NOW,
        expires_at="2026-09-12T13:00:00Z",
    )


def _ledger(*, holds: tuple[Any, ...] = (), unobservable: tuple[Any, ...] = ()) -> Any:
    ledger = importlib.import_module(f"{_PACKAGE}._acp_hold_ledger")
    return ledger.AcpHoldLedger(holds=holds, unobservable=unobservable, observation_ids=frozenset())


def _inputs(**overrides: Any) -> Any:
    preflight = importlib.import_module(f"{_PACKAGE}._acp_candidate_preflight")
    return preflight.PreflightInputs(**overrides)


def _keys(*, preflight: Any) -> list[str | None]:
    return [
        None if candidate.identity is None else candidate.identity.candidate_key
        for candidate in preflight.candidates
    ]


def _filter(*, chain: Any, inputs: Any, assessed: dict[str, str] | None = None) -> Any:
    module = importlib.import_module(f"{_PACKAGE}._acp_candidate_preflight")
    return module.filter_node_candidates(
        chain=chain, inputs=inputs, assessed={} if assessed is None else assessed
    )


def test_the_committed_graph_resolves_exactly_implement_review_and_pr() -> None:
    """The contract's named set, derived rather than spelled.

    This is the one control that ties the derivation to the real workflow. It
    also proves the negative half that matters: `fix`, `review_fix` and
    `disposition` are ACP nodes on green paths and are NOT admission-required,
    because a run that never goes Red reaches `exit` without any of them.
    """
    modules = _modules()
    graph = modules["_acp_workflow_graph"].parse_workflow_graph(
        text=_WORKFLOW_GRAPH.read_text(encoding="utf-8")
    )
    critical = modules["_acp_success_critical"].derive_success_critical(graph=graph)

    assert set(critical.nodes) == {"implement", "review", "pr"}
    assert critical.start == "start"
    assert critical.green_terminal == "exit"
    assert set(graph.acp_names) == {
        "implement",
        "fix",
        "review_fix",
        "pr",
        "review",
        "disposition",
    }


def test_a_conditional_acp_node_on_a_green_path_is_not_success_critical() -> None:
    """`side` is reachable, runs an adapter, and still dominates nothing."""
    modules = _modules()
    graph = modules["_acp_workflow_graph"].parse_workflow_graph(text=_MINIMAL_GRAPH)
    critical = modules["_acp_success_critical"].derive_success_critical(graph=graph)

    assert critical.nodes == ("implement",)
    assert "fix" in graph.acp_names


def test_a_node_attribute_is_bound_to_its_first_value() -> None:
    """A script attribute's escaped quotes cannot displace an earlier `shape`."""
    modules = _modules()
    text = '    node [shape=parallelogram, script="echo \\"shape=Msquare\\""]\n'
    graph = modules["_acp_workflow_graph"].parse_workflow_graph(text=text)

    assert graph.nodes[0].shape == "parallelogram"
    assert graph.nodes[0].is_acp is False
    assert graph.names == ("node",)


def test_a_repeated_node_declaration_is_read_once() -> None:
    modules = _modules()
    text = "    node [shape=Mdiamond]\n    node [shape=Msquare]\n"
    graph = modules["_acp_workflow_graph"].parse_workflow_graph(text=text)

    assert graph.names == ("node",)
    assert graph.with_shape(shape="Mdiamond") == ("node",)


def test_graph_predecessors_and_successors_read_declared_edges() -> None:
    modules = _modules()
    graph = modules["_acp_workflow_graph"].parse_workflow_graph(text=_MINIMAL_GRAPH)

    assert graph.successors(node="gate") == ("exit", "fix")
    assert graph.predecessors(node="gate") == ("implement", "fix")


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("    exit [shape=Msquare]\n", "declares no start node"),
        ("    start [shape=Mdiamond]\n", "declares no green terminal node"),
        (
            "    a [shape=Mdiamond]\n    b [shape=Mdiamond]\n    e [shape=Msquare]\n",
            "declares 2 start nodes",
        ),
        (
            "    a [shape=Mdiamond]\n    e [shape=Msquare]\n    f [shape=Msquare]\n",
            "declares 2 green terminal nodes",
        ),
        (
            "    a [shape=Mdiamond]\n    e [shape=Msquare]\n    e -> a\n",
            "declares outgoing edges",
        ),
        ("    a [shape=Mdiamond]\n    e [shape=Msquare]\n", "is unreachable from start"),
    ],
)
def test_an_unsupported_or_ambiguous_graph_refuses_deterministically(
    text: str, fragment: str
) -> None:
    """Each end fault refuses with its own explanation, never an empty set.

    An empty success-critical set would ADMIT every dispatch, which is the
    fail-open direction on the one gate that exists to hold work back.
    """
    modules = _modules()
    graph = modules["_acp_workflow_graph"].parse_workflow_graph(text=text)
    refusal = modules["_acp_success_critical"].derive_success_critical(graph=graph)

    assert isinstance(refusal, str)
    assert fragment in refusal


def test_candidate_preflight_retains_configured_order_after_filtering() -> None:
    """The middle candidate is held; the survivors keep primary-then-fallback order."""
    modules = _modules()
    chain = _chain(
        node="implement",
        candidates=(
            _candidate(candidate_key="one"),
            _candidate(candidate_key="two"),
            _candidate(candidate_key="three"),
        ),
    )
    result = _filter(
        chain=chain,
        inputs=_inputs(holds=(_hold(scope="candidate", hold_key="codex", candidate_key="two"),)),
    )

    assert _keys(preflight=result) == ["one", "three"]
    assert [skip.candidate_key for skip in result.skipped] == ["two"]
    assert result.skipped[0].reason == modules["_acp_candidate_preflight"].TYPED_HOLD_SKIP
    assert result.exhausted is False


def test_a_domain_hold_skips_every_candidate_in_its_domain() -> None:
    chain = _chain(
        node="implement",
        candidates=(
            _candidate(availability_key="codex", candidate_key="one"),
            _candidate(availability_key="codex", candidate_key="two"),
            _candidate(availability_key="anthropic", candidate_key="three"),
        ),
    )
    result = _filter(
        chain=chain, inputs=_inputs(holds=(_hold(scope="availability-domain", hold_key="codex"),))
    )

    assert _keys(preflight=result) == ["three"]


def test_a_domain_hold_reaches_a_declared_override_hold_key() -> None:
    """A candidate routing through a shared pool is skipped by a hold on the pool."""
    chain = _chain(
        node="implement",
        candidates=(
            _candidate(
                availability_key="router-a",
                candidate_key="one",
                signatures=(_domain_signature(hold_key="shared-pool"),),
            ),
            _candidate(availability_key="router-b", candidate_key="two"),
        ),
    )
    result = _filter(
        chain=chain,
        inputs=_inputs(holds=(_hold(scope="availability-domain", hold_key="shared-pool"),)),
    )

    assert _keys(preflight=result) == ["two"]


def test_a_live_legacy_provider_record_covers_a_matching_builtin_candidate() -> None:
    """The legacy blanket is wide for a built-in alias and bounded elsewhere.

    The second candidate spells the SAME provider string but is not a built-in
    this build rendered, so broadening the legacy vendor record onto it is the
    "unrelated identities" case the contract forbids.
    """
    modules = _modules()
    builtin = _candidate(availability_key="codex", candidate_key="builtin")
    chain = _chain(
        node="implement",
        candidates=(builtin, _candidate(availability_key="codex", candidate_key="operator")),
    )
    result = _filter(
        chain=chain,
        inputs=_inputs(
            legacy_providers=frozenset({"codex"}),
            builtin_pairs=frozenset({("codex", "builtin")}),
        ),
    )

    assert _keys(preflight=result) == ["operator"]
    assert result.skipped[0].reason == modules["_acp_candidate_preflight"].LEGACY_HOLD_SKIP
    assert result.skipped[0].hold_key == "codex"


def test_a_live_legacy_record_covers_an_identity_less_legacy_candidate() -> None:
    chain = _chain(
        node="implement",
        candidates=(_candidate(availability_key=None), _candidate(availability_key="anthropic")),
    )
    result = _filter(chain=chain, inputs=_inputs(legacy_providers=frozenset({"codex"})))

    assert _keys(preflight=result) == ["gpt-5-5"]
    assert result.skipped[0].availability_key is None


def test_typed_candidate_evidence_outranks_legacy_attribution_of_the_same_candidate() -> None:
    """Both records cover it; the skip is attributed to the TYPED one.

    Ordering IS the precedence rule here, so the observable claim is the
    reported reason and cause rather than the selectable set -- both records
    remove the candidate, and only the attribution tells them apart.
    """
    modules = _modules()
    chain = _chain(
        node="implement",
        candidates=(
            _candidate(availability_key="codex", candidate_key="builtin"),
            _candidate(availability_key="anthropic", candidate_key="other"),
        ),
    )
    result = _filter(
        chain=chain,
        inputs=_inputs(
            holds=(
                _hold(
                    scope="candidate",
                    hold_key="codex",
                    candidate_key="builtin",
                    cause="model_not_entitled",
                ),
            ),
            legacy_providers=frozenset({"codex"}),
            builtin_pairs=frozenset({("codex", "builtin")}),
        ),
    )

    assert _keys(preflight=result) == ["other"]
    assert result.skipped[0].reason == modules["_acp_candidate_preflight"].TYPED_HOLD_SKIP
    assert result.skipped[0].cause == "model_not_entitled"


def test_each_credential_is_assessed_at_most_once_per_evaluation() -> None:
    """Two candidates on one account cost one probe, and the memo is shared across nodes."""
    calls: list[str] = []

    def probe(key: str) -> str:
        calls.append(key)
        return "usable"

    assessed: dict[str, str] = {}
    for node in ("implement", "review"):
        chain = _chain(
            node=node,
            candidates=(
                _candidate(availability_key="codex", candidate_key="one"),
                _candidate(availability_key="codex", candidate_key="two"),
                _candidate(availability_key="anthropic", candidate_key="three"),
            ),
        )
        result = _filter(chain=chain, inputs=_inputs(probe=probe), assessed=assessed)
        assert len(result.candidates) == 3

    assert calls == ["codex", "anthropic"]


def test_a_provider_limit_probe_refusal_is_an_ephemeral_candidate_local_skip() -> None:
    """No journal, no hold, no expiry, and no broadening onto the other domain."""
    modules = _modules()
    chain = _chain(
        node="implement",
        candidates=(
            _candidate(availability_key="codex", candidate_key="one"),
            _candidate(availability_key="anthropic", candidate_key="two"),
        ),
    )
    result = _filter(
        chain=chain,
        inputs=_inputs(probe=lambda key: "exhausted" if key == "codex" else "usable"),
    )

    assert _keys(preflight=result) == ["two"]
    skip = result.skipped[0]
    assert skip.reason == modules["_acp_candidate_preflight"].PROBE_SKIP
    assert skip.condition == "exhausted"
    # An ephemeral local condition is NOT one of the eight typed availability
    # causes, and writing it into `cause` would make the two indistinguishable.
    assert skip.cause is None
    assert skip.hold_key is None


def test_a_probe_refusal_no_fallback_governs_leaves_the_candidate_selectable() -> None:
    """An absent or revoked credential is a fault no fallback repairs."""
    chain = _chain(node="implement", candidates=(_candidate(candidate_key="one"),))
    result = _filter(chain=chain, inputs=_inputs(probe=lambda _key: "revoked"))

    assert _keys(preflight=result) == ["one"]
    assert result.skipped == ()


def test_an_identity_less_candidate_is_never_probed() -> None:
    calls: list[str] = []
    chain = _chain(node="implement", candidates=(_candidate(availability_key=None),))
    result = _filter(chain=chain, inputs=_inputs(probe=lambda key: calls.append(key) or "usable"))

    assert calls == []
    assert len(result.candidates) == 1


def test_a_locally_unusable_primary_with_a_viable_fallback_stays_viable() -> None:
    """The control the whole feature turns on, at verdict level."""
    modules = _modules()
    chains = {
        node: _chain(
            node=node,
            candidates=(
                _candidate(availability_key="codex", candidate_key="primary"),
                _candidate(availability_key="anthropic", candidate_key="fallback"),
            ),
        )
        for node in ("implement",)
    }
    verdict = modules["_acp_preflight_verdict"].build_acp_preflight_verdict(
        chains=chains,
        graph_text=_MINIMAL_GRAPH,
        ledger=_ledger(),
        inputs=_inputs(probe=lambda key: "exhausted" if key == "codex" else "usable"),
    )

    assert verdict.viable is True
    assert verdict.exhausted == ()
    assert verdict.success_critical == ("implement",)
    assert _keys(preflight=verdict.node_preflight(node="implement")) == ["fallback"]
    assert modules["_dispatcher_acp_preflight"].credential_reprobe_wait_applies(
        verdict=verdict
    ) is (False)


def test_an_exhausted_success_critical_chain_makes_the_verdict_refuse() -> None:
    modules = _modules()
    verdict = modules["_acp_preflight_verdict"].build_acp_preflight_verdict(
        chains={
            "implement": _chain(node="implement", candidates=(_candidate(candidate_key="only"),))
        },
        graph_text=_MINIMAL_GRAPH,
        ledger=_ledger(holds=(_hold(scope="availability-domain", hold_key="codex"),)),
        inputs=_inputs(holds=(_hold(scope="availability-domain", hold_key="codex"),)),
    )

    assert verdict.viable is False
    assert verdict.exhausted == ("implement",)
    assert verdict.detail == "no candidate remains for success-critical ACP node implement"
    assert modules["_dispatcher_acp_preflight"].credential_reprobe_wait_applies(verdict=verdict)


def test_an_exhausted_conditional_chain_alone_still_admits() -> None:
    """Scenario 127: a conditional node with no candidate does not refuse admission."""
    modules = _modules()
    held = (_hold(scope="availability-domain", hold_key="codex"),)
    verdict = modules["_acp_preflight_verdict"].build_acp_preflight_verdict(
        chains={
            "implement": _chain(
                node="implement",
                candidates=(_candidate(availability_key="anthropic", candidate_key="ok"),),
            ),
            "fix": _chain(node="fix", candidates=(_candidate(candidate_key="held"),)),
        },
        graph_text=_MINIMAL_GRAPH,
        ledger=_ledger(holds=held),
        inputs=_inputs(holds=held),
    )

    assert verdict.viable is True
    assert verdict.node_preflight(node="fix").exhausted is True
    assert verdict.node_preflight(node="missing") is None


def test_a_reached_conditional_empty_chain_terminates_typed_before_any_adapter() -> None:
    """It carries the typed cause, traverses nothing, and is not a work failure."""
    modules = _modules()
    termination = modules["_acp_reached_termination"]
    held = (_hold(scope="availability-domain", hold_key="codex", cause="model_unavailable"),)
    result = _filter(
        chain=_chain(node="fix", candidates=(_candidate(candidate_key="held"),)),
        inputs=_inputs(holds=held),
    )
    terminal = termination.reached_node_termination(preflight=result)

    assert terminal.cause == "model_unavailable"
    assert terminal.scope == "availability-domain"
    assert terminal.hold_key == "codex"
    assert terminal.node == "fix"
    assert terminal.stage == termination.TERMINATION_STAGE
    assert terminal.successor is None
    assert terminal.is_deterministic_work_failure is False
    assert terminal.stage not in termination.FORBIDDEN_SUCCESSORS
    assert "terminating before adapter startup" in terminal.detail


def test_a_reached_node_with_a_candidate_produces_no_termination() -> None:
    modules = _modules()
    result = _filter(
        chain=_chain(node="fix", candidates=(_candidate(candidate_key="ok"),)), inputs=_inputs()
    )

    assert modules["_acp_reached_termination"].reached_node_termination(preflight=result) is None


def test_a_chain_emptied_only_by_probe_refusals_terminates_unattributed() -> None:
    """An ephemeral local condition never masquerades as an observed outage."""
    modules = _modules()
    termination = modules["_acp_reached_termination"]
    result = _filter(
        chain=_chain(node="fix", candidates=(_candidate(candidate_key="one"),)),
        inputs=_inputs(probe=lambda _key: "rate_limited"),
    )
    terminal = termination.reached_node_termination(preflight=result)

    assert terminal.cause == termination.UNATTRIBUTED_CAUSE
    assert terminal.scope is None
    assert terminal.candidate_key is None


def test_an_unknown_observation_version_is_carried_and_never_interpreted() -> None:
    """Neither read on v1's meanings nor discarded as ordinary empty hold state."""
    modules = _modules()
    unknown = ({"schema_version": 9, "scope": "availability-domain", "hold_key": "codex"},)
    verdict = modules["_acp_preflight_verdict"].build_acp_preflight_verdict(
        chains={
            "implement": _chain(node="implement", candidates=(_candidate(candidate_key="only"),))
        },
        graph_text=_MINIMAL_GRAPH,
        ledger=_ledger(unobservable=unknown),
        inputs=_inputs(),
    )

    # Not interpreted: the candidate its fields NAME is still selectable.
    assert _keys(preflight=verdict.node_preflight(node="implement")) == ["only"]
    assert verdict.viable is True
    # Not ignored: the record rides the verdict verbatim.
    assert verdict.unobservable == unknown


def test_a_verdict_over_an_unsupported_graph_refuses_and_still_carries_unobservables() -> None:
    modules = _modules()
    unknown = ({"schema_version": 9},)
    verdict = modules["_acp_preflight_verdict"].build_acp_preflight_verdict(
        chains={"implement": _chain(node="implement", candidates=(_candidate(),))},
        graph_text="    start [shape=Mdiamond]\n",
        ledger=_ledger(unobservable=unknown),
        inputs=_inputs(),
    )

    assert verdict.viable is False
    assert "declares no green terminal node" in verdict.detail
    assert verdict.unobservable == unknown


def test_a_verdict_with_no_readable_graph_refuses_rather_than_guessing() -> None:
    modules = _modules()
    verdict = modules["_acp_preflight_verdict"].build_acp_preflight_verdict(
        chains={"implement": _chain(node="implement", candidates=(_candidate(),))},
        graph_text=None,
        ledger=_ledger(),
        inputs=_inputs(),
    )

    assert verdict.viable is False
    assert "could not be read" in verdict.detail


def test_two_exhausted_nodes_render_a_plural_deterministic_explanation() -> None:
    modules = _modules()
    held = (_hold(scope="availability-domain", hold_key="codex"),)
    graph = """
    start [shape=Mdiamond]
    exit  [shape=Msquare]
    implement [backend="acp", acp.command="a"]
    review    [backend="acp", acp.command="b"]
    start -> implement
    implement -> review
    review -> exit
"""
    verdict = modules["_acp_preflight_verdict"].build_acp_preflight_verdict(
        chains={
            "implement": _chain(node="implement", candidates=(_candidate(candidate_key="a"),)),
            "review": _chain(node="review", candidates=(_candidate(candidate_key="b"),)),
        },
        graph_text=graph,
        ledger=_ledger(holds=held),
        inputs=_inputs(holds=held),
    )

    assert verdict.detail.startswith("no candidate remains for success-critical ACP nodes ")
    assert set(verdict.exhausted) == {"implement", "review"}


def test_a_repository_with_no_fallback_configuration_gets_a_total_no_op() -> None:
    """The additive guarantee, as the early return rather than as luck."""
    modules = _modules()
    verdict = modules["_acp_preflight_verdict"].build_acp_preflight_verdict(
        chains={"implement": _chain(node="implement", candidates=(_candidate(),), enabled=False)},
        graph_text=None,
        ledger=_ledger(),
        inputs=_inputs(),
    )

    assert verdict == modules["_acp_preflight_verdict"].no_fallback_verdict()
    assert verdict.viable is True
    assert verdict.fallback_enabled is False
    # The legacy single-candidate re-probe wait is unchanged by this slice.
    assert modules["_dispatcher_acp_preflight"].credential_reprobe_wait_applies(verdict=verdict)


def test_this_repository_resolves_the_viable_no_op_verdict(tmp_path: Path) -> None:
    """The live composer, against both this repo and an empty target."""
    modules = _modules()
    composer = modules["_dispatcher_acp_preflight"]

    for repo in (_REPO_ROOT, tmp_path):
        verdict = composer.resolve_acp_preflight(repo=repo, journal_path=None, now_iso=_NOW)
        assert verdict.fallback_enabled is False
        assert verdict.viable is True


def test_a_malformed_chain_table_refuses_before_claim(tmp_path: Path) -> None:
    """Fail-closed: an unresolvable chain table refuses earlier than the run path."""
    modules = _modules()
    (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"acp_nodes": '
        '{"implement": {"fallbacks": [{"candidate_key": "x"}]}}}}}',
        encoding="utf-8",
    )
    verdict = modules["_dispatcher_acp_preflight"].resolve_acp_preflight(
        repo=tmp_path, journal_path=None, now_iso=_NOW
    )

    assert verdict.viable is False
    assert verdict.fallback_enabled is True


def test_admission_refuses_both_legs_on_one_shared_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Initial and rework admission consume the SAME verdict, and both refuse."""
    modules = _modules()
    admission_module = importlib.import_module(f"{_PACKAGE}._dispatcher_admission")
    eligibility_module = importlib.import_module(f"{_PACKAGE}._dispatcher_admission_eligibility")
    monkeypatch.setattr(admission_module, "store_config", lambda **_: tmp_path)
    monkeypatch.setattr(admission_module, "update_work_item_status", lambda **_: None)
    monkeypatch.setattr(eligibility_module, "read_dispatch_labels", lambda **_: ())
    monkeypatch.setattr(
        admission_module,
        "claimed_active_accounting",
        lambda **_: _Accounting(rework_pending_active_ids=("bd-ib-rework",)),
    )
    io_module = importlib.import_module(f"{_PACKAGE}._dispatcher_io")
    journal = io_module.JournalFile(path=tmp_path / "journal.jsonl")
    verdict = modules["_acp_preflight_verdict"].AcpPreflightVerdict(
        fallback_enabled=True, success_critical=("implement",), exhausted=("implement",)
    )
    monkeypatch.setattr(admission_module, "resolve_acp_preflight", lambda **_: verdict)

    admission = admission_module.admit_and_select(
        repo=tmp_path,
        items=[_item(id="bd-ib-rework", status="active", assignee="fabro")],
        candidates=[_item(id="bd-ib-ready", status="ready")],
        journal=journal,
        enforce_cap=False,
    )

    stage = modules["_dispatcher_acp_preflight"].ACP_PREFLIGHT_REFUSAL_STAGE
    assert admission.admitted == []
    assert admission.rework == []
    # One refusal per leg, from ONE verdict: the marked rework row and the
    # ready candidate are refused on identical terms.
    assert [outcome.stage for outcome in admission.refused] == [stage, stage]
    assert {outcome.work_item_id for outcome in admission.refused} == {
        "bd-ib-rework",
        "bd-ib-ready",
    }
    assert admission.refused[0].detail.startswith("acp preflight refusal: ")
    refusals = [
        record
        for record in _journal_records(path=tmp_path / "journal.jsonl")
        if record.get("stage") == stage
    ]
    assert [record["exhausted"] for record in refusals] == [["implement"], ["implement"]]
    assert refusals[0]["success_critical"] == ["implement"]


def _journal_records(*, path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


@dataclass(frozen=True, kw_only=True)
class _Accounting:
    """The accounting verdict, stubbed so the rework leg has a marked row."""

    active_count: int = 0
    live_lock_active_ids: tuple[str, ...] = ()
    journal_unreadable_active_ids: tuple[str, ...] = ()
    green_terminal_active_ids: tuple[str, ...] = ()
    rework_pending_active_ids: tuple[str, ...] = ()


def test_admission_admits_normally_under_a_viable_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    modules = _modules()
    admission_module = importlib.import_module(f"{_PACKAGE}._dispatcher_admission")
    eligibility_module = importlib.import_module(f"{_PACKAGE}._dispatcher_admission_eligibility")
    monkeypatch.setattr(admission_module, "store_config", lambda **_: tmp_path)
    monkeypatch.setattr(admission_module, "update_work_item_status", lambda **_: None)
    monkeypatch.setattr(eligibility_module, "read_dispatch_labels", lambda **_: ())
    journal = _MemoryJournal()

    admission = admission_module.admit_and_select(
        repo=tmp_path,
        items=[],
        candidates=[_item(id="bd-ib-ready", status="ready")],
        journal=journal,
        enforce_cap=False,
    )

    assert [item.id for item in admission.admitted] == ["bd-ib-ready"]
    stage = modules["_dispatcher_acp_preflight"].ACP_PREFLIGHT_REFUSAL_STAGE
    assert [record for record in journal.records if record.get("stage") == stage] == []


def test_the_credential_reprobe_wait_is_skipped_while_a_fallback_is_viable(
    tmp_path: Path,
) -> None:
    """A viable fallback cannot start the legacy wait, and cannot hold the loop."""
    modules = _modules()
    reprobe = importlib.import_module(f"{_PACKAGE}._dispatcher_credential_reprobe")
    journal = _MemoryJournal()
    viable = modules["_acp_preflight_verdict"].AcpPreflightVerdict(
        fallback_enabled=True, success_critical=("implement",)
    )

    reprobe.await_usable_credential(
        repo=tmp_path,
        journal=journal,
        budget=1,
        probe=lambda **_: pytest.fail("a viable chain must not be probed"),
        sleep=lambda _seconds: pytest.fail("a viable chain must not wait"),
        preflight=viable,
    )

    assert journal.records == []


def test_the_loop_wave_hands_its_resolved_verdict_to_the_reprobe_wait(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The PRODUCTION wave gates the wait, not just a hand-supplied unit call.

    The sibling above proves the gate refuses to wait when it is GIVEN a viable
    fallback verdict. That is worth nothing unless the one production caller
    supplies one: a wave that calls `await_usable_credential` with no verdict
    leaves the gate permanently unreachable, and the contract clause "never a
    primary-only probe refusal with a viable fallback" would hold only in the
    test suite. So this drives `dispatch_loop_wave` itself and asserts the
    credential is never even ASSESSED — the observable the gate exists to
    suppress, and the one a preflight-less wave cannot avoid reaching.
    """
    modules = _modules()
    wave = importlib.import_module(f"{_PACKAGE}._dispatcher_loop_wave")
    reprobe = importlib.import_module(f"{_PACKAGE}._dispatcher_credential_reprobe")
    admission_module = importlib.import_module(f"{_PACKAGE}._dispatcher_admission")
    rework_module = importlib.import_module(f"{_PACKAGE}._dispatcher_rework_admission")
    journal_file = importlib.import_module(f"{_PACKAGE}._dispatcher_io").JournalFile(
        path=tmp_path / "journal.jsonl"
    )
    viable = modules["_acp_preflight_verdict"].AcpPreflightVerdict(
        fallback_enabled=True, success_critical=("implement",)
    )
    resolved: list[dict[str, object]] = []

    def fake_resolve(**kwargs: object) -> object:
        resolved.append(kwargs)
        return viable

    monkeypatch.setattr(wave, "resolve_acp_preflight", fake_resolve, raising=False)
    monkeypatch.setattr(
        reprobe,
        "assess_credential_status",
        lambda **_: pytest.fail("a viable fallback chain must not be assessed"),
    )
    monkeypatch.setattr(
        wave,
        "admit_and_select",
        lambda **_: admission_module.Admission(admitted=[], deferred=[], refused=[]),
    )

    outcomes = wave.dispatch_loop_wave(
        args=_wave_args(),
        repo=tmp_path,
        items=[],
        selected_candidates=[],
        journal=journal_file,
        janitor=None,
        rework=rework_module.ReworkPass(),
    )

    assert outcomes == []
    assert [call["repo"] for call in resolved] == [tmp_path]
    assert [call["journal_path"] for call in resolved] == [journal_file.path]
    assert all("probe" not in call for call in resolved)


def _wave_args() -> Any:
    """The two `argparse.Namespace` fields one wave reads."""
    return argparse.Namespace(budget=1, parallel=1)


def test_wait_attention_and_idle_factory_consume_the_same_probe_free_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One verdict, two surfaces, no probe and no other external call."""
    modules = _modules()
    waits = importlib.import_module(f"{_PACKAGE}._needs_attention_waits")
    idle = importlib.import_module(f"{_PACKAGE}._needs_attention_idle_factory")
    calls: list[dict[str, object]] = []
    exhausted = modules["_acp_preflight_verdict"].AcpPreflightVerdict(
        fallback_enabled=True, success_critical=("implement",), exhausted=("implement",)
    )

    def fake(**kwargs: object) -> object:
        calls.append(kwargs)
        return exhausted

    monkeypatch.setattr(waits, "resolve_acp_preflight", fake)
    monkeypatch.setattr(waits, "provider_exhaustion_wait_active", lambda **_: False)
    monkeypatch.setattr(idle, "provider_exhaustion_wait_active", lambda **_: False)
    monkeypatch.setattr(
        idle, "counted_claims", lambda **_: pytest.fail("the chain wait must refuse first")
    )

    assert waits.acp_chain_wait_active(project_root=tmp_path) is True
    assert idle.idle_factory_items(project_root=tmp_path, repo="repo", items=[]) == []
    assert all("probe" not in call for call in calls)
    assert len(calls) == 2


def test_the_idle_factory_row_survives_a_viable_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The condition CLEARS rather than suppressing the row permanently."""
    modules = _modules()
    idle = importlib.import_module(f"{_PACKAGE}._needs_attention_idle_factory")
    monkeypatch.setattr(idle, "provider_exhaustion_wait_active", lambda **_: False)
    monkeypatch.setattr(idle, "acp_chain_wait_active", lambda **_: modules and False)
    monkeypatch.setattr(idle, "counted_claims", lambda **_: 1)

    assert idle.idle_factory_items(project_root=tmp_path, repo="repo", items=[]) == []


def _item(**overrides: object) -> Any:
    types = importlib.import_module("livespec_orchestrator_beads_fabro.types")
    fields: dict[str, object] = {
        "id": "bd-ib-item",
        "type": "task",
        "status": "ready",
        "title": "Task",
        "description": "Do it.",
        "origin": "freeform",
        "gap_id": None,
        "rank": "a1",
        "assignee": None,
        "depends_on": (),
        "captured_at": "2026-07-16T00:00:00Z",
        "resolution": None,
        "reason": None,
        "audit": None,
        "superseded_by": None,
        "admission_policy": None,
        "acceptance_policy": None,
    }
    fields.update(overrides)
    return types.WorkItem(**fields)


_ENABLED_CONFIG = """{
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
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

_ENABLED_MANIFEST = """[workflow]
graph = "workflow.fabro"

[run.inputs]
implement_adapter = "adapter-primary"
"""


def _enabled_repo(*, tmp_path: Path, graph: str = _MINIMAL_GRAPH) -> Path:
    """A repository whose `work` node carries a real two-candidate chain."""
    workflow = tmp_path / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    (workflow / "workflow.toml").write_text(_ENABLED_MANIFEST, encoding="utf-8")
    (workflow / "workflow.fabro").write_text(graph, encoding="utf-8")
    (tmp_path / ".livespec.jsonc").write_text(_ENABLED_CONFIG, encoding="utf-8")
    return tmp_path


def test_an_enabled_repository_resolves_a_viable_two_candidate_chain(tmp_path: Path) -> None:
    """The live composer over a real fixture: config, variant, graph and ledger."""
    modules = _modules()
    repo = _enabled_repo(tmp_path=tmp_path)

    verdict = modules["_dispatcher_acp_preflight"].resolve_acp_preflight(
        repo=repo, journal_path=None, now_iso=_NOW
    )

    assert verdict.fallback_enabled is True
    assert verdict.viable is True
    assert verdict.success_critical == ("implement",)
    assert _keys(preflight=verdict.node_preflight(node="implement")) == ["primary", "fallback"]


def test_a_live_legacy_record_is_read_from_the_journal_at_one_evaluation_time(
    tmp_path: Path,
) -> None:
    """The legacy provider inputs come from the dispatch journal, not a constant."""
    modules = _modules()
    repo = _enabled_repo(tmp_path=tmp_path)
    journal = repo / "journal.jsonl"
    journal.write_text(
        json.dumps(
            {
                "stage": "provider-exhaustion-observed",
                "provider": "codex",
                "governing_condition": "provider_usage_limit",
                "record_expires_at": "2026-09-12T13:00:00Z",
                "work_item_id": "bd-earlier",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    verdict = modules["_dispatcher_acp_preflight"].resolve_acp_preflight(
        repo=repo, journal_path=journal, now_iso=_NOW
    )

    # The primary is NOT built-in here (this build rendered no such adapter),
    # so the legacy vendor record must not be broadened onto it.
    assert verdict.viable is True
    assert _keys(preflight=verdict.node_preflight(node="implement")) == ["primary", "fallback"]


def test_an_enabled_repository_with_an_unsupported_graph_refuses(tmp_path: Path) -> None:
    modules = _modules()
    repo = _enabled_repo(tmp_path=tmp_path, graph="    start [shape=Mdiamond]\n")

    verdict = modules["_dispatcher_acp_preflight"].resolve_acp_preflight(
        repo=repo, journal_path=None, now_iso=_NOW
    )

    assert verdict.viable is False
    assert "declares no green terminal node" in verdict.detail


def test_an_unreadable_graph_declaration_refuses_rather_than_admitting(tmp_path: Path) -> None:
    """Both "no graph declared" and "graph file missing" reach the same refusal."""
    modules = _modules()
    repo = _enabled_repo(tmp_path=tmp_path)
    workflow = repo / ".fabro" / "workflows" / "implement-work-item"
    (workflow / "workflow.fabro").unlink()

    verdict = modules["_dispatcher_acp_preflight"].resolve_acp_preflight(
        repo=repo, journal_path=None, now_iso=_NOW
    )

    assert verdict.viable is False
    assert "could not be read" in verdict.detail


def test_an_unreadable_workflow_manifest_refuses_before_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unreadable manifest is a refusal, never a fall-through to another graph."""
    modules = _modules()
    composer = modules["_dispatcher_acp_preflight"]
    variants = importlib.import_module(f"{_PACKAGE}._workflow_variants")
    repo = _enabled_repo(tmp_path=tmp_path)
    monkeypatch.setattr(
        composer,
        "prepare_workflow_variant",
        lambda **_: variants.WorkflowVariant(name="gone", directory="no-such-directory"),
    )

    verdict = composer.resolve_acp_preflight(repo=repo, journal_path=None, now_iso=_NOW)

    assert verdict.viable is False
    assert "cannot read the workflow config" in verdict.detail


def test_a_registry_variant_directory_supplies_the_graph_that_is_graded(
    tmp_path: Path,
) -> None:
    """A registered default variant is read from its own declared directory."""
    modules = _modules()
    repo = _enabled_repo(tmp_path=tmp_path)
    variant = repo / "custom-workflow"
    variant.mkdir()
    (variant / "workflow.toml").write_text(_ENABLED_MANIFEST, encoding="utf-8")
    (variant / "workflow.fabro").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    config = json.loads((repo / ".livespec.jsonc").read_text(encoding="utf-8"))
    dispatcher = config["livespec-orchestrator-beads-fabro"]["dispatcher"]
    dispatcher["workflows"] = {"custom": "custom-workflow"}
    dispatcher["workflow"] = "custom"
    (repo / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")

    verdict = modules["_dispatcher_acp_preflight"].resolve_acp_preflight(
        repo=repo, journal_path=None, now_iso=_NOW
    )

    assert verdict.viable is True
    assert verdict.success_critical == ("implement",)


def test_an_unresolvable_workflow_variant_refuses_before_claim(tmp_path: Path) -> None:
    """A registry fault is surfaced as a preflight refusal, not guessed around."""
    modules = _modules()
    repo = _enabled_repo(tmp_path=tmp_path)
    config = json.loads((repo / ".livespec.jsonc").read_text(encoding="utf-8"))
    config["livespec-orchestrator-beads-fabro"]["dispatcher"]["workflows"] = {
        "implement-work-item": "custom-workflow"
    }
    (repo / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")

    verdict = modules["_dispatcher_acp_preflight"].resolve_acp_preflight(
        repo=repo, journal_path=None, now_iso=_NOW
    )

    assert verdict.viable is False
    assert "cannot resolve the workflow variant" in verdict.detail


def test_a_repository_with_no_committed_workflow_is_graded_against_the_bundled_one(
    tmp_path: Path,
) -> None:
    """An adopter committing no workflow still gets a real derivation.

    `_manifest_path` falls through to the plugin's own bundled manifest, which
    is the same precedence a dispatch of such a target uses -- so the graded
    graph is the one that would actually run.
    """
    modules = _modules()
    (tmp_path / ".livespec.jsonc").write_text(_ENABLED_CONFIG, encoding="utf-8")

    verdict = modules["_dispatcher_acp_preflight"].resolve_acp_preflight(
        repo=tmp_path, journal_path=None, now_iso=_NOW
    )

    assert verdict.fallback_enabled is True
    assert set(verdict.success_critical) == {"implement", "review", "pr"}
    assert verdict.viable is True


def test_a_node_the_workflow_declares_no_adapter_input_for_refuses(tmp_path: Path) -> None:
    """A resolution refusal reaches the verdict rather than being swallowed."""
    modules = _modules()
    repo = _enabled_repo(tmp_path=tmp_path)
    manifest = repo / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"
    manifest.write_text('[workflow]\ngraph = "workflow.fabro"\n\n[run.inputs]\n', encoding="utf-8")

    verdict = modules["_dispatcher_acp_preflight"].resolve_acp_preflight(
        repo=repo, journal_path=None, now_iso=_NOW
    )

    assert verdict.viable is False
    assert "declares no adapter input" in verdict.detail


def test_a_duplicate_identity_within_one_chain_refuses_before_claim(tmp_path: Path) -> None:
    """The attach-time refusal: one chain may not repeat an entitlement pair."""
    modules = _modules()
    repo = _enabled_repo(tmp_path=tmp_path)
    config = json.loads(_ENABLED_CONFIG)
    node = config["livespec-orchestrator-beads-fabro"]["dispatcher"]["acp_nodes"]["implement"]
    node["fallbacks"][0]["candidate_key"] = node["candidate_key"]
    node["fallbacks"][0]["availability_key"] = node["availability_key"]
    (repo / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")

    verdict = modules["_dispatcher_acp_preflight"].resolve_acp_preflight(
        repo=repo, journal_path=None, now_iso=_NOW
    )

    assert verdict.viable is False
    assert verdict.fallback_enabled is True


def test_an_overlay_refusal_is_surfaced_rather_than_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every `| str` seam this composer reads is a refusal it must propagate.

    The overlay reader and the chain reader validate the same committed table,
    so in practice the chain reader refuses first; this pins the propagation
    itself, which is what a later divergence between the two readers would
    otherwise silently lose.
    """
    modules = _modules()
    composer = modules["_dispatcher_acp_preflight"]
    repo = _enabled_repo(tmp_path=tmp_path)
    monkeypatch.setattr(
        composer, "resolve_acp_node_overlays", lambda **_: "overlay layer is unreadable"
    )

    verdict = composer.resolve_acp_preflight(repo=repo, journal_path=None, now_iso=_NOW)

    assert verdict.viable is False
    assert verdict.detail == "overlay layer is unreadable"
