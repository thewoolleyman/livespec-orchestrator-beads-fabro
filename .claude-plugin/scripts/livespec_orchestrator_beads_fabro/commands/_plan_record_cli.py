"""The plan posting primitive's command-line surface, and the seams it binds.

Split out of `_plan_record_post` along the usual boundary: that module is the
primitive, expressed over three injected seams, and this one is the ONE place
those seams are bound to real ones — the shell runner, the process environment,
and stdout.

WHAT IS NOT ON THIS SURFACE, and why its absence is the design. There is no
`--identity`, no `--session`, no `--timestamp` and no `--mode` flag. Each names
something the plan-record clause requires the primitive to COMPUTE, and a flag
for any of them would be the route by which a session hand-formats the record
this primitive exists to render. The identity flag would be the worst: it would
reduce the independence refusal — the whole of the "party with no role in the
plan's implementation" guarantee — to a naming convention.

WHY THE VERDICT IS A CLOSED CHOICE. `argparse` refuses anything outside the four
plan-record words before the primitive runs. The control that matters is
`host_verified`: it is a real Proof-of-Done verdict word, just not a PLAN one, so
a primitive accepting any string would publish a record whose first line no plan
reader accepts — a record that is permanent, invisible to the archive gate, and
indistinguishable from a successful post from the publisher's side.

WHY THE TARGET IS AN EPIC AND THERE IS NO `--pull-request`. A plan record is an
append-only comment on the plan epic. The epic id is the whole of the target, and
the flag is `--epic` rather than `--item` so an operator who has just used
`post-host-record --item` is told, by the flag itself, that this is the other
surface.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import add_invoker_argument
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._plan_proof_record import (
    PLAN_PROOF_RECORD_VERDICTS,
)
from livespec_orchestrator_beads_fabro.commands._plan_record_post import (
    PlanRecordPost,
    run_post_plan_record_command,
)
from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = [
    "add_post_plan_record_arguments",
    "run_post_plan_record_cli",
]


def add_post_plan_record_arguments(*, parser: argparse.ArgumentParser) -> None:
    """Attach the plan posting primitive's governed surface to its subparser.

    There is deliberately NO `--identity`, `--session`, `--timestamp` or `--mode`
    flag. Each of those is a thing the clause requires the primitive to COMPUTE,
    and a flag for one would be the route by which a session hand-formats the
    record the primitive exists to render.
    """
    _ = parser.add_argument("--repo", dest="repo", required=True)
    _ = parser.add_argument("--epic", dest="epic", required=True)
    _ = parser.add_argument(
        "--verdict",
        dest="verdict",
        required=True,
        choices=list(PLAN_PROOF_RECORD_VERDICTS),
        help="the plan-record verdict to publish; a replay owns an earlier capture",
    )
    _ = parser.add_argument(
        "--record",
        dest="record",
        required=True,
        help=(
            "path to a JSON object carrying the build identity exercised and, per "
            "plan assertion, the numbered steps, the proof and whether they reproduced"
        ),
    )
    add_invoker_argument(parser=parser)


def run_post_plan_record_cli(*, args: argparse.Namespace) -> int:
    """The CLI adapter: build the real seams and run the primitive."""
    repo = Path(args.repo)
    return run_post_plan_record_command(
        post=PlanRecordPost(
            repo=repo,
            epic_id=args.epic,
            verdict=args.verdict,
            record_path=Path(args.record),
        ),
        config=resolve_store_config(cwd=repo, work_items_arg=None),
        runner=ShellCommandRunner(),
        env=os.environ,
        # A lambda rather than a named helper: the seam is POSITIONAL by
        # construction — the primitive calls it as `emit(body)`, and the test
        # doubles are `list.append` — so a `def` here could not carry the
        # keyword-only separator this tree requires of one.
        emit=lambda text: write_stdout(text=text),
    )
