"""ONE MODEL CATALOG ENTRY: its canonical id, its aliases, its price, its signatures.

`SPECIFICATION/contracts.md` section "Agent and model catalogs": model entries
"are keyed by `provider/model` and carry the canonical model id, aliases, the
four USD-per-million prices in the `pricing` shape of the
factory-configurable-ACP-fallback-priority section, and measured availability
signatures in that section's signature grammar."

WHY THE KEY IS DERIVED RATHER THAN STORED. The `provider/model` key and the
entry's own `provider` / `model` fields are the same fact written twice, and two
copies of one fact drift: a catalog table whose key said `openai/gpt-5.5` while
its entry said `provider: anthropic` would resolve one way on lookup and price
another way on read. `key` is a property of the entry, so the two cannot
disagree.

PRICING AND SIGNATURES ARE OPTIONAL, AND THE ABSENCE IS THE HONEST VALUE. The
same section makes a per-candidate override win over the catalog value and
applies "the all-or-none pricing rule ... to catalog entry and override alike",
so an entry either carries all four prices or none. An entry whose price this
repository has not MEASURED carries none rather than a plausible guess: a
guessed price is summed into a run cost and read as an observation, which is
worse than a gap a reader can see. The catalog-first cost path is a separate
ratified item (`acp-catalog-pricing-and-signatures`) and is not this module's
job; this module only has to be able to HOLD what that item will populate.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_candidate_pricing import (
    AcpCandidatePricing,
    parse_candidate_pricing,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_signatures import (
    AcpAvailabilitySignature,
    parse_availability_signatures,
)
from livespec_orchestrator_beads_fabro.commands._acp_schema_fields import (
    non_empty_text,
    string_tuple,
    unknown_keys_refusal,
)

__all__: list[str] = [
    "MODEL_ENTRY_KEYS",
    "AcpModelEntry",
    "parse_model_entry",
    "split_model_catalog_key",
]

# Every key a model-catalog entry may carry. Closed for the same reason the
# agent entry's set is: section "Agent and model catalogs" refuses an unknown
# key before claim, so a misspelled `aliases` cannot silently leave a model
# unreachable by the name an operator actually writes.
MODEL_ENTRY_KEYS: frozenset[str] = frozenset(
    {
        "aliases",
        "availability_signatures",
        "canonical_id",
        "display_name",
        "pricing",
    }
)


@dataclass(frozen=True, kw_only=True)
class AcpModelEntry:
    """One model as a provider serves it, from committed bytes alone.

    `canonical_id` is what the ADAPTER is given, and it is deliberately
    separate from the catalog's own `model` segment: an operator may name a
    model by an alias or by a shortened id, and the value that reaches the
    adapter has to be the one the provider answers to. `aliases` is what the
    operator MAY write; `canonical_id` is what gets rendered.
    """

    provider: str
    model: str
    display_name: str
    canonical_id: str
    aliases: tuple[str, ...] = ()
    pricing: AcpCandidatePricing | None = None
    signatures: tuple[AcpAvailabilitySignature, ...] = ()

    @property
    def key(self) -> str:
        """This entry's own `provider/model` catalog key."""
        return f"{self.provider}/{self.model}"


def split_model_catalog_key(*, catalog_key: str) -> tuple[str, str] | None:
    """The `(provider, model)` halves of a catalog key, or `None` when it is not one.

    EXACTLY ONE separator, and both halves non-blank. A key with two would make
    `provider/model` ambiguous against a model id that itself carries a slash,
    and a key with none carries no provider at all -- which is the half a
    structured candidate's identity derives from, so guessing it would mint an
    entitlement key nobody wrote.
    """
    provider, separator, model = catalog_key.partition("/")
    if separator == "" or provider.strip() == "" or model.strip() == "" or "/" in model:
        return None
    return (provider, model)


def parse_model_entry(
    *, catalog_key: str, entry: Mapping[str, Any], key: str
) -> AcpModelEntry | str:
    """Parse one model entry under its `provider/model` key, or refuse.

    `canonical_id` defaults to the key's own model segment rather than being
    required. Most providers answer to the id they are catalogued under, so
    requiring the field would make every entry restate it -- and a restated
    value is a second copy of one fact, which is the drift this module's `key`
    property already exists to prevent.
    """
    split = split_model_catalog_key(catalog_key=catalog_key)
    if split is None:
        return (
            f"{key} must be keyed by <provider>/<model>; {catalog_key!r} is not one, so the "
            "provider a structured candidate's identity derives from is unknown"
        )
    provider, model = split
    unknown = unknown_keys_refusal(entry=entry, allowed=MODEL_ENTRY_KEYS, key=key)
    if unknown is not None:
        return unknown
    display_name = non_empty_text(value=entry.get("display_name"))
    if display_name is None:
        return f"{key}.display_name must be non-empty text; got {entry.get('display_name')!r}"
    naming = _naming_fields(entry=entry, key=key, model=model)
    if isinstance(naming, str):
        return naming
    metadata = _optional_metadata(entry=entry, key=key)
    if isinstance(metadata, str):
        return metadata
    return AcpModelEntry(
        provider=provider,
        model=model,
        display_name=display_name,
        canonical_id=naming[0],
        aliases=naming[1],
        pricing=metadata[0],
        signatures=metadata[1],
    )


def _naming_fields(
    *, entry: Mapping[str, Any], key: str, model: str
) -> tuple[str, tuple[str, ...]] | str:
    """The canonical id and the aliases, or a refusal naming the bad field.

    `model` is the key's own segment, which is what an absent `canonical_id`
    resolves to. Threading it in rather than re-deriving it keeps the default in
    one place -- the alternative is two readers of the catalog key that could
    disagree about which half is the model.
    """
    canonical = (
        model if entry.get("canonical_id") is None else non_empty_text(value=entry["canonical_id"])
    )
    if canonical is None:
        return f"{key}.canonical_id must be non-empty text; got {entry['canonical_id']!r}"
    aliases = () if entry.get("aliases") is None else string_tuple(value=entry["aliases"])
    if aliases is None:
        return f"{key}.aliases must be an array of strings; got {entry['aliases']!r}"
    return (canonical, aliases)


def _optional_metadata(
    *, entry: Mapping[str, Any], key: str
) -> tuple[AcpCandidatePricing | None, tuple[AcpAvailabilitySignature, ...]] | str:
    """The optional `pricing` and `availability_signatures` objects, or a refusal.

    Both go through the SAME parsers a per-candidate override uses. That is what
    makes "the all-or-none pricing rule applies to catalog entry and override
    alike" true by construction rather than by a rule someone has to remember:
    there is one pricing grammar and one signature grammar, and a catalog entry
    is simply a second place they are written.
    """
    pricing: AcpCandidatePricing | None = None
    if entry.get("pricing") is not None:
        priced = parse_candidate_pricing(value=entry["pricing"], key=f"{key}.pricing")
        if isinstance(priced, str):
            return priced
        pricing = priced
    signatures: tuple[AcpAvailabilitySignature, ...] = ()
    if entry.get("availability_signatures") is not None:
        parsed = parse_availability_signatures(
            value=entry["availability_signatures"], key=f"{key}.availability_signatures"
        )
        if isinstance(parsed, str):
            return parsed
        signatures = parsed
    return (pricing, signatures)
