"""The dispatch arguments a resume derives from its published anchor.

The resume command owns the order of its pre-launch work.  This module owns the
small value transformation that turns the operator's namespace into the
namespace for the resumed run: it carries the published entry node and head,
while the workflow recorded by the earlier dispatch takes precedence over the
operator's requested fallback.
"""

from __future__ import annotations

import argparse

from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import ResumeAnchor
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry import (
    RESUME_ENTRY_NODE_ARG,
    RESUME_HEAD_ARG,
    RESUME_PROOF_ONLY_ARG,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation import ResumeGather

__all__: list[str] = [
    "resumed_args",
]


def resumed_args(
    *, args: argparse.Namespace, gather: ResumeGather, anchor: ResumeAnchor
) -> argparse.Namespace:
    """Clone arguments with the published entry, head, and workflow identity."""
    cloned = argparse.Namespace(**vars(args))
    setattr(cloned, RESUME_ENTRY_NODE_ARG, anchor.resumed_at)
    setattr(cloned, RESUME_HEAD_ARG, anchor.head)
    setattr(cloned, RESUME_PROOF_ONLY_ARG, gather.observation.proof_only_resume is True)
    cloned.workflow_name = gather.workflow_name or getattr(args, "workflow_name", None)
    return cloned
