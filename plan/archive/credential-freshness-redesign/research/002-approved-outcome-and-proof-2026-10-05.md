## The maintainer's statement of what done means

Yes that is all correct and you can backfill the definition of done. Continue working this autonomously and only prompt me as a human if you are blocked on something.

Make sure that your definition of done is valid and will actually assert that this all works for real.

## Definition of Done assertions derived from that statement

- With the host refresh timer disabled, the released Dispatcher renews a real recoverable Codex credential below its admission threshold during dispatch preflight after an idle period.
- A real factory worker launched by that dispatch authenticates to Codex using the renewed projection and completes its assigned work.
- The released Dispatcher admits a Codex credential only when its remaining lifetime exceeds the maximum enforced credential-use duration of that worker plus the documented safety margin.
- When bounded preflight renewal leaves insufficient lifetime, the released Dispatcher refuses before claiming the item and reports the observed failure without treating an unanswered or unchanged renewal as proof of an authentication failure.
- With timer-based refresh retired, the released credential-status command still raises the documented expiry alarm on the credential-source host.
- The released credential observation surface reports whether session and token identifiers changed across an observed natural renewal without exposing credential material or interpreting identifier stability as proof that older access tokens remain valid.
- A real dispatched worker receives an inert refresh credential while the credential-source host retains ownership of the usable refresh credential.

## Approved direction and derivation context

On 2026-10-05 the maintainer approved the direction summarized in the resumed
plan: refresh during dispatch preflight, right-size the freshness gate, retain
expiry warnings, retire the host timer, and defer mid-run refresh pending evidence.
The two verbatim messages above authorize backfilling this legacy plan and require
observable real-world success. These assertions are the session's derivation of
that approval; they are not quoted as if the maintainer authored their wording.

## Proof obligations

All seven assertions are host-captured. Exercise the published release installed
through its normal installation route, recording release and commit, credential-
source host, factory URL, run ID, timestamps and sanitized outcomes. A separate
session must replay the captured steps and post verified plan proof before archive.
A mock provider, edited JWT, mocked expiry clock, unit suite, green pull request,
closed child or successful account/read response cannot establish real renewal or
real worker authentication. Synthetic negative controls may supplement real proof
but must be labelled, and do not discharge the positive live assertions.

For assertions 1 and 2, observe a real recoverable credential below the threshold,
with the timer disabled, then follow ordinary dispatch through renewal and a real
Codex node to completed work. Observe advanced expiry and provider authentication;
record neither token bytes nor raw session identifiers. If the relevant lifecycle
has not occurred, retain the open assertion rather than manufacture a credential
or weaken the definition. An independent replay needs another authentic lifecycle
or independently replayable provider evidence, not repetition of the same claim.

For assertion 3, demonstrate the admission boundary against the effective enforced
worker lifetime, including retries and time spent waiting before credential use.
Run-time percentiles are measurements, not hard upper bounds. Merely replacing
four hours with the p99 does not establish this assertion. Preserve the existing
floor until a sound bound or enforcement mechanism justifies a change.

For assertion 4, exercise renewal failure and unchanged-expiry outcomes through
the released admission surface with before/after item and run-store observations.
Establish the actual response class; account/read does not expose all auth errors.
For assertion 5, exercise the status CLI at the alarm boundary and retain an
operator-visible warning path after disabling the refresh timer.
For assertion 6, observe a natural renewal and report only safe comparisons or
one-way fingerprints; stable session_id alone cannot prove old-token validity.
For assertion 7, inspect the worker projection without printing secrets and show
successful provider use by the real worker while its refresh credential is inert.

## Revalidation findings on 2026-10-05

The July note remains historical evidence, not the current implementation account.
The current project_codex_auth already attempts one bounded host renewal and
re-reads both credential and clock before admission (4325a137). The standalone
refresher uses the same app-server account/read refreshToken request (35a606a3).
The refresh guard is now derived from the five-hour admission threshold. Therefore
the July claim that the only renewal route is a five-minute-window codex exec is
obsolete. The refusal explanation was further corrected in f0b1e187 to distinguish
an unchanged expiry from explicit authentication failure.

The primary host refresh timer was loaded, enabled and active at inspection.
The installation instructions remain in orchestrator-image/README.md. The gate
still uses a fixed four-hour run allowance and one-hour margin; its comment treats
the dominant node as a proxy for the whole run. Current node timeouts and retry
paths require measurement before any claim that this bounds the whole worker.
The observation task bd-ib-zz6gii still lacks the proposed implementation.

## Scope and explicit deferrals

Preserve provider-owned host renewal and non-rotatable worker projection. Reuse
existing renewal code rather than duplicate it. Reconcile the remaining budget,
operator guidance, timer retirement and passive observation work through ledger
children. Keep real lifecycle proof as a plan obligation even if all code ships.

Mid-run credential delivery and direct OAuth endpoint refresh are deferred because
the approved direction is preflight renewal; reconsider them in a separately scoped
plan only after provider-validity evidence and concurrency analysis. Passive
identifier observation is supporting evidence, never sufficient authorization for
mid-run top-up. GitHub App token lifetime is a different credential mechanism and
remains outside this Codex plan; the older child's notes are adjacent evidence only.
