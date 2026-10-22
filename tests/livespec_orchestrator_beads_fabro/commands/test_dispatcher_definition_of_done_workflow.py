"""The Definition-of-Done workflow-node admission gate.

The gate is intentionally exercised through the shared pre-dispatch wall as
well as directly.  A validator that found the right missing node after the
admission valve would still leave the item claimed, which is the failure this
gate prevents.

NO CASE HERE REPLACES THE VARIANT RESOLUTION, and that is the point of the
module rather than a detail of it.  The gate reads a repository off disk: the
variant resolution, the run config and the graph are all inputs it can meet in
a fault state, and a stub standing in for any of them hands the gate a
well-formed answer the real path cannot promise.  Every case therefore drives
the real `criteria_wall_variant`, which is what lets the input-fault cases below
fail for the reason they name — a bare `tmp_path` target carries no
`.livespec.jsonc`, so the resolution degrades to the ARMED reserved variant and
the gate goes on to validate it, instead of raising
`ConnectionPrefixMissingError` out of the wall.

THE FOUR INPUT-FAULT CASES ARE EACH OTHER'S CONTROL, because every one of them
is a state in which the pre-repair gate produced a TRACEBACK out of the
pre-dispatch wall rather than a refusal: a run config declaring no
`[workflow] graph`, a declared graph file that is absent, a graph the shared
parser deliberately refuses, and a run config that cannot be read at all.  A
gate that answered `None` for all four would be worse than the traceback it
replaces — it would admit exactly the fork this gate exists to stop — so each
case asserts the refusal NAMES the file and the finding, and the two admitted
cases are what keep "refuses everything" from passing.

THE TWO REGISTERED-VARIANT CASES assert the resolved variant's own DIRECTORY
reaches `workflow_toml`, which nothing else here can observe: the reserved
workflow and a registered variant are both resolvable, so a gate that dropped
the directory would still validate a real graph — the bundled one — and admit a
registered variant whose own graph is incomplete.  The groom case is the
exemption's only cover, and it is a real pinned groom variant rather than a
stand-in so the kind is read off the manifest the dispatch would read.
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._store_dispatch_workflow import record_dispatch_workflow
from livespec_orchestrator_beads_fabro.commands import _dispatcher_pre_dispatch_wall as wall
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done_workflow"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
    / "_dispatcher_definition_of_done_workflow.py"
)
_REQUIRED_NODES = ("dod_gate", "proof_capture", "proof_verify")
_GROOM_VARIANT = "groom-cut"
_IMPLEMENT_VARIANT = "slice"
_GROOM_DIR = f".fabro/workflows/{_GROOM_VARIANT}"
_IMPLEMENT_DIR = f".fabro/workflows/{_IMPLEMENT_VARIANT}"
_GROOM_MANIFEST = '[workflow]\ngraph = "workflow.fabro"\n\n[run.inputs]\nworkflow_kind = "groom"\n'
_MANIFEST = '[workflow]\ngraph = "workflow.fabro"\n'


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(*, item_id: str = "bd-ib-7k7re5") -> WorkItem:
    return WorkItem(
        id=item_id,
        type="bug",
        status="ready",
        title="Workflow-node admission gate",
        description="Refuse an incomplete implement workflow before the claim.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-22T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="The dispatcher refuses an incomplete implement workflow.",
    )


def _graph_text(*, nodes: tuple[str, ...], extra: str = "") -> str:
    declarations = "\n".join(f'{node} [label="{node}"]' for node in nodes)
    return f"digraph ImplementWorkItem {{\n{declarations}\n{extra}}}\n"


def _write_workflow(
    *,
    root: Path,
    nodes: tuple[str, ...],
    directory: str = ".fabro/workflows/implement-work-item",
    manifest_text: str = _MANIFEST,
    graph: bool = True,
    extra: str = "",
) -> Path:
    workflow = root / directory
    workflow.mkdir(parents=True)
    manifest = workflow / "workflow.toml"
    _ = manifest.write_text(manifest_text, encoding="utf-8")
    if graph:
        _ = (workflow / "workflow.fabro").write_text(
            _graph_text(nodes=nodes, extra=extra), encoding="utf-8"
        )
    return manifest


def _registering_repo(*, tmp_path: Path) -> Path:
    """A target registering one groom-kind and one implement-kind variant."""
    repo = tmp_path / "target"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                    "dispatcher": {
                        "workflows": {
                            _GROOM_VARIANT: _GROOM_DIR,
                            _IMPLEMENT_VARIANT: _IMPLEMENT_DIR,
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return repo


def _pinned(*, item_id: str, workflow: str) -> WorkItem:
    item = _item(item_id=item_id)
    append_work_item(path=_config(), item=item)
    record_dispatch_workflow(path=_config(), work_item_id=item_id, workflow=workflow)
    return item


def _module() -> object:
    """Import the new validator only after a genuine, observable Red assertion."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


def _args(*, repo: Path, workflow: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(repo=str(repo), workflow=workflow, workflow_name=None)


def _refusal(
    *, repo: Path, item: WorkItem | None = None, workflow: str | None = None
) -> str | None:
    module = _module()
    return module.definition_of_done_workflow_refusal(
        args=_args(repo=repo, workflow=workflow), repo=repo, items=[item or _item()]
    )


@pytest.mark.parametrize("missing", _REQUIRED_NODES)
def test_each_missing_required_node_refuses_and_names_the_resolved_workflow_path(
    tmp_path: Path, missing: str
) -> None:
    repo = tmp_path / "target"
    workflow = _write_workflow(
        root=repo, nodes=tuple(node for node in _REQUIRED_NODES if node != missing)
    )

    refusal = _refusal(repo=repo)

    assert refusal is not None
    assert missing in refusal
    assert str(workflow) in refusal
    assert "no claim was taken" in refusal
    assert "no Fabro run was created" in refusal


def test_the_bundled_workflow_with_all_required_nodes_is_admitted(tmp_path: Path) -> None:
    repo = tmp_path / "target"
    repo.mkdir()

    assert _refusal(repo=repo) is None


def test_a_target_local_workflow_with_all_required_nodes_is_admitted(tmp_path: Path) -> None:
    repo = tmp_path / "target"
    _ = _write_workflow(root=repo, nodes=_REQUIRED_NODES)

    assert _refusal(repo=repo) is None


def test_a_run_config_declaring_no_graph_refuses_naming_the_run_config(tmp_path: Path) -> None:
    """A manifest with no `[workflow] graph` names no graph to read.

    `workflow_graph_path` answers None, which the pre-repair gate cast to a
    `Path` and dereferenced — an `AttributeError` out of the pre-dispatch wall.
    """
    repo = tmp_path / "target"
    workflow = _write_workflow(
        root=repo, nodes=_REQUIRED_NODES, manifest_text="[workflow]\n", graph=False
    )

    refusal = _refusal(repo=repo)

    assert refusal is not None
    assert str(workflow) in refusal
    assert "[workflow] graph" in refusal
    assert "no claim was taken" in refusal


def test_an_absent_declared_graph_file_refuses_naming_the_graph(tmp_path: Path) -> None:
    """A declared graph that is not there is unreadable, not a crash."""
    repo = tmp_path / "target"
    workflow = _write_workflow(root=repo, nodes=_REQUIRED_NODES, graph=False)

    refusal = _refusal(repo=repo)

    assert refusal is not None
    assert str(workflow.parent / "workflow.fabro") in refusal
    assert "could not be read" in refusal
    assert "no claim was taken" in refusal


def test_a_graph_the_shared_parser_refuses_is_refused_carrying_its_finding(
    tmp_path: Path,
) -> None:
    """The parser's own refusal rides the gate's, rather than being dereferenced.

    The graph declares all three required nodes, so an admitted answer here
    could only come from a gate that never reached the parse at all — and the
    `--` edge is one of the constructs `parse_dot_graph` documents as refused.
    """
    repo = tmp_path / "target"
    workflow = _write_workflow(
        root=repo, nodes=_REQUIRED_NODES, extra="dod_gate -- proof_capture\n"
    )

    refusal = _refusal(repo=repo)

    assert refusal is not None
    assert str(workflow.parent / "workflow.fabro") in refusal
    assert "undirected `--` edge" in refusal
    assert "no claim was taken" in refusal


def test_an_unreadable_run_config_refuses_naming_it(tmp_path: Path) -> None:
    """An explicit `--workflow` outranks every registry step, absent or not."""
    repo = tmp_path / "target"
    repo.mkdir()
    absent = tmp_path / "absent" / "workflow.toml"

    refusal = _refusal(repo=repo, workflow=str(absent))

    assert refusal is not None
    assert str(absent) in refusal
    assert "could not be read" in refusal
    assert "no claim was taken" in refusal


def test_a_registered_implement_variants_own_graph_is_the_one_validated(
    tmp_path: Path,
) -> None:
    """The resolved variant's DIRECTORY reaches `workflow_toml`.

    The reserved workflow is left complete and the registered variant's graph is
    not, so a refusal can only have come from the registered directory — which a
    gate that dropped the resolved directory would never have read.
    """
    repo = _registering_repo(tmp_path=tmp_path)
    _ = _write_workflow(root=repo, nodes=_REQUIRED_NODES)
    variant = _write_workflow(root=repo, nodes=("dod_gate",), directory=_IMPLEMENT_DIR)
    item = _pinned(item_id="bd-ib-dodimpl", workflow=_IMPLEMENT_VARIANT)

    refusal = _refusal(repo=repo, item=item)

    assert refusal is not None
    assert str(variant) in refusal
    assert "proof_capture, proof_verify" in refusal


def test_a_registered_groom_variant_is_exempt_from_the_proof_stage_nodes(
    tmp_path: Path,
) -> None:
    """A groom variant's acceptance is the human approval of its draft.

    Its graph carries none of the three nodes and must still be admitted, which
    is the exemption `CriteriaWallVariant.exempt` already states — the gate must
    not keep a second copy of that precedence.
    """
    repo = _registering_repo(tmp_path=tmp_path)
    _ = _write_workflow(
        root=repo, nodes=("propose",), directory=_GROOM_DIR, manifest_text=_GROOM_MANIFEST
    )
    item = _pinned(item_id="bd-ib-dodgroom", workflow=_GROOM_VARIANT)

    assert _refusal(repo=repo, item=item) is None


def test_the_shared_wall_returns_before_any_admission_or_later_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "target"
    _ = _write_workflow(root=repo, nodes=("dod_gate",))
    monkeypatch.setattr(wall, "implementation_pr_override_refusal", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "fabro_currency_refusal", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "pre_dispatch_criteria_refusal", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "dod_judgement_refusal", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "proof_assets_refusal_for_items", lambda **_kwargs: None)
    monkeypatch.setattr(wall, "proof_credentials_refusal_for_items", lambda **_kwargs: None)
    monkeypatch.setattr(
        wall,
        "selection_credential_requirement",
        lambda **_kwargs: pytest.fail("the wall reached a gate after the refusal"),
    )

    assert (
        wall.pre_dispatch_wall_exit(
            args=_args(repo=repo), repo=repo, items=[_item()], journal=object()
        )
        == 3
    )
