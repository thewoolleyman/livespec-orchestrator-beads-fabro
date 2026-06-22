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

__all__: list[str] = [
    "CommandRun",
    "build_dispatcher_argv",
    "main",
    "plan_actions",
    "run_action",
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
    if not action_id.startswith("impl:"):
        return {
            "action_id": action_id,
            "kind": "unknown",
            "status": "failed",
            "summary": "Unsupported action id; expected 'impl:<id>' or 'spec:<action>:<index>'.",
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
    repo = Path(args.repo)
    if not repo.exists():
        _ = sys.stderr.write(f"ERROR: --repo does not exist: {repo}\n")
        return _EXIT_PRECONDITION_ERROR
    if args.subcommand == "plan":
        plan = plan_actions(repo=repo, runner=runner)
        _emit_payload(payload=plan, as_json=bool(args.as_json))
        return 0
    if args.subcommand == "run":
        result = run_action(repo=repo, action_id=str(args.action), runner=runner)
        _emit_payload(payload=result, as_json=bool(args.as_json))
        return 0 if result["status"] in {"green", "human-gated"} else _EXIT_FAILURE
    return _EXIT_USAGE_ERROR  # pragma: no cover - argparse requires a known subcommand.


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
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    plan = subparsers.add_parser("plan")
    _ = plan.add_argument("--repo", dest="repo", required=True)
    _ = plan.add_argument("--json", dest="as_json", action="store_true")
    run = subparsers.add_parser("run")
    _ = run.add_argument("--repo", dest="repo", required=True)
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
    if "actions" in payload:
        actions_raw = payload["actions"]
        if isinstance(actions_raw, list) and actions_raw:
            actions = cast("list[object]", actions_raw)
            return "\n".join(
                _action_summary_id(action=cast("dict[object, object]", action))
                for action in actions
                if isinstance(action, dict)
            )
        return "No actions ready."
    return str(payload.get("summary", payload))


def _action_summary_id(*, action: dict[object, object]) -> str:
    action_dict = cast("dict[str, object]", action)
    return str(action_dict.get("id", "unknown"))


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
