---
topic: provider-refusal-booked-as-success
author: claude-opus-5-5:factory-configurable-model-fallback-priority
created_at: 2026-10-20T07:52:46Z
---

## Proposal: A provider refusal booked as a successful turn is a failed attempt of its candidate

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a fourth signature source, `turn.final_output`, that classifies an ACP node attempt the engine recorded as SUCCEEDED as a FAILED attempt of its executed candidate when the turn's final output ends with a measured provider refusal sentence. Seed it with one built-in codex-acp form, `provider_capacity` with candidate scope, whose literals are `selected model is at capacity` and `try a different model`. Such an attempt mints its candidate hold, takes the existing provider-limit release instead of resting at needs_human, and is never a successful completion for hold retirement, warning retirement or availability confirmation. New Scenario 209 exercises it.

### Motivation

Measured 2026-10-20 on gmktec run 01M5C0FBAE8FVZK15XN9WHVM6H (bd-ib-davaxq, orchestrator build d10a96243a69). At admission the Dispatcher skipped the review node's claude-opus-5 primary on its session-headroom projection: 43 percent remaining, 26.6 points per hour of drain, projected exhaustion at 08:11Z inside the 180-minute horizon. The codex-acp gpt-5.6-terra fallback became the node's only candidate. After 212 seconds and 37 tool-call updates, that turn's output ended with "Selected model is at capacity. Please try a different model." codex-acp delivered the sentence as assistant text on a normal turn end, so the engine's step.finished recorded status success, outcome succeeded and an empty failure_class. With no verdict label, the graph took the unmatched-review-outcome edge to needs_human. Every existing signature source (`protocol.machine_code`, `protocol.message`, `process.terminal_diagnostic`) reads the failing node's recorded failure, and §"Factory-configurable ACP fallback priority" mints holds only from a failed node. So the refusal was invisible to the fallback mechanism, and a whole run rested for a human on a transient provider condition. Worse, the falsifiability paragraph retires a hold when a later attempt "completes successfully" against its key, and a confirmation turn makes a candidate eligible only on a "successfully completed prompt turn", so an attempt booked this way could clear a hold or confirm availability on the very provider that refused. The engine's recorded token usage is zero for every turn on this factory (finding F-bj), so it cannot discriminate a refusal from real work; the turn's final text is the only recorded discriminator. Coordinator ruling R284 (gitops-fleet-capacity-monitoring, 2026-10-20) directed this proposal; drafting proceeds without a maintainer gate under R202, and ratification goes through revise.

### Proposed Changes

In `SPECIFICATION/contracts.md`, §"Factory-configurable ACP fallback priority":

1. In the signature grammar paragraph that begins "`source` is exactly", replace the source list with: "`source` is exactly `protocol.machine_code`, `protocol.message`, `process.terminal_diagnostic`, or `turn.final_output`." Extend the requirement sentence so that `turn.final_output`, like the message and diagnostic sources, requires a non-empty array of non-empty `all_literals` and forbids `machine_code`. Add: "A `turn.final_output` signature MUST declare `scope: candidate` and MUST NOT declare `exit_code`."

2. In the paragraph beginning "Text matching is a conjunction", append: "A `turn.final_output` signature applies only to an agent node attempt that the engine recorded as succeeded. It matches when, after Unicode case-folding and whitespace normalization, every literal occurs in the turn's FINAL sentence, meaning the text after the last sentence terminator that precedes the end of the recorded turn output, ignoring trailing whitespace. The same literals appearing anywhere earlier in the output MUST NOT match, so a turn that quotes or discusses a refusal and then continues is not a refusal. The Dispatcher MUST read the recorded output from the run's resolved factory, exactly as it reads a failure for the other sources."

3. In the paragraph that lists the measured minimum set of built-in forms, append to the codex-acp forms: "and the capacity form, source `turn.final_output`, `cause: provider_capacity`, `scope: candidate`, literals `selected model is at capacity` and `try a different model`". This form is candidate-scoped to codex-acp. A claude-acp attempt whose output ends with the same words MUST NOT match it.

4. Immediately after the paragraph beginning "A hold MUST come from an actual candidate attempt", insert a new paragraph:

"**A provider refusal booked as a successful turn is a failed attempt.** An agent node attempt that the engine recorded as succeeded, but whose turn matches a `turn.final_output` signature of its executed candidate, MUST be treated by the Dispatcher as a FAILED attempt of that candidate with the matched cause and scope, for every purpose of this section. It mints the candidate hold that the signature declares, with expiry computed from the attempt's completion instant. It journals the model-fallback warning exactly as a failed attempt does. It MUST NOT count as a successful completion under "A record is falsifiable only by later matching execution", under the warning-retirement rule, or as a successfully completed availability confirmation turn. When the run terminates at any terminal other than a successful exit and its last attempt of any agent node matched such a signature, that attempt is the failing node attempt for "Provider-limit release and re-dispatch": the Dispatcher MUST perform that release, including returning the item to `ready` with no `blocked_reason`, and MUST NOT rest the item at `blocked / needs-human`. A run that nevertheless reaches its successful exit keeps its outcome; the hold and the warning still stand. The release record MUST name the matched signature's source as `turn.final_output`."

5. In the paragraph beginning "**A record is falsifiable only by later matching execution.**", after "completes successfully", insert "(an attempt reclassified as failed under "A provider refusal booked as a successful turn is a failed attempt" is not a successful completion)".

In `SPECIFICATION/scenarios.md`, append a new heading `## Scenario 209 — A provider refusal booked as a successful turn is released, not left for a human` with a gherkin block:

```gherkin
Feature: A provider refusal delivered as turn text is a failed attempt of its candidate
  As the maintainer of a repository dispatched to the factory
  I want a turn that ends with a measured provider refusal to count as that candidate's failure
  So that a transient provider condition releases the item for re-dispatch instead of losing the run to a human gate

  Scenario: A codex-acp capacity refusal on review releases the item
    Given a review node attempt on the codex-acp candidate that the engine recorded as succeeded
    And the turn's final output sentence reads "Selected model is at capacity. Please try a different model."
    And the run ended at the needs_human terminal through the unmatched review outcome edge
    When the Dispatcher reconciles the terminal run
    Then it records a candidate hold with cause provider_capacity for that codex-acp candidate
    And it journals one provider-limit-release record whose source is turn.final_output
    And the item returns to ready with no blocked reason and no needs-human decision

  Scenario: A refusal sentence that is not the final sentence does not match
    Given a succeeded agent node attempt whose output quotes "Selected model is at capacity" and then continues with a review verdict
    When the Dispatcher classifies the attempt
    Then no turn.final_output signature matches and the attempt remains a success

  Scenario: A reclassified attempt does not retire a hold
    Given a live candidate hold on the codex-acp candidate
    And a later attempt on that candidate whose final output sentence is the measured capacity refusal
    When the Dispatcher evaluates hold retirement
    Then the hold is not retired by that attempt

  Scenario: The codex-acp form does not match a claude-acp attempt
    Given a succeeded claude-acp attempt whose final output sentence reads "Selected model is at capacity. Please try a different model."
    When the Dispatcher classifies the attempt
    Then the built-in codex-acp capacity form does not match it
```

The revise pass that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new Scenario 209 heading in the same change. That entry MAY carry `test: "TODO"` with a non-empty reason naming the implementing work-item.
