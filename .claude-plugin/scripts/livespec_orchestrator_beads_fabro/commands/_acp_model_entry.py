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

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_candidate_pricing import AcpCandidatePricing
from livespec_orchestrator_beads_fabro.commands._acp_candidate_signatures import (
    AcpAvailabilitySignature,
)

__all__: list[str] = [
    "MODEL_ENTRY_KEYS",
    "AcpModelEntry",
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
