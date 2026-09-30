"""ONE AGENT CATALOG ENTRY: its launch distribution, its identity, its limits.

`SPECIFICATION/contracts.md` section "Agent and model catalogs" fixes what
every entry carries: "the launch distribution rendered from the registry's
`npx`, `uvx` or per-platform `binary` distribution at a pinned agent version,
in the manual-form shape (`command`, `args`, `env`); the agent's display name;
its account domain, an opaque `availability_key` naming the allowance the agent
draws on; the mechanism by which the agent takes `model` and `effort` ...;
whether the agent is multi-provider ...; and the effort levels it declares."

THE LAUNCH DISTRIBUTION IS THE MANUAL FORM, DELIBERATELY. An entry renders into
`(command, env, args)` -- the same triple an operator writes by hand -- so the
structured form is a SPELLING over the manual one rather than a second
resolution path. Section "ACP node adapter configuration" requires exactly
that: "The Dispatcher MUST render a structured entry into the manual form below
before any layer merge, journal, digest or run input, so every downstream rule
... applies to the rendered candidate unchanged."

WHY `account_domain` AND NOT `provider`. They answer different questions and
conflating them is how a hold strands the wrong candidates. `provider` is who
serves the MODEL; `account_domain` is whose ALLOWANCE the agent draws on, and
it becomes the candidate's `availability_key`. One account can reach several
providers (a multi-provider agent) and one provider can be reached through
several accounts (a router), so neither determines the other.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_agent_mechanism import (
    AcpModelMechanism,
    parse_model_mechanism,
)
from livespec_orchestrator_beads_fabro.commands._acp_schema_fields import (
    missing_keys_refusal,
    non_empty_text,
    string_map,
    string_tuple,
    unknown_keys_refusal,
)

__all__: list[str] = [
    "AGENT_ENTRY_KEYS",
    "AcpAgentEntry",
    "parse_agent_entry",
]

# Every key an agent-catalog entry may carry, in the repository-supplied
# `dispatcher.agent_catalog` table as much as in the shipped snapshot. The set
# is CLOSED: section "Agent and model catalogs" says "an unknown key refuses
# before claim", because a misspelled `account_domain` would otherwise leave
# the agent silently drawing on an allowance nobody named.
AGENT_ENTRY_KEYS: frozenset[str] = frozenset(
    {
        "account_domain",
        "args",
        "command",
        "display_name",
        "effort_levels",
        "env",
        "mechanism",
        "multi_provider",
        "provider",
        "read_only_env",
        "version",
    }
)

# Every key an entry MUST declare. `provider` is absent on purpose: it is
# required exactly when `multi_provider` is false, which is a rule about the
# pair rather than about either key, and `_provider_refusal` owns it.
_REQUIRED_AGENT_KEYS: frozenset[str] = frozenset(
    {"account_domain", "command", "display_name", "mechanism", "version"}
)

# The three non-empty text fields beside `command`, which carries its own
# message because it is the launch distribution rather than a label.
_TEXT_FIELDS: tuple[str, ...] = ("display_name", "account_domain", "version")


@dataclass(frozen=True, kw_only=True)
class AcpAgentEntry:
    """One registry agent as this build knows it, from committed bytes alone.

    `read_only_env` is the environment a node that performs NO WRITES takes
    instead of the entry's own. `SPECIFICATION/scenarios.md` Scenario 90
    requires a review node routed to Codex to render
    `INITIAL_AGENT_MODE=read-only` while a write-capable node renders
    `agent-full-access`, and the posture is a property of the NODE rather than
    of the agent -- so the entry declares both and the renderer picks. An agent
    with no write/read-only distinction declares an empty table and renders
    the same environment for every node.

    `provider` is empty exactly when `multi_provider` is true: a
    multi-provider agent takes a `provider/model` reference, so there is no
    single provider to record, and recording one would make a bare model id
    resolve against a provider the operator never named.
    """

    agent_id: str
    display_name: str
    account_domain: str
    version: str
    command: str
    mechanism: AcpModelMechanism
    args: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    read_only_env: Mapping[str, str] = field(default_factory=dict)
    effort_levels: tuple[str, ...] = ()
    provider: str = ""
    multi_provider: bool = False


def parse_agent_entry(*, agent_id: str, entry: Mapping[str, Any], key: str) -> AcpAgentEntry | str:
    """Parse one COMPLETE agent entry, or refuse naming the key at fault.

    An entry is complete rather than a patch over the shipped snapshot. A
    partial override would make the effective entry half committed
    configuration and half a snapshot that moves under it at the next re-seed,
    so the operator could not predict the rendered bytes from what they wrote --
    which is the one property the structured form exists to give them.
    """
    keys = _key_set_refusal(entry=entry, key=key)
    if keys is not None:
        return keys
    labels = _label_fields(entry=entry, key=key)
    if isinstance(labels, str):
        return labels
    mechanism = parse_model_mechanism(value=entry["mechanism"], key=f"{key}.mechanism")
    if isinstance(mechanism, str):
        return mechanism
    launch = _launch_fields(entry=entry, key=key)
    if isinstance(launch, str):
        return launch
    provider = _provider(entry=entry, key=key)
    if isinstance(provider, str):
        return provider
    return AcpAgentEntry(
        agent_id=agent_id,
        display_name=labels[0],
        account_domain=labels[1],
        version=labels[2],
        command=labels[3],
        mechanism=mechanism,
        args=launch[0],
        env=launch[1],
        read_only_env=launch[2],
        effort_levels=launch[3],
        provider=provider[0],
        multi_provider=provider[1],
    )


def _key_set_refusal(*, entry: Mapping[str, Any], key: str) -> str | None:
    """Refuse an unknown key or an incomplete entry, in that order.

    Unknown comes first because a misspelling presents as BOTH faults at once --
    the wrong key is unknown and the right one is missing -- and naming the
    misspelling is the one message that tells the operator what to edit.
    """
    unknown = unknown_keys_refusal(entry=entry, allowed=AGENT_ENTRY_KEYS, key=key)
    if unknown is not None:
        return unknown
    return missing_keys_refusal(entry=entry, required=_REQUIRED_AGENT_KEYS, key=key)


def _label_fields(*, entry: Mapping[str, Any], key: str) -> tuple[str, str, str, str] | str:
    """The three required label fields and the launch command, or a refusal.

    `command` rides along because it answers the same question -- is this a
    non-empty string -- while carrying its own message: it is the launch
    distribution rather than a label, so a refusal that called it one would send
    the operator looking for a display-name problem.
    """
    resolved: list[str] = []
    for name in _TEXT_FIELDS:
        text = non_empty_text(value=entry[name])
        if text is None:
            return f"{key}.{name} must be non-empty text; got {entry[name]!r}"
        resolved.append(text)
    command = non_empty_text(value=entry["command"])
    if command is None:
        return f"{key}.command must be a non-empty launch command; got {entry['command']!r}"
    return (resolved[0], resolved[1], resolved[2], command)


def _launch_fields(
    *, entry: Mapping[str, Any], key: str
) -> tuple[tuple[str, ...], Mapping[str, str], Mapping[str, str], tuple[str, ...]] | str:
    """The optional launch-distribution fields, each empty when absent.

    An omitted `args` resolves to the empty tuple and an omitted `env` to the
    empty table, matching the manual form's own wording in
    `_acp_candidate_schema` -- the structured form is a spelling over that form,
    so the two must agree about what an omission means.
    """
    tuples: list[tuple[str, ...]] = []
    for name in ("args", "effort_levels"):
        value = () if entry.get(name) is None else string_tuple(value=entry[name])
        if value is None:
            return f"{key}.{name} must be an array of strings; got {entry[name]!r}"
        tuples.append(value)
    maps: list[Mapping[str, str]] = []
    empty: Mapping[str, str] = {}
    for name in ("env", "read_only_env"):
        table = empty if entry.get(name) is None else string_map(value=entry[name])
        if table is None:
            return f"{key}.{name} must be a table of string to string; got {entry[name]!r}"
        maps.append(table)
    return (tuples[0], maps[0], maps[1], tuples[1])


def _provider(*, entry: Mapping[str, Any], key: str) -> tuple[str, bool] | str:
    """The provider and multi-provider flag, refusing any combination of them
    that leaves a bare model id unresolvable.

    Both directions refuse, and each catches a different silent failure. A
    multi-provider agent ALSO naming a provider would let a bare model id
    resolve against that provider while the operator believes every reference
    is qualified. A single-provider agent naming NONE would leave every model
    lookup for it without a provider to search, which surfaces later as "the
    catalog does not declare this model" -- a refusal that names the wrong
    thing.
    """
    flag = entry.get("multi_provider", False)
    if not isinstance(flag, bool):
        return f"{key}.multi_provider must be true or false; got {flag!r}"
    declared = entry.get("provider")
    if flag and declared is not None:
        return (
            f"{key}.multi_provider is true, so {key}.provider must be absent; a "
            "multi-provider agent takes a provider/model reference per candidate"
        )
    if flag:
        return ("", True)
    provider = non_empty_text(value=declared)
    if provider is None:
        return (
            f"{key}.provider must name the provider this agent serves, or "
            f"{key}.multi_provider must be true; got {declared!r}"
        )
    return (provider, False)
