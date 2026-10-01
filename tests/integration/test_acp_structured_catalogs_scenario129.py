"""Scenario 129 and the catalogs behind it, through the real resolution seams.

Binds `SPECIFICATION/scenarios.md` "Scenario 129 — A structured candidate
renders through the catalogs and keeps the manual form as the escape hatch" and
`SPECIFICATION/contracts.md` "Agent and model catalogs", whose heading-coverage
entries both owed integration-tier coverage: "the binding must drive the real
configuration, catalog and rendering seams rather than a unit-tier stub".

SO EVERY CASE STARTS FROM A COMMITTED `.livespec.jsonc` ON DISK and resolves it
the way a dispatch does — `resolve_acp_catalogs` over the real dispatcher block,
then the real repository overlay and chain readers, then the real three-layer
merge. Nothing here constructs a catalog entry or an overlay by hand. That is
the whole point of the tier: the unit-tier modules grade each stage against
values handed to it, and a stage can be perfectly correct while nothing wires it
to the configuration an operator actually writes.

THE NO-FETCH INVARIANT IS ASSERTED STRUCTURALLY, not by watching for a request.
"The Dispatcher MUST NOT fetch a registry, a provider, or a catalog service at
dispatch time" is a claim about what the code CANNOT do, and a test that merely
observed no traffic during one resolution would pass equally against a build
that fetches on a cache miss. The catalog modules are therefore checked for the
ABSENCE of any import that could perform one — a fetch cannot exist if the API
to perform it is absent.

THE MANUAL FORM IS ASSERTED TO DERIVE NOTHING, which is the escape hatch's whole
content. Asserting that it resolves would pass against a build that silently
filled its identity in from the catalogs; the discriminating observation is that
the identity it comes back with is the one the operator WROTE, and that a manual
entry naming no agent reaches no catalog at all.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_catalogs import (
    catalog_snapshot_record,
    resolve_acp_catalogs,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import resolve_acp_nodes
from livespec_orchestrator_beads_fabro.commands._acp_node_repository import (
    repository_acp_chains,
    repository_acp_overlays,
)
from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)

_CODEX_PATH = "/opt/livespec/codex-acp/bin/codex-acp"
_CODEX_PINNED = (
    'CODEX_CONFIG=\'{"approval_policy":"never","model":"gpt-5.5",'
    '"model_reasoning_effort":"high","sandbox_mode":"danger-full-access"}\' '
    f"INITIAL_AGENT_MODE=agent-full-access {_CODEX_PATH}"
)

# A deliberately different workflow default per node, so a structured entry
# that failed to apply renders the sentinel rather than a plausible adapter.
_WORKFLOW_INPUTS: dict[str, str] = {
    "implement_adapter": "WORKFLOW=implement placeholder-adapter",
    "fix_adapter": "WORKFLOW=fix placeholder-adapter",
    "review_fix_adapter": "WORKFLOW=review_fix placeholder-adapter",
    "pr_adapter": "WORKFLOW=pr placeholder-adapter",
    "review_adapter": "WORKFLOW=review placeholder-adapter",
    "disposition_adapter": "WORKFLOW=disposition placeholder-adapter",
}

# The modules that make up the catalogs and the structured render. The no-fetch
# invariant is a property of this whole set, not of any one of them.
_CATALOG_MODULES = (
    "_acp_agent_catalog",
    "_acp_agent_entry",
    "_acp_agent_mechanism",
    "_acp_catalog_overrides",
    "_acp_catalogs",
    "_acp_model_catalog",
    "_acp_model_entry",
    "_acp_structured_render",
)
_FETCH_IMPORTS = (
    "urllib",
    "http.client",
    "httpx",
    "requests",
    "socket",
    "subprocess",
    "ssl",
    "ftplib",
    "telnetlib",
    "xmlrpc",
)


def _write_config(*, repo: Path, dispatcher: dict[str, Any]) -> None:
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}),
        encoding="utf-8",
    )


def _resolved(*, repo: Path) -> Any:
    """Every node's adapter and chain, resolved the way a dispatch resolves them.

    The dispatcher block is READ FROM DISK and the catalogs are resolved from
    that block, so a per-repository catalog addition reaches the render by the
    same route an operator's would.
    """
    block = dispatcher_block(cwd=repo)
    catalogs = resolve_acp_catalogs(block=block)
    assert not isinstance(catalogs, str), catalogs
    overlays = repository_acp_overlays(block=block, catalogs=catalogs)
    if isinstance(overlays, str):
        return overlays
    chains = repository_acp_chains(block=block, catalogs=catalogs)
    if isinstance(chains, str):
        return chains
    resolution = resolve_acp_nodes(
        workflow_inputs=_WORKFLOW_INPUTS, repository=overlays, dispatch={}
    )
    assert not isinstance(resolution, str), resolution
    return (resolution, chains)


def _rendered(*, repo: Path, node: str) -> str:
    outcome = _resolved(repo=repo)
    assert not isinstance(outcome, str), outcome
    resolution, _ = outcome
    return resolution.nodes[node].rendered


def _chain(*, repo: Path, node: str) -> Any:
    outcome = _resolved(repo=repo)
    assert not isinstance(outcome, str), outcome
    _, chains = outcome
    return chains[node]


def _refusal(*, repo: Path) -> str:
    outcome = _resolved(repo=repo)
    assert isinstance(outcome, str), f"expected a refusal, got a resolution: {outcome!r}"
    return outcome


def test_a_structured_codex_entry_renders_from_the_catalogs_with_derived_identity(
    tmp_path: Path,
) -> None:
    """Scenario 129: the launch distribution with that model and effort applied."""
    _write_config(
        repo=tmp_path,
        dispatcher={
            "acp_nodes": {"implement": {"agent": "codex-acp", "model": "gpt-5.5", "effort": "high"}}
        },
    )

    assert _rendered(repo=tmp_path, node="implement") == _CODEX_PINNED
    identity = _chain(repo=tmp_path, node="implement").identity
    assert identity is not None
    assert identity.candidate_key == "codex-acp/openai/gpt-5.5"
    assert identity.availability_key == "codex"


def test_a_multi_provider_agent_takes_a_provider_qualified_model(tmp_path: Path) -> None:
    """Scenario 129: identity derives from the agent, provider and model triple.

    `opencode` is multi-provider, so a BARE model id has no provider to resolve
    against. The qualified form is asserted to work and the bare form to refuse,
    because a build that silently picked some provider would render and identify
    the candidate under a provider nobody named.
    """
    _write_config(
        repo=tmp_path,
        dispatcher={
            "acp_nodes": {
                "implement": {
                    "agent": "codex-acp",
                    "model": "gpt-5.5",
                    "effort": "high",
                    "fallbacks": [{"agent": "opencode", "model": "zai/glm-5.2"}],
                }
            }
        },
    )

    [fallback] = _chain(repo=tmp_path, node="implement").fallbacks
    assert fallback.identity.candidate_key == "opencode/zai/glm-5.2"

    _write_config(
        repo=tmp_path,
        dispatcher={"acp_nodes": {"implement": {"agent": "opencode", "model": "glm-5.2"}}},
    )
    assert "multi-provider" in _refusal(repo=tmp_path)


def test_the_manual_form_is_accepted_with_no_field_derived_from_any_catalog(
    tmp_path: Path,
) -> None:
    """Scenario 129: the escape hatch derives NOTHING.

    The identity that comes back must be the one the operator WROTE. A build
    that filled any field in from the catalogs would still "accept" the entry,
    so acceptance alone is not the observation that discriminates.
    """
    declared = {
        "display_name": "Hand-written ACP",
        "candidate_key": "hand/written/acp",
        "availability_key": "hand-written",
    }
    _write_config(
        repo=tmp_path,
        dispatcher={
            "acp_nodes": {
                "implement": {
                    "command": "uvx some-other-acp",
                    "env": {"SOME_MODEL": "whatever"},
                    **declared,
                }
            }
        },
    )

    # The workflow default's own env survives, because a manual TABLE is a
    # per-FIELD overlay whose `env` MERGES -- the ratified behaviour, and the
    # discriminator from a STRUCTURED entry, which renders a complete adapter
    # and replaces the environment outright.
    assert _rendered(repo=tmp_path, node="implement") == (
        "SOME_MODEL=whatever WORKFLOW=implement uvx some-other-acp"
    )
    identity = _chain(repo=tmp_path, node="implement").identity
    assert identity is not None
    assert identity.display_name == declared["display_name"]
    assert identity.candidate_key == declared["candidate_key"]
    assert identity.availability_key == declared["availability_key"]


def test_mixed_unknown_or_unresolvable_entries_refuse_before_claim(tmp_path: Path) -> None:
    """Scenario 129: each of the three faults refuses naming the entry."""
    faults = (
        ({"agent": "claude-acp", "model": "claude-opus-5", "command": "uvx acp"}, "command"),
        ({"agent": "no-such-agent", "model": "claude-opus-5"}, "no-such-agent"),
        ({"agent": "claude-acp", "model": "no-such-model"}, "no-such-model"),
    )

    for entry, needle in faults:
        _write_config(repo=tmp_path, dispatcher={"acp_nodes": {"implement": entry}})
        refusal = _refusal(repo=tmp_path)

        assert "dispatcher.acp_nodes.implement" in refusal, entry
        assert needle in refusal, entry


def test_rendering_is_deterministic_across_two_resolutions(tmp_path: Path) -> None:
    """Scenario 129: the same snapshot and entry render identical bytes.

    Two independent RESOLUTIONS rather than two calls to one function: two
    calls would prove the renderer is not stateful, while two resolutions prove
    the whole path — block read, catalog resolution, render, parse, merge — is,
    which is the claim the contract makes about a dispatch.
    """
    entry = {"agent": "codex-acp", "model": "gpt-5.5", "effort": "high"}
    _write_config(repo=tmp_path, dispatcher={"acp_nodes": {"implement": entry}})

    first = _rendered(repo=tmp_path, node="implement")
    second = _rendered(repo=tmp_path, node="implement")

    assert first == second == _CODEX_PINNED


def test_a_per_repository_catalog_addition_reaches_the_render(tmp_path: Path) -> None:
    """The catalogs contract: a repository MAY add entries under the closed grammar.

    This is what makes the catalogs a CONFIGURATION surface rather than a
    constant. The added model is one the shipped catalog does not declare, so a
    build that ignored `dispatcher.model_catalog` would refuse rather than
    render — the failure is unmistakable in either direction.
    """
    _write_config(
        repo=tmp_path,
        dispatcher={
            "model_catalog": {
                "openai/gpt-5.9-fictional": {
                    "canonical_id": "gpt-5.9-fictional",
                    "display_name": "GPT-5.9 Fictional",
                }
            },
            "acp_nodes": {
                "implement": {
                    "agent": "codex-acp",
                    "model": "gpt-5.9-fictional",
                    "effort": "high",
                }
            },
        },
    )

    rendered = _rendered(repo=tmp_path, node="implement")

    assert '"model":"gpt-5.9-fictional"' in rendered
    assert rendered.endswith(_CODEX_PATH)


def test_an_unknown_catalog_key_refuses_before_claim(tmp_path: Path) -> None:
    """The catalogs contract: "an unknown key refuses before claim"."""
    _write_config(
        repo=tmp_path,
        dispatcher={
            "model_catalog": {
                "openai/gpt-5.9-fictional": {
                    "canonical_id": "gpt-5.9-fictional",
                    "display_name": "GPT-5.9 Fictional",
                    "not_a_catalog_key": True,
                }
            }
        },
    )
    block = dispatcher_block(cwd=tmp_path)

    refusal = resolve_acp_catalogs(block=block)

    assert isinstance(refusal, str), refusal
    assert "not_a_catalog_key" in refusal


def test_the_catalogs_record_their_registry_snapshot_digest_and_date() -> None:
    """The catalogs contract: the snapshot digest and seed date are recorded."""
    snapshot = catalog_snapshot_record()

    assert snapshot["agent_catalog_digest"]
    assert snapshot["model_catalog_digest"]
    assert snapshot["registry_snapshot_date"]


def test_no_catalog_module_can_fetch_a_registry_or_a_provider() -> None:
    """The no-fetch invariant, asserted as an ABSENT CAPABILITY.

    "The Dispatcher MUST NOT fetch a registry, a provider, or a catalog service
    at dispatch time" is a claim about what the code cannot do. Observing that
    one resolution issued no traffic would pass equally against a build that
    fetches only on a cache miss, so what is checked is that the API to perform
    a fetch is not imported at all.
    """
    for name in _CATALOG_MODULES:
        source = (_COMMANDS / f"{name}.py").read_text(encoding="utf-8")
        imported = [
            line
            for line in source.splitlines()
            if line.startswith(("import ", "from ")) and any(mod in line for mod in _FETCH_IMPORTS)
        ]

        assert imported == [], f"{name} imports a fetch-capable module: {imported}"
