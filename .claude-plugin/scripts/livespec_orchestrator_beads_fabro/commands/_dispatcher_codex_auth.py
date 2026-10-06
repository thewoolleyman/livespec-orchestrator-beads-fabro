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
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_freshness import (
    CODEX_HOME_ENV,
    absent_credential_refusal,
    graded_freshness,
    post_claim_shortfall_refusal,
    renewal_expiry_observation,
    renewal_shortfall_refusal,
    unparseable_credential_refusal,
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
    HostCodexCredentialStatus,
    assess_host_codex_credential,
    codex_refresh_guard_seconds,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_requirement import (
    WorkflowFaultDeferral,
    operator_credential_requirement,
    requirement_refusal_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    project_codex_auth_snapshot,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_projection import (
    CodexFreshnessVerdict,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout

__all__: list[str] = [
    "CodexProjectionRefusal",
    "host_codex_auth_path",
    "project_codex_auth",
    "project_host_codex_auth",
    "read_host_codex_auth",
    "renew_host_codex_credential",
    "run_codex_cred_refresh",
    "run_codex_cred_status",
]


def host_codex_auth_path() -> Path:
    """Resolve WHERE the host's Codex `auth.json` lives.

    The ONE resolver, so the path a caller is told about is the path
    `read_host_codex_auth` actually opens. That identity is load-bearing for
    the observation's destination guard: a guard comparing against a
    separately-derived path would be comparing against a guess, and a guess
    that drifts from the real location silently stops protecting the file it
    was written to protect.
    """
    home = os.environ.get(CODEX_HOME_ENV) or str(Path.home() / ".codex")
    return Path(home) / "auth.json"


def read_host_codex_auth() -> str | None:
    """Read the host's Codex `auth.json` text (the projection SOURCE).

    DIRECT host-file read — the host is the sole `codex login`+refresh
    owner; the sandbox never touches the live credential. Honors a
    host-side `CODEX_HOME` override (default `~/.codex`). Returns the raw
    text, or None when the file is missing/unreadable, so the caller
    renders an actionable refusal naming `codex login`.

    `UnicodeDecodeError` counts as unreadable alongside `OSError`, which is
    exactly what the sentence above has always promised. A credential holding
    non-UTF-8 bytes is undecodable, not a crash, and letting that error escape
    turned BOTH callers of this read — the status command and the dispatch
    credential projection — into a traceback instead of the actionable refusal.
    """
    auth_text = attempt(
        action=lambda: host_codex_auth_path().read_text(encoding="utf-8"),
        exceptions=(OSError, UnicodeDecodeError),
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


def project_codex_auth(
    *, clock: Callable[[], int], run_budget_seconds: int
) -> str | CodexProjectionRefusal:
    """Grade the host Codex credential BEFORE the item is claimed, renewing once.

    The pre-claim gate's decision function, reached through
    `_dispatcher_codex_credential_gate` from both dispatch paths. It is the ONE
    surface that spends the bounded in-place renewal, because a renewal is the
    only thing that can turn an insufficient credential into a sufficient one —
    so that question has to be settled while the item is still unclaimed and no
    run exists to reap. `project_host_codex_auth` below is the post-claim
    projection, and it renews nothing for exactly that reason.

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

    `run_budget_seconds` is the caller's RESOLVED execution allowance for the
    workflow this dispatch selected, which is what makes the floor follow the
    configuration rather than a constant. It is threaded down to the
    post-renewal re-grade too, so the credential is measured against ONE
    requirement on both sides of the request.
    """
    source_auth_json = read_host_codex_auth()
    if source_auth_json is None:
        return CodexProjectionRefusal(message=absent_credential_refusal())
    verdict = graded_freshness(
        source_auth_json=source_auth_json,
        now_epoch=clock(),
        run_budget_seconds=run_budget_seconds,
    )
    # An UNDECODABLE credential is refused here rather than renewed: a rotation
    # request cannot repair bytes that will not parse, so spending one would buy
    # nothing and would report a renewal the operator cannot act on.
    if verdict is None:
        return CodexProjectionRefusal(message=unparseable_credential_refusal())
    if verdict.fresh_enough:
        return project_codex_auth_snapshot(source_auth_json=source_auth_json)
    return _renew_then_regrade(verdict=verdict, clock=clock, run_budget_seconds=run_budget_seconds)


def _renew_then_regrade(
    *,
    verdict: CodexFreshnessVerdict,
    clock: Callable[[], int],
    run_budget_seconds: int,
) -> str | CodexProjectionRefusal:
    """Spend the ONE bounded renewal, then grade the re-read against the clock.

    Split from `project_codex_auth` along its own seam: everything above the
    split decides whether a renewal is WARRANTED, and everything here is what
    happens once it is. `verdict` is the pre-request grade, carried in for two
    jobs: a refusal reports the shortfall that justified spending the request,
    and its expiry instant is the BASELINE the re-read is compared against, so
    the refusal can say whether the renewal actually advanced anything. Without
    that baseline the only honest wording would be no wording at all, which is
    how a working renewal came to be reported as a dead one.
    """
    outcome = renew_host_codex_credential()
    renewed_auth_json = read_host_codex_auth()
    # Read the clock AGAIN, after the request. Never reuse the reading above.
    now_after_renewal = clock()
    if renewed_auth_json is None:
        return CodexProjectionRefusal(
            message=renewal_shortfall_refusal(
                verdict=verdict,
                outcome=outcome,
                # The re-read failed, so the expiry after the request was never
                # observed. Reporting a hold here would report a measurement
                # this arm is precisely the absence of.
                expiry=renewal_expiry_observation(before=verdict, after=None),
            )
        )
    renewed = graded_freshness(
        source_auth_json=renewed_auth_json,
        now_epoch=now_after_renewal,
        run_budget_seconds=run_budget_seconds,
    )
    # The credential was rewritten under this dispatch and is now undecodable.
    # Reporting the PRE-renewal shortfall would report a lifetime this file no
    # longer has, so report what is actually known: it cannot be read.
    if renewed is None:
        return CodexProjectionRefusal(message=unparseable_credential_refusal())
    if renewed.fresh_enough:
        return project_codex_auth_snapshot(source_auth_json=renewed_auth_json)
    return CodexProjectionRefusal(
        message=renewal_shortfall_refusal(
            verdict=renewed,
            outcome=outcome,
            expiry=renewal_expiry_observation(before=verdict, after=renewed),
        )
    )


def project_host_codex_auth(
    *, clock: Callable[[], int], run_budget_seconds: int
) -> str | CodexProjectionRefusal:
    """Project the host Codex credential as it now stands, renewing NOTHING.

    The overlay's projection step, and the second half of a decision whose first
    half ran before the item was claimed. `project_codex_auth` above owns the
    bounded in-place renewal; by the time this runs the item IS claimed, so a
    renewal here could only extend a credential whose shortfall can no longer be
    reported before a claim — and it would spend a second provider request to do
    it.

    It still GRADES. The gate's verdict was taken earlier, and the loop's
    bounded credential re-probe can hold a wave for an unbounded stretch
    between the two, so a projection that skipped the grade would do the one
    thing the freshness gate exists to prevent: project a credential that may
    expire mid-run.

    EVERY arm returns a refusal; none raises. That is load-bearing rather than
    stylistic, because this function runs AFTER the claim: an exception here
    escapes `dispatch_one` and skips `release_pre_run_claim_if_needed`, which
    leaves the work item `active` with no factory run behind it. The
    undecodable-credential arm exists for exactly that reason — the host file
    can be rewritten between the gate's read and this one, and a rewritten file
    must be a refusal the claim-release valve can see.
    """
    source_auth_json = read_host_codex_auth()
    if source_auth_json is None:
        return CodexProjectionRefusal(message=absent_credential_refusal())
    verdict = graded_freshness(
        source_auth_json=source_auth_json,
        now_epoch=clock(),
        run_budget_seconds=run_budget_seconds,
    )
    if verdict is None:
        return CodexProjectionRefusal(message=unparseable_credential_refusal())
    if verdict.fresh_enough:
        return project_codex_auth_snapshot(source_auth_json=source_auth_json)
    return CodexProjectionRefusal(message=post_claim_shortfall_refusal(verdict=verdict))


def run_codex_cred_status(*, args: argparse.Namespace) -> int:
    """Emit host Codex credential lifetime status for operators.

    The identity observation is an OPT-IN rider on this reading, and it never
    touches the exit code: external monitoring is already wired to the alarm,
    so letting an observation move that signal would change what a page means.
    """
    requirement = operator_credential_requirement(
        repo=Path.cwd(),
        workflow_name=getattr(args, "workflow_name", None),
        review_fix_cap=getattr(args, "review_fix_cap", None),
    )
    if isinstance(requirement, str | WorkflowFaultDeferral):
        # A status that cannot state the requirement it grades against is not a
        # status, so it refuses rather than printing a `refresh_due` computed
        # from nothing. The exit code is the ALARM code, which external
        # monitoring already watches: an unresolvable requirement means no
        # dispatch can be graded at all, which is at least as urgent as a short
        # credential.
        _ = write_stderr(text=f"{requirement_refusal_text(outcome=requirement)}\n")
        return 1
    source_auth_json = read_host_codex_auth()
    now_epoch = int(time.time())
    status = _assess_host_codex_credential_now(
        source_auth_json=source_auth_json,
        now_epoch=now_epoch,
        run_budget_seconds=requirement.allowance_seconds,
    )
    payload = _codex_cred_status_payload(status=status)
    observation = identity_observation_for(
        source_auth_json=source_auth_json,
        source_auth_path=host_codex_auth_path(),
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
    run_budget_seconds: int,
) -> HostCodexCredentialStatus:
    return assess_host_codex_credential(
        source_auth_json=source_auth_json,
        now_epoch=now_epoch,
        alarm_threshold_seconds=CODEX_ALARM_THRESHOLD_SECONDS,
        refresh_guard_seconds=codex_refresh_guard_seconds(run_budget_seconds=run_budget_seconds),
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
