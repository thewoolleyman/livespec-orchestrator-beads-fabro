---
proposal: label-every-host-model-judgement.md
decision: accept
revised_at: 2026-10-31T19:15:42Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:revise-label-and-sandbox-retention
---

## Decision and Rationale

Accepted as filed. The proposal adds `### Host model-judgement caller labelling` under contracts.md §"Bounded session waits and observable inventory", immediately after §"Dispatch trace correlation", the heading the Dispatcher's dispatch-time spec-stated judgement named when it held work-item bd-ib-h23kbx: every host model-judgement spawn carries a caller-supplied `livespec.caller=<caller>` entry appended to the child's `OTEL_RESOURCE_ATTRIBUTES`, with a closed caller list (drift_run, dod_governing_heading, dod_judgement_pre_admission, dod_judgement_pre_dispatch, ledger_intent_scan), no other environment change, a label failure that never fails the judgement, and a receiver-allowlist admission for the attribute. It extends the section's shared attribute vocabulary and reuses §"Dispatch trace correlation"'s identifier-shaped definition and the curated-field rule, contradicting neither. The scenario is allocated Scenario 280 (next free after 279), carried in the file's fenced-gherkin form with its two Given/When/Then groups as two Scenario blocks and the step text unchanged; the subsection names it, and tests/heading-coverage.json gains its TODO entry owned by bd-ib-h23kbx in the same change. The independent sonnet reviewer returned NO BLOCKERS; its advisory that the label-composition-failure clause has no scenario is left to the implementing item's tests. Step 3.5 stale-branch precondition skipped via `--skip-stale-branch-check` (coordinator decision, 2026-10-31); the two stale `spec/*` branches it reported are NOT being surfaced as blockers this pass, and neither was touched, merged or deleted:
- `spec/host-judgement-isolation` (5cbf3f823, "host judgements launch outside the interactive agent configuration (v221)"): the loser of a v221 numbering collision; master's v221 is fea77b047 and master has since advanced to v260, so it cuts no version this pass could collide with and edits none of the text added here.
- `spec/reprove-merged-item-v2` (e942de03e): a WIP propose-change draft marked "Not for filing yet"; it adds only proposed_changes/reprove-merged-item.md, cuts no history version, and touches neither contracts.md section nor scenarios 280-281.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-31T19:14:48Z
verdict: NO BLOCKERS
proposal_stem: label-every-host-model-judgement
content_digest: 6dca75eead1094c63ad27ef0967c4ebe9e80c73ec8248705ffd2a3f4272675d2
