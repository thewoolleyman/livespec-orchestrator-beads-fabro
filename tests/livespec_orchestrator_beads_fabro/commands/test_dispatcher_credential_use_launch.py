"""Every coding-agent launch route runs behind the guard, exercised by EXECUTION.

The projection sibling covers how the guard and its inputs REACH a sandbox. This
module's subject is the other half of the same assertion: that the thing which
actually execs a coding agent goes THROUGH that guard, on every route a supported
dispatch can take, and that executing the result really does stop at the deadline.

WHAT THIS MODULE COVERS, STATED NARROWLY SO IT IS NOT OVERSOLD. Every ACP node in
the graphs this repository ships declares `acp.command="{{ inputs.<node>_adapter
}}"`, and the Dispatcher supplies the actual command through `fabro run --input
<node>_adapter=<rendered>`. So wrapping that render covers every launch THOSE
graphs take, and it covers them through one chokepoint -- the built-in catalog
adapters, a repository's `dispatcher.acp_nodes` overlay and a per-dispatch
`--acp-node` override all converge on it, where a guard attached per adapter
IDENTITY would leave whichever route nobody remembered unprotected.

IT DOES NOT FOLLOW THAT EVERY ACCEPTABLE GRAPH IS COVERED, and an earlier draft of
this docstring claimed it did -- that `run_inputs` was "the ONLY channel by which a
launch command reaches the engine". That was false, and it was falsified by
execution rather than by review: a control replacing one node's `acp.command` input
reference with a literal command saw the requirement resolve, the guard install and
the startup check pass, and the literal command then run 1.003 seconds PAST the
absolute deadline, exit 0. A node declaring a literal command, or declaring its
process through `acp.config`, never reads the wrapped input at all.

Recognising which graphs are guardable, and REFUSING the rest before launch, is
`_dispatcher_credential_use_routes`' subject and is covered by its own tests. What
the cases here establish is narrower and still necessary: that the launches which
DO route through a wrapped input are guarded, and that executing one really is
bounded by the deadline.

THE FIRST CASE GRADES ALL NINE NODES THROUGH THE REAL RESOLVER rather than one
adapter through a fixture, because a single node passing says nothing about the
other eight.

THE EXECUTION CASES USE A SYNTHETIC COMMAND ON PURPOSE. The real adapters are not
installed here, so launching one would measure the absence of a binary; what is
under test is whether the WRAP the production renderer produces enforces when it
runs. So those cases wrap a shell command through the SAME production function and
then execute the result the way the engine does -- POSIX-tokenizing it and
treating leading `KEY=value` tokens as environment, which is exactly what makes the
env-prefix ordering below load-bearing rather than cosmetic.
"""

from __future__ import annotations

import importlib
import os
import re
import shlex
import subprocess
import time
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_catalogs import builtin_catalogs
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import resolve_acp_nodes
from livespec_orchestrator_beads_fabro.commands._config_acp import resolve_acp_node_overlays
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_nodes import (
    dispatch_acp_overlays,
    workflow_layer,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard import (
    CREDENTIAL_USE_DEADLINE_ENV_VAR,
    GUARD_REFUSAL_EXIT_CODE,
    GUARD_SCRIPT_PATH,
    GUARD_TERM_GRACE_SECONDS,
    guard_script_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    dispatch_fabro_run_inputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan

_SANDBOX_ROOT = "/workspace"
_STEP_TIMEOUT_SECONDS = 60

# An env assignment as the engine's POSIX tokenization recognizes one: a leading
# token of this shape becomes environment rather than the executable.
_ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# Must exceed the guard's TERM grace, or TERM would be due before the child had
# started and the case would be measuring process startup instead of the deadline.
_SOON_SECONDS = GUARD_TERM_GRACE_SECONDS + 4

# Signal-delivery slack only. The guard floors a fractional measurement, so its
# KILL is due at or BEFORE the epoch by construction; this covers the scheduling
# delay between the signal and the child stopping. Never widen it to make a late
# kill pass -- that is precisely the defect such a widening would hide.
_HARD_TOLERANCE_SECONDS = 0.5

_WORKFLOW_TOML = Path(".claude-plugin/.fabro/workflows/implement-work-item/workflow.toml")

_GUARD_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard"


def _guarded(*, rendered: str) -> str:
    """Wrap one launch string through the production wrapper.

    Resolved by name rather than imported at module scope so a case fails on its
    own assertion while the wrapper does not exist yet, instead of dying at
    collection and proving only unimportability.
    """
    wrap = getattr(importlib.import_module(_GUARD_MODULE), "guarded_adapter_string", None)
    assert wrap is not None, "guarded_adapter_string is not implemented yet"
    return str(wrap(rendered=rendered))


def _rendered_adapters(*, repo: Path) -> dict[str, str]:
    """Every node's launch string, through the REAL resolver and argv builder.

    Resolved through the real three-layer merge against this repository's
    committed workflow inputs, then rendered through the real dispatch argv
    builder, so what is graded is the string a node's `acp.command` would
    actually receive.
    """
    overlays = resolve_acp_node_overlays(cwd=repo)
    assert not isinstance(overlays, str), overlays
    workflow_inputs = workflow_layer(committed=_WORKFLOW_TOML, catalogs=builtin_catalogs())
    assert not isinstance(workflow_inputs, str), workflow_inputs
    resolution = resolve_acp_nodes(
        workflow_inputs=workflow_inputs,
        repository=overlays,
        dispatch={},
    )
    assert not isinstance(resolution, str), resolution
    inputs = dispatch_fabro_run_inputs(
        plan=build_plan(
            repo=repo,
            work_item_id="bd-ib-yx7pdm",
            workflow_toml=repo / "workflow.toml",
            goal_file=repo / "goal.md",
            fabro_bin="fabro",
            janitor=None,
            janitor_checkout=repo / "janitor",
            acp_nodes=resolution,
        )
    )
    rendered: dict[str, str] = {}
    for node, name in resolution.inputs.items():
        prefix = f"{name}="
        [value] = [pair.removeprefix(prefix) for pair in inputs if pair.startswith(prefix)]
        rendered[node] = value
    return rendered


def _engine_launch(*, rendered: str, sandbox: Path) -> tuple[dict[str, str], list[str]]:
    """Split a launch string the way the engine does: env prefix, then argv.

    POSIX tokenization, then leading `KEY=value` tokens become environment. This
    is the step that makes the env prefix ordering matter: the guard must sit
    between the assignments and the executable, or the assignments would become
    arguments to it.
    """
    tokens = [token.replace(_SANDBOX_ROOT, str(sandbox)) for token in shlex.split(rendered)]
    env: dict[str, str] = {}
    index = 0
    for token in tokens:
        if _ENV_ASSIGNMENT_RE.match(token) is None:
            break
        key, _, value = token.partition("=")
        env[key] = value
        index += 1
    return env, tokens[index:]


def _install_guard(*, sandbox: Path) -> Path:
    """Place the SHIPPED guard where a rendered launch string expects it."""
    guard = Path(GUARD_SCRIPT_PATH.replace(_SANDBOX_ROOT, str(sandbox)))
    guard.parent.mkdir(parents=True, exist_ok=True)
    _ = guard.write_text(guard_script_text(), encoding="utf-8")
    guard.chmod(0o700)
    return guard


def _launch(
    *,
    rendered: str,
    sandbox: Path,
    deadline: int,
    extra_env: dict[str, str] | None = None,
    timeout: int = _STEP_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    """Execute one rendered launch string as the engine would."""
    adapter_env, argv = _engine_launch(rendered=rendered, sandbox=sandbox)
    child_env = dict(os.environ)
    child_env[CREDENTIAL_USE_DEADLINE_ENV_VAR] = str(deadline)
    child_env.update(extra_env or {})
    # The adapter's own assignments are applied AFTER the projected ones, exactly
    # as the engine's exec would, so a case can observe whether an adapter is able
    # to displace a projected value.
    child_env.update(adapter_env)
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=child_env,
        check=False,
    )


def _heartbeat_adapter(*, beat_file: Path) -> str:
    """A synthetic adapter whose command writes a heartbeat until it is stopped.

    The heartbeat is the instrument rather than process existence: a
    stopped-but-unreaped process writes nothing, so the last timestamp is the last
    moment the command actually executed -- and a zombie holds no credential.
    """
    inner = f"while : ; do date +%s.%N >> {beat_file}; sleep 0.2; done"
    return _guarded(rendered=f"/bin/sh -c {shlex.quote(inner)}")


def _beats(*, beat_file: Path) -> list[float]:
    """Every instant the command was observed EXECUTING; empty if it never ran."""
    if not beat_file.exists():
        return []
    return [
        float(line.strip())
        for line in beat_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _last_beat(*, beat_file: Path) -> float:
    beats = _beats(beat_file=beat_file)
    assert beats, "the command never recorded a heartbeat, so nothing was measured"
    return beats[-1]


def test_every_resolved_adapter_launches_through_the_guard(tmp_path: Path) -> None:
    """ALL NINE nodes, through the real resolver: each launches behind the guard.

    The claim is "every supported route", so every node this repository's workflow
    declares is graded rather than one sampled adapter. The guard must sit AFTER
    any env assignments and BEFORE the executable: the engine turns leading
    `KEY=value` tokens into environment, so a guard placed first would swallow
    them as its own arguments and the adapter would lose its configuration.
    """
    adapters = _rendered_adapters(repo=tmp_path)
    assert len(adapters) >= 9, adapters
    for node, rendered in adapters.items():
        adapter_env, argv = _engine_launch(rendered=rendered, sandbox=tmp_path)
        assert argv[:3] == [
            "/bin/sh",
            str(tmp_path / ".livespec/credential-use-guard.sh"),
            "--",
        ], f"node {node} does not launch through the guard: {rendered}"
        # The wrapped command is still there behind the guard, and the adapter's
        # own environment survived in front of it.
        assert len(argv) > 3, node
        assert CREDENTIAL_USE_DEADLINE_ENV_VAR not in adapter_env, node


def test_a_guarded_launch_runs_its_command_while_the_deadline_is_future(
    tmp_path: Path,
) -> None:
    """THE POSITIVE CONTROL: a guarded launch still actually runs the agent.

    An implementation that refused every launch would satisfy both negatives below
    and leave the factory unable to do any work at all.
    """
    _ = _install_guard(sandbox=tmp_path)
    marker = tmp_path / "ran"
    rendered = _guarded(rendered=f"/bin/sh -c {shlex.quote(f'printf done > {marker}')}")
    result = _launch(rendered=rendered, sandbox=tmp_path, deadline=int(time.time()) + 3600)
    assert result.returncode == 0, result.stderr
    assert marker.read_text(encoding="utf-8") == "done"


def test_a_guarded_launch_refuses_a_late_start(tmp_path: Path) -> None:
    """A node entered AFTER the deadline never execs the agent.

    This is what makes inter-stage and queue delay count against the bound rather
    than being forgiven: the refusal is observed as the command's own side effect
    being ABSENT, not merely as a non-zero exit.
    """
    _ = _install_guard(sandbox=tmp_path)
    marker = tmp_path / "ran"
    rendered = _guarded(rendered=f"/bin/sh -c {shlex.quote(f'printf done > {marker}')}")
    result = _launch(rendered=rendered, sandbox=tmp_path, deadline=int(time.time()) - 120)
    assert result.returncode == GUARD_REFUSAL_EXIT_CODE, result.stdout
    assert not marker.exists(), "the agent ran despite the deadline having passed"

    # And a refused launch leaves NO heartbeat at all, which is the instrument the
    # enforcement cases read: process existence cannot tell a never-started command
    # from a stopped-but-unreaped one, while an absent beat file can.
    beat_file = tmp_path / "beats"
    refused = _launch(
        rendered=_heartbeat_adapter(beat_file=beat_file),
        sandbox=tmp_path,
        deadline=int(time.time()) - 120,
    )
    assert refused.returncode == GUARD_REFUSAL_EXIT_CODE, refused.stdout
    assert _beats(beat_file=beat_file) == []


def test_an_adapter_with_no_executable_is_refused_rather_than_launched(
    tmp_path: Path,
) -> None:
    """An adapter that is ALL environment and no command refuses, fail-closed.

    A degenerate configuration rather than a hypothetical: the adapter layers merge
    env key by key, so a repository overlay supplying only environment for a node
    whose command never resolved renders exactly this. The wrap leaves the guard
    with nothing to exec, and the guard refuses by its own "no command was given"
    arm rather than silently succeeding at doing nothing -- which would read as a
    green agent node that never ran.
    """
    _ = _install_guard(sandbox=tmp_path)
    all_env = "ANTHROPIC_MODEL=claude-opus-5 CLAUDE_CODE_EFFORT_LEVEL=high"

    # The engine's own split of the UNWRAPPED form, which is WHY the guard ends up
    # with nothing: every token is an assignment, so no executable remains. Asserted
    # here because it is the premise the refusal below rests on.
    adapter_env, argv = _engine_launch(rendered=all_env, sandbox=tmp_path)
    assert argv == []
    assert adapter_env == {
        "ANTHROPIC_MODEL": "claude-opus-5",
        "CLAUDE_CODE_EFFORT_LEVEL": "high",
    }

    result = _launch(
        rendered=_guarded(rendered=all_env), sandbox=tmp_path, deadline=int(time.time()) + 3600
    )
    assert result.returncode == GUARD_REFUSAL_EXIT_CODE, result.stdout
    assert "no command" in result.stderr


def test_a_guarded_launch_is_stopped_by_the_deadline(tmp_path: Path) -> None:
    """A running agent does not continue past the absolute deadline.

    The enforcement half, measured on a real process through the real rendered
    launch string: the heartbeat's last entry must not be after the epoch.
    """
    _ = _install_guard(sandbox=tmp_path)
    beat_file = tmp_path / "beats"
    deadline = int(time.time()) + _SOON_SECONDS
    result = _launch(
        rendered=_heartbeat_adapter(beat_file=beat_file),
        sandbox=tmp_path,
        deadline=deadline,
    )
    assert result.returncode != 0 or beat_file.exists(), result.stderr
    last_beat = _last_beat(beat_file=beat_file)
    assert (
        last_beat <= deadline + _HARD_TOLERANCE_SECONDS
    ), f"the agent was still executing {last_beat - deadline:.3f}s past the deadline"


def test_a_retried_launch_does_not_get_a_fresh_budget(tmp_path: Path) -> None:
    """The deadline is an INSTANT, so a retry inherits what is LEFT of it.

    A duration would hand every retry a full allowance, which is how a bounded run
    becomes unbounded by failing repeatedly. Both launches are issued against the
    SAME deadline, and the assertion is that NO beat from EITHER of them falls after
    that instant: a retry granted a fresh budget would run a further whole
    allowance past it.

    THE ASSERTION IS OVER THE BEATS RATHER THAN THE RETRY'S EXIT CODE, because the
    guard's TERM grace lands BEFORE the deadline -- so the first launch returns with
    several seconds of budget still unspent, and whether the retry has enough left
    to start at all depends on where that grace fell. Both outcomes are correct;
    executing past the deadline is the only thing that is not. An earlier draft of
    this case asserted the retry was REFUSED, which demanded behaviour a correct
    guard does not produce.
    """
    _ = _install_guard(sandbox=tmp_path)
    deadline = int(time.time()) + _SOON_SECONDS
    first = tmp_path / "beats-first"
    second = tmp_path / "beats-second"
    _ = _launch(rendered=_heartbeat_adapter(beat_file=first), sandbox=tmp_path, deadline=deadline)
    _ = _launch(rendered=_heartbeat_adapter(beat_file=second), sandbox=tmp_path, deadline=deadline)

    beats = _beats(beat_file=first) + _beats(beat_file=second)
    assert beats, "neither launch recorded a heartbeat, so nothing was measured"
    latest = max(beats)
    assert latest <= deadline + _HARD_TOLERANCE_SECONDS, (
        f"a launch was still executing {latest - deadline:.3f}s past the absolute "
        "deadline, so a retry was granted a fresh budget"
    )


def test_an_adapter_declaring_the_deadline_variable_refuses_the_dispatch() -> None:
    """An adapter that sets the deadline itself is REFUSED at resolution.

    The engine places an adapter's env assignments ahead of the executable, so
    they are applied to the guard's OWN process -- which means an adapter able to
    declare this name could hand itself any deadline it liked and the bound would
    be advisory. It is refused where adapters are VALIDATED rather than where they
    are wrapped, because a refusal has to reach the operator as a dispatch refusal
    naming the variable, and the wrap step has no channel to report one.

    The positive control is the first case in this module: ordinary adapters, which
    declare no such variable, resolve and render normally.
    """
    overlays = dispatch_acp_overlays(
        overrides=(f"implement={CREDENTIAL_USE_DEADLINE_ENV_VAR}=9999999999 /usr/bin/agent",),
        catalogs=builtin_catalogs(),
    )
    assert not isinstance(overlays, str), overlays
    workflow_inputs = workflow_layer(committed=_WORKFLOW_TOML, catalogs=builtin_catalogs())
    assert not isinstance(workflow_inputs, str), workflow_inputs

    refusal = resolve_acp_nodes(
        workflow_inputs=workflow_inputs,
        repository={},
        dispatch=overlays,
    )
    assert isinstance(refusal, str), refusal
    assert CREDENTIAL_USE_DEADLINE_ENV_VAR in refusal
    assert "implement" in refusal
