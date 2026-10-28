"""The `drive` human-valve ACTION-ID GRAMMAR: which ids are recognized, and how.

Split out of `_drive_valves`, which holds the router and the ledger-only valves.
The grammar is its own concern and a different KIND of thing from either:
`SPECIFICATION/contracts.md` binds the action-id grammar as "a consumer contract
rather than an implementation-private parser", so the shapes below are what a
console or an operator may type, while the router is free to change how it
dispatches on them.

Only `parse_human_valve_action` and `is_human_valve_action` cross a module
boundary, so only those two are public; the two per-shape parsers stay private
here, beside the constants they read.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._drive_factory_safety_valve import (
    FACTORY_SAFETY_ACTION,
)
from livespec_orchestrator_beads_fabro.commands._drive_policy_valves import CAP_ACTION_VERBS
from livespec_orchestrator_beads_fabro.commands._drive_release_spec_tier_valve import (
    RELEASE_SPEC_TIER_ACTION,
)

__all__: list[str] = [
    "ACTION_WITH_ITEM_PARTS",
    "ACTION_WITH_VALUE_PARTS",
    "APPROVAL_ACTIONS",
    "VALUE_ALLOWLISTS",
    "is_human_valve_action",
    "parse_human_valve_action",
]

ACTION_WITH_ITEM_PARTS = 2
ACTION_WITH_VALUE_PARTS = 3
APPROVAL_ACTIONS = frozenset({"approve", "accept"})
VALUE_ALLOWLISTS = {
    "reject": frozenset({"rework", "regroom"}),
    "resolve-blocked": frozenset({"ready", "backlog"}),
    "set-admission": frozenset({"auto", "manual"}),
    "set-acceptance": frozenset({"ai-only", "human-only", "ai-then-human"}),
    "set-workflow-scope-override": frozenset({"citation-only"}),
    # The hold's value space is exactly the switch it is: `on` writes the label,
    # `off` removes it. Anything else in that position is not a weaker hold, it
    # is a typo, and the grammar refuses it before the store is ever read.
    "set-merge-hold": frozenset({"on", "off"}),
}

# The verbs whose third field this grammar passes through UNGRADED, because the
# valve behind each owns that value domain and can say something useful about a
# bad value. The caps and `move` join because their spaces are unbounded or
# stated by the valve's own refusal; `set-factory-safety` joins even though its
# enum IS closed, because contracts.md requires a refusal NAMING the three
# canonical reasons, and an id rejected here reaches the operator as the generic
# "Unsupported human valve action id." — the one message that cannot tell a
# typo'd reason from a typo'd verb.
_UNGRADED_VALUE_ACTIONS: frozenset[str] = CAP_ACTION_VERBS | {"move", FACTORY_SAFETY_ACTION}


def is_human_valve_action(*, action_id: str) -> bool:
    """Does `action_id` select one of the human valves?"""
    return action_id.startswith(
        (
            "approve:",
            "accept:",
            "reject:",
            "resolve-blocked:",
            "set-admission:",
            "set-acceptance:",
            f"{FACTORY_SAFETY_ACTION}:",
            "set-workflow-scope-override:",
            "set-merge-on-review-cap:",
            "set-review-fix-cap:",
            "set-acceptance-rework-cap:",
            "set-merge-hold:",
            "move:",
            f"{RELEASE_SPEC_TIER_ACTION}:",
        )
    )


def parse_human_valve_action(*, action_id: str) -> tuple[str, str, str | None] | None:
    """Split one action id into (verb, work-item id, value), or `None` if malformed."""
    if action_id.startswith(f"{RELEASE_SPEC_TIER_ACTION}:"):
        return _parse_release_spec_tier(action_id=action_id)
    parts = action_id.split(":")
    parsed = _parse_action_with_item(parts=parts)
    if parsed is not None:
        return parsed
    return _parse_action_with_value(parts=parts)


def _parse_action_with_item(*, parts: list[str]) -> tuple[str, str, str | None] | None:
    if len(parts) != ACTION_WITH_ITEM_PARTS:
        return None
    action, item = parts
    if item == "" or action not in APPROVAL_ACTIONS:
        return None
    return (action, item, None)


def _parse_action_with_value(*, parts: list[str]) -> tuple[str, str, str | None] | None:
    if len(parts) != ACTION_WITH_VALUE_PARTS:
        return None
    action, item, value = parts
    if item == "":
        return None
    if action in _UNGRADED_VALUE_ACTIONS:
        return (action, item, value)
    allowed_values = VALUE_ALLOWLISTS.get(action)
    if allowed_values is None or value not in allowed_values:
        return None
    return (action, item, value)


def _parse_release_spec_tier(*, action_id: str) -> tuple[str, str, str | None] | None:
    """Split `release-spec-tier:<id>:<heading>`, the heading being the REST of the id.

    A heading is arbitrary specification text and may itself carry a colon, so
    the generic three-field split would refuse every such title as malformed.
    """
    _, _, rest = action_id.partition(":")
    item, separator, heading = rest.partition(":")
    if not separator or item == "" or heading.strip() == "":
        return None
    return (RELEASE_SPEC_TIER_ACTION, item, heading)
