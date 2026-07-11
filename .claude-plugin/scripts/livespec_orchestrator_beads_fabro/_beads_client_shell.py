"""Shell execution helpers for `ShellBeadsClient`."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsTenantMissingError,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "assert_repo_root_matches_config",
    "invoke",
    "raise_for_status",
    "read_bd_config_value",
]


def invoke(*, config: StoreConfig, argv: list[str]) -> subprocess.CompletedProcess[str]:
    """Run one `bd` command after validating the resolved repo tenant."""
    if not os.environ.get("BEADS_DOLT_PASSWORD"):
        raise BeadsCredentialMissingError(variable="BEADS_DOLT_PASSWORD")
    repo_root = config.repo_root
    if repo_root is not None:
        assert_repo_root_matches_config(config=config, repo_root=repo_root)
    try:
        completed = subprocess.run(  # noqa: S603  # pragma: no cover
            argv,
            capture_output=True,
            text=True,
            check=False,
            cwd=repo_root,
        )
    except FileNotFoundError as exc:  # pragma: no cover
        raise BeadsConnectionError(detail=f"bd binary not found at {config.bd_path}") from exc
    raise_for_status(completed=completed, argv=argv, tenant=config.database)  # pragma: no cover
    return completed  # pragma: no cover


def assert_repo_root_matches_config(*, config: StoreConfig, repo_root: Path) -> None:
    """Raise when `.beads/config.yaml` points at a different tenant."""
    expected = {
        "dolt.server-user": config.server_user,
        "dolt.database": config.database,
    }
    observed = {
        key: read_bd_config_value(config=config, repo_root=repo_root, key=key) for key in expected
    }
    if observed == expected:
        return
    observed_text = ", ".join(f"{key}={observed[key]}" for key in sorted(observed))
    expected_text = ", ".join(f"{key}={expected[key]}" for key in sorted(expected))
    raise BeadsConnectionError(
        detail=(
            f"bd config in {repo_root} does not match resolved StoreConfig "
            f"({observed_text}; expected {expected_text})"
        )
    )


def read_bd_config_value(*, config: StoreConfig, repo_root: Path, key: str) -> str:
    """Read one `bd config get` value from the target repo root."""
    argv = [config.bd_path, "config", "get", key]
    try:
        completed = subprocess.run(  # noqa: S603  # pragma: no cover
            argv,
            capture_output=True,
            text=True,
            check=False,
            cwd=repo_root,
        )
    except FileNotFoundError as exc:  # pragma: no cover
        raise BeadsConnectionError(detail=f"bd binary not found at {config.bd_path}") from exc
    raise_for_status(completed=completed, argv=argv, tenant=config.database)  # pragma: no cover
    return completed.stdout.strip()


def raise_for_status(
    *,
    completed: subprocess.CompletedProcess[str],
    argv: list[str],
    tenant: str,
) -> None:
    """Map a nonzero `bd` exit onto the typed expected-error surface."""
    if completed.returncode == 0:
        return
    stderr = completed.stderr or ""
    command = " ".join(argv)
    lowered = stderr.lower()
    if "connection refused" in lowered or "can't connect" in lowered:
        raise BeadsConnectionError(detail=stderr.strip())
    if "unknown database" in lowered or "does not exist" in lowered:
        raise BeadsTenantMissingError(tenant=tenant)
    raise BeadsCommandError(
        command=command,
        exit_code=completed.returncode,
        stderr=stderr,
    )
