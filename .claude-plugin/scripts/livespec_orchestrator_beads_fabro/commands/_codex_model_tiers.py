"""Codex model pins for the factory's Codex ACP nodes.

Split out of `_config` so the pin policy -- which carries the measurement
record that justifies its values -- lives next to its own resolver rather than
inside the general connection-resolution module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

__all__: list[str] = [
    "CodexModelTier",
    "CodexModelTiers",
    "codex_model_tiers_from_block",
]

_CODEX_MODELS_KEY = "codex_models"
_IMPLEMENTER_TIER_KEY = "implementer"
_PR_TIER_KEY = "pr"
_TIER_MODEL_KEY = "model"
_TIER_EFFORT_KEY = "reasoning_effort"
_TIER_COMPACTION_KEY = "compaction_token_limit"

# Built-in Codex model pins for the factory's ACP nodes. These are FLEET
# defaults: every repo dispatching through this plugin inherits them unless
# its own `dispatcher.codex_models` block overrides them.
#
# WHY THESE VALUES, and why the pin exists at all. Before this pin the
# implementer adapter carried no model override at all, so the sandbox's Codex
# model was whatever `codex-acp` resolved at runtime. That resolution was NOT
# the current frontier model: the predecessor adapter
# `@zed-industries/codex-acp@0.16.0` shipped a models-manager that could not
# decode the present-day catalog (`unknown variant `max``, the reasoning tier
# the gpt-5.6 line introduced), so it silently fell back to its baked static
# list and landed on `gpt-5.5` at `medium`. Nobody chose that; it was the
# residue of a decode failure.
#
# REACHABLE TIERS, RE-MEASURED FOR THE SUCCESSOR ADAPTER (2026-08-26). The
# reachable set is a property OF THE BAKED ADAPTER VERSION, so the
# Codex-ACP-node-model-pins contract in `SPECIFICATION/contracts.md` requires it
# re-measured whenever that version changes, and requires any recorded table to
# NAME the version it was measured against. This table REPLACES the 2026-08-22
# one, which belonged to the retired predecessor and is no longer true of
# anything the image bakes.
#
# Measured from inside a live Fabro sandbox on image `python-agent-v1.35.0`
# against the REAL projected credential (the Dispatcher's non-rotatable
# auth.json snapshot at `$CODEX_HOME` = /workspace/.codex), driving the
# successor adapter `@agentclientprotocol/codex-acp` 1.6.2 and its bundled
# `@openai/codex` 0.148.0. Each probe was one non-interactive turn.
#
# These six COMPLETED a turn, at the reasoning effort noted where it was not
# the tier default: gpt-5.6-terra at xhigh, gpt-5.6-sol at low, gpt-5.6-luna at
# high, then gpt-5.5, gpt-5.4 and gpt-5.4-mini.
#
# These three REFUSED, each with HTTP 400 "The '<slug>' model is not supported
# when using Codex with a ChatGPT account" and each also warning that model
# metadata for the slug was not found: gpt-5.6, gpt-5.6-codex and
# gpt-5.3-codex.
#
# THE THREE REFUSED SLUGS ARE EXACTLY THE THREE ABSENT FROM THE CATALOG the
# adapter fetches (`$CODEX_HOME/models_cache.json`, client_version 0.148.0),
# which lists `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5`,
# `gpt-5.4`, `gpt-5.4-mini` and `gpt-5.3-codex-spark`. So the refusal is an
# account/catalog boundary rather than an adapter-version one: the 2026-08-22
# "requires a newer version of Codex" refusal that blocked the WHOLE gpt-5.6
# line is GONE, which is the entire point of the package succession.
# `gpt-5.3-codex` is a slug the catalog no longer carries at all (it ships
# `gpt-5.3-codex-spark` instead), so its refusal names a model that no longer
# exists rather than a tier withheld from this account.
#
# REASONING LEVELS, from the same catalog read: every listed gpt-5.6 slug
# accepts `xhigh`; `gpt-5.6-sol` and `gpt-5.6-terra` go on to `max` and
# `ultra`, `gpt-5.6-luna` stops at `max`, and `gpt-5.5` / `gpt-5.4` /
# `gpt-5.4-mini` stop at `xhigh`.
#
# The implementer holds `gpt-5.5` and drops only its reasoning effort: a
# weaker implementer buys token savings at the cost of extra `review_fix`
# rounds, which are themselves Codex turns, so the cut that does not risk
# paying for itself twice is effort rather than model.
#
# THESE ARE NO LONGER THE FLEET DEFAULT FOR EITHER NODE. Since the v107
# revision the pr node's fleet default is the workflow's model-agnostic
# Claude Haiku adapter, and the implementer node's is the Claude Opus
# adapter; a tier's Codex overlay is emitted ONLY when its `codex_models`
# entry is an explicit table (`_acp_node_repository._has_explicit_*_tier`).
# So these `_DEFAULT_*` values are consumed ONLY as the PARTIAL-TABLE
# fallback: a repository that writes a `codex_models.pr` (or `.implementer`)
# table but omits `model` or `reasoning_effort` inherits the missing key
# from here. `_DEFAULT_PR_MODEL` is therefore held at a LIVE Codex slug
# (`gpt-5.3-codex-spark`, measured reachable on the ChatGPT-account catalog
# 2026-09-09) rather than the retired `gpt-5.4-mini`, so a partial pr table
# never renders a slug the account catalog has dropped.
_DEFAULT_IMPLEMENTER_MODEL = "gpt-5.5"
_DEFAULT_IMPLEMENTER_EFFORT = "low"
_DEFAULT_PR_MODEL = "gpt-5.3-codex-spark"
_DEFAULT_PR_EFFORT = "high"


@dataclass(frozen=True, kw_only=True)
class CodexModelTier:
    """Resolved Codex model pin for one class of factory ACP node.

    An EMPTY `model` is the explicit opt-out: the adapter is emitted with NO
    `model` key and NO `model_reasoning_effort` key inside `CODEX_CONFIG` --
    the keys are absent rather than present-and-empty -- restoring the pre-pin
    behaviour of letting `codex-acp` resolve its own default. It is spelled as
    an empty string rather than a missing key so an operator can disable the
    pin without deleting the surrounding documentation.

    `compaction_token_limit` is the Codex `model_auto_compact_token_limit`
    for the nodes this tier backs, and ZERO means "unset" -- the same
    "configure nothing, change nothing" shape as the empty `model`. It
    belongs here rather than in a key of its own because THIS is the
    per-node Codex configuration surface. Unlike the model pins, which moved
    onto the adapter's `CODEX_CONFIG` environment channel with the package
    succession, the limit stays an adapter ARGUMENT -- which is where the
    ACP-node-timeouts contract in `SPECIFICATION/contracts.md` puts it.

    WHY THE LIMIT IS WORTH CONFIGURING AT ALL. Reaching Codex's
    auto-compaction threshold mid-turn is what made a long implement turn
    fatal: at the threshold Codex calls a remote compaction endpoint that is
    dead, with no local fallback, so the turn dies rather than compacting.
    A node still backed by Codex can therefore need its threshold moved --
    and moving it must not require an orchestrator code change.
    """

    model: str
    reasoning_effort: str
    compaction_token_limit: int = 0

    @property
    def pinned(self) -> bool:
        """Whether this tier contributes model overrides to the adapter."""
        return self.model != ""


@dataclass(frozen=True, kw_only=True)
class CodexModelTiers:
    """The per-node-class Codex pins resolved for one dispatch."""

    implementer: CodexModelTier
    pr: CodexModelTier


def codex_model_tiers_from_block(*, block: dict[str, Any]) -> CodexModelTiers:
    """Resolve the factory's Codex model pins from a dispatcher config block.

    Reads `dispatcher.codex_models`. Each tier entry is an optional
    `{"model": ..., "reasoning_effort": ...}` table; a missing entry, a
    non-table entry, or a missing key falls back to the built-in default for
    that tier, so a partial override is legal. A tier whose `model` is the
    empty string is the opt-out described on `CodexModelTier` and carries an
    empty effort with it -- an effort without a model would be a pin the
    adapter cannot express.

    There is deliberately NO AD-HOC SHELL environment override. The pins are a
    steady-state cost policy read once per dispatch on the orchestrator host;
    reading them from the host's ambient environment would let an ad-hoc shell
    silently re-tier the whole factory with nothing in the committed record to
    show for it.

    That rule does NOT constrain the adapter's OWN DECLARED env map, which is
    where the resolved pins are rendered (`CODEX_CONFIG`). The distinction is
    load-bearing rather than pedantic: that map is committed configuration,
    rendered verbatim into the recorded adapter string and journaled with the
    layer that supplied each key, so it leaves exactly the committed record an
    ambient seam would destroy.
    """
    models_raw = block.get(_CODEX_MODELS_KEY)
    models = cast("dict[str, Any]", models_raw) if isinstance(models_raw, dict) else {}
    return CodexModelTiers(
        implementer=_codex_model_tier(
            entry=models.get(_IMPLEMENTER_TIER_KEY),
            default_model=_DEFAULT_IMPLEMENTER_MODEL,
            default_effort=_DEFAULT_IMPLEMENTER_EFFORT,
        ),
        pr=_codex_model_tier(
            entry=models.get(_PR_TIER_KEY),
            default_model=_DEFAULT_PR_MODEL,
            default_effort=_DEFAULT_PR_EFFORT,
        ),
    )


def _codex_model_tier(
    *,
    entry: object,
    default_model: str,
    default_effort: str,
) -> CodexModelTier:
    if not isinstance(entry, dict):
        return CodexModelTier(model=default_model, reasoning_effort=default_effort)
    table = cast("dict[str, Any]", entry)
    compaction = _tier_compaction_token_limit(value=table.get(_TIER_COMPACTION_KEY))
    model_raw = table.get(_TIER_MODEL_KEY)
    model = model_raw if isinstance(model_raw, str) else default_model
    if model == "":
        return CodexModelTier(model="", reasoning_effort="", compaction_token_limit=compaction)
    return CodexModelTier(
        model=model,
        reasoning_effort=_tier_effort(value=table.get(_TIER_EFFORT_KEY), default=default_effort),
        compaction_token_limit=compaction,
    )


def _tier_compaction_token_limit(*, value: object) -> int:
    """The configured compaction token limit, or 0 when none is configured.

    `bool` is excluded explicitly: it is an `int` subclass, so `true` would
    otherwise resolve to a one-token compaction threshold -- a value that
    reads as configured and makes every turn compact immediately.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(0, value)


def _tier_effort(*, value: object, default: str) -> str:
    return value if isinstance(value, str) and value != "" else default
