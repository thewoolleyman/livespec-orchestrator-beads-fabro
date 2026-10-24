"""The SHAPE of one availability confirmation turn: a bounded minimal factory run.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Availability is re-confirmed after expiry": "Availability is
confirmed only by a successfully completed ACP prompt turn using the
candidate's pinned adapter version, requested model and effort, and projected
worker credential identity. ... A host-side probe is permitted only when these
execution properties are equivalent and its outcome is durably observable
through the same authoritative evidence source; otherwise the probe MUST be a
minimal factory run. The probe sends one fixed minimal prompt." Scenario 127's
"An expired hold is re-confirmed by a completed turn before a real dispatch
uses the candidate" is the scenario this half serves.

THE EQUIVALENCE CLAIM IS WHAT IS UNDER TEST, not the DOT syntax. A probe whose
adapter bytes differ from the ones a dispatch would render for that candidate
has not exercised that candidate at all -- it has exercised a neighbour that
happens to share a name -- so the graph's `acp.command` is asserted
byte-identical to `render_adapter` over the candidate's own adapter, which is
the one function the dispatch path renders through.

ONE NODE IS THE WHOLE OF "MINIMAL". The run is counted rather than described:
a graph carrying a second ACP node would spend a second allowance per probe,
and a graph carrying a script node would make the succeeded-attempt reader
below answer about a node that launched no adapter.

THE LABELS ARE NOT COSMETIC: they are the mechanism by which a successful
confirmation becomes host-wide evidence. `_acp_factory_hold_evidence` derives a
`FactorySuccessObservation` from a succeeded node attempt ONLY when the run's
labels record an entitlement for that node's own id, so the test asserts the
recovery through `executed_candidate_identity` rather than by comparing label
strings -- the reader is the authority on which labels are readable.

Everything is HERMETIC: the candidates are built in memory and nothing reaches
a factory, a provider or a credential.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE = "_acp_availability_probe"


def _probe_module() -> Any:
    """Import the probe's pure half, proving its file exists first."""
    path = _COMMANDS / f"{_MODULE}.py"
    assert path.is_file(), f"{_MODULE}.py is not implemented yet"
    return importlib.import_module(f"{_PACKAGE}.{_MODULE}")


def _candidate(
    *,
    command: str = "claude-code-acp",
    env: dict[str, str] | None = None,
    args: tuple[str, ...] = (),
    availability_key: str = "anthropic.com",
    candidate_key: str = "claude-opus-5-high",
    config_options: dict[str, str] | None = None,
) -> Any:
    """One identified candidate whose adapter carries its model and effort."""
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    return schema.AcpCandidate(
        adapter=adapters.AcpAdapter(
            command=command,
            env={"ANTHROPIC_MODEL": "claude-opus-5"} if env is None else env,
            args=args,
        ),
        identity=schema.AcpCandidateIdentity(
            display_name="Claude Opus 5 (high)",
            candidate_key=candidate_key,
            availability_key=availability_key,
        ),
        config_options={} if config_options is None else config_options,
    )


def _node_attributes(*, graph: str, node: str) -> str:
    """The attribute text of one DOT node declaration."""
    opening = f"    {node} ["
    body = graph.split(opening, 1)
    assert len(body) == 2, f"graph declares no node {node!r}:\n{graph}"
    return body[1].split("]", 1)[0]


def test_the_probe_graph_is_one_acp_node_running_the_candidates_own_adapter_bytes() -> None:
    """The probe exercises the candidate a dispatch would render, and nothing else."""
    module = _probe_module()
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    candidate = _candidate(args=("--model", "claude-opus-5"))

    graph = module.availability_probe_graph(candidate=candidate, timeout_seconds=120)
    attributes = _node_attributes(graph=graph, node=module.AVAILABILITY_PROBE_NODE)

    rendered = adapters.render_adapter(adapter=candidate.adapter)
    assert f'acp.command="{rendered}"' in attributes
    assert 'backend="acp"' in attributes
    # ONE adapter-bearing node, so one probe spends one allowance.
    assert graph.count('backend="acp"') == 1
    assert "shape=parallelogram" not in graph


def test_the_probe_sends_one_fixed_minimal_prompt_whatever_the_candidate_is() -> None:
    """The prompt is a constant of the probe, never a function of the candidate."""
    module = _probe_module()
    one = module.availability_probe_graph(
        candidate=_candidate(command="claude-code-acp"), timeout_seconds=120
    )
    other = module.availability_probe_graph(
        candidate=_candidate(
            command="codex-acp", env={"CODEX_CONFIG": '{"model":"gpt-5.5"}'}, args=("acp",)
        ),
        timeout_seconds=600,
    )

    assert module.AVAILABILITY_PROBE_PROMPT.strip() != ""
    for graph in (one, other):
        assert f'prompt="{module.AVAILABILITY_PROBE_PROMPT}"' in graph


def test_the_probe_node_timeout_is_the_committed_probe_bound() -> None:
    """The run is BOUNDED by the configured probe timeout, in the graph itself."""
    module = _probe_module()
    graph = module.availability_probe_graph(candidate=_candidate(), timeout_seconds=97)

    assert 'timeout="97s"' in _node_attributes(graph=graph, node=module.AVAILABILITY_PROBE_NODE)


def test_the_probe_labels_make_a_successful_turn_readable_host_wide() -> None:
    """The host-wide success reader recovers this candidate from the probe's labels."""
    module = _probe_module()
    executed = importlib.import_module(f"{_PACKAGE}._fabro_executed_candidate")
    candidate = _candidate(availability_key="chatgpt-team", candidate_key="gpt-5.5-high")

    labels = dict(
        pair.split("=", 1) for pair in module.availability_probe_labels(candidate=candidate)
    )

    recovered = executed.executed_candidate_identity(
        labels=labels, node=module.AVAILABILITY_PROBE_NODE
    )
    assert recovered is not None
    assert recovered.availability_key == "chatgpt-team"
    assert recovered.candidate_key == "gpt-5.5-high"
    assert module.is_availability_probe_run(labels=labels) is True
    assert module.is_availability_probe_run(labels={}) is False


def test_a_candidate_whose_requested_model_the_probe_cannot_render_is_refused() -> None:
    """An in-protocol candidate's model reaches no adapter, so no turn confirms it."""
    module = _probe_module()

    assert module.availability_probe_refusal(candidate=_candidate()) is None

    in_protocol = module.availability_probe_refusal(
        candidate=_candidate(config_options={"model": "grok-4.6"})
    )
    assert in_protocol is not None
    assert "config_options" in in_protocol

    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    identity_less = module.availability_probe_refusal(
        candidate=schema.AcpCandidate(adapter=adapters.AcpAdapter(command="legacy-acp"))
    )
    assert identity_less is not None
    assert "identity" in identity_less
