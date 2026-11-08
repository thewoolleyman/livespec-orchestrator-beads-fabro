---
proposal: tree-can-pass-under-the-harness-judging-it.md
decision: modify
revised_at: 2026-11-07T21:49:25Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

The maintainer chose Option Scrub on 2026-11-07 (verbatim, said in the legacy-coordinator-agent session at about 21:40Z and relayed by that session: "I choose scrub. Go with your recommendation."; the time "about 21:5xZ" first given here came from the coordinator's relay, which corrected it to about 21:40Z, matching the verbatim record on bd-ib-s754le stamped 21:40:33Z), recorded on bd-ib-s754le and livespec-dev-tooling-6tgd2z. The requirement section and Option Scrub are accepted and Option Refresh is rejected, as the proposal required: a revise accepts the requirement and exactly one option. This is the maintainer's decision, not a delegated one. The plan seat factory-run-work-preservation drafted the bytes.

## Modifications

Accepted the requirement section and Option Scrub; rejected Option Refresh, so none of its text or its scenario replacement lands. Option Scrub's appended sentences are merged into the requirement paragraph, and its scenario step 'And the seeded tree's bytes are unchanged by the harness' is added to the first scenario. Added a fourth scenario, 'A test case that sets the variable itself still observes the refusal', for Option Scrub's MAY clause. Added the measurement sentence from the proposal's evidence to the paragraph. Numbered the scenario 326, because v315 took Scenario 325. Its heading-coverage and heading-coverage-debt entries are edited directly in the revise commit, owned by bd-ib-s754le, because resulting_files cannot reach tests/.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-07T21:48:37Z
verdict: NO BLOCKERS
proposal_stem: tree-can-pass-under-the-harness-judging-it
content_digest: 31ef70f6f6048caeda5e149334577cd6a4d821aba240e6e95092c29cd0b144af
