"""Scenarios 90 and 91 — the Codex adapter's baked-path identity and env channel.

These run at the INTEGRATION tier on purpose. Both scenarios assert properties
of the adapter string a REAL DISPATCH renders — its env pairs in sorted key
order, its command, the byte-identity of the opt-out against the un-pinned base
string — and a unit-tier assertion on `codex_adapter` alone cannot reach them:
the string a node actually receives is the product of the workflow layer, the
repository layer and the render order, not of the tier renderer by itself.

The workflow layer is read from THIS repository's own committed
`workflow.toml` rather than synthesized, and the last test resolves against
this repository's own `.livespec.jsonc`, so the control (every committed
structured entry's agent, model and effort reach its rendered adapter) is
graded against what a dispatch from here would really carry, without pinning
which agent or model the repository has chosen.

THE PINNED NODE IS `review_fix`, NOT `pr`, and the ratified scenarios say so
outright: publication is a COMMAND stage for an implementation workflow, so
there is no `pr` adapter for a dispatch to render and both scenarios name
`review_fix` in its place. A case that kept pinning `pr` here would be grading a
chain the Dispatcher does not build. The repository's own compatibility
`acp_nodes.pr` entry is therefore SCOPED OUT below exactly as a dispatch scopes
it, which is what keeps the committed-configuration control reading the real
resolution rather than a refusal.
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _jsonc as jsonc
from livespec_orchestrator_beads_fabro.commands._acp_agent_entry import AcpAgentEntry
from livespec_orchestrator_beads_fabro.commands._acp_agent_mechanism import (
    ENV_MECHANISM,
    JSON_ENV_MECHANISM,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import resolve_acp_nodes
from livespec_orchestrator_beads_fabro.commands._acp_node_repository import (
    repository_acp_overlays,
)
from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._config_acp import resolve_acp_catalogs_for
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_nodes import (
    workflow_layer,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_publication_policy import (
    GROOM_ONLY_ACP_NODES,
    scoped_repository_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard import (
    GUARD_SCRIPT_PATH,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    dispatch_fabro_run_inputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    CODEX_ADAPTER_BASE,
    build_plan,
)
from livespec_orchestrator_beads_fabro.commands._workflow_variant_kind import (
    WORKFLOW_KIND_IMPLEMENT,
)

_CONFIG_NAME = ".livespec.jsonc"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_TOML = (
    _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"
)

# The ratified literals, restated here rather than imported, so a change to the
# renderer has to be made twice before these tests stop failing. The
# Codex-ACP-node-model-pins contract in `SPECIFICATION/contracts.md` spells them
# all out; a reader must be able to predict them from the specification alone,
# and a test that imported the renderer's own constants could not tell a
# deliberate change from a regression.
_CODEX_ADAPTER_COMMAND = "/opt/livespec/codex-acp/bin/codex-acp"
_CLAUDE_OPUS_5_ADAPTER = (
    "ANTHROPIC_MODEL=claude-opus-5 CLAUDE_CODE_EFFORT_LEVEL=high "
    "npx -y @agentclientprotocol/claude-agent-acp"
)
_UNPINNED_BASE = (
    'CODEX_CONFIG=\'{"approval_policy":"never","sandbox_mode":"danger-full-access"}\' '
    "INITIAL_AGENT_MODE=agent-full-access /opt/livespec/codex-acp/bin/codex-acp"
)
# The rendered Codex adapter for a repository that EXPLICITLY routes its
# `review_fix` node to Codex. Scenario 90 names the STRUCTURED entry, whose
# wording is: sets the review_fix node to agent codex-acp with a model and an
# effort. It named `pr` until v121 retired publication's adapter entirely, and
# `review_fix` is the node it names now — a write-capable implementer-class node
# whose adapter a dispatch still renders.
_EXPLICIT_CODEX_REVIEW_FIX = {
    "acp_nodes": {"review_fix": {"agent": "codex-acp", "model": "gpt-5.4-mini", "effort": "high"}}
}
_PINNED_ADAPTER = (
    'CODEX_CONFIG=\'{"approval_policy":"never","model":"gpt-5.4-mini",'
    '"model_reasoning_effort":"high","sandbox_mode":"danger-full-access"}\' '
    "INITIAL_AGENT_MODE=agent-full-access /opt/livespec/codex-acp/bin/codex-acp"
)
# The posture-only CODEX_CONFIG object: the un-pinned opt-out's own value,
# carrying no `model` key. Spelled out rather than imported so a renderer change
# has to be made twice before this stops failing.
_UNPINNED_CODEX_CONFIG = '{"approval_policy":"never","sandbox_mode":"danger-full-access"}'
_TERRA_CODEX_CONFIG = (
    '{"approval_policy":"never","model":"gpt-5.6-terra",'
    '"model_reasoning_effort":"xhigh","sandbox_mode":"danger-full-access"}'
)


def _write_dispatcher_config(*, repo: Path, dispatcher: dict[str, Any]) -> None:
    config = {"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}
    _ = (repo / _CONFIG_NAME).write_text(json.dumps(config), encoding="utf-8")


# Every adapter launch is now spliced behind the credential-use guard, between its
# env assignments and its executable (`test_dispatcher_credential_use_launch` owns
# that behaviour and asserts it for all nine nodes). These cases grade WHICH adapter
# a node resolves to, so they assert the guard is present and then compare the
# command behind it -- stripping it silently would let the wrap regress unnoticed
# here while these cases kept passing.
_GUARD_LAUNCH_PREFIX = f"/bin/sh {GUARD_SCRIPT_PATH} -- "


def _unguarded(*, rendered: str) -> str:
    """The adapter command behind the credential-use guard."""
    assert _GUARD_LAUNCH_PREFIX in rendered, f"launch is not guarded: {rendered}"
    return rendered.replace(_GUARD_LAUNCH_PREFIX, "", 1)


def _rendered_adapters(*, repo: Path) -> dict[str, str]:
    """Every node's rendered adapter for a dispatch whose target is `repo`.

    Resolved through the real three-layer merge against this repository's
    committed workflow inputs, then rendered through the real dispatch argv
    builder, so the assertions below grade the string a node's `acp.command`
    would actually receive.
    """
    # Scoped by workflow kind, as `prepare_acp_nodes` scopes it: this
    # repository's compatibility `acp_nodes.pr` entry applies to its groom-kind
    # variant alone, and an unscoped read would refuse here for naming a node
    # the implementation workflow declares no adapter input for.
    scoped, _not_applied = scoped_repository_block(
        block=dispatcher_block(cwd=repo), workflow_kind=WORKFLOW_KIND_IMPLEMENT
    )
    catalogs = resolve_acp_catalogs_for(cwd=repo)
    assert not isinstance(catalogs, str), catalogs
    overlays = repository_acp_overlays(block=scoped, catalogs=catalogs)
    assert not isinstance(overlays, str), overlays
    # Through `workflow_layer`, which is what a dispatch uses: the committed
    # defaults are STRUCTURED entries, so a raw `workflow_adapter_inputs` read
    # would hand the merge JSON text and every assertion below would grade the
    # wrong bytes.
    workflow_inputs = workflow_layer(committed=_WORKFLOW_TOML, catalogs=catalogs)
    assert not isinstance(workflow_inputs, str), workflow_inputs
    resolution = resolve_acp_nodes(
        workflow_inputs=workflow_inputs,
        repository=overlays,
        dispatch={},
    )
    assert not isinstance(resolution, str), resolution
    inputs = dispatch_fabro_run_inputs(
        plan=build_plan(
            repo=repo,
            work_item_id="bd-ib-nr3pon",
            workflow_toml=repo / "workflow.toml",
            goal_file=repo / "goal.md",
            fabro_bin="fabro",
            janitor=None,
            janitor_checkout=repo / "janitor",
            acp_nodes=resolution,
        )
    )
    rendered: dict[str, str] = {}
    for node, name in resolution.inputs.items():
        prefix = f"{name}="
        [value] = [pair.removeprefix(prefix) for pair in inputs if pair.startswith(prefix)]
        rendered[node] = _unguarded(rendered=value)
    return rendered


def test_a_default_dispatch_renders_no_publication_adapter(tmp_path: Path) -> None:
    """An unconfigured target renders the implementer default and no publisher.

    The negative half is the v121 assertion and it is checked over the whole
    resolved set rather than one key: publication is a command stage, so there
    is no node for a publication adapter to be rendered FOR, and a key-scoped
    check would pass just as well against a resolution that had quietly
    reintroduced one under a different node name.
    """
    adapters = _rendered_adapters(repo=tmp_path)
    assert "pr" not in adapters
    assert all("claude-haiku" not in rendered for rendered in adapters.values())
    assert adapters["implement"] == _CLAUDE_OPUS_5_ADAPTER


def test_scenario90_a_codex_pinned_dispatch_renders_both_adapters_in_their_ratified_forms(
    tmp_path: Path,
) -> None:
    """With a structured codex-acp `review_fix` entry that adapter is
    env-then-baked-path; the implementer is unchanged."""
    _write_dispatcher_config(repo=tmp_path, dispatcher=_EXPLICIT_CODEX_REVIEW_FIX)
    adapters = _rendered_adapters(repo=tmp_path)

    assert adapters["review_fix"] == _PINNED_ADAPTER
    assert adapters["review_fix"].endswith(f" {_CODEX_ADAPTER_COMMAND}")
    assert '"model":"gpt-5.4-mini"' in adapters["review_fix"]
    assert '"model_reasoning_effort":"high"' in adapters["review_fix"]
    assert " -c model=" not in adapters["review_fix"]
    assert " -c model_reasoning_effort=" not in adapters["review_fix"]

    # The value must survive the POSIX tokenization fabro applies before it
    # launches the process. The whole-string assertion above cannot stand in
    # for this one: it is satisfied by whatever bytes the renderer emits, and
    # the two characters that decide whether the adapter can start at all are
    # exactly the ones a reader skims past.
    tokenized = shlex.split(adapters["review_fix"])[0].removeprefix("CODEX_CONFIG=")
    assert json.loads(tokenized)["model"] == "gpt-5.4-mini"

    assert adapters["implement"] == _CLAUDE_OPUS_5_ADAPTER


def test_scenario90_the_pinned_adapter_declares_agent_full_access(tmp_path: Path) -> None:
    """A write-capable Codex class carries INITIAL_AGENT_MODE=agent-full-access."""
    _write_dispatcher_config(repo=tmp_path, dispatcher=_EXPLICIT_CODEX_REVIEW_FIX)
    assert "INITIAL_AGENT_MODE=agent-full-access" in _rendered_adapters(repo=tmp_path)["review_fix"]


def test_scenario90_a_node_that_performs_no_writes_is_rendered_read_only(
    tmp_path: Path,
) -> None:
    """An `acp_nodes` entry routing review to Codex renders it read-only."""
    _write_dispatcher_config(
        repo=tmp_path,
        dispatcher={
            "acp_nodes": {
                "review": {
                    "command": _CODEX_ADAPTER_COMMAND,
                    "env": {
                        "CODEX_CONFIG": _TERRA_CODEX_CONFIG,
                        "INITIAL_AGENT_MODE": "read-only",
                    },
                }
            }
        },
    )
    review = _rendered_adapters(repo=tmp_path)["review"]
    assert "INITIAL_AGENT_MODE=read-only" in review
    assert "INITIAL_AGENT_MODE=agent-full-access" not in review
    assert review.endswith(f" {_CODEX_ADAPTER_COMMAND}")


def test_scenario90_package_name_resolution_is_never_used_to_identify_the_adapter(
    tmp_path: Path,
) -> None:
    """No rendered Codex adapter resolves through npx by package name.

    The discriminating token is `codex-acp` rather than `npx`: the Claude
    adapter legitimately uses `npx -y`, so a bare `npx` count would report the
    same number whether or not the Codex adapter were fixed. Every rendering
    that mentions codex-acp at all must mention it as the baked path. A
    structured codex-acp `review_fix` entry is written so at least one node
    actually renders the Codex adapter rather than a Claude default.
    """
    _write_dispatcher_config(repo=tmp_path, dispatcher=_EXPLICIT_CODEX_REVIEW_FIX)
    for node, rendered in _rendered_adapters(repo=tmp_path).items():
        if "codex-acp" not in rendered:
            continue
        assert _CODEX_ADAPTER_COMMAND in rendered, node
        assert "@zed-industries/codex-acp" not in rendered, node
        assert "npx --no-install" not in rendered, node


def test_scenario91_the_empty_model_opt_out_omits_the_keys_rather_than_emptying_them(
    tmp_path: Path,
) -> None:
    """The manual-form opt-out renders the un-pinned base string byte-for-byte.

    Scenario 91 names the MANUAL form explicitly -- "the manual form naming the
    baked codex-acp path with a CODEX_CONFIG that carries no model key" -- because
    section "Built-in ACP node defaults" gives the opt-out no structured spelling:
    every structured codex-acp candidate must carry a model and an effort, so an
    operator who disables the pin does so visibly, in the escape-hatch form.

    THE NODE IS `disposition` BECAUSE ITS WORKFLOW DEFAULT DECLARES NO
    ENVIRONMENT, and that isolates the claim this scenario actually makes. A
    repository-layer entry MERGES its `env` with the layer beneath it, so
    asserting byte-identity on a node whose default carries
    `ANTHROPIC_MODEL` / `CLAUDE_CODE_EFFORT_LEVEL` would grade the
    cross-provider merge recorded as `bd-ib-5j4b` rather than the opt-out
    rendering. `disposition` has no such default, so what is compared here is
    the opt-out's own bytes and nothing else.
    """
    _write_dispatcher_config(
        repo=tmp_path,
        dispatcher={"acp_nodes": {"disposition": _UNPINNED_BASE}},
    )
    disposition = _rendered_adapters(repo=tmp_path)["disposition"]

    assert '"model"' not in disposition
    assert '"model_reasoning_effort"' not in disposition
    assert disposition == _UNPINNED_BASE
    assert disposition == CODEX_ADAPTER_BASE


def _committed_structured_entries() -> dict[str, dict[str, str]]:
    """This repository's committed structured `acp_nodes` entries, by node."""
    config = jsonc.loads(text=(_REPO_ROOT / _CONFIG_NAME).read_text(encoding="utf-8"))
    dispatcher = config["livespec-orchestrator-beads-fabro"]["dispatcher"]
    return {
        node: entry
        for node, entry in dispatcher.get("acp_nodes", {}).items()
        if isinstance(entry, dict)
    }


# How a rendered adapter spells one (key, value) setting under each mechanism
# the built-in agents declare.
_SPELLINGS: dict[str, Callable[[str, str], str]] = {
    ENV_MECHANISM: lambda key, value: f"{key}={value}",
    JSON_ENV_MECHANISM: lambda key, value: f'"{key}":"{value}"',
}


def _model_and_effort_spellings(*, entry: dict[str, str], agent: AcpAgentEntry) -> tuple[str, str]:
    """How a rendered adapter spells this entry's model and effort for its agent."""
    spell = _SPELLINGS[agent.mechanism.kind]
    return (
        spell(agent.mechanism.model, entry["model"]),
        spell(agent.mechanism.effort, entry["effort"]),
    )


@pytest.mark.committed_routing_lint
def test_this_repository_committed_entries_reach_their_rendered_adapters() -> None:
    """The control graded on THIS repository's committed configuration.

    It pins no model, agent or effort: those are the repository's to choose and
    change. What it grades is that the committed table resolves and renders
    through the real dispatch path with no refusal, and that every structured
    entry's agent, model and effort reach the node's rendered adapter through
    the mechanism the agent catalog declares for that agent.

    A GROOM-ONLY NODE'S ENTRY IS EXCLUDED, AND THE EXCLUSION IS ASSERTED rather
    than taken as a `continue`. This repository configures `acp_nodes.pr` for
    its groom-kind variant, and an implementation dispatch renders no adapter
    for it; skipping it silently would make this control pass equally well for a
    node whose adapter simply failed to render, so each excluded node is
    required to be BOTH committed and unrendered.
    """
    catalogs = resolve_acp_catalogs_for(cwd=_REPO_ROOT)
    assert not isinstance(catalogs, str), catalogs
    adapters = _rendered_adapters(repo=_REPO_ROOT)
    entries = _committed_structured_entries()

    for node in sorted(GROOM_ONLY_ACP_NODES & set(entries)):
        assert node not in adapters, node

    for node, entry in sorted(entries.items()):
        if node in GROOM_ONLY_ACP_NODES:
            continue
        agent = catalogs.agents[entry["agent"]]
        rendered = adapters[node]
        assert rendered.endswith(f" {agent.command}"), (node, rendered)
        model, effort = _model_and_effort_spellings(entry=entry, agent=agent)
        assert model in rendered, (node, rendered)
        assert effort in rendered, (node, rendered)
        for other in catalogs.agents.values():
            if other.command != agent.command:
                assert other.command not in rendered, (node, rendered)
