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
_GROOM_CUT_APPROVALS = ("human", "consensus")


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
    # The two settings v100 ratified with the consensus-gated automated groom
    # cut. Both are API-configurable like every other policy setting, and both
    # are INERT until the groom door and the groom workflow variant that read
    # them land. `groom_cut_approval` carries a per-item override that may only
    # LOWER an item to `human` — the manifest records that an override EXISTS,
    # not which direction it may move, and `effective_groom_cut_approval` is
    # where the asymmetry is enforced.
    ConfigKey(
        key="groom_cut_approval",
        value_type="enum",
        default="human",
        values=_GROOM_CUT_APPROVALS,
        per_item_override=True,
    ),
    ConfigKey(
        key="automated_regroom_cap",
        value_type="positive_integer",
        default=2,
        per_item_override=True,
    ),
    ConfigKey(
        key="ready_aging_threshold_hours",
        value_type="positive_integer",
        default=24,
        per_item_override=False,
    ),
    ConfigKey(
        key="wip_cap",
        value_type="non_negative_integer",
        default=5,
        per_item_override=False,
    ),
    # Detection recency is a repository property, so the drift trigger carries
    # no per-item override (the detection coverage-record contract).
    ConfigKey(
        key="drift_capture_merge_threshold",
        value_type="positive_integer",
        default=1,
        per_item_override=False,
    ),
    # The open drift-origin proposal queue is likewise a repository property:
    # every proposal costs a human review whichever merge occasioned it, so
    # this cap carries no per-item override either.
    ConfigKey(
        key="drift_proposal_queue_cap",
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
    if config_key.value_type in ("positive_integer", "non_negative_integer"):
        return _coerce_int_value(config_key=config_key, raw_value=raw_value)
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
    if config_key.value_type == "non_negative_integer":
        return _parse_non_negative_int_value(raw_value=raw_value)
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
    if config_key.value_type == "non_negative_integer":
        return "a non-negative integer"
    return "one of " + ", ".join(config_key.values)


def _coerce_int_value(*, config_key: ConfigKey, raw_value: object) -> int | None:
    if not isinstance(raw_value, int) or isinstance(raw_value, bool):
        return None
    if config_key.value_type == "positive_integer" and raw_value > 0:
        return raw_value
    if config_key.value_type == "non_negative_integer" and raw_value >= 0:
        return raw_value
    return None


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


def _parse_non_negative_int_value(*, raw_value: str) -> int | None:
    if not raw_value.isdecimal():
        return None
    return int(raw_value)


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
