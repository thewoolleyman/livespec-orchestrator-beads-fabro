"""Tests for extracting Claude cache-write lifetimes from API usage."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._claude_cache_lifetimes import (
    cache_write_lifetimes,
)


def test_usage_with_both_cache_write_lifetimes_keeps_each_count() -> None:
    usage = {
        "cache_creation": {
            "ephemeral_5m_input_tokens": 125,
            "ephemeral_1h_input_tokens": 40,
        }
    }

    assert cache_write_lifetimes(usage=usage) == {
        "cache_creation_5m_tokens": 125,
        "cache_creation_1h_tokens": 40,
    }
