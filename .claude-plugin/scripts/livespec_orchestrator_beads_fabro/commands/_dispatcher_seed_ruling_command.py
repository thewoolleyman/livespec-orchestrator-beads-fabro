"""`dispatcher.py seed-ruling` — record an operator's ruled seed for an item's next dispatch.

Scenario 185 lets an operator name the preserved tree a released item's next
dispatch starts from. This command is the writer of that instruction. It takes
ONE remote read of origin and writes only when the named ref stands at the
named commit: one ledger comment opening with the `livespec-seed-ruling`
marker, and one `seed-ruling` journal record carrying the same facts. A ref
that is absent or at another commit, or a body the shared template-opener
detector flags, is refused with exit 3 BEFORE either write, because a ledger
comment is append-only and cannot be repaired afterwards.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from livespec_orchestrator_beads_fabro._beads_client import BeadsClient, make_beads_client
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import (
    add_invoker_argument,
    invoker_from_args,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
    utc_now_iso,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import journal_path
from livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling import (
    SeedRuling,
    record_verified_seed_ruling,
    verify_seed_ruling,
)
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout

__all__: list[str] = [
    "add_seed_ruling_arguments",
    "run_seed_ruling_cli",
    "run_seed_ruling_command",
]


def add_seed_ruling_arguments(*, parser: argparse.ArgumentParser) -> None:
    """Attach the seed-ruling flag surface to its subparser."""
    add_invoker_argument(parser=parser)
    _ = parser.add_argument("--repo", dest="repo", default=None)
    _ = parser.add_argument("--item", dest="item", required=True)
    _ = parser.add_argument(
        "--ref",
        dest="ref",
        required=True,
        help="the full ref on origin that preserves the ruled tree",
    )
    _ = parser.add_argument(
        "--commit",
        dest="commit",
        required=True,
        help="the commit SHA the ref must stand at on origin",
    )
    _ = parser.add_argument(
        "--reason",
        dest="reason",
        required=True,
        help="why the operator rules this tree as the item's next seed",
    )
    _ = parser.add_argument("--journal", dest="journal", default=None)


def run_seed_ruling_cli(*, args: argparse.Namespace) -> int:
    """The CLI adapter: bind the real ledger and shell runner, then run the command."""
    repo = Path(args.repo) if args.repo is not None else Path.cwd()
    return run_seed_ruling_command(
        args=args,
        runner=ShellCommandRunner(),
        ledger=make_beads_client(config=resolve_store_config(cwd=repo, work_items_arg=None)),
    )


def run_seed_ruling_command(
    *, args: argparse.Namespace, runner: CommandRunner, ledger: BeadsClient
) -> int:
    """Record one ruling, refusing with exit 3 before any write whenever it must."""
    repo = Path(args.repo) if args.repo is not None else Path.cwd()
    if not ledger.exists(issue_id=args.item):
        _ = write_stderr(text=f"ERROR: seed-ruling refused: no work-item {args.item}.\n")
        return EXIT_PRECONDITION_ERROR
    identity = invoker_from_args(args=args)
    ruling = SeedRuling(
        work_item_id=args.item,
        preservation_ref=args.ref,
        commit_sha=args.commit,
        invoker=identity.invoker,
        reason=args.reason,
        instant=utc_now_iso(),
    )
    verified = verify_seed_ruling(runner=runner, repo=repo, ruling=ruling)
    journal = JournalFile(path=journal_path(args=args, repo=repo), identity=identity)
    refusal = (
        verified
        if verified != ruling.commit_sha
        else record_verified_seed_ruling(
            ruling=ruling,
            verified_commit=verified,
            append_comment=lambda body: ledger.add_comment(issue_id=args.item, body=body),
            append_journal=lambda record: journal.append(record=record),
        )
    )
    if refusal is not None:
        _ = write_stderr(text=f"ERROR: seed-ruling refused: {refusal}\n")
        return EXIT_PRECONDITION_ERROR
    _ = write_stdout(
        text=(
            f"RULED  {args.item}  {ruling.preservation_ref} at {ruling.commit_sha}  "
            f"by {ruling.invoker}: {ruling.reason}\n"
        )
    )
    return 0
