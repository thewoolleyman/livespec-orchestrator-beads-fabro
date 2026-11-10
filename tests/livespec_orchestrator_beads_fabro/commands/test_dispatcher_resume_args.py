"""The resume argument clone carries the published run's launch identity.

The resume command needs an ordinary ``argparse.Namespace`` with three values
changed for its eventual dispatch: the node to enter, the published head, and
the workflow. This small seam owns that construction so the command retains the
launch sequence while the clone's two workflow-precedence cases stay directly
observable.
"""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import ResumeAnchor
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation import ResumeGather

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_args"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_resume_args.py"
)


def _module() -> ModuleType:
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


@pytest.mark.parametrize(
    ("recorded_workflow", "requested_workflow", "expected_workflow"),
    [
        ("published-workflow", "requested-workflow", "published-workflow"),
        (None, "requested-workflow", "requested-workflow"),
    ],
)
def test_resumed_args_carry_the_anchor_and_prefer_the_recorded_workflow(
    recorded_workflow: str | None, requested_workflow: str, expected_workflow: str
) -> None:
    """The published workflow wins; absent history preserves the request."""
    module = _module()
    original = argparse.Namespace(workflow_name=requested_workflow, untouched="value")
    gather = cast(
        ResumeGather,
        SimpleNamespace(
            workflow_name=recorded_workflow,
            observation=SimpleNamespace(proof_only_resume=False),
        ),
    )
    anchor = cast(ResumeAnchor, SimpleNamespace(resumed_at="review", head="a" * 40))

    resumed = module.resumed_args(args=original, gather=gather, anchor=anchor)

    assert resumed is not original
    assert resumed.resume_entry_node == "review"
    assert resumed.resume_head == "a" * 40
    assert resumed.resume_proof_only is False
    assert resumed.workflow_name == expected_workflow
    assert resumed.untouched == "value"
