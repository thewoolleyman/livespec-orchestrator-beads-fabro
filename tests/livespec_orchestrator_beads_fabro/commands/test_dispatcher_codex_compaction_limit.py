"""The Codex compaction token limit, as the rendered adapter carries it.

Reaching Codex's auto-compaction threshold mid-turn is what made a long
implement turn fatal: at the threshold Codex calls a remote compaction
endpoint that is dead, with no local fallback. A node still backed by Codex
therefore needs that threshold movable WITHOUT an orchestrator code change.
Unlike the model pin, which rides the adapter's `CODEX_CONFIG` environment
channel, the limit stays an adapter ARGUMENT
(`-c model_auto_compact_token_limit=`) — which is where contracts.md section
"ACP node timeouts" puts it.

THESE CASES DRIVE THE RENDERER RATHER THAN A CONFIGURATION READER, AND THE
REASON IS THE RETIREMENT. The limit used to resolve from
`dispatcher.codex_models` alongside the model pins; contracts.md section
"Built-in ACP node defaults" retired that key, so there is no class-shaped
reader left to assert against. The surviving claim is about what
`codex_adapter` RENDERS from the settings it is handed — which is exactly
what a node needing the threshold moved now writes as an ordinary manual-form
`args` entry.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._codex_model_tiers import CodexModelTier
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_argv import (
    CODEX_ADAPTER_BASE,
    codex_adapter,
)


def test_configured_compaction_limit_rides_the_adapter_c_channel() -> None:
    """A configured limit renders as `-c model_auto_compact_token_limit=`.

    The model pin rides `CODEX_CONFIG` while the limit rides the argument
    channel, so this also pins the two apart: a regression that moved the limit
    into `CODEX_CONFIG` alongside the model would change this string.
    """
    tier = CodexModelTier(model="gpt-5.5", reasoning_effort="low", compaction_token_limit=300000)

    assert codex_adapter(tier=tier) == (
        'CODEX_CONFIG=\'{"approval_policy":"never","model":"gpt-5.5",'
        '"model_reasoning_effort":"low","sandbox_mode":"danger-full-access"}\' '
        "INITIAL_AGENT_MODE=agent-full-access /opt/livespec/codex-acp/bin/codex-acp "
        "-c model_auto_compact_token_limit=300000"
    )


def test_unconfigured_compaction_limit_renders_nothing() -> None:
    """ZERO is "unset": the argument is absent, not present-and-zero."""
    tier = CodexModelTier(model="gpt-5.5", reasoning_effort="low")

    assert tier.compaction_token_limit == 0
    assert "model_auto_compact_token_limit" not in codex_adapter(tier=tier)


def test_compaction_limit_survives_the_model_opt_out() -> None:
    """A node opting out of the model pin still carries its own limit.

    Folding the limit into the pinned branch would drop it for exactly this
    configuration — a node letting `codex-acp` pick its model while still
    needing its compaction threshold moved.
    """
    tier = CodexModelTier(model="", reasoning_effort="", compaction_token_limit=120000)

    assert tier.pinned is False
    assert codex_adapter(tier=tier) == (
        f"{CODEX_ADAPTER_BASE} -c model_auto_compact_token_limit=120000"
    )


def test_a_non_positive_limit_renders_nothing() -> None:
    """A zero or negative threshold is not a one-token threshold that always compacts."""
    for value in (0, -1):
        tier = CodexModelTier(model="gpt-5.5", reasoning_effort="low", compaction_token_limit=value)

        assert "model_auto_compact_token_limit" not in codex_adapter(tier=tier)
