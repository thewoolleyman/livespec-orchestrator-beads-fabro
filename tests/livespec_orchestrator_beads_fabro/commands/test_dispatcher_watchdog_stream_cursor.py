"""The watchdog's per-run, cursor-based factory stream read."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpPort


def test_the_server_api_exposes_the_per_run_stream_route() -> None:
    """The cursor read belongs on the bound factory server API face."""
    assert hasattr(FabroHttpPort, "stream")
