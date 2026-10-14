"""The sandbox credential-use guard, scoped to dispatches that route Codex.

`bd-ib-meejjz`, the third and last of the three surfaces. The guard enforces an
ABSOLUTE credential-use deadline over every coding-agent launch, and it is
installed by the overlay the projection leg feeds. Both of the launch routes
that reach an adapter were wrapped UNCONDITIONALLY: the `--input` pairs
`dispatch_fabro_run_inputs` renders, and the literal `acp.command` the payload
graph carries since plan `fabro-currency` P4.

WHY UNCONDITIONAL WRAPPING CANNOT SURVIVE THE PROJECTION BECOMING CONDITIONAL,
and why this is the half that breaks loudly rather than quietly. The guard FAILS
CLOSED on an absent deadline, by design -- "a guard that proceeded when blinded
would be decoration" -- so a launch wrapped by a dispatch that projected no
deadline does not run unbounded, it REFUSES with exit 78, every node, every
such dispatch. The two decisions are therefore one decision, and both read the
same routing off the plan.

THE MEASUREMENT IS THE RENDERED LAUNCH STRING, both ways. A guarded launch opens
with the guard in the executable position, ahead of the adapter and behind the
adapter's own `KEY=value` env prefix; an unguarded one is the adapter as the
resolution rendered it. Each case below asserts the prefix's presence in one
direction and its absence in the other over the SAME resolved adapters, because
an assertion in one direction alone is satisfied by a build that wraps nothing
and by a build that wraps everything.
"""

from __future__ import annotations

import argparse
import importlib
import json
import shutil
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard import (
    GUARD_SCRIPT_PATH,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    dispatch_fabro_run_inputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_materialize import (
    MaterializationRefusal,
    materialize_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan

from tests.conftest import ResolveAcpNodes

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SHIPPED_WORKFLOW = (
    _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"
)

# The exact token sequence the wrap puts in the executable position. Read from
# the guard's own constant rather than spelled, so a change to the wrap cannot
# leave these cases asserting a prefix nothing produces.
_GUARD_PREFIX = f"/bin/sh {GUARD_SCRIPT_PATH} --"

_GIT_AUTHOR_BLOCK = {"operator_name": "Operator", "operator_email": "operator@example.com"}


class _RecordingJournal:
    """Collects journal records so a materialization can be asserted on."""

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _adapter_inputs(*, tmp_path: Path, resolve: ResolveAcpNodes, routes_codex: bool) -> list[str]:
    """The `--input <name>=<adapter>` values one dispatch's plan renders."""
    plan = build_plan(
        repo=tmp_path,
        work_item_id="bd-ib-meejjz",
        workflow_toml=tmp_path / "wf.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor-co",
        acp_nodes=resolve(repo=tmp_path),
        routes_codex=routes_codex,
    )
    return [pair for pair in dispatch_fabro_run_inputs(plan=plan) if pair.endswith("acp")]


def test_an_all_claude_dispatch_launches_each_adapter_with_no_use_deadline(
    tmp_path: Path, resolve_test_acp_nodes: ResolveAcpNodes
) -> None:
    """No guard in any adapter launch, and the adapters themselves are intact.

    The second assertion is what separates "not wrapped" from "not rendered":
    every pair still carries its resolved adapter command, so the dispatch
    launches exactly what it resolved -- just with no credential-use deadline
    governing it, because this dispatch projects no credential for one to bound.
    """
    pairs = _adapter_inputs(tmp_path=tmp_path, resolve=resolve_test_acp_nodes, routes_codex=False)

    assert pairs
    assert not any(_GUARD_PREFIX in pair for pair in pairs)
    assert all("claude-agent-acp" in pair for pair in pairs)


def test_a_codex_routing_dispatch_launches_every_adapter_behind_the_guard(
    tmp_path: Path, resolve_test_acp_nodes: ResolveAcpNodes
) -> None:
    """Every launch stays wrapped where a node routes to Codex.

    One argument apart from the case above, over the same resolved adapters, so
    a build that stopped wrapping altogether passes that test and fails this
    one -- and the EVERY here is deliberate: one unwrapped node is one
    coding-agent launch outside the bound.
    """
    pairs = _adapter_inputs(tmp_path=tmp_path, resolve=resolve_test_acp_nodes, routes_codex=True)

    assert pairs
    assert all(_GUARD_PREFIX in pair for pair in pairs)


def _guarded_commands(*, guarded: bool) -> dict[str, str]:
    """The payload graph's literal `acp.command` values for one routing."""
    module = importlib.import_module(f"{_PACKAGE}._dispatcher_graph_adapters")
    return dict(
        module.guarded_adapter_commands(
            run_inputs=("implement_adapter=FOO=bar /usr/bin/agent --acp",), guarded=guarded
        )
    )


def test_the_payload_graph_literal_carries_no_guard_for_an_all_claude_dispatch() -> None:
    """The OTHER launch route, which is the one a reader is most likely to miss.

    Since plan `fabro-currency` P4 each node's resolved adapter is rendered into
    the payload graph as a LITERAL, because a templated `acp.command` kills the
    agent before the ACP protocol completes on the Petri-era engine. That
    literal is a second, independent launch route: wrapping only the `--input`
    pairs would leave it refusing with exit 78 on every node of an unprotected
    dispatch.

    The env prefix is asserted to survive in both directions, because the wrap's
    whole subtlety is that it goes AFTER the assignments and BEFORE the
    executable -- a build that dropped them would start the adapter without the
    configuration they carry.
    """
    unguarded = _guarded_commands(guarded=False)
    guarded = _guarded_commands(guarded=True)

    assert _GUARD_PREFIX not in unguarded["implement_adapter"]
    assert _GUARD_PREFIX in guarded["implement_adapter"]
    for rendered in (unguarded, guarded):
        assert rendered["implement_adapter"].startswith("FOO=bar ")
        assert rendered["implement_adapter"].endswith("/usr/bin/agent --acp")


def test_materialize_dispatch_renders_this_target_graph_with_no_guarded_launch(
    tmp_path: Path,
) -> None:
    """End to end: the shipped workflow, materialized for this repository.

    The fixture is a real copy of the SHIPPED workflow, so the candidates
    resolved are the ones this repository actually dispatches -- every one of
    them `claude-acp` -- and the graph asserted on is the file `fabro run` would
    be pointed at. This is the case that fails if the routing is resolved
    correctly and then not threaded into the render.
    """
    repo = tmp_path / "repo"
    variant = repo / ".fabro/workflows/implement-work-item"
    variant.parent.mkdir(parents=True)
    _ = shutil.copytree(_SHIPPED_WORKFLOW.parent, variant)
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"git_author": _GIT_AUTHOR_BLOCK}), encoding="utf-8"
    )

    materialized: Any = materialize_dispatch(
        args=argparse.Namespace(workflow=None, repo=str(repo)),
        repo=repo,
        work_item_id="bd-ib-meejjz",
        journal=_RecordingJournal(),
    )

    assert not isinstance(materialized, MaterializationRefusal), materialized
    assert materialized.routes_codex is False
    rendered_graph = materialized.payload.graph.read_text(encoding="utf-8")
    assert "acp.command" in rendered_graph
    assert GUARD_SCRIPT_PATH not in rendered_graph
