# Active-to-parked continuity and independent recovery

This clarification supersedes research 001's claim that busy and parked plans
are disjoint and research 002's default expiry-to-human behavior. They are
states of one outstanding obligation, not independent coordination systems.
The maintainer-authorized reviewer `stall_plan_review` supplied a new incident:
the coordinator ended its turn around 2026-10-07T14:23Z with gate
`20261007T142403Z-3604049` outstanding; the gate failed at 14:37:09Z and no
continuation occurred through 22:55Z. A prose deadline had no live consumer and
the epic pointer still described an earlier completed diagnostic. This note
attributes those incident times to that review; this session has not replayed
the historical gate. The new acceptance scenario below reproduces its causal
shape rather than treating the reported times as new measurements.

## Ownership boundary

This plan owns required-result identity, authoritative satisfaction, immutable
original deadlines, recovery epochs and evidence. Plan
`agent-session-stall-prevention` (`bd-ib-jnpvh4`) owns independently running
observers, wake transport and actual continuation execution. Its inventory
references the canonical obligation rather than copying and resetting it.
Starting dispatch/delegation registers unfinished work before a caller can
report it handed off; an explicit wait registration is not required for the
independent consumer to discover that obligation. A turn-end check is an extra
safeguard, not the only producer or consumer of durable obligations.

An independent consumer reads the canonical obligation across coordinator
working, idle, stopped and replacement-session states. Terminal failure or
expiry causes an authorized diagnosis/recovery command to execute within 60
seconds, or a durable specific safety deferral to appear within that bound.
Missing consumer coverage itself is an actionable liveness failure; it cannot
be hidden by an idle pane or a sent notification. Consumer registration carries
verifiable identity/liveness evidence and a takeover route independent of the
coordinator. Lost waiter, notification path, consumer owner and coordinator are
separate failure cases.

## Delivery vocabulary and causal recovery

Transport queued, transport delivered, coordinator consumption, recovery attempt
started, and target effect fulfilled are separate observations. Acknowledgment
of any earlier stage never satisfies a later one. A timed-out relay retains its
sender and original result/deadline while the independent consumer performs
bounded recovery. A retired sender's durable obligation transfers only through
an explicit recoverable owner/takeover record, never disappears with the pane.

Changed approach is not self-certification. It references the unresolved
obligation and previous epoch, measured failure evidence, cause classification,
an executable authorized next operation, a unique recovery-attempt id, and a
bounded attempt deadline. Registering that attempt does not postpone the
original obligation deadline. A claim receipt is distinct from a start/command
execution receipt. Progress is a newly observed required target effect, or a
measured causal milestone explicitly required by the recovery attempt; repair
children and unrelated merges are never substitutes. Renaming or replacing a
target preserves the unresolved original until an explicit causal supersession
is justified. Unknown causes trigger diagnosis; host causes trigger bounded
host recovery; neither is mislabeled an item-attributable repeated failure.
Human escalation is reserved for an actual decision or authorization deficit,
not an automatic consequence of time passing.

A stable attempt id fences duplicate terminal events, repeated scans and
consumer restarts. An uncertain command outcome requires reconciliation of the
execution receipt before retry. Exactly-once means the observable recovery
operation executes once for that event/attempt, not merely that one message
was queued. Valid human HOLDs, active commit hooks and open Red-Green pairs
prevent unsafe continuation. Their safety deferral is recorded within the same
60-second bound; the consumer keeps observing and resumes only when the
specific protected condition clears through its authorized path.

## Cross-plan host scenario

On normally installed released artifacts, launch a real gate that later fails,
with a durable required-result obligation but deliberately without wait
registration. End the coordinator turn and exercise both idle and gone cases.
The independent consumer must observe the failed gate, reconcile the stale
completed-diagnostic pointer, and invoke an instrumented authorized recovery
command exactly once within 60 seconds. Capture gate completion time, consumer
observation, claim, actual command execution, resulting ledger action, and
continued ownership of any unfulfilled target. A queued prompt or acknowledgment
is not the success instrument. Observe a real target effect separately.

Repeat with deadline expiry before gate completion, waiter loss, dropped
notification, consumer-owner loss/takeover, renamed target, a repair-child merge,
an acknowledged relay and a purported changed approach with no executed causal
attempt. The original deadline and unresolved target must survive. Duplicate
terminal notifications and a consumer restart must still produce one execution.
Negative controls keep a valid human HOLD, a running commit and an open Red pair;
they must produce a specific safety deferral within 60 seconds and no prohibited
command, then exactly one authorized continuation after the protection clears.
Repeat with an unknown cause and a known host cause to prove diagnostic routing
without incrementing the item-attributable repetition counter.

Both plans must retain this cross-plan released host capture and independent
replay as completion evidence. Filing a referral, a message acknowledgment,
closing an implementation child and seeing an alert are each insufficient.
