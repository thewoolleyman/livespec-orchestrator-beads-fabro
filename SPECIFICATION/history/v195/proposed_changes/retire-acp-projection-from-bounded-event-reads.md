---
topic: retire-acp-projection-from-bounded-event-reads
author: claude-opus-5-5
created_at: 2026-10-21T20:20:08Z
---

## Proposal: Retire the ACP projection from the bounded Fabro event reads contract

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Remove the ACP fallback event projection and its reconcile replay from the callers of '### Bounded Fabro event reads', withdraw the 'Exhausted projection reads' paragraph and its acp-projection-exhausted record, replace the matching Scenario 227 examples and exhaustion scenario with a scenario stating that no reconciliation surface replays the retired projection, and keep every read-size, backoff and concurrency bound on the remaining callers unchanged.

### Motivation

Conformance repair of a contradiction between two ratified versions, ruled by coordinator gitops-fleet-capacity-monitoring as R521 on 2026-10-21. v127 (proposal dispatcher-level-model-fallback, 'Retire engine failover events and their projection') deleted the agent.acp.failover projection, the hygiene:model-fallback-projection fact and its stop-picking rule. v176 (PR 3411, for bd-ib-2dlh7m) later added '### Bounded Fabro event reads' and Scenario 227, which name 'the ACP projection and its reconcile replay' as a governed caller and mandate an acp-projection-exhausted record — re-requiring a reader v127 had retired. The contradiction is now blocking: bd-ib-qm6r1 (PR 3336), which deletes the retired projection code, is refused at the launch-time Definition-of-Done preflight on both legs (gate 20261021T200550Z-2517949), because its removal assertion conflicts with v176. The cost of the still-running projection is measured: on 2026-10-21 bd-ib-ouk27x took 22 minutes to admit on gmktec while the dispatch journal gained about 350 acp-projection-failure timed-out rows across 19 runs, because the dispatch preamble runs a non-dry reconcile pass whose replay re-reads every unresolved run; a dispatch of bd-ib-dtfv2p the same day reported 409 unresolved projection failures, one run carrying 2083 attempts. Bounding a reader that the specification has already retired keeps it on the admission path; removing it is what v127 ratified.

### Proposed Changes

```diff
--- a/SPECIFICATION/contracts.md
+++ b/SPECIFICATION/contracts.md
@@ ### Bounded Fabro event reads
-Every `fabro events` read the Dispatcher issues — from the progress watchdog, the ACP projection and its reconcile replay, the review-gate and cost readers, and any other caller — is a read of one run's event log on one factory. Each such read MUST be bounded in size, in retries and in concurrency, so that a run whose event log is large or slow to serve cannot turn the Dispatcher into an unbounded source of load on the factory. This subsection does not govern how the factory serves the log.
+Every `fabro events` read the Dispatcher issues — from the progress watchdog, the review-gate and cost readers, and any other caller — is a read of one run's event log on one factory. Each such read MUST be bounded in size, in retries and in concurrency, so that a run whose event log is large or slow to serve cannot turn the Dispatcher into an unbounded source of load on the factory. This subsection does not govern how the factory serves the log.
+
+**No projection reader.** The ACP fallback event projection and its reconcile replay are retired (§"Factory-configurable ACP fallback priority", since v127), and they are not a caller of this subsection. The Dispatcher MUST NOT issue a `fabro events` read whose purpose is to project `agent.acp.failover` events, and no reconciliation surface — the loop tick, the dispatch preamble, or the standalone `reconcile-runs` sweep — MAY re-read a run's events to replay such a projection.
@@
-**Exhausted projection reads.** When the ACP projection's read of one run has failed on five consecutive attempts, `reconcile-runs` MUST journal one `acp-projection-exhausted` record naming the work-item, the run id, the factory, the attempt count and the last failure reason, and MUST NOT re-read that run's events on any later pass. The projection failure MUST remain visible as exhausted rather than being cleared. A new dispatch of the work-item creates a new run and is not affected by the exhausted state of an earlier run.
-
 **Concurrency.** One `reconcile-runs` pass MUST issue at most one `fabro events` read per run. ...
```

The **Read size**, **Failed reads and backoff** and **Concurrency** paragraphs MUST remain unchanged. The `acp-projection-exhausted` journal record is withdrawn: the Dispatcher MUST NOT be required to write it, and a journal reader MUST still parse any such record already written, per the record-readability rule of §"Factory-configurable ACP fallback priority".

```diff
--- a/SPECIFICATION/scenarios.md
+++ b/SPECIFICATION/scenarios.md
@@ ## Scenario 227 — Fabro event reads are bounded in size, retries and concurrency
     Examples:
       | caller                |
       | progress watchdog     |
-      | ACP projection        |
-      | ACP reconcile replay  |
       | review-gate reader    |
       | cost reader           |
@@
-  Scenario: Repeated projection read failures are exhausted durably
-    Given the ACP projection's read of a run has failed on four consecutive attempts
-    When its fifth consecutive attempt fails
-    Then reconcile-runs journals exactly one acp-projection-exhausted record
-    And the record names the work-item, run id, factory, attempt count 5 and last failure reason
-    And the projection failure remains visible as exhausted
-    When later reconcile-runs passes run
-    Then none reads that run's events
-    And none duplicates the exhaustion record or clears the failure
-    When a new dispatch creates a new run for the same work-item
-    Then the earlier run's exhaustion does not prevent reading the new run
+  Scenario: No reconciliation surface replays the retired ACP projection
+    Given a dispatch journal holding acp-projection-failure records for a run
+    When the loop tick, the dispatch preamble or the standalone reconcile-runs sweep reconciles that run's factory
+    Then it issues no fabro events read of that run to project agent.acp.failover events
+    And the existing acp-projection-failure records still parse
```

The heading `## Scenario 227 — Fabro event reads are bounded in size, retries and concurrency` MUST remain verbatim, so `tests/heading-coverage.json` needs no change; every other scenario in its Gherkin block MUST remain unchanged.
