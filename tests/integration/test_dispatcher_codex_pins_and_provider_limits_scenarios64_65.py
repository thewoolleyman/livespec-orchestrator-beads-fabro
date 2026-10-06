"""Integration coverage for Codex pins and provider-limit permanence."""

from __future__ import annotations

import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config_acp import resolve_acp_node_overlays
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard import (
    GUARD_SCRIPT_PATH,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    dispatch_fabro_run_inputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    CODEX_ADAPTER_COMMAND,
    build_plan,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    fabro_failure_detail_from_payload,
)

from tests.conftest import ResolveAcpNodes

_CONFIG_NAME = ".livespec.jsonc"
_ACP_WRAPPER = "ACP protocol error"
_CODEX_PROVIDER_LIMIT = (
    'Internal error: {"data": {"message": "You\'ve hit your usage limit. '
    "Visit https://chatgpt.com/codex/settings/usage to purchase more credits "
    'or try again at Aug 20th, 2026 3:33 AM.", '
    '"codex_error_info": "usage_limit_exceeded"}}'
)
_CLAUDE_OPUS_5_ADAPTER = (
    "ANTHROPIC_MODEL=claude-opus-5 CLAUDE_CODE_EFFORT_LEVEL=high "
    "npx -y @agentclientprotocol/claude-agent-acp"
)
_CLAUDE_HAIKU_PR_ADAPTER = (
    "ANTHROPIC_MODEL=claude-haiku-4-5 CLAUDE_CODE_EFFORT_LEVEL=high "
    "npx -y @agentclientprotocol/claude-agent-acp"
)


def _plan(*, repo: Path, resolve: ResolveAcpNodes):
    """One dispatch plan for `repo`, its per-node adapters already resolved.

    The resolution is what a real dispatch carries; a plan without one
    renders no adapter input at all, so these scenarios must resolve to
    assert on the adapters they are about.
    """
    return build_plan(
        repo=repo,
        work_item_id="bd-ib-cxv3",
        workflow_toml=repo / "workflow.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor",
        acp_nodes=resolve(repo=repo),
    )


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


def _input_value(*, inputs: tuple[str, ...], name: str) -> str:
    prefix = f"{name}="
    matches = [value.removeprefix(prefix) for value in inputs if value.startswith(prefix)]
    assert len(matches) == 1
    return _unguarded(rendered=matches[0])


def _write_dispatcher_config(*, repo: Path, dispatcher: dict[str, object]) -> None:
    config = {"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}
    (repo / _CONFIG_NAME).write_text(json.dumps(config), encoding="utf-8")


def _failure_payload(*, cause: str) -> list[object]:
    return [
        {
            "status": {"kind": "failed"},
            "failure": {
                "category": "transient_infra",
                "signature": "fabro|transient_infra|acp",
                "causes": [_ACP_WRAPPER, cause],
            },
        }
    ]


def test_default_dispatch_acp_adapter_is_claude_opus_5(
    tmp_path: Path, resolve_test_acp_nodes: ResolveAcpNodes
) -> None:
    """Scenario 86: absent implementer config renders the Claude default."""
    inputs = dispatch_fabro_run_inputs(plan=_plan(repo=tmp_path, resolve=resolve_test_acp_nodes))
    assert _input_value(inputs=inputs, name="implement_adapter") == _CLAUDE_OPUS_5_ADAPTER


def test_scenario64_an_unconfigured_target_renders_the_claude_structured_defaults(
    tmp_path: Path, resolve_test_acp_nodes: ResolveAcpNodes
) -> None:
    """Scenario 64: no `acp_nodes` table means the built-in per-node defaults.

    "And neither the implementer nor the publish adapter is a Codex adapter
    absent an explicit entry" is the load-bearing half. The two defaults also
    have to DIFFER: a regression collapsing them onto one model would satisfy
    each adapter's own assertion while silently re-pricing the publish node.
    """
    inputs = dispatch_fabro_run_inputs(plan=_plan(repo=tmp_path, resolve=resolve_test_acp_nodes))
    implementer = _input_value(inputs=inputs, name="implement_adapter")
    publish = _input_value(inputs=inputs, name="pr_adapter")

    assert implementer == _CLAUDE_OPUS_5_ADAPTER
    assert publish == _CLAUDE_HAIKU_PR_ADAPTER
    assert CODEX_ADAPTER_COMMAND not in implementer
    assert CODEX_ADAPTER_COMMAND not in publish
    assert implementer != publish


def test_scenario64_a_structured_codex_entry_pins_exactly_the_node_it_names(
    tmp_path: Path, resolve_test_acp_nodes: ResolveAcpNodes
) -> None:
    """Scenario 64: the entry routes ONE node, and leaves every other alone.

    The retired `codex_models` class-shaped shorthand is what made the second
    half worth asserting: `implementer` moved three nodes at once, so "exactly
    the node it names" is the behaviour that REPLACED it, not a restatement of
    what was already true.
    """
    _write_dispatcher_config(
        repo=tmp_path,
        dispatcher={
            "acp_nodes": {"implement": {"agent": "codex-acp", "model": "gpt-5.5", "effort": "high"}}
        },
    )
    inputs = dispatch_fabro_run_inputs(plan=_plan(repo=tmp_path, resolve=resolve_test_acp_nodes))

    assert _input_value(inputs=inputs, name="implement_adapter") == (
        'CODEX_CONFIG=\'{"approval_policy":"never","model":"gpt-5.5",'
        '"model_reasoning_effort":"high","sandbox_mode":"danger-full-access"}\' '
        f"INITIAL_AGENT_MODE=agent-full-access {CODEX_ADAPTER_COMMAND}"
    )
    # The sibling nodes the retired `implementer` class would have moved too.
    assert _input_value(inputs=inputs, name="fix_adapter") == _CLAUDE_OPUS_5_ADAPTER
    assert _input_value(inputs=inputs, name="review_fix_adapter") == _CLAUDE_OPUS_5_ADAPTER
    assert _input_value(inputs=inputs, name="pr_adapter") == _CLAUDE_HAIKU_PR_ADAPTER


def test_scenario64_the_retired_codex_models_key_refuses_and_prints_its_replacement(
    tmp_path: Path,
) -> None:
    """Scenario 64: the retired key refuses before claim, carrying the migration.

    Asserted through `resolve_acp_node_overlays`, the repository-layer reader a
    dispatch actually calls, so this grades the refusal a dispatch would hit
    rather than a helper's ability to produce the message.
    """
    _write_dispatcher_config(
        repo=tmp_path,
        dispatcher={"codex_models": {"implementer": {"model": "gpt-5.5"}}},
    )
    refusal = resolve_acp_node_overlays(cwd=tmp_path)

    assert isinstance(refusal, str), refusal
    assert "dispatcher.codex_models" in refusal
    for node in ("implement", "fix", "review_fix"):
        assert f"dispatcher.acp_nodes.{node}" in refusal
    assert '{"agent": "codex-acp", "model": "gpt-5.5", "effort": "low"}' in refusal


def test_scenario65_provider_usage_ceiling_is_permanent_and_transients_stay_transient() -> None:
    """Scenario 65: provider ceilings are typed permanent failures; transients are not."""
    provider_limit = fabro_failure_detail_from_payload(
        payload=_failure_payload(cause=_CODEX_PROVIDER_LIMIT)
    )
    assert provider_limit is not None
    assert provider_limit.provider_usage_limit is True
    assert provider_limit.category == "deterministic"
    assert provider_limit.signature == "fabro|deterministic|acp"
    assert provider_limit.cause is not None
    assert provider_limit.cause.startswith("You've hit your usage limit.")
    assert "try again at Aug 20th, 2026 3:33 AM." in provider_limit.cause

    transient = fabro_failure_detail_from_payload(
        payload=_failure_payload(cause="connection reset by peer")
    )
    assert transient is not None
    assert transient.provider_usage_limit is False
    assert transient.category == "transient_infra"
    assert transient.signature == "fabro|transient_infra|acp"
    assert transient.cause == "connection reset by peer"
