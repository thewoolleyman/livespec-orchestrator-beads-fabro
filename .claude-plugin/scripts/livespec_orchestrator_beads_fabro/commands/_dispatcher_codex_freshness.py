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
from typing import Literal

from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_early_renewal import (
    CodexRenewalOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_projection import (
    CodexFreshnessVerdict,
    assess_codex_credential_freshness,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "CODEX_HOME_ENV",
    "RenewalExpiryObservation",
    "absent_credential_refusal",
    "graded_freshness",
    "post_claim_shortfall_refusal",
    "renewal_expiry_observation",
    "renewal_shortfall_refusal",
    "unparseable_credential_refusal",
]

# Host-side override for where the live Codex `auth.json` lives. The host is the
# sole `codex login`+refresh owner; the Dispatcher reads its auth.json directly
# (default `~/.codex/auth.json`) and projects a non-rotatable snapshot into the
# sandbox. An env-var NAME, not a secret.
CODEX_HOME_ENV = "CODEX_HOME"

# What the post-renewal re-read observed about the credential's EXPIRY INSTANT.
# Three answers, not two, because "the re-read could not be taken" is an absent
# observation and must not be rendered as either of the two that were taken.
RenewalExpiryObservation = Literal["advanced", "unchanged", "unmeasured"]


def graded_freshness(
    *, source_auth_json: str, now_epoch: int, run_budget_seconds: int
) -> CodexFreshnessVerdict | None:
    """Grade the credential, or return None when it cannot be decoded at all.

    `None` is a THIRD answer beside fresh and stale, and it must stay distinct
    from both: an undecodable credential has no measurable lifetime, so reporting
    it as stale would state a shortfall nobody observed, and reporting it as
    fresh would project a credential no one could read. Callers render
    `unparseable_credential_refusal` for it.

    `run_budget_seconds` is RESOLVED BY THE CALLER and is deliberately not a
    module constant. It was one -- the `implement` node's own four-hour ceiling
    standing in for the whole run -- and a constant is precisely what cannot
    follow a repository that raises a node timeout or dispatches a longer graph.
    `_dispatcher_credential_requirement` resolves it from the workflow this
    dispatch selected, and every caller on both sides of the claim passes the
    same resolution, so the grade cannot drift between them.
    """
    verdict = attempt(
        action=lambda: assess_codex_credential_freshness(
            source_auth_json=source_auth_json,
            now_epoch=now_epoch,
            run_budget_seconds=run_budget_seconds,
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


def renewal_expiry_observation(
    *,
    before: CodexFreshnessVerdict,
    after: CodexFreshnessVerdict | None,
) -> RenewalExpiryObservation:
    """Compare the pre- and post-renewal EXPIRY INSTANTS, never the remainders.

    `remaining_seconds` cannot answer this question, and reaching for it is the
    available mistake: the two readings are taken against two different clock
    readings, so an expiry that genuinely HELD reads as a smaller remainder
    afterwards, and one that advanced by less than the request took reads as
    smaller too. `access_token_expires_at_epoch` is absolute, so it says what
    happened to the expiry across the request and nothing about how long the
    request took.

    What it CANNOT say is WHY the expiry changed. Two readings of one instant
    are evidence of a change and never of its cause: a concurrent host refresh
    moves the expiry with no renewal response at all, so a caller rendering
    this observation must report the change and stop there.

    `None` for `after` is the re-read that could not be taken at all, and it
    returns `unmeasured` rather than `unchanged`: the renewal may well have
    advanced the expiry in a file this dispatch then failed to read, so
    reporting a hold there would be reporting an observation nobody made.
    """
    if after is None:
        return "unmeasured"
    if after.access_token_expires_at_epoch > before.access_token_expires_at_epoch:
        return "advanced"
    return "unchanged"


def _renewal_expiry_clause(*, expiry: RenewalExpiryObservation) -> str:
    """Render the ONE clause reporting what was OBSERVED of the expiry.

    Three wordings for the three observations, because one wording for all of
    them is the defect this split exists to retire: the hardcoded "did not
    advance it" was false on a dispatch whose expiry moved from 900 to 17970
    seconds of remaining lifetime across an answered renewal and still landed
    under the floor — an expiry that demonstrably advanced reported as one that
    stood still, which points the operator at a broken refresh path instead of
    at the lifetime shortfall actually measured.

    The `advanced` arm reports the before/after CHANGE and stops there. It does
    not name the renewal request as the cause of that change, and it does not
    call the resulting lifetime a mint: the whole evidence here is two readings
    of `access_token_expires_at_epoch`, which identify neither a cause — a
    concurrent host refresh produces the same pair, which is why `expiry` and
    `outcome.answered` are independent — nor a token issuance, since nothing on
    this route observes one. The first fix of this arm asserted both, and an
    invented cause is the same defect as an invented hold, one level subtler.

    The three share NO discriminating vocabulary, and that is deliberate rather
    than stylistic. These clauses are read by substring, both by this package's
    tests and by the published proof record's grader, so an `unmeasured` clause
    phrased as "whether its expiry advanced was not observed" would contain the
    `advanced` arm's own token and grade as an advance — the first draft of this
    function did exactly that. `unmeasured` therefore says "moved".
    """
    if expiry == "advanced":
        return (
            ", and the credential expiry ADVANCED between the readings taken "
            "before and after one bounded in-place renewal request, without "
            "reaching that floor — the lifetime above is the POST-request "
            "reading, and that pair of readings compares the expiry instant "
            "alone, so the change is attributed neither to that request nor to "
            "any token issuance: a concurrent host refresh advances the expiry "
            "the same way, and no issuance was observed here"
        )
    if expiry == "unchanged":
        return ", and one bounded in-place renewal request did not advance it"
    return (
        ", and the credential could not be re-read after one bounded in-place "
        "renewal request, so whether that request moved its expiry was not "
        "observed and the lifetime above is the PRE-renewal reading"
    )


def renewal_shortfall_refusal(
    *,
    verdict: CodexFreshnessVerdict,
    outcome: CodexRenewalOutcome,
    expiry: RenewalExpiryObservation,
) -> str:
    """Render the refusal for a credential still short after the bounded renewal.

    THREE observations are kept apart here, and the separation is the whole
    point of the function. `expiry` says what the renewal did to the expiry
    instant — advanced it, left it standing, or left it unobserved — and
    `outcome.answered` says whether a successful renewal response came back at
    all. They are independent: a credential can advance while no response
    returned (a concurrent host refresh), and a response can return while the
    expiry holds. Collapsing either pair is how an absent observation becomes a
    false statement about the credential.

    Deliberately NOT a claim that authentication has failed, and it says so in
    as many words, for the same reason: none of the three expiry observations,
    and neither answered state, is evidence about an account.

    And the login remedy is conditioned on EXPLICIT auth evidence rather than
    on a non-advancing expiry, because this route cannot produce such evidence:
    upstream DISCARDS the refresh outcome on the `account/read` path
    (`workspace_routing.rs` binds nothing from `refresh_token_if_requested`,
    and the v1 `getAuthStatus` path discards it too), so no response here can
    confirm or deny an authentication failure. Telling an operator to re-read
    status until it "still reports no advance" would send them after evidence
    that is structurally unavailable, and a stale-blocker loop is exactly how
    this item's 2026-10-05 incident played out.

    The tail naming what does NOT count as that explicit evidence is phrased
    against the LIFETIME SHORTFALL rather than against a non-advancing expiry,
    because only the shortfall is common to all three arms. Naming the expiry
    there was a true general statement sitting in front of an operator whose
    expiry had demonstrably advanced — the same mis-aimed reading as the clause
    above it, one sentence further down.
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
        f"{verdict.remaining_seconds} seconds of usable lifetime, which does not exceed the "
        f"{verdict.required_remaining_seconds} seconds the dispatch freshness "
        "gate requires (run budget plus margin)"
        f"{_renewal_expiry_clause(expiry=expiry)} ({outcome.detail}). That does "
        f"NOT by itself establish an authentication failure{unanswered_note}. Note "
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
        "authentication failure — a lifetime shortfall and a status reading "
        "cannot establish one, however many times they are re-read."
    )


def post_claim_shortfall_refusal(*, verdict: CodexFreshnessVerdict) -> str:
    """Render the refusal for a credential below the floor AFTER the claim.

    Deliberately NOT the renewal-shortfall message above, and it carries NONE of
    that message's three expiry clauses. No renewal was requested on this path,
    so this text must not report an expiry that advanced, one that declined to
    advance, or one it failed to re-read — it never asked. Reporting any of them
    would be the same defect those three clauses exist to prevent: an observation
    nobody made, written up as evidence.

    It asserts nothing about authentication for the same reason. A short lifetime
    is a lifetime measurement; the one route that could have produced provider
    evidence was not taken here, and a remaining-seconds reading could not
    establish an authentication failure even if it had been.
    """
    return (
        "C-mode dispatch refused: the host Codex credential has "
        f"{verdict.remaining_seconds} seconds of usable lifetime, which does not exceed the "
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
