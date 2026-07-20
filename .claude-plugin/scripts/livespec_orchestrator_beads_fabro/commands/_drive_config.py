"""Drive actions for API-configurable dispatcher settings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands import _jsonc, _jsonc_splice
from livespec_orchestrator_beads_fabro.commands._drive_config_schema import (
    CONFIG_KEYS,
    ConfigKey,
    api_configurable_key_manifest,
    coerce_config_value,
    config_key_by_name,
    expected_keys,
    parse_config_value,
    value_domain,
)

__all__: list[str] = [
    "is_config_action",
    "run_config_action",
]

_LIVESPEC_CONFIG = ".livespec.jsonc"
_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_DISPATCHER_KEY = "dispatcher"
_CONFIG_READ_ACTION = "config"
_CONFIG_MANIFEST_ACTION = "config-manifest"
_CONFIG_NONWRITE_ACTIONS = frozenset({_CONFIG_READ_ACTION, _CONFIG_MANIFEST_ACTION})
_SET_CONFIG_PREFIX = "set-config:"
_SET_CONFIG_PARTS = 2


def is_config_action(*, action_id: str) -> bool:
    """Return whether the action id belongs to the config surface."""
    return action_id in _CONFIG_NONWRITE_ACTIONS or action_id.startswith(_SET_CONFIG_PREFIX)


def run_config_action(*, repo: Path, action_id: str) -> dict[str, Any]:
    """Run one config read/write/manifest drive action."""
    if action_id == _CONFIG_READ_ACTION:
        return _read_config(repo=repo, action_id=action_id)
    if action_id == _CONFIG_MANIFEST_ACTION:
        return _read_manifest(action_id=action_id)
    return _write_config(repo=repo, action_id=action_id)


def _read_config(*, repo: Path, action_id: str) -> dict[str, Any]:
    dispatcher = _read_dispatcher_for_effective_settings(repo=repo)
    return {
        "action_id": action_id,
        "kind": "config-read",
        "status": "green",
        "settings": [
            _effective_setting(config_key=config_key, dispatcher=dispatcher)
            for config_key in CONFIG_KEYS
        ],
        "summary": "Read effective dispatcher settings.",
    }


def _read_manifest(*, action_id: str) -> dict[str, Any]:
    return {
        "action_id": action_id,
        "kind": "config-manifest",
        "status": "green",
        "manifest": api_configurable_key_manifest(),
        "summary": "Read API-configurable dispatcher key manifest.",
    }


def _write_config(*, repo: Path, action_id: str) -> dict[str, Any]:
    parsed = _parse_set_config_action(action_id=action_id)
    if parsed["status"] == "failed":
        return parsed
    key = str(parsed["key"])
    value = parsed["value"]
    root_result = _read_root_for_write(repo=repo, action_id=action_id)
    if root_result["status"] == "failed":
        return root_result
    root = cast("dict[str, Any]", root_result["root"])
    dispatcher = _dispatcher_block_for_write(root=root)
    if dispatcher is None:
        return _invalid_config_shape(
            action_id=action_id, summary="dispatcher block must be an object."
        )
    dispatcher[key] = value
    _write_root(repo=repo, root=root, key=key, value=value)
    return {
        "action_id": action_id,
        "kind": "config-write",
        "status": "green",
        "key": key,
        "value": value,
        "summary": f"Set dispatcher.{key}.",
    }


def _parse_set_config_action(*, action_id: str) -> dict[str, Any]:
    remainder = action_id.removeprefix(_SET_CONFIG_PREFIX)
    parts = remainder.split(":", 1)
    if len(parts) != _SET_CONFIG_PARTS or parts[0] == "" or parts[1] == "":
        return {
            "action_id": action_id,
            "kind": "config-write",
            "status": "failed",
            "domain_error": "invalid-action-id",
            "summary": "Expected set-config:<key>:<value>.",
        }
    key, raw_value = parts
    config_key = config_key_by_name(key=key)
    if config_key is None:
        return _invalid_key(action_id=action_id, key=key)
    value = parse_config_value(config_key=config_key, raw_value=raw_value)
    if value is None:
        return _invalid_value(action_id=action_id, config_key=config_key)
    return {
        "action_id": action_id,
        "kind": "config-write",
        "status": "green",
        "key": config_key.key,
        "value": value,
    }


def _read_dispatcher_for_effective_settings(*, repo: Path) -> dict[str, Any]:
    config_path = repo / _LIVESPEC_CONFIG
    if not config_path.is_file():
        return {}
    root = _jsonc.parse(text=config_path.read_text(encoding="utf-8"))
    if isinstance(root, _jsonc.JsoncFailure):
        return {}
    if not isinstance(root, dict):
        return {}
    plugin = cast("dict[str, Any]", root).get(_PLUGIN_BLOCK)
    if not isinstance(plugin, dict):
        return {}
    dispatcher = cast("dict[str, Any]", plugin).get(_DISPATCHER_KEY)
    if not isinstance(dispatcher, dict):
        return {}
    return cast("dict[str, Any]", dispatcher)


def _read_root_for_write(*, repo: Path, action_id: str) -> dict[str, Any]:
    config_path = repo / _LIVESPEC_CONFIG
    if not config_path.is_file():
        return {"status": "green", "root": {}}
    root = _jsonc.parse(text=config_path.read_text(encoding="utf-8"))
    if isinstance(root, _jsonc.JsoncFailure):
        return _invalid_config_shape(
            action_id=action_id,
            summary=f"Cannot write config until .livespec.jsonc parses: {root.detail}",
        )
    if not isinstance(root, dict):
        return _invalid_config_shape(
            action_id=action_id, summary=".livespec.jsonc root must be an object."
        )
    return {"status": "green", "root": cast("dict[str, Any]", root)}


def _dispatcher_block_for_write(*, root: dict[str, Any]) -> dict[str, Any] | None:
    plugin = root.get(_PLUGIN_BLOCK)
    if plugin is None:
        plugin = {}
        root[_PLUGIN_BLOCK] = plugin
    if not isinstance(plugin, dict):
        return None
    plugin_dict = cast("dict[str, Any]", plugin)
    dispatcher = plugin_dict.get(_DISPATCHER_KEY)
    if dispatcher is None:
        dispatcher = {}
        plugin_dict[_DISPATCHER_KEY] = dispatcher
    if not isinstance(dispatcher, dict):
        return None
    return cast("dict[str, Any]", dispatcher)


def _effective_setting(*, config_key: ConfigKey, dispatcher: dict[str, Any]) -> dict[str, Any]:
    raw = dispatcher.get(config_key.key)
    value = coerce_config_value(config_key=config_key, raw_value=raw)
    if value is None:
        return {"key": config_key.key, "value": config_key.default, "source": "default"}
    return {"key": config_key.key, "value": value, "source": "explicit"}


def _invalid_key(*, action_id: str, key: str) -> dict[str, Any]:
    return {
        "action_id": action_id,
        "kind": "config-write",
        "status": "failed",
        "domain_error": "invalid-config-key",
        "summary": f"Unsupported config key {key!r}. Expected one of: {expected_keys()}.",
    }


def _invalid_value(*, action_id: str, config_key: ConfigKey) -> dict[str, Any]:
    summary = f"Invalid value for {config_key.key}; expected {value_domain(config_key=config_key)}."
    return {
        "action_id": action_id,
        "kind": "config-write",
        "status": "failed",
        "domain_error": "invalid-config-value",
        "summary": summary,
    }


def _invalid_config_shape(*, action_id: str, summary: str) -> dict[str, Any]:
    return {
        "action_id": action_id,
        "kind": "config-write",
        "status": "failed",
        "domain_error": "invalid-config-shape",
        "summary": summary,
    }


def _write_root(*, repo: Path, root: dict[str, Any], key: str, value: Any) -> None:
    config_path = repo / _LIVESPEC_CONFIG
    if not config_path.is_file():
        _ = config_path.write_text(json.dumps(root, indent=2) + "\n", encoding="utf-8")
        return
    text = config_path.read_text(encoding="utf-8")
    updated = _jsonc_splice.set_path(
        text=text,
        path=(_PLUGIN_BLOCK, _DISPATCHER_KEY, key),
        value=value,
    )
    _ = config_path.write_text(updated, encoding="utf-8")
