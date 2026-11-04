"""Tests for the moved `fabro_port_for_plan` constructor."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._fabro_port_factory import fabro_port_for_plan


def test_moved_constructor_keeps_its_original_docstring() -> None:
    assert fabro_port_for_plan.__doc__ == "Construct the Fabro CLI port from a dispatch plan."
