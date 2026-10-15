---
topic: session-headroom-burn-projection
author: claude-opus-5-5:factory-configurable-model-fallback-priority
created_at: 2026-10-15T11:47:51Z
---

## Proposal: Admission skips a covered candidate whose observed drain exhausts it before its reset

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds a burn-rate projection to the admission session-headroom filter. Beside the existing floor, a covered candidate whose valid reading passes the floor is ALSO skipped for that admission evaluation when the five-hour drain rate observed across the Dispatcher's own journaled assessments of the same credential projects that headroom to reach zero before the earlier of the provider's reported five-hour reset and a committed admission horizon. The projection is computed only from recorded assessments, so it issues no new usage request. Where no rate can be computed, the projection is journaled as unavailable and adds no skip, and the floor alone governs. Four scenarios are added to the Scenario 60 block. No new H2 heading is introduced, so tests/heading-coverage.json is unchanged.

### Motivation

Work-item bd-ib-2n2s7b, filed at the maintainer's request on 2026-10-15, and the maintainer's 06:32Z ruling placing plan factory-configurable-model-fallback-priority against the account-exhaustion failures. On 2026-10-15 the floor-only gate admitted bd-ib-dls2qt at 04:53:22Z on credential aad1734c0ce2713f (anthropic-3) reading 25 percent remaining. That is above the 20 percent floor, but the account was draining about 21 percentage points per hour. The caam loop's readings were 22 percent at 04:55Z, 10 percent at 05:37Z, 2 percent at 06:01Z, and 0 percent from about 06:05Z until the 06:30Z reset. The run (01M4YYJZESMMEWJ74AEVAMK7TP) died at proof_capture with the provider's session-limit refusal. bd-ib-kgo6f6, admitted at about 03:32Z at 52 percent, died the same way at proof_verify. A run keeps its dispatch-time credential for its whole life, so the caam loop's 04:55:44Z rotation to anthropic-4 protected neither. Admission is therefore the only point that can prevent this shape. The ratified clause already says that a reading above the floor is not evidence of availability; this change adds the one admission-time signal that distinguishes a steady account from a collapsing one. Applied to the two measured deaths, the rule projects exhaustion at about 06:04Z for dls2qt and about 06:01Z for kgo6f6, both before the 06:30Z reset, so both would have been skipped. The drain input is the per-credential five_hour_drain_percent_per_hour that ready child bd-ib-rszkjc journals. This proposal makes that figure load-bearing without adding a provider request.

### Proposed Changes

In SPECIFICATION/contracts.md, paragraph **Admission filters candidates by projected Claude session headroom.**, insert the following sentences immediately after the sentence beginning "A floor of 0 disables both kinds of headroom skip":

With a positive floor, a covered candidate whose valid reading passes the floor MUST additionally be assessed for projected exhaustion. The five-hour drain rate MUST be computed from this reading and the most recent earlier valid assessment journaled under this clause for the same opaque credential identity in the same repository whose observation time is no less than 5 minutes and no more than 90 minutes earlier. The rate is the increase in utilization percentage points divided by the elapsed hours between the two observation times. The projection is unavailable when no such earlier assessment exists, when the current utilization is lower than the earlier one (the window reset between them), or when the computed rate is not strictly positive. An unavailable projection MUST be journaled with its reason and MUST NOT skip the candidate, because the floor already governs an unprojected reading and a projection with no history would otherwise refuse every first dispatch on a credential. When the projection is available, the projected exhaustion instant is the observation time plus the remaining headroom divided by the rate, in hours. The admission horizon is a committed-only `dispatcher.session_headroom_horizon_minutes` (integer from 0 through 1440 inclusive, default **180**). It is NOT declared API-configurable, and is therefore committed-only per §"Orchestrator-owned attention facts" → "The declared-API-configurable class". The candidate MUST be skipped for this admission evaluation when its projected exhaustion instant is strictly earlier than the observation time plus the horizon AND, when the provider reported the five-hour window's reset instant with the same response as the reading, strictly earlier than that reset instant. A reset instant that is missing or malformed is unobservable, MUST be journaled as such, and leaves the horizon alone to govern. A horizon of 0 disables projection skips while retaining the computation and its journal record. The projection MUST be computed only from journaled assessments and MUST NOT issue any usage request beyond the one bounded reading this clause already requires. For each assessed credential, the journal record MUST additionally carry the drain rate or an explicit unavailable result with its reason, the earlier assessment's observation time when one was used, the projected exhaustion instant, the reset instant or an explicit unobservable result, the governing horizon, and whether a projection skip applied. A projection skip has exactly the semantics of a floor skip: it is ephemeral and candidate-local to this evaluation, per-node selection MUST continue to the next eligible candidate, a successful credential-usability probe MUST NOT override it, an emptied admission-required node leaves a ready item ready without a claim or blocked reason, and reevaluation follows the same scheduling rule. A headroom-governed refusal record and the per-node selection record MUST name a projection skip as a projection skip, distinct from a floor skip, and MUST reference the assessment carrying the projection. A projection creates NO observed availability record and retires none.

In SPECIFICATION/scenarios.md, inside the gherkin block of `## Scenario 60 — An observed provider exhaustion refuses admission, and expires`, immediately after the scenario "A disabled floor retains observation without refusing on unobservability", the following scenarios MUST be added:

```gherkin
  Scenario: A covered primary projected to exhaust before its reset selects an uncovered fallback
    Given an item whose implement node's primary is a covered candidate under the admission session-headroom clause
    And dispatcher.session_headroom_floor_percent is 15
    And dispatcher.session_headroom_horizon_minutes is 180
    And the primary credential's journaled assessment 30 minutes earlier read 64.5 percent utilization
    And its current reading is 75 percent utilization, so its remaining headroom of 25 percent passes the floor
    And the provider reports the five-hour window resets 96 minutes after the current observation
    And that node lists an uncovered eligible fallback candidate
    And every other admission condition is satisfied
    When the Dispatcher evaluates admission
    Then the journal records a drain rate of 21 percentage points per hour and a projected exhaustion about 71 minutes after the observation
    And the primary is skipped by projection, not by the floor
    And the fallback candidate is selected for the implement node
    And the selection record references the primary's assessment as a projection skip

  Scenario: A credential whose window resets before its projected exhaustion is admitted
    Given a covered candidate whose remaining headroom of 25 percent passes a floor of 15
    And a journaled drain rate of 21 percentage points per hour from an assessment 30 minutes earlier
    And the provider reports the five-hour window resets 40 minutes after the current observation
    When admission is evaluated
    Then no projection skip applies to that candidate
    And all other admission conditions are still applied

  Scenario: A first assessment of a credential has no projection and is governed by the floor alone
    Given a covered candidate whose remaining headroom passes the floor
    And no earlier assessment of its credential identity was journaled in the preceding 90 minutes
    When admission is evaluated
    Then the projection is journaled as unavailable with its reason
    And no projection skip applies to that candidate

  Scenario: A horizon of zero records the projection without skipping
    Given a covered candidate whose projected exhaustion precedes its reported reset
    And dispatcher.session_headroom_horizon_minutes is 0
    When admission is evaluated
    Then the drain rate and projected exhaustion instant are journaled
    And no projection skip applies to that candidate
```

The accompanying implementation MUST NOT read any figure from a third-party account-selection process to compute the projection; every input is the Dispatcher's own journaled assessment or the reading response it already receives.

## Proposal: Lower the default session headroom floor to 15 percent and keep it at or below an external rotation trigger

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Changes the default of `dispatcher.session_headroom_floor_percent` from 20 to 15. Adds a SHOULD that, where an external account-selection process chooses which credential the Dispatcher projects, the committed floor not exceed that process's own rotation trigger. Both thresholds are then defined against the same quantity, the account's remaining five-hour allowance, each read by its own path. The burn projection of the companion proposal carries the protection a higher floor was approximating.

### Motivation

Work-item bd-ib-2n2s7b, defect (a). The caam loop that selects the factory's Claude account rotates only when the selected account's five-hour remaining falls below 15 percent, while the gate refuses below 20 percent. Between 15 and 20 percent, the loop keeps the account selected and the gate refuses every covered candidate on it, so the factory admits nothing until the account drains past 15 percent or resets. The loop's maintainer recommends defining both thresholds against the one quantity, account five-hour utilization, and letting each side keep its own read path; this proposal does that. The gate reads the rate-limit header on the projected setup-token, and the loop reads the usage endpoint on each account's interactive login. Reconciling the two readings, for example by journaling a divergence beyond a tolerance, is deliberately NOT part of this proposal: the loop's cached reading lives in another repository's private state file whose format this specification does not govern, and the gate's own reading is already the authoritative input for admission because it is taken on the exact credential the run will use.

### Proposed Changes

In SPECIFICATION/contracts.md, paragraph **Admission filters candidates by projected Claude session headroom.**, the sentence defining the floor MUST change its default from **20** to **15**, reading: "The floor is a committed-only `dispatcher.session_headroom_floor_percent` (integer from 0 through 100 inclusive, default **15**), measured in percentage points of the five-hour usage allowance remaining, not elapsed wall-clock time."

Immediately after that sentence, insert: "When an account-selection process outside the Dispatcher chooses which subscription credential Worker credential projection supplies, and that process rotates away from an account when its five-hour remaining allowance falls below a trigger of its own, the committed floor SHOULD NOT exceed that trigger. A floor above it refuses every covered candidate on a credential the selection process still holds selected, so the factory idles until the account drains past the trigger or resets. The Dispatcher MUST NOT read that process's trigger or its usage readings to decide admission; the alignment is a property of committed configuration, and the floor and projection remain computed from the Dispatcher's own reading."

The existing Scenario 60 scenarios set the floor explicitly, so they MUST remain unchanged by this default change.
