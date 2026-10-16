"""The per-node run labels name the SELECTED candidate's entitlement.

Binds the "Per-node selection" paragraph of `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority" to the run labels a dispatch
stamps: the labels identify the selected candidate's `availability_key` and
`candidate_key` as the node's candidate entitlement.

WHY THIS IS A CORRECTNESS CLAIM AND NOT A COSMETIC ONE. The labels are the ONLY
venue a provider-limit attribution can read the executed candidate off --
`_fabro_executed_candidate` resolves them by these exact keys, and
`contracts.md` requires the provider be "attributed from the recorded executed
candidate identity, never inferred from a shared message literal". A label
naming the candidate that was SKIPPED is a perfectly well-formed entitlement,
so no surface downstream can tell it from the truth: a ceiling spent on the
fallback would be recorded against the primary's allowance, holding an account
nothing spent while the exhausted one stayed unheld. That is the same
misattribution, in both directions at once, that the executed-candidate
attribution exists to close -- arriving through the label instead of through
the cause text.

THE UNHELD CASE IS A CONTROL AND IS NOT OPTIONAL. An implementation that read
the LAST candidate, or the fallback unconditionally, would satisfy the held case
exactly as well as a correct one does. Only the pair can fail for the right
reason: the same two-candidate chain, graded once with the primary held and once
without, must name different entitlements.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_NODE = "implement"
_ITEM = "bd-ib-wvj4rk"

_PRIMARY_DOMAIN = "primarydomain"
_PRIMARY_KEY = "primarymodel"
_FALLBACK_DOMAIN = "fallbackdomain"
_FALLBACK_KEY = "fallbackmodel"

_WORKFLOW_TOML = """_version = 1

[workflow]
graph = "workflow.fabro"

[run.inputs]
implement_adapter = "npx -y claude-acp"
review_adapter = "npx -y claude-acp"

[run.environment]
id = "livespec-ci"
"""

_WORKFLOW_GRAPH = """digraph implement {
    graph [stall_timeout="7200s"]
    start [shape=Mdiamond, label="Start"]
    exit  [shape=Msquare, label="Exit"]
    implement [backend="acp", acp.command="{{ inputs.implement_adapter }}", timeout="60s"]
    review    [backend="acp", acp.command="{{ inputs.review_adapter }}", timeout="60s"]
    start -> implement
    implement -> review
    review -> exit
}
"""


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


class _Journal:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _manual_primary() -> dict[str, Any]:
    return {
        "display_name": "Primary adapter",
        "candidate_key": _PRIMARY_KEY,
        "availability_key": _PRIMARY_DOMAIN,
        "command": "primary-acp",
        "args": ["--stdio"],
        "env": {"PRIMARY_BASE_URL": "https://primary.example"},
    }


def _manual_fallback() -> dict[str, Any]:
    return {
        "display_name": "Fallback adapter",
        "candidate_key": _FALLBACK_KEY,
        "availability_key": _FALLBACK_DOMAIN,
        "command": "fallback-acp",
        "args": ["--stdio"],
        "env": {"FALLBACK_BASE_URL": "https://fallback.example"},
    }


def _repo(*, tmp_path: Path) -> Path:
    """A repo whose `implement` node declares a two-candidate chain.

    `review` is configured with its own manual adapter rather than left at the
    workflow default, so this node's labels are the only ones under test and a
    built-in identity attaching to the default cannot be mistaken for them.
    """
    repo = tmp_path / "repo"
    workflow = repo / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    _ = (workflow / "workflow.toml").write_text(_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow / "workflow.fabro").write_text(_WORKFLOW_GRAPH, encoding="utf-8")
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "git_author": {
                    "operator_name": "Operator",
                    "operator_email": "operator@example.com",
                },
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {
                        "acp_nodes": {
                            _NODE: {**_manual_primary(), "fallbacks": [_manual_fallback()]},
                            "review": _manual_fallback(),
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return repo


def _domain_hold(*, hold_key: str) -> Any:
    records = _module(name="_acp_hold_records")
    return records.AcpAvailabilityHold(
        schema_version=1,
        observation_id="acp-obs-0123456789abcdef",
        scope="availability-domain",
        hold_key=hold_key,
        candidate_key=None,
        cause="quota",
        occurred_at="2026-10-16T10:00:00Z",
        expires_at="2026-10-16T22:00:00Z",
    )


def _verdict(*, repo: Path, holds: tuple[Any, ...]) -> Any:
    sources = _module(name="_dispatcher_acp_chain_sources")
    catalogs_module = _module(name="_acp_catalogs")
    repository = _module(name="_acp_node_repository")
    ledger_module = _module(name="_acp_hold_ledger")
    preflight = _module(name="_acp_candidate_preflight")
    verdicts = _module(name="_acp_preflight_verdict")

    block = sources.workflow_scoped_dispatcher_block(repo=repo)
    catalogs = catalogs_module.resolve_acp_catalogs(block=block)
    assert not isinstance(catalogs, str), catalogs
    declared = repository.repository_acp_chains(block=block, catalogs=catalogs)
    assert not isinstance(declared, str), declared
    resolved = sources.repository_acp_chain_sources(
        repo=repo, block=block, declared=declared, catalogs=catalogs
    )
    assert not isinstance(resolved, str), resolved
    chains, graph_text, builtin_pairs = resolved
    return verdicts.build_acp_preflight_verdict(
        chains=chains,
        graph_text=graph_text,
        ledger=ledger_module.AcpHoldLedger(
            holds=holds, unobservable=(), observation_ids=frozenset()
        ),
        inputs=preflight.PreflightInputs(holds=holds, builtin_pairs=builtin_pairs),
    )


def _labels(*, repo: Path, holds: tuple[Any, ...]) -> tuple[str, ...]:
    """The label pairs a dispatch of this repo would carry."""
    nodes = _module(name="_dispatcher_acp_nodes")
    labels = _module(name="_dispatcher_run_labels")
    resolution = nodes.prepare_acp_nodes(
        repo=repo,
        committed=repo / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml",
        overrides=(),
        journal=_Journal(),
        work_item_id=_ITEM,
        verdict=_verdict(repo=repo, holds=holds),
    )
    assert not isinstance(resolution, str), resolution
    return labels.dispatch_run_label_pairs(repo=repo, acp_nodes=resolution)


def test_a_held_primary_labels_the_node_with_the_selected_fallbacks_entitlement(
    tmp_path: Path,
) -> None:
    """The entitlement the run would actually spend, not the one it skipped."""
    repo = _repo(tmp_path=tmp_path)

    pairs = _labels(repo=repo, holds=(_domain_hold(hold_key=_PRIMARY_DOMAIN),))

    assert f"livespec.acp.{_NODE}.availability={_FALLBACK_DOMAIN}" in pairs, pairs
    assert f"livespec.acp.{_NODE}.candidate={_FALLBACK_KEY}" in pairs, pairs
    # The skipped primary's entitlement is a well-formed label naming an
    # allowance this run never touches, so its ABSENCE is the whole claim.
    assert f"livespec.acp.{_NODE}.availability={_PRIMARY_DOMAIN}" not in pairs, pairs
    assert f"livespec.acp.{_NODE}.candidate={_PRIMARY_KEY}" not in pairs, pairs


def test_an_unheld_primary_still_labels_the_node_with_the_primarys_entitlement(
    tmp_path: Path,
) -> None:
    """The CONTROL: the same chain, graded with nothing held, names position zero.

    Without this, an implementation that labelled the last candidate -- or the
    fallback unconditionally -- would pass the case above while being wrong for
    every dispatch whose primary is healthy, which is nearly all of them.
    """
    repo = _repo(tmp_path=tmp_path)

    pairs = _labels(repo=repo, holds=(_domain_hold(hold_key="an-unrelated-domain"),))

    assert f"livespec.acp.{_NODE}.availability={_PRIMARY_DOMAIN}" in pairs, pairs
    assert f"livespec.acp.{_NODE}.candidate={_PRIMARY_KEY}" in pairs, pairs
    assert f"livespec.acp.{_NODE}.candidate={_FALLBACK_KEY}" not in pairs, pairs
