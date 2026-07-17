"""Paired coverage for shell-backed beads client effects."""

from __future__ import annotations

import subprocess

import pytest
from livespec_orchestrator_beads_fabro.effects import _beads_client_shell as shell
from livespec_orchestrator_beads_fabro.errors import BeadsConnectionError


def test_raise_for_status_maps_connection_refused() -> None:
    completed = subprocess.CompletedProcess(
        args=["bd", "list"],
        returncode=1,
        stdout="",
        stderr="connection refused",
    )

    with pytest.raises(BeadsConnectionError):
        shell.raise_for_status(completed=completed, argv=["bd", "list"], tenant="tenant")
