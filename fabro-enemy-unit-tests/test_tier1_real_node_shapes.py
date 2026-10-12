"""Tier 1 Enemy Unit Tests that copy the SHAPES of the real factory nodes.

The preserved-behaviour probes in `test_tier1_preserved_behaviours.py` prove
engine semantics with self-contained scripts. They passed on the Petri-era
candidate while two real nodes failed on it, because no probe fed a workflow
input through the template renderer or launched into a declared environment:

- canary 4 (run 01M4NHJVACZV, 2026-10-11) died in prepare with exit 127,
  `mise` not found, because the engine took the sandbox image only from
  `--environment` and fell back to the catalog default;
- canary 7 (run 01M4PCG8ADWW, 2026-10-11) died in the janitor with exit 127 on
  all three visits, because Petri shell-quotes every `inputs.*` token when it
  renders a script, so the bare check-suite interpolation arrived as ONE word
  and bash looked the whole suite up as a command name.

Each probe below renders the same template shape the real graph uses, with the
same kind of value the Dispatcher supplies, and lets the script's exit status
be the oracle (`goal_gate=true`), exactly as the preserved-behaviour probes do.
The janitor probe reads its script from the real graph, so a change to that
node is exercised here without editing this file. Excluded from `just check`:

    just fabro-enemy-tier1
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from _tier0_support import TIMEOUT_SECONDS, _assert_success, _FabroTier0Config, _inspect_record
from _tier1_support import _failure_block, _write_goal, _write_workflow
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget

__all__: list[str] = []

_RUN_TIMEOUT_SECONDS = 300.0
_REAL_GRAPH = (
    Path(__file__).resolve().parent.parent
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)
# The Dispatcher renders the resolved check-suite argv as one shell line of
# plain words (for example `mise exec -- just check`); these keep that shape
# with commands every sandbox image carries.
_PASSING_SUITE = "test ok = ok"
# A failing suite that leaves a sentinel behind, so "the suite ran and failed"
# is told apart from a node that failed because the suite never ran (canary
# 7's exit 127). Neither engine reports script stderr in the same place, so
# the oracle is a file in the sandbox rather than the failure message.
_SUITE_SENTINEL = "/tmp/eut-check-suite-ran"
_FAILING_SUITE = f"touch {_SUITE_SENTINEL} && false"
# Created by the fix-loop probe's `fix` node; the suite fails until it exists.
_FIX_SENTINEL = "/tmp/eut-fix-applied"
# Which outgoing janitor edge the run took, read by the single goal gate.
_VERDICT = "/tmp/eut-janitor-verdict"


def _real_node_script(*, node: str) -> str:
    """Return the `script` attribute of `node` in the real implement graph."""
    text = _REAL_GRAPH.read_text()
    block = re.search(rf"^\s+{re.escape(node)} \[(.*?)^\s+\]", text, re.MULTILINE | re.DOTALL)
    assert block is not None, f"node {node} not found in {_REAL_GRAPH}"
    script = re.search(r'^\s+script="((?:[^"\\]|\\.)*)"', block.group(1), re.MULTILINE)
    assert script is not None, f"node {node} has no script attribute"
    return script.group(1)


def _single_node_workflow(*, name: str, script: str) -> str:
    return f"""
digraph {name} {{
    start [shape=Mdiamond, label="Start"]
    probe [shape=parallelogram, label="Probe", goal_gate=true, script="{script}"]
    exit [shape=Msquare, label="Exit"]
    start -> probe
    probe -> exit
}}
"""


def _run_status(
    *, port: FabroPort, tmp_path: Path, name: str, body: str, inputs: tuple[str, ...]
) -> tuple[str, str]:
    """Launch `body` with `inputs` and return `(status kind, failure message)`."""
    workflow = _write_workflow(tmp_path=tmp_path, name=name, body=body)
    goal = _write_goal(tmp_path=tmp_path, title=name)
    run = port.run(
        workflow_toml=workflow,
        goal_file=goal,
        inputs=inputs,
        timeout_seconds=_RUN_TIMEOUT_SECONDS,
    )
    assert run.run_id is not None, run.command.stderr or run.command.stdout
    inspect = port.inspect(run_id=run.run_id, timeout_seconds=TIMEOUT_SECONDS)
    _assert_success(command=inspect.command)
    record = _inspect_record(value=inspect.payload)
    status = record.get("status")
    kind = status.get("kind") if isinstance(status, dict) else status
    failure = _failure_block(value=record) or {}
    detail = failure.get("detail")
    message = detail.get("message") if isinstance(detail, dict) else failure.get("message")
    return (str(kind), str(message or ""))


def test_janitor_node_runs_an_interpolated_multi_word_check_suite(
    *, tmp_path: Path, port: FabroPort
) -> None:
    body = _single_node_workflow(
        name="FabroEnemyJanitorShape", script=_real_node_script(node="janitor")
    )
    kind, message = _run_status(
        port=port,
        tmp_path=tmp_path,
        name="janitor-shape-pass",
        body=body,
        inputs=(f"sandbox_check_suite={_PASSING_SUITE}",),
    )
    assert kind == "succeeded", message


def test_janitor_node_fails_when_the_interpolated_check_suite_fails(
    *, tmp_path: Path, port: FabroPort
) -> None:
    # The janitor's three real edges: Green on `outcome=succeeded`, Red on
    # `outcome!=succeeded`, and the unconditional exhaustion fallback. Each
    # branch records which edge was taken, and the one goal gate, `verdict`,
    # passes only for Red with the suite's sentinel present. Only `verdict`
    # carries goal_gate because Petri fails a run that leaves ANY goal-gate
    # node unvisited, reporting an earlier node's failure as the cause, while
    # the pinned engine ignores an unvisited gate (measured 2026-10-12: run
    # 01M4Q638BKSR failed on the candidate, 01M4Q6429N5D succeeded on pinned,
    # same graph). The real graph's gates, `implement` and `pr`, lie on every
    # path to exit, so the difference does not reach it.
    janitor = _real_node_script(node="janitor")
    body = f"""
digraph FabroEnemyJanitorShapeFail {{
    start [shape=Mdiamond, label="Start"]
    janitor [shape=parallelogram, label="Janitor", script="{janitor}"]
    red [shape=parallelogram, label="Red", script="test -f {_SUITE_SENTINEL} && echo red > {_VERDICT}"]
    green [shape=parallelogram, label="Green", script="echo green > {_VERDICT}"]
    exhausted [shape=parallelogram, label="Exhausted", script="echo exhausted > {_VERDICT}"]
    verdict [shape=parallelogram, label="Verdict", goal_gate=true, script="cat {_VERDICT} >&2; test \\"$(cat {_VERDICT})\\" = red"]
    exit [shape=Msquare, label="Exit"]
    start -> janitor
    janitor -> green [condition="outcome=succeeded"]
    janitor -> red [condition="outcome!=succeeded"]
    janitor -> exhausted
    red -> verdict
    green -> verdict
    exhausted -> verdict
    verdict -> exit
}}
"""
    kind, message = _run_status(
        port=port,
        tmp_path=tmp_path,
        name="janitor-shape-fail",
        body=body,
        inputs=(f"sandbox_check_suite={_FAILING_SUITE}",),
    )
    assert kind == "succeeded", message


def test_janitor_red_routes_through_fix_and_a_later_green_succeeds_the_run(
    *, tmp_path: Path, port: FabroPort
) -> None:
    # The janitor/fix loop as the real graph wires it: the suite fails until
    # `fix` repairs the sandbox, then the janitor's second visit is Green.
    # Only the always-visited `verdict` node is a goal gate (see above).
    janitor = _real_node_script(node="janitor")
    body = f"""
digraph FabroEnemyJanitorFixLoop {{
    start [shape=Mdiamond, label="Start"]
    janitor [shape=parallelogram, label="Janitor", script="{janitor}"]
    fix [shape=parallelogram, label="Fix", max_visits=3, script="touch {_FIX_SENTINEL}"]
    exhausted [shape=parallelogram, label="Exhausted", script="echo exhausted > {_VERDICT}"]
    publish [shape=parallelogram, label="Publish", script="echo publish > {_VERDICT}"]
    verdict [shape=parallelogram, label="Verdict", goal_gate=true, script="cat {_VERDICT} >&2; test -f {_FIX_SENTINEL} && test \\"$(cat {_VERDICT})\\" = publish"]
    exit [shape=Msquare, label="Exit"]
    start -> janitor
    janitor -> publish [label="Green", condition="outcome=succeeded"]
    janitor -> fix [label="Red", condition="outcome!=succeeded"]
    janitor -> exhausted [label="Exhausted (fix-loop cap)"]
    fix -> janitor
    publish -> verdict
    exhausted -> verdict
    verdict -> exit
}}
"""
    kind, message = _run_status(
        port=port,
        tmp_path=tmp_path,
        name="janitor-fix-loop",
        body=body,
        inputs=(f"sandbox_check_suite=test -f {_FIX_SENTINEL}",),
    )
    assert kind == "succeeded", message


def test_input_inside_a_word_renders_as_its_value(*, tmp_path: Path, port: FabroPort) -> None:
    # dead_implementer's shape: `origin/<default_branch>...HEAD` in one word.
    body = _single_node_workflow(
        name="FabroEnemyInWordInput",
        script='ref=origin/{{ inputs.default_branch }}...HEAD; echo \\"ref=$ref\\" >&2; test \\"$ref\\" = origin/master...HEAD',
    )
    kind, message = _run_status(
        port=port,
        tmp_path=tmp_path,
        name="in-word-input",
        body=body,
        inputs=("default_branch=master",),
    )
    assert kind == "succeeded", message


def test_input_inside_double_quotes_renders_as_its_value(
    *, tmp_path: Path, port: FabroPort
) -> None:
    # publish_draft's shape: `default_branch="<default_branch>"` and
    # `--base "<default_branch>"`, where a quoting renderer's own quotes would
    # survive as literal characters inside the double quotes.
    body = _single_node_workflow(
        name="FabroEnemyQuotedInput",
        script='default_branch=\\"{{ inputs.default_branch }}\\"; echo \\"default_branch=$default_branch\\" >&2; test \\"$default_branch\\" = master',
    )
    kind, message = _run_status(
        port=port,
        tmp_path=tmp_path,
        name="quoted-input",
        body=body,
        inputs=("default_branch=master",),
    )
    assert kind == "succeeded", message


def test_declared_environment_carries_the_prepare_toolchain(
    *, tmp_path: Path, config: _FabroTier0Config
) -> None:
    # The prepare nodes run mise, just and git. The environment is a property
    # of the factory, so the probe takes it from FABRO_EUT_ENVIRONMENT (the
    # candidate's `livespec-ci`); the pinned engine has no --environment flag.
    environment = os.environ.get("FABRO_EUT_ENVIRONMENT")
    if not environment:
        pytest.skip("set FABRO_EUT_ENVIRONMENT to the factory's declared environment id")
    port = FabroPort(
        fabro_bin=config.fabro_bin,
        target=FabroTarget(server_url=config.server_url, environment=environment),
        runner=ShellCommandRunner(),
        cwd=Path.cwd(),
    )
    body = _single_node_workflow(
        name="FabroEnemyEnvironmentToolchain",
        script='for t in mise just git; do command -v $t >&2 || { echo \\"missing $t\\" >&2; exit 1; }; done',
    )
    kind, message = _run_status(
        port=port, tmp_path=tmp_path, name="environment-toolchain", body=body, inputs=()
    )
    assert kind == "succeeded", message
