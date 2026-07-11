from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Final, Protocol, cast

from livespec_runtime.github_auth.errors import GithubAppAuthError

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    GithubTokenEnvRunner,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_notify import (
    HttpNotifyPoster,
    NotifyPoster,
)

__all__: list[str] = [
    "DISPATCHER_SCRIPT_PREFIXES",
    "SELF_UPDATE_BREACH_CLASS",
    "CanaryVerdict",
    "PromotionDecision",
    "canary_self_check_argv",
    "canary_verdict",
    "candidate_dispatcher_bin",
    "github_token_supplier",
    "is_self_merge",
    "parse_pr_files",
    "post_verdict_runner",
    "pr_files_argv",
    "promotion_decision",
    "run_id",
    "self_update_after_merge",
    "self_update_after_verdict",
]

DISPATCHER_SCRIPT_PREFIXES: tuple[str, ...] = (
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/",
    ".claude-plugin/scripts/bin/",
    ".claude-plugin/scripts/_bootstrap.py",
)

_DISPATCHER_SCRIPT_PATTERNS: tuple[str, ...] = (
    "commands/_dispatcher_*.py",
    "commands/dispatcher.py",
    "dispatcher.py",
)

SELF_UPDATE_BREACH_CLASS = "self-update-canary-failed"


@dataclass(frozen=True, kw_only=True, slots=True)
class CanaryVerdictValue:
    value: str


class CanaryVerdict:
    PASS: Final = CanaryVerdictValue(value="pass")
    FAIL: Final = CanaryVerdictValue(value="fail")


@dataclass(frozen=True, kw_only=True)
class PromotionDecision:
    promote: bool
    alarm: bool
    reason: str


def pr_files_argv(*, branch: str) -> list[str]:
    return ["gh", "pr", "view", branch, "--json", "files"]


def parse_pr_files(*, stdout: str) -> tuple[str, ...]:
    try:
        parsed_raw: object = json.loads(stdout)
    except json.JSONDecodeError:
        return ()
    if not isinstance(parsed_raw, dict):
        return ()
    files_raw: object = cast("dict[str, Any]", parsed_raw).get("files")
    if not isinstance(files_raw, list):
        return ()
    return tuple(
        path_raw
        for entry in cast("list[object]", files_raw)
        if isinstance(entry, dict)
        for path_raw in (cast("dict[str, Any]", entry).get("path"),)
        if isinstance(path_raw, str) and path_raw != ""
    )


def is_self_merge(*, merged_paths: tuple[str, ...]) -> bool:
    return any(_path_is_dispatcher_code(path=path) for path in merged_paths)


def _path_is_dispatcher_code(*, path: str) -> bool:
    normalized = path.strip()
    if normalized == "":
        return False
    for prefix in DISPATCHER_SCRIPT_PREFIXES:
        if prefix.endswith("/"):
            if normalized.startswith(prefix):
                return True
        elif normalized == prefix:
            return True
    return any(fnmatchcase(normalized, pattern) for pattern in _DISPATCHER_SCRIPT_PATTERNS)


def canary_self_check_argv(*, candidate_bin: str, scratch_root: str) -> list[str]:
    return [
        "python3",
        candidate_bin,
        "ledger-check",
        "--project-root",
        scratch_root,
        "--json",
    ]


def canary_verdict(*, exit_code: int) -> CanaryVerdictValue:
    return CanaryVerdict.PASS if exit_code == 0 else CanaryVerdict.FAIL


def promotion_decision(*, verdict: CanaryVerdictValue) -> PromotionDecision:
    if verdict is CanaryVerdict.PASS:
        return PromotionDecision(
            promote=True,
            alarm=False,
            reason="canary passed; promoting staged self-update to the active pinned copy",
        )
    return PromotionDecision(
        promote=False,
        alarm=True,
        reason=(
            "canary FAILED; keeping the last-known-good pinned copy and alarming "
            "(the staged self-update is NOT promoted)"
        ),
    )


class SelfUpdateJournal(Protocol):
    def append(self, *, record: dict[str, object]) -> None: ...


def github_token_supplier() -> Callable[[], str] | str:
    from livespec_orchestrator_beads_fabro.commands import _dispatcher_self_update_stage

    return _dispatcher_self_update_stage.github_token_supplier()


def _github_token_error_supplier(*, detail: str) -> Callable[[], str]:
    def _raise_github_token_error() -> str:
        raise GithubAppAuthError(detail=detail)

    return _raise_github_token_error


def post_verdict_runner(
    *,
    runner: CommandRunner | None,
    token_supplier: Callable[[], str] | None = None,
) -> CommandRunner:
    resolved_runner: CommandRunner = runner if runner is not None else ShellCommandRunner()
    resolved_supplier = token_supplier
    if resolved_supplier is None and runner is None:
        supplier_or_error = github_token_supplier()
        resolved_supplier = (
            _github_token_error_supplier(detail=supplier_or_error)
            if isinstance(supplier_or_error, str)
            else supplier_or_error
        )
    if resolved_supplier is None:
        return resolved_runner
    return GithubTokenEnvRunner(inner=resolved_runner, token=resolved_supplier)


def self_update_after_verdict(
    *,
    repo: Path,
    outcomes: list[DispatchOutcome],
    journal: SelfUpdateJournal,
    runner: CommandRunner | None = None,
    token_supplier: Callable[[], str] | None = None,
    poster: NotifyPoster | None = None,
) -> None:
    from livespec_orchestrator_beads_fabro.commands import _dispatcher_self_update_stage
    from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import resolve_merged_paths

    resolved_runner = post_verdict_runner(runner=runner, token_supplier=token_supplier)
    resolved_poster = poster if poster is not None else HttpNotifyPoster()
    for outcome in outcomes:
        if outcome.status != "green" or outcome.pr_number is None:
            continue
        merged_paths = resolve_merged_paths(repo=repo, runner=resolved_runner)
        _dispatcher_self_update_stage.self_update_after_merge(
            work_item_id=outcome.work_item_id,
            merged_paths=merged_paths,
            candidate_bin=str(candidate_dispatcher_bin()),
            scratch_root=tempfile.mkdtemp(prefix=f"self-update-canary-{outcome.work_item_id}-"),
            repo=repo,
            journal=journal,
            runner=resolved_runner,
            poster=resolved_poster,
        )


def candidate_dispatcher_bin() -> Path:
    from livespec_orchestrator_beads_fabro.commands import _dispatcher_self_update_stage

    return _dispatcher_self_update_stage.candidate_dispatcher_bin()


def self_update_after_merge(  # noqa: PLR0913 - kw-only fail-open stage; fields are caller inputs.
    *,
    work_item_id: str,
    merged_paths: tuple[str, ...],
    candidate_bin: str,
    scratch_root: str,
    repo: Path,
    journal: SelfUpdateJournal,
    runner: CommandRunner | None = None,
    poster: NotifyPoster | None = None,
) -> None:
    from livespec_orchestrator_beads_fabro.commands import _dispatcher_self_update_stage

    _dispatcher_self_update_stage.self_update_after_merge(
        work_item_id=work_item_id,
        merged_paths=merged_paths,
        candidate_bin=candidate_bin,
        scratch_root=scratch_root,
        repo=repo,
        journal=journal,
        runner=runner,
        poster=poster,
    )


def run_id() -> str:
    from livespec_orchestrator_beads_fabro.commands import _dispatcher_self_update_stage

    return _dispatcher_self_update_stage.run_id()
