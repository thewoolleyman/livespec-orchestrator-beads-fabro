"""Which SURFACE refuses a workflow fault the credential derivation noticed first.

WHAT THIS BINDS. The credential wall runs EARLY and, to size the execution
allowance, it resolves the selected workflow's registry entry, reads its
committed run config and its graph, and reads the dispatch target's
node-timeout policy. That makes it the first thing to NOTICE a fault in any of
them -- and treating such a fault as its own refusal is a measured defect, not
a style question: Scenario 89's invalid node timeout reported a credential
refusal at the precondition exit code instead of a timeout refusal at the
dispatch exit code, and a registry fault wrote NO outcome record at all because
the wall returned before the stage that writes one.

So each case here asserts the TYPE, not just that something refused. A
`WorkflowFaultDeferral` is the derivation saying "a later stage owns this";
a refusal STRING is the derivation saying "this is mine". The last case is the
string arm, paired deliberately: without it, these cases would be satisfied by
a build that deferred EVERYTHING and so never refused a genuinely unbounded
graph at all -- which is what would quietly retire Scenario 19.

DEFERRING CANNOT ADMIT UNGRADED CREDENTIAL USE, which is why it is safe rather
than merely quieter. Every fault routed this way is a fault in configuration a
dispatch must read before it can launch anything, so the owning stage refuses
before any Fabro run exists and no credential is ever projected into a sandbox.
`tests/integration/test_named_workflow_variants.py` and
`tests/integration/test_node_timeouts_scenario89.py` are the integration-tier
controls that each fault still refuses, under its own stage, before a run.

These cases live in their own module rather than beside the requirement
derivation's because that module's bytes are frozen by its Red commit.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_REQUIREMENT_MODULE = f"{_PACKAGE}._dispatcher_credential_requirement"
_REQUIREMENT_PATH = (
    _REPO_ROOT
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_credential_requirement.py"
)

_FIXTURE_WORKFLOW_TOML = """_version = 1

[workflow]
graph = "workflow.fabro"

[run]
goal = "fixture"

[run.inputs]
loop_cap = 3

[run.checkpoint]
commit_timeout = "10m"
"""

_FIXTURE_GRAPH = """digraph Fixture {
    graph [
        default_max_retries=0
        stall_timeout="7200s"
    ]

    start [shape=Mdiamond, label="Start"]
    exit  [shape=Msquare, label="Exit"]

    work [
        timeout="1800s"
    ]

    loop [
        timeout="1800s"
    ]

    start -> work
    work -> loop [label="again", condition="outcome!=succeeded && \
context.internal.node_visit_count < {{ inputs.loop_cap }}"]
    work -> exit
    loop -> work
}
"""


def _write_repo(
    *,
    tmp_path: Path,
    block: dict[str, Any] | None = None,
    workflow_toml: str = _FIXTURE_WORKFLOW_TOML,
    graph: str = _FIXTURE_GRAPH,
    directory: str = ".fabro/workflows/implement-work-item",
) -> Path:
    """A dispatch target carrying one workflow directory and one config block."""
    workflow_dir = tmp_path / directory
    workflow_dir.mkdir(parents=True, exist_ok=True)
    _ = (workflow_dir / "workflow.toml").write_text(workflow_toml, encoding="utf-8")
    _ = (workflow_dir / "workflow.fabro").write_text(graph, encoding="utf-8")
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {"livespec-orchestrator-beads-fabro": {"dispatcher": {} if block is None else block}}
        ),
        encoding="utf-8",
    )
    return tmp_path


def _resolve(*, repo: Path, workflow_name: str | None = None) -> Any:
    module = importlib.import_module(_REQUIREMENT_MODULE)
    return module.resolve_credential_lifetime_requirement(
        repo=repo,
        workflow_override=None,
        workflow_name=workflow_name,
    )


def test_a_run_config_holding_undecodable_bytes_defers_rather_than_raising(
    tmp_path: Path,
) -> None:
    """An undecodable run config is a WORKFLOW fault, deferred, never a traceback.

    Asserted as a `WorkflowFaultDeferral` rather than a refusal string because
    the TYPE is what routes it: the credential wall runs early and reads the run
    config to size the allowance, so it is the first thing to notice the file
    cannot be read -- but the stage that materializes that config owns the
    diagnostic and refuses with its own exit code.

    NON-UTF-8 BYTES are the fixture deliberately. A run config that is merely
    ABSENT is not this case at all: `workflow_toml` legitimately falls back to
    the bundled workflow, so an absent file resolves a perfectly good
    requirement for a DIFFERENT graph (measured here first, which is how the
    original version of this case was wrong). A file that exists at the resolved
    path and cannot be decoded is the one that reaches the unreadable arm -- and
    it used to RAISE through the wall rather than route as data, because the read
    caught only `OSError` while `UnicodeDecodeError` is a `ValueError`.
    """
    assert _REQUIREMENT_PATH.is_file(), "the credential-requirement module is not written yet"
    module = importlib.import_module(_REQUIREMENT_MODULE)
    repo = _write_repo(tmp_path=tmp_path)
    committed = repo / ".fabro/workflows/implement-work-item/workflow.toml"
    _ = committed.write_bytes(b"_version = 1\n\xff\xfe not utf-8\n")

    deferral = _resolve(repo=repo)

    assert isinstance(deferral, module.WorkflowFaultDeferral), deferral
    assert "unreadable" in deferral.message
    # The text reads identically to a refusal for the surfaces that have no
    # owning stage behind them, which is what `requirement_refusal_text` is for.
    assert module.requirement_refusal_text(outcome=deferral) == deferral.message


def test_a_run_config_declaring_no_graph_defers_rather_than_sizing_another_graph(
    tmp_path: Path,
) -> None:
    """No `[workflow]` graph means no graph to size, and a later stage says so."""
    assert _REQUIREMENT_PATH.is_file(), "the credential-requirement module is not written yet"
    module = importlib.import_module(_REQUIREMENT_MODULE)

    deferral = _resolve(
        repo=_write_repo(
            tmp_path=tmp_path,
            workflow_toml='_version = 1\n\n[run]\ngoal = "fixture"\n',
        )
    )

    assert isinstance(deferral, module.WorkflowFaultDeferral), deferral
    assert "declares no [workflow] graph" in deferral.message


def test_a_declared_graph_that_cannot_be_read_defers(tmp_path: Path) -> None:
    """A declared-but-unreadable graph file is the same class of workflow fault."""
    assert _REQUIREMENT_PATH.is_file(), "the credential-requirement module is not written yet"
    module = importlib.import_module(_REQUIREMENT_MODULE)
    repo = _write_repo(tmp_path=tmp_path)
    graph = repo / ".fabro/workflows/implement-work-item/workflow.fabro"
    _ = graph.write_bytes(b"digraph G {\n\xff\xfe\n}\n")

    deferral = _resolve(repo=repo)

    assert isinstance(deferral, module.WorkflowFaultDeferral), deferral
    assert "workflow graph" in deferral.message


def test_an_invalid_node_timeout_defers_to_its_own_validator(tmp_path: Path) -> None:
    """Scenario 89's validator owns this diagnostic and its exit code.

    The measured defect: an invalid `dispatcher.node_timeouts` entry reported a
    credential refusal at the precondition exit code instead of a node-timeout
    refusal at the dispatch exit code, because the credential derivation reads
    the same block and saw it first.
    """
    assert _REQUIREMENT_PATH.is_file(), "the credential-requirement module is not written yet"
    module = importlib.import_module(_REQUIREMENT_MODULE)

    deferral = _resolve(repo=_write_repo(tmp_path=tmp_path, block={"node_timeouts": {"work": 0}}))

    assert isinstance(deferral, module.WorkflowFaultDeferral), deferral
    assert "node_timeouts" in deferral.message


def test_a_refusal_string_passes_through_the_refusal_text_reader_unchanged(
    tmp_path: Path,
) -> None:
    """The other arm of `requirement_refusal_text`: a genuine credential refusal.

    Paired with the deferral case above, because the reader's whole job is that
    the two members read identically to a surface with nothing behind it — and a
    reader that returned the right thing for only one member would satisfy
    either case alone.
    """
    assert _REQUIREMENT_PATH.is_file(), "the credential-requirement module is not written yet"
    module = importlib.import_module(_REQUIREMENT_MODULE)
    unguarded = _FIXTURE_GRAPH.replace(
        '[label="again", condition="outcome!=succeeded && '
        'context.internal.node_visit_count < {{ inputs.loop_cap }}"]',
        '[label="again"]',
    )

    refusal = _resolve(repo=_write_repo(tmp_path=tmp_path, graph=unguarded))

    assert isinstance(refusal, str), refusal
    assert module.requirement_refusal_text(outcome=refusal) == refusal
