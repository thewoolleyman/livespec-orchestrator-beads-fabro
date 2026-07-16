"""Schema and manifest data for drive's API-configurable settings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__: list[str] = [
    "CONFIG_KEYS",
    "ConfigKey",
    "api_configurable_key_manifest",
    "coerce_config_value",
    "config_key_by_name",
    "expected_keys",
    "parse_config_value",
    "value_domain",
]

_ACCEPTANCE_MODES = ("ai-only", "ai-then-human", "human-only")


@dataclass(frozen=True, kw_only=True)
class ConfigKey:
    key: str
    value_type: str
    default: bool | int | str
    per_item_override: bool
    values: tuple[str, ...] = ()


CONFIG_KEYS: tuple[ConfigKey, ...] = (
    ConfigKey(
        key="auto_approve_ready",
        value_type="boolean",
        default=False,
        per_item_override=True,
    ),
    ConfigKey(
        key="merge_on_review_cap",
        value_type="boolean",
        default=False,
        per_item_override=True,
    ),
    ConfigKey(
        key="acceptance_mode",
        value_type="enum",
        default="ai-then-human",
        values=_ACCEPTANCE_MODES,
        per_item_override=True,
    ),
    ConfigKey(
        key="review_fix_cap",
        value_type="positive_integer",
        default=3,
        per_item_override=True,
    ),
    ConfigKey(
        key="acceptance_rework_cap",
        value_type="positive_integer",
        default=2,
        per_item_override=True,
    ),
    ConfigKey(
        key="wip_cap",
        value_type="positive_integer",
        default=5,
        per_item_override=False,
    ),
)


def api_configurable_key_manifest() -> dict[str, Any]:
    """Return the declared machine-readable API-configurable key manifest."""
    return {
        "surface": "livespec-orchestrator-beads-fabro.dispatcher",
        "keys": [_manifest_entry(config_key=config_key) for config_key in CONFIG_KEYS],
    }


def config_key_by_name(*, key: str) -> ConfigKey | None:
    for config_key in CONFIG_KEYS:
        if config_key.key == key:
            return config_key
    return None


def coerce_config_value(*, config_key: ConfigKey, raw_value: object) -> bool | int | str | None:
    if config_key.value_type == "boolean" and isinstance(raw_value, bool):
        return raw_value
    if config_key.value_type == "positive_integer":
        if isinstance(raw_value, int) and not isinstance(raw_value, bool) and raw_value > 0:
            return raw_value
        return None
    if (
        config_key.value_type == "enum"
        and isinstance(raw_value, str)
        and raw_value in config_key.values
    ):
        return raw_value
    return None


def parse_config_value(*, config_key: ConfigKey, raw_value: str) -> bool | int | str | None:
    if config_key.value_type == "boolean":
        return _parse_bool_value(raw_value=raw_value)
    if config_key.value_type == "positive_integer":
        return _parse_positive_int_value(raw_value=raw_value)
    if raw_value in config_key.values:
        return raw_value
    return None


def expected_keys() -> str:
    return ", ".join(config_key.key for config_key in CONFIG_KEYS)


def value_domain(*, config_key: ConfigKey) -> str:
    if config_key.value_type == "boolean":
        return "true or false"
    if config_key.value_type == "positive_integer":
        return "a positive integer"
    return "one of " + ", ".join(config_key.values)


def _parse_bool_value(*, raw_value: str) -> bool | None:
    if raw_value == "true":
        return True
    if raw_value == "false":
        return False
    return None


def _parse_positive_int_value(*, raw_value: str) -> int | None:
    if not raw_value.isdecimal():
        return None
    parsed = int(raw_value)
    if parsed > 0:
        return parsed
    return None


def _manifest_entry(*, config_key: ConfigKey) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "key": config_key.key,
        "type": config_key.value_type,
        "default": config_key.default,
        "per_item_override": config_key.per_item_override,
    }
    if config_key.values:
        entry["values"] = list(config_key.values)
    return entry
