"""Why a host Codex credential cannot be projected, as operator-facing text.

The PURE diagnostics half of the dual-credential projection: the guarded
freshness grade, plus every refusal a caller can need to render. Split out of
`_dispatcher_codex_auth` by cohesion — that module performs IO (reads the host
file, spends the bounded renewal, projects the snapshot, serves the operator
status command) while this one decides nothing and touches nothing, so it is
reachable from a test with no filesystem at all.

This is the concern that KEEPS GROWING: every position the credential can refuse
from adds another paragraph of prose, and each paragraph has to be careful about
exactly the same thing — not claiming an observation the caller never made.
Keeping them together is what makes that discipline checkable in one place
instead of drifting across call sites.

WHY `CODEX_HOME_ENV` LIVES HERE rather than beside `host_codex_auth_path`, which
also needs it. This module is the LEAF: it imports `_dispatcher_projection` and
nothing else from the dispatcher tree, while `_dispatcher_codex_auth` imports
this one. A constant defined up there and imported down here would close an
import cycle; one defined here and imported up does not. Two refusals quote the
variable by name, so it cannot simply be private to the path resolver.

THE GRADE IS GUARDED, AND THAT IS THE LOAD-BEARING PART. `decode_codex_access_token_exp`
RAISES on a credential it cannot decode — malformed JSON, no `access_token`, an
access token that is not a JWT — and an unreadable credential is an EXPECTED
condition rather than a bug in this package. Letting it raise put a bug-class
exception on the dispatch path: it escaped `dispatch_one`, which skipped
`release_pre_run_claim_if_needed`, and the work item was left `active` with no
factory run behind it. `graded_freshness` therefore returns `None` for
"undecodable" and every caller renders `unparseable_credential_refusal` instead.
The status command already drew this line (`assess_host_codex_credential`'s
`malformed` arm); the dispatch path simply had not.
"""

from __future__ import annotations

import json

from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_early_renewal import (
    CodexRenewalOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_projection import (
    CODEX_FRESHNESS_RUN_BUDGET_SECONDS,
    CodexFreshnessVerdict,
    assess_codex_credential_freshness,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "CODEX_HOME_ENV",
    "absent_credential_refusal",
    "graded_freshness",
    "post_claim_shortfall_refusal",
    "unadvanced_renewal_refusal",
    "unparseable_credential_refusal",
]

# Host-side override for where the live Codex `auth.json` lives. The host is the
# sole `codex login`+refresh owner; the Dispatcher reads its auth.json directly
# (default `~/.codex/auth.json`) and projects a non-rotatable snapshot into the
# sandbox. An env-var NAME, not a secret.
CODEX_HOME_ENV = "CODEX_HOME"


def graded_freshness(*, source_auth_json: str, now_epoch: int) -> CodexFreshnessVerdict | None:
    """Grade the credential, or return None when it cannot be decoded at all.

    `None` is a THIRD answer beside fresh and stale, and it must stay distinct
    from both: an undecodable credential has no measurable lifetime, so reporting
    it as stale would state a shortfall nobody observed, and reporting it as
    fresh would project a credential no one could read. Callers render
    `unparseable_credential_refusal` for it.
    """
    verdict = attempt(
        action=lambda: assess_codex_credential_freshness(
            source_auth_json=source_auth_json,
            now_epoch=now_epoch,
            run_budget_seconds=CODEX_FRESHNESS_RUN_BUDGET_SECONDS,
        ),
        exceptions=(ValueError, json.JSONDecodeError),
    )
    return None if isinstance(verdict, AttemptFailure) else verdict


def absent_credential_refusal() -> str:
    """Render the refusal for a host credential that is not there at all.

    Shared by the pre-claim gate and the post-claim projection because an absent
    credential is the ONE case neither a renewal nor a re-read can change: there
    is nothing to renew, so both surfaces owe the operator the same answer.
    """
    return (
        "C-mode dispatch refused: no host Codex credential found at "
        f"${CODEX_HOME_ENV}/auth.json (default ~/.codex/auth.json). "
        "The Dispatcher projects a non-rotatable snapshot of the "
        "host credential into the sandbox; run `codex login` on the "
        "orchestrator host before dispatch."
    )


def unparseable_credential_refusal() -> str:
    """Render the refusal for a credential present but impossible to decode.

    It reports exactly one thing: the file could not be parsed. It must NOT
    report a remaining lifetime, because none was measurable, and it must NOT
    report an authentication failure, because nothing here asked a provider
    anything — an undecodable local file is equally consistent with a healthy
    account and a dead one. A renewal is not offered as the remedy either: a
    rotation request cannot repair bytes that will not parse.
    """
    return (
        "C-mode dispatch refused: the host Codex credential at "
        f"${CODEX_HOME_ENV}/auth.json is present but could not be parsed, so its "
        "usable lifetime could not be measured at all. This is NOT a lifetime "
        "shortfall and NOT a provider verdict — an undecodable file says nothing "
        "either way. It can mean the credential was rewritten while this "
        "dispatch was reading it, in which case re-running the dispatch resolves "
        "it. Read `dispatcher.py codex-cred-status` on the credential-source "
        "host — the host running the Dispatcher, NOT the remote factory host "
        "that executes the run — and re-run `codex login` there only if that "
        "status also reports the credential unparseable."
    )


def unadvanced_renewal_refusal(
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
        f"reads ${CODEX_HOME_ENV}/auth.json and projects a non-rotatable "
        "snapshot — NOT on the remote factory host that executes the run, so "
        "check that host and no other. Re-read `dispatcher.py "
        "codex-cred-status` before carrying this forward as a blocker, since a "
        "credential renewed since this reading retires it; then run "
        "`dispatcher.py codex-cred-refresh` there. Run `codex login` on that "
        "same host only if Codex explicitly reports an unrecoverable "
        "authentication failure — a non-advancing expiry and a status reading "
        "cannot establish one, however many times they are re-read."
    )


def post_claim_shortfall_refusal(*, verdict: CodexFreshnessVerdict) -> str:
    """Render the refusal for a credential below the floor AFTER the claim.

    Deliberately NOT the unadvanced-renewal message above. No renewal was
    requested on this path, so this text must not report an expiry that declined
    to advance — it never asked. Reporting one would be the inverse of the defect
    that message exists to prevent: an observation nobody made, written up as
    evidence.

    It asserts nothing about authentication for the same reason. A short lifetime
    is a lifetime measurement; the one route that could have produced provider
    evidence was not taken here, and a remaining-seconds reading could not
    establish an authentication failure even if it had been.
    """
    return (
        "C-mode dispatch refused: the host Codex credential has "
        f"{verdict.remaining_seconds} seconds of usable lifetime, below the "
        f"{verdict.required_remaining_seconds} seconds the dispatch freshness "
        "gate requires (run budget plus margin). The pre-claim credential gate "
        "already spent this dispatch's one bounded in-place renewal, so no "
        "second renewal is spent here, and this lifetime reading is NOT a claim "
        "that authentication has failed. Re-read `dispatcher.py "
        "codex-cred-status` on the credential-source host — the host running "
        f"the Dispatcher, which reads ${CODEX_HOME_ENV}/auth.json, NOT the "
        "remote factory host that executes the run — then run `dispatcher.py "
        "codex-cred-refresh` there. Run `codex login` on that same host only if "
        "Codex explicitly reports an unrecoverable authentication failure."
    )
