"""The `impl:<id>` dispatch transport of the drive operator surface.

Split out of `drive.py` along its cohesion seam: `drive.py` is the CLI
supervisor and action ROUTER (parse, refuse, pick a handler, render), while
this module is the one handler that shells out — it builds the
`dispatcher.py loop` argv, runs it through the injected `CommandRunner`, and
maps the Dispatcher's exit code and JSON onto a drive result payload.

`CommandRun` and the `CommandRunner` protocol live here because they are the
transport's own vocabulary; `drive.py` imports them back so its published
surface is unchanged.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from livespec_orchestrator_beads_fabro._store_ready_dwell import utc_now_iso
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import (
    FALLBACK_SOURCE,
    INVOKER_FLAG,
    InvokerIdentity,
)
from livespec_orchestrator_beads_fabro.commands._plan_recovery_receipt_write import (
    record_impl_recovery_receipts,
)
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "CommandRun",
    "CommandRunner",
    "build_dispatcher_argv",
    "run_impl_dispatch",
]

_JOURNAL_RELATIVE_PATH = Path("tmp") / "fabro-dispatch-journal.jsonl"
_BEADS_CONFIG_RELATIVE_PATH = Path(".beads") / "config.yaml"


@dataclass(frozen=True, kw_only=True)
class CommandRun:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> CommandRun:
        """Run argv and return captured output."""
        ...


def run_impl_dispatch(  # noqa: PLR0913 — kw-only transport; `workflow_name` is one more independent per-dispatch input forwarded verbatim, not a coupled one.
    *,
    repo: Path,
    work_item_ref: str,
    runner: CommandRunner | None,
    dispatcher_bin: Path | None,
    acp_nodes: tuple[str, ...],
    workflow_name: str | None,
    identity: InvokerIdentity | None,
) -> dict[str, Any]:
    """Run one `impl:<id>` action as a `dispatcher.py loop` subprocess."""
    resolved_runner = _SubprocessRunner() if runner is None else runner
    resolved_dispatcher = _resolve_dispatcher_bin(dispatcher_bin=dispatcher_bin)
    argv = build_dispatcher_argv(
        repo=repo,
        dispatcher_bin=resolved_dispatcher,
        work_item_ref=work_item_ref,
        acp_nodes=acp_nodes,
        workflow_name=workflow_name,
        identity=identity,
    )
    result = resolved_runner(argv=argv, cwd=repo)
    _record_recovery_receipts(
        repo=repo,
        work_item_ref=work_item_ref,
        identity=identity,
    )
    parsed = _parse_json_object_or_array(text=result.stdout)
    status = _dispatch_status(returncode=result.returncode, parsed=parsed)
    return {
        "action_id": f"impl:{work_item_ref}",
        "kind": "impl",
        "work_item_ref": work_item_ref,
        "status": status,
        "dispatcher": {
            "argv": list(argv),
            "exit_code": result.returncode,
            "stdout_json": parsed,
            "stderr": result.stderr,
        },
        "summary": _dispatch_summary(status=status, work_item_ref=work_item_ref),
    }


def _record_recovery_receipts(
    *, repo: Path, work_item_ref: str, identity: InvokerIdentity | None
) -> None:
    """Attach only executor-observed receipts after the Dispatcher returns.

    The journal is the durable source of dispatch, run, and terminal-outcome
    evidence.  A configured repository without that file still reaches the
    writer with `None`, which preserves its recorded-but-not-executed answer for
    an authorized attempt whose command never dispatched.  Fixture repositories
    without the Beads pointer are not stores and must not be treated as one.
    """
    journal_path = repo / _JOURNAL_RELATIVE_PATH
    if not journal_path.is_file() and not (repo / _BEADS_CONFIG_RELATIVE_PATH).is_file():
        return
    _ = record_impl_recovery_receipts(
        config=resolve_store_config(cwd=repo, work_items_arg=None),
        work_item_id=work_item_ref,
        journal_path=journal_path if journal_path.is_file() else None,
        author=_receipt_author(identity=identity),
        now=utc_now_iso(),
    )


def _receipt_author(*, identity: InvokerIdentity | None) -> str:
    """The executor identity carried on its authority transition."""
    return (
        identity.invoker
        if identity is not None and identity.invoker_source != FALLBACK_SOURCE
        else "unattributed drive executor"
    )


def build_dispatcher_argv(
    *,
    repo: Path,
    dispatcher_bin: Path,
    work_item_ref: str,
    acp_nodes: tuple[str, ...] = (),
    workflow_name: str | None = None,
    identity: InvokerIdentity | None = None,
) -> tuple[str, ...]:
    """Build the `dispatcher.py loop` argv one `impl:<id>` action runs.

    Each ACP adapter override becomes its own `--acp-node NODE=ADAPTER`
    pair, so the value reaches the Dispatcher as a single argv element and
    an adapter carrying spaces survives without quoting games.

    `--workflow-name` is re-emitted the same way and for the same reason the
    ACP overrides are: the workflow-variant selector is a recorded ARGUMENT
    and never an environment variable, so the only route from this operator
    surface to the Dispatcher is the argv this function builds — which is
    also what the drive result payload publishes back. Omitted entirely when
    unselected, so the Dispatcher's own ledger-then-default precedence
    resolves it rather than being pre-empted by an empty string.

    An ASSERTED identity (flag or environment) is forwarded as an explicit
    `--invoker` so the spawned Dispatcher records the operator, not the shell
    that spawned it. A FALLBACK identity is deliberately NOT forwarded: it is a
    mark meaning "nobody asserted", and passing it as a flag would relabel it
    `flag`-sourced — laundering an unattributed act into an asserted one, and
    defeating `require_invoker` downstream into the bargain.
    """
    overrides = tuple(element for override in acp_nodes for element in ("--acp-node", override))
    return (
        "python3",
        str(dispatcher_bin),
        "loop",
        *_forwarded_invoker(identity=identity),
        "--repo",
        str(repo),
        "--budget",
        "1",
        "--parallel",
        "1",
        "--item",
        work_item_ref,
        *_forwarded_workflow_name(workflow_name=workflow_name),
        *overrides,
        "--json",
    )


class _SubprocessRunner:
    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> CommandRun:
        completed = subprocess.run(  # noqa: S603 - argv is constructed without shell.
            argv,
            check=False,
            cwd=cwd,
            text=True,
            capture_output=True,
        )
        return CommandRun(
            argv=argv,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


def _forwarded_workflow_name(*, workflow_name: str | None) -> tuple[str, ...]:
    if workflow_name is None or workflow_name == "":
        return ()
    return ("--workflow-name", workflow_name)


def _forwarded_invoker(*, identity: InvokerIdentity | None) -> tuple[str, ...]:
    if identity is None or identity.invoker_source == FALLBACK_SOURCE:
        return ()
    return (INVOKER_FLAG, identity.invoker)


def _dispatch_status(*, returncode: int, parsed: object) -> str:
    if isinstance(parsed, list) and parsed:
        parsed_list = cast("list[object]", parsed)
        first = parsed_list[0]
        if isinstance(first, dict):
            first_dict = cast("dict[str, object]", first)
            status = first_dict.get("status")
            if isinstance(status, str):
                return status
    if returncode == 0:
        return "green"
    return "failed"


def _dispatch_summary(*, status: str, work_item_ref: str) -> str:
    if status == "green":
        return f"Dispatcher reported green for {work_item_ref}."
    if status == "blocked":
        return f"Dispatcher reported a human-gated blocked run for {work_item_ref}."
    return f"Dispatcher did not report green for {work_item_ref}."


def _parse_json_object_or_array(*, text: str) -> object:
    parsed = parse_json(text=text)
    if isinstance(parsed, JsonParseFailure):
        return None
    return parsed


def _resolve_dispatcher_bin(*, dispatcher_bin: Path | None) -> Path:
    if dispatcher_bin is not None:
        return dispatcher_bin
    return _scripts_root() / "bin" / "dispatcher.py"


def _scripts_root() -> Path:
    return Path(__file__).resolve().parents[2]
