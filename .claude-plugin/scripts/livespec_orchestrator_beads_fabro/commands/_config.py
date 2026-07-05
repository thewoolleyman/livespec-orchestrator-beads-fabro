"""Connection resolution shared across the thin-transport command modules.

The plaintext sibling resolved a pair of filesystem JSONL paths here. The
beads store has no JSONL files; instead this module resolves the per-repo
tenant CONNECTION descriptor (`StoreConfig`) from the `.livespec.jsonc`
connection block, overlaid by environment variables.

Resolution order (later wins):

1. Built-in defaults (`server_host=127.0.0.1`, `server_port=3307`,
   `fake=False`).
2. The `.livespec.jsonc` connection block at `<cwd>/.livespec.jsonc`
   under `livespec-orchestrator-beads-fabro.connection` (and the substrate `format`
   marker / `tenant` key). A missing file or block falls back to
   defaults plus a placeholder tenant. `connection.prefix`, however, is
   REQUIRED: it is bd's server-stored issue-ID create-prefix (e.g.
   `bd-ib`) and is DECOUPLED from the tenant DB name, so it is never
   defaulted — an unset/empty prefix raises `ConnectionPrefixMissingError`
   (`database` and `server_user` still default to the tenant, which they
   ARE).
3. Environment overlay:
   - `LIVESPEC_BD_PATH` — absolute path to the pinned bd v1.0.5 binary
     (NEVER the mise shim). Overrides the config `bd_path`.
   - `LIVESPEC_BEADS_FAKE` — when truthy (`1`/`true`/`yes`), forces the
     hermetic in-memory backend. This is how the default CI tier and the
     no-live-connection runtime fallback select the `FakeBeadsClient`.

The tenant PASSWORD is never resolved here: the shell backend reads
`BEADS_DOLT_PASSWORD` from the environment at `bd`-call time. It is never
stored on the descriptor.

`resolve_fabro_bin` resolves the Dispatcher's `fabro` engine binary by the
same env > config > default precedence (later listed wins the tie-break the
other way — env is highest-priority):

1. `LIVESPEC_FABRO_BIN` — an absolute path to the `fabro` binary. Highest
   priority (mirrors `LIVESPEC_BD_PATH`). A non-empty value wins outright.
2. The `.livespec.jsonc` `livespec-orchestrator-beads-fabro.dispatcher`
   block's `fabro_bin` key, when non-empty.
3. The built-in default, resolved AT CALL TIME across BOTH deploy envs: the
   absolute `$HOME/.fabro/bin/fabro` when it exists and is executable, else a
   `PATH` lookup (`shutil.which("fabro")`), else the concrete home-path string.

The default probes the absolute home path before a bare `PATH` lookup because
the two envs that run with no explicit `--fabro-bin` disagree: the fleet
credential wrapper sanitizes `PATH` (secure_path, no `~/.local/bin`) but
PRESERVES `HOME`, so on the host the absolute `$HOME/.fabro/bin/fabro`
resolves where a bare `fabro` lookup fails; the orchestrator container instead
carries `fabro` at `/usr/local/bin/fabro` ON `PATH` with no `~/.fabro`, which
the `shutil.which` fallback finds.

The function signature keeps the plaintext sibling's
`work_items_arg` parameter (`resolve_store_config(*, cwd,
work_items_arg)`) so the command call sites do not change. The
`work_items_arg` parameter is accepted-and-ignored under the beads
substrate (there are no JSONL path overrides); it remains in the
signature only for call-site compatibility.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands import _jsonc
from livespec_orchestrator_beads_fabro.errors import ConnectionPrefixMissingError
from livespec_orchestrator_beads_fabro.types import StoreConfig

_LIVESPEC_CONFIG = ".livespec.jsonc"
_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_CONNECTION_KEY = "connection"
_DISPATCHER_KEY = "dispatcher"

_DEFAULT_SERVER_HOST = "127.0.0.1"
_DEFAULT_SERVER_PORT = 3307
_DEFAULT_BD_PATH = "bd"
_DEFAULT_TENANT = "livespec-orch-beads-fabro"

_ENV_BD_PATH = "LIVESPEC_BD_PATH"
_ENV_FAKE = "LIVESPEC_BEADS_FAKE"
_ENV_FABRO_BIN = "LIVESPEC_FABRO_BIN"

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def resolve_store_config(
    *,
    cwd: Path,
    work_items_arg: str | None,
) -> StoreConfig:
    """Resolve the beads connection descriptor from .livespec.jsonc + env.

    `work_items_arg` is accepted for call-site compatibility with the
    plaintext signature and is intentionally unused under the beads
    substrate (no JSONL path overrides exist).
    """
    _ = work_items_arg
    block = _read_connection_block(cwd=cwd)
    tenant = _str_or(block.get("tenant"), default=_DEFAULT_TENANT)
    prefix = _require_prefix(block=block)
    database = _str_or(block.get("database"), default=tenant)
    server_user = _str_or(block.get("server_user"), default=tenant)
    server_host = _str_or(block.get("server_host"), default=_DEFAULT_SERVER_HOST)
    server_port = _int_or(block.get("server_port"), default=_DEFAULT_SERVER_PORT)
    socket = _optional_str(block.get("socket"))
    bd_path = _resolve_bd_path(block=block)
    fake = _resolve_fake(block=block)
    return StoreConfig(
        tenant=tenant,
        prefix=prefix,
        server_user=server_user,
        database=database,
        bd_path=bd_path,
        server_host=server_host,
        server_port=server_port,
        socket=socket,
        fake=fake,
        repo_root=cwd,
    )


def resolve_fabro_bin(*, cwd: Path) -> str:
    """Resolve the Dispatcher's `fabro` engine binary path (env > config > default).

    Precedence: a non-empty `LIVESPEC_FABRO_BIN` env value wins outright; else
    the `.livespec.jsonc` `dispatcher.fabro_bin` key, when non-empty; else the
    call-time default from `_default_fabro_bin` (absolute home path, else a
    `PATH` lookup, else the concrete home-path string).
    """
    env_value = os.environ.get(_ENV_FABRO_BIN)
    if env_value is not None and env_value != "":
        return env_value
    block = _read_dispatcher_block(cwd=cwd)
    configured = _str_or(block.get("fabro_bin"), default="")
    if configured != "":
        return configured
    return _default_fabro_bin()


def _read_connection_block(*, cwd: Path) -> dict[str, Any]:
    """Read the `livespec-orchestrator-beads-fabro.connection` block, or {} when absent."""
    return _read_plugin_sub_block(cwd=cwd, key=_CONNECTION_KEY)


def _read_dispatcher_block(*, cwd: Path) -> dict[str, Any]:
    """Read the `livespec-orchestrator-beads-fabro.dispatcher` block, or {} when absent."""
    return _read_plugin_sub_block(cwd=cwd, key=_DISPATCHER_KEY)


def _read_plugin_sub_block(*, cwd: Path, key: str) -> dict[str, Any]:
    """Read a named sub-block of the `livespec-orchestrator-beads-fabro` block.

    Returns `{}` for every off-happy-path shape (absent config file, malformed
    JSONC, non-object root, non-dict plugin block, non-dict / absent sub-block)
    so each caller applies its own defaults. Shared by the connection and
    dispatcher readers so the JSONC -> plugin-block -> sub-block traversal is
    single-sourced rather than duplicated per sub-block.
    """
    config_path = cwd / _LIVESPEC_CONFIG
    if not config_path.is_file():
        return {}
    raw_text = config_path.read_text(encoding="utf-8")
    try:
        parsed = _jsonc.loads(text=raw_text)
    except _jsonc.JsoncParseError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    parsed_dict = cast("dict[str, Any]", parsed)
    plugin_block_raw = parsed_dict.get(_PLUGIN_BLOCK)
    if not isinstance(plugin_block_raw, dict):
        return {}
    plugin_block = cast("dict[str, Any]", plugin_block_raw)
    sub_block_raw = plugin_block.get(key)
    if not isinstance(sub_block_raw, dict):
        return {}
    return cast("dict[str, Any]", sub_block_raw)


def _require_prefix(*, block: dict[str, Any]) -> str:
    """Return the explicit `connection.prefix`, or raise if unset/empty.

    `prefix` is bd's server-stored issue-ID create-prefix (e.g. `bd-ib`),
    DECOUPLED from the tenant DB name. It is therefore NEVER defaulted to the
    tenant: an unset/empty prefix would mint tenant-named ids the server
    rejects, so the loader FAILS LOUD instead.
    """
    value = block.get("prefix")
    if isinstance(value, str) and value != "":
        return value
    raise ConnectionPrefixMissingError


def _resolve_bd_path(*, block: dict[str, Any]) -> str:
    env_value = os.environ.get(_ENV_BD_PATH)
    if env_value is not None and env_value != "":
        return env_value
    return _str_or(block.get("bd_path"), default=_DEFAULT_BD_PATH)


def _default_fabro_bin() -> str:
    """The default `fabro` path, resolved AT CALL TIME across BOTH deploy envs.

    Two environments run the Dispatcher with no explicit `--fabro-bin`:

    - Host-under-wrapper: the fleet credential wrapper sanitizes `PATH`
      (secure_path, no `~/.local/bin`) but PRESERVES `HOME`, so the binary at
      `$HOME/.fabro/bin/fabro` resolves by absolute path where a bare `fabro`
      PATH lookup would fail.
    - Orchestrator container (dark factory): `fabro` lives at
      `/usr/local/bin/fabro` ON `PATH`, and `$HOME/.fabro/bin/fabro` is absent.

    So the default probes the absolute home path FIRST (fixes the host bug),
    then falls back to a `PATH` lookup (works in the container). When neither
    resolves it returns the concrete home-path string so the preflight error
    names a real, actionable target rather than a bare name. Computed at call
    time (not import time) so a test that monkeypatches `Path.home()` /
    `shutil.which` observes the redirected values.
    """
    home_candidate = Path.home() / ".fabro" / "bin" / "fabro"
    if home_candidate.is_file() and os.access(home_candidate, os.X_OK):
        return str(home_candidate)
    found = shutil.which("fabro")
    if found is not None:
        return found
    return str(home_candidate)


def _resolve_fake(*, block: dict[str, Any]) -> bool:
    env_value = os.environ.get(_ENV_FAKE)
    if env_value is not None:
        return env_value.strip().lower() in _TRUTHY
    block_value = block.get("fake")
    if isinstance(block_value, bool):
        return block_value
    return False


def _str_or(value: object, *, default: str) -> str:
    if isinstance(value, str) and value != "":
        return value
    return default


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value != "":
        return value
    return None


def _int_or(value: object, *, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default
