"""A per-dispatch `--node-timeout` reaches the credential execution allowance.

The rendered graph and the `fabro run` ceiling already carry the per-dispatch
argument layer; the credential allowance has to be computed from the same
per-node values or it under-sizes the credential wall for a dispatch that
raises a node (Scenario 89, Scenario 325).
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
from pathlib import Path
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_REQUIREMENT_MODULE = f"{_PACKAGE}._dispatcher_credential_requirement"
_SELECTION_MODULE = f"{_PACKAGE}._dispatcher_credential_selection"

_RAISED = 7200

_WORKFLOW_TOML = """_version = 1

[workflow]
graph = "workflow.fabro"

[run]
goal = "fixture"

[run.checkpoint]
commit_timeout = "15m"
"""

_GRAPH = """digraph Fixture {
    graph [
        default_max_retries=0
        stall_timeout="7200s"
    ]

    start [shape=Mdiamond, label="Start"]
    exit  [shape=Msquare, label="Exit"]

    work [
        timeout="1800s"
    ]

    start -> work
    work -> exit
}
"""


def _write_repo(*, tmp_path: Path, block: dict[str, Any] | None = None) -> Path:
    workflow_dir = tmp_path / ".fabro" / "workflows" / "implement-work-item"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    _ = (workflow_dir / "workflow.toml").write_text(_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow_dir / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {"livespec-orchestrator-beads-fabro": {"dispatcher": {} if block is None else block}}
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_the_resolver_takes_the_per_dispatch_argument_and_it_raises_the_allowance(
    tmp_path: Path,
) -> None:
    """An argument raising a node sizes the requirement like the same table entry."""
    module = importlib.import_module(_REQUIREMENT_MODULE)
    parameters = inspect.signature(module.resolve_credential_lifetime_requirement).parameters
    assert "node_timeout_arguments" in parameters, (
        "the credential requirement resolver must take the dispatch's "
        "--node-timeout arguments, or its allowance disagrees with the rendered graph"
    )
    default = module.resolve_credential_lifetime_requirement(
        repo=_write_repo(tmp_path=tmp_path / "default")
    )
    by_argument = module.resolve_credential_lifetime_requirement(
        repo=_write_repo(tmp_path=tmp_path / "argument"),
        node_timeout_arguments=(f"work={_RAISED}",),
    )
    by_table = module.resolve_credential_lifetime_requirement(
        repo=_write_repo(tmp_path=tmp_path / "table", block={"node_timeouts": {"work": _RAISED}})
    )
    assert not isinstance(default, str), default
    assert not isinstance(by_argument, str), by_argument
    assert not isinstance(by_table, str), by_table
    assert by_argument.allowance_seconds > default.allowance_seconds
    assert by_argument.allowance_seconds == by_table.allowance_seconds


def test_the_argument_wins_over_the_repository_table_in_the_allowance(tmp_path: Path) -> None:
    """The argument layer outranks a repository entry naming the same node."""
    module = importlib.import_module(_REQUIREMENT_MODULE)
    table_only = module.resolve_credential_lifetime_requirement(
        repo=_write_repo(tmp_path=tmp_path / "table", block={"node_timeouts": {"work": 3600}})
    )
    overridden = module.resolve_credential_lifetime_requirement(
        repo=_write_repo(tmp_path=tmp_path / "both", block={"node_timeouts": {"work": 3600}}),
        node_timeout_arguments=(f"work={_RAISED}",),
    )
    assert not isinstance(table_only, str), table_only
    assert not isinstance(overridden, str), overridden
    assert overridden.allowance_seconds > table_only.allowance_seconds


def test_the_post_claim_entry_point_takes_the_arguments_too(tmp_path: Path) -> None:
    """The requirement for an already-resolved workflow honours the arguments."""
    module = importlib.import_module(_REQUIREMENT_MODULE)
    repo = _write_repo(tmp_path=tmp_path)
    committed = repo / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"
    plain = module.credential_lifetime_requirement_for(committed=committed, block={})
    raised = module.credential_lifetime_requirement_for(
        committed=committed, block={}, node_timeout_arguments=(f"work={_RAISED}",)
    )
    assert not isinstance(plain, str), plain
    assert not isinstance(raised, str), raised
    assert raised.allowance_seconds > plain.allowance_seconds


def test_the_pre_claim_selection_reads_the_namespace_node_timeout(tmp_path: Path) -> None:
    """The pre-claim credential gate sizes against the dispatch's own argument."""
    module = importlib.import_module(_SELECTION_MODULE)
    repo = _write_repo(tmp_path=tmp_path)
    plain = module.selection_credential_requirement(
        args=argparse.Namespace(workflow=None, workflow_name=None), repo=repo, items=[]
    )
    raised = module.selection_credential_requirement(
        args=argparse.Namespace(
            workflow=None, workflow_name=None, node_timeout=[f"work={_RAISED}"]
        ),
        repo=repo,
        items=[],
    )
    assert not isinstance(plain, str), plain
    assert not isinstance(raised, str), raised
    assert raised.allowance_seconds > plain.allowance_seconds
