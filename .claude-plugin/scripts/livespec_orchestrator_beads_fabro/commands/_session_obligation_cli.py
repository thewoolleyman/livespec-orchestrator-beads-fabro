"""The two host commands a coordinator drives its launch obligations through.

`session-wait launch` is the registration boundary of `contracts.md` section
"Launch obligations and consumed recovery" — "Dispatch/delegation MUST persist
intent ... BEFORE reporting a protected launch" — and `session-wait complete` is
its completion gate: "Supported completion gates MUST verify durable launch
obligations and independent producer/consumer registration."

WHY THESE ARE SEPARATE COMMANDS FROM `wait`. The incident this plan exists to
retire is an obligation whose coordinator never armed a wait, so a registration
reachable only through the wait command could not cover it — the clause says so
in as many words: "An actual owning session leaving its turn with unresolved
authorized work MUST remain covered even if it never arms a wait." `launch`
therefore registers without arming anything, and `complete` reads the obligation
store rather than the wait store.

WHY THE CANONICAL RESULT, EPOCH AND DEADLINE ARE REQUIRED ARGUMENTS. They are
the relay contract's, not this surface's, and the same clause forbids a second
one: "This contract MUST NOT define a second result enum, independently reset an
obligation deadline or equate wait completion with result fulfillment." So the
caller supplies the rendered `ResultReference` identity, the epoch and the
ORIGINAL deadline as the relay already holds them, and nothing here computes,
defaults or refreshes any of the three. A default would be this surface
inventing the deadline it was handed the authority to record.

WHY COVERAGE IS NOT AN ARGUMENT. It is read off the host, through
`_session_obligation_host`, because the clause makes the declaration "runtime
evidence, not a user-selectable exemption" — an option here would be exactly
the exemption it forbids.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

from livespec_orchestrator_beads_fabro.commands._session_obligation_delegation import (
    gate_launch_observer,
    pane_launch_observer,
    register_launch,
)
from livespec_orchestrator_beads_fabro.commands._session_obligation_host import (
    coverage_declaration_path,
    host_coverage_reading,
    obligation_store_root,
)
from livespec_orchestrator_beads_fabro.commands._session_obligation_launch import (
    protected_completion,
)
from livespec_orchestrator_beads_fabro.commands._session_obligation_records import (
    LaunchAuthority,
    LaunchIntent,
)
from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = [
    "SubcommandFactory",
    "add_obligation_parsers",
    "complete_command",
    "launch_command",
]


class SubcommandFactory(Protocol):
    """A host CLI's own `add_parser`, handed in rather than its action type.

    Taking the factory keeps the private `argparse` subparsers-action type out
    of this module's signature while leaving the ONE parser the host CLI owns
    in charge of its own subcommand set.
    """

    def __call__(self, name: str, /) -> argparse.ArgumentParser: ...


# How long one pane observation may spend before the registration reports the
# target as unobserved. It is this surface's own budget rather than the wait's:
# `launch` arms nothing and returns at once, so there is no shared deadline to
# carve it out of, and an unbounded freeze would hold the command open against a
# server that accepted the request and never answered.
_PANE_OBSERVATION_TIMEOUT_SECONDS = 5.0


def add_obligation_parsers(*, add_parser: SubcommandFactory) -> None:
    """Wire the two obligation commands onto the host CLI's subcommand set."""
    launch = add_parser("launch")
    _ = launch.add_argument("--repo", required=True)
    _ = launch.add_argument("--session-id", required=True)
    _ = launch.add_argument("--invoker", required=True)
    _ = launch.add_argument("--scope", required=True)
    _ = launch.add_argument("--operation-id", required=True)
    _ = launch.add_argument("--required-result", required=True)
    _ = launch.add_argument("--result-epoch", required=True, type=int)
    _ = launch.add_argument("--original-deadline", required=True)
    target = launch.add_mutually_exclusive_group(required=True)
    _ = target.add_argument("--gate")
    # Two values rather than one delimited string, for the reason the wait
    # command gives: a Herdr pane id carries a colon by construction.
    _ = target.add_argument("--pane", nargs=2, metavar=("SOCKET", "PANE_ID"))
    complete = add_parser("complete")
    _ = complete.add_argument("--repo", required=True)


def launch_command(
    *,
    args: argparse.Namespace,
    primary: Path,
    gate_store_root: Path,
    wall_clock: Callable[[], float],
) -> int:
    """Register one dispatched or delegated launch and attach its real target."""
    pane = cast("list[str] | None", args.pane)
    observe = (
        gate_launch_observer(gate_store_root=gate_store_root, run_id=str(args.gate))
        if pane is None
        else pane_launch_observer(
            socket_path=Path(pane[0]),
            pane_id=pane[1],
            timeout_seconds=_PANE_OBSERVATION_TIMEOUT_SECONDS,
        )
    )
    outcome = register_launch(
        intent=_intent(args=args, primary=primary),
        coverage=host_coverage_reading(path=coverage_declaration_path(primary=primary)),
        obligation_store_root=obligation_store_root(primary=primary),
        observe=observe,
        now=wall_clock(),
    )
    _ = write_stdout(text=json.dumps(outcome.payload(), indent=2, sort_keys=True) + "\n")
    return int(not outcome.protected)


def _intent(*, args: argparse.Namespace, primary: Path) -> LaunchIntent:
    return LaunchIntent(
        operation_id=str(args.operation_id),
        authority=LaunchAuthority(
            session_id=str(args.session_id),
            repository=primary,
            invoker=str(args.invoker),
            scope=str(args.scope),
        ),
        required_result_identity=str(args.required_result),
        result_epoch=int(args.result_epoch),
        original_deadline=str(args.original_deadline),
    )


def complete_command(*, primary: Path) -> int:
    """Verify this host's durable obligations before a turn reports completion."""
    verdict = protected_completion(
        coverage=host_coverage_reading(path=coverage_declaration_path(primary=primary)),
        obligation_store_root=obligation_store_root(primary=primary),
    )
    payload: dict[str, object] = {
        "coverage_state": verdict.coverage_state,
        "diagnostic": verdict.diagnostic,
        "outstanding_operation_ids": list(verdict.outstanding_operation_ids),
        "protected": verdict.protected,
        "state": verdict.state,
    }
    _ = write_stdout(text=json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return int(not verdict.protected)
