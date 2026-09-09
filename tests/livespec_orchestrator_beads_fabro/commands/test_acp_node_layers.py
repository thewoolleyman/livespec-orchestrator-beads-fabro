"""Three-layer, most-specific-wins resolution of every ACP node's adapter.

Binds `SPECIFICATION/contracts.md` section "ACP node adapter configuration":
the per-node `(command, env, args)` value, its contractual render order, the
workflow / repository / per-dispatch precedence, and the refusals that keep a
misconfigured layer from reaching a run.

THE NEGATIVE CONTROL PER LAYER is the point of this file. Each of the three
layers gets a test that sets a value AT that layer and a CONFLICTING value at
every LESS specific layer, then asserts the more specific value is the one
that renders. A test that only asserted "the configured value appears" would
pass just as happily if precedence ran the other way round, so the conflict
is what makes the assertion load-bearing.

Everything here is HERMETIC: adapters are rendered as strings and nothing
launches an adapter or reaches a provider. Proving that an arbitrary command
with an env map and a provider definition RENDERS is a string-level claim,
and making it depend on a reachable endpoint would be testing the network.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_CLAUDE = "npx -y @agentclientprotocol/claude-agent-acp"
_WORKFLOW_DEFAULT = f"ANTHROPIC_MODEL=claude-opus-5 CLAUDE_CODE_EFFORT_LEVEL=high {_CLAUDE}"

# A six-input workflow: one adapter input per ACP node, which is what makes
# per-node configuration expressible at all.
_WORKFLOW_INPUTS = {
    "implement_adapter": _WORKFLOW_DEFAULT,
    "fix_adapter": _WORKFLOW_DEFAULT,
    "review_fix_adapter": _WORKFLOW_DEFAULT,
    "pr_adapter": _CLAUDE,
    "review_adapter": _CLAUDE,
    "disposition_adapter": _CLAUDE,
}


def _module(*, name: str) -> Any:
    """Import one of the adapter-resolution modules, proving it exists first.

    The `is_file` assertion is deliberately the FIRST thing that runs: it
    fails as a genuine assertion before the import can fail as a collection
    error, which is what keeps the Red honest.
    """
    assert (_COMMANDS / f"{name}.py").is_file(), f"{name} module is not implemented"
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _resolve(
    *,
    repository: dict[str, Any] | None = None,
    dispatch: tuple[str, ...] = (),
    workflow_inputs: dict[str, str] | None = None,
) -> Any:
    """Resolve every node's adapter through all three layers."""
    layers = _module(name="_acp_node_layers")
    repo_module = _module(name="_acp_node_repository")
    seam = _module(name="_dispatcher_acp_nodes")
    repo_overlays = repo_module.repository_acp_overlays(block=repository or {})
    if isinstance(repo_overlays, str):
        return repo_overlays
    dispatch_overlays = seam.dispatch_acp_overlays(overrides=dispatch)
    if isinstance(dispatch_overlays, str):
        return dispatch_overlays
    return layers.resolve_acp_nodes(
        workflow_inputs=_WORKFLOW_INPUTS if workflow_inputs is None else workflow_inputs,
        repository=repo_overlays,
        dispatch=dispatch_overlays,
    )


def test_render_order_is_sorted_env_then_command_then_args() -> None:
    """The rendered string is contractual: sorted env pairs, command, args in order."""
    adapters = _module(name="_acp_node_adapters")
    rendered = adapters.render_adapter(
        adapter=adapters.AcpAdapter(
            command="npx -y some-acp",
            env={"ZULU": "1", "ALPHA": "2", "MIKE": "3"},
            args=("-c", "model=local"),
        )
    )
    assert rendered == "ALPHA=2 MIKE=3 ZULU=1 npx -y some-acp -c model=local"


def test_parsing_an_adapter_string_round_trips_through_rendering() -> None:
    """A workflow default survives decomposition and re-rendering unchanged.

    Round-tripping is what lets a declared default enter resolution as a
    value rather than as an opaque string; a lossy split would silently
    rewrite adapters nobody configured.
    """
    adapters = _module(name="_acp_node_adapters")
    parsed = adapters.parse_adapter_string(text=_WORKFLOW_DEFAULT)
    assert parsed.command == _CLAUDE
    assert dict(parsed.env) == {
        "ANTHROPIC_MODEL": "claude-opus-5",
        "CLAUDE_CODE_EFFORT_LEVEL": "high",
    }
    assert adapters.render_adapter(adapter=parsed) == _WORKFLOW_DEFAULT


def test_workflow_layer_supplies_every_node_when_nothing_else_is_configured() -> None:
    """NEGATIVE CONTROL, layer 1: with no override, the workflow default renders.

    This is the least specific layer, so its control is that the values it
    declares reach every node and the record attributes them to it.
    """
    resolution = _resolve()
    layers = _module(name="_acp_node_layers")
    implement = resolution.nodes["implement"]
    assert implement.rendered == _WORKFLOW_DEFAULT
    assert implement.command_layer == layers.WORKFLOW_LAYER
    assert dict(implement.env_layers) == {
        "ANTHROPIC_MODEL": layers.WORKFLOW_LAYER,
        "CLAUDE_CODE_EFFORT_LEVEL": layers.WORKFLOW_LAYER,
    }
    assert resolution.nodes["review"].rendered == _CLAUDE


def test_repository_layer_overrides_a_conflicting_workflow_default() -> None:
    """NEGATIVE CONTROL, layer 2: the repository entry beats the workflow default.

    The workflow default names Claude Opus 5 and the repository names a
    different command for `implement` ALONE, so the assertion fails if
    precedence runs either backwards or too broadly.
    """
    resolution = _resolve(
        repository={"acp_nodes": {"implement": {"command": "uvx local-acp", "env": {}}}}
    )
    layers = _module(name="_acp_node_layers")
    implement = resolution.nodes["implement"]
    assert implement.adapter.command == "uvx local-acp"
    assert implement.command_layer == layers.REPOSITORY_LAYER
    # Scoped to the node that was configured: `fix` keeps the workflow default.
    assert resolution.nodes["fix"].rendered == _WORKFLOW_DEFAULT
    assert resolution.nodes["fix"].command_layer == layers.WORKFLOW_LAYER


def test_dispatch_layer_overrides_both_less_specific_layers() -> None:
    """NEGATIVE CONTROL, layer 3: the per-dispatch argument beats both below it.

    All three layers name a DIFFERENT model for the same node, so only the
    most specific one can satisfy the assertion. The repository's other env
    keys survive, which is the ratified merge behaviour (Scenario 87) and
    the reason moving one variable does not mean restating an environment.
    """
    resolution = _resolve(
        repository={
            "acp_nodes": {
                "implement": {
                    "env": {
                        "ANTHROPIC_MODEL": "macmini/qwen3-coder-next",
                        "ANTHROPIC_BASE_URL": "http://router.invalid:8081",
                    }
                }
            }
        },
        dispatch=(f"implement=ANTHROPIC_MODEL=m4max/qwen3-coder-next {_CLAUDE}",),
    )
    layers = _module(name="_acp_node_layers")
    implement = resolution.nodes["implement"]
    assert implement.adapter.env["ANTHROPIC_MODEL"] == "m4max/qwen3-coder-next"
    assert implement.env_layers["ANTHROPIC_MODEL"] == layers.DISPATCH_LAYER
    assert implement.adapter.env["ANTHROPIC_BASE_URL"] == "http://router.invalid:8081"
    assert implement.env_layers["ANTHROPIC_BASE_URL"] == layers.REPOSITORY_LAYER


def test_an_arbitrary_adapter_command_renders_with_its_env_map(monkeypatch: Any) -> None:
    """Scenario 88: a Claude adapter aimed at an Anthropic-compatible endpoint.

    Also the standing proof that NO ENVIRONMENT VARIABLE reaches this
    resolution: the variables set below are exactly the ones an operator
    might expect to be honoured, and the rendered adapter must be identical
    with and without them.
    """
    env_map = {
        "ANTHROPIC_BASE_URL": "http://router.invalid:8081",
        "ANTHROPIC_AUTH_TOKEN": "router-key",
        "ANTHROPIC_MODEL": "macmini/qwen3-coder-next",
    }
    repository = {"acp_nodes": {"implement": {"command": _CLAUDE, "env": env_map}}}
    before = _resolve(repository=repository).nodes["implement"].rendered
    # `CLAUDE_CODE_EFFORT_LEVEL` is the workflow default's, kept because env
    # merges; the three router keys are the repository's, and the whole set
    # renders in sorted key order ahead of the command.
    assert before == (
        "ANTHROPIC_AUTH_TOKEN=router-key "
        "ANTHROPIC_BASE_URL=http://router.invalid:8081 "
        "ANTHROPIC_MODEL=macmini/qwen3-coder-next "
        f"CLAUDE_CODE_EFFORT_LEVEL=high {_CLAUDE}"
    )
    for name in ("ANTHROPIC_MODEL", "ANTHROPIC_BASE_URL", "LIVESPEC_ACP_NODE"):
        monkeypatch.setenv(name, "environment-must-not-win")
    assert _resolve(repository=repository).nodes["implement"].rendered == before


def test_an_arbitrary_adapter_renders_its_provider_definition_args() -> None:
    """Scenario 88: a Codex-adapter node whose args carry a provider definition."""
    resolution = _resolve(
        repository={
            "acp_nodes": {
                "pr": {
                    "command": "npx --no-install @zed-industries/codex-acp",
                    "args": ["-c", "model_provider=local-llm-fleet", "-c", "model=qwen3"],
                }
            }
        }
    )
    assert resolution.nodes["pr"].rendered == (
        "npx --no-install @zed-industries/codex-acp "
        "-c model_provider=local-llm-fleet -c model=qwen3"
    )


def test_an_acp_nodes_entry_wins_over_the_codex_models_shorthand() -> None:
    """`codex_models` stays valid, and an explicit entry for the same node beats it."""
    resolution = _resolve(
        repository={
            "codex_models": {"pr": {"model": "gpt-5.4-mini", "reasoning_effort": "high"}},
            "acp_nodes": {"pr": "uvx explicit-acp"},
        }
    )
    assert resolution.nodes["pr"].rendered == "uvx explicit-acp"


def test_pr_expands_to_codex_only_for_an_explicit_pr_tier() -> None:
    """The publish tier expands ONLY when `codex_models.pr` is an explicit table.

    This is the v107 symmetry: absent that table the publish node keeps the
    workflow's own default adapter (a model-agnostic Claude adapter) rather
    than a baked Codex model, exactly as the implementer tier already worked.
    An explicit `codex_models.pr` table still routes the publish node to Codex.
    """
    # No codex_models block at all -> the workflow pr default stands.
    assert _resolve(repository={}).nodes["pr"].rendered == _CLAUDE
    # A block configuring only the implementer leaves the publish node alone.
    assert (
        _resolve(repository={"codex_models": {"implementer": {"model": "gpt-5.5"}}})
        .nodes["pr"]
        .rendered
        == _CLAUDE
    )
    # A non-table pr entry is not an explicit tier, so pr keeps its default.
    assert (
        _resolve(repository={"codex_models": {"pr": "not-a-table"}}).nodes["pr"].rendered == _CLAUDE
    )
    # An explicit pr table DOES route the publish node to the Codex adapter.
    codex_pr = (
        _resolve(
            repository={"codex_models": {"pr": {"model": "gpt-5.5", "reasoning_effort": "high"}}}
        )
        .nodes["pr"]
        .rendered
    )
    assert codex_pr.endswith(" /opt/livespec/codex-acp/bin/codex-acp")
    assert '"model":"gpt-5.5"' in codex_pr


def test_the_codex_shorthand_replaces_the_workflow_env_rather_than_merging() -> None:
    """A Codex command line must never inherit the workflow's Anthropic pins.

    The implementer tier expands only when named explicitly, and when it
    does the whole adapter is Codex's -- an `ANTHROPIC_MODEL` merged onto it
    would pin an Anthropic model on a command that is not Anthropic's.
    """
    resolution = _resolve(
        repository={"codex_models": {"implementer": {"model": "gpt-5.5"}}},
    )
    rendered = resolution.nodes["implement"].rendered
    assert "ANTHROPIC_MODEL" not in rendered
    assert rendered.endswith(" /opt/livespec/codex-acp/bin/codex-acp")
    assert '"model":"gpt-5.5"' in rendered


def test_a_layer_naming_an_unknown_node_refuses_naming_it() -> None:
    """Scenario 87: an unknown node refuses rather than being silently ignored."""
    repository = _resolve(repository={"acp_nodes": {"implemnt": "uvx typo-acp"}})
    assert isinstance(repository, str)
    assert "implemnt" in repository
    dispatch = _resolve(dispatch=("reviewer=uvx typo-acp",))
    assert isinstance(dispatch, str)
    assert "reviewer" in dispatch


def test_a_node_the_workflow_never_parameterized_is_simply_not_overridden() -> None:
    """An un-parameterized node is absent, not fatal — there is nothing to override.

    A workflow is free to hard-code a node's adapter, and dispatching one
    that does must keep working: the Dispatcher passes no input for that
    node and the workflow runs what it declares.
    """
    incomplete = dict(_WORKFLOW_INPUTS)
    del incomplete["review_adapter"]
    resolution = _resolve(workflow_inputs=incomplete)
    assert not isinstance(resolution, str), resolution
    assert "review" not in resolution.nodes
    assert not [pair for pair in resolution.run_inputs if pair.startswith("review_adapter=")]
    assert "implement" in resolution.nodes


def test_configuring_a_node_the_workflow_never_parameterized_refuses() -> None:
    """Scenario 87: configuring an unreachable node refuses, naming it.

    THIS is the case worth refusing. The override cannot possibly take
    effect, so accepting it would leave the operator with a journal saying
    their adapter was configured and a run that never used it.
    """
    incomplete = dict(_WORKFLOW_INPUTS)
    del incomplete["review_adapter"]
    refusal = _resolve(
        workflow_inputs=incomplete,
        repository={"acp_nodes": {"review": "uvx review-acp"}},
    )
    assert isinstance(refusal, str)
    assert "review" in refusal
    assert "declares no" in refusal


def test_nodes_sharing_one_input_refuse_when_they_resolve_differently() -> None:
    """A four-input workflow cannot express a per-node split, and says so.

    One workflow input cannot carry two values, so configuring `fix` alone
    on a graph where three nodes share `acp_adapter` REFUSES rather than
    silently dropping the override -- the failure mode where the journal
    reports an override the run never applied.
    """
    shared = {
        "acp_adapter": _WORKFLOW_DEFAULT,
        "pr_adapter": _CLAUDE,
        "review_adapter": _CLAUDE,
        "disposition_adapter": _CLAUDE,
    }
    resolution = _resolve(workflow_inputs=shared)
    # One pair per DECLARED INPUT, not one per node: the three implementer
    # nodes agree here, so they collapse onto the single input they share.
    # `pr_adapter` is a declared input, so it always renders a pair — here at
    # its workflow default, since no `codex_models.pr` tier is configured.
    assert [pair.split("=", 1)[0] for pair in resolution.run_inputs] == [
        "acp_adapter",
        "disposition_adapter",
        "pr_adapter",
        "review_adapter",
    ]
    assert f"acp_adapter={_WORKFLOW_DEFAULT}" in resolution.run_inputs
    refusal = _resolve(workflow_inputs=shared, dispatch=("fix=uvx only-the-fix-node",))
    assert isinstance(refusal, str)
    assert "acp_adapter" in refusal
    assert "fix" in refusal


def test_the_journal_record_names_the_supplying_layer_per_field() -> None:
    """The dispatch record answers "which layer supplied this" without re-deriving."""
    layers = _module(name="_acp_node_layers")
    resolution = _resolve(
        repository={"acp_nodes": {"review": {"command": "uvx review-acp"}}},
        dispatch=(f"disposition=CLAUDE_CODE_EFFORT_LEVEL=low {_CLAUDE}",),
    )
    record = layers.acp_nodes_journal_record(resolution=resolution)
    nodes = record["acp_nodes"]
    assert nodes["review"]["adapter"] == "uvx review-acp"
    assert nodes["review"]["input"] == "review_adapter"
    assert nodes["review"]["layers"]["command"] == layers.REPOSITORY_LAYER
    assert nodes["disposition"]["layers"]["env"] == {
        "CLAUDE_CODE_EFFORT_LEVEL": layers.DISPATCH_LAYER
    }
    assert nodes["implement"]["layers"]["command"] == layers.WORKFLOW_LAYER
    assert set(nodes) == {"implement", "fix", "review_fix", "pr", "review", "disposition"}


def test_a_malformed_repository_entry_refuses_naming_the_key() -> None:
    """A config typo refuses with the configuration path the operator must edit."""
    for entry, needle in (
        ({"command": 7}, "dispatcher.acp_nodes.implement.command"),
        ({"args": "not-a-list"}, "dispatcher.acp_nodes.implement.args"),
        ({"env": "not-a-table"}, "dispatcher.acp_nodes.implement.env"),
        ({"env": {"KEY": 7}}, "dispatcher.acp_nodes.implement.env"),
        (7, "dispatcher.acp_nodes.implement"),
    ):
        refusal = _resolve(repository={"acp_nodes": {"implement": entry}})
        assert isinstance(refusal, str), entry
        assert needle in refusal, entry
    table = _resolve(repository={"acp_nodes": "not-a-table"})
    assert isinstance(table, str)
    assert "dispatcher.acp_nodes" in table


def test_a_malformed_per_dispatch_argument_refuses() -> None:
    """`--acp-node` misuse refuses rather than resolving to something plausible."""
    for override, needle in (
        ("implement", "<node>=<adapter command>"),
        ("=uvx acp", "<node>=<adapter command>"),
        ("implement=", "<node>=<adapter command>"),
    ):
        refusal = _resolve(dispatch=(override,))
        assert isinstance(refusal, str), override
        assert needle in refusal, override
    repeated = _resolve(dispatch=("implement=uvx one", "implement=uvx two"))
    assert isinstance(repeated, str)
    assert "more than once" in repeated


def test_an_adapter_string_that_is_only_env_assignments_has_an_empty_command() -> None:
    """A string of nothing but `KEY=value` tokens leaves no command behind.

    The env-prefix scan must terminate by exhausting the tokens as well as
    by hitting the first non-assignment; without a case that runs off the
    end, an off-by-one there would look like a normal parse.
    """
    adapters = _module(name="_acp_node_adapters")
    parsed = adapters.parse_adapter_string(text="ALPHA=1 BETA=2")
    assert parsed.command == ""
    assert dict(parsed.env) == {"ALPHA": "1", "BETA": "2"}
    assert adapters.render_adapter(adapter=parsed) == "ALPHA=1 BETA=2 "


def test_an_args_list_holding_a_non_string_refuses() -> None:
    """`args` must be strings, not merely a list.

    A list of the wrong element type is the near miss a plain
    `isinstance(value, list)` check waves through, and it would reach the
    rendered command line as whatever `str()` made of it.
    """
    refusal = _resolve(repository={"acp_nodes": {"implement": {"args": ["-c", 7]}}})
    assert isinstance(refusal, str)
    assert "dispatcher.acp_nodes.implement.args" in refusal
