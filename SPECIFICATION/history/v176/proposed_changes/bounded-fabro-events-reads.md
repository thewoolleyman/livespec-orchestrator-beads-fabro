---
topic: bounded-fabro-events-reads
author: claude-opus-5-5:fabro-currency
created_at: 2026-10-20T18:00:35Z
---

## Proposal: Fabro event reads are bounded in size, retries and concurrency

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds a 'Bounded Fabro event reads' subsection beside 'Dispatcher progress watchdog' requiring every Dispatcher `fabro events` read to be bounded: later reads of a run are since- or tail-bounded while carrying forward progress and open-command-node state; a timed-out, failing or zero-byte read is journaled with its attempt number and backed off exponentially from a 60-second floor; the ACP projection's replay gives up after five consecutive failures with an exhausted record; and one reconcile pass reads a run at most once, with at most two concurrent reads per factory per host. Scenario 227 exercises it.

### Motivation

Work-item bd-ib-2dlh7m, filed under coordinator ruling R330(2) (livespec-dev-tooling-dfixhe). petri measured a 390-minute gmktec run whose `fabro events --json` returns 0 bytes after 240 s or more, while reconcile-runs and the dispatcher loops re-read it continuously; bd-ib-woacnk's loop spent 26 minutes reconciling with 8 such calls live at once on gmktec. In the source, every FabroPort.events caller reads the whole log, and a timed-out ACP projection read becomes an unresolved projection failure that replay_acp_projection re-reads on every pass with no cap or backoff. The R265 Definition-of-Done preflight refused bd-ib-2dlh7m because no ratified clause or scenario governs bounded event reads; the nearest, 'Dispatcher progress watchdog' and Scenario 173, bound poll cost against the factory's run history, not one run's event count. The bounds are stated as finite values rather than new dispatcher.* keys, because §'Dispatcher policy settings' makes every key per-item overridable except wip_cap and these bounds are not per-item properties. In-flight survey: PR 3405 (spec/propose-lockstep-batch-6) touches publication only and reserves Scenarios 224-226; this proposal aligns with it and takes 227.

### Proposed Changes

In SPECIFICATION/contracts.md, under the H2 "Grooming and slice-size calibration", insert a new subsection immediately AFTER the subsection "Dispatcher progress watchdog" (that is, after its closing sentence "Scenario 172 in `scenarios.md` exercises this subsection.") and BEFORE the subsection "Calibration telemetry and the single Fabro tweak":

> ### Bounded Fabro event reads
>
> Every `fabro events` read the Dispatcher issues — from the progress watchdog, the ACP projection and its reconcile replay, the review-gate and cost readers, and any other caller — is a read of one run's event log on one factory. Each such read MUST be bounded in size, in retries and in concurrency, so that a run whose event log is large or slow to serve cannot turn the Dispatcher into an unbounded source of load on the factory. This subsection does not govern how the factory serves the log.
>
> **Read size.** Once a caller has read a run's events, every later read of that run by the same Dispatcher process MUST be bounded to the events after the newest event instant it has already observed, or to a bounded number of trailing events. A liveness sample taken from a bounded read MUST carry forward the progress instant and the open command node that earlier samples of the same run established, so bounding a read never hides a command node that started before the bound; §"Dispatcher progress watchdog" continues to govern what those values mean. The cost of one watchdog sample MUST NOT grow with the run's total event count.
>
> **Failed reads and backoff.** A `fabro events` read that times out, exits non-zero, or returns zero bytes is a FAILED events read. On each failed events read the Dispatcher MUST journal one `fabro-events-read-failed` record naming the work-item, the run id, the factory, the reading caller, the elapsed seconds, the consecutive attempt number for that run and caller, and the backoff before that caller's next read of the run. That caller MUST NOT start its next read of the run until the backoff has elapsed. The backoff MUST be at least 60 seconds after a first failure and MUST at least double after each further consecutive failure; a successful read resets the count. A failed events read MUST be treated as an unobservable sample, never as the run having disappeared or having made no progress.
>
> **Exhausted projection reads.** When the ACP projection's read of one run has failed on five consecutive attempts, `reconcile-runs` MUST journal one `acp-projection-exhausted` record naming the work-item, the run id, the factory, the attempt count and the last failure reason, and MUST NOT re-read that run's events on any later pass. The projection failure MUST remain visible as exhausted rather than being cleared. A new dispatch of the work-item creates a new run and is not affected by the exhausted state of an earlier run.
>
> **Concurrency.** One `reconcile-runs` pass MUST issue at most one `fabro events` read per run. Across every Dispatcher process on one host, at most two `fabro events` reads against one factory MUST be in flight at the same time; a read that cannot start within its caller's timeout because the bound is full MUST be treated as a failed events read for backoff purposes.
>
> Scenario 227 in `scenarios.md` exercises this subsection.

In SPECIFICATION/scenarios.md, add at the end of the file a new scenario heading (tests/heading-coverage.json MUST gain an entry for it in the same revise):

## Scenario 227 — Fabro event reads are bounded in size, retries and concurrency

```gherkin
Feature: The Dispatcher's Fabro event reads cannot become unbounded factory load
  As an operator of a shared factory
  I want every events read bounded
  So that a long run's slow event log does not draw continuous re-reads

  Scenario: A later watchdog sample reads only new events
    Given the progress watchdog has already read a bound run's events once
    And a command node of that run started before the newest observed event instant and has not completed
    When the watchdog takes its next sample
    Then the read is bounded to events after the newest observed instant or to a bounded tail
    And the sample still reports that command node as open

  Scenario: A zero-byte read is journaled and backed off
    Given a fabro events read of a run that returns zero bytes
    When the Dispatcher handles the result
    Then it journals one fabro-events-read-failed record with the run id, elapsed seconds, attempt number and backoff
    And the same caller does not read that run again until the backoff has elapsed
    And the run is not reported as disappeared or stalled

  Scenario: Repeated projection read failures are exhausted
    Given the ACP projection's read of a run has failed on five consecutive attempts
    When a later reconcile-runs pass runs
    Then an acp-projection-exhausted record names the run and the attempt count
    And no later pass reads that run's events

  Scenario: Concurrent reads against one factory are capped
    Given two fabro events reads against one factory are already in flight from this host
    When a third caller needs to read a run on that factory
    Then it does not start a third concurrent read
    And a read that cannot start within its timeout is handled as a failed events read
```
