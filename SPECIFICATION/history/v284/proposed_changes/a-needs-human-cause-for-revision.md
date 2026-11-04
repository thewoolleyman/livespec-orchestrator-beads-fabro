---
proposal: a-needs-human-cause-for.md
decision: modify
revised_at: 2026-11-03T11:30:49Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Re-cut as v284 on master's merged bytes (v282 delegated-valve-authority and v283 dispatcher-fabro-rm-deletions-burst merged first, by coordinator ruling on the revise collision; the earlier v282 cut in PR #4263 is superseded). Modified under delegated revise mode for bd-ib-2h512 (plan sandbox-commit-gate-ceiling, epic bd-ib-qy5wol, plan assertion 5; measured: 10 of 17 implement_hook_route needs-human endings in 48 h said only 'script exited with status 1', livespec-dev-tooling-6vuiwe). The proposal adds the ledger residue that bd-ib-rf7fvk's exit status and failed target names do not cover: a bounded first failure line, an explicit target-unknown reason, and withholding of sandbox environment values, worded for the Scenario 285 commit_red/commit_green graph. A fresh independent read-only review (sonnet) of the final bytes on top of v283 found NO BLOCKERS and confirmed the change is purely additive. Non-blocking notes carried from the earlier review for the implementing item: (1) the 'output absent', 'names no failed target', fix/review_fix path, JSON-escaped and under-8-character cases are carried by the paragraph text without a dedicated scenario; (2) whether the 200-character bound includes the truncation marker is the implementer's choice; (3) the first scenario implicitly assumes the hook output reports no failing test id.

## Modifications

Placement only. The proposal said to insert the paragraph 'immediately after the paragraph that begins "The recorded hook verdict outranks the agent's account of it." and before the paragraph that begins "A commit leg completes past one tool call."'. In the ratified spec 'A commit leg completes past one tool call.' precedes 'The recorded hook verdict outranks the agent's account of it.', so the two halves of that instruction contradict each other. The paragraph is inserted immediately after 'The recorded hook verdict outranks the agent's account of it.' and before 'The run's working tree survives the agent.', which keeps its opening reference to 'the preceding paragraph' correct. The paragraph text and the three Scenario 285 scenarios are applied verbatim. No ## heading changed, so tests/heading-coverage.json is untouched.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-03T11:30:08Z
verdict: NO BLOCKERS
proposal_stem: a-needs-human-cause-for
content_digest: ed51b0cd7a07b5de342469c00119277cae2e8e0e0e9a6c6b7a024808d8b3213f
