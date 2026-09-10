"""Attaching a candidate chain to an ALREADY-RESOLVED ACP primary.

Binds the resolution half of `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority": candidate zero comes through
the existing workflow-default / `codex_models` / repository / per-dispatch
layers FIRST, identity and fallbacks attach only afterwards, built-in
identity survives only while the resolved adapter still matches the
built-in, and the records this produces are structurally redacted.

THE BYTE-IDENTITY CONTROL IS THE LOAD-BEARING ONE. The additive claim is
that configuration carrying no fallback metadata, or only `fallbacks: []`,
renders EXACTLY what it rendered before this feature existed. That is
asserted against the baseline resolution computed in the same test rather
than against a transcribed literal, because a transcribed literal would
keep passing if BOTH sides changed together -- which is precisely the
regression it is there to catch.

Everything is HERMETIC: adapters are rendered as strings and nothing
launches an adapter or reaches a provider.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_CLAUDE = "npx -y @agentclientprotocol/claude-agent-acp"
_IMPLEMENTER_DEFAULT = f"ANTHROPIC_MODEL=claude-opus-5 CLAUDE_CODE_EFFORT_LEVEL=high {_CLAUDE}"

# The six-input graph this repository ships: one adapter input per ACP
# node, which is what makes per-node configuration expressible at all.
_WORKFLOW_INPUTS: dict[str, str] = {
    "implement_adapter": _IMPLEMENTER_DEFAULT,
    "fix_adapter": _IMPLEMENTER_DEFAULT,
    "review_fix_adapter": _IMPLEMENTER_DEFAULT,
    "pr_adapter": _CLAUDE,
    "review_adapter": _CLAUDE,
    "disposition_adapter": _CLAUDE,
}

_CODEX_PR_TIER: dict[str, Any] = {
    "codex_models": {"pr": {"model": "gpt-5.5", "reasoning_effort": "high"}}
}

_IDENTITY: dict[str, Any] = {
    "display_name": "Claude Haiku 4.5",
    "candidate_key": "claude-haiku-4-5",
    "availability_key": "anthropic",
}
# The fallback's command is a SENTINEL that no primary in this file can
# resolve to. That is what makes the "the record never exposes the chain"
# assertion load-bearing: a command shared with the primary would appear in
# the record legitimately, and the assertion would pass on the wrong hit.
_FALLBACK: dict[str, Any] = {
    "display_name": "Codex spark",
    "candidate_key": "gpt-5-3-codex-spark",
    "availability_key": "codex",
    "command": "uvx sentinel-fallback-acp",
}

_WORKFLOW_TOML = f"""_version = 1

[workflow]
graph = "workflow.fabro"

[run.inputs]
implement_adapter = "{_IMPLEMENTER_DEFAULT}"
fix_adapter = "{_CLAUDE}"
review_fix_adapter = "{_CLAUDE}"
pr_adapter = "{_CLAUDE}"
review_adapter = "{_CLAUDE}"
disposition_adapter = "{_CLAUDE}"

[run.environment]
id = "livespec-ci"
"""


class _RecordingJournal:
    """Collects journal records so the dispatch record can be asserted on."""

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _module(*, name: str) -> Any:
    """Import one of the chain-resolution modules, proving it exists first.

    The `is_file` assertion runs FIRST on purpose: it fails as a genuine
    assertion before the import can fail as a collection error, which is
    what keeps the Red honest.
    """
    assert (_COMMANDS / f"{name}.py").is_file(), f"{name} module is not implemented"
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _resolve(
    *,
    block: dict[str, Any],
    dispatch: tuple[str, ...] = (),
    workflow_inputs: dict[str, str] | None = None,
) -> Any:
    """Run the whole pure pipeline: overlays, layers, then chain attachment.

    Returns `(resolution, chains)` on success, or the ATTACHMENT refusal
    string. The ORDER of these calls is the contract under test --
    `resolve_acp_nodes` finishes before `attach_acp_chains` is handed its
    output -- so the helper performs it rather than letting each test
    re-spell it.

    Every earlier stage is ASSERTED rather than returned. Configuration
    that refuses before attachment is covered by
    `test_acp_candidate_schema` and by the seam tests below, so returning
    those refusals here would give each test a second, silent way to
    "pass" -- a refusal from the wrong stage reads exactly like the one
    the test meant to assert.
    """
    declared_inputs = _WORKFLOW_INPUTS if workflow_inputs is None else workflow_inputs
    repository = _module(name="_acp_node_repository")
    layers = _module(name="_acp_node_layers")
    seam = _module(name="_dispatcher_acp_nodes")
    overlays = repository.repository_acp_overlays(block=block)
    assert not isinstance(overlays, str), overlays
    declared = repository.repository_acp_chains(block=block)
    assert not isinstance(declared, str), declared
    dispatch_overlays = seam.dispatch_acp_overlays(overrides=dispatch)
    assert not isinstance(dispatch_overlays, str), dispatch_overlays
    resolution = layers.resolve_acp_nodes(
        workflow_inputs=declared_inputs, repository=overlays, dispatch=dispatch_overlays
    )
    assert not isinstance(resolution, str), resolution
    builtins = _module(name="_acp_builtin_candidates").builtin_acp_identities(
        workflow_inputs=declared_inputs, block=block
    )
    attached = _module(name="_acp_chain_resolution").attach_acp_chains(
        resolution=resolution,
        chains=declared,
        dispatch=dispatch_overlays,
        builtins=builtins,
    )
    if isinstance(attached, str):
        return attached
    return (resolution, attached)


def _rendered(*, block: dict[str, Any]) -> dict[str, str]:
    """Every node's rendered adapter bytes for one configuration."""
    outcome = _resolve(block=block)
    assert not isinstance(outcome, str), outcome
    resolution, _ = outcome
    return {node: resolved.rendered for node, resolved in resolution.nodes.items()}


def test_no_fallback_metadata_and_an_empty_array_render_identical_bytes() -> None:
    """The additive claim, asserted against the baseline computed here.

    Three configurations must agree byte for byte: nothing configured,
    `fallbacks: []` on the unconfigured Claude `pr` default, and
    `fallbacks: []` on an explicit `codex_models.pr` primary.
    """
    baseline = _rendered(block={})
    assert baseline["pr"] == _CLAUDE
    assert _rendered(block={"acp_nodes": {"pr": {"fallbacks": []}}}) == baseline
    codex_baseline = _rendered(block=_CODEX_PR_TIER)
    assert codex_baseline["pr"] != baseline["pr"]
    assert _rendered(block={**_CODEX_PR_TIER, "acp_nodes": {"pr": {"fallbacks": []}}}) == (
        codex_baseline
    )


def test_a_fallback_only_table_does_not_shadow_an_explicit_codex_primary() -> None:
    """Fallback-only fields attach AFTER the `codex_models` shorthand resolves.

    The negative control is the whole point: without it, a table carrying
    nothing but `fallbacks` replaces the shorthand overlay and the node
    silently reverts to the workflow's Claude default -- a plausible,
    green, wrong result.
    """
    codex_baseline = _rendered(block=_CODEX_PR_TIER)
    attached = _rendered(block={**_CODEX_PR_TIER, "acp_nodes": {"pr": {"fallbacks": [_FALLBACK]}}})
    assert attached["pr"] == codex_baseline["pr"]
    assert attached["pr"] != _CLAUDE


def test_an_identity_only_table_does_not_restore_the_workflow_default() -> None:
    """Identity attaches to the resolved primary; it never replaces one."""
    codex_baseline = _rendered(block=_CODEX_PR_TIER)
    identified = _rendered(block={**_CODEX_PR_TIER, "acp_nodes": {"pr": dict(_IDENTITY)}})
    assert identified["pr"] == codex_baseline["pr"]


def test_a_table_that_sets_a_primary_field_still_wins_over_the_shorthand() -> None:
    """The pre-existing `acp_nodes`-wins rule is preserved verbatim.

    This is the `bd-ib-5j4b` boundary: v109 does not silently decide that
    older legacy cross-provider merge issue, so a table SETTING a primary
    field keeps replacing the shorthand overlay exactly as before.
    """
    replaced = _rendered(
        block={**_CODEX_PR_TIER, "acp_nodes": {"pr": {"command": "uvx other-acp"}}}
    )
    assert replaced["pr"] == "uvx other-acp"


def test_built_in_identity_attaches_only_while_the_adapter_matches() -> None:
    """Exact rendered bytes decide it; nothing reads the command for meaning."""
    outcome = _resolve(block={})
    assert not isinstance(outcome, str), outcome
    _, attached = outcome
    assert attached.chains["pr"].primary.identity is not None
    assert attached.chains["pr"].primary.identity.availability_key == "anthropic"
    codex = _resolve(block=_CODEX_PR_TIER)
    assert not isinstance(codex, str), codex
    assert codex[1].chains["pr"].primary.identity is not None
    assert codex[1].chains["pr"].primary.identity.availability_key == "codex"
    arbitrary = _resolve(block={"acp_nodes": {"pr": "uvx claude-agent-acp"}})
    assert not isinstance(arbitrary, str), arbitrary
    assert arbitrary[1].chains["pr"].primary.identity is None


def test_a_fallback_enabled_arbitrary_primary_must_declare_its_own_identity() -> None:
    """It may not retain the replaced built-in's identity, and none is inferred."""
    refusal = _resolve(
        block={"acp_nodes": {"pr": {"command": "uvx mystery-acp", "fallbacks": [_FALLBACK]}}}
    )
    assert isinstance(refusal, str)
    assert "arbitrary primary" in refusal
    accepted = _resolve(
        block={
            "acp_nodes": {
                "pr": {"command": "uvx mystery-acp", **_IDENTITY, "fallbacks": [_FALLBACK]}
            }
        }
    )
    assert not isinstance(accepted, str), accepted
    assert accepted[1].chains["pr"].primary.identity is not None
    assert accepted[1].chains["pr"].primary.identity.candidate_key == _IDENTITY["candidate_key"]


def test_a_built_in_primary_may_carry_fallbacks_without_declaring_identity() -> None:
    """The built-in already HAS an identity, so demanding one would be noise."""
    outcome = _resolve(block={"acp_nodes": {"pr": {"fallbacks": [_FALLBACK]}}})
    assert not isinstance(outcome, str), outcome
    chain = outcome[1].chains["pr"]
    assert chain.primary.identity is not None
    assert len(chain.fallbacks) == 1
    assert chain.fallbacks[0].identity is not None
    assert chain.fallbacks[0].adapter.command == _FALLBACK["command"]


def test_a_legacy_acp_node_string_refuses_on_a_new_grammar_enabled_node() -> None:
    """It stays valid for a legacy node and is refused for an enabled one.

    Both halves are asserted: a check that refused the override outright
    would pass the first assertion's mirror image and still be wrong.
    """
    refusal = _resolve(
        block={"acp_nodes": {"pr": {"fallbacks": [_FALLBACK]}}}, dispatch=("pr=uvx other-acp",)
    )
    assert isinstance(refusal, str)
    assert "--acp-node" in refusal
    legacy = _resolve(block={"acp_nodes": {"pr": "uvx repo-acp"}}, dispatch=("pr=uvx other-acp",))
    assert not isinstance(legacy, str), legacy
    assert legacy[0].nodes["pr"].rendered == "uvx other-acp"
    assert legacy[1].chains["pr"].primary.identity is None


def test_a_node_repeating_one_entitlement_pair_within_its_chain_refuses() -> None:
    """Reuse across nodes is intentional; reuse within one chain is not."""
    refusal = _resolve(
        block={
            "acp_nodes": {
                "pr": {
                    "command": "uvx mystery-acp",
                    **_IDENTITY,
                    "fallbacks": [{**_FALLBACK, **_IDENTITY, "command": "uvx twin-acp"}],
                }
            }
        }
    )
    assert isinstance(refusal, str)
    assert "repeats candidate identity" in refusal


def test_a_credential_reaching_the_resolved_primary_refuses_the_dispatch() -> None:
    """The resolved adapter is scanned, not only the entry's own committed text.

    A layer BELOW the entry can contribute env the entry never mentions,
    so scanning the configuration alone would pass a fallback-enabled node
    whose rendered command still carries a token. The credential here is in
    the WORKFLOW default, which the node's own entry never mentions.

    The tolerated half is the control and it is not cosmetic: a legacy node
    with the same poisoned default must keep resolving, because the
    contract narrows nothing for a node that did not opt in.
    """
    poisoned = {**_WORKFLOW_INPUTS, "pr_adapter": f"ANTHROPIC_AUTH_TOKEN=sk-live-abc {_CLAUDE}"}
    tolerated = _resolve(block={}, workflow_inputs=poisoned)
    assert not isinstance(tolerated, str), tolerated
    leaked = _resolve(block={"acp_nodes": {"pr": dict(_IDENTITY)}}, workflow_inputs=poisoned)
    assert isinstance(leaked, str)
    assert "ANTHROPIC_AUTH_TOKEN" in leaked
    assert "sk-live-abc" not in leaked


def test_the_two_digests_separate_a_primary_replacement_from_a_chain_edit() -> None:
    """A fallback-only edit moves the full chain and leaves the generation.

    This is the discrimination the later warning lifecycle is built on, so
    both halves are asserted against each other rather than either one
    against a literal.
    """
    base = _resolve(block={"acp_nodes": {"pr": {"fallbacks": [_FALLBACK]}}})
    chain_edit = _resolve(
        block={
            "acp_nodes": {
                "pr": {"fallbacks": [_FALLBACK, {**_FALLBACK, "candidate_key": "second"}]}
            }
        }
    )
    primary_edit = _resolve(
        block={
            "acp_nodes": {
                "pr": {"command": "uvx mystery-acp", **_IDENTITY, "fallbacks": [_FALLBACK]}
            }
        }
    )
    assert not isinstance(base, str) and not isinstance(chain_edit, str)
    assert not isinstance(primary_edit, str), primary_edit
    assert base[1].chains["pr"].primary_generation == chain_edit[1].chains["pr"].primary_generation
    assert base[1].chains["pr"].full_chain != chain_edit[1].chains["pr"].full_chain
    assert base[1].chains["pr"].primary_generation != (
        primary_edit[1].chains["pr"].primary_generation
    )


def test_a_reordered_chain_is_a_different_chain() -> None:
    """Configured order is semantic, so the digest must not sort it away."""
    second = {**_FALLBACK, "candidate_key": "second"}
    forward = _resolve(block={"acp_nodes": {"pr": {"fallbacks": [_FALLBACK, second]}}})
    reverse = _resolve(block={"acp_nodes": {"pr": {"fallbacks": [second, _FALLBACK]}}})
    assert not isinstance(forward, str) and not isinstance(reverse, str)
    assert forward[1].chains["pr"].full_chain != reverse[1].chains["pr"].full_chain
    assert [entry.identity.candidate_key for entry in forward[1].chains["pr"].fallbacks] == [
        _FALLBACK["candidate_key"],
        "second",
    ]


def test_the_digests_are_stable_across_two_identical_resolutions() -> None:
    """Determinism is contractual: two runs of one configuration must agree."""
    block = {"acp_nodes": {"pr": {"fallbacks": [_FALLBACK]}}}
    first = _resolve(block=block)
    second = _resolve(block=json.loads(json.dumps(block)))
    assert not isinstance(first, str) and not isinstance(second, str)
    assert first[1].chains["pr"].full_chain == second[1].chains["pr"].full_chain
    assert first[1].chains["pr"].primary_generation == second[1].chains["pr"].primary_generation


def test_the_redacted_record_carries_structure_and_digests_but_no_env_value() -> None:
    """Command, args, env KEY NAMES, layers and digests -- and nothing else."""
    outcome = _resolve(
        block={
            **_CODEX_PR_TIER,
            "acp_nodes": {"pr": {"fallbacks": [_FALLBACK]}},
        }
    )
    assert not isinstance(outcome, str), outcome
    resolution, attached = outcome
    record = attached.chains["pr"].redacted
    assert record["env_keys"] == sorted(resolution.nodes["pr"].adapter.env)
    assert record["env_keys"]
    assert record["fallback_count"] == 1
    assert record["primary_generation_digest"] == attached.chains["pr"].primary_generation
    assert record["full_chain_digest"] == attached.chains["pr"].full_chain
    serialized = json.dumps(record)
    for value in resolution.nodes["pr"].adapter.env.values():
        assert value not in serialized
    assert _FALLBACK["command"] not in serialized


def test_only_a_new_grammar_enabled_node_is_redacted() -> None:
    """A no-fallback legacy node keeps its v107 journal record verbatim."""
    outcome = _resolve(block={"acp_nodes": {"pr": {"fallbacks": [_FALLBACK]}}})
    assert not isinstance(outcome, str), outcome
    assert set(outcome[1].redacted_nodes) == {"pr"}
    assert outcome[1].chains["review"].enabled is False


def _prepare(
    *, tmp_path: Path, acp_nodes: dict[str, Any], overrides: tuple[str, ...] = ()
) -> tuple[Any, _RecordingJournal]:
    """Drive the real dispatch seam over a written-out target repository."""
    committed = tmp_path / "workflow.toml"
    _ = committed.write_text(_WORKFLOW_TOML, encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {"acp_nodes": acp_nodes},
                }
            }
        ),
        encoding="utf-8",
    )
    journal = _RecordingJournal()
    outcome = _module(name="_dispatcher_acp_nodes").prepare_acp_nodes(
        repo=repo,
        committed=committed,
        overrides=overrides,
        journal=journal,
        work_item_id="bd-ib-qu3htl",
    )
    return (outcome, journal)


def test_the_journal_substitutes_the_structural_record_for_enabled_nodes(
    tmp_path: Path,
) -> None:
    """The whole dispatch seam, end to end, writing one journal record."""
    seam = _module(name="_dispatcher_acp_nodes")
    resolution, journal = _prepare(
        tmp_path=tmp_path,
        acp_nodes={
            "pr": {"fallbacks": [_FALLBACK]},
            "review": {"command": "uvx review-acp"},
        },
    )
    assert not isinstance(resolution, str), resolution
    [record] = [entry for entry in journal.records if entry["stage"] == seam.ACP_NODES_STAGE]
    nodes: Any = record["acp_nodes"]
    assert "adapter" not in nodes["pr"]
    assert nodes["pr"]["command"] == _CLAUDE
    assert nodes["pr"]["fallback_count"] == 1
    assert nodes["pr"]["input"] == "pr_adapter"
    assert nodes["review"]["adapter"] == "uvx review-acp"


def test_the_dispatch_seam_reports_a_chain_refusal_before_journalling(
    tmp_path: Path,
) -> None:
    """A malformed chain refuses the dispatch and writes no adapter record."""
    refusal, journal = _prepare(tmp_path=tmp_path, acp_nodes={"pr": {**_IDENTITY, "bogus": 1}})
    assert isinstance(refusal, str)
    assert "bogus" in refusal
    assert journal.records == []


def test_the_dispatch_seam_reports_an_attachment_refusal_before_journalling(
    tmp_path: Path,
) -> None:
    """A refusal raised AFTER the layers resolve still precedes the record.

    The malformed-chain test above refuses while reading configuration, so
    it cannot show that a refusal discovered during ATTACHMENT also
    reaches the operator without a run existing. The legacy `--acp-node`
    override on an enabled node is exactly such a refusal.
    """
    refusal, journal = _prepare(
        tmp_path=tmp_path,
        acp_nodes={"pr": {"fallbacks": [_FALLBACK]}},
        overrides=("pr=uvx other-acp",),
    )
    assert isinstance(refusal, str)
    assert "--acp-node" in refusal
    assert journal.records == []


def test_a_non_table_acp_nodes_value_yields_one_refusal_not_two() -> None:
    """The overlay reader already names the key; the chain reader stays quiet."""
    repository = _module(name="_acp_node_repository")
    assert repository.repository_acp_chains(block={"acp_nodes": "uvx acp"}) == {}
    assert repository.repository_acp_chains(block={}) == {}
    assert isinstance(repository.repository_acp_overlays(block={"acp_nodes": "uvx acp"}), str)


def test_a_built_in_table_maps_rendered_bytes_onto_a_domain_and_a_stable_key() -> None:
    """Both provenances appear, and neither key is parsed out of command text."""
    identities = _module(name="_acp_builtin_candidates").builtin_acp_identities(
        workflow_inputs=_WORKFLOW_INPUTS, block=_CODEX_PR_TIER
    )
    domains = {identity.availability_key for identity in identities.values()}
    assert domains == {"anthropic", "codex"}
    claude = identities[_CLAUDE]
    assert claude.availability_key == "anthropic"
    assert claude.candidate_key.startswith("builtin-anthropic-")
    assert "claude" not in claude.candidate_key
    repeat = _module(name="_acp_builtin_candidates").builtin_acp_identities(
        workflow_inputs=_WORKFLOW_INPUTS, block=_CODEX_PR_TIER
    )
    assert repeat[_CLAUDE].candidate_key == claude.candidate_key


def test_a_candidate_fingerprint_covers_identity_signatures_and_pricing() -> None:
    """Each metadata object moves the digest, so a silent edit cannot hide."""
    digests = _module(name="_acp_chain_digests")
    schema = _module(name="_acp_candidate_schema")
    adapters = _module(name="_acp_node_adapters")
    bare = schema.AcpCandidate(adapter=adapters.AcpAdapter(command="uvx acp"))
    fingerprint = digests.candidate_fingerprint(candidate=bare)
    assert fingerprint["identity"] is None
    assert fingerprint["pricing"] is None
    assert fingerprint["signatures"] == []
    identified = schema.parse_fallback_candidate(
        entry={
            **_FALLBACK,
            "pricing": {
                "model": "gpt-5.3-codex-spark",
                "input_usd_per_million": 1.0,
                "output_usd_per_million": 2.0,
                "cache_write_usd_per_million": 0.5,
                "cache_read_usd_per_million": 0.1,
            },
            "availability_signatures": [
                {
                    "source": "protocol.message",
                    "all_literals": ["usage limit"],
                    "cause": "quota",
                    "scope": "availability-domain",
                    "hold_key": "chatgpt-account",
                }
            ],
        },
        key="k",
    )
    assert not isinstance(identified, str), identified
    rich = digests.candidate_fingerprint(candidate=identified)
    assert rich["identity"] == ["codex", "gpt-5-3-codex-spark"]
    assert rich["pricing"] == "gpt-5.3-codex-spark"
    assert rich["signatures"] == [
        ["protocol.message", "quota", "availability-domain", "chatgpt-account"]
    ]
    assert digests.primary_generation_digest(primary=bare) != (
        digests.primary_generation_digest(primary=identified)
    )
