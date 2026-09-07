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
from livespec_orchestrator_beads_fabro.commands._otel_enrich import enrich_span
from livespec_orchestrator_beads_fabro.commands._otel_scrub import (
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


def test_o4_run_turn_attrs_are_allowlisted() -> None:
    # O4 (bd-ib-98c.7) emits a fabro-side `run_turn` SPAN carrying these
    # per-ACP-turn scalars. Span attributes (unlike span EVENTS, which bypass
    # this allowlist) are filtered by the fail-closed enrich stage, so without
    # these entries the span lands in Honeycomb with every O4 field silently
    # DROPPED — proven live on 2026-07-19: 6 run_turn spans arrived carrying
    # none of them. All are non-secret scalars: an ACP argv-only command
    # string, an operator-set config name, a visit counter, a bounded
    # stop-reason enum, and the node id.
    for key in ("command", "config_name", "visit", "stop_reason", "node_id"):
        assert key in ATTRIBUTE_ALLOWLIST
        assert is_allowed_attr(key=key) is True


def test_review_gate_keys_survive_enrich_while_prompt_io_drops() -> None:
    span: dict[str, object] = {
        "name": "review-gate",
        "attributes": [
            {"key": "review.verdict", "value": {"stringValue": "approve"}},
            {"key": "review.fix_rounds", "value": {"intValue": "2"}},
            {"key": "review.hit_cap", "value": {"boolValue": True}},
            {"key": "pr.shipped_on_cap", "value": {"boolValue": True}},
            {"key": "agent.acp.completed.stdout", "value": {"stringValue": "prompt text"}},
        ],
    }

    enriched = enrich_span(span=span, triple={"work.item.id": "bd-1"})

    assert enriched is not None
    keys = {
        entry["key"]
        for entry in enriched["attributes"]
        if isinstance(entry, dict) and isinstance(entry.get("key"), str)
    }
    assert {
        "review.verdict",
        "review.fix_rounds",
        "review.hit_cap",
        "pr.shipped_on_cap",
        "work.item.id",
    } <= keys
    assert "agent.acp.completed.stdout" not in keys


def test_fabro_failure_keys_survive_enrich_with_existing_attr_cap() -> None:
    for key in (
        "fabro.failure.cause",
        "fabro.failure.category",
        "fabro.failure.signature",
    ):
        assert key in ATTRIBUTE_ALLOWLIST
        assert is_allowed_attr(key=key) is True
    long_cause = "script failed " + ("x" * (ATTR_MAX_LEN + 50))
    span: dict[str, object] = {
        "name": "livespec.dispatch.calibration",
        "attributes": [
            {"key": "fabro.failure.cause", "value": {"stringValue": long_cause}},
            {"key": "fabro.failure.category", "value": {"stringValue": "deterministic"}},
            {
                "key": "fabro.failure.signature",
                "value": {"stringValue": "fix|deterministic|script failed"},
            },
            {"key": "agent.acp.completed.stderr", "value": {"stringValue": "ACP turn failed"}},
        ],
    }

    enriched = enrich_span(span=span, triple={"work.item.id": "bd-1"})

    assert enriched is not None
    attrs = {
        str(entry["key"]): entry["value"]
        for entry in enriched["attributes"]
        if isinstance(entry, dict) and isinstance(entry.get("key"), str)
    }
    assert "agent.acp.completed.stderr" not in attrs
    cause_value = attrs["fabro.failure.cause"]
    assert isinstance(cause_value, dict)
    assert cause_value["stringValue"] == long_cause[:ATTR_MAX_LEN]
    assert attrs["fabro.failure.category"] == {"stringValue": "deterministic"}
    assert attrs["fabro.failure.signature"] == {"stringValue": "fix|deterministic|script failed"}


@given(value=st.text(alphabet=st.characters(blacklist_characters="@"), max_size=400))
def test_scrub_at_credential_free_value_never_exceeds_max_len(*, value: str) -> None:
    # A value with no '@' cannot match the credential-URL shape, so scrub
    # passes it through, only ever truncated to ATTR_MAX_LEN (property).
    scrubbed = scrub(value=value)
    assert len(scrubbed) <= ATTR_MAX_LEN
    assert scrubbed == value[:ATTR_MAX_LEN]


def test_factory_build_phase_attrs_are_allowlisted() -> None:
    """The fabro-sandbox cargo shim's build-telemetry scheme keys reach Honeycomb.

    Measured before this test existed: `repo` + `git.commit.sha` arrived while
    `build.env` / `build.phase` were dropped by this allowlist, so the console's
    factory baselines had to be queried by span NAME (console item -elt9).
    """
    for key in (
        "build.env",
        "build.phase",
        "toolchain.version",
        "cargo.subcommand",
        "work_item_id",
        "build.cache.tier",
        "build.cache.hit",
    ):
        assert key in ATTRIBUTE_ALLOWLIST
        assert is_allowed_attr(key=key) is True


def test_factory_sccache_and_registry_cache_attrs_are_allowlisted() -> None:
    """The sccache shim's per-cache-tier scalars reach Honeycomb.

    44ca04f5 widened this allowlist to `build.cache.tier` + `build.cache.hit`
    ONLY, so every attribute the livespec-dev-tooling sccache shim attaches to
    a `build.cargo-*` span was scrubbed on receipt and the factory span arrived
    bare. All are bounded bool / count / ratio / enum scalars, scrub-safe.
    """
    for key in (
        "build.cache.sccache.enabled",
        "build.cache.sccache.hits",
        "build.cache.sccache.misses",
        "build.cache.sccache.errors",
        "build.cache.sccache.hit_ratio",
        "build.cache.sccache.backend",
        "build.cache.sccache.rw_mode",
        "build.cache.registry.hit",
    ):
        assert key in ATTRIBUTE_ALLOWLIST
        assert is_allowed_attr(key=key) is True
    # Still an allowlist, never a `build.cache.sccache.*` prefix match.
    assert "build.cache.sccache.unknown" not in ATTRIBUTE_ALLOWLIST
    assert is_allowed_attr(key="build.cache.sccache.unknown") is False
