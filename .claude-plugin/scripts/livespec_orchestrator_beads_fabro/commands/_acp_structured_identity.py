"""The identity, pricing and signatures a structured candidate DERIVES.

`SPECIFICATION/contracts.md` section "Agent and model catalogs": "Derived
identity, when not overridden, is: `display_name` = the agent's display name
followed by the model's display name; `candidate_key` = the canonical
`<agent>/<provider>/<model>` triple; `availability_key` = the agent entry's
account domain."

WHY THE TRIPLE IS DERIVED RATHER THAN WRITTEN. The same section states the
property it buys: "Two structured entries naming the same agent and model
therefore share identity across nodes by construction, which is the cross-node
reuse ... already permits." A hand-written identity can only achieve that by two
operators spelling the same string twice, and a typo in either half silently
splits one entitlement into two -- after which a hold minted by one node's
failure skips nothing on the other.

WHY `candidate_key` CARRIES THE PROVIDER AND `availability_key` DOES NOT. They
key different things. The candidate key names WHAT RAN, so it needs all three
parts: two agents reaching the same model through different providers are
different candidates. The availability key names WHOSE ALLOWANCE was spent, which
is the account, so a domain hold correctly strands every model that account
reaches.

OVERRIDES ARE PER FIELD, and that is not a convenience. The example the contract
gives -- `availability_key: "chatgpt-team-account"` beside a derived
`candidate_key` -- is exactly the case where one account's entitlement is shared
across a team while the candidate identity stays the canonical triple. Replacing
the whole triple when any one field is overridden would make that unexpressible.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidateIdentity
from livespec_orchestrator_beads_fabro.commands._acp_structured_render import AcpResolvedStructured

__all__: list[str] = [
    "derived_identity",
]


def derived_identity(
    *, resolved: AcpResolvedStructured, override: AcpCandidateIdentity | None
) -> AcpCandidateIdentity:
    """The candidate's identity: each field overridden or derived, field by field.

    `override` is the PARTIAL identity a structured entry may declare. It is
    already validated by the time it arrives -- `parse_partial_identity` refuses a
    blank or secret-looking value -- so an empty field here means "not
    overridden" rather than "overridden with nothing".
    """
    agent = resolved.agent
    model = resolved.model
    return AcpCandidateIdentity(
        display_name=_chosen(
            override=None if override is None else override.display_name,
            derived=f"{agent.display_name} {model.display_name}",
        ),
        candidate_key=_chosen(
            override=None if override is None else override.candidate_key,
            derived=f"{agent.agent_id}/{model.provider}/{model.model}",
        ),
        availability_key=_chosen(
            override=None if override is None else override.availability_key,
            derived=agent.account_domain,
        ),
    )


def _chosen(*, override: str | None, derived: str) -> str:
    """The override when one was declared, else the derived value."""
    if override is None or override == "":
        return derived
    return override
