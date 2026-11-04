"""Scenario 204 — repair turns retain detached commit-runner settlement.

Red and Green now commit through dedicated command nodes.  The existing
detached-runner protocol remains only on the `fix` and `review_fix` repair
turns, so this module pins that intentionally narrower surface.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_program import (
    COMMIT_RUNNER_PROGRAM_FILENAME,
    commit_runner_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GRAPH = _REPO_ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
_FIX_SETTLE = "fix_commit_settle"
_REVIEW_FIX_SETTLE = "review_fix_commit_settle"
_JANITOR_ADMISSION = "janitor_admission"
_FIX_LIVE_GIT_PATH = "livespec-fix-live-commit"
_REVIEW_FIX_LIVE_GIT_PATH = "livespec-review-fix-live-commit"
_STAGE_CAUSE_GIT_PATH = "livespec-stage-cause"
_JANITOR_VISIT_CAP = 8


def _targets(*, source: str) -> list[tuple[str, str]]:
    parsed = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(parsed, str), parsed
    return [
        (edge.destination, edge.attributes.get("condition", ""))
        for edge in parsed.edges
        if edge.source == source
    ]


def _attributes(*, node: str) -> dict[str, str]:
    parsed = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(parsed, str), parsed
    return dict(parsed.nodes.get(node, {}))


def _clone(tmp_path: Path) -> Path:
    repo = tmp_path / "clone"
    repo.mkdir(parents=True)
    _ = subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
    return repo


def _plugins(tmp_path: Path) -> Path:
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    _ = (plugins / COMMIT_RUNNER_PROGRAM_FILENAME).write_text(
        commit_runner_program_source(), encoding="utf-8"
    )
    return plugins


def _run_node(*, repo: Path, node: str, plugins: Path) -> subprocess.CompletedProcess[str]:
    script = _attributes(node=node).get("script", "exit 2")
    env = dict(os.environ)
    env["LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT"] = str(plugins)
    return subprocess.run(
        ["sh", "-c", script], cwd=repo, check=False, capture_output=True, text=True, env=env
    )


def test_repair_turns_reach_their_settle_nodes_before_janitor() -> None:
    """Both repair paths wait for their own commits before a new janitor visit."""
    assert _targets(source="fix") == [
        ("needs_human", "outcome=failed"),
        (_FIX_SETTLE, ""),
    ]
    assert _targets(source="review_fix") == [
        ("needs_human", "outcome=failed"),
        ("recapture_route", "preferred_label=recapture"),
        (_REVIEW_FIX_SETTLE, ""),
    ]
    assert _targets(source=_FIX_SETTLE) == [(_JANITOR_ADMISSION, "")]
    assert _targets(source=_REVIEW_FIX_SETTLE) == [(_JANITOR_ADMISSION, "")]


def test_repair_settle_nodes_remain_bounded_commit_runner_commands() -> None:
    """Only repair nodes retain the detached runner and their own live brief."""
    for node, brief in (
        (_FIX_SETTLE, _FIX_LIVE_GIT_PATH),
        (_REVIEW_FIX_SETTLE, _REVIEW_FIX_LIVE_GIT_PATH),
    ):
        attributes = _attributes(node=node)
        script = attributes.get("script", "")
        assert attributes.get("shape") == "parallelogram", node
        assert "livespec-commit-runner.py" in script, node
        assert f"git rev-parse --git-path {brief}" in script, node
        bound = re.search(r"settle --timeout-seconds (\d+)", script)
        assert bound is not None, node
        assert 0 < int(bound.group(1)) < int(attributes.get("timeout", "0s").rstrip("s"))


def test_repair_settle_nodes_accept_an_idle_runner_state(tmp_path: Path) -> None:
    """No stale implement-stage state is required to let a repair settle pass."""
    repo = _clone(tmp_path)
    plugins = _plugins(tmp_path)
    for node in (_FIX_SETTLE, _REVIEW_FIX_SETTLE):
        result = _run_node(repo=repo, node=node, plugins=plugins)
        assert result.returncode == 0, result.stderr


def test_janitor_admission_remains_the_shared_reentry_gate(tmp_path: Path) -> None:
    """The ninth entry preserves the tree instead of reusing a stale janitor result."""
    repo = _clone(tmp_path)
    plugins = _plugins(tmp_path)
    for _ in range(_JANITOR_VISIT_CAP):
        admitted = _run_node(repo=repo, node=_JANITOR_ADMISSION, plugins=plugins)
        assert admitted.returncode == 0, admitted.stderr
    refused = _run_node(repo=repo, node=_JANITOR_ADMISSION, plugins=plugins)
    assert refused.returncode != 0
    cause = (repo / ".git" / _STAGE_CAUSE_GIT_PATH).read_text(encoding="utf-8")
    assert "stage: janitor_admission" in cause
    assert "LIVESPEC_JANITOR_VISIT_BOUND_EXHAUSTED" in cause
    assert str(_JANITOR_VISIT_CAP) in cause
