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
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard import (
    CREDENTIAL_USE_DEADLINE_ENV_VAR,
    GUARD_SCRIPT_PATH,
)
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


# --- Stylesheet-selected backends ------------------------------------------------
#
# A node's backend does NOT have to be written on the node. The pinned engine's
# `StylesheetApplicationTransform` (`fabro-workflow/src/transforms/stylesheet_
# application.rs`) reads the graph's `model_stylesheet` attribute and fills in any
# of five properties a node does not declare explicitly -- and `backend` is one of
# them (`transforms/stylesheet.rs` `STYLESHEET_PROPERTIES`). So `backend: acp` can
# arrive from the stylesheet, and a validator keyed on the literal node attribute
# sees an ordinary command node where the engine will launch a coding agent.
#
# THAT WAS MEASURED on the implementation these cases drive: taking the shipped
# graph, removing ONLY `implement`'s explicit `backend="acp"`, pointing its
# `acp.command` at a literal, and adding `model_stylesheet="#implement { backend:
# acp; }"` left `unguardable_launch_refusal` returning None -- admitted -- while
# the engine would select ACP and launch the literal outside the guard.
#
# The four selector kinds and their specificities are the engine's own
# (`fabro-graphviz/src/stylesheet.rs`): `*` universal 0, a bare word matching the
# node's SHAPE 1, `.class` 2, `#id` 3. Higher specificity wins; an EXPLICIT node
# attribute is never overridden at all.

_STYLED_TEMPLATED = """digraph G {
  graph [model_stylesheet="#implement { backend: acp; }"]
  start [shape=Mdiamond]
  implement [acp.command="{{ inputs.implement_adapter }}", timeout="60s"]
  start -> implement
  implement -> exit
  exit [shape=Msquare]
}
"""


def test_a_stylesheet_selected_acp_node_launching_from_a_wrapped_input_is_admitted() -> None:
    """THE POSITIVE CONTROL for this whole section, and it comes first deliberately.

    Every negative below is refused by an implementation that refuses every graph
    carrying a `model_stylesheet` at all, which would break any repository using
    one. This case is the styled route done RIGHT: no explicit backend, the
    stylesheet supplies `acp`, and the command is still the wrapped input -- so the
    guard reaches it and the dispatch must be admitted.
    """
    assert (
        unguardable_launch_refusal(graph_text=_STYLED_TEMPLATED, adapter_inputs=_WRAPPED_INPUTS)
        is None
    )


def test_a_stylesheet_selected_acp_node_with_a_literal_command_is_refused() -> None:
    """THE REGRESSION: the exact shape the control reproduced.

    Differs from the admitted case above in ONE way -- the command is a literal --
    so the refusal is attributable to the launch, not to the stylesheet.
    """
    graph = _STYLED_TEMPLATED.replace('"{{ inputs.implement_adapter }}"', '"/usr/bin/true"')
    refusal = unguardable_launch_refusal(graph_text=graph, adapter_inputs=_WRAPPED_INPUTS)
    assert refusal is not None, "a stylesheet-selected ACP node with a literal command was admitted"
    assert "implement" in refusal
    assert "/usr/bin/true" in refusal


def test_a_stylesheet_selected_acp_node_declaring_acp_config_is_refused() -> None:
    """The other launch form the engine accepts, reached through the stylesheet.

    `fabro-acp/src/command.rs` takes `acp.config` JSON carrying its own command,
    args and env, so this node launches without ever reading a wrapped input.
    """
    graph = _STYLED_TEMPLATED.replace(
        'acp.command="{{ inputs.implement_adapter }}"',
        'acp.config="{\\"command\\": \\"/usr/bin/true\\"}"',
    )
    refusal = unguardable_launch_refusal(graph_text=graph, adapter_inputs=_WRAPPED_INPUTS)
    assert refusal is not None, "a stylesheet-selected acp.config launch was admitted"
    assert "implement" in refusal
    assert "acp.config" in refusal


def test_a_class_selector_can_make_a_node_acp_and_is_graded() -> None:
    """Specificity 2, and the class comes from the node's own `class` attribute.

    The engine splits `class` on commas into `node.classes`
    (`fabro-graphviz/src/parser/semantic.rs` `process_node`), which is what a
    `.code` selector matches.
    """
    graph = _STYLED_TEMPLATED.replace(
        '"#implement { backend: acp; }"', '".code { backend: acp; }"'
    ).replace(
        '  implement [acp.command="{{ inputs.implement_adapter }}"',
        '  implement [class="planning,code", acp.command="/usr/bin/true"',
    )
    refusal = unguardable_launch_refusal(graph_text=graph, adapter_inputs=_WRAPPED_INPUTS)
    assert refusal is not None, "a class-selected ACP node with a literal command was admitted"
    assert "implement" in refusal
    assert "/usr/bin/true" in refusal


# A node's CLASS MEMBERSHIP ACCUMULATES ACROSS DECLARATIONS while its `class`
# ATTRIBUTE is last-wins, and the two diverge the moment a node is declared twice.
# The pinned `fabro-graphviz/src/parser/semantic.rs` `process_node` OVERWRITES
# `node.attrs` but only ever PUSHES onto `node.classes` and never clears it, and
# `transforms/stylesheet.rs` matches `Selector::Class` against that ACCUMULATED
# list -- not against the final attribute. So reconstructing membership from the
# merged `class` attribute silently drops every class an earlier declaration
# contributed, and a rule the engine still matches reads as not matching.

_CLASS_REDECLARED = """digraph G {
  graph [model_stylesheet=".retained { backend: acp; }"]
  start [shape=Mdiamond]
  implement [class="retained", acp.command="/usr/bin/true", timeout="60s"]
  implement [class="replacement"]
  start -> implement
  implement -> exit
  exit [shape=Msquare]
}
"""


def test_a_class_retained_from_an_earlier_declaration_still_selects_the_node() -> None:
    """THE REGRESSION: re-declaring a node must not drop its earlier classes.

    `implement` is declared twice. Its `class` ATTRIBUTE ends as `replacement`, but
    the engine's accumulated `node.classes` is `[retained, replacement]`, so
    `.retained { backend: acp; }` still selects it and the literal launches over
    ACP. Measured before the fix: this exact graph was ADMITTED, while the
    single-declaration form of it was correctly refused.
    """
    refusal = unguardable_launch_refusal(
        graph_text=_CLASS_REDECLARED, adapter_inputs=_WRAPPED_INPUTS
    )
    assert refusal is not None, "a re-declared node dropped the class that selects it"
    assert "implement" in refusal
    assert "/usr/bin/true" in refusal


def test_a_class_added_by_a_later_declaration_also_selects_the_node() -> None:
    """The mirror direction: the LATER declaration's class counts too.

    Accumulation is a union, not a swap, so a fix that merely read the FIRST
    declaration's classes instead of the last would pass the case above and fail
    this one.
    """
    graph = _CLASS_REDECLARED.replace(
        '".retained { backend: acp; }"', '".replacement { backend: acp; }"'
    )
    refusal = unguardable_launch_refusal(graph_text=graph, adapter_inputs=_WRAPPED_INPUTS)
    assert refusal is not None, "a class added by a later declaration was ignored"
    assert "implement" in refusal
    assert "/usr/bin/true" in refusal


def test_a_re_declared_node_whose_launch_stays_templated_is_still_admitted() -> None:
    """THE POSITIVE CONTROL for accumulation: re-declaration is not itself a fault.

    Without it, both cases above would be satisfied by refusing every graph that
    declares a node more than once, which DOT permits and real graphs do.
    """
    graph = _CLASS_REDECLARED.replace('"/usr/bin/true"', '"{{ inputs.implement_adapter }}"')
    assert unguardable_launch_refusal(graph_text=graph, adapter_inputs=_WRAPPED_INPUTS) is None


def test_a_universal_selector_makes_every_node_acp_including_the_terminals() -> None:
    """`* { backend: acp; }` reaches EVERY node, so the terminals are graded too.

    `start` and `exit` declare no `acp.command`, and under this stylesheet the
    engine would select ACP for them, so the missing-command refusal is the correct
    verdict and `exit` is simply the first node in sorted order to hit it. Recorded
    as an assertion rather than left implicit because it is the one case where the
    refusal names a node the author did not write a launch for.
    """
    graph = _STYLED_TEMPLATED.replace('"#implement { backend: acp; }"', '"* { backend: acp; }"')
    refusal = unguardable_launch_refusal(graph_text=graph, adapter_inputs=_WRAPPED_INPUTS)
    assert refusal is not None, "a universal backend stylesheet was admitted"
    assert "'exit'" in refusal
    assert "no acp.command" in refusal


def test_an_explicit_backend_is_not_overridden_by_the_stylesheet() -> None:
    """The engine fills in only what a node does NOT declare.

    `apply_stylesheet` inserts a property only `if !node.attrs.contains_key(prop)`,
    so a node explicitly declaring a non-ACP backend stays non-ACP and launches no
    coding agent -- it must still be admitted, or a stylesheet anywhere in a graph
    would refuse every command node in it.
    """
    graph = _STYLED_TEMPLATED.replace(
        '  implement [acp.command="{{ inputs.implement_adapter }}"',
        '  implement [backend=command, script="just check"',
    )
    assert unguardable_launch_refusal(graph_text=graph, adapter_inputs=_WRAPPED_INPUTS) is None


def test_a_higher_specificity_rule_decides_the_backend() -> None:
    """Id (3) beats universal (0), which is what makes the ladder worth modelling.

    Written so the universal rule names a NON-ACP backend: the terminals take it and
    drop out of grading, and `implement` is ACP only if the `#id` rule won. An
    implementation that merely scanned the stylesheet for `backend: acp` would pass
    this; one that took the LAST rule regardless of specificity would not.
    """
    graph = _STYLED_TEMPLATED.replace(
        '"#implement { backend: acp; }"',
        '"#implement { backend: acp; } * { backend: command; }"',
    ).replace('"{{ inputs.implement_adapter }}"', '"/usr/bin/true"')
    refusal = unguardable_launch_refusal(graph_text=graph, adapter_inputs=_WRAPPED_INPUTS)
    assert refusal is not None, "an id-selected ACP node was admitted"
    assert "implement" in refusal
    assert "/usr/bin/true" in refusal


def test_an_unparseable_stylesheet_is_refused_rather_than_ignored() -> None:
    """FAIL CLOSED, and deliberately STRICTER than the pinned engine.

    `StylesheetApplicationTransform` swallows a parse error and runs the graph with
    the stylesheet UNAPPLIED, so this graph would launch today with `implement` left
    non-ACP. We refuse anyway: a stylesheet we cannot read is one whose effective
    backends we cannot enumerate, and the cost of being wrong in the admitting
    direction is a live credential with no enforcement. A dispatch refused here is
    told exactly which declaration to fix.
    """
    graph = _STYLED_TEMPLATED.replace(
        '"#implement { backend: acp; }"', '"#implement { backend acp; }"'
    )
    refusal = unguardable_launch_refusal(graph_text=graph, adapter_inputs=_WRAPPED_INPUTS)
    assert refusal is not None, "an unparseable model_stylesheet was admitted"
    assert "model_stylesheet" in refusal


def test_a_shape_selector_against_a_node_declaring_no_shape_is_refused() -> None:
    """The one genuinely UNDECIDABLE case, and it must not resolve to "no match".

    A bare-word selector matches a node's SHAPE, and a node declaring none takes the
    engine's default -- a value this repository cannot read from the pinned source it
    has. So whether `box { backend: acp; }` selects `implement` is unknown, and an
    unknown that defaulted to "not selected" would admit an unguarded launch.
    """
    graph = _STYLED_TEMPLATED.replace(
        '"#implement { backend: acp; }"', '"box { backend: acp; }"'
    ).replace('"{{ inputs.implement_adapter }}"', '"/usr/bin/true"')
    refusal = unguardable_launch_refusal(graph_text=graph, adapter_inputs=_WRAPPED_INPUTS)
    assert refusal is not None, "an undecidable shape selector was admitted"
    assert "implement" in refusal
    assert "shape" in refusal


def test_a_shape_selector_matching_a_declared_shape_is_graded() -> None:
    """A node that DOES declare its shape is decidable, and this one is selected."""
    graph = _STYLED_TEMPLATED.replace(
        '"#implement { backend: acp; }"', '"box { backend: acp; }"'
    ).replace(
        '  implement [acp.command="{{ inputs.implement_adapter }}"',
        '  implement [shape=box, acp.command="/usr/bin/true"',
    )
    refusal = unguardable_launch_refusal(graph_text=graph, adapter_inputs=_WRAPPED_INPUTS)
    assert refusal is not None, "a shape-selected ACP node was admitted"
    assert "implement" in refusal
    assert "/usr/bin/true" in refusal


def test_a_shape_selector_not_matching_a_declared_shape_leaves_the_node_alone() -> None:
    """The positive half of the pair above: a decidable NON-match still admits.

    Without it, the undecidable-shape refusal could be satisfied by refusing every
    graph whose stylesheet carries any shape selector.
    """
    graph = _STYLED_TEMPLATED.replace(
        '"#implement { backend: acp; }"', '"box { backend: acp; }"'
    ).replace(
        '  implement [acp.command="{{ inputs.implement_adapter }}"',
        '  implement [shape=ellipse, script="just check"',
    )
    assert unguardable_launch_refusal(graph_text=graph, adapter_inputs=_WRAPPED_INPUTS) is None


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


def test_a_dispatch_selecting_a_styled_literal_launch_is_refused_before_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The styled route reaches the REAL materializer, not just the decision above.

    The stylesheet cases earlier in this file grade `unguardable_launch_refusal`
    directly, which establishes that the decision is right and NOT that a real
    dispatch asks it about a styled graph -- the distinction this repository keeps
    paying for elsewhere ("an argv-transform unit test is not proof that those
    production routes invoke it"). So this drives `materialize_overlay` over a graph
    whose ACP-ness exists ONLY in its `model_stylesheet`.

    Pre-fix this returned no refusal at all: the measured control had
    `unguardable_launch_refusal` returning None for this exact shape, so the
    materializer had nothing to refuse and wrote the overlay.
    """
    error = _materialize_with(
        graph=_STYLED_TEMPLATED.replace('"{{ inputs.implement_adapter }}"', '"/usr/bin/true"'),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert error is not None, "a styled literal launch materialized an overlay"
    assert "implement" in error
    assert "literal acp.command" in error
    assert not (tmp_path / "overlay.toml").exists()


def test_a_dispatch_selecting_a_styled_config_launch_is_refused_before_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other engine-accepted launch form, styled, at the same seam."""
    error = _materialize_with(
        graph=_STYLED_TEMPLATED.replace(
            'acp.command="{{ inputs.implement_adapter }}"',
            'acp.config="{\\"command\\": \\"/usr/bin/true\\"}"',
        ),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert error is not None, "a styled acp.config launch materialized an overlay"
    assert "implement" in error
    assert "acp.config" in error
    assert not (tmp_path / "overlay.toml").exists()


def test_a_dispatch_selecting_a_styled_templated_launch_still_materializes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE STYLED WIRING POSITIVE CONTROL, and the one that makes the pair meaningful.

    A stylesheet is not itself a defect: a repository may legitimately select its
    backends that way, and such a dispatch must still run. Without this, both styled
    refusals above would be satisfied by refusing every graph carrying a
    `model_stylesheet` at all.
    """
    error = _materialize_with(graph=_STYLED_TEMPLATED, tmp_path=tmp_path, monkeypatch=monkeypatch)
    assert error is None, error
    assert (tmp_path / "overlay.toml").exists()


def test_a_dispatch_whose_class_was_re_declared_is_refused_before_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The accumulated-class route reaches the REAL materializer too.

    Same distinction the styled cases above draw: grading the decision establishes
    that it is right, not that a dispatch asks it. This drives `materialize_overlay`
    over a graph whose ACP-ness comes from a class an EARLIER declaration
    contributed and the final `class` attribute no longer names.
    """
    error = _materialize_with(graph=_CLASS_REDECLARED, tmp_path=tmp_path, monkeypatch=monkeypatch)
    assert error is not None, "a re-declared-class literal launch materialized an overlay"
    assert "implement" in error
    assert "literal acp.command" in error
    assert not (tmp_path / "overlay.toml").exists()


def test_a_dispatch_with_a_re_declared_templated_launch_still_materializes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The materializer-seam positive control for the same accumulation."""
    error = _materialize_with(
        graph=_CLASS_REDECLARED.replace('"/usr/bin/true"', '"{{ inputs.implement_adapter }}"'),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert error is None, error
    assert (tmp_path / "overlay.toml").exists()


# THE SECOND RECOGNISED SHAPE, added by plan `fabro-currency` P4: the payload
# generator now renders each ACP node's resolved, ALREADY-GUARDED adapter command
# into the graph as a LITERAL, because a templated `acp.command` kills the agent
# before the ACP protocol completes on the Petri-era engine. Recognising it is
# strictly stronger than recognising the template, which only shows the wrap WOULD
# apply; these cases read the executable position of the command that will be
# exec'd and require the guard to be it.
_GUARD = f"/bin/sh {GUARD_SCRIPT_PATH} --"


def _literal(*, command: str) -> str:
    """The guardable probe graph with its ACP node declaring a literal command."""
    return _GUARDABLE.replace('"{{ inputs.implement_adapter }}"', f'"{command}"', 1)


def test_a_literal_running_behind_the_projected_guard_is_admitted() -> None:
    """The rendered shape: the guard IS the executable, so the bound binds."""
    graph = _literal(command=f"{_GUARD} npx -y claude-agent-acp")
    assert unguardable_launch_refusal(graph_text=graph, adapter_inputs=frozenset()) is None


def test_a_guarded_literal_keeps_its_leading_key_value_prefix() -> None:
    """The engine peels leading assignments into the GUARD's environment, not past it."""
    graph = _literal(command=f"ANTHROPIC_MODEL=m EFFORT=high {_GUARD} npx -y acp")
    assert unguardable_launch_refusal(graph_text=graph, adapter_inputs=frozenset()) is None


def test_a_guarded_literal_declaring_an_enforcement_variable_is_refused() -> None:
    """A launch that could set its own deadline is not bounded by one."""
    graph = _literal(
        command=f"{CREDENTIAL_USE_DEADLINE_ENV_VAR}=1 {_GUARD} npx -y acp",
    )
    refusal = unguardable_launch_refusal(graph_text=graph, adapter_inputs=frozenset())
    assert refusal is not None
    assert CREDENTIAL_USE_DEADLINE_ENV_VAR in refusal


def test_a_command_that_is_only_env_assignments_is_refused() -> None:
    """Assignments with nothing after them launch nothing the guard could wrap."""
    graph = _literal(command="FOO=bar BAZ=qux")
    refusal = unguardable_launch_refusal(graph_text=graph, adapter_inputs=frozenset())
    assert refusal is not None
    assert "not the projected guard" in refusal


def test_a_command_that_does_not_tokenize_is_refused() -> None:
    """An unparseable command line is a launch this dispatch cannot establish."""
    graph = _literal(command="npx -y 'unbalanced")
    refusal = unguardable_launch_refusal(graph_text=graph, adapter_inputs=frozenset())
    assert refusal is not None
    assert "does not tokenize" in refusal
