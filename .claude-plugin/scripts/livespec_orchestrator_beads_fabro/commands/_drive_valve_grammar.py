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

from livespec_orchestrator_beads_fabro.commands._drive_policy_valves import CAP_ACTION_VERBS

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
            "set-workflow-scope-override:",
            "set-merge-on-review-cap:",
            "set-review-fix-cap:",
            "set-acceptance-rework-cap:",
            "set-merge-hold:",
            "move:",
        )
    )


def parse_human_valve_action(*, action_id: str) -> tuple[str, str, str | None] | None:
    """Split one action id into (verb, work-item id, value), or `None` if malformed."""
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
    if action in CAP_ACTION_VERBS:
        return (action, item, value)
    if action == "move":
        return ("move", item, value)
    allowed_values = VALUE_ALLOWLISTS.get(action)
    if allowed_values is None or value not in allowed_values:
        return None
    return (action, item, value)
