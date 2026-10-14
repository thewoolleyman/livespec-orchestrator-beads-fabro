---
topic: admission-session-headroom
author: claude-opus-5-5-spec-session-headroom
created_at: 2026-10-14T05:10:42Z
---

## Proposal: Admission filters candidates by projected Claude session headroom

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Add an admission-time session headroom filter for covered Claude candidates, applied through the per-node eligibility predicate, skipping a covered candidate on a low or unobservable reading while preserving eligible fallback selection, creating no availability record, and registered with the containment-refusal and admission-wait attention clauses.

### Motivation

Maintainer ruling of 2026-10-14: plan factory-configurable-model-fallback-priority (epic bd-ib-jxvgq5) owns provider session-limit handling, and work-item bd-ib-jwuxs4 was re-parented to it. Plan factory-run-wall-budget (epic bd-ib-hqt3s5) measured 11 hp runs and 42.5 slot-hours lost since 2026-10-07 to Claude's "You've hit your session limit" partway through long Opus ACP turns, the largest late-failure class with no owner. Two existing mechanisms cannot see it: the admission-time credential probe is a 1-token call that reports the credential usable right up to the limit, and the provider-exhaustion records refuse admission only once a limit has already been observed. livespec-overseer item overseer-pffwyp measured the caveat this clause is written around: on 2026-10-13 the provider usage endpoint read 45% five-hour headroom left nine minutes before that account's first session-limit refusal, so a reading is a filter that reduces doomed admissions, never a proof of availability. The floor default of 20 is an unmeasured starting policy, not a run-consumption estimate or an availability guarantee; it is committed-only so a repository can tune it through review. An independent Codex gpt-6-astra review (ACCEPT-WITH-CHANGES) supplied the covered-candidate definition, the disabled-floor precedence, and the dependent-clause updates folded into this proposal. The 2026-10-14 04:00Z session window measured the probe's blindness directly: bd-ib-s22sg run 01M4W1W22FZP was refused mid-implement at 03:39Z with "You have hit your session limit, resets 4am (UTC)" after about 1h40m of implement, while claude-cred-status still reported the credential usable (HTTP 200) at 03:41:33Z; this plan's own runs 01M4VRGQBHH7 (bd-ib-vlctc3) and 01M4VRWHXYHV (bd-ib-mnuo5n) died in implement on the same window after more than three hours each, and livespec-dev-tooling-ycahud run 01M4W5AQB3MEHTAQPJHWWHAGFW died at dod_gate on it. Whether the sandbox ran on a different account identity than the probe has not yet been excluded.

### Proposed Changes

Heading: contracts.md "## Dispatcher admission, WIP cap, and post-merge acceptance". Edit 1. After the paragraph that currently reads

> **The admission-time credential-probe refusal re-probes rather than exiting.** A `loop` invocation (§"Dispatcher loop invocation surface") whose admission is refused by the admission-time credential-usability probe -- the projected worker credential returning a provider-limit or rate-limit condition BEFORE any sandbox is launched -- MUST NOT exit on that refusal while its `--budget` is unspent. It MUST re-run the probe on a bounded cadence and resume normal admission on the first usable probe result, subject to every other admission-valve condition (§"Admission valve (`ready → active`)"). The cadence is a committed-only `dispatcher.credential_reprobe_interval_seconds` (positive integer, default **300**); it is NOT declared API-configurable and is therefore committed-only per §"Orchestrator-owned attention facts" → "The declared-API-configurable class". Each refused probe MUST be journaled as one record under §"Control surface and audit" -- the re-probe wait is not silent. This clause governs ONLY the loop's response to a probe refusal; it creates NO new availability-record retirement route. A usable probe result MUST NOT retire an unexpired observed record: the three ratified retirement routes -- bounded expiry, matching execution (this section's "A record is falsifiable only by later matching execution"), and operator clearance -- stand unchanged, because a live credential probe is a non-dispatch-outcome host signal. Where observed holds exhaust an admission-required chain, admission remains refused until at least one candidate becomes eligible; a hold covering only the primary does not defeat an eligible fallback. The re-probe keeps the loop alive rather than substituting for record retirement.

insert this new paragraph, separated by one blank line:

> **Admission filters candidates by projected Claude session headroom.** For this clause, a covered candidate is a structured candidate whose resolved agent id is `claude-acp`, or a manual-form candidate recognized as a built-in Claude adapter under the existing built-in byte-equality rule, whose execution uses the Claude subscription credential supplied by Worker credential projection. Coverage MUST follow resolved agent provenance and actual credential projection, never display text, a model-name prefix, or a spelling inferred from an opaque availability or candidate key. Arbitrary manual adapters and other agents are outside this clause's coverage; extending coverage to them requires an explicit authentication binding. Before claim and final per-node selection, the Dispatcher MUST assess every otherwise-selectable covered candidate on an admission-required ACP node, including covered fallbacks and built-in single-candidate nodes without fallback metadata. It MUST read the provider's five-hour session utilization using the exact credential snapshot that the dispatch would project. One assessment per distinct projected credential per admission evaluation MUST be reused across nodes and candidates sharing that credential. If that snapshot changes before projection, the affected assessment MUST be repeated before claim. For each affected work-item and assessed credential, the Dispatcher MUST journal under §"Control surface and audit" the opaque non-secret credential identity, the utilization and remaining-headroom percentages or an explicit unobservable result, and the local observation time. The journal MUST NOT contain credential values or raw provider responses. The floor is a committed-only `dispatcher.session_headroom_floor_percent` (integer from 0 through 100 inclusive, default **20**), measured in percentage points of the five-hour usage allowance remaining, not elapsed wall-clock time. It is NOT declared API-configurable, and is therefore committed-only per §"Orchestrator-owned attention facts" → "The declared-API-configurable class". Remaining headroom equals 100 minus the provider's five-hour utilization percentage. A valid reading is a finite numeric utilization from 0 through 100 inclusive. Missing, malformed, out-of-range, transport-failed, authentication-failed, or timed-out readings are unobservable and MUST be journaled as such, never coerced to a numeric reading. The usage request MUST have a finite implementation-defined timeout. With a positive floor, a covered candidate is skipped for this admission evaluation when its remaining headroom is strictly below the floor or its reading is unobservable. Equality passes this filter. A floor of 0 disables both kinds of headroom skip while retaining the bounded reading attempt and journal record; it disables no other admission condition. With a positive floor, a successful credential-usability probe MUST NOT override a headroom skip. A headroom skip is ephemeral and candidate-local to this admission evaluation; candidates sharing the assessed projected credential use the same reading. Per-node selection MUST continue in configured order to the next candidate satisfying every eligibility condition, whether that candidate is uncovered or is covered and passes its own headroom assessment. Headroom MUST NOT refuse or delay a dispatch while every admission-required node retains an eligible candidate. If headroom skips leave an admission-required node with no eligible candidate, a ready item remains ready without a claim or blocked reason; a parked rework item retains its parked state without a new claim. Every other admission-valve condition remains in force. Reevaluation MUST use the existing Per-node selection scheduling rule of §"Factory-configurable ACP fallback priority": the earliest expiry among holds emptying a chain when applicable, otherwise after `dispatcher.credential_reprobe_interval_seconds`. The unattended loop MUST reevaluate automatically while its budget remains, without exiting solely because of a headroom wait or requiring a human. A headroom wait MUST be surfaced through the existing admission-wait attention surface, derived from the recorded admission evaluation and its scheduled reevaluation instant. Its handoff MUST inspect that recorded assessment and governing floor; it MUST NOT offer clearance of a nonexistent hold or require human action before retry. Snapshot composition MUST NOT issue a live usage request. The existing idle-factory projection MUST consume the recorded headroom outcome as part of the shared verdict and MUST NOT report an item as admission-eligible contrary to its outstanding recorded headroom wait. A due wait is reevaluated by the admission loop, not by a live probe during snapshot composition. A reading creates NO observed availability record and retires none: the provider's usage figure has been measured stale relative to its own refusals, so a reading above the floor is not evidence of availability, and a run that still meets its session limit mid-run is released under the provider-limit release of §"Factory-configurable ACP fallback priority". A passing or disabled headroom filter adds no restriction to admission, but MUST NOT override any live hold, outstanding availability confirmation, credential-usability refusal, or other admission condition.

Edit 2. In the No silent containment paragraph, replace this current text

> their expiries when present. When no hold governs the refusal, it MUST name
>   the outstanding confirmation, unavailable evidence source, or admission-time
>   credential-probe skip instead; it MUST NOT invent a hold identity or
>   expiry.

with

> their expiries when present. When no hold governs the refusal, it MUST name the outstanding confirmation, unavailable evidence source, admission-time credential-probe skip, or admission session-headroom skip instead; it MUST NOT invent a hold identity or expiry. A headroom-governed refusal MUST additionally name the assessed credential identity, reading or explicit unobservable result, observation time, governing floor, and skipped candidates for the admission-required node lacking an eligible candidate.

Heading: contracts.md "## Factory-configurable ACP fallback priority". Edit 3. Replace this current text

> **Per-node selection.** For each node, the Dispatcher MUST choose the first
> candidate in configured order that has no covering live hold, has satisfied any
> outstanding post-expiry availability confirmation, and has not been skipped by
> the admission-time credential-usability probe for this evaluation. Such a
> candidate is *eligible*.

with

> **Per-node selection.** For each node, the Dispatcher MUST choose the first candidate in configured order that has no covering live hold, has satisfied any outstanding post-expiry availability confirmation, has not been skipped by the admission-time credential-usability probe for this evaluation, and has not been skipped by the admission session-headroom filter for this evaluation. Such a candidate is *eligible*.

Edit 4. Immediately after this current text

> skipped earlier candidates; that record contains no command, env value,
> credential, prompt, raw error, or unredacted diagnostic.

append

> When headroom skips an earlier candidate, the selection record MUST identify that candidate and reference its headroom assessment and governing floor; it MUST NOT represent that skip as an observed hold.

Heading: the section carrying the admission-wait attention enumeration (contracts.md, the needs-attention wait item for an admission-required ACP chain with no eligible candidate). Edit 5. Replace the exact text `unavailable evidence, or admission-time credential-probe skips, which likewise` with `unavailable evidence, admission-time credential-probe skips, or admission session-headroom skips, which likewise`.


## Proposal: Scenario 60 binds the session headroom filter

### Target specification files

- SPECIFICATION/scenarios.md

### Summary

Extend Scenario 60's no-hold refusal assertion with the headroom skip, and add six sub-scenarios: low primary headroom selects an uncovered fallback, no eligible candidate waits without a claim, unobservable headroom with a viable fallback, equality passes, a disabled floor, and a passing reading cannot clear a hold.

### Motivation

Maintainer ruling of 2026-10-14: plan factory-configurable-model-fallback-priority (epic bd-ib-jxvgq5) owns provider session-limit handling, and work-item bd-ib-jwuxs4 was re-parented to it. Plan factory-run-wall-budget (epic bd-ib-hqt3s5) measured 11 hp runs and 42.5 slot-hours lost since 2026-10-07 to Claude's "You've hit your session limit" partway through long Opus ACP turns, the largest late-failure class with no owner. Two existing mechanisms cannot see it: the admission-time credential probe is a 1-token call that reports the credential usable right up to the limit, and the provider-exhaustion records refuse admission only once a limit has already been observed. livespec-overseer item overseer-pffwyp measured the caveat this clause is written around: on 2026-10-13 the provider usage endpoint read 45% five-hour headroom left nine minutes before that account's first session-limit refusal, so a reading is a filter that reduces doomed admissions, never a proof of availability. The floor default of 20 is an unmeasured starting policy, not a run-consumption estimate or an availability guarantee; it is committed-only so a repository can tune it through review. An independent Codex gpt-6-astra review (ACCEPT-WITH-CHANGES) supplied the covered-candidate definition, the disabled-floor precedence, and the dependent-clause updates folded into this proposal. The 2026-10-14 04:00Z session window measured the probe's blindness directly: bd-ib-s22sg run 01M4W1W22FZP was refused mid-implement at 03:39Z with "You have hit your session limit, resets 4am (UTC)" after about 1h40m of implement, while claude-cred-status still reported the credential usable (HTTP 200) at 03:41:33Z; this plan's own runs 01M4VRGQBHH7 (bd-ib-vlctc3) and 01M4VRWHXYHV (bd-ib-mnuo5n) died in implement on the same window after more than three hours each, and livespec-dev-tooling-ycahud run 01M4W5AQB3MEHTAQPJHWWHAGFW died at dod_gate on it. Whether the sandbox ran on a different account identity than the probe has not yet been excluded.

The Scenario 60 heading is unchanged, so tests/heading-coverage.json needs no heading edit.

### Proposed Changes

Heading: scenarios.md "## Scenario 60 — An observed provider exhaustion refuses admission, and expires". Edit 1. Replace this current line

>     And when no hold governs the refusal, the record names the outstanding confirmation, unavailable evidence source, or admission-time credential-probe skip without inventing a hold identity or expiry

with

>     And when no hold governs the refusal, the record names the outstanding confirmation, unavailable evidence source, admission-time credential-probe skip, or admission session-headroom skip without inventing a hold identity or expiry

Edit 2. After the current sub-scenario ending

>   Scenario: A containment refusal never disposes a needs-human item
>     Given a work-item carrying blocked_reason "needs-human"
>     And observed holds exhaust an admission-required chain
>     When the Dispatcher evaluates that item
>     Then the item is not auto-resolved
>     And the item stays surfaced through the needs-attention awareness surface

append, inside the same gherkin block:

>   Scenario: Low session headroom on the primary selects an uncovered fallback
>     Given an item whose implement node's primary is a covered candidate under the admission session-headroom clause
>     And dispatcher.session_headroom_floor_percent is 20
>     And that node lists an uncovered eligible fallback candidate
>     And every other admission-required node retains an eligible candidate
>     And every other admission-valve condition is satisfied
>     And the primary credential's remaining five-hour headroom reads below 20 percent
>     When the Dispatcher evaluates admission
>     Then the reading is journaled with the work-item id and the opaque credential identity
>     And the fallback candidate is selected for the implement node
>     And the selection record references the primary's headroom assessment and the governing floor
>     And the item is admitted
>
>   Scenario: Low or unobservable session headroom with no eligible candidate waits without a claim
>     Given a ready item whose every candidate on one admission-required node is a covered candidate under the admission session-headroom clause
>     And dispatcher.session_headroom_floor_percent is 20
>     And every other admission-required node retains an eligible candidate
>     And every other admission-valve condition is satisfied
>     And each of those credentials' remaining five-hour headroom reads below 20 percent or is unobservable
>     When the Dispatcher evaluates admission
>     Then the item stays ready with no dispatch claim and no blocked_reason
>     And its containment refusal record names the assessed credential identity, the reading or unobservable result, the observation time, the governing floor and the skipped candidates
>     And the refusal names the admission-required node and scheduled reevaluation instant
>     And no observed availability record is created
>     And no observed availability record is retired
>     And the unattended loop reevaluates automatically after the configured cadence
>     And wait attention exposes the recorded assessment without making a live usage request
>
>   Scenario: Unobservable headroom skips a covered primary without defeating a viable fallback
>     Given a ready item with a covered primary whose headroom reading is unobservable
>     And dispatcher.session_headroom_floor_percent is 20
>     And that node has an uncovered eligible fallback
>     And every other admission condition is satisfied
>     When admission is evaluated
>     Then the primary's unobservable result is journaled
>     And the fallback is selected and the item is admitted
>
>   Scenario: Equality passes the headroom filter without overriding another gate
>     Given a covered candidate with 20 percent remaining headroom
>     And dispatcher.session_headroom_floor_percent is 20
>     When admission is evaluated
>     Then the headroom filter does not skip that candidate
>     And all other admission conditions are still applied
>
>   Scenario: A disabled floor retains observation without refusing on unobservability
>     Given a covered candidate whose headroom reading is unobservable
>     And dispatcher.session_headroom_floor_percent is 0
>     When admission is evaluated
>     Then the unobservable result is journaled
>     And the headroom filter does not skip that candidate
>     And all other admission conditions are still applied
>
>   Scenario: A passing usage reading cannot clear observed availability evidence
>     Given a covered candidate with headroom above the positive floor
>     And a live observed hold covers that candidate
>     When admission is evaluated
>     Then that candidate remains ineligible under the hold
>     And no usage reading retires the hold

