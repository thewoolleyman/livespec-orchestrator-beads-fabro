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
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.types import StoreConfig

_CONFIG_NAME = ".livespec.jsonc"


def _write_config(*, cwd: Path, body: str) -> None:
    _ = (cwd / _CONFIG_NAME).write_text(body, encoding="utf-8")


def test_resolve_uses_defaults_when_no_config_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    monkeypatch.delenv("LIVESPEC_BD_PATH", raising=False)
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    assert config.tenant == "livespec-impl-beads"
    assert config.prefix == "livespec-impl-beads"
    assert config.database == "livespec-impl-beads"
    assert config.server_user == "livespec-impl-beads"
    assert config.server_host == "127.0.0.1"
    assert config.server_port == 3307
    assert config.socket is None
    assert config.bd_path == "bd"
    assert config.fake is False


def test_work_items_path_property_returns_self(
    tmp_path: Path,
) -> None:
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


def test_prefix_database_user_default_to_tenant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """prefix==database==server_user default to the tenant when unset."""
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    _write_config(
        cwd=tmp_path,
        body='{"livespec-orchestrator-beads-fabro": {"connection": {"tenant": "solo"}}}',
    )
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    assert config.prefix == "solo"
    assert config.database == "solo"
    assert config.server_user == "solo"


def test_env_bd_path_overrides_block(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIVESPEC_BD_PATH", "/managed/bd")
    _write_config(
        cwd=tmp_path,
        body='{"livespec-orchestrator-beads-fabro": {"connection": {"bd_path": "/block/bd"}}}',
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
        body='{"livespec-orchestrator-beads-fabro": {"connection": {"bd_path": "/block/bd"}}}',
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
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    assert config.fake is True


def test_env_fake_falsy_forces_real(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "0")
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    assert config.fake is False


def test_block_fake_used_when_env_unset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    _write_config(
        cwd=tmp_path,
        body='{"livespec-orchestrator-beads-fabro": {"connection": {"fake": true}}}',
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
        body='{"livespec-orchestrator-beads-fabro": {"connection": {"fake": "yes"}}}',
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
        body='{"livespec-orchestrator-beads-fabro": {"connection": {"server_port": "nope"}}}',
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
        body='{"livespec-orchestrator-beads-fabro": {"connection": {"socket": ""}}}',
    )
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    assert config.socket is None


def test_malformed_jsonc_falls_back_to_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    _write_config(cwd=tmp_path, body="{ this is not valid json ")
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    assert config.tenant == "livespec-impl-beads"


def test_non_object_root_falls_back_to_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    _write_config(cwd=tmp_path, body="[1, 2, 3]")
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    assert config.tenant == "livespec-impl-beads"


def test_non_dict_plugin_block_falls_back_to_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    _write_config(cwd=tmp_path, body='{"livespec-orchestrator-beads-fabro": "scalar"}')
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    assert config.tenant == "livespec-impl-beads"


def test_non_dict_connection_block_falls_back_to_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    _write_config(cwd=tmp_path, body='{"livespec-orchestrator-beads-fabro": {"connection": 7}}')
    config = resolve_store_config(cwd=tmp_path, work_items_arg=None)
    assert config.tenant == "livespec-impl-beads"


def test_path_args_are_accepted_and_ignored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The plaintext-signature work_items_arg is a no-op here."""
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    config = resolve_store_config(
        cwd=tmp_path,
        work_items_arg="custom/work.jsonl",
    )
    assert config.tenant == "livespec-impl-beads"


def test_no_password_field_on_descriptor() -> None:
    """The tenant password is NEVER a field on StoreConfig (read from env only)."""
    field_names = {field.name for field in fields(StoreConfig)}
    assert "password" not in field_names
    assert not any("password" in name.lower() for name in field_names)
