# Handoff — credential-freshness-redesign

## What this thread is

Reconsider **how the host keeps its Codex credential fresh** for the dark
factory. The shipped `codex-credential-broker` track (epic `bd-ib-rck`, CLOSED)
landed a working but host-coupled shape: a freshness **gate** at dispatch
preflight + a host **systemd timer** that polls Codex's ~5-min pre-expiry window.
A design review after that track landed questioned the gate/timer architecture
and produced a design-of-record recommending a **less-coupled shape**:

> right-sized freshness gate **+** preflight refresh in the dispatch path **+** a
> liveness check **+** the W1 expiry alarm — and **drop the host timer**. Defer
> the more aggressive "mid-run top-up" until one open question is settled.

**Nothing here is built yet.** This thread supersedes the timer's *design intent*,
NOT the shipped *code* — every landed piece (`codex-cred-status`,
`codex-cred-refresh`, the runbook, the gate) remains a valid building block.

- **Design of record:** [`research/credential-freshness-redesign.md`](research/credential-freshness-redesign.md)
  — the full analysis, the design space (A preflight / mid-run top-up / B direct
  endpoint), the grounded investigation findings, and the recommendation.
- **Parent track (closed):** `plan/archive/codex-credential-broker/handoff.md` (epic
  `bd-ib-rck`). This thread graduated out of that track's post-completion design
  reconsideration.

## ▶ CURRENT STATE + NEXT ACTION (read this first)

**Status: awaiting a MAINTAINER DECISION on the redesign direction.** This is an
architecture change to *shipped* behavior, so the shape is the maintainer's call,
not something to build unprompted. Analysis + tracking are complete; no product
code has changed.

**Next action (maintainer):** okay (or amend) the recommended shape in the design
of record. Once the shape is chosen, decompose `bd-ib-yx7pdm` into per-deliverable
work-items and dispatch the factory-safe ones.

## Ledger items

| Item | Status | What |
|---|---|---|
| **`bd-ib-yx7pdm`** | BACKLOG (epic-shaped) | Credential-freshness redesign: preflight refresh + right-sized gate + liveness check (supersede the W3 timer). Multiple coherent deliverables — decompose after the maintainer okays the shape. |
| **`bd-ib-zz6gii`** | BLOCKED (needs-tier) | Instrument `codex-cred-status` to capture `session_id`/`jti` across refreshes — the zero-risk way to settle the Case 1/2 access-token-revocation question (see below). Direction-independent; useful under any chosen shape. |

## The open question the instrumentation settles

Does a Codex **refresh bump `session_id`** (Case 2 — outstanding access tokens
held by concurrent workers are invalidated at rotation, a fleet-wide simultaneous
failure) or keep it stable (Case 1 — old tokens live to their own `exp`)? This
gates whether **mid-run top-up** is safe to build.

- **A-priori lean is Case 1.** A `session_id`/`sid` claim identifies the *sign-in
  session*; a refresh-token exchange is designed to extend that session without
  re-authenticating, so the standard behavior is a **stable `session_id`, new
  `jti`** per token. For `session_id` to bump on refresh, OpenAI would have to mint
  a new session on every refresh — nonstandard. And OpenAI's anti-concurrency
  guidance is **fully explained by refresh-token rotation desync alone** (single-use
  refresh tokens), which our seatbelt + sentinel already neutralize for workers —
  so it is *not* strong evidence for Case 2.
- **But it's unproven.** The `session_id` claim makes Case 2 *possible*, and Codex's
  auth implementation is opaque. There is **no safe way to force a refresh now**
  (Codex has no force-refresh; an out-of-band refresh would rotate and thus break
  the live refresh token → forced `codex login`).
- **`bd-ib-zz6gii`** resolves it with zero live-credential risk: record
  `session_id`/`jti` (structural, non-secret) whenever the token is observed to
  change, so the next *natural* refresh near expiry reveals whether `session_id`
  bumped — answered within one ~10-day cycle.

## Relationship to the shipped track

This thread does **not** revert `codex-credential-broker`. If the redesign is
adopted, it will *supersede the systemd timer's role* (preflight refresh self-heals
an idle-expired token at the next dispatch) while keeping `codex-cred-status`,
`codex-cred-refresh`, the freshness gate (right-sized), and the W1 alarm. The
gate's 1h margin is load-bearing beyond runway — it **temporally separates rotation
from worker execution**, which is what makes our concurrent credential-sharing safe
against a session bump; mid-run top-up deliberately destroys that separation, which
is exactly why it is deferred on the open question above.
