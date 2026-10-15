---
proposal: sandbox-commit-leg-completion.md
decision: modify
revised_at: 2026-10-15T00:22:07Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5-plan-sandbox-commit-gate-ceiling
---

## Decision and Rationale

Accepted with two revise-time wording repairs. Approved by the driver session gitops-fleet-capacity-monitoring under the maintainer's in-session ruling recorded as a scope event on livespec-dev-tooling-dfixhe at 2026-10-15T00:08Z ('I authorize you to run the revise on my behalf and approve them. Just go ahead and run them by a quick Fable subagent review to make sure there are no glaring problems and then you can run the revise...'), which names this proposal in its pending set. The driver's Fable subagent review returned APPROVE, no blockers. The independent read-only gpt-6-astra ratification review returned BLOCKERS in round 1 (scenario/contract exit-status mismatch) and NO BLOCKERS in round 2 on the exact final bytes.

## Modifications

1. contracts.md, paragraph 'A commit leg completes past one tool call': '`failed` when it exited on its own with a status from 1 to 127' became '`failed` when it exited on its own with any non-zero status', because git exits 128 on fatal errors (index.lock, bad ref) and the 1-to-127 range left that status in no state; signal death is already no-verdict. Requested by the driver's Fable review. 2. scenarios.md, Scenario 179, 'A commit refused by its hook is reported as failed': 'the hook's exit status' became 'the commit process's exit status', because the contract reports the commit process's status and a hook's own status can differ from git's. Raised as the one blocker of the gpt-6-astra round-1 review.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-15T00:21:50Z
verdict: NO BLOCKERS
proposal_stem: sandbox-commit-leg-completion
content_digest: d2d5fa41dcacc494fcbcc39893a43cac0c10998287585288ad8184ed11a56ac8
