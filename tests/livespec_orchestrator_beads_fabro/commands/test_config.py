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

import json
from collections.abc import Callable
from dataclasses import fields
from inspect import signature
from pathlib import Path
from typing import TypeVar

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _config,
    _dispatcher_overlay,
    _dispatcher_plugin_cache_gate,
)
from livespec_orchestrator_beads_fabro.commands._config import (
    resolve_credential_wrapper,
    resolve_fabro_bin,
    resolve_store_config,
)
from livespec_orchestrator_beads_fabro.errors import (
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig
from returns.io import IOFailure, IOResult
from returns.unsafe import unsafe_perform_io

_Value = TypeVar("_Value")


def _read(outcome: IOResult[_Value, object]) -> _Value:
    """The value out of a config read that SUCCEEDED.

    ⚠️ `unsafe_perform_io` is mandatory rather than decorative: `IOResult.unwrap`
    yields `IO[value]`, not the value, so a bare `.unwrap()` compares an `IO`
    wrapper against the expected string and is false for every input.
    """
    return unsafe_perform_io(outcome.unwrap())


_CONFIG_NAME = ".livespec.jsonc"
_GITHUB_APP_ENV_KEYS = (
    "GITHUB_APP_ID",
    "GITHUB_PRIVATE_KEY",
    "GITHUB_APP_INSTALLATION_ID",
    "GITHUB_API_URL",
)


@pytest.fixture(autouse=True)
def _clear_github_app_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep overlay assertions independent from factory credential injection."""
    for key in _GITHUB_APP_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


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


def test_malformed_jsonc_names_the_parse_failure_not_a_missing_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A file that will not parse refuses by NAMING that, not the prefix.

    It used to raise `ConnectionPrefixMissingError` — a true refusal naming the
    wrong cause, sending an operator to look at a `connection.prefix` that was
    sitting there correctly all along.
    """
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    _write_config(cwd=tmp_path, body="{ this is not valid json ")

    with pytest.raises(LivespecConfigUnreadableError) as raised:
        _ = resolve_store_config(cwd=tmp_path, work_items_arg=None)

    assert "does not parse" in raised.value.detail
    assert not isinstance(raised.value, ConnectionPrefixMissingError)


def test_non_object_root_names_the_shape_not_a_missing_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-object JSON root refuses by naming the root, not the prefix."""
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    _write_config(cwd=tmp_path, body="[1, 2, 3]")

    with pytest.raises(LivespecConfigUnreadableError) as raised:
        _ = resolve_store_config(cwd=tmp_path, work_items_arg=None)

    assert "root is not an object" in raised.value.detail


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(
            lambda cwd: _config.has_fabro_factory(cwd=cwd, factory="default"),
            id="has_fabro_factory",
        ),
        pytest.param(lambda cwd: _config.has_fabro_factories(cwd=cwd), id="has_fabro_factories"),
        pytest.param(
            lambda cwd: _config.resolve_fabro_factory(cwd=cwd), id="resolve_fabro_factory"
        ),
        pytest.param(
            lambda cwd: _config.resolve_codex_model_tiers(cwd=cwd), id="resolve_codex_model_tiers"
        ),
    ],
)
def test_dispatcher_readers_refuse_an_unreadable_config_rather_than_reading_it_as_unset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    call: Callable[[Path], object],
) -> None:
    """An unreadable config is NOT "nothing is configured", for every dispatcher reader.

    ⛔ THE REGRESSION THIS PINS. These four readers were added while the
    read-vs-write swallow fix sat unlanded, and each re-committed it: they called
    the block reader and treated a parse failure as an absent `factories` key, so
    `has_fabro_factory` answered a confident `False` for a config with a stray
    comma in it. Every one of them now refuses by naming the real cause.
    """
    monkeypatch.delenv("LIVESPEC_BEADS_FAKE", raising=False)
    _write_config(cwd=tmp_path, body="{ this is not valid json ")

    with pytest.raises(LivespecConfigUnreadableError) as raised:
        _ = call(tmp_path)

    assert "does not parse" in raised.value.detail


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


_CONFIG_SHUTIL_WHICH = "livespec_orchestrator_beads_fabro.commands._fabro_bin.shutil.which"


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


def test_resolve_fabro_factory_uses_env_selected_config_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-empty `LIVESPEC_FABRO_FACTORY` selects that named factory outright."""
    assert hasattr(_config, "resolve_fabro_factory")
    monkeypatch.setenv("LIVESPEC_FABRO_FACTORY", "remote")
    monkeypatch.setenv("FABRO_DEV_TOKEN__remote", "remote-token")
    _write_config(
        cwd=tmp_path,
        body=json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {
                        "default_factory": "local",
                        "factories": {
                            "local": {"server": "http://127.0.0.1:32276"},
                            "remote": {"server": "https://factory.example.test"},
                        },
                    }
                }
            }
        ),
    )
    target = _config.resolve_fabro_factory(cwd=tmp_path)
    assert target.name == "remote"
    assert target.server == "https://factory.example.test"
    assert target.dev_token == "remote-token"


def test_resolve_fabro_factory_uses_configured_default_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no env override, `dispatcher.default_factory` selects a configured entry."""
    monkeypatch.delenv("LIVESPEC_FABRO_FACTORY", raising=False)
    monkeypatch.setenv("FABRO_DEV_TOKEN__west", "west-token")
    _write_config(
        cwd=tmp_path,
        body=json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {
                        "default_factory": "west",
                        "factories": {
                            "west": {"server": "https://west.example.test"},
                        },
                    }
                }
            }
        ),
    )
    target = _config.resolve_fabro_factory(cwd=tmp_path)
    assert target.name == "west"
    assert target.server == "https://west.example.test"
    assert target.dev_token == "west-token"


def test_resolve_fabro_factory_defaults_to_configured_default_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without `default_factory`, a `factories.default` entry is used when present."""
    monkeypatch.delenv("LIVESPEC_FABRO_FACTORY", raising=False)
    _write_config(
        cwd=tmp_path,
        body=json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {
                        "factories": {
                            "default": {"server": "https://default.example.test"},
                        },
                    }
                }
            }
        ),
    )
    target = _config.resolve_fabro_factory(cwd=tmp_path)
    assert target.name == "default"
    assert target.server == "https://default.example.test"
    assert target.dev_token is None


def test_committed_config_sets_hp_default_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """This repo's committed config selects the hp Fabro host by default."""
    monkeypatch.delenv("LIVESPEC_FABRO_FACTORY", raising=False)
    monkeypatch.delenv("FABRO_DEV_TOKEN__hp", raising=False)
    repo_root = Path(__file__).parents[3]
    target = _config.resolve_fabro_factory(cwd=repo_root)
    assert target.name == "hp"
    assert target.server == "https://hp-xubuntu.perch-rudd.ts.net:32276"
    assert target.dev_token is None


def test_resolve_fabro_factory_implicit_default_preserves_loopback_behavior(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No env or configured entry yields the implicit single default factory."""
    monkeypatch.delenv("LIVESPEC_FABRO_FACTORY", raising=False)
    target = _config.resolve_fabro_factory(cwd=tmp_path)
    assert target.name == "default"
    assert target.server is None
    assert target.dev_token is None


def test_resolve_fabro_factory_empty_env_falls_through_to_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty env override is ignored, matching the existing Fabro-bin pattern."""
    monkeypatch.setenv("LIVESPEC_FABRO_FACTORY", "")
    _write_config(
        cwd=tmp_path,
        body=json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {
                        "default_factory": "east",
                        "factories": {"east": {"server": "https://east.example.test"}},
                    }
                }
            }
        ),
    )
    target = _config.resolve_fabro_factory(cwd=tmp_path)
    assert target.name == "east"
    assert target.server == "https://east.example.test"


def test_resolve_fabro_factory_env_unknown_does_not_fall_back_to_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An env-selected missing factory still wins over the configured default."""
    monkeypatch.setenv("LIVESPEC_FABRO_FACTORY", "adhoc")
    _write_config(
        cwd=tmp_path,
        body=json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {
                        "default_factory": "remote",
                        "factories": {"remote": {"server": "https://remote.example.test"}},
                    }
                }
            }
        ),
    )
    target = _config.resolve_fabro_factory(cwd=tmp_path)
    assert target.name == "adhoc"
    assert target.server is None


_WORKFLOW_WITH_IMAGE = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    "[run.environment]\n"
    'id = "livespec-ci"\n'
    "\n"
    "[environments.livespec-ci]\n"
    'provider = "docker"\n'
    "\n"
    "[environments.livespec-ci.image]\n"
    'docker = "ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-agent-v1.0.0"\n'
    "\n"
    "[[run.prepare.steps]]\n"
    'script = "just bootstrap"\n'
)

_IMAGE_OVERRIDE = "ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-rust-agent-v9.9.9"
_FAKE_TOKEN = "test-oauth-token"
_FAKE_GITHUB_TOKEN = "test-github-token"


def test_render_run_config_overlay_accepts_a_sandbox_image_override(tmp_path: Path) -> None:
    """Image override rewrites only the image table; graph remains workflow-local."""
    assert (
        "fabro_sandbox_image" in signature(_dispatcher_overlay.render_run_config_overlay).parameters
    )
    rendered = _dispatcher_overlay.render_run_config_overlay(
        committed_text=_WORKFLOW_WITH_IMAGE,
        workflow_dir=tmp_path / "plugin-workflow",
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        fabro_sandbox_image=_IMAGE_OVERRIDE,
    )
    assert rendered is not None
    pre_env_table = rendered.split("[environments.livespec-ci.env]", 1)[0]
    assert f'graph = "{tmp_path / "plugin-workflow" / "workflow.fabro"}"' in pre_env_table
    assert f'docker = "{_IMAGE_OVERRIDE}"' in pre_env_table
    assert "python-agent-v1.0.0" not in pre_env_table


def test_render_run_config_overlay_without_sandbox_image_override_is_byte_identical(
    tmp_path: Path,
) -> None:
    """Omitting the image override preserves the exact existing overlay bytes."""
    rendered = _dispatcher_overlay.render_run_config_overlay(
        committed_text=_WORKFLOW_WITH_IMAGE,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
    )
    expected = (
        _WORKFLOW_WITH_IMAGE.replace(
            'graph = "workflow.fabro"', f'graph = "{tmp_path / "workflow.fabro"}"'
        )
        + "\n# --- Dispatcher-materialized sandbox-local tmux socket root ---\n"
        + "[[run.prepare.steps]]\n"
        + 'script = "mkdir -p /workspace/.tmux && chmod 700 /workspace/.tmux"\n'
        # Rendered from the gate module rather than restated: the script is the
        # gate's own text, and a second copy here would diverge silently.
        + _dispatcher_plugin_cache_gate.plugin_cache_gate_prepare_steps_block()
        + "\n# --- Dispatcher-materialized run-scoped credential projection"
        + "\n# --- (UNCOMMITTED; mode 600; deleted when the run returns) ---\n"
        + "[environments.livespec-ci.env]\n"
        + 'CLAUDE_CODE_OAUTH_TOKEN = "test-oauth-token"\n'
        + 'GITHUB_TOKEN = "test-github-token"\n'
        + 'TMUX_TMPDIR = "/workspace/.tmux"\n'
        + 'LIVESPEC_CURRENCY_GATE = "fail"\n'
    )
    assert rendered == expected


def test_render_run_config_overlay_image_override_is_scope_fenced(tmp_path: Path) -> None:
    """The override value is TOML-quoted and cannot reach graph, env id, or steps."""
    assert (
        "fabro_sandbox_image" in signature(_dispatcher_overlay.render_run_config_overlay).parameters
    )
    hostile = (
        'ghcr.io/example/custom:tag"\n'
        'graph = "other.fabro"\n'
        'id = "other-env"\n'
        'script = "curl example.test"'
    )
    rendered = _dispatcher_overlay.render_run_config_overlay(
        committed_text=_WORKFLOW_WITH_IMAGE,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        fabro_sandbox_image=hostile,
    )
    assert rendered is not None
    pre_env_table = rendered.split("[environments.livespec-ci.env]", 1)[0]
    assert f'graph = "{tmp_path / "workflow.fabro"}"' in pre_env_table
    assert "[environments.livespec-ci.env]" in rendered
    assert "[environments.other-env.env]" not in rendered
    assert rendered.count("[[run.prepare.steps]]") == 3
    assert 'script = "just bootstrap"' in rendered
    assert 'script = "curl example.test"' not in rendered
    assert "other.fabro" in pre_env_table
    assert 'graph = "other.fabro"' not in pre_env_table


def test_resolve_fabro_sandbox_image_uses_dispatcher_config_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no env override, `dispatcher.fabro_sandbox_image` is used."""
    monkeypatch.delenv("LIVESPEC_FABRO_SANDBOX_IMAGE", raising=False)
    configured = "ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-rust-agent-v9.9.9"
    _write_config(
        cwd=tmp_path,
        body=json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {"fabro_sandbox_image": configured}
                }
            }
        ),
    )
    assert _read(_config.resolve_fabro_sandbox_image(cwd=tmp_path)) == configured


def test_env_fabro_sandbox_image_beats_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-empty `LIVESPEC_FABRO_SANDBOX_IMAGE` wins over the config key."""
    configured = "ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-agent-v1.0.0"
    env_value = "ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-rust-agent-v9.9.9"
    monkeypatch.setenv("LIVESPEC_FABRO_SANDBOX_IMAGE", env_value)
    _write_config(
        cwd=tmp_path,
        body=json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {"fabro_sandbox_image": configured}
                }
            }
        ),
    )
    assert _read(_config.resolve_fabro_sandbox_image(cwd=tmp_path)) == env_value


def test_resolve_fabro_sandbox_image_unset_is_noop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No env or config value yields None, leaving the committed workflow unchanged."""
    monkeypatch.delenv("LIVESPEC_FABRO_SANDBOX_IMAGE", raising=False)
    assert _read(_config.resolve_fabro_sandbox_image(cwd=tmp_path)) is None


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
    assert _read(resolve_credential_wrapper(cwd=tmp_path)) == [
        "/usr/local/bin/with-livespec-env.sh",
        "--",
        "7",
    ]


def test_resolve_credential_wrapper_non_list_yields_empty(
    tmp_path: Path,
) -> None:
    """A non-list `credential_wrapper` value is an ANSWER: no wrapper configured."""
    _write_config(
        cwd=tmp_path,
        body='{"credential_wrapper": "not-a-list"}',
    )
    assert _read(resolve_credential_wrapper(cwd=tmp_path)) == []


def test_resolve_credential_wrapper_absent_file_yields_empty(
    tmp_path: Path,
) -> None:
    """No `.livespec.jsonc` at all is an ANSWER: this repo configures no wrapper."""
    assert _read(resolve_credential_wrapper(cwd=tmp_path)) == []


def test_resolve_credential_wrapper_unreadable_config_is_not_no_wrapper(
    tmp_path: Path,
) -> None:
    """An UNREADABLE config takes the FAILURE track, not the empty-argv answer.

    ⛔ THE DEFECT THIS PINS, and it is the most consequential half of `8o8e.21`.
    The sole consumer is the pre-push `check-ledger-conformance-live` gate, which
    SKIPS when no wrapper resolves. While this folded an unparseable file into
    `[]`, a stray comma in `.livespec.jsonc` silently TURNED THAT GATE OFF and
    reported it in the same words as a repo that never configured one.

    ⚠️ The consumer still skips either way — that recipe runs on every push and a
    false-fail would brick them all. What changes is that it can now SAY WHICH.
    """
    _write_config(cwd=tmp_path, body="{ this is not valid json ")

    outcome = resolve_credential_wrapper(cwd=tmp_path)

    assert isinstance(outcome, IOFailure)
    assert "does not parse" in unsafe_perform_io(outcome.failure()).detail
