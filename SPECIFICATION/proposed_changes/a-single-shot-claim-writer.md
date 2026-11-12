---
topic: a-single-shot-claim-writer
author: claude:legacy-dispatcher-agent
created_at: 2026-11-12T14:36:25Z
---

## Proposal: A claim writer that runs once and exits completes a takeover its host has already waited out

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The claim-token takeover wait (step 5) is measured from the first observation of an unapplied transition made on the writer's HOST, which survives process exit, instead of from each process's own first read. A single-shot writer such as one admission attempt can then complete a takeover once the host has waited it out, and every claim-transition-pending report names the instant the wait elapses. No step compares clocks across hosts.

### Motivation

Work item bd-ib-cfucj7, filed by legacy-dispatcher-agent on legacy-coordinator-agent's routing (2026-11-12 ~14:12Z); its filing judgement recorded tier spec-change, verdict partial, generalization target §"Dispatcher policy settings". Scenario 263 states that a writer waits out a recent unapplied transition and takes over once the wait has elapsed on that writer's OWN clock; it does not state that the first observation outlives the process that made it, that a fresh single-shot process can complete the takeover, or that the pending report names when the wait elapses. Measured 2026-11-12: livespec-dev-tooling-wc6sxv and livespec-dev-tooling-5lhafp each named a claim token that a Dispatcher terminal write had closed (12:50:18Z and 12:46:54Z) naming a successor never applied to the item. Every admission attempt is one short-lived `drive` process, and each refused with `admission-claim-refused: ... claim-transition-pending` (wc6sxv at 14:09:20Z), so no admission could ever complete the takeover; the coordinator applied the successor write by hand. Cause on build 58fb211b056e: `_store_claim_tokens._takeover_token` records the first observation with `observations.setdefault((item, token, successor), clock())`, where `clock` is `time.monotonic` and `change_claimed_item` passes a fresh `{}` per call when no map is supplied; `_dispatcher_claim_guard` passes a module-level `TRANSITION_OBSERVATIONS` that dies with the process. Only a process that itself lives 180 seconds (the close tool) can take over. FLEET SCOPE: every claim writer (admission, approve, accept, reconcile). Scoping the wait to the HOST keeps the protocol's rule that no step compares one host's clock with another's: a host's monotonic clock is shared by all its processes until the host restarts, so a durable first observation can be compared on that clock, while a writer on another host still waits on its own. Prior art: bd-ib-kseatc (closed 2026-11-06) built the chain-following takeover assuming a long-lived observer; bd-ib-j6hjhz (closed) made the refusal name its remedy. In-flight survey 2026-11-12 ~14:45Z: five open spec PRs (#5054 a-drift-pass-reuses-one, reserving Scenario 356; #5050; #5048; #5035; #5005) and the stale revise branches; none touches the claim-token protocol (align). Scenario 357 is the first number free of every pending and in-flight reservation.

### Proposed Changes

**1. A durable, host-shared first observation (`contracts.md` §"Dispatcher policy settings", the **Claim tokens** bullet, step 5).** In step 5, replace the clause

> MUST write nothing and MUST report `claim-transition-pending` until it has itself observed that same state, T closed and S not named, across at least 180 seconds of elapsed time on its own monotonic clock, from its first such observation to a fresh read;

with

> MUST write nothing and MUST report `claim-transition-pending` until that same state, T closed and S not named, has been observed across at least 180 seconds of elapsed time on its host's monotonic clock, from the first such observation made on that host to a fresh read of its own;

and append to step 5, after "...only the writer holding the successor that S's close reason names can advance an item that names S.":

> The first observation of an unapplied transition MUST be durable on the host that made it: it MUST survive the exit of the process that made it, and every later claim writer on that host, in any process, MUST measure the takeover wait from that first observation rather than from its own first read. A claim writer that runs once and exits therefore completes a takeover on its first read after the wait has elapsed, whichever process on its host first observed the transition. A recorded first observation that the writer cannot compare on its host's current monotonic clock, because it was made on another host or before the host last restarted, MUST NOT shorten the wait: the writer MUST treat its own read as the first observation. A writer that reports `claim-transition-pending` MUST name in that report the UTC instant at which the wait on its host elapses.

The sentence "No step compares one host's clock with another's: each bound is elapsed time on the measuring writer's own clock" becomes "No step compares one host's clock with another's: each bound is elapsed time on the measuring host's own clock". Every other sentence of the bullet, including both residual classes, is unchanged.

**2. Scenario (`scenarios.md`).** Append:

## Scenario 357 — A claim writer that runs once and exits completes a takeover its host has already waited out

```gherkin
Feature: The takeover wait is measured from the first observation on the writer's host
  Scenario: A fresh process completes the takeover after the host's wait has elapsed
    Given claim tokens are enabled and an item naming closed token T whose close reason names successor S, and the item does not name S
    And a claim writer process on host A observed that state, reported claim-transition-pending and exited
    When a new claim writer process on host A reads the item 200 seconds after that first observation and the state is unchanged
    Then it treats S as the current token and applies the protocol to S

  Scenario: The pending report names when the wait elapses
    Given claim tokens are enabled and an item naming closed token T whose close reason names successor S, and the item does not name S
    And a claim writer process on host A first observed that state 30 seconds ago and exited
    When a new claim writer process on host A reads the item
    Then it writes nothing and reports claim-transition-pending
    And the report names the UTC instant 150 seconds later at which the wait on host A elapses

  Scenario: A writer on another host waits on its own host's clock
    Given claim tokens are enabled and an item naming closed token T whose close reason names successor S, and the item does not name S
    And a claim writer on host A first observed that state 200 seconds ago
    When a claim writer on host B, where no writer has observed that state before, reads the item
    Then it writes nothing and reports claim-transition-pending
```

**3. Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new scenario heading (carried through `resulting_files[]` with the path spelled `../tests/heading-coverage.json`, or edited directly in that commit) with `test: "TODO"`, `work_item: "bd-ib-cfucj7"` and a non-empty `reason` naming the tier the owed test runs at, integration or above, and one matching `tests/heading-coverage-debt.json` entry carrying `work_item: "bd-ib-cfucj7"` and `first_seen` set to the revise date. If the revise renumbers Scenario 357, the row and entry MUST carry the renumbered heading text.
