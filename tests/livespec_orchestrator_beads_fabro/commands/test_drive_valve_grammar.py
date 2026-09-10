"""Tests for the `drive` human-valve action-id grammar, in its own module.

The grammar is a CONSUMER contract, so the assertions here are deliberately
about the whole registered verb set rather than about one verb at a time: a
verb that `is_human_valve_action` admits but no parse accepts is refused with
`invalid-action-id` at the router, which reads to an operator exactly like a
typo in their own command.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _drive_valve_grammar as grammar

_COMMANDS_DIR = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_REGISTERED_VERBS = (
    "approve",
    "accept",
    "reject",
    "resolve-blocked",
    "set-admission",
    "set-acceptance",
    "set-factory-safety",
    "set-workflow-scope-override",
    "set-merge-on-review-cap",
    "set-review-fix-cap",
    "set-acceptance-rework-cap",
    "set-merge-hold",
    "move",
)


def test_the_grammar_lives_in_its_own_module() -> None:
    """The router imports the grammar; it no longer carries a second copy of it."""
    module_path = _COMMANDS_DIR / "_drive_valve_grammar.py"
    assert module_path.is_file()

    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._drive_valve_grammar"
    )
    assert callable(module.is_human_valve_action)
    assert callable(module.parse_human_valve_action)

    router_source = (_COMMANDS_DIR / "_drive_valves.py").read_text(encoding="utf-8")
    assert "_parse_action_with_value" not in router_source
    assert "VALUE_ALLOWLISTS" not in router_source


@pytest.mark.parametrize("verb", _REGISTERED_VERBS)
def test_every_registered_verb_is_recognized_by_the_prefix_gate(verb: str) -> None:
    assert grammar.is_human_valve_action(action_id=f"{verb}:bd-ib-1:whatever")


@pytest.mark.parametrize("verb", _REGISTERED_VERBS)
def test_every_registered_verb_has_a_parse_that_accepts_something(verb: str) -> None:
    """A prefix the gate admits but no parse accepts refuses like an operator typo."""
    approval = grammar.parse_human_valve_action(action_id=f"{verb}:bd-ib-1")
    allowlist = grammar.VALUE_ALLOWLISTS.get(verb, frozenset({"1"}))
    valued = grammar.parse_human_valve_action(action_id=f"{verb}:bd-ib-1:{next(iter(allowlist))}")

    assert approval is not None or valued is not None


def test_set_factory_safety_admits_exactly_the_closed_enum() -> None:
    """The rationale is mandatory and drawn from the field's own three values."""
    assert grammar.VALUE_ALLOWLISTS["set-factory-safety"] == frozenset(
        {"needs-host-secrets", "mutates-host-machinery", "needs-privileged-host"}
    )
    assert grammar.parse_human_valve_action(
        action_id="set-factory-safety:bd-ib-1:needs-host-secrets"
    ) == ("set-factory-safety", "bd-ib-1", "needs-host-secrets")
    assert grammar.parse_human_valve_action(action_id="set-factory-safety:bd-ib-1:") is None
    assert grammar.parse_human_valve_action(action_id="set-factory-safety:bd-ib-1:host") is None


def test_the_gate_rejects_an_unregistered_verb() -> None:
    assert not grammar.is_human_valve_action(action_id="set-factory-safeties:bd-ib-1:x")
    assert not grammar.is_human_valve_action(action_id="impl:bd-ib-1")
