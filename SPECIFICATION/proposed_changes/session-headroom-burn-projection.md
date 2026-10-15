---
topic: session-headroom-burn-projection
author: claude-opus-5-5:factory-configurable-model-fallback-priority
created_at: 2026-10-15T11:47:51Z
---

## Proposal: Admission skips a covered candidate whose observed drain exhausts it within the admission horizon

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds a burn-rate projection to the admission session-headroom filter. Beside the existing floor, a covered candidate whose valid reading passes the floor is ALSO skipped for that admission evaluation when the five-hour drain rate, observed between the Dispatcher's own journaled assessments of the same credential, projects that headroom to reach zero within a committed admission horizon. The projection is computed only from recorded assessments, so it issues no new usage request. Provider-reported reset instants do not govern the skip. Where no rate can be computed, the projection is journaled as unavailable and adds no skip, and the floor alone governs. The proposal states this fail-open explicitly, together with the cases where history is absent. Five scenarios are added to the Scenario 60 block. No new H2 heading is introduced, so tests/heading-coverage.json is unchanged.

### Motivation

Work-item bd-ib-2n2s7b, filed at the maintainer's request on 2026-10-15, and the maintainer's 06:32Z ruling placing plan factory-configurable-model-fallback-priority against the account-exhaustion failures.

On 2026-10-15 the floor-only gate admitted bd-ib-dls2qt at 04:53:22Z on credential aad1734c0ce2713f (anthropic-3), which read 25 percent remaining. That is above the 20 percent floor, but the account was draining about 21 percentage points per hour. The caam loop's readings were 22 percent at 04:55Z, 10 percent at 05:37Z, 2 percent at 06:01Z, and 0 percent from about 06:05Z until the 06:30Z reset. The run (01M4YYJZESMMEWJ74AEVAMK7TP) died at proof_capture with the provider's session-limit refusal. bd-ib-kgo6f6, admitted at about 03:32Z at 52 percent, died the same way at proof_verify. A run keeps its dispatch-time credential for its whole life, so the caam loop's 04:55:44Z rotation to anthropic-4 protected neither run. Admission is therefore the only point that can prevent this shape.

The ratified clause already says that a reading above the floor is not evidence of availability. This change adds the one admission-time signal that distinguishes a steady account from a collapsing one. Applied to the two measured deaths, the rule shows that dls2qt would have been skipped: journal baseline 03:34:52Z 48% -> 04:53:15Z 75%, 20.7 pt/h, exhaustion 06:05:51Z. kgo6f6, the first journaled assessment of that credential in its dispatching checkout, would have had no projection and remains the case the floor alone governs.

The drain input is the per-credential five_hour_drain_percent_per_hour that ready child bd-ib-rszkjc journals. This clause defines that field; where bd-ib-rszkjc's definition differs, this clause governs. This proposal makes that figure load-bearing without adding a provider request.

Provider-reported reset instants are deliberately not used to admit. The maintainer's recorded decision on this plan, in scope events of 2026-09-09 and 2026-09-30, treats provider-reported reset times as untrusted, and contracts.md already refuses to let a provider-stated reset instant schedule or shorten anything. The reading response has, so far, carried only the anthropic-ratelimit-unified-5h-utilization header. A reset leg would make an unverified provider timing claim load-bearing in the admit direction.

### Proposed Changes

In SPECIFICATION/contracts.md, paragraph **Admission filters candidates by projected Claude session headroom.**, insert the following sentences immediately after the sentence beginning "A floor of 0 disables both kinds of headroom skip":

With a positive floor, a covered candidate whose valid reading passes the floor MUST additionally be assessed for projected exhaustion. The five-hour drain rate MUST be computed from this reading and a baseline. The baseline is the EARLIEST assessment carrying a valid reading journaled under this clause for the same opaque credential identity in the dispatching checkout's dispatch journal, read regardless of the work-item it was journaled for, whose observation time is no less than 15 minutes and no more than 90 minutes earlier. The rate is the increase in utilization percentage points divided by the elapsed hours between the baseline's observation time and this one.

The projection is unavailable when no such baseline exists, or when this reading's utilization is not higher than the baseline's (a window reset or a provider correction occurred between them). An unavailable projection MUST be journaled with its reason and MUST NOT skip the candidate. The floor already governs an unprojected reading, and a projection with no history would otherwise refuse every first dispatch on a credential.

The assessment history is per checkout, because it is the dispatching checkout's own dispatch journal. A projection is therefore unavailable in at least these cases: the credential was not assessed in that checkout during the preceding 90 minutes, the journal was removed, or the dispatch runs from another checkout or worktree whose journal holds no assessment of that credential. Each such case is a deliberate fail-open of the projection only, and the floor still applies.

When the projection is available, the projected exhaustion instant is the observation time plus the remaining headroom divided by the rate, in hours. The admission horizon is a committed-only `dispatcher.session_headroom_horizon_minutes` (integer from 0 through 1440 inclusive, default **180**). It is NOT declared API-configurable, and is therefore committed-only per §"Orchestrator-owned attention facts" → "The declared-API-configurable class". The candidate MUST be skipped for this admission evaluation when its projected exhaustion instant is strictly earlier than the observation time plus the horizon. A horizon of 0 disables projection skips while retaining the computation and its journal record. A reset instant the response carries MAY be journaled as an unverified provider claim and MUST NOT change the projection skip.

The projection MUST be computed only from journaled assessments and MUST NOT issue any usage request beyond the one bounded reading this clause already requires.

For each assessed credential, the journal record MUST additionally carry exactly one projection result:
- the drain rate, the baseline's observation time, the projected exhaustion instant, the governing horizon, and whether a projection skip applied;
- or an explicit `unavailable` result with its reason;
- or an explicit `not-projected` result when no projection was attempted because the floor is 0, the reading was skipped by the floor, or the reading was unobservable.

`not-projected` and `unavailable` MUST remain distinct values.

A projection skip has exactly the semantics of a floor skip:
- it is ephemeral and candidate-local to this evaluation;
- per-node selection MUST continue to the next eligible candidate;
- a successful credential-usability probe MUST NOT override it;
- an emptied admission-required node leaves a ready item ready without a claim or blocked reason;
- reevaluation follows the same scheduling rule.

A headroom-governed refusal record and the per-node selection record MUST name a projection skip as a projection skip, distinct from a floor skip, and MUST reference the assessment carrying the projection. A projection creates NO observed availability record and retires none.

In the same file, the sentence "A headroom-governed refusal MUST additionally name the assessed credential identity, reading or explicit unobservable result, observation time, governing floor, and skipped candidates for the admission-required node lacking an eligible candidate." MUST become "A headroom-governed refusal MUST additionally name the assessed credential identity, reading or explicit unobservable result, observation time, governing floor and governing horizon, the projection result, and skipped candidates for the admission-required node lacking an eligible candidate."

In the same file, under **Per-node selection.**, the sentence "When headroom skips an earlier candidate, the selection record MUST identify that candidate and reference its headroom assessment and governing floor; it MUST NOT represent that skip as an observed hold." MUST become "When headroom skips an earlier candidate, the selection record MUST identify that candidate, reference its headroom assessment, governing floor and governing horizon, and state whether the skip was a floor skip or a projection skip; it MUST NOT represent that skip as an observed hold."

In SPECIFICATION/scenarios.md, inside the gherkin block of `## Scenario 60 — An observed provider exhaustion refuses admission, and expires`, immediately after the scenario "A disabled floor retains observation without refusing on unobservability", the following scenarios MUST be added:

```gherkin
  Scenario: A covered primary projected to exhaust within the horizon selects an uncovered fallback
    Given an item whose implement node's primary is a covered candidate under the admission session-headroom clause
    And dispatcher.session_headroom_floor_percent is 20
    And dispatcher.session_headroom_horizon_minutes is 180
    And the earliest assessment of the primary credential journaled between 15 and 90 minutes earlier, for any work-item, read 64.5 percent utilization 30 minutes earlier
    And its current reading is 75 percent utilization, so its remaining headroom of 25 percent passes the floor
    And that node lists an uncovered eligible fallback candidate
    And every other admission condition is satisfied
    When the Dispatcher evaluates admission
    Then the journal records a drain rate of 21 percentage points per hour and a projected exhaustion about 71 minutes after the observation
    And the primary is skipped by projection, not by the floor
    And the fallback candidate is selected for the implement node
    And the selection record references the primary's assessment, the governing floor and the governing horizon as a projection skip

  Scenario: A projected exhaustion beyond the horizon is admitted, and a provider reset claim changes nothing
    Given a covered candidate whose remaining headroom of 25 percent passes a floor of 20
    And its baseline assessment 30 minutes earlier read 72 percent utilization, so the drain rate is 6 percentage points per hour
    And dispatcher.session_headroom_horizon_minutes is 180
    And the reading response carries a provider reset instant 10 minutes away
    When admission is evaluated
    Then the projected exhaustion is about 250 minutes after the observation and no projection skip applies
    And the reset instant is not used for the skip and, if journaled, only as an unverified provider claim
    And all other admission conditions are still applied

  Scenario: A credential with no baseline in this checkout is governed by the floor alone
    Given a covered candidate whose remaining headroom passes the floor
    And this checkout's dispatch journal holds no assessment of its credential identity between 15 and 90 minutes earlier
    When admission is evaluated
    Then the projection is journaled as unavailable with its reason
    And no projection skip applies to that candidate

  Scenario: A reading no higher than its baseline has no projection
    Given a covered candidate whose remaining headroom passes the floor
    And its baseline assessment within the window read a utilization equal to or higher than the current reading
    When admission is evaluated
    Then the projection is journaled as unavailable with its reason
    And no projection skip applies to that candidate

  Scenario: A horizon of zero records the projection without skipping
    Given a covered candidate whose projected exhaustion falls within 180 minutes of its observation
    And dispatcher.session_headroom_horizon_minutes is 0
    When admission is evaluated
    Then the drain rate and projected exhaustion instant are journaled
    And no projection skip applies to that candidate
```

The accompanying implementation MUST NOT read any figure from a third-party account-selection process to compute the projection; every input is the Dispatcher's own journaled assessment or the reading response it already receives.

## Proposal: Align an external rotation trigger with the session headroom floor by configuration

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Leaves the default of `dispatcher.session_headroom_floor_percent` at 20. Adds a SHOULD that, where an external account-selection process rotates away from an account below a five-hour trigger of its own, the trigger and the committed floor be aligned by configuration, with neither below the other. The Dispatcher MUST NOT read that process's trigger or readings. Both thresholds are then defined against the same quantity, the account's remaining five-hour allowance, each read by its own path.

### Motivation

Work-item bd-ib-2n2s7b, defect (a). The caam loop that selects the factory's Claude account rotates only when the selected account's five-hour remaining falls below 15 percent, while the gate refuses below 20 percent. Between 15 and 20 percent, the loop keeps the account selected and the gate refuses every covered candidate on it, so the factory admits nothing until the account drains past 15 percent or resets.

Lowering the floor to 15 was considered and rejected. With no journaled history, a 16 percent credential is refused today and would be admitted at a floor of 15 with its projection unavailable. The first evaluation after a quiet spell, a removed journal, or a different checkout is the common case, so the floor must keep carrying that protection. The band is closed instead from the selection side, by raising the external trigger to the floor; that change is routed to the selection process's own repository.

The loop's maintainer recommends defining both thresholds against the one quantity, account five-hour utilization, with each side keeping its own read path, and this proposal does that. The gate reads the rate-limit header on the projected setup-token. The loop reads the usage endpoint on each account's interactive login.

Reconciling the two readings, for example by journaling a divergence beyond a tolerance, is deliberately NOT part of this proposal. The loop's cached reading lives in another repository's private state file, whose format this specification does not govern. The gate's own reading is already the authoritative input for admission, because it is taken on the exact credential the run will use.

### Proposed Changes

In SPECIFICATION/contracts.md, paragraph **Admission filters candidates by projected Claude session headroom.**, the floor's default MUST remain **20**. Immediately after the sentence defining `dispatcher.session_headroom_floor_percent`, insert: "When an account-selection process outside the Dispatcher rotates away from an account when its five-hour remaining allowance falls below a trigger of its own, that trigger SHOULD NOT be below the committed floor, and the committed floor SHOULD NOT exceed it; an operator aligns the two by configuration, and the Dispatcher MUST NOT read that process's trigger or readings. A misaligned pair leaves a band in which the selection process holds an account the Dispatcher refuses, so the factory idles until the account drains past the trigger or resets."

The existing Scenario 60 scenarios set the floor explicitly and MUST remain unchanged.
