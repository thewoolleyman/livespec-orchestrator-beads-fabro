---
proposal: a-spec-change-hold-whose.md
decision: modify
revised_at: 2026-11-08T04:18:31Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

MODIFY (placement only). The rule is sound and stays word for word: it is visibility only, a read of the spec history that needs no model, it excludes rejected revisions (the plugin-build-record-corrections case of 2026-11-07), and it leaves release and relink exactly where the bullet already puts them. The tier record it keys on already carries spec_version and generalization_target (_spec_change_tier_record.py), and a verdict that names no heading gives no heading to amend, so no candidate. The proposal placed the new text directly after the relink sentence; that would split the relink sentence from its companion ('Every later spec-change tier record ... MUST carry the replacement topic forward') and name 'the pre-dispatch wall's refusal' before the bullet introduces that refusal. The text is therefore inserted after the sentence ending 'as it would any other item.', which follows the exit-code-5 wall refusal and precedes the release-spec-tier valve. The two scenarios are appended to the Scenario 206 gherkin block as proposed. No H2 heading is added, changed or removed, so tests/heading-coverage.json needs no edit. Revised by plan spec-implementation-lockstep (epic bd-ib-ax3rds) for held child bd-ib-jnbcny under the delegated decision mode.

## Modifications

Insertion point moved: the new paragraph is inserted in contracts.md §"Grooming and slice-size calibration", autonomy-tier bullet, immediately after the sentence that ends "and `manual` admission rests it at `pending-approval` for the `approve` valve, as it would any other item." instead of immediately after the sentence that ends "the hold MUST thereafter name the replacement topic as the one awaiting ratification." The inserted text and the two Scenario 206 scenarios are unchanged from the proposal.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-08T04:18:28Z
verdict: NO BLOCKERS
proposal_stem: a-spec-change-hold-whose
content_digest: d0ca57f781c5d1379cc1b0ca9396fddad2832488df5da6748a6074e8c90b93f5
