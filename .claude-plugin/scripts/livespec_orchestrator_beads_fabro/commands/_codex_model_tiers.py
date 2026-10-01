"""The Codex ACP adapter's RENDERED SETTINGS, as one value `codex_adapter` takes.

WHAT THIS MODULE IS AFTER THE RETIREMENT, because its name outlived its old job.
It used to resolve `dispatcher.codex_models` -- a class-shaped shorthand naming
one model per NODE CLASS -- into per-class pins. `SPECIFICATION/contracts.md`
section "Built-in ACP node defaults" retired that key
(`_acp_codex_models_retired` now refuses it), so nothing reads configuration
here any more and there are no tiers to resolve.

What survives is the VALUE TYPE the Codex renderer takes: `codex_adapter` turns
a model, a reasoning effort and a compaction limit into the adapter's
`CODEX_CONFIG` object and its arguments, and it needs those three carried
together. They now arrive from a STRUCTURED candidate resolved through the agent
and model catalogs rather than from a configuration block, which is why the
reachable-model measurement record that used to justify particular default
values lives with the catalog entries that declare them -- `_acp_model_catalog`
-- instead of here. A type with no resolver is the whole point: there is no
second place a Codex model can come from.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "CodexModelTier",
]


@dataclass(frozen=True, kw_only=True)
class CodexModelTier:
    """The Codex settings one rendered adapter carries.

    An EMPTY `model` is the explicit UN-PINNED OPT-OUT: the adapter is emitted
    with NO `model` key and NO `model_reasoning_effort` key inside
    `CODEX_CONFIG` -- the keys are absent rather than present-and-empty --
    letting `codex-acp` resolve its own default. Section "Built-in ACP node
    defaults" defines that opt-out as byte-identity against the un-pinned base
    string, so a present-but-empty key would not satisfy it: it is a
    differently-spelled pin, not the absence of one.

    `compaction_token_limit` is the Codex `model_auto_compact_token_limit`, and
    ZERO means "unset" -- the same "configure nothing, change nothing" shape as
    the empty `model`. Unlike the model pin, which rides the `CODEX_CONFIG`
    environment channel, the limit stays an adapter ARGUMENT, which is where
    section "ACP node timeouts" puts it.

    WHY THE LIMIT IS WORTH CARRYING AT ALL. Reaching Codex's auto-compaction
    threshold mid-turn is what made a long implement turn fatal: at the
    threshold Codex calls a remote compaction endpoint that is dead, with no
    local fallback, so the turn dies rather than compacting. A node backed by
    Codex can therefore need its threshold moved -- and moving it must not
    require an orchestrator code change.
    """

    model: str
    reasoning_effort: str
    compaction_token_limit: int = 0

    @property
    def pinned(self) -> bool:
        """Whether this tier contributes model overrides to the adapter."""
        return self.model != ""
