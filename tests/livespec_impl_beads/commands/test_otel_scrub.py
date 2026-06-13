"""Tests for the shared fail-closed scrub + OTLP attribute discipline.

Covers `_otel_scrub` — the single source of truth (29f E1) lifted out of
`_dispatcher_reflection`. The load-bearing invariants under test
(telemetry-pipeline-architecture.md §3.4): allowlist-not-denylist
(`is_allowed_attr`), fail-CLOSED reject-not-redact on a credential shape
(`scrub`), the bool-before-int OTLP coercion (`attr`), and the efj-rider
membership of `cost_usd` + the token-count scalars in `ATTRIBUTE_ALLOWLIST`.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st
from livespec_impl_beads.commands._otel_scrub import (
    ATTR_MAX_LEN,
    ATTRIBUTE_ALLOWLIST,
    REDACTION_MARKER,
    attr,
    is_allowed_attr,
    scrub,
)


def test_scrub_rejects_credential_shaped_url_wholesale() -> None:
    redacted = scrub(value="https://x-access-token:ghp_secretsecret@github.com/org/repo")
    assert redacted == REDACTION_MARKER


def test_scrub_passes_and_truncates_plain_value() -> None:
    assert scrub(value="plain") == "plain"
    long_value = "x" * (ATTR_MAX_LEN + 50)
    assert len(scrub(value=long_value)) == ATTR_MAX_LEN


def test_attr_builds_typed_otlp_values_bool_before_int() -> None:
    # bool is an int subclass — it MUST map to boolValue, never intValue.
    assert attr(key="k", value=True) == {"key": "k", "value": {"boolValue": True}}
    assert attr(key="k", value=5) == {"key": "k", "value": {"intValue": "5"}}
    assert attr(key="k", value="s") == {"key": "k", "value": {"stringValue": "s"}}


def test_attr_scrubs_string_values() -> None:
    built = attr(key="k", value="scheme://u:p@host")
    assert built == {"key": "k", "value": {"stringValue": REDACTION_MARKER}}


def test_is_allowed_attr_allowlist_not_denylist() -> None:
    assert is_allowed_attr(key="work.item.id") is True
    # An arbitrary unnamed key is NOT forwarded — allowlist, never denylist.
    assert is_allowed_attr(key="agent.acp.completed.stdout") is False
    assert is_allowed_attr(key="OTEL_EXPORTER_OTLP_HEADERS") is False


def test_efj_rider_cost_and_token_scalars_are_allowlisted() -> None:
    # The efj spend-cap reads CC-native cost_usd + token counts THROUGH this
    # pipeline (user-ratified 2026-06-13 rider) — they must survive scrub.
    for key in (
        "cost_usd",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
    ):
        assert key in ATTRIBUTE_ALLOWLIST
        assert is_allowed_attr(key=key) is True


def test_correlation_triple_is_allowlisted() -> None:
    for key in ("work.item.id", "livespec.dispatch.id", "fabro.run_id"):
        assert is_allowed_attr(key=key) is True


@given(value=st.text(alphabet=st.characters(blacklist_characters="@"), max_size=400))
def test_scrub_at_credential_free_value_never_exceeds_max_len(*, value: str) -> None:
    # A value with no '@' cannot match the credential-URL shape, so scrub
    # passes it through, only ever truncated to ATTR_MAX_LEN (property).
    scrubbed = scrub(value=value)
    assert len(scrubbed) <= ATTR_MAX_LEN
    assert scrubbed == value[:ATTR_MAX_LEN]
