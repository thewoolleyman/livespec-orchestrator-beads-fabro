"""A stage script the payload cannot split refuses the dispatch before any run exists.

The split happens inside the payload materializer, so a script naming a template
input with no seam into a helper file would otherwise ship a token no shell
expands. The refusal names the node and the input, and nothing is materialized.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_payload import (
    WorkflowPayload,
    materialize_workflow_payload,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import default_node_timeouts

_OPEN = "{" + "{"
_CLOSE = "}" + "}"
_CONFIG = '_version = 1\n\n[workflow]\ngraph = "workflow.fabro"\n\n[run.environment]\nid = "ci"\n'


def _graph(*, script: str) -> str:
    return "".join(
        [
            'digraph G {\n    graph [\n        stall_timeout="7200s"\n    ]\n\n',
            '    pr [\n        label="x"\n        timeout="600s"\n',
            f'        script="{script}"\n    ]\n}}\n',
        ]
    )


def _materialize(*, root: Path, script: str) -> WorkflowPayload | str:
    workflow_dir = root / "workflow"
    workflow_dir.mkdir()
    _ = (workflow_dir / "workflow.toml").write_text(_CONFIG, encoding="utf-8")
    _ = (workflow_dir / "workflow.fabro").write_text(_graph(script=script), encoding="utf-8")
    return materialize_workflow_payload(
        committed=workflow_dir / "workflow.toml",
        payload_dir=root / "payload",
        timeouts=default_node_timeouts(),
        adapters={},
    )


def test_a_stage_script_with_an_unseamed_input_is_refused(tmp_path: Path) -> None:
    refusal = _materialize(root=tmp_path, script=f"echo {_OPEN} inputs.surprise {_CLOSE}")
    assert isinstance(refusal, str)
    assert "pr" in refusal
    assert "surprise" in refusal
    assert not (tmp_path / "payload").exists()


def test_a_splittable_stage_script_is_materialized_as_an_invocation(tmp_path: Path) -> None:
    payload = _materialize(root=tmp_path, script=f"echo {_OPEN} inputs.default_branch {_CLOSE}")
    assert isinstance(payload, WorkflowPayload), payload
    dispatched = payload.graph.read_text(encoding="utf-8")
    assert "livespec-stage-pr.sh" in dispatched
    assert "echo" not in dispatched
