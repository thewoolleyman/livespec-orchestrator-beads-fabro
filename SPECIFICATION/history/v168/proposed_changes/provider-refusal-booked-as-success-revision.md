---
proposal: provider-refusal-booked-as-success.md
decision: modify
revised_at: 2026-10-20T09:29:55Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:spec-implementation-lockstep
---

## Decision and Rationale

Accepted with modifications under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session spec-implementation-lockstep (epic bd-ib-ax3rds), which took the revise over under fleet coordinator routing R288 (gitops-fleet-capacity-monitoring) from plan factory-configurable-model-fallback-priority (epic bd-ib-jxvgq5), whose seat may only diagnose while its budget is expired. The proposal (coordinator ruling R284) closes a measured gap: on gmktec run 01M5C0FBAE8FVZK15XN9WHVM6H a codex-acp capacity refusal delivered as assistant text on a normal turn end was booked as a succeeded review attempt, so no signature source could see it and the run rested at needs_human on a transient provider condition. The configured ratification reviewer, gpt-6-astra in a separate read-only Codex session, returned NO BLOCKERS on the exact resulting bytes after four rounds. The Scenario 209 coverage entry and debt-register row land in the same change, owned by the implementing work-item bd-ib-wkfwtx.


## Modifications

The resulting bytes carry the proposal's five contracts.md edits and Scenario 209, with these modifications from the ratification review rounds (gpt-6-astra; round 1 on the predecessor seat's draft, rounds 2 to 4 on this draft):
- M1 (round-1 B1): a `turn.final_output` signature carries one `final_text`, the complete measured refusal text, instead of `all_literals`, because the measured codex-acp refusal is two sentences and a final-sentence-only literal rule could never match its first literal. The built-in capacity form's `final_text` is `Selected model is at capacity. Please try a different model.`
- M2 (round-1 B2): the match is a normalized suffix at a sentence boundary, not a literal conjunction: the output equals the text, or the character before it is `.`, `!` or `?` (the measured output has no space after the preceding period), or one space after such a character. An output ending with the refusal marked as a quotation (a closing quotation mark after it, or a colon lead-in immediately before it) does not match.
- M3 (round-1 B3): a reclassified attempt is the failing node attempt for Provider-limit release only when it is the unrecovered failure responsible for the run's terminal disposition; a later failure of any node, agent or not, keeps its own classification and route.
- M4: an explicit exception to "Every provider-limit mapping MUST exist as a protocol.message signature" for a `turn.final_output` form, which has no recorded failure to match.
- M5 (round-2 B1): the measured-minimum-forms sentence keeps its `cause: quota` / domain-scope statement for the quota forms and introduces the candidate-scoped capacity form separately.
- M6 (round-2 B2): the text no longer claims that any quoting output fails to match; an unmarked reproduction at the end of the output is indistinguishable and DOES match, accepted because a match only mints a candidate hold and warning and releases only under the unrecovered-cause condition.
- M7 (round-2 N3): the run's overall outcome never retires the reclassified attempt's hold or warning; their existing retirement rules apply.
- M8 (round-3 N1 to N3): "Literal-based text matching is a conjunction"; the marked-quotation sub-scenario is named for explicit marking; Scenario 209 uses the verbatim incident output.
- S1: Scenario 209 gains sub-scenarios for the marked quotation, the unmarked reproduction on a successful run, and a later test failure keeping its own route.


## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: manual-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-20T09:29:23Z
verdict: NO BLOCKERS
proposal_stem: provider-refusal-booked-as-success
content_digest: d05d920fd08b8cb6b3ece342ca684b3bf22412e5bc1cc1e56d4f341ee0ed4e56
