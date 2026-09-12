"""Pin the public API of the extracted drive action-id grammar module.

The action-id grammar — which prefixes `drive` recognizes as human-valve
actions, and how one action id splits into (verb, item, value) — was carried
inside `_drive_valves` alongside the router and the ledger-only valves. It is
its own concern: a CONSUMER contract (`SPECIFICATION/contracts.md` calls the
action-id grammar "a consumer contract rather than an implementation-private
parser") that the router merely dispatches on. This test pins that the grammar
now lives in `_drive_valve_grammar`, that its cross-module entry points are
PUBLIC, and that the old private parser names are gone from `_drive_valves`.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _drive_valves


def test_action_id_grammar_lives_in_its_own_module() -> None:
    commands_dir = Path(_drive_valves.__file__).parent
    grammar_path = commands_dir / "_drive_valve_grammar.py"
    assert grammar_path.is_file()

    grammar = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._drive_valve_grammar"
    )
    public_names = {
        "APPROVAL_ACTIONS",
        "VALUE_ALLOWLISTS",
        "is_human_valve_action",
        "parse_human_valve_action",
    }
    assert public_names <= set(grammar.__all__)
    for name in public_names:
        assert hasattr(grammar, name)

    old_private_names = {
        "_parse_action_with_item",
        "_parse_action_with_value",
        "_parse_human_valve_action",
    }
    for name in old_private_names:
        assert not hasattr(_drive_valves, name)


def test_grammar_recognizes_and_splits_every_valve_action_shape() -> None:
    grammar = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._drive_valve_grammar"
    )

    assert grammar.is_human_valve_action(action_id="approve:bd-ib-1")
    assert not grammar.is_human_valve_action(action_id="impl:bd-ib-1")
    assert grammar.parse_human_valve_action(action_id="approve:bd-ib-1") == (
        "approve",
        "bd-ib-1",
        None,
    )
    assert grammar.parse_human_valve_action(action_id="reject:bd-ib-1:rework") == (
        "reject",
        "bd-ib-1",
        "rework",
    )
    assert grammar.parse_human_valve_action(action_id="reject:bd-ib-1:nonsense") is None
