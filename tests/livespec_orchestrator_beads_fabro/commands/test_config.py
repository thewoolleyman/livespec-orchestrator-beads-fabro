"""Tests for the beads connection-resolution helper (`commands._config`).

`resolve_store_config` resolves the per-repo tenant connection descriptor
from the `.livespec.jsonc` connection block overlaid by environment
variables. Coverage spans: built-in defaults, the connection block,
the `LIVESPEC_BD_PATH` / `LIVESPEC_BEADS_FAKE` env overlays, the
no-password invariant, and the malformed/absent-config fallbacks.

The autouse hermetic fixture sets `LIVESPEC_BEADS_FAKE=1`; tests that need
to observe the UNSET `fake` default `monkeypatch.delenv` it first.
"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._config import (
    resolve_credential_wrapper,
    resolve_fabro_bin,
    resolve_store_config,
)
from livespec_orchestrator_beads_fabro.errors import ConnectionPrefixMissingError
from livespec_orchestrator_beads_fabro.types import StoreConfig

_CONFIG_NAME = ".livespec.jsonc"


def _write_config(*, cwd: Path, body: str) -> None:
    _ = (cwd / _CONFIG_NAME).write_text(body, encoding="utf-8")


def test_resolve_uses_defaults_when_no_config_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With an explicit prefix supplied, the other fields take built-in defaults.

    `prefix` is REQUIRED (it is decoupled from the tenant DB name), so the
    no-config-file path is exercised by supplying the prefix via the
    connection block while leaving every other field unset.
    """
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    monkeypatch.delenv("LIVESPEC_BD_PATH", raising=False)
    _write_config(
        cwd=tmp_path,
        body='{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
    )
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    assert config.tenant == "livespec-orch-beads-fabro"
    assert config.prefix == "bd-ib"
    assert config.database == "livespec-orch-beads-fabro"
    assert config.server_user == "livespec-orch-beads-fabro"
    assert config.server_host == "127.0.0.1"
    assert config.server_port == 3307
    assert config.socket is None
    assert config.bd_path == "bd"
    assert config.fake is False


def test_unset_prefix_raises_actionable_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unset/empty `connection.prefix` FAILS LOUD instead of defaulting.

    The bd issue-ID create-prefix is decoupled from the tenant DB name, so
    silently defaulting `prefix` to the tenant would mint tenant-named ids
    the server rejects. The loader raises a typed, actionable error instead.
    """
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    _write_config(
        cwd=tmp_path,
        body='{"livespec-orchestrator-beads-fabro": {"connection": {"tenant": "solo"}}}',
    )
    with pytest.raises(ConnectionPrefixMissingError) as excinfo:
        _ = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    message = str(excinfo.value)
    assert "connection.prefix is required" in message
    assert "bd-ib" in message


def test_empty_prefix_string_raises_actionable_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit empty-string prefix is treated as unset and FAILS LOUD."""
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    _write_config(
        cwd=tmp_path,
        body='{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": ""}}}',
    )
    with pytest.raises(ConnectionPrefixMissingError):
        _ = resolve_store_config(cwd=tmp_path, work_items_arg=None)


def test_work_items_path_property_returns_self(
    tmp_path: Path,
) -> None:
    _write_config(
        cwd=tmp_path,
        body='{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
    )
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    assert config.work_items_path is config


def test_resolve_reads_connection_block(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    monkeypatch.delenv("LIVESPEC_BD_PATH", raising=False)
    _write_config(
        cwd=tmp_path,
        body="""
        {
          "livespec-orchestrator-beads-fabro": {
            "connection": {
              "tenant": "my-tenant",
              "prefix": "my-prefix",
              "database": "my-db",
              "server_user": "tenant-user",
              "server_host": "10.0.0.5",
              "server_port": 9999,
              "socket": "/tmp/dolt.sock",
              "bd_path": "/opt/bd/bin/bd",
              "fake": true
            }
          }
        }
        """,
    )
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    assert config.tenant == "my-tenant"
    assert config.prefix == "my-prefix"
    assert config.database == "my-db"
    assert config.server_user == "tenant-user"
    assert config.server_host == "10.0.0.5"
    assert config.server_port == 9999
    assert config.socket == "/tmp/dolt.sock"
    assert config.bd_path == "/opt/bd/bin/bd"
    assert config.fake is True


def test_database_and_user_default_to_tenant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """database==server_user default to the tenant when unset.

    They ARE the tenant identity (no decoupling), so they keep defaulting.
    `prefix`, by contrast, is REQUIRED and supplied explicitly here.
    """
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    _write_config(
        cwd=tmp_path,
        body='{"livespec-orchestrator-beads-fabro": {"connection": {"tenant": "solo", "prefix": "bd-ib"}}}',
    )
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    assert config.prefix == "bd-ib"
    assert config.database == "solo"
    assert config.server_user == "solo"


def test_env_bd_path_overrides_block(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIVESPEC_BD_PATH", "/managed/bd")
    _write_config(
        cwd=tmp_path,
        body='{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib", "bd_path": "/block/bd"}}}',
    )
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    assert config.bd_path == "/managed/bd"


def test_empty_env_bd_path_falls_through_to_block(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIVESPEC_BD_PATH", "")
    _write_config(
        cwd=tmp_path,
        body='{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib", "bd_path": "/block/bd"}}}',
    )
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    assert config.bd_path == "/block/bd"


@pytest.mark.parametrize("truthy", ["1", "true", "TRUE", "yes", "on"])
def test_env_fake_truthy_forces_fake(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    truthy: str,
) -> None:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", truthy)
    _write_config(
        cwd=tmp_path,
        body='{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
    )
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    assert config.fake is True


def test_env_fake_falsy_forces_real(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "0")
    _write_config(
        cwd=tmp_path,
        body='{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
    )
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    assert config.fake is False


def test_block_fake_used_when_env_unset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    _write_config(
        cwd=tmp_path,
        body='{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib", "fake": true}}}',
    )
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    assert config.fake is True


def test_block_non_bool_fake_falls_back_to_false(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    _write_config(
        cwd=tmp_path,
        body='{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib", "fake": "yes"}}}',
    )
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    assert config.fake is False


def test_non_int_server_port_falls_back_to_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    _write_config(
        cwd=tmp_path,
        body='{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib", "server_port": "nope"}}}',
    )
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    assert config.server_port == 3307


def test_empty_socket_string_reads_as_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    _write_config(
        cwd=tmp_path,
        body='{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib", "socket": ""}}}',
    )
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    assert config.socket is None


def test_malformed_jsonc_yields_no_prefix_and_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed JSONC falls back to an empty block, which has no prefix → raises."""
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    _write_config(cwd=tmp_path, body="{ this is not valid json ")
    with pytest.raises(ConnectionPrefixMissingError):
        _ = resolve_store_config(cwd=tmp_path, work_items_arg=None)


def test_non_object_root_yields_no_prefix_and_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-object JSON root falls back to an empty block → no prefix → raises."""
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    _write_config(cwd=tmp_path, body="[1, 2, 3]")
    with pytest.raises(ConnectionPrefixMissingError):
        _ = resolve_store_config(cwd=tmp_path, work_items_arg=None)


def test_non_dict_plugin_block_yields_no_prefix_and_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A scalar plugin block falls back to an empty connection → no prefix → raises."""
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    _write_config(cwd=tmp_path, body='{"livespec-orchestrator-beads-fabro": "scalar"}')
    with pytest.raises(ConnectionPrefixMissingError):
        _ = resolve_store_config(cwd=tmp_path, work_items_arg=None)


def test_non_dict_connection_block_yields_no_prefix_and_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A scalar connection block falls back to an empty block → no prefix → raises."""
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    _write_config(cwd=tmp_path, body='{"livespec-orchestrator-beads-fabro": {"connection": 7}}')
    with pytest.raises(ConnectionPrefixMissingError):
        _ = resolve_store_config(cwd=tmp_path, work_items_arg=None)


def test_no_config_file_yields_no_prefix_and_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An absent config file yields no prefix and FAILS LOUD."""
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    with pytest.raises(ConnectionPrefixMissingError):
        _ = resolve_store_config(cwd=tmp_path, work_items_arg=None)


def test_path_args_are_accepted_and_ignored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The plaintext-signature work_items_arg is a no-op here."""
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    _write_config(
        cwd=tmp_path,
        body='{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
    )
    config = resolve_store_config(
        cwd=tmp_path,
        work_items_arg="custom/work.jsonl",
    )
    assert config.tenant == "livespec-orch-beads-fabro"


def test_no_password_field_on_descriptor() -> None:
    """The tenant password is NEVER a field on StoreConfig (read from env only)."""
    field_names = {field.name for field in fields(StoreConfig)}
    assert "password" not in field_names
    assert not any("password" in name.lower() for name in field_names)


_CONFIG_SHUTIL_WHICH = "livespec_orchestrator_beads_fabro.commands._config.shutil.which"


def test_default_fabro_bin_prefers_existing_home_binary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default (a): an existing, executable `$HOME/.fabro/bin/fabro` is used.

    The host-under-wrapper case. `Path.home` is monkeypatched (proving call-time
    resolution); the tmp home binary is a real chmod-0o755 file; `shutil.which`
    is stubbed to a sentinel to prove the PATH fallback is NOT consulted once
    the absolute home binary resolves.
    """
    monkeypatch.delenv("LIVESPEC_FABRO_BIN", raising=False)
    home = tmp_path / "home"
    fabro = home / ".fabro" / "bin" / "fabro"
    fabro.parent.mkdir(parents=True)
    _ = fabro.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fabro.chmod(0o755)
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(_CONFIG_SHUTIL_WHICH, lambda _name: "/sentinel/should/not/be/used")
    assert resolve_fabro_bin(cwd=tmp_path) == str(fabro)


def test_default_fabro_bin_falls_back_to_path_lookup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default (b): with no home binary, a PATH lookup (shutil.which) supplies it.

    The orchestrator-container case: `$HOME/.fabro/bin/fabro` is absent but
    `fabro` is on PATH (e.g. /usr/local/bin/fabro).
    """
    monkeypatch.delenv("LIVESPEC_FABRO_BIN", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)  # tmp_path has no .fabro/bin/fabro
    monkeypatch.setattr(_CONFIG_SHUTIL_WHICH, lambda _name: "/usr/local/bin/fabro")
    assert resolve_fabro_bin(cwd=tmp_path) == "/usr/local/bin/fabro"


def test_default_fabro_bin_returns_concrete_home_path_when_unresolvable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default (c): with neither a home binary nor a PATH hit, the concrete home path.

    A concrete (not bare-name) path so the downstream preflight error names a
    real, actionable target.
    """
    monkeypatch.delenv("LIVESPEC_FABRO_BIN", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(_CONFIG_SHUTIL_WHICH, lambda _name: None)
    assert resolve_fabro_bin(cwd=tmp_path) == str(tmp_path / ".fabro" / "bin" / "fabro")


def test_resolve_fabro_bin_uses_dispatcher_config_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no env override, the `dispatcher.fabro_bin` config key is used."""
    monkeypatch.delenv("LIVESPEC_FABRO_BIN", raising=False)
    _write_config(
        cwd=tmp_path,
        body='{"livespec-orchestrator-beads-fabro": {"dispatcher": {"fabro_bin": "/opt/fabro/bin/fabro"}}}',
    )
    assert resolve_fabro_bin(cwd=tmp_path) == "/opt/fabro/bin/fabro"


def test_env_fabro_bin_beats_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-empty `LIVESPEC_FABRO_BIN` env value wins over the config key."""
    monkeypatch.setenv("LIVESPEC_FABRO_BIN", "/env/fabro/bin/fabro")
    _write_config(
        cwd=tmp_path,
        body='{"livespec-orchestrator-beads-fabro": {"dispatcher": {"fabro_bin": "/config/fabro/bin/fabro"}}}',
    )
    assert resolve_fabro_bin(cwd=tmp_path) == "/env/fabro/bin/fabro"


def test_resolve_credential_wrapper_reads_top_level_list(
    tmp_path: Path,
) -> None:
    """A top-level `credential_wrapper` list is returned as an argv prefix.

    The `check-ledger-conformance-live` recipe resolves this to invoke the gate
    under the tenant-secret-injecting wrapper. Non-string tokens are coerced to
    str so the returned argv is always a `list[str]`.
    """
    _write_config(
        cwd=tmp_path,
        body='{"credential_wrapper": ["/usr/local/bin/with-livespec-env.sh", "--", 7]}',
    )
    assert resolve_credential_wrapper(cwd=tmp_path) == [
        "/usr/local/bin/with-livespec-env.sh",
        "--",
        "7",
    ]


def test_resolve_credential_wrapper_absent_or_non_list_yields_empty(
    tmp_path: Path,
) -> None:
    """A missing (or non-list) `credential_wrapper` fails open to the empty argv."""
    _write_config(
        cwd=tmp_path,
        body='{"credential_wrapper": "not-a-list"}',
    )
    assert resolve_credential_wrapper(cwd=tmp_path) == []
