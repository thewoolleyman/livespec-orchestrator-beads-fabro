"""Guarded host Codex credential refresh command.

The body behind `dispatcher.py codex-cred-refresh`, which the five-minute host
timer runs. It decodes the access-token expiry locally and spends a renewal
request ONLY inside the refresh guard, so the timer normally costs nothing and
then spends one request near the cliff.

The request is the app-server `account/read` with `refreshToken`, NOT
`codex exec`. Upstream gates the ordinary refresh on a five-minute window
(`should_refresh_proactively` in `codex-rs/login/src/auth/manager.rs`), and the
guard is derived from the dispatch freshness requirement — which is itself
resolved per workflow and is DAYS rather than hours for this repository's own
graph — so a `codex exec` spent anywhere in that span could not advance the
expiry: the timer would attempt and decline while reporting that it had tried.

Dropping `codex exec` dropped a privilege with it. That invocation carried
Codex's approvals-and-sandbox bypass flag, and a hook gate existed only to
decide whether to pass it, because `exec` runs a model turn that wants a
workspace. `account/read` executes nothing — it is a credential RPC — so there
is no sandbox to bypass, no gate to consult, and no full-access code path here.
The flag name is deliberately not spelled here: a structural check asserts
this module carries no bypass token, and prose would defeat it.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_early_renewal import (
    CodexAppServerRunner,
    classify_renewal_result,
    request_early_codex_renewal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_refresh import (
    CODEX_ALARM_THRESHOLD_SECONDS,
    HostCodexCredentialStatus,
    assess_host_codex_credential,
    classify_refresh_outcome,
    codex_refresh_guard_seconds,
    should_invoke_codex_refresh,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_requirement import (
    WorkflowFaultDeferral,
    operator_credential_requirement,
    requirement_refusal_text,
)
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout

__all__: list[str] = [
    "run_codex_cred_refresh_with",
]


@dataclass(frozen=True, kw_only=True)
class _RefreshPayloadInput:
    before: HostCodexCredentialStatus
    after: HostCodexCredentialStatus
    codex_exit_code: int | None
    codex_stderr: str
    dry_run: bool
    invoked_codex: bool
    outcome: str
    renewal_answered: bool
    would_invoke_codex: bool


def run_codex_cred_refresh_with(
    *,
    args: argparse.Namespace,
    cwd: Callable[[], Path],
    now_epoch: Callable[[], int],
    read_host_codex_auth: Callable[[], str | None],
    runner_factory: Callable[[], CodexAppServerRunner],
) -> int:
    """Guardedly invoke Codex so the host-owned credential refreshes itself."""
    requirement = operator_credential_requirement(
        repo=cwd(),
        workflow_name=getattr(args, "workflow_name", None),
        review_fix_cap=getattr(args, "review_fix_cap", None),
    )
    if isinstance(requirement, str | WorkflowFaultDeferral):
        # Eligibility is DERIVED from the dispatch requirement, so a requirement
        # that cannot be resolved leaves no eligibility to compute. Refusing is
        # the only honest answer: spending a provider request against a guard
        # derived from nothing, or declining against one, would both report an
        # eligibility nobody established.
        _ = write_stderr(text=f"{requirement_refusal_text(outcome=requirement)}\n")
        return 1
    guard_seconds = codex_refresh_guard_seconds(run_budget_seconds=requirement.allowance_seconds)
    before = _assess_host_codex_credential(
        now_epoch=now_epoch,
        read_host_codex_auth=read_host_codex_auth,
        guard_seconds=guard_seconds,
    )
    invoked_codex = False
    codex_exit_code: int | None = None
    codex_stderr = ""
    after = before
    would_invoke_codex = should_invoke_codex_refresh(status=before)
    renewal_answered = False
    if would_invoke_codex and not args.dry_run:
        invoked_codex = True
        refresh_cwd = cwd()
        result = request_early_codex_renewal(cwd=refresh_cwd, runner=runner_factory())
        renewal = classify_renewal_result(result=result)
        renewal_answered = renewal.answered
        codex_exit_code = result.exit_code
        # The classifier's secret-free summary, never the server transcript.
        codex_stderr = renewal.detail
        after = _assess_host_codex_credential(
            now_epoch=now_epoch,
            read_host_codex_auth=read_host_codex_auth,
            guard_seconds=guard_seconds,
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
            renewal_answered=renewal_answered,
            would_invoke_codex=would_invoke_codex,
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
    guard_seconds: int,
) -> HostCodexCredentialStatus:
    return assess_host_codex_credential(
        source_auth_json=read_host_codex_auth(),
        now_epoch=now_epoch(),
        alarm_threshold_seconds=CODEX_ALARM_THRESHOLD_SECONDS,
        refresh_guard_seconds=guard_seconds,
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
        "renewal_answered": refresh.renewal_answered,
        "would_invoke_codex": refresh.would_invoke_codex,
    }


def _codex_cred_refresh_message(*, codex_stderr: str, dry_run: bool, outcome: str) -> str:
    if outcome == "noop-not-due":
        return "Host Codex credential is not inside the refresh guard; codex was not invoked."
    if outcome == "refreshed":
        return "Host Codex credential refresh confirmed; access-token expiry advanced."
    if outcome == "codex-error":
        detail = codex_stderr.strip() or "no detail"
        return (
            "The host Codex renewal request did not complete, so it is no "
            f"evidence about this credential: {detail}"
        )
    if dry_run:
        return "Dry run: host Codex credential is refresh-due; codex was not invoked."
    # NAMES THE ROUTE ACTUALLY TAKEN. This said "after codex exec", which this
    # command stopped spending when the renewal moved to the app-server
    # `account/read` request — so it pointed an operator at a mechanism no longer
    # on this path, and implicitly at the five-minute window that no longer gates
    # it. The module docstring has described the real route all along; this one
    # line had not caught up.
    return (
        "Host Codex credential is still stale after one bounded app-server "
        "account/read renewal request; run `codex login` on the orchestrator "
        "host if this persists."
    )


def _codex_cred_refresh_human(*, payload: dict[str, Any]) -> str:
    before_remaining = payload["before"]["remaining_seconds"]
    after_remaining = payload["after"]["remaining_seconds"]
    return "\n".join(
        (
            f"outcome: {payload['outcome']}",
            f"dry_run: {_human_bool(value=payload['dry_run'])}",
            f"would_invoke_codex: {_human_bool(value=payload['would_invoke_codex'])}",
            f"invoked_codex: {_human_bool(value=payload['invoked_codex'])}",
            f"renewal_answered: {_human_bool(value=payload['renewal_answered'])}",
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
