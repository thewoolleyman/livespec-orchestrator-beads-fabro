"""One attempt's price: the catalog entry its identity names first, its own table second.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Cost follows every attempt in a successful fallback run":
"Pricing resolves through the model catalog entry the candidate's identity names
first (section "Agent and model catalogs") and a per-candidate explicit table
second; for a manual-form candidate with no catalog match only its explicit
table applies."

THE EXACT-IDENTITY RULE RUNS ON BOTH SIDES OF THE COMPARISON, and that is not
symmetry for its own sake. The same section puts the rule on the catalog key --
"the exact-identity rule (one trailing `-YYYYMMDD` suffix stripped, no broader
prefix match) applies to the catalog key" -- so a committed entry written with a
date suffix has to answer to the bare emitted identity and vice versa.
Normalizing only the emitted value would leave a legitimately-dated entry
permanently unreachable, and the symptom would be an unpriceable model rather
than a lookup bug: the run cost would simply go unobservable, pointing at no
particular line.

AN ABSENT PRICE IS A RETURN VALUE, NEVER A DEFAULT. Every arm that cannot price
an identity returns `None`, because the no-default rule above this module is
decided by the caller from exactly that absence. A module that substituted a
neighbouring model's rate to get a number out would make that rule unreachable
while leaving every output well-formed.

WHY "SECOND" MEANS SECOND RATHER THAN NEVER. The ladder continues past a catalog
entry that NAMES the identity but carries no measured price. A catalogued model
with no price and a model no catalog names are the same thing from the cost
path's point of view -- an identity the catalog cannot price -- and stopping at
the match would make the per-candidate table dead for exactly the structured
candidates an operator wrote one for.

A KNOWN TENSION IN THE RATIFIED TEXT, recorded rather than silently resolved.
The cost paragraph quoted above orders the catalog FIRST; section "Agent and
model catalogs" says "a per-candidate `pricing` ... override on a structured
entry wins over the catalog value". This module implements the cost paragraph's
order, because that paragraph is the one that governs the cost path and the one
this item's acceptance contract grades. The other sentence is reachable under a
reading where the override replaces the catalog VALUE at configuration time
rather than at pricing time; nothing here depends on which reading wins, and
the precedence lives in one function so a ratified clarification is a one-line
change.
"""

from __future__ import annotations

from collections.abc import Mapping

from livespec_orchestrator_beads_fabro.commands._acp_candidate_pricing import AcpCandidatePricing
from livespec_orchestrator_beads_fabro.commands._acp_model_entry import AcpModelEntry
from livespec_orchestrator_beads_fabro.commands._acp_model_identity import exact_model_identity
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_pricing import (
    ModelPrice,
    model_price_of,
)

__all__: list[str] = [
    "attempt_price",
    "candidate_table_price",
    "catalog_price",
]


def attempt_price(
    *,
    raw_model: str,
    catalog: Mapping[str, AcpModelEntry],
    candidate_pricing: AcpCandidatePricing | None,
) -> ModelPrice | None:
    """The price for one attempt's emitted identity, or None when unpriceable.

    `raw_model` is the identity as the attempt emitted it, dated or bare.
    `candidate_pricing` is the attempt's own candidate's explicit table, which
    is None for every candidate that declared none -- including every
    structured candidate that takes the catalog price as-is.
    """
    identity = exact_model_identity(raw_model=raw_model)
    if identity is None:
        return None
    from_catalog = catalog_price(identity=identity, catalog=catalog)
    if from_catalog is not None:
        return from_catalog
    return candidate_table_price(identity=identity, pricing=candidate_pricing)


def catalog_price(*, identity: str, catalog: Mapping[str, AcpModelEntry]) -> ModelPrice | None:
    """The price of the catalog entry `identity` names, or None.

    Entries are visited in sorted key order so a catalog in which two entries
    answer to one identity -- two providers serving the same model id, say --
    prices an attempt the same way on every dispatch. A nondeterministic choice
    there would make one run's cost differ from the next with identical
    committed bytes.
    """
    for key in sorted(catalog):
        entry = catalog[key]
        if entry.pricing is not None and identity in _entry_identities(entry=entry):
            return model_price_of(pricing=entry.pricing)
    return None


def candidate_table_price(
    *, identity: str, pricing: AcpCandidatePricing | None
) -> ModelPrice | None:
    """The candidate's own table, if it names this exact identity, else None.

    The contract's "applies only when emitted identity matches" clause: a
    complete table for some OTHER model is not a price for this attempt, and
    applying it would silently charge one model's usage at another's rate.
    """
    if pricing is None:
        return None
    named = exact_model_identity(raw_model=pricing.model)
    return model_price_of(pricing=pricing) if named == identity else None


def _entry_identities(*, entry: AcpModelEntry) -> frozenset[str | None]:
    """Every normalized identity one catalog entry answers to.

    The entry's own `model` segment, the `canonical_id` the adapter is given,
    and each declared alias -- the three spellings section "Agent and model
    catalogs" makes operator-writable. Each goes through the same
    exact-identity rule the emitted value does.

    A spelling that normalizes to NOTHING -- an operator-written alias that is
    blank, or is nothing but a date suffix -- is kept as the `None` member
    rather than filtered out. The lookup key is itself never absent (its caller
    returned early on that), so a `None` member cannot match anything, and
    filtering it would add a branch to this helper that no lookup can ever
    take a decision on.
    """
    spellings = (entry.model, entry.canonical_id, *entry.aliases)
    return frozenset(exact_model_identity(raw_model=spelling) for spelling in spellings)
