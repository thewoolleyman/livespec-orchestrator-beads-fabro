"""Turning a STRUCTURED entry into the manual form, through the catalogs alone.

`SPECIFICATION/contracts.md` section "ACP node adapter configuration": "The
Dispatcher MUST render a structured entry into the manual form below before any
layer merge, journal, digest or run input, so every downstream rule of this
section and of the factory-configurable-ACP-fallback-priority section applies to
the rendered candidate unchanged. Rendering MUST be deterministic: the same
catalog snapshot and the same entry MUST render byte-identical adapter bytes."

THE RENDER IS A PURE FUNCTION OF (ENTRY, CATALOGS, POSTURE), which is what makes
determinism structural rather than a property to be tested for. Nothing here
reads a clock, an environment variable, a filesystem or a network; nothing is
memoized, so there is no cache whose contents could differ between two
dispatches. Two calls with equal arguments cannot disagree because there is
nothing for them to disagree about.

WHY THE POSTURE IS AN ARGUMENT AND NOT A CATALOG FIELD. Whether a node WRITES is
a property of the node, not of the agent: `SPECIFICATION/scenarios.md` Scenario
90 requires the same `codex-acp` entry to render `agent-full-access` for the
implementer and `read-only` for the reviewer. So the agent entry declares BOTH
environments and the caller, which knows which node it is resolving, picks.

WHAT A REFUSAL COSTS, AND WHY EVERY ONE NAMES A CONFIGURATION PATH. Section
"Agent and model catalogs" requires a refusal before claim "when either lookup
fails or when `effort` is not one of the agent's declared levels". Before claim
is strictly earlier than before run: a claim taken on an entry that cannot
resolve has to be released again, so the honest place to discover an
unresolvable model is the dispatch that would otherwise have launched the
workflow default it meant to replace.
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Mapping
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_agent_entry import AcpAgentEntry
from livespec_orchestrator_beads_fabro.commands._acp_agent_mechanism import (
    ARG_MECHANISM,
    ENV_MECHANISM,
    JSON_ENV_MECHANISM,
    VALUE_PLACEHOLDER,
    AcpModelMechanism,
)
from livespec_orchestrator_beads_fabro.commands._acp_catalogs import AcpCatalogs
from livespec_orchestrator_beads_fabro.commands._acp_model_entry import (
    AcpModelEntry,
    split_model_catalog_key,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter

__all__: list[str] = [
    "READ_ONLY_NODES",
    "AcpResolvedStructured",
    "AcpStructuredEntry",
    "render_structured_entry",
]

# The ACP nodes of the reserved workflow that perform NO WRITES. The implementer
# nodes edit the workspace and `pr` commits and pushes, so they are write-capable
# and absent from this set; a reviewer and the disposition adjudicator only read.
READ_ONLY_NODES: frozenset[str] = frozenset({"disposition", "review"})


@dataclass(frozen=True, kw_only=True)
class AcpStructuredEntry:
    """The three structured fields, before any catalog has been consulted.

    `effort` is empty when the entry declares none, which is NOT the same as an
    agent that exposes no effort route: the first is a candidate choosing the
    adapter's own default, the second is a mechanism with nowhere to put a
    value.
    """

    agent: str
    model: str
    effort: str = ""


@dataclass(frozen=True, kw_only=True)
class AcpResolvedStructured:
    """One structured entry resolved through the catalogs.

    `config_options` is non-empty ONLY for an agent declaring the `protocol`
    mechanism, where the requested values ride the rendered CHAIN rather than
    the adapter. The two are mutually exclusive by construction here -- each
    mechanism writes one of them and never both -- which is the
    "MUST NOT be combined for one candidate" rule made structural.
    """

    adapter: AcpAdapter
    agent: AcpAgentEntry
    model: AcpModelEntry
    effort: str
    config_options: Mapping[str, str]


def render_structured_entry(
    *,
    entry: AcpStructuredEntry,
    catalogs: AcpCatalogs,
    key: str,
    read_only: bool = False,
) -> AcpResolvedStructured | str:
    """Resolve and render one structured entry, or refuse naming the key at fault."""
    agent = catalogs.agents.get(entry.agent)
    if agent is None:
        return (
            f"{key}.agent names {entry.agent!r}, which the agent catalog does not declare; "
            f"known agents are {', '.join(sorted(catalogs.agents))}"
        )
    model = _resolve_model(entry=entry, agent=agent, catalogs=catalogs, key=key)
    if isinstance(model, str):
        return model
    effort = _resolve_effort(entry=entry, agent=agent, key=key)
    if effort is not None:
        return effort
    return _rendered(entry=entry, agent=agent, model=model, read_only=read_only)


def _resolve_model(
    *, entry: AcpStructuredEntry, agent: AcpAgentEntry, catalogs: AcpCatalogs, key: str
) -> AcpModelEntry | str:
    """The model entry this reference names, or a refusal naming the reference.

    A MULTI-PROVIDER agent requires the qualified form, because it has no single
    provider for a bare id to resolve against and guessing one would silently
    price and identify the candidate under a provider nobody named. A
    single-provider agent accepts either spelling, and refuses a qualified
    reference naming a DIFFERENT provider: that is an operator pointing an agent
    at a provider it does not serve, which fails at the adapter rather than here
    if it is let through.
    """
    provider, refusal = _reference_provider(entry=entry, agent=agent, key=key)
    if refusal is not None:
        return refusal
    _, _, bare = entry.model.rpartition("/")
    found = _lookup_model(catalogs=catalogs, provider=provider, reference=bare)
    if found is None:
        return (
            f"{key}.model names {entry.model!r}, which the model catalog does not declare for "
            f"provider {provider!r}; add it under dispatcher.model_catalog.{provider}/<model>"
        )
    return found


def _reference_provider(
    *, entry: AcpStructuredEntry, agent: AcpAgentEntry, key: str
) -> tuple[str, str | None]:
    """The provider this model reference resolves against, and any refusal.

    The pair is returned rather than a union because a provider name and a
    refusal message are both strings, and a caller that had to tell them apart
    by inspecting the text is one typo away from rendering a candidate against a
    provider called "dispatcher.acp_nodes.implement.model must be ...".
    """
    qualified = split_model_catalog_key(catalog_key=entry.model)
    if qualified is None:
        if agent.multi_provider:
            unqualified = (
                f"{key}.model must be a <provider>/<model> reference because agent "
                f"{agent.agent_id!r} is multi-provider and has no single provider to resolve "
                f"a bare model id against; got {entry.model!r}"
            )
            return ("", unqualified)
        return (agent.provider, None)
    named = qualified[0]
    if not agent.multi_provider and named != agent.provider:
        mismatched = (
            f"{key}.model names provider {named!r}, but agent {agent.agent_id!r} serves "
            f"{agent.provider!r}; use the manual form for an agent the catalogs do not cover"
        )
        return ("", mismatched)
    return (named, None)


def _lookup_model(*, catalogs: AcpCatalogs, provider: str, reference: str) -> AcpModelEntry | None:
    """The catalog entry for one provider's model id or one of its aliases.

    The exact key is tried first so an alias can never shadow a real model of
    the same name, and the alias scan is confined to the named provider for the
    same reason the lookup is keyed by provider at all: an alias is a name
    inside one provider's namespace.
    """
    exact = catalogs.models.get(f"{provider}/{reference}")
    if exact is not None:
        return exact
    aliased = [
        entry
        for entry in catalogs.models.values()
        if entry.provider == provider and reference in entry.aliases
    ]
    if not aliased:
        return None
    return aliased[0]


def _resolve_effort(*, entry: AcpStructuredEntry, agent: AcpAgentEntry, key: str) -> str | None:
    """`None` when the declared effort is admissible, else the refusal.

    An entry declaring NO effort is always admissible: it is the candidate
    taking the adapter's own default, which every agent has whether or not it
    exposes a route for changing it.
    """
    if entry.effort == "":
        return None
    if entry.effort not in agent.effort_levels:
        return (
            f"{key}.effort names {entry.effort!r}, which agent {agent.agent_id!r} does not "
            f"declare; declared levels are {', '.join(agent.effort_levels) or '(none)'}"
        )
    return None


def _rendered(
    *,
    entry: AcpStructuredEntry,
    agent: AcpAgentEntry,
    model: AcpModelEntry,
    read_only: bool,
) -> AcpResolvedStructured:
    """The launch distribution with the model and effort applied by its mechanism."""
    base = dict(agent.read_only_env if read_only and agent.read_only_env else agent.env)
    settings = _settings(mechanism=agent.mechanism, model=model.canonical_id, effort=entry.effort)
    env, args, options = _applied(
        mechanism=agent.mechanism, base=base, args=agent.args, settings=settings
    )
    return AcpResolvedStructured(
        adapter=AcpAdapter(command=agent.command, env=env, args=args),
        agent=agent,
        model=model,
        effort=entry.effort,
        config_options=options,
    )


def _settings(
    *, mechanism: AcpModelMechanism, model: str, effort: str
) -> tuple[tuple[str, str], ...]:
    """The `(target, value)` pairs this candidate actually sets.

    An empty `effort` contributes NOTHING rather than an empty value, and an
    agent exposing no effort route contributes nothing either. Both omissions
    matter for the same reason the Codex opt-out does: a present-but-empty key
    is a differently-spelled pin, not the absence of one.
    """
    pairs = [(mechanism.model, model)]
    if effort != "" and mechanism.effort != "":
        pairs.append((mechanism.effort, effort))
    return tuple(pairs)


def _applied(
    *,
    mechanism: AcpModelMechanism,
    base: dict[str, str],
    args: tuple[str, ...],
    settings: tuple[tuple[str, str], ...],
) -> tuple[Mapping[str, str], tuple[str, ...], Mapping[str, str]]:
    """The env, args and chain config options one mechanism produces."""
    if mechanism.kind == ENV_MECHANISM:
        return ({**base, **dict(settings)}, args, {})
    if mechanism.kind == JSON_ENV_MECHANISM:
        return (_json_applied(mechanism=mechanism, base=base, settings=settings), args, {})
    if mechanism.kind == ARG_MECHANISM:
        rendered = [
            token
            for target, value in settings
            for token in shlex.split(target.replace(VALUE_PLACEHOLDER, value))
        ]
        return (base, (*args, *rendered), {})
    return (base, args, dict(settings))


def _json_applied(
    *,
    mechanism: AcpModelMechanism,
    base: dict[str, str],
    settings: tuple[tuple[str, str], ...],
) -> Mapping[str, str]:
    """The carrier variable's JSON object with the settings MERGED into it.

    The object's other keys survive and the key order stays sorted, which is
    what section "Built-in ACP node defaults" requires of a pinned Codex
    adapter: "the un-pinned base string with `model` and
    `model_reasoning_effort` ADDED inside `CODEX_CONFIG`, the object's keys
    remaining in sorted order". A carrier the entry declares no object for
    starts from the empty object rather than refusing: an agent may take its
    whole session configuration from the pin alone.
    """
    carried = base.get(mechanism.env, "{}")
    decoded = json.loads(carried)
    merged = {**decoded, **dict(settings)}
    return {
        **base,
        mechanism.env: json.dumps(merged, sort_keys=True, separators=(",", ":")),
    }
