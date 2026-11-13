"""Every `output_schema="routing"` command node prints a routing directive on its ordinary lap.

The engine reads a routing-schema node's stdout for a JSON object carrying a
routing field. A script that exits 0 with nothing on stdout is refused ("the
script's output is not a routing directive"), the refusal counts as a
deterministic failure, and the third one ends the run `RoutingBlocked`.
Measured: livespec-dev-tooling-o4j3kg run 01M78J9HFWDTK7VPNDTBPBBPF6 died that
way at `fix_commit_settle`, whose success path ended in a bare `exit 0` after
PR #4989 gave it the routing schema.

These cases discover every routing-schema command node in every committed
workflow graph, run each node's ORDINARY lap (the path a healthy run takes on
almost every visit) in a real throwaway repository, and require a routing
directive whose label the committed graph resolves to the expected successor.
The discovery is the recurrence guard: a new routing-schema node with no
ordinary lap here fails `test_every_routing_schema_node_has_an_ordinary_lap`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_program import (
    COMMIT_RUNNER_PROGRAM_FILENAME,
    commit_runner_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_ROOTS = (
    _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows",
    _REPO_ROOT / ".fabro" / "workflows",
)
_IMPLEMENT = ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
_DEFAULT_BRANCH_TEMPLATE = re.compile(r"\{\{\s*inputs\.default_branch\s*\}\}")
_PASSING_HOOK = "#!/bin/sh\nprintf 'lefthook v1.13.6  hook: pre-commit\\n'\nexit 0\n"


@dataclass(frozen=True)
class _Lap:
    """What one ordinary visit hands the node beyond its checkout."""

    environment: dict[str, str] = field(default_factory=dict)
    stdin: str = ""


def _clean_environment() -> dict[str, str]:
    """The child environment without GIT_ or coverage variables from an outer commit hook."""
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GIT_", "COV_CORE", "COVERAGE"))
    }


def _git(*, repo: Path, argv: tuple[str, ...]) -> str:
    environment = {**_clean_environment(), "GIT_EDITOR": "true", "GIT_CONFIG_GLOBAL": "/dev/null"}
    result = subprocess.run(
        ("git", *argv), cwd=repo, check=True, capture_output=True, text=True, env=environment
    )
    return result.stdout.strip()


def _routing_nodes() -> set[tuple[str, str]]:
    """Every (graph, node) pair whose node declares the routing output schema."""
    found: set[tuple[str, str]] = set()
    for root in _WORKFLOW_ROOTS:
        for path in sorted(root.rglob("*.fabro")):
            graph = parse_dot_graph(text=path.read_text(encoding="utf-8"))
            assert not isinstance(graph, str), (path, graph)
            relative = path.relative_to(_REPO_ROOT).as_posix()
            found.update(
                (relative, name)
                for name, attributes in graph.nodes.items()
                if attributes.get("output_schema") == "routing"
            )
    return found


def _no_setup(*, checkout: Path, scratch: Path) -> _Lap:
    """A lap that needs only an initialized repository."""
    del checkout, scratch
    return _Lap()


def _complete_turn(*, checkout: Path, scratch: Path) -> _Lap:
    """`implement` stated its Definition of Done complete."""
    del checkout, scratch
    return _Lap(stdin='{"definition_of_done_complete": true}\n')


def _passed_fix_commit(*, checkout: Path, scratch: Path) -> _Lap:
    """The fix turn's commit run passed: the node's success path, ending in its last exit."""
    plugins = scratch / "plugins"
    plugins.mkdir()
    runner = plugins / COMMIT_RUNNER_PROGRAM_FILENAME
    _ = runner.write_text(commit_runner_program_source(), encoding="utf-8")
    _ = _git(repo=checkout, argv=("config", "user.name", "Fixture"))
    _ = _git(repo=checkout, argv=("config", "user.email", "fixture@example.invalid"))
    _ = (checkout / "a.txt").write_text("base\n", encoding="utf-8")
    _ = _git(repo=checkout, argv=("add", "a.txt"))
    _ = _git(repo=checkout, argv=("commit", "--quiet", "-m", "base"))
    hook = checkout / ".git" / "hooks" / "pre-commit"
    _ = hook.write_text(_PASSING_HOOK, encoding="utf-8")
    hook.chmod(0o755)
    _ = (checkout / "b.txt").write_text("fix\n", encoding="utf-8")
    _ = _git(repo=checkout, argv=("add", "b.txt"))
    environment = {**_clean_environment(), "GIT_EDITOR": "true"}
    started = subprocess.run(
        (sys.executable, str(runner), "start", "--", "git", "commit", "-m", "fix"),
        cwd=checkout,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    waited = subprocess.run(
        (sys.executable, str(runner), "wait", started.stdout.strip(), "--timeout-seconds", "60"),
        cwd=checkout,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert json.loads(waited.stdout.splitlines()[-1])["state"] == "passed", waited.stdout
    return _Lap(environment={"LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(plugins)})


# The ordinary lap of each routing-schema node and the successor it must select.
_ORDINARY_LAPS: dict[tuple[str, str], tuple[Callable[..., _Lap], str]] = {
    (_IMPLEMENT, "implement_completion"): (_complete_turn, "implementation_diff"),
    (_IMPLEMENT, "fix_commit_settle"): (_passed_fix_commit, "fix_open_red_route"),
    (_IMPLEMENT, "fix_open_red_route"): (_no_setup, "janitor_admission"),
    (_IMPLEMENT, "publish_merged_reconcile_route"): (_no_setup, "proof_capture"),
    (_IMPLEMENT, "janitor_refresh_route"): (_no_setup, "janitor_failure_route"),
    (_IMPLEMENT, "pr_refresh_merged_reconcile_route"): (_no_setup, "pr_refresh_head"),
    (_IMPLEMENT, "pr_route"): (_no_setup, "verify_pr"),
    (_IMPLEMENT, "review_fix_open_red_route"): (_no_setup, "janitor_admission"),
}


def _directive_label(*, stdout: str, stderr: str) -> str:
    """The `preferred_next_label` of the last JSON object line the node printed."""
    objects: list[object] = [
        json.loads(line) for line in stdout.splitlines() if line.startswith("{")
    ]
    assert objects, f"no routing directive on stdout {stdout!r}; stderr {stderr!r}"
    payload = objects[-1]
    assert isinstance(payload, dict), payload
    label = cast("dict[str, object]", payload).get("preferred_next_label")
    assert isinstance(label, str), payload
    return label


def _destination(*, graph_path: str, source: str, preferred_label: str) -> str:
    """Resolve a preferred label: its conditional edge if one exists, else the fallthrough."""
    graph = parse_dot_graph(text=(_REPO_ROOT / graph_path).read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    outgoing = [edge for edge in graph.edges if edge.source == source]
    matching = [
        edge.destination
        for edge in outgoing
        if edge.attributes.get("condition") == f"preferred_label={preferred_label}"
    ]
    fallthrough = [edge.destination for edge in outgoing if "condition" not in edge.attributes]
    assert len(matching) <= 1
    assert len(fallthrough) == 1
    return matching[0] if matching else fallthrough[0]


def test_every_routing_schema_node_has_an_ordinary_lap() -> None:
    """A routing-schema node added without a lap here is a node nothing proves can route."""
    assert _routing_nodes() == set(_ORDINARY_LAPS)


@pytest.mark.parametrize(
    ("graph_path", "node"), sorted(_ORDINARY_LAPS), ids=lambda value: str(value).rsplit("/", 1)[-1]
)
def test_the_ordinary_lap_exits_zero_with_a_routing_directive(
    *, tmp_path: Path, graph_path: str, node: str
) -> None:
    """Exit 0 and a directive whose label selects the node's ordinary successor."""
    setup, successor = _ORDINARY_LAPS[(graph_path, node)]
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    _ = _git(repo=checkout, argv=("init", "--quiet", "-b", "master"))
    lap = setup(checkout=checkout, scratch=tmp_path)
    graph = parse_dot_graph(text=(_REPO_ROOT / graph_path).read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    script = _DEFAULT_BRANCH_TEMPLATE.sub("master", graph.nodes[node]["script"])

    result = subprocess.run(
        ("sh", "-c", script),
        cwd=checkout,
        check=False,
        capture_output=True,
        text=True,
        input=lap.stdin,
        env={**_clean_environment(), **lap.environment},
    )

    assert result.returncode == 0, result.stderr
    label = _directive_label(stdout=result.stdout, stderr=result.stderr)
    assert (
        _destination(graph_path=graph_path, source=node, preferred_label=label) == successor
    ), label
