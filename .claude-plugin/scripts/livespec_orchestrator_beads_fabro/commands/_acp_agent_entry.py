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

from livespec_orchestrator_beads_fabro.commands._acp_agent_mechanism import AcpModelMechanism

__all__: list[str] = [
    "AGENT_ENTRY_KEYS",
    "AcpAgentEntry",
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
