"""A node with no fallback metadata renders the SAME bytes through selection.

Binds the additive guarantee of `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority": a node with no fallback metadata,
or with `fallbacks: []`, renders adapter bytes byte-identical to the resolution
stated in the ACP node adapter configuration section.

WHY THIS NEEDS ITS OWN CASE RATHER THAN THE ONE THAT ALREADY EXISTS.
`test_acp_fallback_resolution.test_no_fallback_metadata_and_an_empty_array_render_identical_bytes`
asserts the same guarantee at the RESOLUTION layer -- `resolve_acp_nodes`
followed by `attach_acp_chains` -- and it was sufficient while that was the last
thing to touch a node's bytes. Under spec v127 it no longer is: the Dispatcher
now SELECTS one candidate per node and `render_acp_commands` rewrites each ACP
node's adapter off the selected candidate, so the bytes a dispatch submits pass
through a stage that case stops short of. A legacy node's adapter is therefore
re-rendered from a candidate the chain layer REBUILT out of the resolved
adapter, and nothing above asserts that the round trip is lossless.

THE FAILURE THIS GUARDS IS SILENT AND FLEET-WIDE. Every node in this repository
that declares no fallbacks -- which is most of them, and every node of every
adopter that has not opted in -- goes through this path on every dispatch. A
round trip that dropped an env entry, reordered args, or re-quoted a command
would still produce a perfectly well-formed adapter, so the run would start, the
agent would launch, and the only evidence would be a model or a credential that
was not the one configured.

THE BASELINE IS COMPUTED, NEVER TRANSCRIBED. An expected command written here
would pass for whatever this repository's defaults happen to render today and
would stop meaning anything the moment a default moved. The comparison is
against the resolution the configuration section itself states, resolved by the
production layer functions in the same process.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_ITEM = "bd-ib-wvj4rk"

_WORKFLOW_TOML = """_version = 1

[workflow]
graph = "workflow.fabro"

[run.inputs]
implement_adapter = "npx -y claude-acp"
review_adapter = "npx -y claude-acp"

[run.environment]
id = "livespec-ci"
"""

_WORKFLOW_GRAPH = """digraph implement {
    graph [stall_timeout="7200s"]
    start [shape=Mdiamond, label="Start"]
    exit  [shape=Msquare, label="Exit"]
    implement [backend="acp", acp.command="{{ inputs.implement_adapter }}", timeout="60s"]
    review    [backend="acp", acp.command="{{ inputs.review_adapter }}", timeout="60s"]
    start -> implement
    implement -> review
    review -> exit
}
"""


# The workflow layer's adapter inputs, keyed by INPUT name as the layer reads
# them -- not by node name. Mirrors the `[run.inputs]` table above.
_WORKFLOW_INPUTS = {
    "implement_adapter": "npx -y claude-acp",
    "review_adapter": "npx -y claude-acp",
}


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


class _Journal:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _manual_entry() -> dict[str, Any]:
    """A manual adapter carrying env and args, so a lossy round trip shows.

    A bare `command` would render identically under several wrong
    implementations; the env entry and the argument vector are what a re-render
    can drop, reorder or re-quote without producing anything malformed.
    """
    return {
        "display_name": "Implement adapter",
        "candidate_key": "implementmodel",
        "availability_key": "implementdomain",
        "command": "implement-acp",
        "args": ["--stdio", "--flag=value with spaces"],
        "env": {"IMPLEMENT_BASE_URL": "https://implement.example", "OTHER": "second"},
    }


def _acp_nodes() -> dict[str, Any]:
    """The two shapes the clause names, one per node.

    `implement` declares NO `fallbacks` key at all and `review` declares an
    EMPTY one: the clause names both, and they reach the chain layer through
    different arms -- one with no metadata to attach, one with metadata that
    attaches an empty chain.
    """
    return {
        "implement": _manual_entry(),
        "review": {**_manual_entry(), "candidate_key": "reviewmodel", "fallbacks": []},
    }


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    workflow = repo / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    _ = (workflow / "workflow.toml").write_text(_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow / "workflow.fabro").write_text(_WORKFLOW_GRAPH, encoding="utf-8")
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "git_author": {
                    "operator_name": "Operator",
                    "operator_email": "operator@example.com",
                },
                "livespec-orchestrator-beads-fabro": {"dispatcher": {"acp_nodes": _acp_nodes()}},
            }
        ),
        encoding="utf-8",
    )
    return repo


def _stated(*, repo: Path) -> Any:
    """The resolution the ACP node adapter configuration section states.

    The three-layer resolution and nothing after it: this is the answer the
    configuration section fixes, which the selection stage must not disturb for
    a node that declared no chain.
    """
    sources = _module(name="_dispatcher_acp_chain_sources")
    catalogs_module = _module(name="_acp_catalogs")
    repository = _module(name="_acp_node_repository")
    layers = _module(name="_acp_node_layers")

    block = sources.workflow_scoped_dispatcher_block(repo=repo)
    catalogs = catalogs_module.resolve_acp_catalogs(block=block)
    assert not isinstance(catalogs, str), catalogs
    overlays = repository.repository_acp_overlays(block=block, catalogs=catalogs)
    assert not isinstance(overlays, str), overlays
    resolution = layers.resolve_acp_nodes(
        workflow_inputs=_WORKFLOW_INPUTS,
        repository=overlays,
        dispatch={},
    )
    assert not isinstance(resolution, str), resolution
    return resolution


def _verdict(*, repo: Path) -> Any:
    """An admission verdict over this configuration, with nothing held."""
    sources = _module(name="_dispatcher_acp_chain_sources")
    catalogs_module = _module(name="_acp_catalogs")
    repository = _module(name="_acp_node_repository")
    ledger_module = _module(name="_acp_hold_ledger")
    preflight = _module(name="_acp_candidate_preflight")
    verdicts = _module(name="_acp_preflight_verdict")

    block = sources.workflow_scoped_dispatcher_block(repo=repo)
    catalogs = catalogs_module.resolve_acp_catalogs(block=block)
    assert not isinstance(catalogs, str), catalogs
    declared = repository.repository_acp_chains(block=block, catalogs=catalogs)
    assert not isinstance(declared, str), declared
    resolved = sources.repository_acp_chain_sources(
        repo=repo, block=block, declared=declared, catalogs=catalogs
    )
    assert not isinstance(resolved, str), resolved
    chains, graph_text, builtin_pairs = resolved
    return verdicts.build_acp_preflight_verdict(
        chains=chains,
        graph_text=graph_text,
        ledger=ledger_module.AcpHoldLedger(holds=(), unobservable=(), observation_ids=frozenset()),
        inputs=preflight.PreflightInputs(holds=(), builtin_pairs=builtin_pairs),
    )


def _selected(*, repo: Path) -> Any:
    """The resolution a dispatch SUBMITS, i.e. after the selection stage."""
    nodes = _module(name="_dispatcher_acp_nodes")
    resolution = nodes.prepare_acp_nodes(
        repo=repo,
        committed=repo / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml",
        overrides=(),
        journal=_Journal(),
        work_item_id=_ITEM,
        verdict=_verdict(repo=repo),
    )
    assert not isinstance(resolution, str), resolution
    return resolution


def _payload(*, resolution: Any) -> Any:
    """The graph attributes a dispatch would submit for one resolution."""
    graphs = _module(name="_dispatcher_graph_adapters")
    rendered = graphs.render_acp_commands(
        graph_text=_WORKFLOW_GRAPH,
        adapters=graphs.guarded_adapter_commands(run_inputs=resolution.run_inputs),
    )
    assert not isinstance(rendered, str), rendered
    return rendered


def test_no_fallback_metadata_and_an_empty_array_survive_selection_byte_for_byte(
    tmp_path: Path,
) -> None:
    """Both shapes the clause names, through the stage that rewrites adapters."""
    repo = _repo(tmp_path=tmp_path)

    stated = {node: one.rendered for node, one in _stated(repo=repo).nodes.items()}
    submitted = {node: one.rendered for node, one in _selected(repo=repo).nodes.items()}

    # Asserted as whole mappings, not key by key: a selection stage that dropped
    # a node entirely is exactly as wrong as one that changed its bytes, and a
    # per-key loop over the SUBMITTED mapping could not see the absence.
    assert submitted == stated
    # The fixture is only meaningful if it actually carried the two shapes
    # through to rendered bytes -- an empty or single-node mapping would make
    # the comparison above vacuously true.
    assert sorted(submitted) == ["implement", "review"]
    assert "implement-acp" in submitted["implement"]
    assert "implement-acp" in submitted["review"]


def test_the_submitted_payload_carries_those_same_bytes(tmp_path: Path) -> None:
    """One level on: the graph the dispatch submits, not just the resolution.

    `render_acp_commands` is what rewrites each node's `acp.command` attribute,
    so a resolution that survived selection intact could still reach the payload
    changed. The guarantee the clause states is about the bytes that RUN.

    BOTH SIDES GO THROUGH THE SAME RENDERER, which is what makes this a
    comparison rather than a transcription. `guarded_adapter_commands` splices
    the credential-use guard between a node's env prefix and its command, so the
    submitted attribute is deliberately NOT the resolved bytes verbatim --
    asserting containment of the stated bytes would fail against a perfectly
    correct payload. Rendering the stated resolution through the same function
    leaves the SELECTION STAGE as the only difference between the two.
    """
    repo = _repo(tmp_path=tmp_path)

    stated = _payload(resolution=_stated(repo=repo))
    submitted = _payload(resolution=_selected(repo=repo))

    assert submitted.node_commands == stated.node_commands
    assert submitted.text == stated.text
    # The guard really is in the bytes under comparison, so this is an identity
    # between two GUARDED payloads rather than between two unguarded ones.
    assert "credential-use-guard.sh" in submitted.node_commands["implement"]
