from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from livespec_runtime.github_auth.config import load_github_app_config
from livespec_runtime.github_auth.errors import GithubAppAuthError
from livespec_runtime.github_auth.provider import InstallationTokenProvider

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
    NotifyEvent,
    NotifyPoster,
    notify_terminal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_self_update_decision import (
    DISPATCHER_SCRIPT_PREFIXES,
    SELF_UPDATE_BREACH_CLASS,
    CanaryVerdict,
    PromotionDecision,
    canary_self_check_argv,
    canary_verdict,
    is_self_merge,
    parse_pr_files,
    pr_files_argv,
    promotion_decision,
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

_CANARY_TIMEOUT_SECONDS = 300.0


class SelfUpdateJournal(Protocol):
    def append(self, *, record: dict[str, object]) -> None: ...


def github_token_supplier() -> Callable[[], str] | str:
    try:
        config = load_github_app_config(environ=os.environ)
    except GithubAppAuthError as error:
        return f"C-mode dispatch refused: {error.detail}"
    return InstallationTokenProvider(config=config).token


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
    from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import resolve_merged_paths

    resolved_runner = post_verdict_runner(runner=runner, token_supplier=token_supplier)
    resolved_poster = poster if poster is not None else HttpNotifyPoster()
    for outcome in outcomes:
        if outcome.status != "green" or outcome.pr_number is None:
            continue
        merged_paths = resolve_merged_paths(repo=repo, runner=resolved_runner)
        self_update_after_merge(
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
    from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import plugin_root

    return plugin_root() / "scripts" / "bin" / "dispatcher.py"


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
    try:
        _self_update(
            work_item_id=work_item_id,
            merged_paths=merged_paths,
            candidate_bin=candidate_bin,
            scratch_root=scratch_root,
            repo=repo,
            journal=journal,
            runner=runner if runner is not None else ShellCommandRunner(),
            poster=poster if poster is not None else HttpNotifyPoster(),
        )
    except Exception as exc:
        journal.append(
            record={
                "stage": "self-update-error",
                "reason": f"{type(exc).__name__}",
            }
        )


def _self_update(  # noqa: PLR0913 - kw-only fail-open stage body; fields are caller inputs.
    *,
    work_item_id: str,
    merged_paths: tuple[str, ...],
    candidate_bin: str,
    scratch_root: str,
    repo: Path,
    journal: SelfUpdateJournal,
    runner: CommandRunner,
    poster: NotifyPoster,
) -> None:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
        is_writable_orchestrator_checkout,
        plugin_root,
    )

    if not is_writable_orchestrator_checkout(root=plugin_root(), runner=runner):
        journal.append(
            record={
                "stage": "self-update-skipped",
                "work_item_id": work_item_id,
                "reason": "no writable orchestrator checkout to promote (read-only plugin cache)",
            }
        )
        return
    if not is_self_merge(merged_paths=merged_paths):
        journal.append(
            record={
                "stage": "self-update-skipped",
                "work_item_id": work_item_id,
                "reason": "merge did not touch the dispatcher's own scripts",
            }
        )
        return
    canary = runner.run(
        argv=canary_self_check_argv(candidate_bin=candidate_bin, scratch_root=scratch_root),
        cwd=repo,
        timeout_seconds=_CANARY_TIMEOUT_SECONDS,
    )
    decision = promotion_decision(verdict=canary_verdict(exit_code=canary.exit_code))
    stage = "self-update-promoted" if decision.promote else "self-update-kept-last-known-good"
    journal.append(
        record={
            "stage": stage,
            "work_item_id": work_item_id,
            "reason": decision.reason,
        }
    )
    if not decision.alarm:
        return
    notify_terminal(
        events=(NotifyEvent(work_item_id=work_item_id, outcome_class=SELF_UPDATE_BREACH_CLASS),),
        run_id=run_id(),
        poster=poster,
        journal=journal,
    )


def run_id() -> str:
    return uuid.uuid4().hex
