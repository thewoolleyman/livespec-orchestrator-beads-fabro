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

WHY THE RECORD FILE'S SHAPE IS ON THE PAGE. The `--record` flag names a file the caller
has to AUTHOR, and nothing else on this surface describes it. Its own `help=` says what
the file carries, which is a true summary and not a shape: the first session to publish
a host record here read `_dispatcher_host_record_payload` to learn the keys, because the
reader is where the key names actually live. A publisher who guesses a key instead gets
no error for it — the reader takes `steps`, `proof` and `reproduced` with defaults, so a
misspelling publishes a record with no steps and an empty proof rather than a refusal.
The skeleton therefore belongs on the surface the publisher is already reading.

It rides the EPILOG rather than `--record`'s own `help=`, because argparse re-flows an
option's help to the terminal width, and a re-flowed JSON object is a paragraph. The
epilog is raw only under `RawDescriptionHelpFormatter`, which is why this function sets
both: the subparser is this surface's, and its formatter is part of the surface.
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
    "RECORD_FILE_SHAPE",
    "add_post_host_record_arguments",
    "reconcile_for",
    "reconcile_merged_for_item",
    "run_post_host_record_cli",
]

# The `--record` file's own shape, written as the file itself so it can be copied. Every
# value is a placeholder describing what belongs there, which is what makes the skeleton
# readable as an instruction rather than as one publisher's record; `reproduced` is the
# exception, because a boolean has no placeholder form.
RECORD_FILE_SHAPE = """\
{
  "build": {
    "release_tag": "<the release tag whose build the steps exercised>",
    "installed_build": "<the installed plugin build identifier>",
    "commit": "<the default-branch commit exercised, where no release applies>"
  },
  "assertions": [
    {
      "text": "<one assertion, verbatim, from the item's Definition of Done>",
      "governing_scenario": "<the scenario that governs it; omit the key when none does>",
      "steps": ["<the first step run>", "<the second step run>"],
      "proof": "<the text those steps printed>",
      "reproduced": true
    }
  ]
}"""

_RECORD_FILE_EPILOG = f"""\
The --record file is a JSON object of this shape:

{RECORD_FILE_SHAPE}
"""


def add_post_host_record_arguments(*, parser: argparse.ArgumentParser) -> None:
    """Attach the posting primitive's governed surface to its subparser.

    There is deliberately NO `--identity`, `--session`, `--timestamp` or
    `--pull-request` flag. Each of those is a thing the clause requires the primitive to
    COMPUTE, and a flag for one would be the route by which a session hand-formats the
    record the primitive exists to render.

    The epilog and the formatter are set here, on the parser this surface was handed,
    for the reason the module docstring records: the record file's shape is part of this
    subcommand's surface, and it only survives onto the page unwrapped.
    """
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    parser.epilog = _RECORD_FILE_EPILOG
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
