"""Every model identity this repository actually renders carries a complete price.

WHAT THIS BINDS. `SPECIFICATION/contracts.md` section "Factory-configurable ACP
fallback priority" -> "Cost follows every attempt in a successful fallback run"
resolves a candidate's price "through the model catalog entry the candidate's
identity names first", and section "Agent and model catalogs" applies "the
all-or-none pricing rule ... to catalog entry and override alike". Scenario 127
is the journey those two clauses serve.

WHY THE IDENTITY SET IS DERIVED FROM THE COMMITTED FILES RATHER THAN LISTED.
An unpriced identity is not a cosmetic gap: `bd-ib-tmgt7v` removed the
default-model price fallback for a fallback-enabled run, so one unpriceable
attempt turns the whole run cost UNOBSERVABLE and the fail-closed cost gate
then refuses to keep picking on an unattended drain. The hazard therefore
arrives the moment somebody edits `workflow.toml` or `dispatcher.acp_nodes` to
name a model nobody priced -- which is exactly the edit a hand-written list of
identities would not notice. So the set is read back out of the two files that
decide it, and the assertion is over whatever they currently say.

THE DERIVATION HAS ITS OWN POSITIVE CONTROL, which is the load-bearing half.
This repository declares NO `fallbacks` today, so a collector that silently
missed every fallback would satisfy the coverage case exactly as a correct one
does -- an instrument that cannot return a hit, reporting no hits. The control
below hands the same collector a synthetic table carrying a structured fallback
AND a manual-form fallback and asserts both identities come back, so the empty
real-world fallback set is an observation rather than a blind spot.

WHY A BROADER MATCH IS ASSERTED HERE AND NOT ONLY IN THE IDENTITY MODULE'S OWN
TEST. The workflow-default identity below is `claude-opus-4-8[1m]`, which starts
with a priced catalog key, so the CHEAPEST way to make the coverage case green is
a prefix or bracket-stripping rule in the normalizer -- the very thing the
contract forbids ("any broader prefix match is not exact identity"). The alias
route is proved by asserting the alias itself, and the forbidden route is closed
by asserting that near-miss spellings of the SAME identity still price nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro.commands._acp_attempt_price import (
    attempt_price,
    catalog_price,
)
from livespec_orchestrator_beads_fabro.commands._acp_catalogs import (
    AcpCatalogs,
    resolve_acp_catalogs,
)
from livespec_orchestrator_beads_fabro.commands._acp_model_catalog import builtin_model_catalog
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import parse_adapter_string
from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_nodes import workflow_layer
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_pricing import ModelPrice

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SHIPPED_WORKFLOW = (
    _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"
)

# The environment variable the Claude ACP adapter takes its model in, and the
# key a structured entry names its model under. Both are read because the two
# layers spell one fact differently: the workflow layer's defaults arrive as
# rendered manual-form adapter strings, while `dispatcher.acp_nodes` entries
# arrive as committed JSONC objects.
_ANTHROPIC_MODEL_ENV = "ANTHROPIC_MODEL"
_MODEL_KEY = "model"
_ENV_KEY = "env"
_FALLBACKS_KEY = "fallbacks"
_ACP_NODES_KEY = "acp_nodes"

# The workflow-default identity the review, dod_gate and proof_verify adapters
# render. Spelled as a LITERAL rather than imported: this module's Red predates
# the alias it binds, so an import of the product constant would make the Red a
# collection error instead of a genuine assertion.
_ONE_MILLION_CONTEXT_IDENTITY = "claude-opus-4-8[1m]"
_OPUS_FOUR_EIGHT_KEY = "anthropic/claude-opus-4-8"

# Opus 4.8's published per-million rates, and the two cache rates derived from
# the input rate by the ratified 1.25x write / 0.10x read multipliers.
_OPUS_FOUR_EIGHT_PRICE = ModelPrice(input=5.00, output=25.00, cache_write=6.25, cache_read=0.50)

# Near-miss spellings of the identity above. Each shares its whole prefix, so a
# prefix matcher returns the Opus 4.8 rate for every one of them; none is the
# `-YYYYMMDD` shape the contract allows to be stripped.
_BROADER_MATCHES = (
    "claude-opus-4-8[1m]-preview",
    "claude-opus-4-8[1m]x",
    "claude-opus-4-8[1m",
    "claude-opus-4-8[1h]",
    "claude-opus-4-8[1m]-2026010",
)


def _catalogs() -> AcpCatalogs:
    """Both catalogs as a dispatch of THIS repository resolves them."""
    resolved = resolve_acp_catalogs(block=dispatcher_block(cwd=_REPO_ROOT))
    assert not isinstance(resolved, str), resolved
    return resolved


def _workflow_identities(*, catalogs: AcpCatalogs) -> frozenset[str]:
    """Every model identity the shipped workflow's adapter defaults render.

    Read through `workflow_layer`, which is the seam a dispatch itself reads, so
    a structured default is rendered into the manual form exactly as the engine
    will receive it. A default that names no model at all -- the un-pinned
    disposition adapter -- contributes nothing rather than an empty identity.
    """
    rendered = workflow_layer(committed=_SHIPPED_WORKFLOW, catalogs=catalogs)
    assert not isinstance(rendered, str), rendered
    declared = (
        parse_adapter_string(text=value).env.get(_ANTHROPIC_MODEL_ENV)
        for value in rendered.values()
    )
    return frozenset(model for model in declared if model is not None)


def _declared_identities(*, node: object) -> list[str]:
    """Every model identity one `acp_nodes` value declares, fallbacks included.

    Recursive over `fallbacks` so an ordered chain contributes every position
    and not just its primary: a chain's fallback is a model this repository has
    configured an attempt to run, so its price is owed on exactly the same
    terms as the primary's.
    """
    if isinstance(node, list):
        return [
            found
            for item in cast("list[object]", node)
            for found in _declared_identities(node=item)
        ]
    if not isinstance(node, dict):
        return []
    entry = cast("dict[str, Any]", node)
    env = entry.get(_ENV_KEY)
    spellings = (
        entry.get(_MODEL_KEY),
        cast("dict[str, Any]", env).get(_ANTHROPIC_MODEL_ENV) if isinstance(env, dict) else None,
    )
    found = [text for text in spellings if isinstance(text, str)]
    return found + _declared_identities(node=entry.get(_FALLBACKS_KEY))


def _table_identities(*, table: object) -> frozenset[str]:
    """Every model identity an `acp_nodes` TABLE declares across all its nodes.

    The table level is separate from the entry level because the two are
    different shapes wearing the same type: a table maps node NAMES onto
    entries, so collecting `model` off the table itself would read a node named
    `model` as a model and would find nothing for every real table.
    """
    assert isinstance(table, dict), table
    return frozenset(
        found
        for entry in cast("dict[str, Any]", table).values()
        for found in _declared_identities(node=entry)
    )


def _repository_identities() -> frozenset[str]:
    """Every model identity this repository's own `dispatcher.acp_nodes` declares."""
    return _table_identities(table=dispatcher_block(cwd=_REPO_ROOT).get(_ACP_NODES_KEY))


@pytest.mark.committed_routing_lint
def test_every_rendered_model_identity_resolves_a_complete_four_component_price() -> None:
    """No identity this repository renders is unpriceable.

    The failure message names every unpriced identity rather than the first,
    because the remedy is one `dispatcher.model_catalog` entry or one base rate
    per identity and a one-at-a-time refusal costs one full suite run each.
    """
    catalogs = _catalogs()
    identities = _workflow_identities(catalogs=catalogs) | _repository_identities()

    assert identities, "the derivation found no identities at all"
    priced = {
        identity: attempt_price(raw_model=identity, catalog=catalogs.models, candidate_pricing=None)
        for identity in sorted(identities)
    }

    assert sorted(name for name, price in priced.items() if price is None) == []


@pytest.mark.committed_routing_lint
def test_every_rendered_identity_prices_all_four_token_categories() -> None:
    """Each resolved price carries four finite, non-negative per-million rates.

    Separate from the case above because "a price resolved" and "a price that
    can charge every token category a run reports" are different claims: a
    three-component table would satisfy the first and go silently useless the
    first time an attempt reported the fourth category.
    """
    catalogs = _catalogs()
    identities = _workflow_identities(catalogs=catalogs) | _repository_identities()

    for identity in sorted(identities):
        price = attempt_price(raw_model=identity, catalog=catalogs.models, candidate_pricing=None)
        assert price is not None, identity
        for rate in (price.input, price.output, price.cache_write, price.cache_read):
            assert rate >= 0.0, identity


def test_the_one_million_context_identity_resolves_through_a_catalog_alias() -> None:
    """`claude-opus-4-8[1m]` is an explicit ALIAS of the Opus 4.8 catalog entry.

    Asserted as an alias on that entry rather than merely as "something that
    prices", because the alias is what makes the resolution exact: the identity
    is a DECORATED spelling of a model the catalog already carries, so a second
    catalog entry for it would be two copies of one published rate and a
    normalizer rule for it would be the forbidden broader match.
    """
    entry = builtin_model_catalog()[_OPUS_FOUR_EIGHT_KEY]

    assert _ONE_MILLION_CONTEXT_IDENTITY in entry.aliases
    assert (
        catalog_price(identity=_ONE_MILLION_CONTEXT_IDENTITY, catalog=dict(builtin_model_catalog()))
        == _OPUS_FOUR_EIGHT_PRICE
    )


def test_the_aliased_identity_still_strips_exactly_one_date_suffix() -> None:
    """A dated emission of the alias prices at the alias's own rate."""
    assert (
        attempt_price(
            raw_model=f"{_ONE_MILLION_CONTEXT_IDENTITY}-20260101",
            catalog=dict(builtin_model_catalog()),
            candidate_pricing=None,
        )
        == _OPUS_FOUR_EIGHT_PRICE
    )


@pytest.mark.parametrize("raw_model", _BROADER_MATCHES)
def test_a_broader_match_on_the_aliased_identity_prices_nothing(*, raw_model: str) -> None:
    """Only the exact alias answers to the alias; no prefix or bracket rule does.

    These are the spellings the cheap fix would have swept in. Each would price
    at the Opus 4.8 rate under a prefix match and under any rule that strips a
    bracketed suffix, and none of them is a model this repository priced.
    """
    assert (
        attempt_price(
            raw_model=raw_model, catalog=dict(builtin_model_catalog()), candidate_pricing=None
        )
        is None
    )


def test_the_identity_collector_does_see_a_fallback_chain() -> None:
    """The positive control for the derivation above.

    This repository declares no `fallbacks`, so the coverage case cannot tell a
    collector that reads them from one that skips them. Both fallback spellings
    are present here -- a structured candidate naming `model`, and a manual-form
    candidate carrying `env.ANTHROPIC_MODEL` -- because the two arrive by
    different keys and a collector blind to either reports a clean empty set.
    """
    table: dict[str, Any] = {
        "review": {
            "agent": "claude-acp",
            _MODEL_KEY: "claude-opus-5",
            _FALLBACKS_KEY: [
                {"agent": "claude-acp", _MODEL_KEY: "claude-sonnet-4-6"},
                {"command": "npx", _ENV_KEY: {_ANTHROPIC_MODEL_ENV: "claude-haiku-4-5"}},
            ],
        }
    }

    assert _table_identities(table=table) == frozenset(
        {"claude-opus-5", "claude-sonnet-4-6", "claude-haiku-4-5"}
    )
