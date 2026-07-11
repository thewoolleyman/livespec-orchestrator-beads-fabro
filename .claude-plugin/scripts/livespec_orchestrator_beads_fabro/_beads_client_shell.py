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

# A server-mode tenant's `.beads/config.yaml` declares this flat-dotted marker
# (whitespace-stripped). Its ABSENCE identifies an EMBEDDED, self-contained Dolt
# ledger (initialized with no `--server`, e.g. the disposable livespec-e2e
# golden-master target). Mirrors the bootstrap credential-precheck's marker.
_SERVER_MODE_MARKER = "dolt.mode:server"


def invoke(*, config: StoreConfig, argv: list[str]) -> subprocess.CompletedProcess[str]:
    """Run one `bd` command after validating the resolved repo tenant.

    An EMBEDDED ledger (self-contained Dolt, no shared server) has no family
    tenant password and no server tenant identity, so both the
    `BEADS_DOLT_PASSWORD` guard and the `.beads/config.yaml` tenant match are
    meaningless there and are SKIPPED. The server-mode path is unchanged.
    """
    repo_root = config.repo_root
    embedded = repo_root is not None and _is_embedded_ledger(repo_root=repo_root)
    if not embedded and not os.environ.get("BEADS_DOLT_PASSWORD"):
        raise BeadsCredentialMissingError(variable="BEADS_DOLT_PASSWORD")
    if repo_root is not None and not embedded:
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


def _is_embedded_ledger(*, repo_root: Path) -> bool:
    """True when the repo's beads ledger is embedded (self-contained Dolt,
    no shared server): its `.beads/config.yaml` exists and does NOT declare
    `dolt.mode: server`. Absent/unreadable config -> False (fail closed:
    treat as server-mode, requiring the password + tenant match)."""
    config_path = repo_root / ".beads" / "config.yaml"
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return not any(
        line.strip().replace(" ", "") == _SERVER_MODE_MARKER for line in text.splitlines()
    )


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
