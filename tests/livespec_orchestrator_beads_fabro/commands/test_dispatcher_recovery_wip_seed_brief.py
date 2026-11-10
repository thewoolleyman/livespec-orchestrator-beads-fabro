"""A dispatch seeded from a work-in-progress ref is told that ref is the tree to start from.

The seed a work-in-progress capture yields rides the same `seeded` route as every
other preserved tree, so the goal brief's account of the placement is only right
if the route carries the CAPTURE'S ref as the fetch ref. The case runs the real
launch-argument step and the real brief section end to end, with the capture's
ref deliberately different from every other ref a seed could name.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_goal_recovery import (
    interrupted_attempt_for,
    interrupted_attempt_section,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_launch import (
    LaunchPins,
    recovery_launch_args,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_SEEDED,
    RecoveryRoute,
    RecoverySeed,
)

_ITEM = "bd-ib-wipbrf"
_WIP_REF = f"refs/livespec/wip/{_ITEM}/01LATESTRUN00000000000000B/10"
_WIP_COMMIT = "b0" * 20


def _factory_pin(
    *, args: argparse.Namespace, repo: Path, work_item_id: str, resume: bool
) -> argparse.Namespace:
    _ = (repo, work_item_id, resume)
    return args


def _workflow_pin(*, args: argparse.Namespace, repo: Path, work_item_id: str) -> argparse.Namespace:
    _ = (repo, work_item_id)
    return args


def test_the_brief_names_the_work_in_progress_ref_as_the_tree_to_start_from() -> None:
    route = RecoveryRoute(
        work_item_id=_ITEM,
        route=ROUTE_SEEDED,
        seed=RecoverySeed(
            source_run_id="01LATESTRUN00000000000000B",
            remote="origin",
            commit_sha=_WIP_COMMIT,
            preservation_ref=_WIP_REF,
        ),
    )
    launched = recovery_launch_args(
        args=argparse.Namespace(),
        repo=Path("/repo"),
        work_item_id=_ITEM,
        route=route,
        pins=LaunchPins(factory=_factory_pin, workflow=_workflow_pin),
    )
    attempt = interrupted_attempt_for(args=launched)
    assert attempt is not None
    assert attempt.fetch_ref == _WIP_REF
    section = interrupted_attempt_section(attempt=attempt)
    assert _WIP_REF in section
    assert _WIP_COMMIT in section
