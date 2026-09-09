"""Codex model-tier resolution for the factory's Codex ACP nodes.

The factory's implementer adapter carried no `-c model=` override, so the
sandbox's Codex model was whatever `codex-acp` resolved at runtime rather than
anything anyone chose. These tests bind the pin: built-in fleet defaults, the
per-repo `dispatcher.codex_models` override, and the empty-model opt-out.
"""

from __future__ import annotations

import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _config
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import resolve_acp_nodes
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_nodes import (
    dispatch_acp_overlays,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import dispatch_fabro_run_inputs
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_argv import CODEX_ADAPTER_BASE
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan

_CONFIG_NAME = ".livespec.jsonc"
_CLAUDE_OPUS_5_ADAPTER = (
    "ANTHROPIC_MODEL=claude-opus-5 CLAUDE_CODE_EFFORT_LEVEL=high "
    "npx -y @agentclientprotocol/claude-agent-acp"
)
_CLAUDE_ADAPTER = "npx -y @agentclientprotocol/claude-agent-acp"
_CLAUDE_HAIKU_PR_ADAPTER = (
    "ANTHROPIC_MODEL=claude-haiku-4-5 CLAUDE_CODE_EFFORT_LEVEL=high "
    "npx -y @agentclientprotocol/claude-agent-acp"
)

# The workflow-defaults layer these tests resolve against — one adapter
# input per ACP node, mirroring this repo's committed workflow. The
# `codex_models` shorthand is a PER-REPOSITORY layer, so it must be seen
# beating these defaults rather than asserted in isolation. The `pr_adapter`
# default is the Claude Haiku publish adapter, mirroring the committed
# workflow.toml since the v107 revision.
_WORKFLOW_INPUTS = {
    "implement_adapter": _CLAUDE_OPUS_5_ADAPTER,
    "fix_adapter": _CLAUDE_OPUS_5_ADAPTER,
    "review_fix_adapter": _CLAUDE_OPUS_5_ADAPTER,
    "pr_adapter": _CLAUDE_HAIKU_PR_ADAPTER,
    "review_adapter": _CLAUDE_ADAPTER,
    "disposition_adapter": _CLAUDE_ADAPTER,
}


def _write_dispatcher_config(*, cwd: Path, dispatcher: dict[str, object]) -> None:
    _ = (cwd / _CONFIG_NAME).write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}),
        encoding="utf-8",
    )


def _dispatch_inputs(*, repo: Path) -> tuple[str, ...]:
    """The `--input` pairs a dispatch of `repo` renders, adapters resolved."""
    overlays = _config.resolve_acp_node_overlays(cwd=repo)
    assert not isinstance(overlays, str), overlays
    resolution = resolve_acp_nodes(
        workflow_inputs=_WORKFLOW_INPUTS,
        repository=overlays,
        dispatch=dispatch_acp_overlays(overrides=()),
    )
    assert not isinstance(resolution, str), resolution
    return dispatch_fabro_run_inputs(
        plan=build_plan(
            repo=repo,
            work_item_id="bd-ib-test",
            workflow_toml=repo / "workflow.toml",
            goal_file=repo / "goal.md",
            fabro_bin="fabro",
            janitor=None,
            janitor_checkout=repo / "janitor",
            acp_nodes=resolution,
        )
    )


def _input(*, inputs: tuple[str, ...], name: str) -> str:
    """The single `--input` pair for one workflow input name."""
    matches = [pair for pair in inputs if pair.startswith(f"{name}=")]
    assert len(matches) == 1, (name, inputs)
    return matches[0]


def test_default_dispatch_adapters_are_claude(tmp_path: Path) -> None:
    """An unconfigured target defaults BOTH classes to Claude: Opus 5 for the
    implementer nodes, Haiku for the publish node — no Codex adapter absent an
    explicit tier."""
    inputs = _dispatch_inputs(repo=tmp_path)
    implement = _input(inputs=inputs, name="implement_adapter")
    assert implement == f"implement_adapter={_CLAUDE_OPUS_5_ADAPTER}"
    assert "@agentclientprotocol/claude-agent-acp" in implement
    assert _input(inputs=inputs, name="pr_adapter") == f"pr_adapter={_CLAUDE_HAIKU_PR_ADAPTER}"
    assert "codex-acp" not in _input(inputs=inputs, name="pr_adapter")


def test_a_plan_without_a_resolution_passes_no_adapter_input(tmp_path: Path) -> None:
    """No resolution means no adapter override, leaving the workflow's own defaults.

    This is what keeps a hard-coded provider out of the package entirely:
    the un-resolved path does not fall back to an adapter string, it
    declines to override, and fabro applies the workflow's declared default.
    """
    inputs = dispatch_fabro_run_inputs(
        plan=build_plan(
            repo=tmp_path,
            work_item_id="bd-ib-test",
            workflow_toml=tmp_path / "workflow.toml",
            goal_file=tmp_path / "goal.md",
            fabro_bin="fabro",
            janitor=None,
            janitor_checkout=tmp_path / "janitor",
        )
    )
    assert not [pair for pair in inputs if pair.endswith("_adapter") or "_adapter=" in pair]
    assert inputs == (
        "review_fix_visit_cap=4",
        "merge_on_review_cap_outcome=__merge_on_review_cap_disabled__",
        "merge_hold=false",
    )


def test_explicit_implementer_pin_keeps_codex_acp_adapter(tmp_path: Path) -> None:
    """A target can stay on Codex by naming the implementer tier explicitly."""
    _write_dispatcher_config(
        cwd=tmp_path,
        dispatcher={
            "codex_models": {"implementer": {"model": "gpt-5.4", "reasoning_effort": "high"}}
        },
    )
    inputs = _dispatch_inputs(repo=tmp_path)
    assert _input(inputs=inputs, name="implement_adapter") == (
        'implement_adapter=CODEX_CONFIG=\'{"approval_policy":"never","model":"gpt-5.4",'
        '"model_reasoning_effort":"high","sandbox_mode":"danger-full-access"}\' '
        "INITIAL_AGENT_MODE=agent-full-access /opt/livespec/codex-acp/bin/codex-acp"
    )


def test_empty_implementer_model_keeps_codex_base_adapter(tmp_path: Path) -> None:
    """An explicit implementer table can opt out of Codex pins, not Codex."""
    _write_dispatcher_config(
        cwd=tmp_path,
        dispatcher={"codex_models": {"implementer": {"model": "", "reasoning_effort": "high"}}},
    )
    inputs = _dispatch_inputs(repo=tmp_path)
    assert (
        _input(inputs=inputs, name="implement_adapter") == f"implement_adapter={CODEX_ADAPTER_BASE}"
    )


def test_implementer_table_without_model_keeps_codex_default_adapter(
    tmp_path: Path,
) -> None:
    """An implementer table missing `model` routes to Codex with defaults."""
    _write_dispatcher_config(
        cwd=tmp_path,
        dispatcher={"codex_models": {"implementer": {"reasoning_effort": "high"}}},
    )
    inputs = _dispatch_inputs(repo=tmp_path)
    assert _input(inputs=inputs, name="implement_adapter") == (
        'implement_adapter=CODEX_CONFIG=\'{"approval_policy":"never","model":"gpt-5.5",'
        '"model_reasoning_effort":"high","sandbox_mode":"danger-full-access"}\' '
        "INITIAL_AGENT_MODE=agent-full-access /opt/livespec/codex-acp/bin/codex-acp"
    )


def test_absent_config_resolves_the_builtin_partial_table_fallback_tiers(tmp_path: Path) -> None:
    """The raw tier resolver returns each tier's built-in Codex fallback — the
    values a partial `codex_models.<tier>` table inherits for a missing key.
    These are NO LONGER the fleet default adapters (those are the Claude
    workflow defaults resolved through the overlay layer); a tier's Codex
    overlay is emitted only for an explicit table."""
    tiers = _config.resolve_codex_model_tiers(cwd=tmp_path)
    assert tiers.implementer.model == "gpt-5.5"
    assert tiers.implementer.reasoning_effort == "low"
    assert tiers.implementer.pinned is True
    assert tiers.pr.model == "gpt-5.3-codex-spark"
    assert tiers.pr.reasoning_effort == "high"
    assert tiers.pr.pinned is True


def test_configured_tiers_override_the_builtin_defaults(tmp_path: Path) -> None:
    """A repo's own `codex_models` block wins over the built-in defaults."""
    _write_dispatcher_config(
        cwd=tmp_path,
        dispatcher={
            "codex_models": {
                "implementer": {"model": "gpt-5.4", "reasoning_effort": "high"},
                "pr": {"model": "gpt-5.4-mini", "reasoning_effort": "low"},
            }
        },
    )
    tiers = _config.resolve_codex_model_tiers(cwd=tmp_path)
    assert tiers.implementer.model == "gpt-5.4"
    assert tiers.implementer.reasoning_effort == "high"
    assert tiers.pr.reasoning_effort == "low"


def test_partial_tier_entry_falls_back_per_key(tmp_path: Path) -> None:
    """A tier naming only a model keeps the built-in effort for that tier."""
    _write_dispatcher_config(
        cwd=tmp_path,
        dispatcher={"codex_models": {"implementer": {"model": "gpt-5.4"}}},
    )
    tiers = _config.resolve_codex_model_tiers(cwd=tmp_path)
    assert tiers.implementer.model == "gpt-5.4"
    assert tiers.implementer.reasoning_effort == "low"
    assert tiers.pr.model == "gpt-5.3-codex-spark"


def test_empty_model_is_the_explicit_opt_out(tmp_path: Path) -> None:
    """`"model": ""` drops the pin entirely rather than defaulting it back."""
    _write_dispatcher_config(
        cwd=tmp_path,
        dispatcher={"codex_models": {"implementer": {"model": "", "reasoning_effort": "high"}}},
    )
    tiers = _config.resolve_codex_model_tiers(cwd=tmp_path)
    assert tiers.implementer.model == ""
    assert tiers.implementer.reasoning_effort == ""
    assert tiers.implementer.pinned is False
    assert tiers.pr.pinned is True


def test_malformed_tier_entries_fall_back_to_defaults(tmp_path: Path) -> None:
    """A non-table tier entry is ignored rather than crashing the dispatch."""
    _write_dispatcher_config(
        cwd=tmp_path,
        dispatcher={"codex_models": {"implementer": "gpt-5.4", "pr": [1, 2]}},
    )
    tiers = _config.resolve_codex_model_tiers(cwd=tmp_path)
    assert tiers.implementer.model == "gpt-5.5"
    assert tiers.pr.model == "gpt-5.3-codex-spark"
