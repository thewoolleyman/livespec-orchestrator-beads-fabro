# Design resolution after maintainer approval

The maintainer confirmed the four existing plan assertions and the proposed
order with: "I approve, continue autonomously". The ledger scope event is the
authority for that approval. This note resolves the questions in research 001;
it is design rationale, not a second status queue or carrier map.

## One reader and a precise result

Use one typed result reference for deadlines and delivery. Each reference names
the repository explicitly and selects one of: item status, an exact marker in
a target item's comment, pull-request state, a verified plan/work-item proof
record, or a file with an expected blob identity on a branch. A file's mere
existence cannot prove that the requested edit landed. A verified proof is a
distinct type because a comment containing the word "verified" is insufficient.
Readers return satisfied, unsatisfied, or unobservable, with source identity,
observation time and evidence identity. An adapter failure is unobservable, not
an unsatisfied result and never success. Cross-tenant reads resolve the target
repository's configuration and working directory through existing registry and
credential seams. No arbitrary shell predicate is accepted.

## Deadline accounting

The proposed next-action schema adds required_result and budget to the existing
kind/ref/text object. Budget carries an absolute UTC deadline and a positive
maximum count of accepted handoffs; both are explicitly selected, and the first
limit reached expires the budget. The deadline remains operative even if no
handoff is written. Legacy pointers remain readable but report missing tracking;
the first subsequent write must supply the new fields. Human/none pointers use
explicit null tracking fields so escalation cannot deadlock on the result reader.

The obligation is keyed by canonical target/result identity, not next-action
wording, kind/ref, session identity, or last_session. Merely calling
set_next_action or changing wording cannot restart the clock. The fixed-shape
progress-event comment records the epoch, original budget and its baseline;
the ledger remains the sole durable store. A changed approach requires a typed
record naming the previous epoch, diagnosis, concrete change, supporting
evidence and replacement budget. A handoff with a prose "approach:" line alone
is insufficient. Replacing an unmet result also requires that record, or a
human escalation that preserves the outstanding obligation.

All pointer-writing primitives enforce the rule, including supervisor writes.
Refusal occurs before the handoff is appended or the pointer changes. Resume
reports exhausted or unobservable obligations instead of automatically
dispatching them. An unattended exhausted resume may transition to human with
the diagnostic and old obligation retained; it must not silently rearm. Explicit
changed approaches remain available to an authorized autonomous session.

## Attention and attribution

The primary detector reads the declared result, and ancillary repair merges
cannot clear its expiry. A second, report-only historical detector reports a
window with handoffs but no attributable new merged PR, closed child or verified
proof record. Require explicit configuration for this window and its positive
handoff threshold; absent configuration produces a configuration finding, not
a guessed threshold. This preserves assertion 4 while addressing research 001's
counterexample where repairs merged but the actual required result never moved.

Attribution follows the union of explicit parent-child edges and dotted-id
children, existing item-to-PR provenance, and typed proof records. It does not
scan arbitrary prose for URLs or infer completion from the child count. A child
closed before the window is not a new result in it. Unobservable sources surface
with their identity; they cannot establish a confident "no result" finding.
The existing record-rate warning remains a separate signal.

## Relay delivery and supervisor ownership

Give each relay a stable id, typed expected result and deadline. Observing the
target controls delivered; sender acknowledgment, peer receipt and peer_recorded
are recorded separately. Unobservable and unsatisfied relays remain undelivered,
with the sender responsible. An idempotent retry of the same relay must preserve
its original deadline. Revise this repository's supervisor guidance alongside
the implementation; refer the corresponding overseer schema/consumer change to
its owning repository once the attention envelope is stable. Do not edit that
repository from this plan. Pane-only messages remain undelivered until they have
a durable target effect.

## Dispatch progress and changed approach

Research 001's "at or before the furthest stage any previous dispatch reached"
must use the high-water mark BEFORE each attempt. Comparing every run against
the maximum including itself is a tautology. The first observed run establishes
a baseline; subsequent comparable item-attributable terminal attempts advance
it or increment a consecutive non-progress count. A committed positive
dispatcher.redispatch_no_progress_limit selects the count that refuses the next
claim. Missing/invalid configuration yields a configuration refusal, never an
implicit numerical policy.

Use milestones in the workflow's actual dependency order, not lexical stage
names or retry indices. Runs from incomparable workflow variants need an
explicit baseline/changed-approach record. Host failures neither increment nor
reset the count. Active, duplicate and superseded observations are excluded.
Unknown terminal causes or unreadable remote history require diagnosis and
must not be silently classified as host failures. Query the run's recorded
factory, never the default local server. Existing within-run caps remain intact.
One changed-approach record authorizes one new epoch and cannot be replayed to
reset every later dispatch.

## Routing and proof

The contract amendment covers all four assertions together, with executable
Given/When/Then scenarios and heading-coverage entries at ratification. Separate
implementation increments own the result reader, deadline enforcement,
attention reporting, relay delivery, and dispatch refusal. Guidance ships with
the behavior it explains. The overseer referral and released-artifact plan proof
remain explicit follow-through work. Spec ratification precedes admission;
factory dispatch implements the children. Completion still requires independent
replay of plan proof against the normally installed released build.

Proof cases must include a queued/acknowledged relay with unchanged target; an
unrelated repair merge while the required result remains absent; repeated
pointer writes attempting to reset a budget; a failed target query; a real
changed-approach recovery; advancing and flat dispatch histories; host failures;
and the correct remote factory. Negative controls must demonstrate that each
instrument can observe a real positive result from the same target surface.
