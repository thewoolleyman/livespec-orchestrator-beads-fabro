---
topic: cost-gate-covers-every-launched-run
author: claude-opus-5-5
created_at: 2026-11-01T01:58:44Z
---

## Proposal: The cost gate covers every launched run, fails closed on an unresolvable run id when unattended, and derives its keyed verdict in report posture

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Amend contracts.md "### Fail-closed cost gate (keyed on `--item` presence)" to close the three coverage weaknesses the section now states honestly. (1) Gate coverage widens from runs that reached a successful terminal outcome to every run that LAUNCHED (carries a run record), whatever its terminal outcome; a dispatch refused before any sandbox launch still yields no gate record. (2) An unresolvable run id stops being fail-open: it is treated as an unobservable cost and takes the same `--item`-keyed verdict (refusal on an unattended drain under `enforce`, warning on a hand-picked dispatch), still journaled with the unresolvable-run-id reason. (3) The `report` posture DERIVES the keyed verdict and journals it as the record's would-be verdict, while still never refusing and never applying a cap, so the gate logic is exercised in the posture nearly every run uses. Scenario 45's existing scenarios are amended in place; no heading is added.

### Motivation

Item bd-ib-0s5 ("Cost gate coverage is narrower than it appears: failed runs ungated, unresolvable run id fail-open, report mode never derives the verdict"), owned by the dispatcher-policy arc whose epic is bd-ib-24j5uy ("Realize the ratified v034 dispatcher policy settings (retire Full autonomous mode)", now closed; the item outlived it as its residual spec amendment). Filed as the linked proposal plan bd-ib-ax3rds (spec-implementation-lockstep) assertion 7 requires, as part of the R1 bd-ib-j6uvkj residual batch under the coordinator ruling of 2026-11-01T00:21:09Z. Judged a FEATURE, not a bug: the ratified section deliberately states today's narrower coverage, including an explicit FAIL-OPEN clause, so the asked-for coverage is new behaviour no clause states. Its stored type `chore` is evidence, not the answer. The item's own premise holds: a run that launched, spent and then failed is exactly where runaway spend is likeliest, and the original rationale that failed runs "have no meaningful cost yet" is contradicted by a run that both launched and spent. Its correction also holds: CC-token-derived cost is the primary observed-cost source (livespec-impl-beads-efj closed), so widening coverage does not turn every run into an unobservable refusal; the residual unobservable case is exactly what the keyed verdict already handles. The item names its route as spec-change tier: an INDEPENDENT Fable review returning no blockers is a precondition of any accept, followed by a maintainer-driven revise, before any implementation. This proposal is a draft for that review and that decision; the maintainer may equally reject it and keep the ratified coverage, which would then be recorded as the item's closure.

### Proposed Changes

### contracts.md — "### Fail-closed cost gate (keyed on `--item` presence)"

Replace the whole **Gate coverage — which runs are gated at all.** bullet (with its two sub-bullets) with:

- **Gate coverage — which runs are gated at all.** The cost gate MUST apply to every dispatched run that LAUNCHED — one for which a run record exists — whatever its terminal outcome: a run that launched, consumed spend and then failed, blocked or was released is gated exactly as a successful one. A dispatch refused before any sandbox run launched (an admission refusal, a host-route refusal, a dry run) has no run and yields no gate record. A run released for a provider-limit failure additionally yields the attempt-cost record of §"Factory-configurable ACP fallback priority" → "Cost follows every attempt"; that record is an observation, and the run's gate verdict is derived from its cost signal like any other gated run's.
  - A run whose id CANNOT be resolved against the cost source MUST be journaled with the work-item and the unresolvable-run-id reason, and its cost signal MUST be treated as UNOBSERVABLE for the verdict below. It is no longer fail-open: under `enforce` with no `--item` it is a fail-closed refusal.

In the **Journaling.** bullet, replace "an unresolvable run id MUST produce the skipped record above. No gated run goes unrecorded." with:

"an unresolvable run id MUST additionally carry the unresolvable-run-id reason. No launched run goes unrecorded."

In the **Enforcement posture** bullet, replace "— but NO keyed verdict is derived and none is applied: the record's severity is `report`, and the Dispatcher MUST NOT refuse and MUST NOT apply a cost cap." with:

"— and the keyed verdict above MUST still be DERIVED and recorded on the gate record as its would-be verdict, but it MUST NOT be applied: the record's severity is `report`, and the Dispatcher MUST NOT refuse and MUST NOT apply a cost cap."

and replace "the cost signal is still observed and a gate record is still journaled regardless of its value." with "the cost signal is still observed, the keyed verdict is still derived, and a gate record is still journaled regardless of its value."

### scenarios.md — "## Scenario 45 — Unobservable cost fails closed on an unattended drain and warns on a hand-picked dispatch"

In the first two scenarios, replace "a dispatched run reached a successful terminal outcome and its run id resolves against the cost source" / "that run reached a successful terminal outcome and its run id resolves against the cost source" with "a dispatched run launched and its run id resolves against the cost source".

Replace the scenario "An unresolvable run id is journaled as a skipped gate and is fail-open" with:

```gherkin
Scenario: An unresolvable run id on an unattended drain fails closed
  Given LIVESPEC_COST_MODE is enforce
  And the Dispatcher loop was invoked with no --item (an unattended queue drain)
  And a dispatched run launched but its run id cannot be resolved against the cost source
  When the cost gate runs
  Then a gate record is journaled naming the work-item and the unresolvable-run-id reason, with an unobservable cost signal
  And the gate verdict is a fail-closed refusal and the Dispatcher stops picking
```

Replace the scenario "A run that did not reach a successful terminal outcome is not gated" with:

```gherkin
Scenario: A launched run that failed is gated like a successful one
  Given LIVESPEC_COST_MODE is enforce
  And the Dispatcher loop was invoked with no --item
  And a dispatched run launched, consumed spend, and did not reach a successful terminal outcome
  When that run's per-run cost signal is unobservable
  Then the gate verdict is a fail-closed refusal and a gate record is journaled for the run
  And a provider-limit-released run still yields its attempt-cost observation besides its gate record

Scenario: A dispatch refused before any sandbox launched yields no gate record
  Given a dispatch refused at admission, so no run launched
  When the cost gate runs
  Then no gate record is journaled for it
```

In the scenario "The default report posture journals a gate record but derives no keyed verdict", rename it "The default report posture derives and records the keyed verdict but never applies it" and replace "And no keyed verdict is derived, the record's severity is report" with "And the record carries the derived would-be verdict, a fail-closed refusal, while its severity is report".

No `## ` heading is added, renamed or removed, so tests/heading-coverage.json is unchanged.
