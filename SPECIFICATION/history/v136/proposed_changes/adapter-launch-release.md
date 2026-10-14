---
topic: adapter-launch-release
author: claude-opus-5-5-factory-configurable-model-fallback-priority
created_at: 2026-10-14T06:34:50Z
---

## Proposal: A first consecutive adapter launch failure is released without a hold

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Add an Adapter launch release and re-dispatch arm after the provider-limit release: an ordinary ACP adapter exit before the prompt boundary, established from complete factory-native evidence and carrying no provider evidence, is released to ready for ordinary re-dispatch without minting a hold, once per consecutive sequence; a repeat rests for a human naming both runs, and missing evidence is retried rather than released.

### Motivation

Work-item bd-ib-x3la32, filed under plan factory-configurable-model-fallback-priority (epic bd-ib-jxvgq5) by the gitops-fleet-capacity coordinator on 2026-10-14 and placed on that day's factory stability allowlist once ready. Measured on hp that day: livespec-dev-tooling-yfqvqm run 01M4WA0WB0JX2BHV7YYP175MAG and bd-ib-zlkjm4 run 01M4W1YH2KEWWV5HXG9FEJKZYQ each failed implement with "ACP process exited before protocol completed: termination=exited, exit_code=unknown" in about one second with zero inference; the node's one retry relaunched the same candidate and failed identically, and each run rested at blocked / needs-human although no agent asked anything, while other runs on the same server at the same minutes ran normally. Research for this proposal (fork origin/factory-integration 8869e88) found that the engine classifies this as non-eligible pre_turn_without_provider_evidence, books it deterministic, and that neither repository configures an implement fallback candidate, so in-run fall-through could not help even if it were permitted; the ratified spec also places ordered fallback between runs. The narrowest remedy is therefore a hold-free release back to ready for the first adapter launch failure of a consecutive sequence, mirroring the first-stall release of Scenario 172: it keeps the ruling that a pre-turn failure is not provider evidence (no hold, no attribution), bounds a deterministic launch fault to one automatic re-dispatch per consecutive sequence, and rests the repeat for a human with both runs named. Capturing the real exit code (today "unknown") is engine-side work in the Fabro fork and is outside this proposal. An independent Codex gpt-6-astra review returned two blockers, both folded in with its wording: the arm is disjoint from the availability route and every non-eligible guard keeps its route, and the prompt boundary is read conservatively from agent.acp.started on a verified-complete attempt event stream, with missing evidence retried rather than released.

### Proposed Changes

Heading: contracts.md "## Factory-configurable ACP fallback priority". Edit 1. Replace this current text

> non-convergence are non-eligible before configured matching: they mint no hold,
> are not released for re-dispatch, and keep their original identity and their
> existing route. A mere pre-turn failure is not provider evidence.

with

> non-convergence are non-eligible before configured matching: they mint no hold,
> are not released for re-dispatch, and keep their original identity and their
> existing route, except that an adapter launch failure is released without a
> hold under "Adapter launch release and re-dispatch" below. A mere pre-turn
> failure is not provider evidence.

Edit 2. Replace the exact text `The release operation MUST be idempotent and replayable by reconciliation,` with `Each release operation of this section -- a provider-limit release, or an adapter launch release below -- MUST be idempotent and replayable by reconciliation,` (line wrapping as in the resulting file).

Edit 3. Immediately after the paragraph beginning "The release operation MUST be idempotent" (Edit 2), which ends with the text

> measured non-match or converted into a needs-human decision.

insert these three new paragraphs, each separated by one blank line, before the paragraph "**Recovery from the failed run's preserved work.**":

> **Adapter launch release and re-dispatch.** An *adapter launch failure* is a failing ACP node attempt whose recorded failure states that the ACP adapter process exited before the ACP protocol completed, for which complete factory-native evidence for that exact node visit, engine attempt, and executed candidate establishes that the prompt boundary was not crossed, and whose recorded termination is an ordinary process exit rather than a signal termination. The Dispatcher MUST first apply the existing non-eligible guards and availability-signature classification to the same attempt's recorded evidence. An eligible availability failure MUST take Provider-limit release and re-dispatch and MUST NOT be classified as an adapter launch failure. An adapter launch failure MUST carry no provider evidence in the recorded protocol machine code, protocol message, or separately captured process terminal diagnostic. Authentication, command-not-found, cancellation, node deadline or stall expiry, generic HTTP 400/404, remote-compaction 404, malformed command/configuration, signal exit, unattributed sandbox/DNS/transport failure, code/test/review/tool failure, and non-convergence retain their existing routes and MUST NOT be reclassified as adapter launch failures. The generic ACP process-exit failure identity alone is not provider evidence, and an adapter launch failure itself is not provider evidence: it mints no hold, retires none, sets no provider-usage-limit flag, and attributes nothing to a provider or account.
>
> Adapter launch evidence MUST be read from the factory recorded for the run and scoped to the unrecovered attempt responsible for its terminal disposition. The prompt boundary is conservatively considered crossed when that attempt has an `agent.acp.started` event; this event precedes prompt submission, so its presence excludes launch release even when no later activity was observed. Absence of that event establishes the boundary was not crossed only when the engine's event-emission and durability guarantees cover that execution path and the attempt's event stream is verified complete through termination. Any recorded agent activity also excludes launch release. Neither zero inference, an empty tool ledger, the generic process-exit message, nor an internal activity-derived `turn_started` value alone establishes eligibility. Missing, incomplete, unreadable, or unscopable evidence is unavailable, not negative evidence: the Dispatcher MUST surface it and retry observation automatically without releasing the item or manufacturing a needs-human decision.
>
> When a run terminates -- through any terminal, the workflow's `needs_human` terminal included -- and its unrecovered failing node attempt is an adapter launch failure, and the item's preceding dispatch did not itself end in an adapter launch failure, the Dispatcher MUST, in this order and without a human: (1) journal one `adapter-launch-release` record naming the work-item, run id, factory, failing node attempt, executed candidate identity, the recorded exit code or its explicit absence, the preceding dispatch's run id or the explicit statement that the item has none, and the recovery source chosen under "Recovery from the failed run's preserved work" below or its confirmed absence; (2) write one ledger comment on the item naming the run id, factory, failing node and the recorded exit code or its explicit absence; (3) release the item's dispatch claim and return it to `ready`, NOT to `blocked` and with no `blocked_reason`; and (4) leave the item to the ordinary admission valve, which re-dispatches it with every node selected afresh as "Per-node selection" specifies. The *preceding dispatch* is the immediately preceding submitted run for the same item in durable dispatch order, relative to the run being classified, across every factory: a refused admission is not a dispatch, a node retry is not a new dispatch, and an item's first dispatch has none. The predecessor identity is persisted with the release decision and reused by any replay; unavailable predecessor history is unavailable evidence, never proof of no predecessor. The bound is therefore one release per consecutive sequence of adapter launch failures: any intervening dispatch that did not end in an adapter launch failure resets it. An adapter launch release MUST NOT consume any budget of §"The three rework caps", MUST neither increment nor reset the item count of §"Across-dispatch required-result progress", and MUST NOT be surfaced as a needs-human decision. When the item's preceding dispatch also ended in an adapter launch failure, the current failure keeps its existing route, including the `blocked / needs-human` rest of §"A factory run never awaits a human"; that terminal is not item-attributable and neither increments nor resets the across-dispatch item count, and its needs-human cause record MUST name both runs and state that a repeated adapter launch failure is not released automatically. The release MUST be idempotent per run under the release operation above: completing or replaying it after a newer dispatch has claimed the item MUST NOT release that newer claim, journal a second record, or write a second ledger comment.

Heading: contracts.md, the paragraph of "Across-dispatch required-result progress" that names host-attributable failures. Edit 4. Replace the exact text `and runs released under §"Factory-configurable ACP fallback priority" → "Provider-limit release and re-dispatch", neither increment nor reset the item count` with `and runs released under §"Factory-configurable ACP fallback priority" → "Provider-limit release and re-dispatch" or → "Adapter launch release and re-dispatch", neither increment nor reset the item count`.

Heading: contracts.md "### A factory run never awaits a human". Edit 5. Replace this current text

>   §"Factory-configurable ACP fallback priority" → "Provider-limit release
>   and re-dispatch" and does not rest at `blocked / needs-human`.

with

>   §"Factory-configurable ACP fallback priority" → "Provider-limit release
>   and re-dispatch" and does not rest at `blocked / needs-human`.
>   Likewise a first consecutive adapter launch failure takes → "Adapter launch
>   release and re-dispatch" of that section and does not rest at
>   `blocked / needs-human`.

## Proposal: Scenario 127 binds the adapter launch release

### Target specification files

- SPECIFICATION/scenarios.md

### Summary

Append seven sub-scenarios to Scenario 127: a first consecutive adapter launch failure is released without a hold and seeds from preserved work, a repeat rests for a human, the release is replayable, and a post-boundary exit, an eligible provider exit, a signal exit, and missing evidence are each not released.

### Motivation

Work-item bd-ib-x3la32, filed under plan factory-configurable-model-fallback-priority (epic bd-ib-jxvgq5) by the gitops-fleet-capacity coordinator on 2026-10-14 and placed on that day's factory stability allowlist once ready. Measured on hp that day: livespec-dev-tooling-yfqvqm run 01M4WA0WB0JX2BHV7YYP175MAG and bd-ib-zlkjm4 run 01M4W1YH2KEWWV5HXG9FEJKZYQ each failed implement with "ACP process exited before protocol completed: termination=exited, exit_code=unknown" in about one second with zero inference; the node's one retry relaunched the same candidate and failed identically, and each run rested at blocked / needs-human although no agent asked anything, while other runs on the same server at the same minutes ran normally. Research for this proposal (fork origin/factory-integration 8869e88) found that the engine classifies this as non-eligible pre_turn_without_provider_evidence, books it deterministic, and that neither repository configures an implement fallback candidate, so in-run fall-through could not help even if it were permitted; the ratified spec also places ordered fallback between runs. The narrowest remedy is therefore a hold-free release back to ready for the first adapter launch failure of a consecutive sequence, mirroring the first-stall release of Scenario 172: it keeps the ruling that a pre-turn failure is not provider evidence (no hold, no attribution), bounds a deterministic launch fault to one automatic re-dispatch per consecutive sequence, and rests the repeat for a human with both runs named. Capturing the real exit code (today "unknown") is engine-side work in the Fabro fork and is outside this proposal. An independent Codex gpt-6-astra review returned two blockers, both folded in with its wording: the arm is disjoint from the availability route and every non-eligible guard keeps its route, and the prompt boundary is read conservatively from agent.acp.started on a verified-complete attempt event stream, with missing evidence retried rather than released.

The Scenario 127 heading is unchanged, so tests/heading-coverage.json needs no heading edit.

### Proposed Changes

Heading: scenarios.md "## Scenario 127 — Ordered ACP fallback preserves primary resolution and failure honesty, and re-dispatches past a held provider". Edit 1. After the current line

>     And a dispatch whose selected candidates use no protocol mechanism does not require the config_options capability

append, inside the same gherkin block:

>   Scenario: A first adapter launch failure is released and re-dispatched without a hold
>     Given a dispatched item whose unrecovered implement node attempt records an ordinary ACP process exit before the protocol completed, with an explicitly unknown exit code
>     And complete attempt-scoped evidence from the run's recorded factory establishes that the prompt boundary was not crossed under the adapter launch evidence rule
>     And the attempt carries no provider evidence and matches none of the excluded failure guards
>     And the item's preceding dispatch did not end in an adapter launch failure
>     And the failed run has verified preserved work at an immutable commit SHA
>     When the run terminates at the workflow's needs_human terminal and the ordinary admission valve next admits the item
>     Then the journal carries one adapter-launch-release record naming the item, run id, factory, node attempt, executed candidate, exit code or its explicit absence, preceding dispatch, and recovery source
>     And one ledger comment on the item names the run id, the factory, the failing node and the exit code or its explicit absence
>     And no availability hold is created and no provider-usage-limit flag is set
>     And the item returns to ready with no blocked_reason before admission
>     And the release consumes no budget of the three rework caps and neither increments nor resets the across-dispatch item count
>     And the next run is a plain dispatch seeded from that preserved commit
>
>   Scenario: A repeated adapter launch failure rests for a human
>     Given an item whose preceding dispatch ended in an adapter launch failure
>     And the current dispatch's unrecovered implement node attempt also fails as an adapter launch failure
>     When the run terminates
>     Then the item rests at blocked with blocked_reason needs-human
>     And its needs-human cause record names both runs and states that a repeated adapter launch failure is not released automatically
>     And the terminal neither increments nor resets the across-dispatch item count
>
>   Scenario: An adapter launch release is replayable without affecting a newer claim
>     Given an adapter launch release interrupted after its ledger comment was written
>     When reconciliation completes that release and later replays it after a newer dispatch has claimed the item
>     Then exactly one adapter-launch-release record and one ledger comment exist for that run
>     And the newer dispatch claim and the item's status are unchanged
>
>   Scenario: An adapter exit after the prompt boundary is not a launch failure
>     Given an unrecovered ACP attempt that exited before the protocol completed after its agent.acp.started event was recorded
>     When the run terminates
>     Then no adapter-launch-release record is journaled
>     And the failure keeps its existing route
>
>   Scenario: A pre-prompt process exit with eligible provider evidence keeps its availability route
>     Given an unrecovered ACP attempt that exited with code 1 before the prompt boundary
>     And its recorded process terminal diagnostic matches the configured candidate-scoped unsupported-model signature and no non-eligible guard
>     When the run terminates
>     Then Provider-limit release and re-dispatch records the candidate hold
>     And no adapter-launch-release record is journaled
>
>   Scenario: An excluded process exit is not released as a launch failure
>     Given an unrecovered pre-prompt ACP process exit with recorded signal termination and no exit code
>     When the run terminates
>     Then no adapter-launch-release record is journaled
>     And the failure keeps its existing route
>
>   Scenario: Missing launch evidence does not authorize release
>     Given a terminal ACP process-exit failure whose attempt event stream cannot be read completely from its recorded factory
>     When the Dispatcher evaluates adapter launch release
>     Then it surfaces unavailable evidence and schedules another observation
>     And it neither journals adapter-launch-release nor creates a needs-human decision from the missing evidence
