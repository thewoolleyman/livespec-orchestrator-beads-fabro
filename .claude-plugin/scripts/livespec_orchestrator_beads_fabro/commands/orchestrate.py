"""Minimal cross-side orchestrate operator surface.

`orchestrate plan` composes the existing spec-side `next` wrapper with
this plugin's impl-side `next` wrapper and emits user-selectable action
records. `orchestrate run` executes only selected impl actions through
the existing Dispatcher/Fabro path; spec-side actions are surfaced as
human handoffs and never mutate spec state directly.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import (
    effective_admission_policy,
    resolve_assignee,
    resolve_wip_cap,
)
from livespec_orchestrator_beads_fabro.store import read_work_items, update_work_item_status
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "CommandRun",
    "build_dispatcher_argv",
    "main",
    "plan_actions",
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
_EXIT_USAGE_ERROR = 2
_EXIT_PRECONDITION_ERROR = 3
_PARTS_ACTION_REF = 2
_PARTS_REJECT = 3
_SPEC_NEXT_BIN_ENV = "LIVESPEC_SPEC_NEXT_BIN"


def plan_actions(
    *,
    repo: Path,
    runner: CommandRunner | None = None,
    spec_next_bin: Path | None = None,
    impl_next_bin: Path | None = None,
) -> dict[str, Any]:
    """Build a deterministic action plan from spec-side and impl-side `next`."""
    resolved_runner = _SubprocessRunner() if runner is None else runner
    spec_result = _load_next(
        argv=_spec_next_argv(repo=repo, spec_next_bin=_resolve_spec_next_bin(spec_next_bin)),
        runner=resolved_runner,
        repo=repo,
    )
    impl_result = _load_next(
        argv=_impl_next_argv(repo=repo, impl_next_bin=_resolve_impl_next_bin(impl_next_bin)),
        runner=resolved_runner,
        repo=repo,
    )
    spec_actions = [
        _spec_action(candidate=candidate, index=index)
        for index, candidate in enumerate(spec_result.candidates)
    ]
    impl_actions = [_impl_action(candidate=candidate) for candidate in impl_result.candidates]
    actions = spec_actions + impl_actions
    return {
        "repo": str(repo),
        "actions": actions,
        "summary": {
            "spec_actions": len(spec_actions),
            "impl_actions": len(impl_actions),
            "total_actions": len(actions),
        },
        "sources": {
            "spec_next": spec_result.source,
            "impl_next": impl_result.source,
        },
    }


def run_action(
    *,
    repo: Path,
    action_id: str,
    runner: CommandRunner | None = None,
    dispatcher_bin: Path | None = None,
) -> dict[str, Any]:
    """Run one selected action.

    Only `impl:<work-item-id>` actions are executed. Spec-side actions
    return a handoff envelope so the operator can invoke the appropriate
    `/livespec:*` lifecycle command.
    """
    if action_id.startswith("spec:"):
        action_name = _action_id_part(action_id=action_id, index=1, default="next")
        return {
            "action_id": action_id,
            "kind": "spec",
            "status": "human-gated",
            "handoff": _spec_handoff(action=action_name),
            "summary": "Spec-side action requires an explicit livespec lifecycle command.",
        }
    if _is_human_valve_action(action_id=action_id):
        return run_human_valve_action(repo=repo, action_id=action_id, runner=runner)
    if not action_id.startswith("impl:"):
        return {
            "action_id": action_id,
            "kind": "unknown",
            "status": "failed",
            "summary": (
                "Unsupported action id; expected 'impl:<id>', 'spec:<action>:<index>', "
                "'approve:<id>', 'accept:<id>', or 'reject:<id>:rework|regroom'."
            ),
        }
    work_item_ref = action_id.removeprefix("impl:")
    resolved_runner = _SubprocessRunner() if runner is None else runner
    resolved_dispatcher = _resolve_dispatcher_bin(dispatcher_bin)
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
    action, item_id, reject_kind = parsed
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
        return _approve_item(repo=repo, config=config, items=items, item=item, action_id=action_id)
    if action == "accept":
        return _accept_item(config=config, item=item, action_id=action_id)
    return _reject_item(
        repo=repo,
        config=config,
        item=item,
        action_id=action_id,
        reject_kind=cast("str", reject_kind),
        runner=runner,
    )


def _is_human_valve_action(*, action_id: str) -> bool:
    return action_id.startswith(("approve:", "accept:", "reject:"))


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
    return None


def _find_item(*, items: list[WorkItem], item_id: str) -> WorkItem | None:
    for item in items:
        if item.id == item_id:
            return item
    return None


def _approve_item(
    *,
    repo: Path,
    config: StoreConfig,
    items: list[WorkItem],
    item: WorkItem,
    action_id: str,
) -> dict[str, Any]:
    if item.status != "ready":
        return _invalid_source_state(action_id=action_id, item=item, expected="ready")
    if effective_admission_policy(item=item) != "manual":
        return _valve_refusal(
            action_id=action_id,
            work_item_id=item.id,
            domain_error="invalid-source-state",
            summary="approve requires an effective-manual ready item.",
        )
    active_count = sum(1 for candidate in items if candidate.status == "active")
    wip_cap = resolve_wip_cap(cwd=repo)
    if active_count >= wip_cap:
        return _valve_refusal(
            action_id=action_id,
            work_item_id=item.id,
            domain_error="wip-cap-exhausted",
            summary=f"approve refused: active WIP {active_count} has reached cap {wip_cap}.",
        )
    assignee = resolve_assignee(item=item)
    if assignee is None:
        return _valve_refusal(
            action_id=action_id,
            work_item_id=item.id,
            domain_error="unresolvable-assignee",
            summary="approve refused: work-item assignee could not be resolved.",
        )
    update_work_item_status(path=config, item_id=item.id, status="active", assignee=assignee)
    return _valve_success(
        action_id=action_id,
        work_item_id=item.id,
        stage="human-valve-approve",
        target_status="active",
        assignee=assignee,
        summary=f"Approved {item.id}: ready -> active.",
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


def main(argv: list[str] | None = None, *, runner: CommandRunner | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    repo = _resolve_repo(repo_arg=getattr(args, "repo", None))
    if not repo.exists():
        _ = sys.stderr.write(f"ERROR: --repo does not exist: {repo}\n")
        return _EXIT_PRECONDITION_ERROR
    # Bare `orchestrate` (no subcommand) presents the read-only plan as the
    # walkthrough entry point; the interactive select -> run loop lives in the
    # skill/harness layer over this CLI, not in the CLI itself.
    if args.subcommand in {None, "plan"}:
        plan = plan_actions(repo=repo, runner=runner)
        _emit_payload(payload=plan, as_json=bool(getattr(args, "as_json", False)))
        return 0
    result = run_action(repo=repo, action_id=str(args.action), runner=runner)
    _emit_payload(payload=result, as_json=bool(args.as_json))
    return 0 if result["status"] in {"green", "human-gated"} else _EXIT_FAILURE


def _resolve_repo(*, repo_arg: str | None) -> Path:
    """Resolve the target repo: the cwd when `--repo` is omitted, else the path."""
    if repo_arg is None:
        return Path.cwd()
    return Path(repo_arg)


@dataclass(frozen=True, kw_only=True)
class _NextResult:
    candidates: list[dict[str, Any]]
    source: dict[str, Any]


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
    parser = argparse.ArgumentParser(prog="orchestrate")
    subparsers = parser.add_subparsers(dest="subcommand", required=False)
    plan = subparsers.add_parser("plan")
    _ = plan.add_argument("--repo", dest="repo", required=False, default=None)
    _ = plan.add_argument("--json", dest="as_json", action="store_true")
    run = subparsers.add_parser("run")
    _ = run.add_argument("--repo", dest="repo", required=False, default=None)
    _ = run.add_argument("--action", dest="action", required=True)
    _ = run.add_argument("--json", dest="as_json", action="store_true")
    return parser


def _load_next(
    *,
    argv: tuple[str, ...],
    runner: CommandRunner,
    repo: Path,
) -> _NextResult:
    result = runner(argv=argv, cwd=repo)
    source: dict[str, Any] = {
        "argv": list(argv),
        "exit_code": result.returncode,
    }
    if result.returncode != 0:
        source["status"] = "failed"
        source["stderr"] = result.stderr
        return _NextResult(candidates=[], source=source)
    parsed = _parse_json_object_or_array(text=result.stdout)
    if not isinstance(parsed, dict):
        source["status"] = "failed"
        source["stderr"] = "next output was not a JSON object"
        return _NextResult(candidates=[], source=source)
    parsed_dict = cast("dict[str, object]", parsed)
    candidates_raw = parsed_dict.get("candidates", [])
    if not isinstance(candidates_raw, list):
        source["status"] = "failed"
        source["stderr"] = "next output did not include candidates[]"
        return _NextResult(candidates=[], source=source)
    source["status"] = "ok"
    candidates = cast("list[object]", candidates_raw)
    source["candidate_count"] = len(candidates)
    return _NextResult(
        candidates=[
            cast("dict[str, Any]", candidate)
            for candidate in candidates
            if isinstance(candidate, dict)
        ],
        source=source,
    )


def _spec_action(*, candidate: dict[str, Any], index: int) -> dict[str, Any]:
    action = str(candidate.get("action", "next"))
    return {
        "id": f"spec:{action}:{index}",
        "kind": "spec",
        "action": action,
        "urgency": str(candidate.get("urgency", "medium")),
        "reason": str(candidate.get("reason", "spec-side candidate")),
        "target": candidate.get("target"),
        "handoff": _spec_handoff(action=action),
        "factory_safe": False,
    }


def _impl_action(*, candidate: dict[str, Any]) -> dict[str, Any]:
    work_item_ref = str(candidate.get("work_item_ref", ""))
    return {
        "id": f"impl:{work_item_ref}",
        "kind": "impl",
        "action": "dispatch",
        "work_item_ref": work_item_ref,
        "urgency": str(candidate.get("urgency", "medium")),
        "reason": str(candidate.get("reason", "ready impl work-item")),
        "factory_safe": True,
    }


def _spec_handoff(*, action: str) -> str:
    command = action if action in {"critique", "next", "propose-change", "revise"} else "next"
    return f"/livespec:{command} --spec-target SPECIFICATION/"


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


def _action_id_part(*, action_id: str, index: int, default: str) -> str:
    parts = action_id.split(":")
    if len(parts) > index and parts[index]:
        return parts[index]
    return default


def _emit_payload(*, payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        _ = sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return
    _ = sys.stdout.write(_human_summary(payload=payload) + "\n")


def _human_summary(*, payload: dict[str, Any]) -> str:
    """Render a payload as human-readable Markdown.

    A `plan` payload (carries `actions`) renders the selectable action
    records; any other payload is a `run` dispatch/handoff envelope.
    """
    if "actions" in payload:
        return _plan_markdown(payload=payload)
    return _run_markdown(payload=payload)


def _plan_markdown(*, payload: dict[str, Any]) -> str:
    lines = [f"# orchestrate plan — {payload.get('repo', 'current repo')}", ""]
    actions = cast("list[dict[str, Any]]", payload["actions"])
    if not actions:
        lines.append("No actions ready.")
        return "\n".join(lines)
    lines.extend(_plan_action_lines(action=action) for action in actions)
    return "\n".join(lines)


def _plan_action_lines(*, action: dict[str, Any]) -> str:
    action_id = str(action.get("id", "unknown"))
    urgency = str(action.get("urgency", "medium"))
    reason = str(action.get("reason", ""))
    head = f"- **{action_id}** ({urgency}) — {reason}"
    detail = (
        f"`{action['handoff']}`"
        if action.get("kind") == "spec" and action.get("handoff")
        else f"dispatch `{action.get('work_item_ref', '')}` (factory-safe)"
    )
    return f"{head}\n  - {detail}"


def _run_markdown(*, payload: dict[str, Any]) -> str:
    action_id = str(payload.get("action_id", "unknown"))
    status = str(payload.get("status", "unknown"))
    lines = [f"# orchestrate run — {action_id}", "", f"- status: **{status}**"]
    handoff = payload.get("handoff")
    if handoff:
        lines.append(f"- handoff: `{handoff}`")
    dispatcher = payload.get("dispatcher")
    if isinstance(dispatcher, dict):
        dispatcher_dict = cast("dict[str, Any]", dispatcher)
        lines.append(f"- dispatcher exit code: {dispatcher_dict.get('exit_code')}")
    lines.append(f"- {payload.get('summary', '')}")
    return "\n".join(lines)


def _spec_next_argv(*, repo: Path, spec_next_bin: Path) -> tuple[str, ...]:
    return (
        "python3",
        str(spec_next_bin),
        "--project-root",
        str(repo),
        "--spec-target",
        str(repo / "SPECIFICATION"),
    )


def _impl_next_argv(*, repo: Path, impl_next_bin: Path) -> tuple[str, ...]:
    return (
        "python3",
        str(impl_next_bin),
        "--project-root",
        str(repo),
        "--json",
    )


def _resolve_spec_next_bin(spec_next_bin: Path | None) -> Path:
    if spec_next_bin is not None:
        return spec_next_bin
    env_value = os.environ.get(_SPEC_NEXT_BIN_ENV)
    if env_value:
        return Path(env_value)
    return Path("/data/projects/livespec/.claude-plugin/scripts/bin/next.py")


def _resolve_impl_next_bin(impl_next_bin: Path | None) -> Path:
    if impl_next_bin is not None:
        return impl_next_bin
    return _scripts_root() / "bin" / "next.py"


def _resolve_dispatcher_bin(dispatcher_bin: Path | None) -> Path:
    if dispatcher_bin is not None:
        return dispatcher_bin
    return _scripts_root() / "bin" / "dispatcher.py"


def _scripts_root() -> Path:
    return Path(__file__).resolve().parents[2]
