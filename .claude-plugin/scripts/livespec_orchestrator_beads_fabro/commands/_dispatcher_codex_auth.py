"""Codex credential projection for the Dispatcher."""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_refresh import (
    CODEX_ALARM_THRESHOLD_SECONDS,
    CODEX_REFRESH_GUARD_SECONDS,
    HostCodexCredentialStatus,
    assess_host_codex_credential,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    CODEX_FRESHNESS_RUN_BUDGET_SECONDS,
    assess_codex_credential_freshness,
    project_codex_auth_snapshot,
)
from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = [
    "CodexProjectionRefusal",
    "project_codex_auth",
    "read_host_codex_auth",
    "run_codex_cred_status",
]

# Host-side override for where the live Codex `auth.json` lives. The host
# is the sole `codex login`+refresh owner; the Dispatcher reads its
# auth.json directly (default `~/.codex/auth.json`) and projects a
# non-rotatable snapshot into the sandbox. An env-var NAME, not a secret.
_CODEX_HOME_ENV = "CODEX_HOME"


def read_host_codex_auth() -> str | None:
    """Read the host's Codex `auth.json` text (the projection SOURCE).

    DIRECT host-file read — the host is the sole `codex login`+refresh
    owner; the sandbox never touches the live credential. Honors a
    host-side `CODEX_HOME` override (default `~/.codex`). Returns the raw
    text, or None when the file is missing/unreadable (any `OSError`), so
    the caller renders an actionable refusal naming `codex login`.
    """
    home = os.environ.get(_CODEX_HOME_ENV) or str(Path.home() / ".codex")
    try:
        return (Path(home) / "auth.json").read_text(encoding="utf-8")
    except OSError:
        return None


@dataclass(frozen=True, kw_only=True)
class CodexProjectionRefusal:
    """A dual-credential-projection refusal routed as data (missing/stale)."""

    message: str


def project_codex_auth(*, now_epoch: int) -> str | CodexProjectionRefusal:
    """Project the host Codex credential into the dispatch sandbox snapshot.

    Returns the non-rotatable `auth.json` snapshot string on success
    (scenarios.md Scenario 18), or a `_CodexProjectionRefusal` carrying an
    actionable message when the host credential is absent (Scenario 18
    precondition) or too short-lived for the run budget plus margin
    (Scenario 19). `now_epoch` is injected so the freshness gate stays
    deterministically testable. The refusal is a distinct type so a
    snapshot that happens to look like a message is never mistaken for one.
    """
    source_auth_json = read_host_codex_auth()
    if source_auth_json is None:
        return CodexProjectionRefusal(
            message=(
                "C-mode dispatch refused: no host Codex credential found at "
                f"${_CODEX_HOME_ENV}/auth.json (default ~/.codex/auth.json). "
                "The Dispatcher projects a non-rotatable snapshot of the "
                "host credential into the sandbox; run `codex login` on the "
                "orchestrator host before dispatch."
            )
        )
    verdict = assess_codex_credential_freshness(
        source_auth_json=source_auth_json,
        now_epoch=now_epoch,
        run_budget_seconds=CODEX_FRESHNESS_RUN_BUDGET_SECONDS,
    )
    if not verdict.fresh_enough:
        return CodexProjectionRefusal(
            message=verdict.renewal_message
            or "C-mode dispatch refused: host Codex credential requires renewal."
        )
    return project_codex_auth_snapshot(source_auth_json=source_auth_json)


def run_codex_cred_status(*, args: argparse.Namespace) -> int:
    """Emit host Codex credential lifetime status for operators."""
    status = assess_host_codex_credential(
        source_auth_json=read_host_codex_auth(),
        now_epoch=int(time.time()),
        alarm_threshold_seconds=CODEX_ALARM_THRESHOLD_SECONDS,
        refresh_guard_seconds=CODEX_REFRESH_GUARD_SECONDS,
    )
    payload = _codex_cred_status_payload(status=status)
    if args.as_json:
        _ = write_stdout(text=json.dumps(payload, indent=2, sort_keys=True) + "\n")
    else:
        _ = write_stdout(text=_codex_cred_status_human(payload=payload))
    return 1 if status.alarm else 0


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


def _codex_cred_status_human(*, payload: dict[str, Any]) -> str:
    return "\n".join(
        (
            f"present: {_human_bool(value=payload['present'])}",
            f"malformed: {_human_bool(value=payload['malformed'])}",
            f"expires_at_epoch: {_human_optional(value=payload['expires_at_epoch'])}",
            f"expires_at_iso: {_human_optional(value=payload['expires_at_iso'])}",
            f"remaining_seconds: {_human_optional(value=payload['remaining_seconds'])}",
            f"remaining_days: {_human_optional(value=payload['remaining_days'])}",
            f"alarm: {_human_bool(value=payload['alarm'])}",
            f"refresh_due: {_human_bool(value=payload['refresh_due'])}",
            f"message: {payload['message']}",
            "",
        )
    )


def _human_bool(*, value: object) -> str:
    return "true" if value is True else "false"


def _human_optional(*, value: object) -> str:
    return "null" if value is None else str(value)
