"""Tests for the ACP transport-fault classification of a failure cause."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._fabro_transport_fault import (
    ADAPTER_EXITED,
    BACKGROUNDED_TOOL,
    TURN_TIMED_OUT,
    TransportFault,
    transport_fault_clause,
    transport_fault_from_cause,
)

_COMMAND = "git push -u origin HEAD:refs/heads/feat/bd-ib-qm4luz 2>&1 | tail -100"
_TASK = "b9hp9md1u"
_MEASURED_BACKGROUNDED = (
    f"ACP tool call toolu_01SANITIZEDTOOLCALL ({_COMMAND}) continued in background "
    f"as task {_TASK}; Fabro terminated the turn before the agent could start "
    "conflicting work"
)
_MEASURED_ADAPTER_EXIT = (
    "ACP process exited before protocol completed: termination=exited, exit_code=1"
)
_MEASURED_PROVIDER_CEILING = (
    "You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage "
    "or try again at 2026-10-04T23:00:00Z"
)


def test_the_measured_backgrounded_cause_names_its_command_and_task() -> None:
    fault = transport_fault_from_cause(cause=_MEASURED_BACKGROUNDED)

    assert fault == TransportFault(
        family=BACKGROUNDED_TOOL,
        command=_COMMAND,
        task_id=_TASK,
    )


def test_a_backgrounded_cause_that_names_no_task_still_classifies() -> None:
    """The engine owns the wording; a partial read degrades, never guesses."""
    fault = transport_fault_from_cause(
        cause=f"ACP tool call toolu_01 ({_COMMAND}) continued in background"
    )

    assert fault is not None
    assert (fault.family, fault.command, fault.task_id) == (BACKGROUNDED_TOOL, _COMMAND, None)


def test_a_backgrounded_cause_with_no_parenthesised_command_names_no_command() -> None:
    """Never an invented command: the family alone is the honest answer."""
    fault = transport_fault_from_cause(cause="a tool call continued in background as task bzz1")

    assert fault == TransportFault(family=BACKGROUNDED_TOOL, command=None, task_id=None)


def test_an_empty_parenthesised_command_is_reported_as_no_command() -> None:
    fault = transport_fault_from_cause(cause="ACP tool call ( ) continued in background")

    assert fault == TransportFault(family=BACKGROUNDED_TOOL, command=None, task_id=None)


def test_the_measured_adapter_exit_cause_is_its_own_family() -> None:
    """`bd-ib-qulf` shared the stage label and nothing else with this fault."""
    fault = transport_fault_from_cause(cause=_MEASURED_ADAPTER_EXIT)

    assert fault == TransportFault(family=ADAPTER_EXITED, command=None, task_id=None)


def test_a_timed_out_turn_is_its_own_family() -> None:
    fault = transport_fault_from_cause(cause="ACP turn timed out after 600s")

    assert fault == TransportFault(family=TURN_TIMED_OUT, command=None, task_id=None)


def test_a_backgrounded_cause_that_also_mentions_a_timeout_stays_backgrounded() -> None:
    """The specific family wins: it is the one with a remedy."""
    fault = transport_fault_from_cause(
        cause=(
            f"ACP tool call toolu_01 ({_COMMAND}) continued in background as task {_TASK} "
            "after its 120s timeout"
        )
    )

    assert fault is not None
    assert fault.family == BACKGROUNDED_TOOL


def test_a_provider_ceiling_is_not_a_transport_fault() -> None:
    """The carrier worked; the model declined. It has its own typed field."""
    assert transport_fault_from_cause(cause=_MEASURED_PROVIDER_CEILING) is None


def test_an_ordinary_node_failure_is_not_a_transport_fault() -> None:
    assert transport_fault_from_cause(cause="janitor script exited 1: coverage below 100%") is None


def test_an_unreadable_cause_classifies_nothing() -> None:
    assert transport_fault_from_cause(cause=None) is None


def test_the_clause_names_the_family_the_command_and_the_task() -> None:
    fault = transport_fault_from_cause(cause=_MEASURED_BACKGROUNDED)

    assert fault is not None
    clause = transport_fault_clause(fault=fault)

    assert clause.startswith(f"transport fault ({BACKGROUNDED_TOOL}): ")
    assert "moved a shell call into a background task" in clause
    assert f"the backgrounded command was `{_COMMAND}`" in clause
    assert f"background task {_TASK}" in clause


def test_the_clause_of_a_family_with_nothing_identified_is_the_family_alone() -> None:
    fault = transport_fault_from_cause(cause=_MEASURED_ADAPTER_EXIT)

    assert fault is not None
    clause = transport_fault_clause(fault=fault)

    assert clause == (
        f"transport fault ({ADAPTER_EXITED}): the ACP adapter process exited before "
        "the protocol completed"
    )
