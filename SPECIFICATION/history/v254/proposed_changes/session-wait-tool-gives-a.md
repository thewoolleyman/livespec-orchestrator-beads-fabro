---
topic: session-wait-tool-gives-a
author: claude-opus-5-5:petri-factory-on-gmktec
created_at: 2026-10-30T19:14:44Z
---

## Proposal: A successor session can retire a dead owner's terminal session wait through the tool, recording who retired it, why, and each target's terminal state

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a `retire` operation to the session-wait CLI under ## Bounded session waits and observable inventory: a non-owning session may dispose of a wait whose targets are all terminal, keeping the original record intact and adding a retirement disposition; a still-running target is refused.

### Motivation

The contract says unacknowledged wait records MUST survive session and waiter exit until explicit disposition, but the only disposition it defines is an ack by the receiving (owning) session. `_session_wait_ack.ack_wait` returns `owner-mismatch` for any other session id, and `check`/`complete` write nothing. So a record whose owner has ended can never be disposed of through the tool, and the host turn-end check reports it forever. Measured 2026-10-30 in the livespec-dev-tooling store: 19 records from 10 ended petri-role sessions, every watched gate terminal (deadlines 2026-10-14..19). The current role owner cannot ack them; hand-deleting them or acking under a dead session's id would falsify the record. Coordinator gitops-fleet-capacity-monitoring ruled a successor-retire verb that records the retiring session, the reason and the terminal state, refuses a non-terminal target and leaves the owner's record intact. Work-item bd-ib-jk5npz carries the implementation and is held as spec-change tier for this topic.

### Proposed Changes

In SPECIFICATION/contracts.md, ## Bounded session waits and observable inventory:

1. In the opening sentence, change "with `wait`, `inventory`, `ack` and `check` operations" to "with `wait`, `inventory`, `ack`, `retire` and `check` operations".

2. After the sentence ending "An explicit ack by the receiving session MUST mark receipt acknowledgement only; execution consumption and target-result fulfillment MUST remain distinct under the shared obligation contract below.", add:

**A successor retires a terminal wait it does not own.** The `retire` operation MUST let a session other than the record's owning session dispose of a wait record, given the retiring session id and a non-empty reason. It MUST refuse, as `target-not-terminal` and without changing the record, while any target of the wait is in a still-running state. A retired record MUST keep its original session identity, frozen targets and observations unchanged, and MUST gain a retirement disposition carrying the retiring session id, the reason, the retirement time and the observed terminal state of every target. Retirement is a disposition, not a receipt acknowledgement: it MUST NOT mark the wait acknowledged by its owner, and MUST NOT establish execution consumption or target-result fulfillment. Inventory and the host turn-end check MUST NOT report a retired record as ended-but-unacknowledged. Retirement MUST publish a `session.wait.retired` event carrying the retiring and the original owning session ids, which joins the wait-family event catalog. Retired records count toward the bounded acknowledged retention.

In SPECIFICATION/scenarios.md, add a scenario (numbered at revise):

## Scenario NN — A successor retires a dead owner's terminal wait without rewriting it

Given a wait record in the session-wait store whose owning session has ended, whose targets have all ended, and which was never acknowledged,
When a different session runs `retire` with its own session id and a reason,
Then the record keeps its original owner, targets and observations, gains a retirement disposition naming the retiring session, the reason and each target's terminal state, and inventory no longer reports it as ended-but-unacknowledged.
And when a session runs `retire` on a wait whose target is still running, the operation refuses as `target-not-terminal` and the record is unchanged.

In tests/heading-coverage.json, add the new scenario heading with test "TODO" and reason "implemented by work-item bd-ib-jk5npz".
