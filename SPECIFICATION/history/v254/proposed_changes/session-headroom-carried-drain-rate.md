---
topic: session-headroom-carried-drain-rate
author: claude-opus-5-5
created_at: 2026-10-17T19:51:31Z
---

## Proposal: Carry the last valid drain rate forward when bunched readings leave no baseline

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The session-headroom projection currently fails open whenever no assessment of the credential falls between 15 and 90 minutes earlier. That happens not only on a credential's first dispatch, but also whenever a checkout's readings bunch inside 15 minutes after the last in-window reading has aged past 90 minutes. This proposal keeps the first-dispatch fail-open. It adds one fallback: when no baseline exists, the projection uses the drain rate carried by the most recent projected assessment of the same credential observed within the preceding 90 minutes, provided no reading since that assessment shows a reset. The record marks the rate as carried and names the assessment it came from.

### Motivation

Measured 2026-10-17 in livespec-orchestrator-beads-fabro on plugin build 047d2403eaeb (v0.211.0), recorded by the freeze driver as finding F-ab. Four consecutive assessments of one credential (opaque identity 559647e88ffce97f), in observation order:

| Observed | Work-item | Utilization | Drain rate (points/hour) | Baseline | Projected exhaustion | Result |
|---|---|---|---|---|---|---|
| 19:27:17Z | bd-ib-qgcpoc | 57 | 22.45 | 17:59:06Z | 21:22:11Z | projection skip |
| 19:29:57Z | bd-ib-yw7otf | 58 | 22.97 | 18:03:44Z | 21:19:40Z | projection skip |
| 19:32:08Z | bd-ib-qgcpoc | 59 | 23.08 | 18:03:44Z | 21:18:44Z | projection skip |
| 19:37:11Z | bd-ib-yw7otf | 61 | none | none | none | unavailable (no-baseline), admitted |

At 19:37:11Z the baseline window ran from 18:07:11Z to 19:22:11Z. The 18:03:44Z reading had just aged past 90 minutes, and every later reading (19:27Z onward) was under 15 minutes old. So no baseline existed, the projection was journaled unavailable, and the item was admitted. Utilization had meanwhile RISEN from 58 to 61 at about 23 points per hour, and exhaustion was still projected about 100 minutes away, inside the 180-minute horizon. The brake opened exactly when it was most needed, and the cause was only that dispatch readings had bunched. The clause's stated reason for the fail-open, that "a projection with no history would otherwise refuse every first dispatch on a credential", does not apply here: the checkout held a valid rate measured five minutes earlier. Carrying that rate forward would have projected exhaustion at about 19:37:11Z plus 39/23.08 hours, about 101 minutes, which is a projection skip under the 180-minute horizon. Interim mitigation until this lands: the 20 percent floor remains the hard brake, and gated retries every 900 seconds keep a reading inside the window.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Dispatcher admission, WIP cap, and post-merge acceptance", paragraph "Admission filters candidates by projected Claude session headroom":

1. Replace the sentence "The projection is unavailable when no such baseline exists, or when this reading's utilization is not higher than the baseline's (a window reset or a provider correction occurred between them)." with:

"When no such baseline exists, the Dispatcher MUST use a carried rate: the drain rate journaled by the most recent assessment of the same opaque credential identity in the dispatching checkout's dispatch journal whose projection result carried a drain rate, whose observation time is no more than 90 minutes earlier, and whose utilization is not higher than this reading's. A carried rate MUST NOT be used when any assessment of that credential journaled after the carried assessment reads a lower utilization than the carried assessment (a window reset or a provider correction occurred since). The projection is unavailable when neither a baseline nor a carried rate exists, or when this reading's utilization is not higher than the baseline's (a window reset or a provider correction occurred between them)."

2. Replace "A projection is therefore unavailable in at least these cases: the credential was not assessed in that checkout during the preceding 90 minutes," with "A projection is therefore unavailable in at least these cases: the credential carried no valid reading and no drain rate in that checkout during the preceding 90 minutes,". The remainder of that sentence and the sentence "Each such case is a deliberate fail-open of the projection only, and the floor still applies." MUST remain unchanged.

3. In the sentence beginning "For each assessed credential, the journal record MUST additionally carry exactly one projection result:", after "the drain rate, the baseline's observation time, the projected exhaustion instant, the governing horizon, and whether a projection skip applied;" insert: "for a carried rate, the record MUST name the rate source as `carried` and MUST carry the carried assessment's observation time in place of the baseline's, and a projection skip taken on a carried rate MUST be named as a projection skip exactly as one taken on a measured rate;". A carried projection skip MUST have exactly the semantics of every other projection skip, and the horizon, the floor and the skip scheduling rules MUST apply to it unchanged.

In SPECIFICATION/scenarios.md, "## Scenario 60 — An observed provider exhaustion refuses admission, and expires" (the heading is unchanged, so tests/heading-coverage.json needs no change):

4. Replace the sub-scenario "A credential with no baseline in this checkout is governed by the floor alone" with:

```gherkin
  Scenario: A credential with no baseline and no carried rate in this checkout is governed by the floor alone
    Given a covered candidate whose remaining headroom passes the floor
    And this checkout's dispatch journal holds no assessment of its credential identity between 15 and 90 minutes earlier
    And no assessment of that credential within the preceding 90 minutes carried a drain rate
    When admission is evaluated
    Then the projection is journaled as unavailable with its reason
    And no projection skip applies to that candidate
```

5. Add, directly after it, a sub-scenario that MUST be satisfied:

```gherkin
  Scenario: Readings bunched inside 15 minutes carry the last measured drain rate forward
    Given dispatcher.session_headroom_floor_percent is 20
    And dispatcher.session_headroom_horizon_minutes is 180
    And this checkout's dispatch journal holds no assessment of the primary credential between 15 and 90 minutes earlier
    And an assessment of that credential 5 minutes earlier read 59 percent utilization and journaled a drain rate of 23 percentage points per hour
    And the current reading is 61 percent utilization, so its remaining headroom of 39 percent passes the floor
    When the Dispatcher evaluates admission
    Then the journal records the drain rate of 23 percentage points per hour with rate source carried and the earlier assessment's observation time
    And the projected exhaustion is about 102 minutes after the observation
    And the primary is skipped by projection, not by the floor

  Scenario: A reset since the carried assessment withholds the carried rate
    Given this checkout's dispatch journal holds no assessment of the primary credential between 15 and 90 minutes earlier
    And an assessment of that credential 40 minutes earlier journaled a drain rate at 80 percent utilization
    And a later assessment of that credential read 5 percent utilization
    When admission is evaluated
    Then no carried rate is used
    And the projection is journaled as unavailable with its reason
    And no projection skip applies to that candidate
```
