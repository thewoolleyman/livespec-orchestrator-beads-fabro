"""The COMMITTED model-catalog snapshot, and the digest that identifies it.

`SPECIFICATION/contracts.md` section "Agent and model catalogs" seeds this
catalog "from upstream Fabro's model catalog where that catalog carries the
model and extended for models it does not, including the ratified Codex
ChatGPT-account diagnostic".

WHICH MODELS ARE HERE, AND WHY NOT MORE. Every entry below is one this
repository has MEASURED or the ratified specification NAMES:

- The four Anthropic models the workflow's own declared adapter inputs and
  section "Built-in ACP node defaults" name (`claude-opus-5`,
  `claude-haiku-4-5`, plus the review and disposition adapters' `claude-opus-4-8`
  and its Sonnet sibling).
- The seven OpenAI slugs MEASURED reachable-or-refused from inside a live Fabro
  sandbox against the real projected credential; the measurement record, its
  date and the adapter version it was taken against are in `_codex_model_tiers`.
- `zai/glm-5.2`, which `SPECIFICATION/scenarios.md` Scenario 129 names as the
  provider-qualified reference a multi-provider agent takes.

NOTHING ELSE IS INVENTED, and the gap is deliberate rather than unfinished. A
model this file does not declare makes a structured candidate REFUSE before
claim, naming the model and the provider -- which is a legible refusal an
operator fixes with one `dispatcher.model_catalog` entry. The alternative, a
catalog padded with slugs nobody measured, turns that legible refusal into a
dispatch that launches and fails at the provider, with a catalog entry standing
behind it that reads like evidence.

THE SIGNATURES ARE MEASUREMENTS, NOT DOCUMENTATION. The ChatGPT-account
diagnostic the contract requires is the one measured at the v107 `pr`-node
outage, and it is carried on the OpenAI entries whose account boundary produced
it rather than on every model in the file: a signature lent to a model whose
adapter never emits it classifies somebody else's failure as that candidate's.
`_acp_builtin_signatures` holds the same measurement for the built-in domains
and records where each came from.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_agent_catalog import (
    ANTHROPIC_PROVIDER,
    OPENAI_PROVIDER,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_pricing import (
    PRICE_FIELDS,
    AcpCandidatePricing,
)
from livespec_orchestrator_beads_fabro.commands._acp_catalog_overrides import catalog_overrides
from livespec_orchestrator_beads_fabro.commands._acp_model_entry import (
    AcpModelEntry,
    parse_model_entry,
)
from livespec_orchestrator_beads_fabro.commands._acp_model_prices import builtin_model_pricing

__all__: list[str] = [
    "MODEL_CATALOG_KEY",
    "builtin_model_catalog",
    "model_catalog_digest",
    "resolve_model_catalog",
]

# The per-repository additions key, in the same committed-configuration-only
# class as `dispatcher.agent_catalog`.
MODEL_CATALOG_KEY = "model_catalog"

_ZAI_PROVIDER = "zai"

# (model id, display name) for each provider. The canonical id equals the model
# id for every entry here: none of these providers exposes a longer canonical
# spelling, and inventing a divergence would make `canonical_id` untestable.
_ANTHROPIC_MODELS: tuple[tuple[str, str], ...] = (
    ("claude-opus-5", "Claude Opus 5"),
    ("claude-opus-4-8", "Claude Opus 4.8"),
    ("claude-sonnet-4-6", "Claude Sonnet 4.6"),
    ("claude-haiku-4-5", "Claude Haiku 4.5"),
)

# MEASURED 2026-09-09 from the ChatGPT-account catalog the baked adapter fetches
# (`$CODEX_HOME/models_cache.json`, client_version 0.148.0). Six completed a
# turn; `gpt-5.3-codex-spark` is the live slug that replaced the retired
# `gpt-5.3-codex`. `_codex_model_tiers` carries the full record, including the
# three slugs the account refuses and why their refusal is an account boundary
# rather than an adapter-version one.
_OPENAI_MODELS: tuple[tuple[str, str], ...] = (
    ("gpt-5.6-terra", "GPT-5.6 Terra"),
    ("gpt-5.6-sol", "GPT-5.6 Sol"),
    ("gpt-5.6-luna", "GPT-5.6 Luna"),
    ("gpt-5.5", "GPT-5.5"),
    ("gpt-5.4", "GPT-5.4"),
    ("gpt-5.4-mini", "GPT-5.4 Mini"),
    ("gpt-5.3-codex-spark", "GPT-5.3 Codex Spark"),
)

_ZAI_MODELS: tuple[tuple[str, str], ...] = (("glm-5.2", "GLM 5.2"),)

_PROVIDER_MODELS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (ANTHROPIC_PROVIDER, _ANTHROPIC_MODELS),
    (OPENAI_PROVIDER, _OPENAI_MODELS),
    (_ZAI_PROVIDER, _ZAI_MODELS),
)


def builtin_model_catalog() -> Mapping[str, AcpModelEntry]:
    """The shipped snapshot, keyed by `provider/model`.

    `pricing` comes from the shared base-rate table in `_acp_model_prices`,
    which is the same fact the per-token price table the legacy host-OTLP span
    path reads is built from. A model with no published rate there carries NO
    pricing, and that absence is the honest value: the cost paragraph's
    no-default rule turns it into an explicit unobservable cost rather than a
    guess summed into an observation.
    """
    entries = [
        AcpModelEntry(
            provider=provider,
            model=model,
            display_name=display_name,
            canonical_id=model,
            pricing=builtin_model_pricing(model=model),
        )
        for provider, models in _PROVIDER_MODELS
        for model, display_name in models
    ]
    return {entry.key: entry for entry in entries}


def resolve_model_catalog(*, block: Mapping[str, Any]) -> Mapping[str, AcpModelEntry] | str:
    """The shipped snapshot with this repository's own entries applied, or refuse."""
    overrides = catalog_overrides(block=block, config_key=MODEL_CATALOG_KEY)
    if isinstance(overrides, str):
        return overrides
    catalog = dict(builtin_model_catalog())
    for catalog_key, entry in overrides.items():
        parsed = parse_model_entry(
            catalog_key=catalog_key,
            entry=entry,
            key=f"dispatcher.{MODEL_CATALOG_KEY}.{catalog_key}",
        )
        if isinstance(parsed, str):
            return parsed
        catalog[catalog_key] = parsed
    return catalog


def model_catalog_digest(*, catalog: Mapping[str, AcpModelEntry]) -> str:
    """A deterministic digest of the shipped model catalog's identity fields.

    The projection covers what a RENDER depends on -- the key, the canonical id
    the adapter is given, the display name the derived identity uses, and the
    aliases an operator may write -- plus, since
    `acp-catalog-pricing-and-signatures` landed, the entry's PRICING. The
    pricing extension is the one this function's own prior wording promised:
    "that item extends this projection when it lands, which is a digest change
    and therefore a snapshot change -- which is the correct signal rather than
    a cost of the omission". A digest blind to pricing would let a re-priced
    catalog ship under an unchanged snapshot id, and a re-priced catalog is
    exactly what changes every derived run cost downstream of it.

    Availability signatures stay OUT, and the reason is the same one that kept
    pricing out until now: no shipped entry carries one, so including them
    would put a field into the digest that no committed byte can vary.
    """
    return _digest(
        payload=[
            [
                key,
                entry.canonical_id,
                entry.display_name,
                list(entry.aliases),
                _pricing_projection(pricing=entry.pricing),
            ]
            for key, entry in sorted(catalog.items())
        ]
    )


def _pricing_projection(*, pricing: AcpCandidatePricing | None) -> list[object] | None:
    """One entry's price table as a positional list, or None when unpriced.

    Positional rather than a mapping so the projection cannot vary with
    `PRICE_FIELDS`' spelling, and keyed off that tuple rather than off four
    literals so a fifth priced component added to the grammar enters the digest
    without a second edit here.
    """
    if pricing is None:
        return None
    return [pricing.model, *(getattr(pricing, name) for name in PRICE_FIELDS)]


def _digest(*, payload: object) -> str:
    """The sha256 of one canonical JSON serialization."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
