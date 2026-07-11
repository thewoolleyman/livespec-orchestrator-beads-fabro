"""Side-effecting staged self-update gate for the Dispatcher."""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from livespec_runtime.github_auth.config import load_github_app_config
from livespec_runtime.github_auth.errors import GithubAppAuthError
from livespec_runtime.github_auth.provider import InstallationTokenProvider

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_notify import (
    HttpNotifyPoster,
    NotifyEvent,
    NotifyPoster,
    notify_terminal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_self_update import (
    SELF_UPDATE_BREACH_CLASS,
    canary_self_check_argv,
    canary_verdict,
    is_self_merge,
    promotion_decision,
)

__all__: list[str] = [
    "candidate_dispatcher_bin",
    "github_token_supplier",
    "run_id",
    "self_update_after_merge",
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
