"""Structured provider errors recorded inside successful ACP turn output.

Some ACP adapters return a provider error as their final response while the
engine still books the agent node as succeeded.  This module reads only those
recorded agent responses and preserves the provider's embedded message as a
typed terminal observation.  It deliberately does not classify a refusal as a
usage ceiling: a rejected model can be permanent for this run without spending
the provider allowance.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import (
    NODE_INPUT_CANDIDATES,
    AcpAdapter,
    parse_adapter_string,
)
from livespec_orchestrator_beads_fabro.commands._fabro_turn_output import succeeded_agent_turns

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan

__all__: list[str] = [
    "ProviderRefusal",
    "provider_refusal_detail",
    "provider_refusal_from_turns",
]


@dataclass(frozen=True, kw_only=True)
class ProviderRefusal:
    """One provider rejection the engine incorrectly recorded as an ACP success."""

    node: str
    message: str
    adapter: str
    model: str | None


def provider_refusal_from_turns(
    *, plan: DispatchPlan, payload: object | None
) -> ProviderRefusal | None:
    """The latest succeeded ACP turn carrying a structured provider error, if any."""
    for turn in reversed(succeeded_agent_turns(payload=payload)):
        message = _provider_message(text=turn.output)
        if message is None:
            continue
        adapter = _adapter_for(plan=plan, node=turn.node)
        if adapter is None:
            continue
        return ProviderRefusal(
            node=turn.node,
            message=message,
            adapter=adapter.command,
            model=_model(adapter_config=adapter.env.get("CODEX_CONFIG")),
        )
    return None


def provider_refusal_detail(*, refusal: ProviderRefusal) -> str:
    """Render the selected ACP adapter and model with the provider's cause."""
    model = refusal.model or "(model not recorded)"
    return (
        f"provider refusal at ACP node {refusal.node} using adapter {refusal.adapter} "
        f"with model {model}: {refusal.message}"
    )


def _provider_message(*, text: str | None) -> str | None:
    """The embedded error message in a structured provider error response."""
    if text is None:
        return None
    decoder = json.JSONDecoder()
    for offset, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[offset:])
        except json.JSONDecodeError:
            continue
        message = _error_message(value=value)
        if message is not None:
            return message
    return None


def _error_message(*, value: object) -> str | None:
    """Validate the provider's structured error shape and return its message."""
    payload = cast("dict[str, object]", value)
    status = payload.get("status")
    error = payload.get("error")
    if payload.get("type") != "error" or not isinstance(status, int) or isinstance(status, bool):
        return None
    if not isinstance(error, dict):
        return None
    message = cast("dict[str, object]", error).get("message")
    return message.strip() if isinstance(message, str) and message.strip() else None


def _adapter_for(*, plan: DispatchPlan, node: str) -> AcpAdapter | None:
    """The selected adapter this node ran, from the dispatch's resolved inputs."""
    resolution = plan.acp_nodes
    if resolution is None:
        return None
    inputs = dict(pair.split("=", 1) for pair in resolution.run_inputs if "=" in pair)
    name = next((name for name in NODE_INPUT_CANDIDATES.get(node, ()) if name in inputs), None)
    return None if name is None else parse_adapter_string(text=inputs[name])


def _model(*, adapter_config: str | None) -> str | None:
    """The Codex model named by the adapter configuration, when it is readable."""
    if adapter_config is None:
        return None
    try:
        parsed: object = json.loads(adapter_config)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    model = cast("dict[str, object]", parsed).get("model")
    return model if isinstance(model, str) and model else None
