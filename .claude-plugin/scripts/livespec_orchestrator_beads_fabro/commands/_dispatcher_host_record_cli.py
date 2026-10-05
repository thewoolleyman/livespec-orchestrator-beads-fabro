"""The posting primitive's command-line surface, and the production seams it binds.

Split out of `_dispatcher_host_record_post` along the usual boundary: that module is the
primitive, expressed over four injected seams, and this one is the ONE place those seams
are bound to real ones — the shell runner, the process environment, stdout, and the
`reconcile-merged` valve.

WHAT IS NOT ON THIS SURFACE, and why its absence is the design. There is no
`--identity`, no `--session`, no `--timestamp` and no `--pull-request` flag. Each names
something the host-leg clause of `SPECIFICATION/contracts.md` requires the primitive to
COMPUTE, and a flag for any of them would be the route by which a session hand-formats
the record this primitive exists to render. The identity flag would be the worst: it
would reduce the independence refusal — the whole of the "independent party" guarantee —
to a naming convention.

WHY THE VERDICT IS A CLOSED CHOICE. `argparse` refuses anything outside the three
host-leg words before the primitive runs. The control that matters is `verified`: it is a
real Proof-of-Done verdict word, just not a host-leg one, so a primitive accepting any
string would cheerfully publish a record the acceptance pass reads as the merging run's
FACTORY evidence.

WHY THE RECONCILE GOES THROUGH THE ORDINARY VALVE. The clause says the primitive drives
`reconcile-merged --item <id>`, and that "`reconcile-merged` driven by hand is the same
route". That is only true if there is one route, so this binds the valve's own command
function rather than re-implementing its arm selection.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_host_leg import REPLAY_VERDICTS
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_post import (
    HostRecordPost,
    run_post_host_record_command,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import add_invoker_argument
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_HOST_RECORDED,
)
from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = [
    "add_post_host_record_arguments",
    "reconcile_for",
    "reconcile_merged_for_item",
    "run_post_host_record_cli",
]

# The `--record` file's own shape, written out as the epilog rather than compressed into
# the flag's `help`. The flag used to describe the file only by what its fields CONTAIN —
# "the build identity exercised and, per assertion, the numbered steps, the proof and
# whether they reproduced" — which names no KEY, so the first session to publish a host
# record here read `_dispatcher_host_record_payload` to learn them. A reader asking a
# command what to feed it should not have to open the parser that feeds it.
#
# The two fields that are not read the way they look carry a sentence each. `text` is a
# LOOKUP KEY into the item's Definition of Done — `read_evidence` takes the proof mode
# from the item and refuses an assertion the item does not declare — and `reproduced` is
# read only for a replay, because a capture is the first leg and has nothing yet to have
# reproduced. A publisher knowing only the key names writes both in good faith and is
# refused by the first, silently ignored by the second.
#
# It is an EPILOG because argparse re-wraps a `help` string to the terminal width, which
# would reflow the object literal into prose and destroy the one thing it is here to show.
# `RawDescriptionHelpFormatter` is set alongside it for that reason.
_RECORD_FILE_SHAPE = """the --record file is a JSON object of this shape:

  {
    "build": {
      "release_tag": "v0.167.1",
      "installed_build": "the plugin build identifier installed on the host",
      "commit": "the default-branch commit exercised, where no release applies"
    },
    "assertions": [
      {
        "text": "the assertion, verbatim from the item's Definition of Done",
        "governing_scenario": "the scenario that governs it, where one does",
        "steps": ["the first step that was run", "the second step that was run"],
        "proof": "the output those steps produced",
        "reproduced": true
      }
    ]
  }

An assertion's "text" has to match one the item's Definition of Done declares, and
is a LOOKUP KEY rather than free prose: the proof mode is read from the item, never
from this file, so an assertion the item does not declare is refused rather than
published under a guessed mode. "reproduced" is read only for a replay verdict
(host_verified or host_not_reproduced) — a host_recorded capture is the first leg,
with nothing yet to have reproduced, so a reproduction verdict in a capture's
payload is dropped instead of published.
"""


def add_post_host_record_arguments(*, parser: argparse.ArgumentParser) -> None:
    """Attach the posting primitive's governed surface to its subparser.

    There is deliberately NO `--identity`, `--session`, `--timestamp` or
    `--pull-request` flag. Each of those is a thing the clause requires the primitive to
    COMPUTE, and a flag for one would be the route by which a session hand-formats the
    record the primitive exists to render.

    The record file's shape rides the EPILOG, which is why the formatter is swapped here
    rather than at the `add_parser` call: the shape and the formatter that preserves it
    are one decision, and separating them would let a later subparser edit reflow the
    object literal into prose with nothing failing.
    """
    parser.epilog = _RECORD_FILE_SHAPE
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    _ = parser.add_argument("--repo", dest="repo", required=True)
    _ = parser.add_argument("--item", dest="item", required=True)
    _ = parser.add_argument(
        "--verdict",
        dest="verdict",
        required=True,
        choices=[VERDICT_HOST_RECORDED, *REPLAY_VERDICTS],
        help="the host-leg verdict to publish; a replay drives reconcile-merged",
    )
    _ = parser.add_argument(
        "--record",
        dest="record",
        required=True,
        help=(
            "path to a JSON object carrying the build identity exercised and, per "
            "assertion, the numbered steps, the proof and whether they reproduced"
        ),
    )
    _ = parser.add_argument("--journal", dest="journal", default=None)
    add_invoker_argument(parser=parser)


def run_post_host_record_cli(*, args: argparse.Namespace) -> int:
    """The CLI adapter: build the real seams and run the primitive.

    The reconcile it drives is the ORDINARY `reconcile-merged` entry point, invoked
    through its own command function rather than re-implemented — the clause says the
    primitive drives that valve, and "driven by hand is the same route", so there is one
    acceptance re-run path and not two that could diverge.
    """
    repo = Path(args.repo)
    return run_post_host_record_command(
        post=HostRecordPost(
            repo=repo,
            work_item_id=args.item,
            verdict=args.verdict,
            record_path=Path(args.record),
        ),
        runner=ShellCommandRunner(),
        env=os.environ,
        # A lambda rather than a named helper: the seam is POSITIONAL by construction —
        # the primitive calls it as `emit(body)`, and the test doubles are
        # `list.append` — so a `def` here could not carry the keyword-only separator
        # this tree requires of one.
        emit=lambda text: write_stdout(text=text),
        reconcile=reconcile_for(repo=repo, args=args),
    )


def reconcile_for(*, repo: Path, args: argparse.Namespace) -> Callable[..., int]:
    """The reconcile the post drives, bound to this invocation's repository.

    A named closure rather than a lambda because the annotation matters: a lambda's
    parameter type is unknowable to the type checker, and this tree runs strict.
    """

    def drive(*, work_item_id: str) -> int:
        return reconcile_merged_for_item(
            args=argparse.Namespace(
                repo=str(repo),
                item=work_item_id,
                janitor=None,
                journal=args.journal,
                invoker=getattr(args, "invoker", None),
                force=False,
                regrade=False,
                as_json=False,
            )
        )

    return drive


def reconcile_merged_for_item(*, args: argparse.Namespace) -> int:
    """Drive the reconcile valve, imported here for the cycle reason recorded above."""
    from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_merged import (
        run_reconcile_merged_command,
    )

    return run_reconcile_merged_command(args=args)
