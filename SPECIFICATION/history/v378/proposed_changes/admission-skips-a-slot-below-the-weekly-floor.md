---
topic: admission-skips-a-slot-below-the-weekly-floor
author: claude-opus-5-5
created_at: 2026-11-14T15:03:13Z
---

## Proposal: Admission skips a pool slot whose weekly remaining headroom is below a committed weekly floor

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Session-headroom admission MUST also refuse to qualify a Claude pool slot whose seven-day remaining headroom is strictly below a new committed-only weekly floor, `dispatcher.session_headroom_weekly_floor_percent` (integer 0 through 100, default 10). Today only the five-hour window is compared against a floor; the seven-day arm skips only on a provider-reported `rejected` status, so admission chooses a slot at 99 percent weekly utilization whenever the provider still reports `allowed_warning`, and the run dies mid-flight on the weekly limit. The new skip is a seven-day floor skip, journaled distinctly; it only removes slots from the qualifying set and does not change the ranking among qualifying slots. An absent or unparseable seven-day utilization is not skipped by it, a weekly floor of 0 disables only it, and a five-hour floor of 0 disables it with every other headroom skip.

### Motivation

MEASURED 2026-11-14 in the livespec tenant's dispatch journal (/data/projects/livespec/tmp/fabro-dispatch-journal.jsonl): the acp-session-headroom assessment at 14:44:33Z for livespec-57r6qo CHOSE slot CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_1 while its seven-day reading was status `allowed_warning`, utilization_percent 99.0, and its five-hour window was `five-hour-window-absent`, so it qualified. Run 01M7D8AHQKYTXHBEJS8CWA047Q (petri) then failed at proof_capture@1 at 14:50:03Z with 'You've hit your weekly limit · resets Nov 19, 5pm (UTC)' and the item went to needs-human, after implement, janitor and review had been spent. That is within the ratified text: contracts.md says a warning status or a utilization below 100 is not exhaustion, and the only floor reads the five-hour window. At about 14:55Z legacy-coordinator-agent reported the factory pool's weekly allowance left as 0 percent on ANTHROPIC_0, _1 and _2, 6 percent on _5, 2 percent on _6, 66 percent on _3 and 100 percent on _4, with _5 and _6 next in rank after _1. No committed setting could keep admission off the near-exhausted slots, so placements were paused and an interim `env -u` narrowing of the dispatcher's injected slots was ruled. An earlier instance of the same class: gmktec run 01M580PF02S0 (bd-ib-fubkcv) failed proof_verify@3 after 6h02m on 'You've hit your weekly limit' (recorded on bd-ib-u3jq5r). bd-ib-u3jq5r (v182) introduced the status-only seven-day arm and left 'a floor or projection for the weekly allowance' as an open design question; this proposal answers it with a floor. Default 10: it matches the weekly-remaining threshold below which the caam rotation loop already rotates interactive spend (bd-ib-2n2s7b records that loop's 'weekly-remaining < 10%' rule), so the factory and the interactive loop stop treating an account as usable at the same weekly level. DE-RANKING DECIDED AGAINST: the floor skips but does not de-rank a slot near it. Every measured failure sat far below 10 percent (1, 2 and 6 percent remaining); de-ranking would add a second threshold with no measurement behind it and would trade away the ranking's purpose, using the soonest-expiring quota first. Reconsider de-ranking only if a run admitted on a slot just above the floor is measured dying on its weekly limit. Scope: the orchestrator only, since admission lives here. Codex candidates are outside this clause's coverage and keep their own window rules (Scenario 243). Whether the factory may use the account the caam loop selected for interactive spend is a separate maintainer question and is not part of this proposal. Routed by legacy-coordinator-agent (session 9b979c55) on 2026-11-14 as the root fix for the interim slot narrowing; owner fabro-currency plan seat. In-flight alignment: default-align; no open spec pull request touches the session-headroom clause (surveyed 2026-11-14 ~15:05Z: #5284, #5281, #5280, #5260, #5257, #5180, #5120, #5083, #5061, #5048, #5005).

### Proposed Changes

Four edits. No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.

**Edit 1 — `SPECIFICATION/contracts.md`, the paragraph that begins **Admission filters candidates by projected Claude session headroom.**** In the sentence that begins "With a positive floor, a slot QUALIFIES when", replace

> and, in both cases, its seven-day status is not exhausted and its projection does not call for a projection skip.

with

> and, in both cases, its seven-day status is not exhausted, it does not call for a seven-day floor skip under the weekly floor below, and its projection does not call for a projection skip.

**Edit 2 — same paragraph.** In the sentence that begins "Every assessment's journal record MUST name the chosen slot's opaque non-secret credential identity", replace

> a floor skip, a seven-day skip, a projection skip, an unobservable reading, or a qualifying slot ranked lower,

with

> a floor skip, a seven-day skip, a seven-day floor skip, a projection skip, an unobservable reading, or a qualifying slot ranked lower,

**Edit 3 — same paragraph.** Immediately AFTER the sentence "An absent, unparseable or unrecognised seven-day reading MUST NOT skip a candidate." and BEFORE the sentence that begins "The journal record of each assessment MUST carry the seven-day utilization percentage", insert:

> The definition of seven-day exhaustion above is unchanged by the weekly floor. Seven-day remaining headroom equals 100 minus the provider's seven-day utilization percentage, and a valid seven-day utilization is a finite number from 0 through 100 inclusive. With a positive floor and a positive weekly floor, a pool slot whose valid seven-day remaining headroom is strictly below the weekly floor MUST NOT qualify, whatever its seven-day status and whether or not its five-hour window is absent; equality passes. This is a seven-day floor skip. It is a headroom skip with exactly the semantics of a floor skip, and the assessment's journal record, a headroom-governed refusal record and the per-node selection record MUST name it as a seven-day floor skip, distinct from a seven-day skip, a floor skip and a projection skip. When a slot calls for both a seven-day skip and a seven-day floor skip, it MUST be named as a seven-day skip. A slot whose seven-day utilization is absent, unparseable or out of range MUST NOT be skipped by the weekly floor. The weekly floor MUST only remove slots from the qualifying set and MUST NOT change the ranking among qualifying slots. The weekly floor is a committed-only `dispatcher.session_headroom_weekly_floor_percent` (integer from 0 through 100 inclusive, default **10**), measured in percentage points of the seven-day allowance remaining. It is NOT declared API-configurable, and is therefore committed-only per §"Orchestrator-owned attention facts" → "The declared-API-configurable class". A weekly floor of 0 disables only the seven-day floor skip, and a floor of 0 disables it together with every other headroom skip. The weekly floor creates no observed availability record and retires none.

**Edit 4 — `SPECIFICATION/scenarios.md`, §"Scenario 231 — Admission skips a Claude candidate whose seven-day allowance is exhausted".** Append these scenarios to the end of that scenario's Gherkin block, inside the same fenced block, after the scenario "A floor of 0 disables the seven-day skip". The scenario's heading is unchanged.

```gherkin
  Scenario: A slot below the weekly floor does not qualify even with a warning status
    Given dispatcher.session_headroom_floor_percent is 20 and dispatcher.session_headroom_weekly_floor_percent is 10
    And a pool slot A whose five-hour window is absent and whose seven-day status is allowed_warning at a seven-day utilization of 99
    And a pool slot B whose five-hour remaining headroom is above the floor and whose seven-day utilization is 0
    And slot B's projection is unavailable, its response carries no reset instant, and slot A's name sorts before slot B's, so slot A would otherwise rank first
    When admission assesses the pool
    Then slot A is not chosen and its assessment names a seven-day floor skip
    And slot B is chosen and every covered candidate of the dispatch projects slot B

  Scenario: A slot exactly at the weekly floor qualifies
    Given dispatcher.session_headroom_floor_percent is 20 and dispatcher.session_headroom_weekly_floor_percent is 10
    And a pool slot whose five-hour remaining headroom is above the floor and whose seven-day utilization is 90
    When admission assesses the pool
    Then the slot qualifies and no seven-day floor skip applies

  Scenario: An absent seven-day utilization is not skipped by the weekly floor
    Given dispatcher.session_headroom_floor_percent is 20 and dispatcher.session_headroom_weekly_floor_percent is 10
    And a pool slot whose five-hour remaining headroom is above the floor and whose provider response carries no seven-day utilization, or one that is unparseable or outside 0 through 100
    When admission assesses the pool
    Then no seven-day floor skip applies and the seven-day reading is journaled as unobservable

  Scenario: A weekly floor of 0 disables only the seven-day floor skip
    Given dispatcher.session_headroom_floor_percent is 20 and dispatcher.session_headroom_weekly_floor_percent is 0
    And a pool slot whose five-hour remaining headroom is above the floor and whose seven-day status is allowed_warning at a seven-day utilization of 99
    And another pool slot whose seven-day status is rejected
    When admission assesses the pool
    Then the first slot qualifies
    And the second slot is still skipped by a seven-day skip

  Scenario: When every slot is below the weekly floor the covered candidate falls back
    Given dispatcher.session_headroom_floor_percent is 20 and dispatcher.session_headroom_weekly_floor_percent is 10
    And every pool slot's seven-day remaining headroom is below 10
    And an admission-required node whose primary is a covered claude-acp candidate and whose fallback is an eligible codex-acp candidate
    When admission assesses the node
    Then no pool slot qualifies and the claude-acp candidate is skipped
    And per-node selection selects the codex-acp fallback

  Scenario: A floor of 0 disables the seven-day floor skip
    Given dispatcher.session_headroom_floor_percent is 0 and dispatcher.session_headroom_weekly_floor_percent is 10
    And a pool slot whose seven-day utilization is 99
    When admission assesses the pool
    Then no seven-day floor skip applies, the slot qualifies, and the seven-day reading is still journaled

  Scenario: A rejected slot is named a seven-day skip, not a seven-day floor skip
    Given dispatcher.session_headroom_floor_percent is 20 and dispatcher.session_headroom_weekly_floor_percent is 10
    And a pool slot whose five-hour remaining headroom is above the floor and whose seven-day status is rejected at a seven-day utilization of 100
    When admission assesses the pool
    Then the slot does not qualify and its assessment names a seven-day skip, not a seven-day floor skip
```
