# 001 — Charter: an idle factory must be visible, and a refused credential must be re-probed

Opened 2026-09-06 at the maintainer's direction from the livespec-dev-tooling
backlog drain (plan `dev-tooling-backlog-drain`, epic
`livespec-dev-tooling-kcoslm`). Spec-first: each carrier below enters as a
proposed change against `SPECIFICATION/contracts.md`, is ratified through
`revise`, and only then is implemented through this repo's factory. Nothing
here is hand-fixed.

## 1. The incident this plan exists for (measured 2026-09-06)

- 10:46Z: the dev-tooling drain's C-mode dispatch was refused at admission:
  `C-mode dispatch refused before sandbox launch: CLAUDE_CODE_OAUTH_TOKEN is
  exhausted or rate-limited (HTTP 429, rate_limit_error). Observed condition:
  exhausted. Remedy: For a rolling rate limit, wait before retrying ...`. The
  session took a reset instant from the 429 body ("resets 15:50 Europe/Berlin
  = 13:50Z") and wrote three detached resumers that slept until 13:55Z.
- 11:50Z: a fresh session resumed the plan and carried the 13:50Z claim from
  the handoff without probing.
- 12:05Z, measured: `dispatcher.py claude-cred-status --json` returned
  `condition: usable`, HTTP 200. The dispatch journal held NO unexpired
  exhaustion record for the repo (the Dispatcher's hold is a bounded 15
  minutes, `_HOLD_INTERVAL`, per §"Provider spend containment" "Every
  exhaustion record expires"). `needs-attention` at 11:50Z listed valves and
  plan items and said nothing about an idle factory with 44 ready items.
- 12:10Z: the maintainer noticed by hand. Two hours of factory idle time.

The Dispatcher's own containment behaved as ratified. What failed is
outside it, in two places this specification does not yet cover.

## 2. Carrier A — the idle-factory attention row (proposed change)

§"needs-attention" composes "spec, implementation, human-valve, plan, and
hygiene gather primitives". §"Provider spend containment" and the attention
snapshot's closed enumeration of waits (contracts.md ~line 962: "an
enumerated wait absent from the snapshot is a composition defect, not a
policy choice") register every wait the orchestrator OWNS. An idle factory is
not a wait on a person or a slot, so no class composes it, and the operator
learns of it only by looking.

Proposed clause (to be filed via `propose-change`): when, for a repository,
(a) the ready set is non-empty and at least one ready item is dispatchable
under the admission valve's non-capacity conditions, (b) `counted_claims`
is zero, (c) no unexpired exhaustion record is held for the provider the
default dispatch would use, and (d) the admission-time credential usability
probe returns usable, `needs-attention` MUST emit exactly one attention item
of a new `idle-factory` composition class, at high urgency, whose summary
names the dispatchable count and the first ranked id, and whose handoff is
the `impl:<first-id>` drive action. It is derived ONLY from this repository's
own journal, ledger, and probe (§"The ownership boundary"). Two invocations
against an unchanged store emit byte-identical rows. Scenario to be added
under the needs-attention scenario block.

Constraint to respect: the row is a composition of existing reads; it MUST
NOT itself dispatch, and MUST NOT create work-items (§"needs-attention":
"executes nothing, and creates no work-items").

## 3. Carrier B — the refused credential probe is re-probed, and its remedy carries no timing claim (proposed change)

The admission-time probe that produced the 10:46Z refusal is a Messages API
call against the projected `CLAUDE_CODE_OAUTH_TOKEN` (the `claude-cred-status`
surface; `probe_claude_credential`). Its refusal is terminal for the loop
invocation and its remedy text tells the operator to "wait before retrying"
without saying how long, which invites exactly the clock-gated resumer the
incident shows. Meanwhile the ratified clause is explicit that a provider's
timing claim "MUST NOT be adopted as the expiry" and "The Dispatcher MUST
NOT assume that any given provider communicates availability timing at all".

Proposed clause: a `loop` invocation whose admission is refused by the
credential usability probe MUST NOT exit on that refusal while its budget is
unspent; it MUST re-run the probe on a bounded cadence (a committed-only
`dispatcher.credential_reprobe_interval_seconds`, default 300) and admit
normally on the first usable result, journaling each refused probe as one
record. The refusal's remedy text MUST NOT carry a provider-stated reset
instant as an instruction; if the provider offered one it MAY be recorded as
provenance "clearly marked as an unverified provider claim", exactly as the
exhaustion-record clause already requires. This is the same principle as
"An exhaustion record is falsifiable by a dispatch outcome", applied to the
probe: the probe's OWN next result is the retirement signal, not a clock.

Open question for `critique` before filing: whether a usable probe result
should ALSO retire an unexpired exhaustion record. The ratified text names
two retirement routes (dispatch outcome, operator clearance) and forbids
credential-material inspection for CREATION. A Messages API probe is not
credential-file inspection, but the clause's reasoning ("host and sandbox
credential state diverge by construction") applies to it too. Default
answer: no, leave the two routes as ratified; the bounded 15-minute hold is
short enough. Record the answer in the proposal, not in prose.

## 4. What this plan does not do

- Does not touch the dev-tooling drain's launcher; that is
  `livespec-dev-tooling-kcoslm.1` (probe-gated launcher, clock resumers
  deleted), already done there.
- Does not reopen the C18 item `bd-ib-6huwuq` (the v067 expiry clause vs. C4's
  code); this plan cites the ratified text as it stands and files nothing on
  that clause.
- Does not hand-fix. Both carriers are spec-ops first; the implementation
  children are filed under this epic only after ratification, with
  acceptance criteria that name the scenario each clause adds.

## 5. Next action

`propose-change` for Carrier A (`idle-factory-attention-row`), then Carrier B
(`credential-probe-reprobe`), then `revise`, then file the two implementation
children as `impl` next actions.
