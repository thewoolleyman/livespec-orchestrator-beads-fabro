"""Per-repository catalog additions, and the CLOSED grammar they answer to.

Binds `SPECIFICATION/contracts.md` section "Agent and model catalogs": "A
repository MAY add or override agent entries under `dispatcher.agent_catalog`
in its `.livespec.jsonc` under the same closed grammar; an unknown key refuses
before claim", and the same permission for `dispatcher.model_catalog`.

AN OVERRIDE IS A WHOLE ENTRY, NOT A PATCH, and the control for that is the case
where a partial override would have been silently completed from the shipped
entry. A merge would make the EFFECTIVE entry a value nobody wrote -- half
committed configuration, half a snapshot that moves under it on the next
re-seed -- so a repository restating an agent restates all of it. The refusal
names the missing keys, which is what makes the rule one edit rather than a
round trip per field.

EVERY REFUSAL IS ASSERTED ON ITS MESSAGE, not merely on its type. A refusal an
operator cannot map back to a configuration line is the failure mode the closed
grammar exists to remove, so each case checks that the fully-qualified key is
in the text.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_AGENT_KEY = "dispatcher.agent_catalog"
_MODEL_KEY = "dispatcher.model_catalog"

# A complete agent entry in the closed grammar, used as the base every negative
# case perturbs by exactly one field. Perturbing a complete entry is what makes
# each refusal attributable to the field it names.
_COMPLETE_AGENT: dict[str, Any] = {
    "display_name": "Local Agent",
    "account_domain": "local-allowance",
    "provider": "local",
    "version": "1.2.3",
    "command": "/opt/local/bin/local-acp",
    "mechanism": {"kind": "env", "model": "LOCAL_MODEL", "effort": "LOCAL_EFFORT"},
    "effort_levels": ["low", "high"],
}

_COMPLETE_MODEL: dict[str, Any] = {
    "display_name": "Local Model 1",
    "canonical_id": "local-model-1-20260930",
    "aliases": ["lm1"],
}

_PRICING: dict[str, Any] = {
    "model": "local-model-1-20260930",
    "input_usd_per_million": 1.0,
    "output_usd_per_million": 2.0,
    "cache_write_usd_per_million": 3.0,
    "cache_read_usd_per_million": 4.0,
}


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _agents(*, table: object) -> Any:
    return _module(name="_acp_agent_catalog").resolve_agent_catalog(block={"agent_catalog": table})


def _models(*, table: object) -> Any:
    return _module(name="_acp_model_catalog").resolve_model_catalog(block={"model_catalog": table})


def test_the_overrides_module_is_a_committed_file() -> None:
    """The shared closed-table reader exists as a committed module."""
    path = (
        _REPO_ROOT
        / ".claude-plugin"
        / "scripts"
        / "livespec_orchestrator_beads_fabro"
        / "commands"
        / "_acp_catalog_overrides.py"
    )
    assert path.is_file()


def test_an_unconfigured_repository_resolves_the_shipped_snapshot_unchanged() -> None:
    """No additions means the shipped catalogs, byte for byte."""
    catalogs = _module(name="_acp_catalogs")
    resolved = catalogs.resolve_acp_catalogs(block={})
    shipped = catalogs.builtin_catalogs()

    assert resolved.agents == shipped.agents
    assert resolved.models == shipped.models
    assert resolved.snapshot == shipped.snapshot


def test_a_repository_adds_a_new_agent_beside_the_shipped_population() -> None:
    """An added agent joins the catalog; the shipped entries survive."""
    resolved = _agents(table={"local-acp": _COMPLETE_AGENT})

    assert "claude-acp" in resolved
    added = resolved["local-acp"]
    assert added.agent_id == "local-acp"
    assert added.display_name == "Local Agent"
    assert added.account_domain == "local-allowance"
    assert added.provider == "local"
    assert added.version == "1.2.3"
    assert added.command == "/opt/local/bin/local-acp"
    assert added.effort_levels == ("low", "high")
    assert added.mechanism.kind == "env"
    assert added.mechanism.model == "LOCAL_MODEL"
    assert added.mechanism.effort == "LOCAL_EFFORT"
    assert added.args == ()
    assert added.env == {}
    assert added.read_only_env == {}
    assert added.multi_provider is False


def test_an_added_agent_may_declare_args_env_and_a_read_only_posture() -> None:
    """The optional launch-distribution fields are read verbatim."""
    resolved = _agents(
        table={
            "local-acp": {
                **_COMPLETE_AGENT,
                "args": ["--acp"],
                "env": {"LOCAL_MODE": "write"},
                "read_only_env": {"LOCAL_MODE": "read"},
            }
        }
    )
    added = resolved["local-acp"]

    assert added.args == ("--acp",)
    assert added.env == {"LOCAL_MODE": "write"}
    assert added.read_only_env == {"LOCAL_MODE": "read"}


def test_a_repository_override_replaces_a_shipped_agent_entry_wholesale() -> None:
    """Overriding `claude-acp` yields the repository's entry, not a merge."""
    resolved = _agents(table={"claude-acp": _COMPLETE_AGENT})

    assert resolved["claude-acp"].display_name == "Local Agent"
    assert resolved["claude-acp"].command == "/opt/local/bin/local-acp"
    assert resolved["claude-acp"].mechanism.model == "LOCAL_MODEL"


def test_a_multi_provider_agent_declares_no_single_provider() -> None:
    """`multi_provider` and `provider` are mutually exclusive, both ways."""
    without = dict(_COMPLETE_AGENT)
    del without["provider"]
    resolved = _agents(table={"local-acp": {**without, "multi_provider": True}})
    assert resolved["local-acp"].multi_provider is True
    assert resolved["local-acp"].provider == ""

    both = _agents(table={"local-acp": {**_COMPLETE_AGENT, "multi_provider": True}})
    assert isinstance(both, str)
    assert "multi_provider" in both

    neither = _agents(table={"local-acp": without})
    assert isinstance(neither, str)
    assert "provider" in neither


def test_an_agent_entry_carrying_an_unknown_key_refuses_naming_it() -> None:
    """The closed key set refuses before claim, naming the key and the entry."""
    refusal = _agents(table={"local-acp": {**_COMPLETE_AGENT, "modle": "typo"}})

    assert isinstance(refusal, str)
    assert f"{_AGENT_KEY}.local-acp" in refusal
    assert "'modle'" in refusal


def test_an_incomplete_agent_entry_refuses_naming_every_field_it_owes() -> None:
    """All-or-none: the refusal enumerates the whole missing set at once."""
    refusal = _agents(table={"local-acp": {"display_name": "Local Agent"}})

    assert isinstance(refusal, str)
    assert "account_domain" in refusal
    assert "command" in refusal
    assert "mechanism" in refusal
    assert "version" in refusal


def test_each_wrong_typed_agent_field_refuses_naming_its_own_path() -> None:
    """Every optional field's type is checked against its own key."""
    cases = {
        "display_name": {"display_name": ""},
        "account_domain": {"account_domain": 7},
        "version": {"version": ""},
        "command": {"command": "   "},
        "args": {"args": "not-a-list"},
        "env": {"env": "not-a-table"},
        "read_only_env": {"read_only_env": [1]},
        "effort_levels": {"effort_levels": [3]},
        "multi_provider": {"multi_provider": "yes"},
        # A run id written as a number is the one `verification_run` value an
        # operator cannot have meant: stringified silently it would become a
        # reference nothing resolves, recorded as though the entry had been run.
        "verification_run": {"verification_run": 7},
    }
    for field, patch in cases.items():
        refusal = _agents(table={"local-acp": {**_COMPLETE_AGENT, **patch}})
        assert isinstance(refusal, str), field
        assert f"{_AGENT_KEY}.local-acp.{field}" in refusal, (field, refusal)


def test_an_agent_catalog_that_is_not_a_table_of_tables_refuses() -> None:
    """Both the table itself and each entry must be a table."""
    not_a_table = _agents(table="local-acp")
    assert isinstance(not_a_table, str)
    assert _AGENT_KEY in not_a_table

    entry_not_a_table = _agents(table={"local-acp": "npx -y local"})
    assert isinstance(entry_not_a_table, str)
    assert f"{_AGENT_KEY}.local-acp" in entry_not_a_table

    blank_id = _agents(table={"  ": _COMPLETE_AGENT})
    assert isinstance(blank_id, str)
    assert _AGENT_KEY in blank_id


def test_the_mechanism_grammar_admits_exactly_the_four_ratified_kinds() -> None:
    """`protocol`, `env`, `json_env` and `arg`, and nothing else."""
    mechanism = _module(name="_acp_agent_mechanism")
    for kind in mechanism.MECHANISM_KINDS:
        entry = {**_COMPLETE_AGENT, "mechanism": {"kind": kind, "model": "m"}}
        if kind == "json_env":
            entry["mechanism"]["env"] = "LOCAL_CONFIG"
        resolved = _agents(table={"local-acp": entry})
        assert not isinstance(resolved, str), (kind, resolved)
        assert resolved["local-acp"].mechanism.kind == kind

    refusal = _agents(
        table={"local-acp": {**_COMPLETE_AGENT, "mechanism": {"kind": "psychic", "model": "m"}}}
    )
    assert isinstance(refusal, str)
    assert "mechanism.kind" in refusal


def test_the_json_env_mechanism_requires_its_carrier_and_the_others_forbid_it() -> None:
    """`env` is meaningful for `json_env` alone, so the grammar keys on kind."""
    missing = _agents(
        table={"local-acp": {**_COMPLETE_AGENT, "mechanism": {"kind": "json_env", "model": "m"}}}
    )
    assert isinstance(missing, str)
    assert "mechanism.env" in missing

    surplus = _agents(
        table={
            "local-acp": {
                **_COMPLETE_AGENT,
                "mechanism": {"kind": "env", "model": "m", "env": "LOCAL_CONFIG"},
            }
        }
    )
    assert isinstance(surplus, str)
    assert "mechanism.env" in surplus


def test_each_wrong_typed_mechanism_field_refuses_naming_its_own_path() -> None:
    """A mechanism is a table with a non-empty kind, model and optional effort."""
    cases = (
        ({"mechanism": "env"}, "mechanism"),
        ({"mechanism": {"kind": "env", "model": ""}}, "mechanism.model"),
        ({"mechanism": {"kind": "env", "model": "m", "effort": 3}}, "mechanism.effort"),
        ({"mechanism": {"kind": "env", "model": "m", "spin": 1}}, "mechanism"),
        ({"mechanism": {"model": "m"}}, "mechanism"),
    )
    for patch, expected in cases:
        refusal = _agents(table={"local-acp": {**_COMPLETE_AGENT, **patch}})
        assert isinstance(refusal, str), patch
        assert f"{_AGENT_KEY}.local-acp.{expected}" in refusal, (patch, refusal)


def test_a_repository_adds_a_model_under_its_provider_qualified_key() -> None:
    """An added model joins the catalog keyed by its own `provider/model`."""
    resolved = _models(table={"local/local-model-1": _COMPLETE_MODEL})

    assert "anthropic/claude-opus-5" in resolved
    added = resolved["local/local-model-1"]
    assert added.provider == "local"
    assert added.model == "local-model-1"
    assert added.key == "local/local-model-1"
    assert added.display_name == "Local Model 1"
    assert added.canonical_id == "local-model-1-20260930"
    assert added.aliases == ("lm1",)
    assert added.pricing is None
    assert added.signatures == ()


def test_an_added_model_defaults_its_canonical_id_to_its_own_key_segment() -> None:
    """An entry declaring no canonical id is served under the name it is keyed by."""
    resolved = _models(table={"local/local-model-1": {"display_name": "Local Model 1"}})
    assert resolved["local/local-model-1"].canonical_id == "local-model-1"


def test_an_added_model_may_declare_pricing_and_measured_signatures() -> None:
    """The two optional objects are parsed through the ratified grammars."""
    resolved = _models(
        table={
            "local/local-model-1": {
                **_COMPLETE_MODEL,
                "pricing": _PRICING,
                "availability_signatures": [
                    {
                        "source": "protocol.machine_code",
                        "machine_code": "local.model.gone",
                        "cause": "model_not_found",
                        "scope": "candidate",
                    }
                ],
            }
        }
    )
    added = resolved["local/local-model-1"]

    assert added.pricing is not None
    assert added.pricing.input_usd_per_million == 1.0
    assert len(added.signatures) == 1
    assert added.signatures[0].cause == "model_not_found"


def test_a_model_entry_carrying_an_unknown_key_refuses_naming_it() -> None:
    """The closed key set refuses before claim for models too."""
    refusal = _models(table={"local/local-model-1": {**_COMPLETE_MODEL, "prcing": {}}})

    assert isinstance(refusal, str)
    assert f"{_MODEL_KEY}.local/local-model-1" in refusal
    assert "'prcing'" in refusal


def test_each_wrong_typed_model_field_refuses_naming_its_own_path() -> None:
    """Every model field is checked against its own fully-qualified key."""
    cases = {
        "display_name": {"display_name": 1},
        "canonical_id": {"canonical_id": ""},
        "aliases": {"aliases": "lm1"},
        "pricing": {"pricing": "free"},
        "availability_signatures": {"availability_signatures": "none"},
    }
    for field, patch in cases.items():
        refusal = _models(table={"local/local-model-1": {**_COMPLETE_MODEL, **patch}})
        assert isinstance(refusal, str), field
        assert f"{_MODEL_KEY}.local/local-model-1.{field}" in refusal, (field, refusal)


def test_a_model_key_that_is_not_provider_slash_model_refuses() -> None:
    """The key carries both halves of the identity, so its shape is checked."""
    for key in ("local-model-1", "local/", "/local-model-1", "local/x/y"):
        refusal = _models(table={key: _COMPLETE_MODEL})
        assert isinstance(refusal, str), key
        assert _MODEL_KEY in refusal, key


def test_a_model_catalog_that_is_not_a_table_of_tables_refuses() -> None:
    """Both the table itself and each entry must be a table."""
    not_a_table = _models(table=["local/local-model-1"])
    assert isinstance(not_a_table, str)
    assert _MODEL_KEY in not_a_table

    entry_not_a_table = _models(table={"local/local-model-1": 3})
    assert isinstance(entry_not_a_table, str)
    assert f"{_MODEL_KEY}.local/local-model-1" in entry_not_a_table


def test_resolve_acp_catalogs_reports_either_catalog_refusal() -> None:
    """One resolution, so a fault in either catalog refuses the whole dispatch."""
    catalogs = _module(name="_acp_catalogs")

    agent_fault = catalogs.resolve_acp_catalogs(
        block={"agent_catalog": {"local-acp": {"display_name": "Local"}}}
    )
    assert isinstance(agent_fault, str)
    assert _AGENT_KEY in agent_fault

    model_fault = catalogs.resolve_acp_catalogs(block={"model_catalog": {"bad-key": {}}})
    assert isinstance(model_fault, str)
    assert _MODEL_KEY in model_fault


def test_an_addition_changes_the_snapshot_digest() -> None:
    """A repository's own entries are part of the snapshot identity.

    Without this the digest would say two dispatches rendered against the same
    catalog while one of them carried an override -- which is exactly the
    question the digest exists to answer.
    """
    catalogs = _module(name="_acp_catalogs")
    shipped = catalogs.builtin_catalogs().snapshot
    with_agent = catalogs.resolve_acp_catalogs(
        block={"agent_catalog": {"local-acp": _COMPLETE_AGENT}}
    )
    with_model = catalogs.resolve_acp_catalogs(
        block={"model_catalog": {"local/local-model-1": _COMPLETE_MODEL}}
    )

    assert with_agent.snapshot["agent_catalog_digest"] != shipped["agent_catalog_digest"]
    assert with_model.snapshot["model_catalog_digest"] != shipped["model_catalog_digest"]
