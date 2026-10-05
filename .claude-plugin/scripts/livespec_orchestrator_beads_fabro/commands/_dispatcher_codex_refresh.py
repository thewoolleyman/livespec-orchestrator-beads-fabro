"""Pure Codex host-credential status assessment."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from livespec_orchestrator_beads_fabro.commands._dispatcher_projection import (
    CODEX_FRESHNESS_RUN_BUDGET_SECONDS,
    codex_freshness_required_seconds,
    decode_codex_access_token_exp,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "CODEX_ALARM_THRESHOLD_SECONDS",
    "CODEX_REFRESH_GUARD_SECONDS",
    "HostCodexCredentialStatus",
    "assess_host_codex_credential",
    "classify_refresh_outcome",
    "should_invoke_codex_refresh",
]

CODEX_ALARM_THRESHOLD_SECONDS = 172_800

# DERIVED from the dispatch freshness requirement, never written as its own
# number. The two diverging IS the dead zone: the guard was 360 seconds — sized
# to Codex's own five-minute proactive-refresh window, because the refresher
# then spent a `codex exec` that could not refresh outside it — while the
# freshness gate demanded 18000. Every lifetime between them refused dispatch
# while this guard reported "not due", so the sanctioned refresh declined to
# act and the refusal told a human to run `codex login`. Measured 2026-10-04 at
# remaining_seconds 13517.
#
# Deriving it makes that interval empty by construction. The companion half of
# the fix is that the renewal now drives the UNGATED app-server `account/read`
# request (`_dispatcher_codex_early_renewal`) instead of the window-gated
# `codex exec`: widening eligibility over a refresher that still cannot act
# would only convert a refusal into an attempt that declines.
CODEX_REFRESH_GUARD_SECONDS = codex_freshness_required_seconds(
    run_budget_seconds=CODEX_FRESHNESS_RUN_BUDGET_SECONDS
)


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


_RefreshOutcome = Literal["noop-not-due", "refreshed", "codex-error", "still-stale"]


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
    expires_at = attempt(
        action=lambda: decode_codex_access_token_exp(source_auth_json=source_auth_json),
        exceptions=(ValueError, json.JSONDecodeError),
    )
    if isinstance(expires_at, AttemptFailure):
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
        # Remaining AND required, so the shortfall is readable off the message
        # instead of computed by whoever is reading it at 3am.
        message=(
            f"Host Codex credential expires in {remaining} seconds; renewal is "
            f"due below {refresh_guard_seconds} seconds, which is the dispatch "
            "freshness requirement."
        ),
    )


def should_invoke_codex_refresh(*, status: HostCodexCredentialStatus) -> bool:
    """Return whether the guarded refresher should spend a Codex request."""
    return status.present and not status.malformed and status.refresh_due


def classify_refresh_outcome(
    *,
    before: HostCodexCredentialStatus,
    after: HostCodexCredentialStatus,
    codex_ok: bool,
) -> _RefreshOutcome:
    """Classify one guarded Codex refresh attempt from credential status only."""
    if not before.present or before.malformed:
        return "still-stale"
    if not before.refresh_due:
        return "noop-not-due"
    if not codex_ok:
        return "codex-error"
    if (
        before.expires_at_epoch is not None
        and after.expires_at_epoch is not None
        and after.expires_at_epoch > before.expires_at_epoch
        and not after.refresh_due
    ):
        return "refreshed"
    return "still-stale"
