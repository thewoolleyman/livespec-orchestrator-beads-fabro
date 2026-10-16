"""The SELECTED candidate's adapter is the one the submitted graph carries.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "at every dispatch and every re-dispatch it MUST render, for each ACP
node, exactly ONE candidate as that node's literal adapter -- the candidate
"Per-node selection" below chooses -- and the engine runs that one adapter with
no knowledge of the other candidates." Scenario 127 states the consequence:
"candidate one's adapter is the only adapter rendered for that node".

THIS IS A DIFFERENT CLAIM FROM THE SELECTION ITSELF, and the gap between them is
exactly where a correct selection stops short of a correct dispatch. The
resolution carries two renderings of each node's adapter: the per-node
`ResolvedAcpNode`, and the `--input <name>=<adapter>` pairs the graph's
`acp.command` attributes are rewritten from. A selection that moved the first
and left the second produces a resolution that REPORTS the fallback while the
engine runs the primary -- and nothing downstream disagrees, because both
strings are well-formed adapters of candidates this node really declares.

THE PRIMARY'S COMMAND IS ASSERTED ABSENT FROM THE WHOLE RENDERED GRAPH, not
merely different from the selected node's attribute. "the only adapter rendered
for that node" is a claim about what is NOT there, and a graph that carried both
-- one in the attribute and one in a stale run input -- satisfies every
assertion about the fallback's presence.

THE UNHELD CONTROL IS LOAD-BEARING for the same reason it is in the selection's
own tests: without it, a rewrite that always took the last candidate would
satisfy the positive case exactly as well as a correct one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_candidate_preflight import PreflightInputs
from livespec_orchestrator_beads_fabro.commands._acp_catalogs import resolve_acp_catalogs
from livespec_orchestrator_beads_fabro.commands._acp_hold_ledger import AcpHoldLedger
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import AcpAvailabilityHold
from livespec_orchestrator_beads_fabro.commands._acp_node_repository import repository_acp_chains
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import (
    AcpPreflightVerdict,
    build_acp_preflight_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_chain_sources import (
    repository_acp_chain_sources,
    workflow_scoped_dispatcher_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_nodes import prepare_acp_nodes
from livespec_orchestrator_beads_fabro.commands._dispatcher_graph_adapters import (
    guarded_adapter_commands,
    render_acp_commands,
)

_NODE = "implement"
_PRIMARY_DOMAIN = "primary-domain"
_FALLBACK_DOMAIN = "fallback-domain"
_PRIMARY_COMMAND = "primary-acp"
_FALLBACK_COMMAND = "fallback-acp"

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


class _RecordingJournal:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _primary_entry() -> dict[str, Any]:
    return {
        "display_name": "Primary adapter",
        "candidate_key": "primary-model",
        "availability_key": _PRIMARY_DOMAIN,
        "command": _PRIMARY_COMMAND,
        "args": ["--stdio"],
        "env": {"PRIMARY_BASE_URL": "https://primary.example"},
    }


def _chained_entry() -> dict[str, Any]:
    return {
        **_primary_entry(),
        "fallbacks": [
            {
                "display_name": "Fallback adapter",
                "candidate_key": "fallback-model",
                "availability_key": _FALLBACK_DOMAIN,
                "command": _FALLBACK_COMMAND,
                "args": ["--stdio"],
                "env": {"FALLBACK_BASE_URL": "https://fallback.example"},
            }
        ],
    }


def _repo(*, tmp_path: Path) -> Path:
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
                    "dispatcher": {"acp_nodes": {_NODE: _chained_entry()}}
                },
            }
        ),
        encoding="utf-8",
    )
    return repo


def _domain_hold(*, hold_key: str) -> AcpAvailabilityHold:
    return AcpAvailabilityHold(
        schema_version=1,
        observation_id="acp-obs-0123456789abcdef",
        scope="availability-domain",
        hold_key=hold_key,
        candidate_key=None,
        cause="quota",
        occurred_at="2026-10-16T10:00:00Z",
        expires_at="2026-10-16T22:00:00Z",
    )


def _verdict(*, repo: Path, holds: tuple[AcpAvailabilityHold, ...]) -> AcpPreflightVerdict:
    """The verdict admission would resolve, through the real reader chain."""
    block = workflow_scoped_dispatcher_block(repo=repo)
    catalogs = resolve_acp_catalogs(block=block)
    assert not isinstance(catalogs, str), catalogs
    declared = repository_acp_chains(block=block, catalogs=catalogs)
    assert not isinstance(declared, str), declared
    resolved = repository_acp_chain_sources(
        repo=repo, block=block, declared=declared, catalogs=catalogs
    )
    assert not isinstance(resolved, str), resolved
    chains, graph_text, builtin_pairs = resolved
    return build_acp_preflight_verdict(
        chains=chains,
        graph_text=graph_text,
        ledger=AcpHoldLedger(holds=holds, unobservable=(), observation_ids=frozenset()),
        inputs=PreflightInputs(holds=holds, builtin_pairs=builtin_pairs),
    )


def _rendered_graph(*, repo: Path, holds: tuple[AcpAvailabilityHold, ...]) -> Any:
    """One dispatch's graph, rendered exactly as the payload materializer does."""
    workflow = repo / ".fabro" / "workflows" / "implement-work-item"
    resolution = prepare_acp_nodes(
        repo=repo,
        committed=workflow / "workflow.toml",
        overrides=(),
        journal=_RecordingJournal(),
        work_item_id="bd-ib-wvj4rk",
        verdict=_verdict(repo=repo, holds=holds),
    )
    assert not isinstance(resolution, str), resolution
    rendered = render_acp_commands(
        graph_text=(workflow / "workflow.fabro").read_text(encoding="utf-8"),
        adapters=guarded_adapter_commands(run_inputs=resolution.run_inputs),
    )
    assert not isinstance(rendered, str), rendered
    return rendered


def test_the_selected_fallback_is_the_only_adapter_the_graph_carries(tmp_path: Path) -> None:
    """Scenario 127: the held primary's command appears nowhere in the payload."""
    repo = _repo(tmp_path=tmp_path)

    rendered = _rendered_graph(repo=repo, holds=(_domain_hold(hold_key=_PRIMARY_DOMAIN),))

    assert _FALLBACK_COMMAND in rendered.node_commands[_NODE]
    assert _PRIMARY_COMMAND not in rendered.node_commands[_NODE]
    assert _FALLBACK_COMMAND in rendered.text
    assert _PRIMARY_COMMAND not in rendered.text


def test_an_unheld_primary_is_still_the_adapter_the_graph_carries(tmp_path: Path) -> None:
    """The control: the rewrite follows the selection rather than the chain's tail.

    Without it, a rewrite that rendered the LAST candidate -- or that always
    rendered a fallback when one exists -- satisfies the case above exactly as
    well as a correct one does.
    """
    repo = _repo(tmp_path=tmp_path)

    rendered = _rendered_graph(repo=repo, holds=(_domain_hold(hold_key=_FALLBACK_DOMAIN),))

    assert _PRIMARY_COMMAND in rendered.node_commands[_NODE]
    assert _FALLBACK_COMMAND not in rendered.text


def test_a_node_the_chain_table_never_mentions_keeps_its_workflow_default(
    tmp_path: Path,
) -> None:
    """Selection moves one node's bytes and leaves every other node's alone.

    `review` is declared by the workflow and configured by nobody, so its
    adapter must stay the workflow default whatever happens to `implement` --
    the additive guarantee read at the level of the rendered payload rather than
    of the resolution.
    """
    repo = _repo(tmp_path=tmp_path)

    rendered = _rendered_graph(repo=repo, holds=(_domain_hold(hold_key=_PRIMARY_DOMAIN),))

    assert "claude-acp" in rendered.node_commands["review"]
    assert _FALLBACK_COMMAND not in rendered.node_commands["review"]
