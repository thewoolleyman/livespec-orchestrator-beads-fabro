---
topic: codex-floor-reset-proximity
author: claude-opus-5-5:plan-anthropic-burn-mitigation
created_at: 2026-11-02T19:29:28Z
spec_commitments:
  impl_followups:
    - id_hint: codex-floor-reset-proximity
      description: |
        Make the Codex usage-window floor reset-aware. Take each valid window's reset_at from the one bounded usage read. Compare each window against its own effective floor: the committed floor, except min(committed floor, 5) when that window's reset_at is within 12 hours of the reading's observation time, inclusive. Journal each window's effective floor and reset instant, and add tests for both arms and the boundary. The Claude clause and its floor are unchanged.
---

## Proposal: The Codex floor relaxes to 5 percent for a usage window within 12 hours of its reset

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Admission compares each Codex usage window against its own effective floor. That floor is the committed dispatcher.session_headroom_floor_percent, except when the provider reports that the window resets within 12 hours of the reading. Then the floor is the smaller of the committed floor and 5. This lets the factory spend most of a weekly Codex allowance that would otherwise expire unused, instead of falling back to Claude, while 5 percent stays in reserve for the interactive Codex seats. The Claude session-headroom clause and its floor are unchanged.

### Motivation

The maintainer approved this through coordinator ruling R301 on 2026-11-02 at about 19:3xZ. The recommendation: "keep it at 20% until about 12 hours before the reset (around 19:30Z tomorrow), then drop it to 5% to use most of the rest. The 5% that's left protects the interactive Codex seats, such as the Hetzner seat, from running out. Paid credits are never touched, because the floor only decides when work falls back to Sonnet." On 2026-11-02 at 19:22Z the weekly window was 46 percent used and resets at 2026-11-04T07:31:30Z. Headroom left unspent at the reset is lost, and every dispatch the brake moves onto Sonnet is Anthropic spend that plan anthropic-burn-mitigation (epic bd-ib-b2jzxw) exists to cut. The coordinator directed that the relaxation be driven by the provider's reported reset instant, not by an operator editing the floor on a clock. Editing the floor would not work anyway. The one committed floor also governs the Claude clause, and the current clause says a reset instant "MUST NOT change any skip", so the change has to be ratified here first.

### Proposed Changes

In `contracts.md`, §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Provider spend containment" → **Admission filters Codex candidates by projected usage-window headroom**:

1. In the first paragraph, the sentence that begins "From the response the Dispatcher MUST take" MUST additionally take, for each present non-null window, its `reset_at`. A window's `reset_at` is usable when it is a positive integer of epoch seconds. A missing or unusable `reset_at` MUST NOT make the window or the reading invalid or unobservable; it only withholds that window's relaxation (item 2). The final sentence, "The governing remaining headroom of a valid reading is the smallest remaining headroom among its windows.", MUST be kept. It MUST be followed by: "Each valid window has an effective floor. When the committed floor is positive and the window's usable `reset_at` is no more than 43,200 seconds (12 hours) after the reading's observation time, the effective floor is the smaller of the committed floor and 5. Otherwise it is the committed floor. A window with no usable `reset_at`, or whose `reset_at` is at or before the observation time, takes the committed floor. The 12-hour reset proximity and the relaxed floor of 5 are fixed by this clause and introduce no configuration key."

2. In the second paragraph, the floor-skip condition "or the governing remaining headroom is strictly below the floor (a floor skip)" MUST be replaced by "or any valid window's remaining headroom is strictly below that window's effective floor (a floor skip)". "Equality passes the floor" MUST then apply per window against its effective floor. The floor of 0 that disables every skip is the COMMITTED floor, and a relaxed effective floor MUST NOT be read as 0. Wherever the paragraph states that a reading "passes the floor", it MUST mean that every valid window passes its effective floor. The `floor-skip` not-projected reason MUST be read the same way.

3. In the third paragraph, the sentence "A reset instant the response carries MAY be journaled as an unverified provider claim and MUST NOT change any skip." MUST be replaced by: "A window's `reset_at` changes a skip ONLY through that window's effective floor. It MUST NOT change the Codex limit skip, the unobservable floor skip, the projection skip, the horizon, or any Claude assessment. For each window the journal MUST additionally carry its `reset_at` (or an explicit absent or unusable result), its effective floor, and whether that floor was relaxed by reset proximity." The remaining sentences of that paragraph are unchanged.

4. The Claude clause, **Admission filters candidates by projected Claude session headroom**, MUST NOT change. Its floor remains the committed `dispatcher.session_headroom_floor_percent`, so one committed value of 20 still yields a Claude floor of 20 while a Codex window within 12 hours of its reset is assessed against 5.

In `scenarios.md`, in `## Scenario 243 — Admission skips a Codex candidate whose usage window is short of headroom` (the H2 heading itself MUST stay unchanged, so `tests/heading-coverage.json` needs no edit), the following scenarios MUST be appended to its gherkin feature:

```gherkin
  Scenario: A Codex window within 12 hours of its reset is assessed against a floor of 5
    Given dispatcher.session_headroom_floor_percent is 20
    And an admission-required node whose primary is a covered codex-acp candidate and whose fallback is an eligible claude-acp candidate
    And the Codex usage read reports a primary window used_percent of 90 whose reset_at is 11 hours after the observation time
    When admission assesses the node
    Then the primary window's effective floor is 5 and is journaled as relaxed by reset proximity
    And the codex-acp candidate is not skipped by a floor skip

  Scenario: A Codex window more than 12 hours from its reset keeps the committed floor
    Given dispatcher.session_headroom_floor_percent is 20
    And a covered codex-acp candidate whose usage read reports a primary window used_percent of 90 whose reset_at is 13 hours after the observation time
    When admission assesses the candidate
    Then the primary window's effective floor is 20 and is journaled as not relaxed
    And the candidate is skipped by a floor skip naming provider codex

  Scenario: A Codex window exactly 12 hours from its reset is relaxed
    Given dispatcher.session_headroom_floor_percent is 20
    And a covered codex-acp candidate whose usage read reports a primary window used_percent of 90 whose reset_at is exactly 43200 seconds after the observation time
    When admission assesses the candidate
    Then the primary window's effective floor is 5
    And the candidate is not skipped by a floor skip

  Scenario: A relaxed Codex window still refuses below 5 percent, and the Claude floor is unchanged
    Given dispatcher.session_headroom_floor_percent is 20
    And a covered codex-acp candidate whose usage read reports a primary window used_percent of 96 whose reset_at is 2 hours after the observation time
    And a covered claude-acp candidate whose Claude session headroom reading is 15 percent remaining
    When admission assesses both candidates
    Then the codex-acp candidate is skipped by a floor skip against an effective floor of 5
    And the claude-acp candidate is skipped by a floor skip against the committed floor of 20

  Scenario: A Codex window with no usable reset_at keeps the committed floor
    Given dispatcher.session_headroom_floor_percent is 20
    And a covered codex-acp candidate whose usage read reports a valid primary window used_percent of 90 with no reset_at
    When admission assesses the candidate
    Then the reading is valid and the primary window's reset_at is journaled as absent
    And the candidate is skipped by a floor skip against the committed floor of 20
```
