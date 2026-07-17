"""Compatibility shim for shell-backed beads client effects."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.effects._beads_client_shell import (
    assert_repo_root_matches_config,
    invoke,
    raise_for_status,
    read_bd_config_value,
)

__all__: list[str] = [
    "assert_repo_root_matches_config",
    "invoke",
    "raise_for_status",
    "read_bd_config_value",
]
