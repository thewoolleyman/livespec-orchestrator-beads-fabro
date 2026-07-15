"""Guarded host Codex credential refresh command."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_refresh import (
    CODEX_ALARM_THRESHOLD_SECONDS,
    CODEX_REFRESH_GUARD_SECONDS,
    HostCodexCredentialStatus,
    assess_host_codex_credential,
    classify_refresh_outcome,
    should_invoke_codex_refresh,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = [
    "run_codex_cred_refresh_with",
]

_CODEX_REFRESH_ARGV = ["codex", "exec", "reply OK"]
_CODEX_REFRESH_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True, kw_only=True)
class _RefreshPayloadInput:
    before: HostCodexCredentialStatus
    after: HostCodexCredentialStatus
    codex_exit_code: int | None
    codex_stderr: str
    dry_run: bool
    invoked_codex: bool
    outcome: str


def run_codex_cred_refresh_with(
    *,
    args: argparse.Namespace,
    cwd: Callable[[], Path],
    now_epoch: Callable[[], int],
    read_host_codex_auth: Callable[[], str | None],
    runner_factory: Callable[[], CommandRunner],
) -> int:
    """Guardedly invoke Codex so the host-owned credential refreshes itself."""
    before = _assess_host_codex_credential(
        now_epoch=now_epoch,
        read_host_codex_auth=read_host_codex_auth,
    )
    invoked_codex = False
    codex_exit_code: int | None = None
    codex_stderr = ""
    after = before
    if should_invoke_codex_refresh(status=before) and not args.dry_run:
        invoked_codex = True
        result = runner_factory().run(
            argv=_CODEX_REFRESH_ARGV,
            cwd=cwd(),
            timeout_seconds=_CODEX_REFRESH_TIMEOUT_SECONDS,
        )
        codex_exit_code = result.exit_code
        codex_stderr = result.stderr
        after = _assess_host_codex_credential(
            now_epoch=now_epoch,
            read_host_codex_auth=read_host_codex_auth,
        )
    outcome = classify_refresh_outcome(
        before=before,
        after=after,
        codex_ok=codex_exit_code in (None, 0),
    )
    payload = _codex_cred_refresh_payload(
        refresh=_RefreshPayloadInput(
            before=before,
            after=after,
            codex_exit_code=codex_exit_code,
            codex_stderr=codex_stderr,
            dry_run=args.dry_run,
            invoked_codex=invoked_codex,
            outcome=outcome,
        )
    )

    if args.as_json:
        _ = write_stdout(text=json.dumps(payload, indent=2, sort_keys=True) + "\n")
    else:
        _ = write_stdout(text=_codex_cred_refresh_human(payload=payload))
    if args.dry_run or outcome in ("noop-not-due", "refreshed"):
        return 0
    return 1


def _assess_host_codex_credential(
    *,
    now_epoch: Callable[[], int],
    read_host_codex_auth: Callable[[], str | None],
) -> HostCodexCredentialStatus:
    return assess_host_codex_credential(
        source_auth_json=read_host_codex_auth(),
        now_epoch=now_epoch(),
        alarm_threshold_seconds=CODEX_ALARM_THRESHOLD_SECONDS,
        refresh_guard_seconds=CODEX_REFRESH_GUARD_SECONDS,
    )


def _codex_cred_status_payload(*, status: HostCodexCredentialStatus) -> dict[str, Any]:
    expires_at_iso = (
        None
        if status.expires_at_epoch is None
        else datetime.fromtimestamp(status.expires_at_epoch, tz=timezone.utc).isoformat()
    )
    remaining_days = None if status.remaining_seconds is None else status.remaining_seconds / 86_400
    return {
        "alarm": status.alarm,
        "expires_at_epoch": status.expires_at_epoch,
        "expires_at_iso": expires_at_iso,
        "malformed": status.malformed,
        "message": status.message,
        "present": status.present,
        "refresh_due": status.refresh_due,
        "remaining_days": remaining_days,
        "remaining_seconds": status.remaining_seconds,
    }


def _codex_cred_refresh_payload(*, refresh: _RefreshPayloadInput) -> dict[str, Any]:
    return {
        "after": _codex_cred_status_payload(status=refresh.after),
        "before": _codex_cred_status_payload(status=refresh.before),
        "codex_exit_code": refresh.codex_exit_code,
        "dry_run": refresh.dry_run,
        "invoked_codex": refresh.invoked_codex,
        "message": _codex_cred_refresh_message(
            codex_stderr=refresh.codex_stderr,
            dry_run=refresh.dry_run,
            outcome=refresh.outcome,
        ),
        "outcome": refresh.outcome,
    }


def _codex_cred_refresh_message(*, codex_stderr: str, dry_run: bool, outcome: str) -> str:
    if outcome == "noop-not-due":
        return "Host Codex credential is not inside the refresh guard; codex was not invoked."
    if outcome == "refreshed":
        return "Host Codex credential refresh confirmed; access-token expiry advanced."
    if outcome == "codex-error":
        detail = codex_stderr.strip() or "no stderr"
        return f"codex exec failed while refreshing the host Codex credential: {detail}"
    if dry_run:
        return "Dry run: host Codex credential is refresh-due; codex was not invoked."
    return (
        "Host Codex credential is still stale after codex exec; run `codex login` "
        "on the orchestrator host if this persists."
    )


def _codex_cred_refresh_human(*, payload: dict[str, Any]) -> str:
    before_remaining = payload["before"]["remaining_seconds"]
    after_remaining = payload["after"]["remaining_seconds"]
    return "\n".join(
        (
            f"outcome: {payload['outcome']}",
            f"dry_run: {_human_bool(value=payload['dry_run'])}",
            f"invoked_codex: {_human_bool(value=payload['invoked_codex'])}",
            f"codex_exit_code: {_human_optional(value=payload['codex_exit_code'])}",
            f"before_remaining_seconds: {_human_optional(value=before_remaining)}",
            f"after_remaining_seconds: {_human_optional(value=after_remaining)}",
            f"message: {payload['message']}",
            "",
        )
    )


def _human_bool(*, value: object) -> str:
    return "true" if value is True else "false"


def _human_optional(*, value: object) -> str:
    return "null" if value is None else str(value)
