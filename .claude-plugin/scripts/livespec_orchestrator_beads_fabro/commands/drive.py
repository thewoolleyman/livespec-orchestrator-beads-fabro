"""Minimal action-id executor for the drive operator surface."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from livespec_orchestrator_beads_fabro.commands._drive_config import (
    is_config_action,
    run_config_action,
)
from livespec_orchestrator_beads_fabro.commands._drive_valves import (
    is_human_valve_action,
    run_human_valve_action,
)
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout

__all__: list[str] = [
    "CommandRun",
    "build_dispatcher_argv",
    "main",
    "run_action",
    "run_human_valve_action",
]


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


_EXIT_FAILURE = 1
_EXIT_PRECONDITION_ERROR = 3


def run_action(
    *,
    repo: Path,
    action_id: str,
    runner: CommandRunner | None = None,
    dispatcher_bin: Path | None = None,
) -> dict[str, Any]:
    """Run one selected action-id."""
    if is_human_valve_action(action_id=action_id):
        return run_human_valve_action(repo=repo, action_id=action_id, runner=runner)
    if is_config_action(action_id=action_id):
        return run_config_action(repo=repo, action_id=action_id)
    if not action_id.startswith("impl:"):
        return {
            "action_id": action_id,
            "kind": "unknown",
            "status": "failed",
            "summary": (
                "Unsupported action id; expected 'impl:<id>', 'approve:<id>', "
                "'accept:<id>', 'reject:<id>:rework|regroom', "
                "'set-admission:<id>:auto|manual', "
                "'set-acceptance:<id>:ai-only|human-only|ai-then-human', "
                "'set-merge-on-review-cap:<id>:true|false', "
                "'set-review-fix-cap:<id>:<positive-int>', "
                "'set-acceptance-rework-cap:<id>:<positive-int>' "
                "(any set-*-cap accepts 'clear' as the value to inherit-global), "
                "'move:<id>:backlog|ready|blocked|active', "
                "'config', 'config-manifest', or 'set-config:<key>:<value>'."
            ),
        }
    work_item_ref = action_id.removeprefix("impl:")
    resolved_runner = _SubprocessRunner() if runner is None else runner
    resolved_dispatcher = _resolve_dispatcher_bin(dispatcher_bin=dispatcher_bin)
    argv = build_dispatcher_argv(
        repo=repo,
        dispatcher_bin=resolved_dispatcher,
        work_item_ref=work_item_ref,
    )
    result = resolved_runner(argv=argv, cwd=repo)
    parsed = _parse_json_object_or_array(text=result.stdout)
    status = _dispatch_status(returncode=result.returncode, parsed=parsed)
    return {
        "action_id": action_id,
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


def build_dispatcher_argv(
    *,
    repo: Path,
    dispatcher_bin: Path,
    work_item_ref: str,
) -> tuple[str, ...]:
    return (
        "python3",
        str(dispatcher_bin),
        "loop",
        "--repo",
        str(repo),
        "--budget",
        "1",
        "--parallel",
        "1",
        "--item",
        work_item_ref,
        "--json",
    )


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
    result = run_action(repo=repo, action_id=args.action, runner=runner)
    _emit_payload(payload=result, as_json=args.as_json)
    return 0 if result["status"] == "green" else _EXIT_FAILURE


def _resolve_repo(*, repo_arg: str | None) -> Path:
    """Resolve the target repo: the cwd when `--repo` is omitted, else the path."""
    if repo_arg is None:
        return Path.cwd()
    return Path(repo_arg)


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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="drive")
    _ = parser.add_argument("retired_subcommand", nargs="?")
    _ = parser.add_argument("--repo", dest="repo", required=False, default=None)
    _ = parser.add_argument("--action", dest="action", required=False, default=None)
    _ = parser.add_argument("--json", dest="as_json", action="store_true")
    return parser


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


def _resolve_dispatcher_bin(*, dispatcher_bin: Path | None) -> Path:
    if dispatcher_bin is not None:
        return dispatcher_bin
    return _scripts_root() / "bin" / "dispatcher.py"


def _scripts_root() -> Path:
    return Path(__file__).resolve().parents[2]
