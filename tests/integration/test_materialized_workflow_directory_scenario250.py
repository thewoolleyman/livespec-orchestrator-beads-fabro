"""Scenario 250 — dotted work-item ids retain a resolvable workflow package."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import (
    NODE_INPUT_CANDIDATES,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_plan import (
    workflow_payload_dir,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_payload import (
    WorkflowPayload,
    materialize_workflow_payload,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    default_node_timeouts,
)

_WORKFLOW = Path(".claude-plugin/.fabro/workflows/implement-work-item/workflow.toml")
_DOTTED_ID = "bd-ib-abc123.2"
_HYPHENATED_ID = "bd-ib-abc123-2"
_UNREACHABLE_SERVER = "http://127.0.0.1:9"
_ADAPTERS = {
    candidates[0]: "npx -y claude-agent-acp" for candidates in NODE_INPUT_CANDIDATES.values()
}


def _real_fabro() -> str:
    """The CI-installed engine, never pytest's dispatch hermetic stub."""
    binary = shutil.which("fabro")
    if binary is None:
        pytest.skip("the Fabro binary is absent in this sandbox")
    return binary


def _materialized_dotted_package(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Materialize the package that both engine-resolution probes inspect."""
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop_plan.tempfile.gettempdir",
        lambda: str(tmp_path),
    )
    dotted_dir = workflow_payload_dir(work_item_id=_DOTTED_ID)
    hyphenated_dir = workflow_payload_dir(work_item_id=_HYPHENATED_ID)
    payload = materialize_workflow_payload(
        committed=_WORKFLOW,
        payload_dir=dotted_dir,
        timeouts=default_node_timeouts(),
        adapters=_ADAPTERS,
    )
    assert isinstance(payload, WorkflowPayload)
    assert "." not in dotted_dir.name
    assert dotted_dir != hyphenated_dir
    return dotted_dir


def _assert_engine_resolution(*, fabro: str, payload_dir: Path, tmp_path: Path) -> None:
    """Validate and launch a package far enough to prove local resolution."""
    validated = subprocess.run(
        [fabro, "validate", str(payload_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert validated.returncode == 0, validated.stderr

    goal_file = tmp_path / "goal.md"
    _ = goal_file.write_text("Scenario 250 engine-resolution probe\n", encoding="utf-8")
    launched = subprocess.run(
        [
            fabro,
            "run",
            str(payload_dir),
            "--goal-file",
            str(goal_file),
            "--no-upgrade-check",
            "--server",
            _UNREACHABLE_SERVER,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    output = f"{launched.stdout}\n{launched.stderr}".casefold()
    assert "workflow not found" not in output
    assert "connect" in output or "connection" in output


def test_dotted_work_item_materializes_a_dot_free_engine_resolvable_package(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A CI-installed Fabro resolves the package before any server contact."""
    payload_dir = _materialized_dotted_package(monkeypatch=monkeypatch, tmp_path=tmp_path)
    _assert_engine_resolution(fabro=_real_fabro(), payload_dir=payload_dir, tmp_path=tmp_path)
