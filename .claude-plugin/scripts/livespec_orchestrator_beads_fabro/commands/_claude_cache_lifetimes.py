"""Extract the measured Claude cache-write lifetime counts from response usage."""

from __future__ import annotations

from typing import cast

__all__: list[str] = ["cache_write_lifetimes"]

_LIFETIME_KEYS: tuple[tuple[str, str], ...] = (
    ("ephemeral_5m_input_tokens", "cache_creation_5m_tokens"),
    ("ephemeral_1h_input_tokens", "cache_creation_1h_tokens"),
)


def cache_write_lifetimes(*, usage: object) -> dict[str, int]:
    """Return every present, non-negative lifetime count from an API response."""
    if not isinstance(usage, dict):
        return {}
    cache_creation = cast("dict[str, object]", usage).get("cache_creation")
    if not isinstance(cache_creation, dict):
        return {}
    values = cast("dict[str, object]", cache_creation)
    return {
        output_key: raw_value
        for input_key, output_key in _LIFETIME_KEYS
        if isinstance(raw_value := values.get(input_key), int)
        and not isinstance(raw_value, bool)
        and raw_value >= 0
    }
