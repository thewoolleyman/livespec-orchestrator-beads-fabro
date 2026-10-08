"""Tier 1 Enemy Unit Tests for the run semantics the factory relies on.

Each test launches one tiny script-node workflow and reads the run's terminal
status as the oracle: the script performs the assertion INSIDE the sandbox and
exits non-zero when it does not hold, and `goal_gate=true` turns that exit into
a failed run on every engine measured so far (0.254.0 and 0.378.0-nightly.0).
That keeps the tests engine-agnostic: nothing here parses event or inspect
payloads whose shape differs between engines.

These are the behaviours plan `fabro-currency` must preserve across the Petri
migration (research notes 006 and 007). Run them against a pinned and a
candidate server through the `FABRO_EUT_*` overrides; a delta between the two
legs is the finding, not a broken test. Excluded from `just check`:

    just fabro-enemy-tier1
"""

from __future__ import annotations

from pathlib import Path

from _tier0_support import TIMEOUT_SECONDS, _assert_success, _inspect_record
from _tier1_support import _failure_block, _write_goal, _write_workflow
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort

__all__: list[str] = []

_RUN_TIMEOUT_SECONDS = 300.0
_NEEDS_HUMAN_MARKER = "LIVESPEC_NEEDS_HUMAN"

# The sandbox environment every leg runs under is the server's `default`
# environment: docker, cpu 2, memory 4GB (`~/.fabro/environments/default.toml`
# on both hp instances). cgroup v2 reports that as `cpu.max` "200000 100000"
# and `memory.max` "4000000000" (decimal GB, as the pinned engine applies it).
_EXPECTED_CPU_MAX = "200000 100000"
# The kernel page-rounds the requested 4000000000 (measured 3999997952 on hp),
# so the memory check accepts a narrow band under the requested byte count.
_MEMORY_MAX_LOW = "3990000000"
_MEMORY_MAX_HIGH = "4000000000"

_RESOURCE_LIMITS_WORKFLOW = f"""
digraph FabroEnemyResourceLimits {{
    start [shape=Mdiamond, label="Start"]
    check [shape=parallelogram, label="Check", goal_gate=true, script="c=$(cat /sys/fs/cgroup/cpu.max 2>/dev/null || echo none); m=$(cat /sys/fs/cgroup/memory.max 2>/dev/null || echo none); echo \\"cpu.max=$c memory.max=$m\\" >&2; test \\"$c\\" = '{_EXPECTED_CPU_MAX}' && test \\"$m\\" -ge {_MEMORY_MAX_LOW} && test \\"$m\\" -le {_MEMORY_MAX_HIGH}"]
    exit [shape=Msquare, label="Exit"]
    start -> check
    check -> exit
}}
"""

# A self-loop routed on the previous node's outcome, bounded by a counter the
# script keeps in the sandbox; the final gate asserts the loop ran exactly
# three times. Succeeds only when outcome conditions route and the sandbox
# persists across visits.
_OUTCOME_LOOP_WORKFLOW = """
digraph FabroEnemyOutcomeLoop {
    start [shape=Mdiamond, label="Start"]
    step [shape=parallelogram, label="Step", script="c=$(cat /tmp/eut-outcome-count 2>/dev/null || echo 0); c=$((c+1)); echo $c > /tmp/eut-outcome-count; echo \\"step visit $c\\" >&2; test $c -lt 3"]
    gate [shape=parallelogram, label="Gate", goal_gate=true, script="test \\"$(cat /tmp/eut-outcome-count)\\" = 3"]
    exit [shape=Msquare, label="Exit"]
    start -> step
    step -> step [condition="outcome=succeeded"]
    step -> gate
    gate -> exit
}
"""

# The upstream-documented fixed-count loop: a diamond gate whose exit edge is
# conditioned on `context.internal.node_visit_count`, with the unconditional
# back-edge as the fallback. The counter safety fails the run at visit 6 so an
# engine that never populates the key cannot loop forever.
_VISIT_COUNT_LOOP_WORKFLOW = """
digraph FabroEnemyVisitCountLoop {
    start [shape=Mdiamond, label="Start"]
    improve [shape=parallelogram, label="Improve", goal_gate=true, script="c=$(cat /tmp/eut-visit-count 2>/dev/null || echo 0); c=$((c+1)); echo $c > /tmp/eut-visit-count; echo \\"improve visit $c\\" >&2; test $c -le 5"]
    gate [shape=diamond, label="Done?"]
    exit [shape=Msquare, label="Exit"]
    start -> improve
    improve -> gate
    gate -> exit [condition="context.internal.node_visit_count >= 3"]
    gate -> improve
}
"""

# `max_visits` caps a node's firings. The script would loop ten times; the cap
# must stop it at three and fail the run (the engine's documented behaviour).
_MAX_VISITS_WORKFLOW = """
digraph FabroEnemyMaxVisits {
    start [shape=Mdiamond, label="Start"]
    step [shape=parallelogram, label="Step", max_visits=3, script="c=$(cat /tmp/eut-max-visits 2>/dev/null || echo 0); c=$((c+1)); echo $c > /tmp/eut-max-visits; echo \\"step visit $c\\" >&2; test $c -lt 10"]
    exit [shape=Msquare, label="Exit"]
    start -> step
    step -> step [condition="outcome=succeeded"]
    step -> exit
}
"""

_NEEDS_HUMAN_WORKFLOW = f"""
digraph FabroEnemyNeedsHuman {{
    start [shape=Mdiamond, label="Start"]
    nh [shape=parallelogram, label="NeedsHuman", goal_gate=true, script="echo '{_NEEDS_HUMAN_MARKER}: enemy probe cannot auto-resolve' >&2; exit 1"]
    exit [shape=Msquare, label="Exit"]
    start -> nh
    nh -> exit
}}
"""

_QUOTING_WORKFLOW = """
digraph FabroEnemyQuoting {
    start [shape=Mdiamond, label="Start"]
    q [shape=parallelogram, label="Quote", goal_gate=true, script="X='a b'; Y=\\"$X-$(echo c)\\"; test \\"$Y\\" = 'a b-c' && printf 'quoting-ok %s\\\\n' \\"$Y\\" >&2"]
    exit [shape=Msquare, label="Exit"]
    start -> q
    q -> exit
}
"""


def _run_status(*, port: FabroPort, tmp_path: Path, name: str, body: str) -> tuple[str, str]:
    """Launch `body` and return `(status kind, failure message)` from inspect."""
    workflow = _write_workflow(tmp_path=tmp_path, name=name, body=body)
    goal = _write_goal(tmp_path=tmp_path, title=name)
    run = port.run(
        workflow_toml=workflow,
        goal_file=goal,
        inputs=(),
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


def test_docker_resource_limits_reach_the_sandbox(*, tmp_path: Path, port: FabroPort) -> None:
    kind, message = _run_status(
        port=port, tmp_path=tmp_path, name="resource-limits", body=_RESOURCE_LIMITS_WORKFLOW
    )
    assert kind == "succeeded", message


def test_outcome_conditions_route_a_bounded_self_loop(*, tmp_path: Path, port: FabroPort) -> None:
    kind, message = _run_status(
        port=port, tmp_path=tmp_path, name="outcome-loop", body=_OUTCOME_LOOP_WORKFLOW
    )
    assert kind == "succeeded", message


def test_node_visit_count_condition_exits_a_fixed_loop(*, tmp_path: Path, port: FabroPort) -> None:
    kind, message = _run_status(
        port=port, tmp_path=tmp_path, name="visit-count-loop", body=_VISIT_COUNT_LOOP_WORKFLOW
    )
    assert kind == "succeeded", message


def test_max_visits_caps_a_self_loop_as_a_failed_run(*, tmp_path: Path, port: FabroPort) -> None:
    kind, message = _run_status(
        port=port, tmp_path=tmp_path, name="max-visits", body=_MAX_VISITS_WORKFLOW
    )
    assert kind == "failed", message
    # The cap, not the counter safety, must be what stopped it.
    assert "step visit 10" not in message


def test_needs_human_marker_is_readable_from_the_failed_run(
    *, tmp_path: Path, port: FabroPort
) -> None:
    kind, message = _run_status(
        port=port, tmp_path=tmp_path, name="needs-human", body=_NEEDS_HUMAN_WORKFLOW
    )
    assert kind == "failed", message
    assert _NEEDS_HUMAN_MARKER in message


def test_script_quoting_is_verbatim_shell(*, tmp_path: Path, port: FabroPort) -> None:
    kind, message = _run_status(
        port=port, tmp_path=tmp_path, name="quoting", body=_QUOTING_WORKFLOW
    )
    assert kind == "succeeded", message
