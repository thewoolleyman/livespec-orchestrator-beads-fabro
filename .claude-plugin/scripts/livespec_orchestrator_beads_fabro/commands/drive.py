"""Minimal action-id executor for the drive operator surface."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import effective_admission_policy
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout
from livespec_orchestrator_beads_fabro.store import (
    read_work_items,
    update_work_item_policy,
    update_work_item_status,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

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
_PARTS_ACTION_REF = 2
_PARTS_REJECT = 3


def run_action(
    *,
    repo: Path,
    action_id: str,
    runner: CommandRunner | None = None,
    dispatcher_bin: Path | None = None,
) -> dict[str, Any]:
    """Run one selected action-id."""
    if _is_human_valve_action(action_id=action_id):
        return run_human_valve_action(repo=repo, action_id=action_id, runner=runner)
    if not action_id.startswith("impl:"):
        return {
            "action_id": action_id,
            "kind": "unknown",
            "status": "failed",
            "summary": (
                "Unsupported action id; expected 'impl:<id>', 'approve:<id>', "
                "'accept:<id>', 'reject:<id>:rework|regroom', "
                "'set-admission:<id>:auto|manual', or "
                "'set-acceptance:<id>:ai-only|human-only|ai-then-human'."
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


def run_human_valve_action(
    *, repo: Path, action_id: str, runner: CommandRunner | None = None
) -> dict[str, Any]:
    parsed = _parse_human_valve_action(action_id=action_id)
    if parsed is None:
        return _valve_refusal(
            action_id=action_id,
            domain_error="invalid-action-id",
            summary="Unsupported human valve action id.",
        )
    action, item_id, action_value = parsed
    config = resolve_store_config(cwd=repo, work_items_arg=None)
    items = list(read_work_items(path=config))
    item = _find_item(items=items, item_id=item_id)
    if item is None:
        return _valve_refusal(
            action_id=action_id,
            domain_error="work-item-not-found",
            summary=f"work-item not found: {item_id}",
        )
    if action == "approve":
        return _approve_item(config=config, item=item, action_id=action_id)
    if action == "accept":
        return _accept_item(config=config, item=item, action_id=action_id)
    if action in {"set-admission", "set-acceptance"}:
        return _set_policy(
            config=config,
            item=item,
            action_id=action_id,
            action=action,
            value=cast("str", action_value),
        )
    return _reject_item(
        repo=repo,
        config=config,
        item=item,
        action_id=action_id,
        reject_kind=cast("str", action_value),
        runner=runner,
    )


def _is_human_valve_action(*, action_id: str) -> bool:
    return action_id.startswith(
        ("approve:", "accept:", "reject:", "set-admission:", "set-acceptance:")
    )


def _parse_human_valve_action(*, action_id: str) -> tuple[str, str, str | None] | None:
    parts = action_id.split(":")
    if len(parts) == _PARTS_ACTION_REF and parts[0] in {"approve", "accept"} and parts[1] != "":
        return (parts[0], parts[1], None)
    if (
        len(parts) == _PARTS_REJECT
        and parts[0] == "reject"
        and parts[1] != ""
        and parts[2] in {"rework", "regroom"}
    ):
        return (parts[0], parts[1], parts[2])
    if (
        len(parts) == _PARTS_REJECT
        and parts[0] == "set-admission"
        and parts[1] != ""
        and parts[2] in {"auto", "manual"}
    ):
        return (parts[0], parts[1], parts[2])
    if (
        len(parts) == _PARTS_REJECT
        and parts[0] == "set-acceptance"
        and parts[1] != ""
        and parts[2] in {"ai-only", "human-only", "ai-then-human"}
    ):
        return (parts[0], parts[1], parts[2])
    return None


def _find_item(*, items: list[WorkItem], item_id: str) -> WorkItem | None:
    for item in items:
        if item.id == item_id:
            return item
    return None


def _approve_item(
    *,
    config: StoreConfig,
    item: WorkItem,
    action_id: str,
) -> dict[str, Any]:
    if item.status != "pending-approval":
        return _invalid_source_state(action_id=action_id, item=item, expected="pending-approval")
    if effective_admission_policy(item=item) != "manual":
        return _valve_refusal(
            action_id=action_id,
            work_item_id=item.id,
            domain_error="invalid-source-state",
            summary="approve requires an effective-manual pending-approval item.",
        )
    update_work_item_status(path=config, item_id=item.id, status="ready")
    return _valve_success(
        action_id=action_id,
        work_item_id=item.id,
        stage="human-valve-approve",
        target_status="ready",
        assignee=None,
        summary=f"Approved {item.id}: pending-approval -> ready.",
    )


def _set_policy(
    *,
    config: StoreConfig,
    item: WorkItem,
    action_id: str,
    action: str,
    value: str,
) -> dict[str, Any]:
    admission_policy = value if action == "set-admission" else None
    acceptance_policy = value if action == "set-acceptance" else None
    update_work_item_policy(
        path=config,
        item_id=item.id,
        admission_policy=admission_policy,
        acceptance_policy=acceptance_policy,
    )
    return _valve_success(
        action_id=action_id,
        work_item_id=item.id,
        stage=f"human-valve-{action}",
        target_status=item.status,
        assignee=item.assignee,
        summary=(
            f"Updated {item.id}: {action.removeprefix('set-')} policy -> {value}; "
            "status unchanged."
        ),
    )


def _accept_item(*, config: StoreConfig, item: WorkItem, action_id: str) -> dict[str, Any]:
    if item.status != "acceptance":
        return _invalid_source_state(action_id=action_id, item=item, expected="acceptance")
    update_work_item_status(path=config, item_id=item.id, status="done")
    return _valve_success(
        action_id=action_id,
        work_item_id=item.id,
        stage="human-valve-accept",
        target_status="done",
        assignee=None,
        summary=f"Accepted {item.id}: acceptance -> done.",
    )


def _reject_item(
    *,
    repo: Path,
    config: StoreConfig,
    item: WorkItem,
    action_id: str,
    reject_kind: str,
    runner: CommandRunner | None,
) -> dict[str, Any]:
    if item.status != "acceptance":
        return _invalid_source_state(action_id=action_id, item=item, expected="acceptance")
    target_status = "active" if reject_kind == "rework" else "backlog"
    if reject_kind == "regroom":
        revert_refusal = _revert_merged_change(
            repo=repo, item=item, action_id=action_id, runner=runner
        )
        if revert_refusal is not None:
            return revert_refusal
    update_work_item_status(path=config, item_id=item.id, status=target_status)
    return _valve_success(
        action_id=action_id,
        work_item_id=item.id,
        stage=f"human-valve-reject-{reject_kind}",
        target_status=target_status,
        assignee=None,
        summary=f"Rejected {item.id}: acceptance -> {target_status}.",
    )


def _revert_merged_change(
    *, repo: Path, item: WorkItem, action_id: str, runner: CommandRunner | None
) -> dict[str, Any] | None:
    merge_sha = item.audit.merge_sha if item.audit is not None else None
    if not merge_sha:
        return _valve_refusal(
            action_id=action_id,
            work_item_id=item.id,
            domain_error="missing-merge-evidence",
            summary="reject:regroom refused: no merged change recorded to revert.",
        )
    resolved_runner = _SubprocessRunner() if runner is None else runner
    result = resolved_runner(argv=("git", "revert", "--no-edit", merge_sha), cwd=repo)
    if result.returncode == 0:
        return None
    return _valve_refusal(
        action_id=action_id,
        work_item_id=item.id,
        domain_error="revert-failed",
        summary=f"reject:regroom refused: git revert {merge_sha} failed: {result.stderr}",
    )


def _invalid_source_state(*, action_id: str, item: WorkItem, expected: str) -> dict[str, Any]:
    return _valve_refusal(
        action_id=action_id,
        work_item_id=item.id,
        domain_error="invalid-source-state",
        summary=(
            f"{action_id} expected {expected} source state for {item.id}; " f"found {item.status}."
        ),
    )


def _valve_success(
    *,
    action_id: str,
    work_item_id: str,
    stage: str,
    target_status: str,
    assignee: str | None,
    summary: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "action_id": action_id,
        "kind": "human-valve",
        "work_item_ref": work_item_id,
        "status": "green",
        "target_status": target_status,
        "journal": _valve_journal(stage=stage, work_item_id=work_item_id),
        "summary": summary,
    }
    if assignee is not None:
        payload["assignee"] = assignee
    return payload


def _valve_refusal(
    *,
    action_id: str,
    domain_error: str,
    summary: str,
    work_item_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "action_id": action_id,
        "kind": "human-valve",
        "status": "failed",
        "domain_error": domain_error,
        "summary": summary,
    }
    if work_item_id is not None:
        payload["work_item_ref"] = work_item_id
    return payload


def _valve_journal(*, stage: str, work_item_id: str) -> dict[str, str]:
    return {"actor": "operator", "stage": stage, "work_item_id": work_item_id}


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
        "--mode",
        "shadow",
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
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


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
