---
topic: tests-order-by-events-not-real-time
author: claude-opus-5-5:seat:fleet-flaky-tests
created_at: 2026-11-04T03:07:27Z
---

## Proposal: Forbid real-time sleeps and wall-clock verdicts in tests, enforced by a check with a reasoned exemption marker

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

Add a Forbidden-patterns rule that a test MUST NOT wait by sleeping in real time or decide its verdict on a real wall-clock elapsed bound; it orders by an injected clock or a deterministic event, a remaining wall-clock wait is only a hang guard, and a check in the just check aggregate refuses violations by file and line while honouring a per-line exemption marker with a written reason. Add one scenario stating the refusal and the exemption.

### Motivation

Flaky tests with a real sleep plus a tight elapsed bound are the largest single class of defective factory endings in this repository: the coordinator's 2026-10-14 tally counted 9 of 37 defective endings from five tests of that one shape, and the fleet-flaky-tests plan (epic livespec-dev-tooling-zwveqp) has since root-fixed more of them (bd-ib-acnvo, bd-ib-dsprir, bd-ib-gb24he, bd-ib-lwiila, and the Scenario 297 regression bd-ib-4t7o4i). Work item bd-ib-ke5wkf exists to sweep the rest of the class and close the door behind it with a refusing check, but its Definition of Done was REFUSED at the pre-dispatch judgement on 2026-11-03T23:23:58Z because no ratified clause governs real-time sleeps, wall-clock bounds or injected clocks in tests: its only reference, Scenario 254, is about the aggregate's parallel lanes. Without a governing clause the item cannot be dispatched, and the rule the fleet already applies (coordinator-duties section 2: order by a rendezvous, keep a wall-clock wait as a liveness guard only) lives nowhere in this repository's specification.

### Proposed Changes

Append one bullet to `SPECIFICATION/constraints.md` §"Forbidden patterns", after the last existing bullet:

```diff
+- No real-time sleeps or wall-clock verdicts in tests. A test under
+  `tests/` MUST NOT wait for a condition by sleeping in real time
+  (`time.sleep`), and MUST NOT decide pass or fail on a real wall-clock
+  elapsed reading (a difference of `time.monotonic`, `time.perf_counter`
+  or `time.time` values, or thread-start timing). It MUST instead advance
+  an injected clock or wait on a deterministic event (a joined thread, a
+  set `threading.Event`, a written file, a child's exit). A wall-clock
+  wait that remains MAY exist only as a liveness guard against a hang,
+  never as the condition that decides the verdict. A check in the
+  `just check` aggregate MUST refuse a test file that violates this rule,
+  naming each offending file and line, and MUST honour an explicit
+  per-line exemption marker that carries a written reason, for a test
+  whose subject is real time itself.
```

Add one scenario to `SPECIFICATION/scenarios.md`, numbered as the next free scenario number at revise time (the file currently ends at Scenario 303; an in-flight revise may take further numbers):

```gherkin
## Scenario NNN — The check aggregate refuses a test that sleeps in real time or judges a wall-clock bound, unless an exemption marker states why
Given a test file under tests/ that calls time.sleep to wait for a condition
  And another test file that asserts on a difference of two time.monotonic readings
When the just check aggregate runs
Then the real-time-test check fails
  And its refusal names each offending file and line
Given the same time.sleep line carries the per-line exemption marker with a written reason
When the just check aggregate runs again
Then the check does not refuse that line
  And a marker with an empty reason is still refused
```

The scenario MUST be co-edited with its `tests/heading-coverage.json` entry in the revise commit.
