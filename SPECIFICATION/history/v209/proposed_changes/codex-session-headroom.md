---
topic: codex-session-headroom
author: claude-opus-5-5
created_at: 2026-10-24T22:17:49Z
---

## Proposal: Admission filters Codex candidates by projected usage-window headroom

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Admission today assesses session headroom only for Claude candidates, so a chain whose primary is codex-acp reaches its Claude fallback only after a run has already met the Codex limit mid-turn and lost its in-flight work. This proposal adds a sibling clause that covers codex-acp candidates, binds them to the Codex worker credential the dispatch projects, reads the provider's usage windows through one bounded read per credential per evaluation, and applies the same floor, explicit-exhaustion and projection skips the Claude clause applies, with the same journaling and the same fail-open rules for an unavailable projection. It also names the new clause in the Dispatcher's list of admission conditions and adds Scenario 242.

### Motivation

Work-item bd-ib-4jdgcw. On 2026-10-24 this repository routed implement, fix, review and the proof nodes Codex-primary (PR 3592) and the fleet still routes Codex in other repositories. Measured on dispatch e7733d07ffbd43fd8112d63eff7fbf4f (bd-ib-3kqdln, 21:11:24Z): no codex-acp candidate carried any headroom assessment, while claude-opus-5 was headroom-skipped on dod_gate and review_fix. The code matches the ratified clause: _acp_session_headroom.headroom_covers_candidate covers only claude-acp and Anthropic-domain built-ins, and the usage reader reads only Anthropic headers. The clause itself says other agents are outside its coverage and that extending coverage requires an explicit authentication binding, which this proposal supplies. A token-spend projection measured Codex draining at 3.0 points per hour with exhaustion projected days before its reset, and the maintainer ruled proactive Codex headroom a stability fix. The usage read is measured: a read-only GET of https://chatgpt.com/backend-api/wham/usage authenticated by the host Codex credential's access token and ChatGPT account id answered 200 on 2026-10-24 with rate_limit.allowed, rate_limit.limit_reached, rate_limit.primary_window {used_percent 18, limit_window_seconds 604800, reset_after_seconds, reset_at}, a null secondary_window, and a separate credits block. The Codex CLI's own session snapshots report the same primary window (used_percent, window_minutes 10080). In-flight alignment: the pending session-headroom-baseline and session-headroom-carried-drain-rate proposals refine how the Claude projection chooses its baseline; this proposal ALIGNS with both by applying the Claude clause's baseline and drain-rate rules to Codex readings unchanged, so whatever either ratifies governs both providers.

### Proposed Changes

In `contracts.md`, immediately after the paragraph that begins **Admission filters candidates by projected Claude session headroom.**, insert a new paragraph:

**Admission filters Codex candidates by projected usage-window headroom.** For this clause, a covered candidate is a structured candidate whose resolved agent id is `codex-acp` and whose execution uses the Codex worker credential supplied by Worker credential projection. That projected credential snapshot is this clause's authentication binding. Coverage MUST follow resolved agent provenance and actual credential projection, never display text, a model-name prefix, or a spelling inferred from an opaque availability or candidate key. Before claim and final per-node selection, the Dispatcher MUST assess every otherwise-selectable covered candidate on an admission-required ACP node, including covered fallbacks. For each distinct projected Codex credential per admission evaluation, the Dispatcher MUST issue exactly one bounded usage read to the provider's account usage endpoint, `https://chatgpt.com/backend-api/wham/usage`, authenticated by that snapshot's access token and account identifier, and MUST reuse that one reading across every node and candidate sharing the credential. The read MUST have a finite implementation-defined timeout and MUST NOT run a model turn or spend any model allowance. From the response the Dispatcher MUST take `rate_limit.allowed`, `rate_limit.limit_reached`, and, for each of `rate_limit.primary_window` and `rate_limit.secondary_window` that is present and non-null, its `used_percent` and `limit_window_seconds`. A window's remaining headroom equals 100 minus its `used_percent`; a valid window reading is a finite numeric `used_percent` from 0 through 100 inclusive with a positive `limit_window_seconds`. The governing remaining headroom is the smallest remaining headroom among the valid windows. Missing, malformed, out-of-range, transport-failed, authentication-failed, or timed-out readings, and a response carrying no valid window, are unobservable and MUST be journaled as such, never coerced to a numeric reading.

The committed `dispatcher.session_headroom_floor_percent` and `dispatcher.session_headroom_horizon_minutes` govern this clause; it introduces no configuration key of its own, and a floor of 0 disables every skip this clause defines while retaining the bounded read and its journal record. With a positive floor, a covered candidate MUST be skipped for this admission evaluation when: `rate_limit.allowed` is `false` or `rate_limit.limit_reached` is `true` (a Codex limit skip); or the governing remaining headroom is strictly below the floor (a floor skip); or the reading is unobservable (a floor skip on an unobservable reading). Equality passes the floor. A credit balance, an overage allowance, or any other field outside `rate_limit` MUST NOT count as headroom and MUST NOT prevent a skip, because work served from credits beyond the usage window is spend the operator did not schedule. With a positive floor, a covered candidate whose valid reading passes the floor and is not limit-reached MUST additionally be assessed for projected exhaustion per window, using exactly the baseline, drain-rate, unavailable-projection, and horizon rules of the Claude clause, applied per opaque credential identity AND per window length, so a reading of one window is never a baseline for another. The candidate MUST be skipped by a projection skip when any valid window's projected exhaustion instant is strictly earlier than the observation time plus the horizon. An unavailable projection MUST be journaled with its reason and MUST NOT skip the candidate.

Every skip this clause defines has exactly the semantics of a Claude floor skip: it is ephemeral and candidate-local to this evaluation; per-node selection MUST continue in configured order to the next eligible candidate; a successful credential-usability probe MUST NOT override it; it MUST NOT refuse or delay a dispatch while every admission-required node retains an eligible candidate; an emptied admission-required node leaves a ready item ready without a claim or blocked reason; and reevaluation follows the same scheduling rule. The per-node selection record and any headroom-governed refusal record MUST name each skip by its kind, distinguishing a Codex limit skip, a floor skip, and a projection skip, and MUST name the provider as `codex`. For each affected work-item and assessed Codex credential, the Dispatcher MUST journal under §"Control surface and audit" the opaque non-secret credential identity, `rate_limit.allowed` and `rate_limit.limit_reached`, each window's `used_percent`, `limit_window_seconds` and remaining headroom, or an explicit unobservable result, the local observation time, and exactly one projection result per window in the Claude clause's form. A reset instant the response carries MAY be journaled as an unverified provider claim and MUST NOT change any skip. The journal MUST NOT contain credential values, the account email, or raw provider responses. A reading creates NO observed availability record and retires none, and a passing reading MUST NOT override any live hold, outstanding availability confirmation, credential-usability refusal, or other admission condition. A run that still meets the Codex limit mid-turn is released under the provider-limit release of §"Factory-configurable ACP fallback priority", exactly as before this clause.

In `contracts.md`, in the numbered list of the three admission conditions the Dispatcher owns, item 2 MUST read: "The admission session-headroom assessments of §\"Provider spend containment\" → \"Admission filters candidates by projected Claude session headroom\" and \"Admission filters Codex candidates by projected usage-window headroom\"." followed by its existing remaining sentences unchanged.

In `scenarios.md`, add:

## Scenario 242 — Admission skips a Codex candidate whose usage window is short of headroom

```gherkin
Feature: A Codex-primary chain falls back before a run meets the Codex limit
  As an operator running Codex-routed factory nodes
  I want admission to read the Codex usage window before it selects a candidate
  So that a run is not launched on a Codex account the provider is about to refuse

  Scenario: A Codex window below the floor selects the fallback
    Given dispatcher.session_headroom_floor_percent is 20
    And an admission-required node whose primary is a covered codex-acp candidate and whose fallback is an eligible claude-acp candidate
    And the Codex usage read reports a primary window used_percent of 85
    When admission assesses the node
    Then the codex-acp candidate is skipped by a floor skip naming provider codex
    And per-node selection selects the claude-acp fallback

  Scenario: A limit-reached Codex account is skipped even with credits
    Given dispatcher.session_headroom_floor_percent is 20
    And a covered codex-acp candidate whose usage read reports rate_limit.limit_reached true and a positive credit balance
    When admission assesses the candidate
    Then the candidate is skipped by a Codex limit skip

  Scenario: A projected Codex exhaustion inside the horizon is skipped
    Given dispatcher.session_headroom_floor_percent is 20 and dispatcher.session_headroom_horizon_minutes is 180
    And a covered codex-acp candidate whose primary window passes the floor
    And an in-window baseline assessment of the same credential and window length whose drain rate projects exhaustion within 180 minutes
    When admission assesses the candidate
    Then the candidate is skipped by a projection skip and the journal carries the projection for that window

  Scenario: An unobservable Codex reading is skipped and journaled
    Given dispatcher.session_headroom_floor_percent is 20
    And the Codex usage read for a covered codex-acp candidate times out
    When admission assesses the candidate
    Then the candidate is skipped by a floor skip on an unobservable reading
    And the journal records the reading as unobservable rather than as a number

  Scenario: A floor of 0 disables every Codex headroom skip
    Given dispatcher.session_headroom_floor_percent is 0
    And the Codex usage read reports rate_limit.limit_reached true for a covered candidate
    When admission assesses the candidate
    Then no Codex headroom skip applies and the reading is still journaled
```

The revise that accepts this proposal MUST co-edit `tests/heading-coverage.json` with an entry for the `## Scenario 242` heading in `scenarios.md`, and MAY bind it to `test: "TODO"` with a reason naming work-item bd-ib-4jdgcw as the implementing item.
