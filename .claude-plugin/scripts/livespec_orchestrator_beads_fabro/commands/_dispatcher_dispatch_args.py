"""The flag surface every DISPATCHING dispatcher subcommand shares.

Split out of `dispatcher.py` by cohesion. That module is the Dispatcher's
supervisor and subcommand ROUTER -- it owns `main`, the handler table and the
per-subcommand argument declarations of the check and reconcile commands --
while this one owns a single group: the arguments that describe HOW one
dispatch runs. `dispatch`, `loop` and `probe` all take that group whole, and
none of the other subcommands takes any of it.

It follows the shape `_dispatcher_invoker.add_invoker_argument` already
established here: an argument GROUP lives beside its own concern and is added
back into whichever parser needs it, rather than being spelled out again per
subcommand.

`add_probe_arguments` moves with it because the probe's surface IS the common
surface plus two decisions about it, so the two cannot be understood apart.
"""

from __future__ import annotations

import argparse

from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import (
    add_invoker_argument,
)

__all__: list[str] = [
    "add_dispatch_common",
    "add_probe_arguments",
]


def add_probe_arguments(*, parser: argparse.ArgumentParser) -> None:
    # The probe drives the SAME published machinery an ordinary dispatch uses,
    # so it carries the same flag surface: the namespace it builds is the one
    # the dispatch and reconcile entry points are handed unchanged.
    add_dispatch_common(parser=parser)
    # `--item` is deliberately NOT `required=True`. The loop-probe clause makes
    # "refuse without a designated item, and create nothing" a BEHAVIOUR of the
    # probe rather than a parser accident, so the flag is optional here and the
    # handler owns the refusal, its wording, and its precondition exit code.
    _ = parser.add_argument("--item", dest="item", default=None)
    # The reconcile valve's live-dispatch bypass is never the probe's to take:
    # the probe drives its own cycle, so there is no dead dispatcher process to
    # reach around. Its re-grade arm is never the probe's either — the probe's
    # item reaches acceptance for the first time, so it carries no failed
    # verdict to revisit. Both are defaulted rather than exposed so no
    # invocation can arm them.
    parser.set_defaults(force=False, regrade=False)


def add_dispatch_common(*, parser: argparse.ArgumentParser) -> None:
    # `--invoker` is the FIRST of the two accepted identity inputs of
    # the journal invoker attribution contract in contracts.md; it wins over
    # `LIVESPEC_INVOKER`, which wins over the derived unattributed mark.
    add_invoker_argument(parser=parser)
    _ = parser.add_argument("--repo", dest="repo", required=True)
    _ = parser.add_argument("--factory", dest="factory", default=None)
    _ = parser.add_argument("--workflow", dest="workflow", default=None)
    # WHICH named variant of `dispatcher.workflows` this dispatch runs, per the
    # named-workflow-variant clause of `SPECIFICATION/contracts.md`. Like
    # `--acp-node` below it is an ARGUMENT and never an environment variable,
    # for the same reason: an ad-hoc shell must not be able to change which
    # GRAPH the factory runs with nothing in the committed record or the
    # journal to show for it. The resolved name is pinned to the work-item, so
    # a retry re-runs the variant the first attempt ran.
    _ = parser.add_argument(
        "--workflow-name",
        dest="workflow_name",
        default=None,
        metavar="NAME",
        help=(
            "select one registered `dispatcher.workflows` variant for this dispatch; "
            "defaults to the name this work-item last dispatched under, then to "
            "dispatcher.default_workflow"
        ),
    )
    # Default None (NOT the bare name "fabro"): a None sentinel means "not
    # explicitly passed -> resolve from LIVESPEC_FABRO_BIN / the .livespec.jsonc
    # dispatcher.fabro_bin key / the absolute default at command entry". An
    # explicit `--fabro-bin <path>` still wins over resolution.
    _ = parser.add_argument("--fabro-bin", dest="fabro_bin", default=None)
    _ = parser.add_argument("--janitor", dest="janitor", default=None)
    _ = parser.add_argument("--journal", dest="journal", default=None)
    # The PER-DISPATCH adapter layer of `SPECIFICATION/contracts.md`. It is an
    # ARGUMENT and never an environment variable, on purpose: an ad-hoc shell
    # must not be able to re-provider the factory with nothing in the record,
    # so the override is given on the command line and journaled on the
    # dispatch record. Repeatable, one node per occurrence.
    _ = parser.add_argument(
        "--acp-node",
        dest="acp_node",
        action="append",
        default=None,
        metavar="NODE=ADAPTER",
        help=(
            "override one ACP node's adapter for this dispatch only, as a complete "
            "adapter command line (leading KEY=value env assignments, then the "
            "command and its arguments); repeatable"
        ),
    )
    _ = parser.add_argument("--poll-attempts", dest="poll_attempts", type=int, default=80)
    _ = parser.add_argument(
        "--poll-interval-seconds",
        dest="poll_interval_seconds",
        type=float,
        default=30.0,
    )
    _ = parser.add_argument(
        "--no-close-on-merge",
        dest="close_on_merge",
        action="store_false",
    )
    _ = parser.add_argument(
        "--skip-ledger-check",
        dest="skip_ledger_check",
        action="store_true",
    )
    _ = parser.add_argument("--json", dest="as_json", action="store_true")
