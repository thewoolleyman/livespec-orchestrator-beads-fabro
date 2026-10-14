"""The `drive` CLI's operator transport: the argv it accepts and what it renders back.

Split out of `drive.py` by cohesion, on the same seam `_session_wait_cli` sits on
for `session_wait`. `drive.py` keeps the two things that DECIDE — the action
router and the supervisor sequence — while this module owns the conversion
between an operator's shell and a typed call: the argument surface going in, and
the payload rendering plus the exit code coming back. Nothing here reads the
store, spawns a dispatch, or grades an action.

The exit codes live here with `exit_code_for_status`, which is the one place
they are mapped from a result status. `EXIT_PRECONDITION_ERROR` is public
because the supervisor returns it directly for the two faults it detects before
any action runs — a `--repo` that does not exist and an unattributed
state-changing invocation — and splitting the codes across two modules so one
could stay private is how the surface comes to disagree with itself.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import (
    add_invoker_argument,
)
from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = [
    "EXIT_PRECONDITION_ERROR",
    "build_parser",
    "emit_payload",
    "exit_code_for_status",
    "resolve_repo",
]

_EXIT_FAILURE = 1
EXIT_PRECONDITION_ERROR = 3
_EXIT_BLOCKED = 4


def exit_code_for_status(*, status: str) -> int:
    if status == "green":
        return 0
    if status == "blocked":
        return _EXIT_BLOCKED
    return _EXIT_FAILURE


def resolve_repo(*, repo_arg: str | None) -> Path:
    """Resolve the target repo: the cwd when `--repo` is omitted, else the path."""
    if repo_arg is None:
        return Path.cwd()
    return Path(repo_arg)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="drive")
    _ = parser.add_argument("retired_subcommand", nargs="?")
    _ = parser.add_argument("--repo", dest="repo", required=False, default=None)
    _ = parser.add_argument("--action", dest="action", required=False, default=None)
    # The PER-DISPATCH ACP adapter layer, reachable from the operator
    # surface as well as from `dispatcher.py` directly. It is an ARGUMENT
    # and never an environment variable so the override lands in the
    # recorded argv and on the dispatch record.
    _ = parser.add_argument(
        "--acp-node",
        dest="acp_node",
        action="append",
        default=None,
        metavar="NODE=ADAPTER",
        help=(
            "override one ACP node's adapter for this dispatch only, as a complete "
            "adapter command line; repeatable"
        ),
    )
    # The PER-DISPATCH workflow-variant selector, reachable from the operator
    # surface on the same terms as `--acp-node` above and re-emitted into the
    # `dispatcher.py loop` argv verbatim. An ARGUMENT and never an environment
    # variable: which GRAPH the factory runs must be visible in the recorded
    # argv and on the dispatch record.
    _ = parser.add_argument(
        "--workflow-name",
        dest="workflow_name",
        default=None,
        metavar="NAME",
        help=(
            "select one registered `dispatcher.workflows` variant for this dispatch; "
            "forwarded to the Dispatcher, which resolves the work-item's recorded "
            "variant then dispatcher.default_workflow when this is omitted"
        ),
    )
    # WHAT CHANGED since this work-item's recorded dispatch failure, forwarded
    # into the `dispatcher.py loop` argv as one unchanged argument. An ARGUMENT
    # for the same reason `--acp-node` is one: the reason is written to the item
    # and to the dispatch journal, so what authorized a re-dispatch belongs in
    # the recorded invocation rather than in an ambient value.
    _ = parser.add_argument(
        "--because",
        dest="because",
        default=None,
        metavar="REASON",
        help=(
            "what changed since this work-item's most recently recorded dispatch "
            "failure, for 'impl:<id>' only; forwarded to the Dispatcher, which "
            "refuses a re-dispatch past a recorded refusal signature without it"
        ),
    )
    # The v093-native answer route. A factory run that needs a human decision
    # TERMINATES, so the answer cannot go back to the run that asked: it is
    # written to the item's ledger, which is what the NEXT dispatch's goal brief
    # already reads.
    _ = parser.add_argument(
        "--answer",
        dest="answer",
        default=None,
        metavar="TEXT",
        help=(
            "the answer to the question a terminated run published, for "
            "resolve-blocked only; written to the work-item's ledger before the "
            "transition so the re-dispatched brief carries it"
        ),
    )
    # The driver-dispatch door's one input: WHICH session is taking the
    # host-only item. An ARGUMENT for the same reason `--acp-node` is one — the
    # reference belongs in the recorded argv and on the journal record, not in
    # an environment variable no reader of either can see.
    _ = parser.add_argument(
        "--driver-session",
        dest="driver_session",
        default=None,
        metavar="REF",
        help=(
            "reference to the session that will drive the item by hand, for "
            "driver-dispatch only; journaled with the ready -> active transition. "
            "Defaults to the resolved invoker."
        ),
    )
    add_invoker_argument(parser=parser)
    _ = parser.add_argument("--json", dest="as_json", action="store_true")
    return parser


def emit_payload(*, payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        _ = write_stdout(text=json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return
    _ = write_stdout(text=_human_summary(payload=payload) + "\n")


def _human_summary(*, payload: dict[str, Any]) -> str:
    """Render a drive result as human-readable Markdown."""
    return _run_markdown(payload=payload)


def _run_markdown(*, payload: dict[str, Any]) -> str:
    action_id = str(payload.get("action_id", "unknown"))
    status = str(payload.get("status", "unknown"))
    lines = [f"# drive — {action_id}", "", f"- status: **{status}**"]
    dispatcher = payload.get("dispatcher")
    if isinstance(dispatcher, dict):
        dispatcher_dict = cast("dict[str, Any]", dispatcher)
        lines.append(f"- dispatcher exit code: {dispatcher_dict.get('exit_code')}")
    lines.append(f"- {payload.get('summary', '')}")
    return "\n".join(lines)
