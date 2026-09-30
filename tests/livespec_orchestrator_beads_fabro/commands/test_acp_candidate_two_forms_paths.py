"""The two-form dispatch's remaining decision paths, driven one by one.

Companion to `test_acp_candidate_two_forms`, which binds the acceptance
assertions (the closed grammar, and identity derived from the catalogs). This
module exercises the decisions those cases do not reach: each refusal a
structured candidate can produce once it is nested inside a `fallbacks` array,
the override validation, and the catalog-refusal path every seam that resolves a
chain must answer to.

WHY THE NESTED CASES NEED THEIR OWN COVERAGE. A fallback and a node entry go
through the SAME structured parser, but they reach it by different routes and
carry different keys -- a node may declare `fallbacks` and a fallback may not.
A refusal proven only on the node entry is a refusal proven on one of the two
call sites.

THE CATALOG-REFUSAL LEG IS THE ONE WORTH SPELLING OUT. A repository whose
catalog will not parse cannot resolve a single structured candidate, and three
seams resolve chains independently -- the dispatch-time journal, the preflight
verdict, and the projection's primary-generation read. Each has its own correct
answer to an unparseable catalog, and they DIFFER: the first two refuse (they run
before claim), while the projection returns the empty mapping (it runs after a
run has finished, where refusing would strand the evidence). Asserting them
together is what keeps that asymmetry deliberate.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_PREFIX = "dispatcher.acp_nodes"

_OPUS_ENTRY: dict[str, Any] = {
    "agent": "claude-acp",
    "model": "claude-opus-5",
    "effort": "high",
}

_BROKEN_AGENT_CATALOG: dict[str, Any] = {"agent_catalog": {"local-acp": {"display_name": "Local"}}}


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _chains(*, block: dict[str, Any]) -> Any:
    catalogs = _module(name="_acp_catalogs").resolve_acp_catalogs(block=block)
    assert not isinstance(catalogs, str), catalogs
    return _module(name="_acp_node_repository").repository_acp_chains(
        block=block, catalogs=catalogs
    )


def _with_fallback(*, fallback: Any) -> dict[str, Any]:
    return {"acp_nodes": {"implement": {**_OPUS_ENTRY, "fallbacks": [fallback]}}}


def _repo_with(*, dispatcher: dict[str, Any], tmp_path: Path) -> Path:
    config = {"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}
    _ = (tmp_path / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")
    return tmp_path


def test_a_non_table_fallback_entry_refuses_naming_its_index() -> None:
    """A fallback array holding something that is not a table."""
    refusal = _chains(block=_with_fallback(fallback="npx -y acp"))

    assert isinstance(refusal, str)
    assert f"{_PREFIX}.implement.fallbacks[0]" in refusal


def test_a_mixed_form_fallback_refuses_naming_both_fields() -> None:
    """The mixed-form refusal fires inside a `fallbacks` array too."""
    refusal = _chains(
        block=_with_fallback(fallback={"agent": "claude-acp", "model": "x", "command": "adapter"})
    )

    assert isinstance(refusal, str)
    assert f"{_PREFIX}.implement.fallbacks[0]" in refusal
    assert "command" in refusal


def test_a_structured_fallback_missing_its_model_refuses() -> None:
    """The structured form's own required fields, inside the array."""
    refusal = _chains(block=_with_fallback(fallback={"agent": "claude-acp"}))

    assert isinstance(refusal, str)
    assert f"{_PREFIX}.implement.fallbacks[0].model" in refusal


def test_a_structured_fallback_may_declare_a_nested_fallbacks_key_nowhere() -> None:
    """`fallbacks` is a NODE key, not a candidate key: a chain of chains is refused.

    The contract defines one ordered chain per node. Admitting the key on a
    candidate would accept a nested chain the preflight, the digests and the
    runtime handler have no definition for -- and it would be accepted silently,
    because a nested array parses perfectly well.
    """
    refusal = _chains(
        block=_with_fallback(fallback={**_OPUS_ENTRY, "fallbacks": [dict(_OPUS_ENTRY)]})
    )

    assert isinstance(refusal, str)
    assert "'fallbacks'" in refusal


def test_a_structured_candidates_identity_override_is_validated_per_field() -> None:
    """An override answers to the same per-field rules a declared identity does."""
    blank = _chains(block={"acp_nodes": {"implement": {**_OPUS_ENTRY, "candidate_key": ""}}})
    assert isinstance(blank, str)
    assert "candidate_key" in blank

    secretish = _chains(
        block={"acp_nodes": {"implement": {**_OPUS_ENTRY, "availability_key": "ANTHROPIC_API_KEY"}}}
    )
    assert isinstance(secretish, str)
    assert "credential reference" in secretish


def test_a_structured_candidates_pricing_override_answers_to_the_same_grammar() -> None:
    """The all-or-none pricing rule reaches a structured entry unchanged."""
    refusal = _chains(
        block={"acp_nodes": {"implement": {**_OPUS_ENTRY, "pricing": {"model": "claude-opus-5"}}}}
    )

    assert isinstance(refusal, str)
    assert f"{_PREFIX}.implement.pricing" in refusal


def test_a_structured_candidates_pricing_override_wins_over_the_catalog() -> None:
    """A per-candidate override wins, and the catalog value stands without one."""
    chains = _chains(
        block={
            "model_catalog": {
                "anthropic/claude-opus-5": {
                    "display_name": "Claude Opus 5",
                    "pricing": {
                        "model": "claude-opus-5",
                        "input_usd_per_million": 1.0,
                        "output_usd_per_million": 1.0,
                        "cache_write_usd_per_million": 1.0,
                        "cache_read_usd_per_million": 1.0,
                    },
                }
            },
            "acp_nodes": {
                "implement": {
                    **_OPUS_ENTRY,
                    "pricing": {
                        "model": "claude-opus-5",
                        "input_usd_per_million": 9.0,
                        "output_usd_per_million": 9.0,
                        "cache_write_usd_per_million": 9.0,
                        "cache_read_usd_per_million": 9.0,
                    },
                },
                "fix": _OPUS_ENTRY,
            },
        }
    )
    assert not isinstance(chains, str), chains

    overridden = chains["implement"].pricing
    inherited = chains["fix"].pricing
    assert overridden is not None
    assert overridden.input_usd_per_million == 9.0
    assert inherited is not None
    assert inherited.input_usd_per_million == 1.0


def test_a_structured_candidate_inherits_the_models_measured_signatures() -> None:
    """A model's catalog signatures reach the candidate, and an override replaces them."""
    signature = {
        "source": "protocol.machine_code",
        "machine_code": "anthropic.model.gone",
        "cause": "model_not_found",
        "scope": "candidate",
    }
    chains = _chains(
        block={
            "model_catalog": {
                "anthropic/claude-opus-5": {
                    "display_name": "Claude Opus 5",
                    "availability_signatures": [signature],
                }
            },
            "acp_nodes": {"implement": _OPUS_ENTRY},
        }
    )
    assert not isinstance(chains, str), chains

    [inherited] = chains["implement"].signatures
    assert inherited.machine_code == "anthropic.model.gone"


def test_a_manual_form_fallback_carrying_config_options_refuses() -> None:
    """The committed-`config_options` refusal reaches a MANUAL fallback too.

    The manual fallback route is a separate call site from the manual node-entry
    route below, and the key is illegal on both.
    """
    refusal = _chains(
        block=_with_fallback(
            fallback={
                "display_name": "operator text",
                "candidate_key": "stable-candidate",
                "availability_key": "default-domain",
                "command": "adapter",
                "config_options": {"model": "x"},
            }
        )
    )

    assert isinstance(refusal, str)
    assert f"{_PREFIX}.implement.fallbacks[0]" in refusal
    assert "config_options" in refusal


def test_a_manual_form_node_entry_carrying_config_options_refuses() -> None:
    """The committed-`config_options` refusal reaches the manual node-entry route."""
    refusal = _chains(
        block={"acp_nodes": {"implement": {"command": "adapter", "config_options": {"model": "x"}}}}
    )

    assert isinstance(refusal, str)
    assert "config_options" in refusal


def test_a_legacy_manual_node_entry_still_resolves_to_the_empty_chain() -> None:
    """The control for the case above: a manual entry with no new-grammar field.

    Without this leg, "the config_options refusal fired" is equally consistent
    with the manual route having started refusing every entry.
    """
    chains = _chains(block={"acp_nodes": {"implement": {"command": "adapter"}}})

    assert not isinstance(chains, str), chains
    assert chains["implement"].enabled is False


def test_the_dispatch_seam_refuses_an_unparseable_catalog_before_any_run(tmp_path: Path) -> None:
    """`prepare_acp_nodes` runs before a run exists, so it refuses."""
    seam = _module(name="_dispatcher_acp_nodes")
    repo = _repo_with(dispatcher=_BROKEN_AGENT_CATALOG, tmp_path=tmp_path)
    committed = tmp_path / "workflow.toml"
    _ = committed.write_text('[run.inputs]\nimplement_adapter = "npx -y acp"\n', encoding="utf-8")

    written: list[dict[str, object]] = []

    class _Journal:
        def append(self, *, record: dict[str, object]) -> None:
            written.append(record)

    refusal = seam.prepare_acp_nodes(
        repo=repo,
        committed=committed,
        overrides=(),
        journal=_Journal(),
        work_item_id="bd-ib-kc7vzk",
    )

    assert isinstance(refusal, str)
    assert "dispatcher.agent_catalog.local-acp" in refusal
    assert written == [], "a refusal before claim journals no acp-nodes record"

    # The control that makes the empty list evidence rather than a vacuous truth:
    # the same recorder, the same invocation, a catalog that parses. Without it,
    # "nothing was journaled" is equally consistent with a recorder that cannot
    # record.
    healthy = _repo_with(
        dispatcher={"acp_nodes": {"implement": dict(_OPUS_ENTRY)}}, tmp_path=tmp_path
    )
    resolution = seam.prepare_acp_nodes(
        repo=healthy,
        committed=committed,
        overrides=(),
        journal=_Journal(),
        work_item_id="bd-ib-kc7vzk",
    )

    assert not isinstance(resolution, str), resolution
    assert [record["stage"] for record in written] == [seam.ACP_NODES_STAGE]


def test_the_preflight_refuses_an_unparseable_catalog_before_claim(tmp_path: Path) -> None:
    """Admission runs before claim, so an unresolvable catalog is not viable."""
    preflight = _module(name="_dispatcher_acp_preflight")
    repo = _repo_with(dispatcher=_BROKEN_AGENT_CATALOG, tmp_path=tmp_path)

    verdict = preflight.resolve_acp_preflight(
        repo=repo, journal_path=None, now_iso="2026-09-30T00:00:00Z"
    )

    assert verdict.viable is False
    assert verdict.refusal is not None
    assert "dispatcher.agent_catalog.local-acp" in verdict.refusal


def test_the_projection_read_returns_nothing_rather_than_refusing(tmp_path: Path) -> None:
    """The asymmetry: this one runs AFTER a run, where refusing strands evidence."""
    preflight = _module(name="_dispatcher_acp_preflight")
    repo = _repo_with(dispatcher=_BROKEN_AGENT_CATALOG, tmp_path=tmp_path)

    assert preflight.resolve_acp_primary_generations(repo=repo) == {}
