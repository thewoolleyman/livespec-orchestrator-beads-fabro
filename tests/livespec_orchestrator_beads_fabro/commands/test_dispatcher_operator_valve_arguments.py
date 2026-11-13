"""Tests for the parser registration of human-held dispatcher valves."""

from __future__ import annotations

import argparse

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_operator_valve_arguments


def test_registers_each_operator_valve_with_its_own_parser(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each valve argument surface receives the parser bearing its command name."""
    seen: list[str] = []

    def add_parser(name: str) -> argparse.ArgumentParser:
        return argparse.ArgumentParser(prog=name)

    monkeypatch.setattr(
        _dispatcher_operator_valve_arguments,
        "add_clear_provider_exhaustion_arguments",
        lambda *, parser: seen.append(parser.prog),
    )
    monkeypatch.setattr(
        _dispatcher_operator_valve_arguments,
        "add_clear_acp_availability_hold_arguments",
        lambda *, parser: seen.append(parser.prog),
    )
    monkeypatch.setattr(
        _dispatcher_operator_valve_arguments,
        "add_fresh_ruling_arguments",
        lambda *, parser: seen.append(parser.prog),
    )

    _dispatcher_operator_valve_arguments.add_operator_valve_subcommands(add_parser=add_parser)

    assert seen == [
        "clear-provider-exhaustion",
        "clear-acp-availability-hold",
        "fresh-ruling",
    ]
