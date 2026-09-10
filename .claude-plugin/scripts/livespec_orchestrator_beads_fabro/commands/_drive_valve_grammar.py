"""The `drive` human-valve ACTION-ID GRAMMAR: which verbs exist, and how one parses.

Split out of `_drive_valves` along the seam that module's own docstring already
named — it held "the action-id grammar, the router that dispatches on it, and
the two valves that do nothing but write the ledger". The grammar is the one of
those three that reads no store, no configuration and no forge: it is a pure
function from the operator's string to a parsed `(action, item-id, value)`
triple, so cutting here leaves the router holding only routing.

Keeping every registered verb in ONE module is what makes contracts.md's claim
that the action-id grammar is a consumer contract rather than an
implementation-private parser checkable in one place: a reader asking which
verbs exist, and which values each admits, reads this file.

A verb whose value space is a CLOSED ENUM is refused HERE, before the store is
ever read, by listing that enum in `VALUE_ALLOWLISTS`. The cap verbs are the
deliberate exception — their domain is a TYPE rather than a set, so
`_drive_policy_valves.set_cap` grades those values beside the schema that
defines them.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._drive_policy_valves import CAP_ACTION_VERBS

__all__: list[str] = ["is_human_valve_action", "parse_human_valve_action"]

ACTION_WITH_ITEM_PARTS = 2
ACTION_WITH_VALUE_PARTS = 3
APPROVAL_ACTIONS = frozenset({"approve", "accept"})
VALUE_ALLOWLISTS = {
    "reject": frozenset({"rework", "regroom"}),
    "resolve-blocked": frozenset({"ready", "backlog"}),
    "set-admission": frozenset({"auto", "manual"}),
    "set-acceptance": frozenset({"ai-only", "human-only", "ai-then-human"}),
    # The three canonical `factory_safety` reasons, exactly as the field's own
    # closed enum defines them. The verb exists to retire an unattributable raw
    # `bd label add`, so admitting free text here would reintroduce the very
    # thing it replaces: a recorded reason nobody can act on. The mandatory
    # rationale is enforced by the same line, because the empty trailing field
    # is not a member of the enum either.
    "set-factory-safety": frozenset(
        {"needs-host-secrets", "mutates-host-machinery", "needs-privileged-host"}
    ),
    "set-workflow-scope-override": frozenset({"citation-only"}),
    # The hold's value space is exactly the switch it is: `on` writes the label,
    # `off` removes it. Anything else in that position is not a weaker hold, it
    # is a typo, and the grammar refuses it before the store is ever read.
    "set-merge-hold": frozenset({"on", "off"}),
}


def is_human_valve_action(*, action_id: str) -> bool:
    return action_id.startswith(
        (
            "approve:",
            "accept:",
            "reject:",
            "resolve-blocked:",
            "set-admission:",
            "set-acceptance:",
            "set-factory-safety:",
            "set-workflow-scope-override:",
            "set-merge-on-review-cap:",
            "set-review-fix-cap:",
            "set-acceptance-rework-cap:",
            "set-merge-hold:",
            "move:",
        )
    )


def parse_human_valve_action(*, action_id: str) -> tuple[str, str, str | None] | None:
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
