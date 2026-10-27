"""Shell execution helpers for `ShellBeadsClient`."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
    "reset_tenant_verification_memo",
]


# Tier 1: positive tenant verifications, memoized for process lifetime per
# (repo root, expected server user, expected database). Every bd invocation used
# to re-prove the tenant with two fresh `bd config get` subprocesses, which made
# those config reads most of the fleet's bd traffic. Only POSITIVE results are
# memoized; a mismatch keeps raising on every call.
_VERIFIED_TENANTS: set[tuple[str, str, str]] = set()
_LOGGER = logging.getLogger(__name__)


def reset_tenant_verification_memo() -> None:
    """Forget the in-process (tier 1) verifications — the fresh-process seam."""
    _VERIFIED_TENANTS.clear()


def _tenant_memo_key(*, config: StoreConfig, repo_root: Path) -> tuple[str, str, str]:
    """Memo key for one process-lifetime tenant verification."""
    return (str(repo_root), config.server_user, config.database)


# Tier 2: the same positive verifications, cached ACROSS processes. ~82% of the
# fleet's observed `bd config` traffic comes from one-shot CLI wrapper processes
# (scripts/bin/*.py) that spawn, make one or two bd calls, and exit, so the
# in-process memo above never gets a second hit there. The cache is keyed by
# tenant identity PLUS the `.beads/config.yaml` mtime+size, so any config edit
# forces a fresh verification. A short TTL bounds the one case the key cannot
# see: a config rotation that preserves both mtime and size.
#
# The file lives OUTSIDE the governed repo, under the XDG cache dir, one file
# per repo root. It first lived at `.beads/tenant-verification-cache.json`,
# which `.beads/.gitignore` (bd-managed, never hand-edited here) does not cover,
# so every repo the orchestrator touched grew a permanently untracked file.
_CACHE_TTL_SECONDS = 300.0
_LEGACY_CACHE_RELATIVE_PATH = Path(".beads") / "tenant-verification-cache.json"


def _tenant_cache_path(*, repo_root: Path) -> Path:
    """The XDG-cache file holding this repo root's verifications."""
    xdg_home = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg_home) if xdg_home else Path.home() / ".cache"
    digest = hashlib.sha256(str(repo_root).encode("utf-8")).hexdigest()[:32]
    return base / "livespec-orchestrator-beads-fabro" / "tenant-verification" / f"{digest}.json"


def _discard_legacy_cache(*, repo_root: Path) -> None:
    """Best-effort removal of the in-repo cache file this location replaced."""
    try:
        (repo_root / _LEGACY_CACHE_RELATIVE_PATH).unlink(missing_ok=True)
    except OSError:  # pragma: no cover  — a read-only `.beads/` keeps its stale file.
        return


def _tenant_cache_key(*, config: StoreConfig, repo_root: Path) -> str:
    """Cross-process cache key: tenant identity plus config-file identity."""
    try:
        stat = (repo_root / ".beads" / "config.yaml").stat()
    except OSError:
        identity = "absent"
    else:
        identity = f"{stat.st_mtime_ns}:{stat.st_size}"
    return "|".join((str(repo_root), config.server_user, config.database, identity))


def _load_cache_entries(*, cache_path: Path) -> dict[str, float]:
    """Read the unexpired cached verifications; a corrupt file reads as empty."""
    try:
        payload: Any = json.loads(cache_path.read_text(encoding="utf-8"))
        items: list[tuple[Any, Any]] = list(payload.items())
    except (OSError, ValueError, AttributeError):
        return {}
    now = time.time()
    return {
        str(key): float(value)
        for key, value in items
        if isinstance(value, int | float) and now - float(value) < _CACHE_TTL_SECONDS
    }


def _store_cache_entry(*, cache_path: Path, cache_key: str) -> None:
    """Record one positive verification, replacing the cache file atomically."""
    entries = _load_cache_entries(cache_path=cache_path)
    entries[cache_key] = time.time()
    staging_path = cache_path.with_name(f"{cache_path.name}.{os.getpid()}.tmp")
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        _ = staging_path.write_text(json.dumps(entries), encoding="utf-8")
        _ = staging_path.replace(cache_path)
    except OSError:  # pragma: no cover  — an unwritable `.beads/` degrades to no cache.
        return


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
    if not embedded and not config.credential_wrapper and not os.environ.get("BEADS_DOLT_PASSWORD"):
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
        detail = (
            "credential wrapper not found: " + shlex.join(config.credential_wrapper)
            if config.credential_wrapper
            else f"bd binary not found at {config.bd_path}"
        )
        raise BeadsConnectionError(detail=detail) from exc
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
    memo_key = _tenant_memo_key(config=config, repo_root=repo_root)
    if memo_key in _VERIFIED_TENANTS:
        return
    cache_path = _tenant_cache_path(repo_root=repo_root)
    cache_key = _tenant_cache_key(config=config, repo_root=repo_root)
    if cache_key in _load_cache_entries(cache_path=cache_path):
        _VERIFIED_TENANTS.add(memo_key)
        return
    expected = {
        "dolt.server-user": config.server_user,
        "dolt.database": config.database,
    }
    observed = {
        key: read_bd_config_value(config=config, repo_root=repo_root, key=key) for key in expected
    }
    if observed == expected:
        _VERIFIED_TENANTS.add(memo_key)
        _store_cache_entry(cache_path=cache_path, cache_key=cache_key)
        _discard_legacy_cache(repo_root=repo_root)
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
    argv = [*config.credential_wrapper, config.bd_path, "config", "get", key]
    try:
        completed = subprocess.run(  # noqa: S603  # pragma: no cover
            argv,
            capture_output=True,
            text=True,
            check=False,
            cwd=repo_root,
        )
    except FileNotFoundError as exc:  # pragma: no cover
        detail = (
            "credential wrapper not found: " + shlex.join(config.credential_wrapper)
            if config.credential_wrapper
            else f"bd binary not found at {config.bd_path}"
        )
        raise BeadsConnectionError(detail=detail) from exc
    raise_for_status(completed=completed, argv=argv, tenant=config.database)  # pragma: no cover
    return completed.stdout.strip()


def raise_for_status(
    *,
    completed: subprocess.CompletedProcess[str],
    argv: list[str],
    tenant: str,
) -> None:
    """Map a nonzero `bd` exit onto the typed expected-error surface."""
    stderr = completed.stderr or ""
    if completed.returncode == 0:
        if stderr:
            _LOGGER.warning(
                "bd exited zero with stderr",
                extra={
                    "bd_argv": argv,
                    "bd_tenant": tenant,
                    "bd_stderr": stderr.strip(),
                },
            )
        return
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
