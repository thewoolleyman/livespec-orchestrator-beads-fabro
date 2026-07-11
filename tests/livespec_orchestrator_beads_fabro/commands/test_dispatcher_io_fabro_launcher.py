"""Tests for the Fabro launcher IO extraction."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands import _dispatcher_io
from livespec_orchestrator_beads_fabro.commands._dispatcher_io_fabro_launcher import (
    WatchedFabroLauncher,
)


def test_watched_launcher_remains_the_dispatcher_io_public_entry_point() -> None:
    assert _dispatcher_io.WatchedFabroLauncher is WatchedFabroLauncher
