"""Scenarios 90 and 91 — the Codex adapter's baked-path identity and env channel.

These run at the INTEGRATION tier on purpose. Both scenarios assert properties
of the adapter string a REAL DISPATCH renders — its env pairs in sorted key
order, its command, the byte-identity of the opt-out against the un-pinned base
string — and a unit-tier assertion on `codex_adapter` alone cannot reach them:
the string a node actually receives is the product of the workflow layer, the
repository layer and the render order, not of the tier renderer by itself.

The workflow layer is read from THIS repository's own committed
`workflow.toml` rather than synthesized, and the last test resolves against
this repository's own `.livespec.jsonc`, so the negative control (all three
node classes render Claude adapters — implementer Opus 5, review Opus 4.8,
publish Haiku 4.5 — with none on Codex) is graded against what a dispatch from
here would really carry.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_node_layers import resolve_acp_nodes
from livespec_orchestrator_beads_fabro.commands._config import resolve_acp_node_overlays
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_nodes import (
    workflow_adapter_inputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    dispatch_fabro_run_inputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    CODEX_ADAPTER_BASE,
    build_plan,
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
# The publish node's fleet DEFAULT since v107: the Claude Haiku adapter,
# read from this repository's committed workflow.toml `pr_adapter` input.
_PUBLISH_DEFAULT_HAIKU = (
    "ANTHROPIC_MODEL=claude-haiku-4-5 CLAUDE_CODE_EFFORT_LEVEL=high "
    "npx -y @agentclientprotocol/claude-agent-acp"
)
# The rendered Codex publish adapter for a repository that EXPLICITLY pins its
# `pr` tier to Codex via `dispatcher.codex_models.pr` — no longer the default.
_EXPLICIT_CODEX_PR = {"codex_models": {"pr": {"model": "gpt-5.4-mini", "reasoning_effort": "high"}}}
_PUBLISH_ADAPTER = (
    'CODEX_CONFIG=\'{"approval_policy":"never","model":"gpt-5.4-mini",'
    '"model_reasoning_effort":"high","sandbox_mode":"danger-full-access"}\' '
    "INITIAL_AGENT_MODE=agent-full-access /opt/livespec/codex-acp/bin/codex-acp"
)
_TERRA_CODEX_CONFIG = (
    '{"approval_policy":"never","model":"gpt-5.6-terra",'
    '"model_reasoning_effort":"xhigh","sandbox_mode":"danger-full-access"}'
)


def _write_dispatcher_config(*, repo: Path, dispatcher: dict[str, Any]) -> None:
    config = {"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}
    _ = (repo / _CONFIG_NAME).write_text(json.dumps(config), encoding="utf-8")


def _rendered_adapters(*, repo: Path) -> dict[str, str]:
    """Every node's rendered adapter for a dispatch whose target is `repo`.

    Resolved through the real three-layer merge against this repository's
    committed workflow inputs, then rendered through the real dispatch argv
    builder, so the assertions below grade the string a node's `acp.command`
    would actually receive.
    """
    overlays = resolve_acp_node_overlays(cwd=repo)
    assert not isinstance(overlays, str), overlays
    resolution = resolve_acp_nodes(
        workflow_inputs=workflow_adapter_inputs(
            committed_text=_WORKFLOW_TOML.read_text(encoding="utf-8")
        ),
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
        rendered[node] = value
    return rendered


def test_a_default_dispatch_renders_the_claude_haiku_publish_adapter(tmp_path: Path) -> None:
    """The v107 default: an unconfigured target renders the publish node as the
    Claude Haiku adapter (from the committed workflow.toml), not a Codex one."""
    adapters = _rendered_adapters(repo=tmp_path)
    assert adapters["pr"] == _PUBLISH_DEFAULT_HAIKU
    assert "codex-acp" not in adapters["pr"]
    assert adapters["implement"] == _CLAUDE_OPUS_5_ADAPTER


def test_scenario90_a_codex_pinned_publish_dispatch_renders_both_adapters_in_their_ratified_forms(
    tmp_path: Path,
) -> None:
    """With an explicit `codex_models.pr` table the publish adapter is
    env-then-baked-path; the implementer is unchanged."""
    _write_dispatcher_config(repo=tmp_path, dispatcher=_EXPLICIT_CODEX_PR)
    adapters = _rendered_adapters(repo=tmp_path)

    assert adapters["pr"] == _PUBLISH_ADAPTER
    assert adapters["pr"].endswith(f" {_CODEX_ADAPTER_COMMAND}")
    assert '"model":"gpt-5.4-mini"' in adapters["pr"]
    assert '"model_reasoning_effort":"high"' in adapters["pr"]
    assert " -c model=" not in adapters["pr"]
    assert " -c model_reasoning_effort=" not in adapters["pr"]

    # The value must survive the POSIX tokenization fabro applies before it
    # launches the process. The whole-string assertion above cannot stand in
    # for this one: it is satisfied by whatever bytes the renderer emits, and
    # the two characters that decide whether the adapter can start at all are
    # exactly the ones a reader skims past.
    tokenized = shlex.split(adapters["pr"])[0].removeprefix("CODEX_CONFIG=")
    assert json.loads(tokenized)["model"] == "gpt-5.4-mini"

    assert adapters["implement"] == _CLAUDE_OPUS_5_ADAPTER


def test_scenario90_the_publish_adapter_declares_agent_full_access(tmp_path: Path) -> None:
    """A write-capable Codex class carries INITIAL_AGENT_MODE=agent-full-access."""
    _write_dispatcher_config(repo=tmp_path, dispatcher=_EXPLICIT_CODEX_PR)
    assert "INITIAL_AGENT_MODE=agent-full-access" in _rendered_adapters(repo=tmp_path)["pr"]


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
    that mentions codex-acp at all must mention it as the baked path. An
    explicit `codex_models.pr` table is written so at least one node actually
    renders the Codex adapter rather than the Claude publish default.
    """
    _write_dispatcher_config(repo=tmp_path, dispatcher=_EXPLICIT_CODEX_PR)
    for node, rendered in _rendered_adapters(repo=tmp_path).items():
        if "codex-acp" not in rendered:
            continue
        assert _CODEX_ADAPTER_COMMAND in rendered, node
        assert "@zed-industries/codex-acp" not in rendered, node
        assert "npx --no-install" not in rendered, node


def test_scenario91_the_empty_model_opt_out_omits_the_keys_rather_than_emptying_them(
    tmp_path: Path,
) -> None:
    """An empty model renders the un-pinned base string byte-for-byte."""
    _write_dispatcher_config(
        repo=tmp_path,
        dispatcher={"codex_models": {"implementer": {"model": "", "reasoning_effort": "high"}}},
    )
    implement = _rendered_adapters(repo=tmp_path)["implement"]

    assert '"model"' not in implement
    assert '"model_reasoning_effort"' not in implement
    assert implement == _UNPINNED_BASE
    assert implement == CODEX_ADAPTER_BASE


def test_this_repository_reviews_on_opus_while_its_implementer_stays_on_claude_opus_5() -> None:
    """The negative control, graded on THIS repository's committed configuration.

    One dispatch, three node classes, three different answers: the review node
    reverts to the workflow-default Claude Opus 4.8 review adapter (the
    dispatcher.acp_nodes.review gpt-5.6-terra override was removed 2026-08-28
    after repeated review non-convergence at the Codex review gate; the
    contracts material makes review NOT Codex-backed by default), the publish
    node takes the v107 fleet Claude Haiku default (this repository dropped its
    former Codex `pr` pin so it now inherits that default), and the implementer
    class stays on Claude Opus 5. None of the three is a Codex adapter. Asserting
    them together is the point — a change that accidentally re-providered any one
    would pass any single assertion taken alone.
    """
    adapters = _rendered_adapters(repo=_REPO_ROOT)

    assert "claude-opus-4-8[1m]" in adapters["review"]
    assert "gpt-5.6-terra" not in adapters["review"]
    assert _CODEX_ADAPTER_COMMAND not in adapters["review"]
    assert adapters["review"].endswith(" npx -y @agentclientprotocol/claude-agent-acp")

    assert adapters["implement"] == _CLAUDE_OPUS_5_ADAPTER
    assert "claude-opus-5" in adapters["implement"]
    assert "gpt-5.6-terra" not in adapters["implement"]

    assert adapters["pr"] == _PUBLISH_DEFAULT_HAIKU
    assert _CODEX_ADAPTER_COMMAND not in adapters["pr"]
