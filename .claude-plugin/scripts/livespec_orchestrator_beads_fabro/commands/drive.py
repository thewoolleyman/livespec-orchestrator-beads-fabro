"""Minimal action-id executor for the drive operator surface.

`drive` is a published state-changing entry point, so per the journal invoker
attribution contract in `SPECIFICATION/contracts.md` it accepts
`--invoker <id>` and otherwise honors `LIVESPEC_INVOKER`, falling back to the
`unattributed:<os-user>@<hostname>` MARK. The resolved identity is threaded
into the human-valve journal writes and forwarded to `dispatcher.py loop` on
an `impl:` dispatch, so one operator act is attributed the same way wherever it
lands. Its two READ-ONLY actions (`config`, `config-manifest`) resolve identity
identically but are never refused on attribution grounds.

This module is the CLI supervisor and action ROUTER: parse, refuse, pick a
handler, render. The handlers live beside it — `_drive_valves` for the human
valves, `_drive_config` for the settings surface, and `_drive_impl_dispatch`
for the one handler that shells out to the Dispatcher.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import (
    InvokerIdentity,
    add_invoker_argument,
    default_invoker_identity,
    invoker_from_args,
    require_invoker_refusal,
)
from livespec_orchestrator_beads_fabro.commands._drive_config import (
    is_config_action,
    run_config_action,
)
from livespec_orchestrator_beads_fabro.commands._drive_driver_dispatch import (
    DRIVER_DISPATCH_PREFIX,
    is_driver_dispatch_action,
    run_driver_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._drive_impl_dispatch import (
    CommandRun,
    CommandRunner,
    build_dispatcher_argv,
    run_impl_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._drive_valve_grammar import is_human_valve_action
from livespec_orchestrator_beads_fabro.commands._drive_valves import run_human_valve_action
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout

__all__: list[str] = [
    "CommandRun",
    "build_dispatcher_argv",
    "main",
    "run_action",
    "run_human_valve_action",
]

_EXIT_FAILURE = 1
_EXIT_PRECONDITION_ERROR = 3
_EXIT_BLOCKED = 4
_IMPL_PREFIX = "impl:"
_RESOLVE_BLOCKED_PREFIX = "resolve-blocked:"

# The drive actions that only READ. Per the journal invoker attribution contract
# in contracts.md, a read-only invocation resolves and stamps identity
# identically when it journals, but is never REFUSED on attribution grounds.
_READ_ONLY_ACTIONS = frozenset({"config", "config-manifest"})

_UNSUPPORTED_ACTION_SUMMARY = (
    "Unsupported action id; expected 'impl:<id>', 'driver-dispatch:<id>', "
    "'approve:<id>', "
    "'accept:<id>', 'reject:<id>:rework|regroom', "
    "'set-admission:<id>:auto|manual', "
    "'set-acceptance:<id>:ai-only|human-only|ai-then-human', "
    "'set-factory-safety:<id>:needs-host-secrets|mutates-host-machinery|needs-privileged-host', "
    "'set-workflow-scope-override:<id>:citation-only', "
    "'set-merge-on-review-cap:<id>:true|false', "
    "'set-review-fix-cap:<id>:<positive-int>', "
    "'set-acceptance-rework-cap:<id>:<positive-int>' "
    "(any set-*-cap accepts 'clear' as the value to inherit-global), "
    "'set-merge-hold:<id>:on|off', "
    "'move:<id>:backlog|ready|blocked', "
    "'config', 'config-manifest', or 'set-config:<key>:<value>'."
)

# `--answer` is scoped to ONE action rather than accepted-and-ignored
# elsewhere. An answer discarded in silence is the worst available outcome: the
# operator sees a green result, believes the decision reached the item, and the
# re-dispatched brief arrives without it — the very gap this route closes.
_ANSWER_SCOPE_SUMMARY = (
    "--answer is accepted only by 'resolve-blocked:<id>:ready|backlog'; it is the "
    "answer written to the work-item's ledger so the next dispatch's brief carries it."
)

# `--driver-session` is scoped the same way and for the same reason: a reference
# accepted here and dropped would journal the wrong session on some later door,
# or none at all, while the operator saw a green result.
_DRIVER_SESSION_SCOPE_SUMMARY = (
    "--driver-session is accepted only by 'driver-dispatch:<id>'; it is the reference "
    "to the session driving the item, journaled with the transition it opens."
)


def run_action(  # noqa: PLR0913 — kw-only router; `answer` is one more independent transport input, not a coupled one.
    *,
    repo: Path,
    action_id: str,
    runner: CommandRunner | None = None,
    dispatcher_bin: Path | None = None,
    acp_nodes: tuple[str, ...] = (),
    workflow_name: str | None = None,
    identity: InvokerIdentity | None = None,
    answer: str | None = None,
    driver_session: str | None = None,
) -> dict[str, Any]:
    """Run one selected action-id.

    `acp_nodes` carries the per-dispatch ACP adapter overrides through to
    the Dispatcher unchanged. They are forwarded rather than interpreted
    here: `drive` is a transport onto `dispatcher.py loop`, and the layer
    that validates a node name is the one that also knows which workflow
    the dispatch will run.

    `workflow_name` selects one registered `dispatcher.workflows` variant and
    is forwarded on exactly the same terms: the registry lives in the dispatch
    TARGET's configuration, so the name is only meaningful to the layer that
    reads it, and the refusal for an unregistered one belongs there too.

    `identity` is the invocation's resolved invoker. `None` means "resolve it
    from the environment here" so a direct caller is still attributed; the CLI
    supervisor passes the identity it resolved, flag included.

    `answer` is the operator's answer to the question a terminated run
    published, and `driver_session` the reference to the session that will drive
    a host-only item by hand. Each is refused here for any action that cannot
    deliver it, so a mis-aimed input is reported rather than dropped.
    """
    resolved_identity = default_invoker_identity() if identity is None else identity
    misaimed = _misaimed_input_refusal(
        action_id=action_id, answer=answer, driver_session=driver_session
    )
    if misaimed is not None:
        return misaimed
    if is_driver_dispatch_action(action_id=action_id):
        return run_driver_dispatch(
            repo=repo,
            action_id=action_id,
            identity=resolved_identity,
            driver_session=driver_session,
        )
    if is_human_valve_action(action_id=action_id):
        return run_human_valve_action(
            repo=repo,
            action_id=action_id,
            runner=runner,
            identity=resolved_identity,
            answer=answer,
        )
    if is_config_action(action_id=action_id):
        return run_config_action(repo=repo, action_id=action_id)
    if not action_id.startswith(_IMPL_PREFIX):
        return {
            "action_id": action_id,
            "kind": "unknown",
            "status": "failed",
            "summary": _UNSUPPORTED_ACTION_SUMMARY,
        }
    return run_impl_dispatch(
        repo=repo,
        work_item_ref=action_id.removeprefix(_IMPL_PREFIX),
        runner=runner,
        dispatcher_bin=dispatcher_bin,
        acp_nodes=acp_nodes,
        workflow_name=workflow_name,
        identity=resolved_identity,
    )


def _misaimed_input_refusal(
    *, action_id: str, answer: str | None, driver_session: str | None
) -> dict[str, Any] | None:
    """Refuse a transport input the SELECTED action cannot deliver.

    An input accepted and discarded in silence is the worst available outcome:
    the operator sees a green result and believes the value reached the item.
    Both scoped inputs are graded here, in the router, so neither can reach a
    handler that has no idea what to do with it.
    """
    if answer is not None and not action_id.startswith(_RESOLVE_BLOCKED_PREFIX):
        return _scope_refusal(action_id=action_id, summary=_ANSWER_SCOPE_SUMMARY)
    if driver_session is not None and not action_id.startswith(DRIVER_DISPATCH_PREFIX):
        return _scope_refusal(action_id=action_id, summary=_DRIVER_SESSION_SCOPE_SUMMARY)
    return None


def _scope_refusal(*, action_id: str, summary: str) -> dict[str, Any]:
    return {
        "action_id": action_id,
        "kind": "unknown",
        "status": "failed",
        "summary": summary,
    }


def main(*, argv: list[str] | None = None, runner: CommandRunner | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.retired_subcommand is not None:
        parser.error(f"invalid choice: {args.retired_subcommand!r}")
    if args.action is None:
        parser.error("the following arguments are required: --action")
    repo = _resolve_repo(repo_arg=args.repo)
    if not repo.exists():
        _ = write_stderr(text=f"ERROR: --repo does not exist: {repo}\n")
        return _EXIT_PRECONDITION_ERROR
    refusal_exit = _invoker_refusal_exit(args=args, repo=repo)
    if refusal_exit is not None:
        return refusal_exit
    result = run_action(
        repo=repo,
        action_id=args.action,
        runner=runner,
        acp_nodes=tuple(args.acp_node or ()),
        workflow_name=args.workflow_name,
        identity=invoker_from_args(args=args),
        answer=args.answer,
        driver_session=args.driver_session,
    )
    _emit_payload(payload=result, as_json=args.as_json)
    return _exit_code_for_status(status=str(result["status"]))


def _invoker_refusal_exit(*, args: argparse.Namespace, repo: Path) -> int | None:
    """Refuse an unattributed STATE-CHANGING invocation before `run_action`.

    Called from the supervisor rather than from a handler on purpose: at this
    point no valve has read the store, no journal line has been written, and no
    dispatch has been spawned. The two read-only actions are exempt — the
    contract refuses state-changing invocations on attribution grounds, reads
    never.
    """
    if args.action in _READ_ONLY_ACTIONS:
        return None
    refusal = require_invoker_refusal(args=args, repo=repo)
    if refusal is None:
        return None
    _ = write_stderr(text=refusal)
    return _EXIT_PRECONDITION_ERROR


def _exit_code_for_status(*, status: str) -> int:
    if status == "green":
        return 0
    if status == "blocked":
        return _EXIT_BLOCKED
    return _EXIT_FAILURE


def _resolve_repo(*, repo_arg: str | None) -> Path:
    """Resolve the target repo: the cwd when `--repo` is omitted, else the path."""
    if repo_arg is None:
        return Path.cwd()
    return Path(repo_arg)


def _build_parser() -> argparse.ArgumentParser:
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


def _emit_payload(*, payload: dict[str, Any], as_json: bool) -> None:
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
