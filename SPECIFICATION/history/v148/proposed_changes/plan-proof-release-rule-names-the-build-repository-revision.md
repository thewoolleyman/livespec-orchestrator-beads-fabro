---
proposal: plan-proof-release-rule-names-the-build-repository.md
decision: accept
revised_at: 2026-10-16T08:29:30Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted. Maintainer authorized continuing the recorded steps on 2026-10-16 (plan k3s-on-gmktec-for-vps-usage, livespec epic livespec-sab5gn), after approving the design direction on 2026-10-13 and ruling on 2026-10-14 that release tags are read from the forge remote, never a local clone. Motivation: the livespec plan k3s-on-gmktec-for-vps-usage shipped as livespec-dev-tooling releases (v1.95.12 captured, v1.96.1 verified), and archive_thread refused both honest records because the gate judged tags only against the governed repository. Review history: six independent Fable review rounds on the proposal, round 6 NO BLOCKERS. An earlier gpt-6-astra run against pre-v133 bytes was stopped. The proposal branch was rebased onto master at v147 (no conflicts; it adds only its proposal file), the resulting files were rebuilt from the proposal's quoted replacements (the contracts.md replacement re-wrapped to the paragraph's width), and the independent read-only ratification review (gpt-6-astra, codex session 01a143d1-c365-7422-8d65-cd8cca8388f7) returned NO BLOCKERS on these exact bytes, confirming the digest, that only the plan-record occurrence of 'recorded, not verified' changed, and no contradicting drift. No ## heading changes, so tests/heading-coverage.json is unchanged. Step 3.5 note: the stale-branch precondition was skipped explicitly; its only finding was this proposal's own branch, spec/plan-proof-release-rule-names-the-build-repository, which is the branch carrying this revise. Implementation carrier: a gate implementation work-item filed in livespec-orchestrator-beads-fabro after this revise (_plan_proof_leg.py, _plan_release_tags.py remote fail-closed read, prose/plan.md release paragraph); it is not dispatched until the 2026-10-14 factory stability freeze lifts.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-16T08:28:22Z
verdict: NO BLOCKERS
proposal_stem: plan-proof-release-rule-names-the-build-repository
content_digest: 3b41559830bff64c9ccec64f128a39ad4eb32ef1250ec9840752d5b5fce804ec
