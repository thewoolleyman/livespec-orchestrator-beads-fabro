# Unregistered obligations and consumed recovery

This is a maintainer-authorized scope correction from the
`overseer-herdr-rewrite` review, received during the 2026-10-08 planning session.
It supersedes research 002 wherever that note starts coverage only at wait
registration, equates owner acknowledgement with consumption, or treats an
operator alert/referral as sufficient prevention. The original five outcomes
and the Honeycomb rider remain; the epic adds the missing autonomous outcomes.

## Incident and discriminating observation

The review reports that the owning session sent FINAL at about
2026-10-07T14:23Z before detached acceptance gate
`20261007T142403Z-3604049` returned. The gate failed at 14:37:09Z; no owner
resumed, and at 22:55Z no active subagents remained. A 14:25 deadline existed
only in prose, and epic `overseer-uzvcbn` still pointed at a completed 14:17
diagnostic. No human decision blocked progress. These are reviewer-provided
incident facts, not independently replayed product evidence in this session.

The failure is an outstanding authorized obligation with no effective consumer.
A perfect wait primitive cannot help if no wait was armed. A notification or
operator attention fact is not recovery. Coverage therefore starts at dispatch
or delegation, survives the owning turn, and ends only at an authoritative result
or a valid explicit disposition.

## Shared semantic owner

Plan `relay-delivery-and-progress-deadline`, epic `bd-ib-lrik25`, owns the ONE
canonical required-result reference and reader, original deadline/budget,
progress epoch, target-effect fulfillment and typed changed-approach semantics.
Its owner confirmed this boundary directly in the current session and accepted
the same incident. Its proposal is
`SPECIFICATION/proposed_changes/relay-delivery-and-progress-deadline.md` on its
own branch; do not introduce a competing target/result enum or silently extend
the current three-field next_action before that contract is ratified.

The shared interface identifies obligation, canonical target/result, epoch,
original deadline, recovery attempt and causal evidence. This plan owns the
launch/completion integration, durable independent wake scheduling, recovery
consumer claim/execution receipts and proof that work actually resumes. Relay
owns satisfaction and whether a recovery constitutes a valid new approach.
Receipt, consumption and target satisfaction are separate facts.

Coordination uses the two existing Codex tasks and the exact verified herdr
panes `w1:pD` (relay) and `w1:pF` (stall). The maintainer authorized standalone
`herdr --session default` communication without setting `HERDR_ENV`; both pane
identities and repository paths were verified through `agent get`. A submitted
message proves submission only. The peer's concrete proposal/carrier state,
read through its own repository/ledger, establishes incorporation.

## Registration before the coordinator can disappear

The dispatch/delegation boundary records a durable launch intent tied to the
existing result obligation BEFORE the external effect, then attaches the real
gate/run/delegation identity. It binds the owning session and scope of authority,
result epoch, original deadline and a verifiable independent recovery owner.
An idempotent operation id and partial-launch reconciliation cover a crash
between launching and attaching the target. A missing owner or unsupported
launch path produces an explicit unmonitored refusal/finding; it cannot report
successful protected delegation. Never auto-kill a live target to repair tracking.

The same obligation stays present when no wait command is ever used. The local
inventory is an operational projection, not a second result ledger. Discovery
cross-checks launch intents and actual gates/runs to recover a missing wait row;
an unreadable authority is unobservable, not an empty or completed work set.

Before the actual owning session ends its turn with unfinished authorized work,
the supported completion boundary verifies the obligation and independent
producer/consumer registration. Ending a turn is different from declaring the
objective complete. A runtime without an enforceable end-of-turn hook must use
the launch boundary plus independent consumer and disclose hook coverage; it
cannot claim a universal completion gate it does not have. Existing supervised
completion rules that already refuse open obligations are preserved.

## Independent recovery and bounded consumption

The existing overseer daemon and its ordinary service supervision own the
independent scheduling/execution leg. It reads durable obligations on startup
and while the coordinator is idle or gone, independent of a waiter process or
pane notification. Local target completion or the original deadline schedules
recovery. A dropped notification is discovered by reconciliation. An expired
consumer lease is claimed by an authorized replacement with a new fencing
generation; the displaced consumer cannot mutate the obligation afterward.

Under the declared supported host configuration, a terminal target or expired
deadline must start an actual authorized diagnosis/recovery command within
60 seconds, without a human prompt, while no legitimate HOLD or commit/Red
safety barrier applies. Losing the coordinator or first recovery consumer is
part of this guarantee: the installed service recovery path must be exercised,
not assumed. If no independent owner or takeover path can be verified, protected
launch/turn completion refuses or reports unmonitored; that negative case is
not counted as autonomous prevention.

Use separate durable transitions: notification produced, receipt acknowledged,
consumer claim, execution started, execution evidence recorded, and resulting
next action reconciled. The existing ack command records receipt ONLY. Neither
ack nor a claimed consumer closes an obligation. The relay-owned authoritative
reader alone establishes the requested target effect; intermediate recovery
can be successfully consumed while the original required result remains unmet.

Before executing, re-read authoritative ledger, forge, recorded remote factory,
current result epoch, current authorization and any safety disposition. A stale
pointer to a completed diagnostic cannot be blindly repeated. A failed gate
does not prove its remote run or merged pull request failed; use the sanctioned
per-item reconciliation before selecting the next authorized action. A valid
changed approach comes from the relay-owned policy, not a rewritten timestamp.

Use a stable recovery attempt id and generation-fenced claim. Duplicate events,
concurrent consumers and restarts must converge on one observed command effect.
After a crash with an ambiguous execution outcome, inspect the command's durable
effect before retrying; retain uncertainty when it cannot be determined. Do not
claim universal exactly-once execution for arbitrary shell commands. The host
proof uses a supported idempotent recovery operation with a durable receipt.

## Safety is a state, not silence

A legitimate human HOLD records its authority, reason, owner and release
condition and preserves the obligation/deadline history. It prohibits autonomous
mutation while held. A running commit/hook or open Red-Green pair is likewise a
visible execution barrier: queue recovery, preserve the worker, and re-evaluate
at the normal safe boundary. Never send an interrupt, close a pane, reset a
branch, abandon a run or bypass an admission/spec gate to meet the 60-second
bound. Wake/observation can proceed while mutation is held. When the barrier
clears, execute the still-authorized recovery within 60 seconds of clearance.

Ordinary idle state, a prose deadline, an unanswered transport notification and
a completed diagnostic are not legitimate HOLDs. Expiry wakes authorized
diagnosis; it does not manufacture a human blocker. Only a genuine decision
outside existing authority routes to a person.

## Required released-host scenario

Provide one runnable isolated scenario through the normally installed releases:
start an authorized detached operation from a real Codex coordinator in Herdr, register
the obligation at launch, deliberately omit wait registration, end the owning
turn, and let the target gate fail later. Prove the independent consumer observes
the failure, refreshes the stale diagnostic pointer and executes the correct
recovery command once within 60 seconds without a human prompt. Capture the
continuing authorized action and target evidence; an alert, queued prompt,
receipt acknowledgement or started-but-idle replacement is insufficient.

Exercise coordinator idle and coordinator gone, absent waiter, dead waiter,
dropped notification and killed/expired first recovery owner. Exercise duplicate
events and simultaneous consumers. A valid human HOLD, a running commit/hook
and an open Red-Green pair must suppress mutation without losing the obligation;
after legitimate clearance recovery resumes normally. Lost/ambiguous execution
receipts must cause effect reconciliation rather than a duplicate command.
Missing all recovery-owner coverage must produce the explicit unmonitored
refusal and must not pass as prevention.

Correlate this scenario's obligation/epoch/attempt identities in Honeycomb with
OTLP registration, deadline, notification, receipt, claim, execution, safe-HOLD,
reconciliation and next-action observations. Publish elapsed deadline and
recovery latency, overdue age, retry/duplicate/fencing counts and coverage state
as typed measurements. Keep all controls locally effective with telemetry down.
Independent replay against released installations is mandatory. Closing the
sibling referral, or merely writing this scenario, cannot discharge the plan.

The discriminating incident surface is real Codex/Herdr turn completion, including
FINAL, through normally installed releases. A Claude Stop hook or a simulated
session cannot satisfy this proof. Label Claude, pi and any other runtime results
independently. Missing Codex automatic hooks do not waive launch registration
and independent consumption on its no-wait path: if that path is unsupported,
record the actual incident as uncovered and leave this assertion unmet.
