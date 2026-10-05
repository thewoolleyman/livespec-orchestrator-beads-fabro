"""Codex credential projection for the Dispatcher."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_app_server_io import (
    ShellCodexAppServerRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_cred_refresh_command import (
    run_codex_cred_refresh_with,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_early_renewal import (
    CodexRenewalOutcome,
    classify_renewal_result,
    request_early_codex_renewal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_identity_command import (
    IDENTITY_OBSERVATION_PAYLOAD_KEY,
    identity_observation_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_identity_observation import (
    identity_observation_human_lines,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_refresh import (
    CODEX_ALARM_THRESHOLD_SECONDS,
    CODEX_REFRESH_GUARD_SECONDS,
    HostCodexCredentialStatus,
    assess_host_codex_credential,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    CODEX_FRESHNESS_RUN_BUDGET_SECONDS,
    CodexFreshnessVerdict,
    assess_codex_credential_freshness,
    project_codex_auth_snapshot,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = [
    "CodexProjectionRefusal",
    "project_codex_auth",
    "read_host_codex_auth",
    "renew_host_codex_credential",
    "run_codex_cred_refresh",
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
    auth_text = attempt(
        action=lambda: (Path(home) / "auth.json").read_text(encoding="utf-8"),
        exceptions=(OSError,),
    )
    if isinstance(auth_text, AttemptFailure):
        return None
    return auth_text


@dataclass(frozen=True, kw_only=True)
class CodexProjectionRefusal:
    """A dual-credential-projection refusal routed as data (missing/stale)."""

    message: str


def renew_host_codex_credential() -> CodexRenewalOutcome:
    """Spend ONE bounded request asking the host Codex to renew itself early.

    Host-only and in place: no token is copied, parsed or written here. The
    caller still grades the CREDENTIAL by re-reading `auth.json`; the outcome
    returned here describes only what happened to the REQUEST, which is what
    lets a diagnostic separate "Codex answered and the expiry held" from "the
    request never reached Codex". Neither is a verdict about authentication.
    """
    repo = Path.cwd()
    return classify_renewal_result(
        result=request_early_codex_renewal(cwd=repo, runner=ShellCodexAppServerRunner())
    )


def project_codex_auth(*, clock: Callable[[], int]) -> str | CodexProjectionRefusal:
    """Project the host Codex credential into the dispatch sandbox snapshot.

    Returns the non-rotatable `auth.json` snapshot string on success
    (scenarios.md Scenario 18), or a `CodexProjectionRefusal` carrying an
    actionable message when the host credential is absent (Scenario 18
    precondition) or cannot be brought above the run budget plus margin
    (Scenario 19). The refusal is a distinct type so a snapshot that happens
    to look like a message is never mistaken for one.

    A credential BELOW the requirement is not refused on sight. It is inside
    the refresh guard by construction (the guard is derived from the same
    requirement), so the sanctioned host-only renewal is eligible: this spends
    it, re-reads, and admits the dispatch when the credential now outlives the
    budget. That re-read is what retires a blocker the credential has already
    outgrown — the freshness FLOOR itself is never lowered to admit anything.

    `clock` is a CALLABLE rather than a timestamp because the renewal request
    is bounded at two minutes, and re-grading the re-read credential against
    the PRE-request instant would credit it with up to that much lifetime it
    no longer has. That error runs in the UNSAFE direction — it would admit a
    dispatch whose credential is already below the floor — so the clock is
    read again after the request and the stale reading is never reused.
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
    verdict = _assess_freshness(source_auth_json=source_auth_json, now_epoch=clock())
    if verdict.fresh_enough:
        return project_codex_auth_snapshot(source_auth_json=source_auth_json)
    outcome = renew_host_codex_credential()
    renewed_auth_json = read_host_codex_auth()
    # Read the clock AGAIN, after the request. Never reuse the reading above.
    now_after_renewal = clock()
    if renewed_auth_json is None:
        return CodexProjectionRefusal(message=_unadvanced_refusal(verdict=verdict, outcome=outcome))
    renewed = _assess_freshness(
        source_auth_json=renewed_auth_json,
        now_epoch=now_after_renewal,
    )
    if renewed.fresh_enough:
        return project_codex_auth_snapshot(source_auth_json=renewed_auth_json)
    return CodexProjectionRefusal(message=_unadvanced_refusal(verdict=renewed, outcome=outcome))


def _assess_freshness(*, source_auth_json: str, now_epoch: int) -> CodexFreshnessVerdict:
    return assess_codex_credential_freshness(
        source_auth_json=source_auth_json,
        now_epoch=now_epoch,
        run_budget_seconds=CODEX_FRESHNESS_RUN_BUDGET_SECONDS,
    )


def _unadvanced_refusal(
    *,
    verdict: CodexFreshnessVerdict,
    outcome: CodexRenewalOutcome,
) -> str:
    """Render the refusal for a credential the bounded renewal did not advance.

    Deliberately NOT a claim that authentication has failed, and it says so in
    as many words, because the two reasons an expiry can hold are not
    equivalent evidence: Codex may have answered and declined to advance it, or
    no successful renewal response may have come back at all. The second says
    nothing whatsoever about the credential, so collapsing the two is what
    turns an absent observation into a false demand for a human login.

    And the login remedy is conditioned on EXPLICIT auth evidence rather than
    on a non-advancing expiry, because this route cannot produce such evidence:
    upstream DISCARDS the refresh outcome on the `account/read` path
    (`workspace_routing.rs` binds nothing from `refresh_token_if_requested`,
    and the v1 `getAuthStatus` path discards it too), so no response here can
    confirm or deny an authentication failure. Telling an operator to re-read
    status until it "still reports no advance" would send them after evidence
    that is structurally unavailable, and a stale-blocker loop is exactly how
    this item's 2026-10-05 incident played out.
    """
    unanswered_note = (
        ""
        if outcome.answered
        else (
            "; no successful renewal response was received, so it is no "
            "evidence about this credential at all"
        )
    )
    return (
        "C-mode dispatch refused: the host Codex credential has "
        f"{verdict.remaining_seconds} seconds of usable lifetime, below the "
        f"{verdict.required_remaining_seconds} seconds the dispatch freshness "
        "gate requires (run budget plus margin), and one bounded in-place "
        f"renewal request did not advance it ({outcome.detail}). That does NOT "
        f"by itself establish an authentication failure{unanswered_note}. Note "
        "that this renewal route cannot report an authentication failure "
        "either: Codex discards the refresh outcome on the account/read path, "
        "so no response here can confirm or deny one. This credential lives on "
        "the credential-source host — the host running the Dispatcher, which "
        f"reads ${_CODEX_HOME_ENV}/auth.json and projects a non-rotatable "
        "snapshot — NOT on the remote factory host that executes the run, so "
        "check that host and no other. Re-read `dispatcher.py "
        "codex-cred-status` before carrying this forward as a blocker, since a "
        "credential renewed since this reading retires it; then run "
        "`dispatcher.py codex-cred-refresh` there. Run `codex login` on that "
        "same host only if Codex explicitly reports an unrecoverable "
        "authentication failure — a non-advancing expiry and a status reading "
        "cannot establish one, however many times they are re-read."
    )


def run_codex_cred_status(*, args: argparse.Namespace) -> int:
    """Emit host Codex credential lifetime status for operators.

    The identity observation is an OPT-IN rider on this reading, and it never
    touches the exit code: external monitoring is already wired to the alarm,
    so letting an observation move that signal would change what a page means.
    """
    source_auth_json = read_host_codex_auth()
    now_epoch = int(time.time())
    status = _assess_host_codex_credential_now(
        source_auth_json=source_auth_json,
        now_epoch=now_epoch,
    )
    payload = _codex_cred_status_payload(status=status)
    observation = identity_observation_for(
        source_auth_json=source_auth_json,
        state_path_argument=args.observe_identity_state,
        now_epoch=now_epoch,
    )
    if observation is not None:
        payload[IDENTITY_OBSERVATION_PAYLOAD_KEY] = observation
    if args.as_json:
        _ = write_stdout(text=json.dumps(payload, indent=2, sort_keys=True) + "\n")
    else:
        _ = write_stdout(text=_codex_cred_status_human(payload=payload, observation=observation))
    return 1 if status.alarm else 0


def run_codex_cred_refresh(*, args: argparse.Namespace) -> int:
    return run_codex_cred_refresh_with(
        args=args,
        cwd=Path.cwd,
        now_epoch=lambda: int(time.time()),
        read_host_codex_auth=read_host_codex_auth,
        runner_factory=ShellCodexAppServerRunner,
    )


def _assess_host_codex_credential_now(
    *,
    source_auth_json: str | None,
    now_epoch: int,
) -> HostCodexCredentialStatus:
    return assess_host_codex_credential(
        source_auth_json=source_auth_json,
        now_epoch=now_epoch,
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


def _codex_cred_status_human(
    *,
    payload: dict[str, Any],
    observation: dict[str, Any] | None,
) -> str:
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
            *identity_observation_human_lines(observation=observation),
            "",
        )
    )


def _human_bool(*, value: object) -> str:
    return "true" if value is True else "false"


def _human_optional(*, value: object) -> str:
    return "null" if value is None else str(value)
