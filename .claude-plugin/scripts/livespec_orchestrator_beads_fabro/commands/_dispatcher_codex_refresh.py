"""Pure Codex host-credential status assessment."""

from __future__ import annotations

import json
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_projection import (
    decode_codex_access_token_exp,
)

__all__: list[str] = [
    "CODEX_ALARM_THRESHOLD_SECONDS",
    "CODEX_REFRESH_GUARD_SECONDS",
    "HostCodexCredentialStatus",
    "assess_host_codex_credential",
]

CODEX_ALARM_THRESHOLD_SECONDS = 172_800
CODEX_REFRESH_GUARD_SECONDS = 360


@dataclass(frozen=True, kw_only=True)
class HostCodexCredentialStatus:
    """Status of the host-owned Codex credential."""

    present: bool
    malformed: bool
    expires_at_epoch: int | None
    remaining_seconds: int | None
    alarm: bool
    refresh_due: bool
    message: str


def assess_host_codex_credential(
    *,
    source_auth_json: str | None,
    now_epoch: int,
    alarm_threshold_seconds: int,
    refresh_guard_seconds: int,
) -> HostCodexCredentialStatus:
    """Assess whether the host Codex credential needs operator attention."""
    if source_auth_json is None:
        return HostCodexCredentialStatus(
            present=False,
            malformed=False,
            expires_at_epoch=None,
            remaining_seconds=None,
            alarm=True,
            refresh_due=False,
            message=(
                "No host Codex credential found; run `codex login` on the " "orchestrator host."
            ),
        )
    try:
        expires_at = decode_codex_access_token_exp(source_auth_json=source_auth_json)
    except (ValueError, json.JSONDecodeError):
        return HostCodexCredentialStatus(
            present=True,
            malformed=True,
            expires_at_epoch=None,
            remaining_seconds=None,
            alarm=True,
            refresh_due=False,
            message=(
                "Host Codex auth.json is present but unparseable; run "
                "`codex login` on the orchestrator host."
            ),
        )
    remaining = expires_at - now_epoch
    return HostCodexCredentialStatus(
        present=True,
        malformed=False,
        expires_at_epoch=expires_at,
        remaining_seconds=remaining,
        alarm=remaining < alarm_threshold_seconds,
        refresh_due=remaining < refresh_guard_seconds,
        message=f"Host Codex credential expires in {remaining} seconds.",
    )
