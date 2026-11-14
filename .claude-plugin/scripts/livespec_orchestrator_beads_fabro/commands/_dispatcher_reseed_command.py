"""`dispatcher.py reseed` — move a stale preserved seed onto the default branch's tip.

A seeded relaunch whose recorded seed is far behind the default branch used to need a
hand-built seed, because a refresh rebase produces the commit shape the commit runner's
authored-subject guard refuses. This command is the sanctioned route: it diff-applies the
seed's work onto the current tip as ONE authored commit (`_dispatcher_diff_apply_reseed`),
publishes it under `refs/livespec/reseed/<item>/<commit>`, confirms that ref by a remote
read, and then records the reseed ref as the item's ruled seed, so the item's next dispatch
is routed `seeded` from it and its seed record names the ref and the reseed commit's full
id (`_dispatcher_seed_ruling`, Scenario 185).

Every refusal exits 3 BEFORE the ledger is written: a seed that carries no work, a diff
that conflicts (every conflicting path named), and any read or publication that failed.
A refusal never touches the item, so a blocked item stays blocked for its owner.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from livespec_orchestrator_beads_fabro._beads_client import BeadsClient, make_beads_client
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_default_branch import (
    resolve_default_branch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_diff_apply_reseed import (
    ReseedRefusal,
    diff_apply_reseed,
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
)
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout

__all__: list[str] = [
    "add_reseed_arguments",
    "run_reseed_cli",
    "run_reseed_command",
]


def add_reseed_arguments(*, parser: argparse.ArgumentParser) -> None:
    """Attach the reseed flag surface to its subparser."""
    add_invoker_argument(parser=parser)
    _ = parser.add_argument("--repo", dest="repo", default=None)
    _ = parser.add_argument("--item", dest="item", required=True)
    _ = parser.add_argument(
        "--seed-ref",
        dest="seed_ref",
        required=True,
        help="the full ref on origin that preserves the stale seed",
    )
    _ = parser.add_argument(
        "--default-branch",
        dest="default_branch",
        default=None,
        help="the branch to re-seed onto (default: the repository's resolved default branch)",
    )
    _ = parser.add_argument(
        "--reason",
        dest="reason",
        default=None,
        help="why the seed is re-seeded (default: names the seed ref and the tip)",
    )
    _ = parser.add_argument("--journal", dest="journal", default=None)


def run_reseed_cli(*, args: argparse.Namespace) -> int:
    """The CLI adapter: bind the real ledger and shell runner, then run the command."""
    repo = Path(args.repo) if args.repo is not None else Path.cwd()
    return run_reseed_command(
        args=args,
        runner=ShellCommandRunner(),
        ledger=make_beads_client(config=resolve_store_config(cwd=repo, work_items_arg=None)),
    )


def run_reseed_command(
    *, args: argparse.Namespace, runner: CommandRunner, ledger: BeadsClient
) -> int:
    """Reseed one item's stale seed and rule the reseed ref as its next seed."""
    repo = Path(args.repo) if args.repo is not None else Path.cwd()
    if not ledger.exists(issue_id=args.item):
        _ = write_stderr(text=f"ERROR: reseed refused: no work-item {args.item}.\n")
        return EXIT_PRECONDITION_ERROR
    branch = args.default_branch or resolve_default_branch(repo=repo, runner=runner)
    if branch is None:
        _ = write_stderr(text="ERROR: reseed refused: the default branch could not be resolved.\n")
        return EXIT_PRECONDITION_ERROR
    reseeded = diff_apply_reseed(
        runner=runner,
        repo=repo,
        work_item_id=args.item,
        seed_ref=args.seed_ref,
        default_branch=branch,
    )
    if isinstance(reseeded, ReseedRefusal):
        _ = write_stderr(text=f"ERROR: reseed refused: {reseeded.detail}\n")
        return EXIT_PRECONDITION_ERROR
    identity = invoker_from_args(args=args)
    ruling = SeedRuling(
        work_item_id=args.item,
        preservation_ref=reseeded.ref,
        commit_sha=reseeded.commit,
        invoker=identity.invoker,
        reason=args.reason
        or (
            f"diff-apply reseed of {reseeded.source_ref} at {reseeded.source_commit} "
            f"onto {branch} at {reseeded.tip_commit}"
        ),
        instant=utc_now_iso(),
    )
    journal = JournalFile(path=journal_path(args=args, repo=repo), identity=identity)
    refusal = record_verified_seed_ruling(
        ruling=ruling,
        verified_commit=reseeded.commit,
        append_comment=lambda body: ledger.add_comment(issue_id=args.item, body=body),
        append_journal=lambda record: journal.append(record=record),
    )
    if refusal is not None:
        _ = write_stderr(
            text=f"ERROR: reseed published {reseeded.ref} but could not rule it: {refusal}\n"
        )
        return EXIT_PRECONDITION_ERROR
    _ = write_stdout(
        text=(
            f"RESEEDED  {args.item}  {reseeded.ref} at {reseeded.commit}  "
            f"from {reseeded.source_ref} at {reseeded.source_commit} "
            f"onto {branch} at {reseeded.tip_commit}\n"
        )
    )
    return 0
