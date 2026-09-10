"""The CLOSED candidate grammar an ACP node's fallback chain is spelled in.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP
fallback priority": the candidate identity triple, the complete fallback
entry, the availability-signature discriminator rule, the all-or-none
pricing table, and every refusal that must fire BEFORE a claim or a run.

WHAT MAKES EACH ASSERTION LOAD-BEARING HERE is that the refusals are
NEGATIVE claims, and a negative claim needs its positive control beside
it: every "this shape refuses" test is paired with the nearly-identical
shape that must be ACCEPTED, so a parser that refused everything would
fail just as loudly as one that accepted everything. The pairs are
deliberately one edit apart -- a key added, a type changed, a literal
blanked -- because that is the distance a real misconfiguration is from a
correct one.

Everything is HERMETIC: these are dictionaries in, dataclasses or refusal
strings out. Nothing launches an adapter or reaches a provider.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_IDENTITY: dict[str, Any] = {
    "display_name": "Claude Haiku 4.5",
    "candidate_key": "claude-haiku-4-5",
    "availability_key": "anthropic",
}
_PRICING: dict[str, Any] = {
    "model": "claude-haiku-4-5",
    "input_usd_per_million": 1.0,
    "output_usd_per_million": 5,
    "cache_write_usd_per_million": 1.25,
    "cache_read_usd_per_million": 0.1,
}
_MACHINE_SIGNATURE: dict[str, Any] = {
    "source": "protocol.machine_code",
    "machine_code": "model.unsupported",
    "cause": "model_unsupported",
    "scope": "candidate",
}
_MESSAGE_SIGNATURE: dict[str, Any] = {
    "source": "protocol.message",
    "all_literals": ["usage limit", "requested model"],
    "exit_code": 1,
    "cause": "quota",
    "scope": "availability-domain",
    "hold_key": "chatgpt-account",
}


def _module(*, name: str) -> Any:
    """Import one of the candidate-grammar modules, proving it exists first.

    The `is_file` assertion runs FIRST on purpose: it fails as a genuine
    assertion before the import can fail as a collection error, which is
    what keeps the Red honest.
    """
    assert (_COMMANDS / f"{name}.py").is_file(), f"{name} module is not implemented"
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _fields() -> Any:
    return _module(name="_acp_schema_fields")


def _secrets() -> Any:
    return _module(name="_acp_candidate_secrets")


def _signatures() -> Any:
    return _module(name="_acp_candidate_signatures")


def _pricing() -> Any:
    return _module(name="_acp_candidate_pricing")


def _schema() -> Any:
    return _module(name="_acp_candidate_schema")


def _chains() -> Any:
    return _module(name="_acp_node_chains")


def _candidate(**overrides: Any) -> dict[str, Any]:
    """A COMPLETE fallback candidate table, with the named fields replaced."""
    return {**_IDENTITY, "command": "uvx claude-acp", **overrides}


def _fallback_node(**overrides: Any) -> dict[str, Any]:
    """A node entry declaring one complete fallback."""
    return {"fallbacks": [_candidate(**overrides)]}


def test_the_field_readers_accept_their_own_type_and_nothing_else() -> None:
    """Every primitive reader answers `None` for a value it cannot read.

    These are the shared readers behind every refusal message in this
    file, so their negatives are asserted once here rather than
    re-derived through each parser that consumes them.
    """
    fields = _fields()
    assert fields.non_empty_text(value="ok") == "ok"
    assert fields.non_empty_text(value="   ") is None
    assert fields.non_empty_text(value=7) is None
    assert fields.string_tuple(value=["a", "b"]) == ("a", "b")
    assert fields.string_tuple(value="a") is None
    assert fields.string_tuple(value=["a", 2]) is None
    assert fields.string_map(value={"A": "1"}) == {"A": "1"}
    assert fields.string_map(value=["A"]) is None
    assert fields.string_map(value={"A": 1}) is None


def test_a_bounded_integer_refuses_bool_and_both_ends_of_its_range() -> None:
    """`exit_code: true` must not resolve to the real exit code 1."""
    fields = _fields()
    assert fields.bounded_int(value=1, low=1, high=125) == 1
    assert fields.bounded_int(value=125, low=1, high=125) == 125
    assert fields.bounded_int(value=True, low=1, high=125) is None
    assert fields.bounded_int(value=0, low=1, high=125) is None
    assert fields.bounded_int(value=126, low=1, high=125) is None
    assert fields.bounded_int(value="1", low=1, high=125) is None


def test_a_price_must_be_finite_and_non_negative() -> None:
    """A price is summed into a run cost, so infinity and NaN are refused."""
    fields = _fields()
    assert fields.finite_price(value=0) == 0.0
    assert fields.finite_price(value=2.5) == 2.5
    assert fields.finite_price(value=-0.1) is None
    assert fields.finite_price(value=float("inf")) is None
    assert fields.finite_price(value=float("nan")) is None
    assert fields.finite_price(value=True) is None
    assert fields.finite_price(value="1.0") is None


def test_the_key_set_refusals_name_the_offending_and_the_owed_keys() -> None:
    """A closed grammar reports what it refused, not merely that it refused."""
    fields = _fields()
    assert fields.unknown_keys_refusal(entry={"a": 1}, allowed=frozenset({"a"}), key="k") is None
    unknown = fields.unknown_keys_refusal(entry={"b": 1}, allowed=frozenset({"a"}), key="k")
    assert unknown is not None
    assert "'b'" in unknown
    assert fields.missing_keys_refusal(entry={"a": 1}, required=frozenset({"a"}), key="k") is None
    missing = fields.missing_keys_refusal(entry={}, required=frozenset({"a", "b"}), key="k")
    assert missing is not None
    assert "a, b" in missing


def test_a_credential_marker_is_found_in_every_committed_position() -> None:
    """Command, args, env key and env value are all committed public data."""
    secrets = _secrets()
    assert secrets.secret_marker(text="ANTHROPIC_MODEL") is None
    assert secrets.secret_marker(text="ANTHROPIC_AUTH_TOKEN") == "token"
    clean = {"command": "uvx acp", "args": ("--flag",), "env": {"MODEL": "x"}, "key": "k"}
    assert secrets.adapter_secret_refusal(**clean) is None
    assert secrets.adapter_secret_refusal(**{**clean, "command": "acp --token abc"}) is not None
    assert secrets.adapter_secret_refusal(**{**clean, "args": ("--api-key", "x")}) is not None
    assert secrets.adapter_secret_refusal(**{**clean, "env": {"X_SECRET": "v"}}) is not None
    assert secrets.adapter_secret_refusal(**{**clean, "env": {"X": "my-password"}}) is not None


def test_a_credential_refusal_never_echoes_the_credential() -> None:
    """A refusal is journalled, so it must carry no credential material."""
    refusal = _secrets().adapter_secret_refusal(
        command="uvx acp",
        args=(),
        env={"ANTHROPIC_AUTH_TOKEN": "sk-live-do-not-print"},
        key="dispatcher.acp_nodes.pr",
    )
    assert refusal is not None
    assert "ANTHROPIC_AUTH_TOKEN" in refusal
    assert "sk-live-do-not-print" not in refusal


def test_each_signature_source_requires_its_own_discriminator() -> None:
    """A machine code and a literal conjunction are mutually exclusive."""
    signatures = _signatures()
    parsed = signatures.parse_availability_signatures(
        value=[_MACHINE_SIGNATURE, _MESSAGE_SIGNATURE], key="k"
    )
    assert not isinstance(parsed, str), parsed
    assert parsed[0].machine_code == "model.unsupported"
    assert parsed[0].all_literals == ()
    assert parsed[1].all_literals == ("usage limit", "requested model")
    assert parsed[1].hold_key == "chatgpt-account"
    assert parsed[1].exit_code == 1


def test_a_mismatched_discriminator_refuses_rather_than_being_ignored() -> None:
    """The forbidden field is named, because the remedy is to delete it."""
    signatures = _signatures()
    for entry, needle in (
        ({**_MACHINE_SIGNATURE, "all_literals": ["x"]}, "all_literals"),
        ({**_MACHINE_SIGNATURE, "machine_code": ""}, "machine_code"),
        ({**_MESSAGE_SIGNATURE, "machine_code": "c"}, "machine_code"),
        ({**_MESSAGE_SIGNATURE, "all_literals": []}, "all_literals"),
        ({**_MESSAGE_SIGNATURE, "all_literals": [" "]}, "all_literals"),
        ({**_MESSAGE_SIGNATURE, "all_literals": "usage limit"}, "all_literals"),
    ):
        refusal = signatures.parse_availability_signatures(value=[entry], key="k")
        assert isinstance(refusal, str), entry
        assert needle in refusal


def test_the_signature_enumerations_and_optional_fields_are_closed() -> None:
    """Every enum value, the exit-code bounds, and hold-key scoping refuse."""
    signatures = _signatures()
    for entry in (
        {**_MACHINE_SIGNATURE, "extra": 1},
        {"source": "protocol.machine_code", "machine_code": "c"},
        {**_MACHINE_SIGNATURE, "source": "protocol.stdout"},
        {**_MACHINE_SIGNATURE, "cause": "annoyed"},
        {**_MACHINE_SIGNATURE, "scope": "global"},
        {**_MACHINE_SIGNATURE, "exit_code": 0},
        {**_MACHINE_SIGNATURE, "hold_key": "k"},
        {**_MESSAGE_SIGNATURE, "hold_key": ""},
    ):
        assert isinstance(signatures.parse_availability_signatures(value=[entry], key="k"), str)
    assert isinstance(signatures.parse_availability_signatures(value=[3], key="k"), str)
    assert isinstance(signatures.parse_availability_signatures(value={}, key="k"), str)


def test_identical_matchers_conflict_only_when_they_dispose_differently() -> None:
    """Redundancy is harmless; a disposition split can only ever be ambiguous.

    The two cases differ by ONE field, so a check that refused every
    repeat -- or none of them -- fails exactly one of these assertions.
    """
    signatures = _signatures()
    redundant = signatures.parse_availability_signatures(
        value=[_MACHINE_SIGNATURE, dict(_MACHINE_SIGNATURE)], key="k"
    )
    assert not isinstance(redundant, str), redundant
    assert len(redundant) == 2
    conflicting = signatures.parse_availability_signatures(
        value=[_MACHINE_SIGNATURE, {**_MACHINE_SIGNATURE, "cause": "quota"}], key="k"
    )
    assert isinstance(conflicting, str)
    assert "first match" in conflicting


def test_a_literal_conjunction_conflicts_regardless_of_its_written_order() -> None:
    """`all_literals` is a conjunction, so ordering must not hide a conflict."""
    reordered = {
        **_MESSAGE_SIGNATURE,
        "all_literals": ["requested model", "usage limit"],
        "cause": "rate_limit",
    }
    refusal = _signatures().parse_availability_signatures(
        value=[_MESSAGE_SIGNATURE, reordered], key="k"
    )
    assert isinstance(refusal, str)


def test_a_pricing_table_is_all_or_none_and_names_one_exact_model() -> None:
    """A partial table would make cost silently unobservable much later."""
    pricing = _pricing()
    parsed = pricing.parse_candidate_pricing(value=_PRICING, key="k")
    assert not isinstance(parsed, str), parsed
    assert parsed.model == "claude-haiku-4-5"
    assert parsed.output_usd_per_million == 5.0
    for value in (
        "table",
        {**_PRICING, "extra": 1},
        {key: item for key, item in _PRICING.items() if key != "cache_read_usd_per_million"},
        {**_PRICING, "model": " "},
        {**_PRICING, "input_usd_per_million": -1},
    ):
        assert isinstance(pricing.parse_candidate_pricing(value=value, key="k"), str)


def test_a_candidate_identity_is_all_or_none_and_never_names_a_credential() -> None:
    """A partial identity is refused rather than completed by guesswork."""
    schema = _schema()
    parsed = schema.parse_candidate_identity(entry=_IDENTITY, key="k")
    assert not isinstance(parsed, str) and parsed is not None
    assert parsed.pair == ("anthropic", "claude-haiku-4-5")
    assert schema.parse_candidate_identity(entry={"command": "x"}, key="k") is None
    for entry in (
        {"display_name": "only"},
        {**_IDENTITY, "candidate_key": ""},
        {**_IDENTITY, "candidate_key": 4},
        {**_IDENTITY, "display_name": "prod api_key holder"},
    ):
        assert isinstance(schema.parse_candidate_identity(entry=entry, key="k"), str), entry


def test_a_fallback_carries_a_complete_command_and_inherits_nothing() -> None:
    """Omitted `args` and `env` resolve to EMPTY, never to a neighbour's."""
    parsed = _schema().parse_fallback_candidate(entry=_candidate(), key="k")
    assert not isinstance(parsed, str), parsed
    assert parsed.adapter.command == "uvx claude-acp"
    assert parsed.adapter.args == ()
    assert parsed.adapter.env == {}
    assert parsed.signatures == ()
    assert parsed.pricing is None
    assert parsed.identity is not None


def test_a_fallback_reads_its_own_metadata_and_refuses_every_malformed_field() -> None:
    """One table in, one candidate out, with the closed grammar enforced."""
    schema = _schema()
    complete = _candidate(
        args=["--flag"],
        env={"BASE_URL": "https://example.invalid"},
        pricing=_PRICING,
        availability_signatures=[_MACHINE_SIGNATURE],
    )
    parsed = schema.parse_fallback_candidate(entry=complete, key="k")
    assert not isinstance(parsed, str), parsed
    assert parsed.adapter.args == ("--flag",)
    assert parsed.adapter.env == {"BASE_URL": "https://example.invalid"}
    assert parsed.pricing is not None
    assert len(parsed.signatures) == 1
    for entry in (
        "uvx claude-acp",
        _candidate(unknown_key=1),
        {**_candidate(), "candidate_key": ""},
        {"command": "uvx claude-acp"},
        _candidate(command=""),
        _candidate(args="--flag"),
        _candidate(env=["A=1"]),
        _candidate(env={"ANTHROPIC_AUTH_TOKEN": "sk-live"}),
        _candidate(pricing={"model": "m"}),
        _candidate(availability_signatures=[{"source": "protocol.message"}]),
    ):
        assert isinstance(schema.parse_fallback_candidate(entry=entry, key="k"), str), entry


def test_a_node_entry_without_new_grammar_metadata_carries_no_chain() -> None:
    """The legacy spellings stay legal and stay inert.

    `fallbacks: []` is included deliberately: the contract calls it the
    byte-identical no-op, so it must NOT enable the new grammar.
    """
    chains = _chains()
    for entry in ("uvx claude-acp", {"command": "uvx claude-acp"}, {"fallbacks": []}, {}):
        parsed = chains.parse_node_chain(entry=entry, key="k")
        assert not isinstance(parsed, str), entry
        assert parsed.enabled is False
        assert parsed.fallbacks == ()
        assert parsed.identity is None


def test_each_new_grammar_field_on_its_own_enables_the_node() -> None:
    """Identity, a signature, pricing, or one fallback each opt the node in."""
    chains = _chains()
    for entry in (
        dict(_IDENTITY),
        {"availability_signatures": [_MACHINE_SIGNATURE]},
        {"pricing": _PRICING},
        _fallback_node(),
    ):
        parsed = chains.parse_node_chain(entry=entry, key="k")
        assert not isinstance(parsed, str), entry
        assert parsed.enabled is True


def test_an_enabled_node_entry_closes_its_key_set_and_its_committed_data() -> None:
    """Opting in buys the strict grammar, including the credential scan."""
    chains = _chains()
    for entry in (
        {**_IDENTITY, "bogus": 1},
        {**_IDENTITY, "command": 4},
        {**_IDENTITY, "args": "--flag"},
        {**_IDENTITY, "env": ["A=1"]},
        {**_IDENTITY, "env": {"OPENAI_API_KEY": "sk-live"}},
        {**_IDENTITY, "pricing": {"model": "m"}},
        {"display_name": "partial"},
        {"fallbacks": "not-an-array"},
        {"fallbacks": [{"command": "uvx acp"}]},
    ):
        assert isinstance(chains.parse_node_chain(entry=entry, key="k"), str), entry


def test_a_wrong_typed_fallbacks_array_refuses_even_on_a_legacy_entry() -> None:
    """An unreadable `fallbacks` value is never silently dropped."""
    refusal = _chains().parse_node_chain(entry={"command": "uvx acp", "fallbacks": 3}, key="k")
    assert isinstance(refusal, str)
    assert "fallbacks" in refusal


def test_parsing_every_configured_node_propagates_the_first_refusal() -> None:
    """A table of nodes refuses on the first malformed one, in sorted order."""
    chains = _chains()
    parsed = chains.parse_node_chains(
        table={"pr": _fallback_node(), "review": "uvx acp"}, key_prefix="dispatcher.acp_nodes"
    )
    assert not isinstance(parsed, str), parsed
    assert parsed["pr"].enabled is True
    assert parsed["review"].enabled is False
    refusal = chains.parse_node_chains(
        table={"pr": {**_IDENTITY, "bogus": 1}}, key_prefix="dispatcher.acp_nodes"
    )
    assert isinstance(refusal, str)
    assert "dispatcher.acp_nodes.pr" in refusal


def test_the_same_entitlement_pair_may_be_reused_across_two_nodes() -> None:
    """Cross-node identity reuse is intentional when the entitlement is shared."""
    parsed = _chains().parse_node_chains(
        table={"pr": dict(_IDENTITY), "review": dict(_IDENTITY)},
        key_prefix="dispatcher.acp_nodes",
    )
    assert not isinstance(parsed, str), parsed
    assert parsed["pr"].identity is not None
    assert parsed["pr"].identity.pair == parsed["review"].identity.pair
