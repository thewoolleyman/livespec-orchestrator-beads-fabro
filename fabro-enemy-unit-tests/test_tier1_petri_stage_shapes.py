"""Tier 1 Enemy Unit Tests for the two STAGE-level Petri-era regressions.

`test_tier1_real_node_shapes.py` beside this file probes what one NODE is
handed: a rendered template, a declared environment. The two failures below are
properties of a stage's SURROUNDINGS instead -- what the engine COMMITS after a
step runs, and what it CARRIES into the next node's prompt -- so no node-shape
probe can see either. Each cost a two-to-three-hour canary on hp-candidate
(canaries 5 to 12, 2026-10-11 to 2026-10-15), and each canary surfaced only the
first failure it met, because a run stops there:

- THE SANDBOX-ROOT CHECKPOINT (`bd-ib-dud2ww`, `bd-ib-ccywva`, `bd-ib-5qxa5q`).
  The Petri-era engine runs each prepare step as a graph node and checkpoints
  after it, staging what the step left in the worktree; and on that engine the
  repository clone IS `/workspace`, so every `/workspace` path a prepare step
  writes is committed into the run branch and from there into the draft pull
  request's diff, as a change no implementer wrote. Run 01M4Q45S5AGK met its own
  committed gh-refresh bundle as an untracked file and refused at pick 26; run
  01M4XNM4BBMYFPQDA6X5JCBDYM committed 286 lines of credential-use guard into
  draft pull request 2977.
- THE CARRIED PREAMBLE (`bd-ib-7zxqyl`). Fabro's DEFAULT `compact` fidelity is
  a per-stage report with handler-specific detail and NO declared size target,
  so it grows with the volume of the stages behind it. On run
  01M4XNM4BBMYFPQDA6X5JCBDYM review succeeded after reporting about 361000
  tokens of context, and `disposition`'s ACP prompt was then refused with
  `Internal error: Prompt is too long` against the 200000-token window of its
  configured model, so the run fell to needs_human having decided nothing.

EACH PROBE COPIES THE SHAPE THE REAL FACTORY USES TO SURVIVE ITS FAILURE, AND
READS THAT SHAPE FROM PRODUCTION RATHER THAN RESTATING IT. The checkpoint probe
renders its exclusion through `worktree_exclude_script`, the one renderer every
Dispatcher-materialized path goes through, and the preamble probe takes its
`fidelity` from the real graph's own `disposition` node. A probe that restated
either would keep passing after the real one changed, which is the whole
failure mode a stage probe exists to retire.

Both run against whichever server the `FABRO_EUT_*` overrides select, so the
same two probes compare the pinned engine with the Petri-era candidate. A delta
between the two legs is the finding, not a broken test. Excluded from
`just check`:

    just fabro-enemy-tier1
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from _fake_acp_agent import (
    BULK_RESPONSE_BYTES,
    BULK_RESPONSE_MODE,
    PROMPT_BOUND_BYTES,
    PROMPT_BOUND_MODE,
)
from _tier0_support import (
    TIMEOUT_SECONDS,
    _assert_success,
    _FabroTier0Config,
    _inspect_record,
)
from _tier1_support import _failure_block, _write_goal, _write_workflow
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_worktree_exclude import (
    worktree_exclude_script,
)
from livespec_orchestrator_beads_fabro.commands._fabro_client import overlay_graph_reference
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroPort,
    FabroRunResult,
    FabroTarget,
)

__all__: list[str] = []

# Both probes clone this repository into the sandbox before their first node
# runs, so the ceiling covers a clone plus two stages rather than one script.
_RUN_TIMEOUT_SECONDS = 600.0
_REAL_GRAPH = (
    Path(__file__).resolve().parent.parent
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)

# The sandbox mount both engines hand a run. The target repository's clone sits
# AT it on the Petri-era engine and at `/workspace/<repo>` on the pinned one,
# which is the whole reason a materialized path can land inside the run's own
# worktree on one engine and outside it on the other.
_SANDBOX_MOUNT = "/workspace"
# The path the prepare step writes AT the sandbox root -- the shape every
# Dispatcher materialization has (`_dispatcher_gh_refresh`'s bundle,
# `_dispatcher_credential_use_guard`'s guard script, the sandbox CODEX_HOME).
_SANDBOX_ROOT_MARKER_NAME = "eut-sandbox-root-marker"
_SANDBOX_ROOT_MARKER = f"{_SANDBOX_MOUNT}/{_SANDBOX_ROOT_MARKER_NAME}"
# THE CONTROL, and it is load-bearing rather than decoration: an untracked file
# the SAME prepare step writes inside the clone, wherever the clone is. Without
# it the probe passes on an engine that checkpointed nothing at all, or that
# stages no untracked file -- two readings indistinguishable from the exclusion
# working, and both earned by an instrument that could not have returned a hit.
_CLONE_CONTROL_NAME = "eut-checkpoint-control"

# Relative to the repository root the sandbox clones; the fake agent must be on
# the commit the run observes.
_FAKE_AGENT = "fabro-enemy-unit-tests/_fake_acp_agent.py"
_BULK_RECORD = "/tmp/eut-preamble-bulk-record.jsonl"
_BOUND_RECORD = "/tmp/eut-preamble-bound-record.jsonl"

# Where the verify node parks the run branch's tree listing. A file rather than
# a shell variable so the script needs no double quotes of its own, which keeps
# it legible as one DOT attribute.
_TREE_LISTING = "/tmp/eut-run-branch-tree"

_WRITE_PREPARE_SCRIPT = (
    "set -eu\n"
    'top="$(git rev-parse --show-toplevel)"\n'
    f"printf 'eut\\n' > \"$top/{_CLONE_CONTROL_NAME}\"\n"
    f"mkdir -p {_SANDBOX_MOUNT}\n"
    f"printf 'eut\\n' > {_SANDBOX_ROOT_MARKER}\n"
)

# The first graph node exists only so a checkpoint lands between preparation
# and the verify node on BOTH engines: the Petri-era engine checkpoints after
# each prepare step, while the pinned engine's first checkpoint follows its
# first graph node, and the probe must not depend on which. `git status` makes
# the node's own export say what the worktree held when it ran.
_SETTLE_SCRIPT = "git status --porcelain >&2"

_VERIFY_SCRIPT = (
    f"git ls-tree -r --name-only HEAD > {_TREE_LISTING}; "
    f"if ! grep -qx {_CLONE_CONTROL_NAME} {_TREE_LISTING}; then "
    "echo 'EUT_CHECKPOINT_INERT: the control file preparation wrote inside the clone "
    "is absent from the run branch, so this run cannot say whether a sandbox-root "
    "file would have been committed' >&2; exit 1; fi; "
    f"if grep -q {_SANDBOX_ROOT_MARKER_NAME} {_TREE_LISTING}; then "
    "echo 'EUT_SANDBOX_ROOT_COMMITTED: a file written at the sandbox root during "
    "preparation is in the run branch after a checkpoint' >&2; exit 1; fi"
)

_CHECKPOINT_GRAPH = f"""
digraph FabroEnemySandboxRootCheckpoint {{
    start [shape=Mdiamond, label="Start"]
    settle [shape=parallelogram, label="Settle", script="{_SETTLE_SCRIPT}"]
    verify [shape=parallelogram, label="Verify", goal_gate=true, script="{_VERIFY_SCRIPT}"]
    exit [shape=Msquare, label="Exit"]
    start -> settle
    settle -> verify
    verify -> exit
}}
"""


def _real_node_attribute(*, node: str, attribute: str) -> str:
    """Return a plain `attribute="value"` of `node` in the real implement graph.

    Deliberately separate from `test_tier1_real_node_shapes._real_node_script`,
    which reads the ONE attribute carrying shell escapes and therefore needs an
    escape-aware pattern. A plain attribute's value cannot contain a quote, so
    matching one with that looser pattern would accept a malformed value this
    probe has to refuse.
    """
    text = _REAL_GRAPH.read_text()
    block = re.search(rf"^\s+{re.escape(node)} \[(.*?)^\s+\]", text, re.MULTILINE | re.DOTALL)
    assert block is not None, f"node {node} not found in {_REAL_GRAPH}"
    value = re.search(rf'^\s+{re.escape(attribute)}="([^"]*)"', block.group(1), re.MULTILINE)
    assert value is not None, f"node {node} declares no {attribute} in {_REAL_GRAPH}"
    return value.group(1)


def _acp_config(*, mode: str, record: str) -> str:
    """The DOT-escaped `acp.config` JSON that launches the in-suite fake agent.

    Built by `json.dumps` and then escaped, rather than hand-written with its
    quotes already doubled: the escape is the step that has gone wrong before
    (`bd-ib-4gkfaa`), and one rendering of it is cheaper to trust than two.
    """
    payload = json.dumps({"command": "python3", "args": [_FAKE_AGENT, mode, record], "env": {}})
    return payload.replace('"', '\\"')


def _preamble_graph() -> str:
    """The bulk-answer stage followed by the real adjudicator's bounded shape."""
    fidelity = _real_node_attribute(node="disposition", attribute="fidelity")
    bulk = _acp_config(mode=BULK_RESPONSE_MODE, record=_BULK_RECORD)
    bound = _acp_config(mode=PROMPT_BOUND_MODE, record=_BOUND_RECORD)
    return f"""
digraph FabroEnemyCarriedPreambleBound {{
    start [shape=Mdiamond, label="Start"]
    bulk [shape=box, label="Bulk", backend="acp", acp.config="{bulk}", prompt="answer at length"]
    bounded [shape=box, label="Bounded", backend="acp", goal_gate=true, fidelity="{fidelity}", acp.config="{bound}", prompt="say hi"]
    exit [shape=Msquare, label="Exit"]
    start -> bulk
    bulk -> bounded
    bounded -> exit
}}
"""


def _run_config(*, graph: Path, prepare_scripts: tuple[str, ...]) -> str:
    """The run config declaring the clone, the managed branches and the steps.

    Every key here is one the real factory's committed `workflow.toml` carries.
    `push = false` on both managed branches is load-bearing rather than
    cosmetic: a probe is not entitled to publish a `fabro/run/*` ref to origin.
    `skip_git_hooks` matches the real declaration so the checkpoint under test
    is the bare `git add` plus `git commit` the factory actually runs.

    Each script rides a TOML LITERAL multi-line string. That is not a style
    choice: `worktree_exclude_script`'s body carries `printf '%s\\n'`, and a
    basic string would process that backslash escape and hand the sandbox a
    `printf` whose format ends in a real newline.
    """
    steps = "\n".join(
        f"[[run.prepare.steps]]\nscript = '''\n{script}\n'''\n" for script in prepare_scripts
    )
    return (
        "_version = 1\n\n"
        f'[workflow]\ngraph = "{graph}"\n\n'
        "[run.clone]\nenabled = true\n\n"
        "[run.run_branch]\nenabled = true\npush = false\n\n"
        "[run.meta_branch]\nenabled = true\npush = false\n\n"
        "[run.checkpoint]\nskip_git_hooks = true\n\n"
        f"{steps}"
    )


def _probe_port(*, config: _FabroTier0Config, fabro_version: str | None) -> FabroPort:
    """A port on the configured factory, carrying the environment when declared.

    `FABRO_EUT_ENVIRONMENT` rides every probe in this file rather than only the
    one that reads a toolchain: the candidate engine takes the sandbox image
    ONLY from `--environment` and otherwise falls back to the catalog default,
    which is where canary 4 died in prepare. The pinned engine has no such flag
    and `fabro_run_argv` emits none when the value is absent.

    `fabro_version` decides the LAUNCH SHAPE and the two probes need different
    ones, which is `_fabro_client`'s own documented split: a Petri-era client is
    handed a workflow PACKAGE directory, so the config path a version-carrying
    port is given must be the `workflow.toml` inside one, while a bare graph is
    launched through a port carrying no version at all.
    """
    return FabroPort(
        fabro_bin=config.fabro_bin,
        target=FabroTarget(
            server_url=config.server_url,
            environment=os.environ.get("FABRO_EUT_ENVIRONMENT"),
        ),
        runner=ShellCommandRunner(),
        cwd=Path.cwd(),
        fabro_version=fabro_version,
    )


def _terminal(*, port: FabroPort, run: FabroRunResult) -> tuple[str, str]:
    """Read `(status kind, failure message)` off one launched run."""
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


def _packaged_run_status(
    *,
    config: _FabroTier0Config,
    tmp_path: Path,
    name: str,
    body: str,
    prepare_scripts: tuple[str, ...],
) -> tuple[str, str]:
    """Launch `body` under a run config declaring `prepare_scripts`, either era."""
    version = f"fabro {config.expected_client_version}"
    package = tmp_path / f"{name}-package"
    package.mkdir()
    graph = package / "workflow.fabro"
    _ = graph.write_text(body.strip() + "\n", encoding="utf-8")
    overlay = package / "workflow.toml"
    _ = overlay.write_text(
        _run_config(
            graph=overlay_graph_reference(version=version, graph=graph, package_dir=package),
            prepare_scripts=prepare_scripts,
        ),
        encoding="utf-8",
    )
    port = _probe_port(config=config, fabro_version=version)
    run = port.run(
        workflow_toml=overlay,
        goal_file=_write_goal(tmp_path=tmp_path, title=name),
        inputs=(),
        timeout_seconds=_RUN_TIMEOUT_SECONDS,
    )
    return _terminal(port=port, run=run)


def _graph_run_status(
    *, config: _FabroTier0Config, tmp_path: Path, name: str, body: str
) -> tuple[str, str]:
    """Launch one bare graph, the shape every other tier 1 ACP probe uses."""
    port = _probe_port(config=config, fabro_version=None)
    run = port.run(
        workflow_toml=_write_workflow(tmp_path=tmp_path, name=name, body=body),
        goal_file=_write_goal(tmp_path=tmp_path, title=name),
        inputs=(),
        timeout_seconds=_RUN_TIMEOUT_SECONDS,
    )
    return _terminal(port=port, run=run)


def test_a_sandbox_root_file_written_in_preparation_stays_out_of_the_run_branch(
    *, config: _FabroTier0Config, tmp_path: Path
) -> None:
    """The run branch must not carry a `/workspace` file preparation wrote.

    The exclusion is rendered FIRST, by the production renderer, exactly as
    every Dispatcher projection renders it -- the checkpoint lands after the
    step that wrote a path, so an exclusion added afterwards is already too
    late. The oracle is the run's terminal status: the verify node reads the run
    branch's own tree inside the sandbox, because the test cannot see the
    sandbox and the draft pull request this defect reached does not exist here.
    """
    kind, message = _packaged_run_status(
        config=config,
        tmp_path=tmp_path,
        name="sandbox-root-checkpoint",
        body=_CHECKPOINT_GRAPH,
        prepare_scripts=(
            worktree_exclude_script(paths=(_SANDBOX_ROOT_MARKER,), label="fabro-eut-sandbox-root"),
            _WRITE_PREPARE_SCRIPT,
        ),
    )
    assert kind == "succeeded", message


def test_an_agent_nodes_prompt_stays_under_its_bound_after_a_very_large_response(
    *, config: _FabroTier0Config, tmp_path: Path
) -> None:
    """A bounded node's prompt must stay under its bound however large the stage before it.

    The oracle is the fake agent's own judgement: it measures the prompt text it
    was handed and exits non-zero above `PROMPT_BOUND_BYTES`, which fails the
    goal-gated node and so the run. Nothing the host can read reports the
    carried size, which is why the measurement has to happen inside the sandbox.
    """
    # The instrument has to be able to return the other answer: a bulk answer
    # smaller than the bound would make this probe pass whatever the engine
    # carried forward.
    assert BULK_RESPONSE_BYTES > PROMPT_BOUND_BYTES
    kind, message = _graph_run_status(
        config=config,
        tmp_path=tmp_path,
        name="carried-preamble-bound",
        body=_preamble_graph(),
    )
    assert kind == "succeeded", message
