"""Which declared launch routes a protected dispatch may admit, and which it refuses.

THE DEFECT THIS COVERS was measured, not reasoned about. Wrapping the adapter the
Dispatcher passes as a `fabro run --input` pair protects every launch in the graphs
this repository ships, because each of their ACP nodes declares
`acp.command="{{ inputs.<node>_adapter }}"`. A control that took the shipped
workflow and replaced ONE node's input reference with a literal command saw the
requirement resolve, the guard install and the startup check pass -- and the literal
command then execute 1.003 seconds PAST the absolute deadline, exit 0. Nothing was
broken except the assumption: a node declaring a literal command, or declaring its
process through `acp.config`, never reads the wrapped input at all.

SO THE RULE IS FAIL-CLOSED, and the cases below are arranged around the thing that
makes fail-closed honest rather than merely strict: THE POSITIVE CONTROL. A check
that refused everything would satisfy every negative here and break the factory, so
the first case grades the graph this repository actually dispatches, through the
adapter inputs a real resolution produces, and requires it to be ADMITTED.

Each negative is a graph that differs from a guardable one in exactly ONE way, so a
refusal is attributable to that difference rather than to the fixture being
malformed in some other respect.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_codex_auth,
    _dispatcher_credentials,
    _dispatcher_sibling_clones,
)
from livespec_orchestrator_beads_fabro.commands._acp_catalogs import builtin_catalogs
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import resolve_acp_nodes
from livespec_orchestrator_beads_fabro.commands._config_acp import resolve_acp_node_overlays
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_nodes import workflow_layer
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_routes import (
    unguardable_launch_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import materialize_overlay
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor

_SHIPPED_GRAPH = Path(".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro")
_SHIPPED_WORKFLOW_TOML = Path(".claude-plugin/.fabro/workflows/implement-work-item/workflow.toml")

# A minimal graph in the shape the shipped one uses: one ACP node launching from an
# adapter input. Every negative below is this graph with ONE attribute changed, so
# the refusal is attributable to that change.
_GUARDABLE = """digraph G {
  start [shape=Mdiamond]
  implement [backend=acp, acp.command="{{ inputs.implement_adapter }}", timeout="60s"]
  start -> implement
  implement -> exit
  exit [shape=Msquare]
}
"""

_WRAPPED_INPUTS = frozenset({"implement_adapter"})


def _resolved_adapter_inputs(*, repo: Path) -> frozenset[str]:
    """The workflow input names a REAL resolution wraps for the shipped workflow."""
    overlays = resolve_acp_node_overlays(cwd=repo)
    assert not isinstance(overlays, str), overlays
    workflow_inputs = workflow_layer(committed=_SHIPPED_WORKFLOW_TOML, catalogs=builtin_catalogs())
    assert not isinstance(workflow_inputs, str), workflow_inputs
    resolution = resolve_acp_nodes(
        workflow_inputs=workflow_inputs, repository=overlays, dispatch={}
    )
    assert not isinstance(resolution, str), resolution
    return frozenset(resolution.inputs.values())


def test_the_shipped_workflow_is_admitted(tmp_path: Path) -> None:
    """THE POSITIVE CONTROL: the graph this repository dispatches is guardable.

    Graded against the adapter inputs a REAL resolution produces rather than a
    hand-written set, because the question is whether the dispatch's own wrapping
    covers its own graph. A check that refused this would satisfy every negative
    below while making the factory unable to run anything at all.
    """
    assert (
        unguardable_launch_refusal(
            graph_text=_SHIPPED_GRAPH.read_text(encoding="utf-8"),
            adapter_inputs=_resolved_adapter_inputs(repo=tmp_path),
        )
        is None
    )


def test_a_minimal_templated_graph_is_admitted() -> None:
    """The fixture the negatives are derived from is itself guardable.

    Without this, a negative could pass because the fixture is malformed in some
    way unrelated to the attribute it changes.
    """
    assert unguardable_launch_refusal(graph_text=_GUARDABLE, adapter_inputs=_WRAPPED_INPUTS) is None


def test_a_literal_command_is_refused_by_name() -> None:
    """The measured defect: a literal command never consumes the wrapped input."""
    graph = _GUARDABLE.replace('"{{ inputs.implement_adapter }}"', '"/usr/bin/agent --serve"')
    refusal = unguardable_launch_refusal(graph_text=graph, adapter_inputs=_WRAPPED_INPUTS)
    assert refusal is not None
    assert "implement" in refusal
    assert "literal" in refusal
    assert "/usr/bin/agent --serve" in refusal


def test_an_acp_config_launch_is_refused() -> None:
    """`acp.config` is the pinned engine's other accepted launch form.

    `fabro-acp/src/command.rs` accepts either `acp.command` or an `acp.config` JSON
    stdio command/args/env, and the second carries its own command, so the wrap
    never reaches it.
    """
    graph = _GUARDABLE.replace(
        'acp.command="{{ inputs.implement_adapter }}"',
        'acp.config="{\\"command\\":\\"/usr/bin/agent\\"}"',
    )
    refusal = unguardable_launch_refusal(graph_text=graph, adapter_inputs=_WRAPPED_INPUTS)
    assert refusal is not None
    assert "implement" in refusal
    assert "acp.config" in refusal


def test_graph_declared_fallback_candidates_are_refused() -> None:
    """A fallback chain in the graph launches commands the wrap never sees.

    The pinned `acp_fallback/chain.rs` requires candidate zero's command to be
    byte-equal to the node's, and `acp.rs` builds a fresh process spec from EACH
    candidate's command -- so wrapping only the primary would leave every later
    candidate unguarded. Unrecognised `acp.*` attributes are refused as a class
    rather than enumerated, because the ones that do not exist yet are exactly the
    ones a future engine would add.
    """
    graph = _GUARDABLE.replace(
        'acp.command="{{ inputs.implement_adapter }}"',
        'acp.command="{{ inputs.implement_adapter }}", acp.candidates="[{...}]"',
    )
    refusal = unguardable_launch_refusal(graph_text=graph, adapter_inputs=_WRAPPED_INPUTS)
    assert refusal is not None
    assert "implement" in refusal
    assert "acp.candidates" in refusal


def test_an_unwrapped_input_reference_is_refused() -> None:
    """A reference to an input nobody supplied runs the workflow's own default.

    It looks identical in the graph to a protected node, which is why the check
    grades against the dispatch's OWN wrapped set rather than against the shape of
    the reference.
    """
    refusal = unguardable_launch_refusal(
        graph_text=_GUARDABLE, adapter_inputs=frozenset({"some_other_adapter"})
    )
    assert refusal is not None
    assert "implement_adapter" in refusal
    assert "did not wrap" in refusal


def test_a_surrounded_reference_is_refused() -> None:
    """A reference with text around it no longer puts the guard first.

    `wrapper {{ inputs.x }}` reaches the engine as a command line whose first token
    is the wrapper, so the guard is not what executes.
    """
    graph = _GUARDABLE.replace(
        '"{{ inputs.implement_adapter }}"', '"/usr/bin/strace {{ inputs.implement_adapter }}"'
    )
    refusal = unguardable_launch_refusal(graph_text=graph, adapter_inputs=_WRAPPED_INPUTS)
    assert refusal is not None
    assert "implement" in refusal


def test_an_acp_node_declaring_no_command_is_refused() -> None:
    """Nothing to recognise is still not something to admit."""
    graph = _GUARDABLE.replace(', acp.command="{{ inputs.implement_adapter }}"', "")
    refusal = unguardable_launch_refusal(graph_text=graph, adapter_inputs=_WRAPPED_INPUTS)
    assert refusal is not None
    assert "implement" in refusal
    assert "no acp.command" in refusal


def test_a_non_acp_node_is_not_graded() -> None:
    """A command node is not a coding-agent launch and holds no credential.

    The graphs carry several: the publish-draft push, the janitor. Refusing over
    their scripts would refuse every real workflow.
    """
    graph = _GUARDABLE.replace(
        "  implement [backend=acp",
        '  janitor [shape=parallelogram, script="just check"]\n  implement [backend=acp',
    )
    assert unguardable_launch_refusal(graph_text=graph, adapter_inputs=_WRAPPED_INPUTS) is None


def test_a_late_duplicate_declaration_overriding_the_command_is_refused() -> None:
    """THE REGRESSION: a SECOND declaration of a node is a real launch route.

    DOT permits a node to be declared more than once, and the pinned
    `fabro-graphviz/src/parser/semantic.rs` `apply_node_stmt` UPDATES an existing
    node's attributes rather than ignoring the repeat -- so the LAST value of
    `acp.command` is the one the engine launches.

    This is not hypothetical. An earlier draft of the validator read the graph
    through a first-wins regex reader, and a control that appended exactly this
    shape to the shipped graph had it ADMITTED while the effective command was
    `/usr/bin/true`. The attributes graded must be the MERGED ones.
    """
    graph = _GUARDABLE.replace("}\n", '  implement [acp.command="/usr/bin/true"]\n}\n', 1)
    refusal = unguardable_launch_refusal(graph_text=graph, adapter_inputs=_WRAPPED_INPUTS)
    assert refusal is not None, "a late override of acp.command was admitted"
    assert "implement" in refusal
    assert "/usr/bin/true" in refusal


def test_a_late_duplicate_declaration_that_keeps_the_input_is_admitted() -> None:
    """The positive half: a repeat that does NOT change the launch still admits.

    Without it, the case above would also pass an implementation that refused every
    graph containing any repeated declaration, which the shipped graphs are free to
    contain for unrelated attributes.
    """
    graph = _GUARDABLE.replace("}\n", '  implement [timeout="120s"]\n}\n', 1)
    assert unguardable_launch_refusal(graph_text=graph, adapter_inputs=_WRAPPED_INPUTS) is None


def test_an_unparseable_graph_is_refused_rather_than_read_as_empty() -> None:
    """A graph whose launches cannot be enumerated is not a graph with none.

    The reader this validator replaced was total by construction: a text it
    recognised nothing in yielded an empty graph, which for this question reads as
    "no ACP nodes" and therefore as admission.
    """
    refusal = unguardable_launch_refusal(
        graph_text="digraph G { implement [backend=acp,", adapter_inputs=_WRAPPED_INPUTS
    )
    assert refusal is not None
    assert "could not be parsed" in refusal


# --- The wiring: the refusal has to reach a real dispatch ------------------------
#
# The cases above grade the decision. These two grade that `materialize_overlay`
# ASKS it, before the launch and before the proof-credential mint. A sound decision
# nothing consults is the shape this whole item started in -- a tested guard with no
# production importer.

_COMMITTED_WORKFLOW_TOML = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    "[run.environment]\n"
    'id = "livespec-ci"\n'
)

_FLEET_MANIFEST_TEXT = (
    "{\n"
    '  "owner": "thewoolleyman",\n'
    '  "members": [{ "repo": "livespec", "class": "core" }]\n'
    "}\n"
)
_GIT_AUTHOR_FOR_OVERLAY = GitAuthor(name="Operator", email="operator@example.com")
_OVERLAY_TOKEN = "test-oauth-token"
_OVERLAY_GITHUB_TOKEN = "test-github-token"
_REVIEW_FIX_VISIT_CAP = 3
_UNGUARDABLE_GRAPH = """digraph G {
  start [shape=Mdiamond]
  implement [backend=acp, acp.command="/usr/bin/agent --serve", timeout="60s"]
  start -> implement
  implement -> exit
  exit [shape=Msquare]
}
"""


def _auth_json_far_future(*, now: int) -> str:
    import base64
    import json

    exp = now + 100 * 365 * 24 * 3600
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {"access_token": f"header.{payload}.sig", "refresh_token": "host"},
        }
    )


def _materialize_with(*, graph: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str | None:
    """Drive the real pre-launch materializer over one declared graph."""
    committed = tmp_path / "workflow.toml"
    _ = committed.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (committed.parent / "workflow.fabro").write_text(graph, encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _OVERLAY_TOKEN)
    monkeypatch.setattr(
        _dispatcher_sibling_clones, "fetch_fleet_manifest_text", lambda: _FLEET_MANIFEST_TEXT
    )
    now = 1_700_000_000
    monkeypatch.setattr(_dispatcher_credentials.time, "time", lambda: now)
    monkeypatch.setattr(
        _dispatcher_codex_auth, "read_host_codex_auth", lambda: _auth_json_far_future(now=now)
    )
    return materialize_overlay(
        committed=committed,
        overlay=tmp_path / "overlay.toml",
        repo=tmp_path / "repo",
        work_item_id="wi-1",
        dispatch_id="disp-1",
        token=lambda: _OVERLAY_GITHUB_TOKEN,
        git_author=_GIT_AUTHOR_FOR_OVERLAY,
        review_fix_visit_cap=_REVIEW_FIX_VISIT_CAP,
        adapter_inputs=frozenset({"implement_adapter"}),
    )


def test_a_dispatch_selecting_an_unguardable_graph_is_refused_before_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real materializer REFUSES, naming the node, and writes no overlay.

    No overlay means no projected credential and no launch: the refusal lands before
    the sandbox exists rather than being discovered once an agent is already running
    against a credential nothing bounds.
    """
    error = _materialize_with(graph=_UNGUARDABLE_GRAPH, tmp_path=tmp_path, monkeypatch=monkeypatch)
    assert error is not None
    assert "implement" in error
    assert "literal acp.command" in error
    assert not (tmp_path / "overlay.toml").exists()


def test_a_dispatch_selecting_a_guardable_graph_still_materializes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE WIRING POSITIVE CONTROL: a guardable graph is still admitted.

    Paired with the case above so the refusal is attributable to the graph rather
    than to the fixture, and so an implementation that refused every dispatch could
    not pass both.
    """
    error = _materialize_with(graph=_GUARDABLE, tmp_path=tmp_path, monkeypatch=monkeypatch)
    assert error is None, error
    assert (tmp_path / "overlay.toml").exists()
