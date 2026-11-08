---
topic: factory-run-wall-budget-hold-released-by-verified-ref
author: claude-opus-5-5
created_at: 2026-11-05T23:56:24Z
---

## Proposal: Release a held wall-budget cancel on a verified preservation ref, and escalate a held cancel with no verified copy

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Bound the whole-run wall budget's export hold. A run whose export cannot be read back is cancelled as soon as a remote ref listing of origin verifies a preservation ref of the run holding its committed tree (its needs-human ref, preserve/run- ref, a preserved-publish ref for the run, or its latest work-in-progress capture). When no verified copy exists the run is still not cancelled, but at the third consecutive held poll the Dispatcher records one named needs-human escalation on the item instead of holding silently. The preserve-before-cancel rule is unchanged.

### Motivation

bd-ib-l77jxo (plan factory-run-work-preservation, epic bd-ib-nckst7). The maintainer adopted it on legacy-coordinator-agent's recommendation, verbatim: "re: 3 save-before-cancel - ok adopt on your recommendation" (recorded on livespec-dev-tooling-6tgd2z at 2026-11-05T23:54:15Z). The adopted direction: the hold releases once a verified needs-human/ or preserve/ ref, checked with ls-remote, holds the run's committed tree, and an unverifiable tree raises a named needs-human cause within a bound instead of holding forever, with preserve-before-cancel unchanged. Design recorded as scope events frwp-adopt-l77jxo-2026-11-06 and frwp-l77jxo-design-correction-2026-11-06. The second event records that a run with no verified copy is not cancelled at the bound, because that cancel would destroy the only copy (the bd-ib-svm3fe loss).

Measured: bd-ib-uq2ocd run 01M6PAS50BAVMD32HFBV8P89YR (petri, 2026-11-05) journaled run-wall-budget-held 31 times ("selective stage-diff read failed; no preserve-by-reference pointer was written") and ran 23,579 s against a 21,600 s wall. Throughout, its tree cc9568cc88a0 was on refs/heads/needs-human/01M6PAS50BAVMD32HFBV8P89YR and refs/heads/preserve/run-01M6PAS50BAVMD32HFBV8P89YR, both verified by ls-remote, and it ended only on a human-relayed cancel. The current clause is conformant behaviour, so the fix is a spec change. The latest work-in-progress capture qualifies alongside the refs the maintainer named because Scenario 317 creates it from the run branch's tip.

### Proposed Changes

Two edits. Every other sentence of the edited paragraph and scenario block is unchanged.

**1. `SPECIFICATION/contracts.md`, §"Dispatcher progress watchdog" → "The whole-run wall budget".**

Replace the paragraph

> When the export cannot be read back, the Dispatcher MUST NOT cancel the run. It MUST journal one `run-wall-budget-held` record naming the run, the elapsed seconds, the budget and the failed measurement, and MUST re-attempt the export on the next poll, cancelling only once a read-back succeeds. Scenario 175 in `scenarios.md` exercises this paragraph and the budget key of §"ACP node timeouts".

with

> When the export cannot be read back, the Dispatcher MUST NOT cancel the run on that export alone. It MUST journal one `run-wall-budget-held` record naming the run, the elapsed seconds, the budget and the failed measurement, and MUST re-attempt the export on the next poll. On each held poll it MUST also list the refs on origin with a remote ref listing (`git ls-remote`, never a local clone) and look for a *verified preservation ref* of the run: a ref that names this run, namely `refs/heads/needs-human/<run-id>`, `refs/heads/preserve/run-<run-id>`, a `refs/livespec/preserved-publish/<work-item-id>/<commit-sha>` ref the Dispatcher published for this run, or the run's latest preserved capture `refs/livespec/wip/<work-item-id>/<run-id>/<n>` (§"Dispatcher admission, WIP cap, and post-merge acceptance" → "Each committing step of a run preserves the run branch's tip to an ordered work-in-progress ref"), whose commit's tree equals the tree of the run branch `fabro/run/<run-id>`'s committed tip as the run's own record reports it. When the run's record cannot report that tip, the run's latest preserved capture or its needs-human ref qualifies on its own, because the run created each from the run branch's tip. The Dispatcher MUST cancel the run as soon as either a re-attempted export reads back or a verified preservation ref exists. A cancel released by a verified preservation ref MUST journal `run-wall-budget-exceeded` exactly as above, with that ref and its commit id in place of the preserve-by-reference pointer and a statement that the export could not be read back, and its ledger comment MUST name the same. When no verified preservation ref exists, the Dispatcher MUST NOT cancel the run, because the cancel would destroy the only copy of its work. Instead, at the third consecutive `run-wall-budget-held` record for the same run, it MUST journal one `run-wall-budget-hold-escalated` record and add one ledger comment to the item naming the run id, the factory, the elapsed seconds, the budget, each failed measurement, the statement that no verified preservation ref exists, and the remedy: a person preserves or abandons the run's work and then cancels the run. The escalation is a needs-human cause recorded once per run; it MUST NOT change the item's status while the run is live, and the Dispatcher MUST keep re-attempting the export and the ref listing on every later poll and MUST cancel as soon as either release condition holds. A remote ref listing that cannot be taken is a failed measurement of that poll, never evidence that no ref exists. Scenario 175 in `scenarios.md` exercises this paragraph and the budget key of §"ACP node timeouts".

The export-then-terminate precondition, the `run-wall-budget-exceeded` record's other fields, the blocked/needs-human rest after a cancel, and the precedence over a simultaneous stall are unchanged. The preserve-before-cancel rule is not weakened: a run is cancelled only once a read-back succeeds or a verified copy of its committed work is on origin.

**2. `SPECIFICATION/scenarios.md`, `## Scenario 175 — A run past the whole-run wall budget is exported, cancelled and rested for a human`.**

Replace the scenario `An export that cannot be read back holds the cancel until it can` with the four scenarios below. No `## ` heading is added or changed, so `tests/heading-coverage.json` needs no edit.

```gherkin
  Scenario: An export that cannot be read back holds the cancel until it can
    Given a run past the budget whose preserve-by-reference pointer cannot be read back
    And origin holds no verified preservation ref of the run
    When the watchdog samples the run
    Then it does not cancel the run
    And the journal carries a run-wall-budget-held record naming the run, the elapsed seconds, the budget and the failed measurement
    And the export is re-attempted on the immediately following poll
    And while that re-attempt's read-back fails and no verified preservation ref exists the run is still not cancelled
    And once a re-attempt's read-back succeeds the run is cancelled as run-wall-budget-exceeded
  Scenario: A verified preservation ref releases a held budget cancel
    Given a run past the budget whose preserve-by-reference pointer cannot be read back
    And a remote ref listing of origin shows refs/heads/needs-human/<run-id> at a commit whose tree equals the run branch's committed tip as the run's record reports it
    When the watchdog samples the run
    Then the run is cancelled as run-wall-budget-exceeded
    And the record and the item's ledger comment name that ref and its commit id and state that the export could not be read back
    And the item rests at blocked with blocked_reason needs-human
  Scenario: A held budget cancel with no verified copy escalates once and keeps the run
    Given a run past the budget whose export read-back has failed on three consecutive polls
    And no remote ref listing of origin shows a verified preservation ref of the run
    When the Dispatcher journals the third run-wall-budget-held record for the run
    Then the journal carries one run-wall-budget-hold-escalated record for the run
    And the item carries one ledger comment naming the run, the factory, the elapsed seconds, the budget, each failed measurement, that no verified preservation ref exists, and the remedy
    And the run is not cancelled and the item's status is unchanged
    And a later poll that finds a verified preservation ref cancels the run as run-wall-budget-exceeded without a second escalation
  Scenario: An unreadable ref listing is not an absent ref
    Given a run past the budget whose export read-back fails
    And the remote ref listing of origin cannot be taken on that poll
    When the watchdog samples the run
    Then the run-wall-budget-held record names the failed ref listing as a failed measurement
    And the run is not cancelled on that poll
```

