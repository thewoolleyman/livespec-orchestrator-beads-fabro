---
proposal: released-item-recovery-routing.md
decision: accept
revised_at: 2026-10-15T20:36:44Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted under the maintainer's delegation recorded on livespec-dev-tooling-dfixhe (2026-10-15T00:08Z and 00:09Z rulings), as exercised by the stability freeze driver gitops-fleet-capacity-monitoring, which directed this revise. This session did not receive that authorization from the maintainer directly. Review history: the driver's Fable review of the first draft returned BLOCK on four text fixes, all applied before filing (PR 3069). The independent ratification review (gpt-6-astra, read-only) round 1 (codex session 01a14129-ed4c-77b3-9302-8c26396954b9) returned BLOCKERS: the four routes were not exhaustive for a live ownership lock or a merged pull request. That was fixed in the proposal by classifying resume refusals as fallback-permitting or non-fallback, and the driver's Fable delta review approved it with three tidies, all applied. Round 2 (01a1412f-c12d-7761-bf2d-a4bb480b5bcf) and round 3 (01a14135-2493-7ba1-992d-6801b4147448) returned NO BLOCKERS, round 3 on these final bytes. Deviations from the proposal text, each accepted by the ratification reviewer: the change-1b replacement ends in ';' at both sites, because each continues an inline numbered list; change 4 moves the bullet's list-closing ';' to the end of the appended sentence; the Scenario 185 heading sits outside the gherkin fence, matching the file's convention. Heading coverage: a Scenario 185 TODO row and debt row owned by bd-ib-qgcpoc are added, and Scenario 172's coverage and debt rows move from bd-ib-3snvbf to bd-ib-qgcpoc, because the 2026-10-15 re-cut moved Scenario 172's recovery scenarios to bd-ib-qgcpoc. Step 3.5 note: the stale-branch precondition was skipped explicitly for its only finding, spec/plan-proof-release-rule-names-the-build-repository (another thread's branch, which adds only its own proposed-change file and does not touch contracts.md or scenarios.md); v144 recorded the same skip under the driver's authorization. Implementation carrier: bd-ib-qgcpoc (plan stall-watchdog-false-kills, epic bd-ib-laf735); the provider-limit carriers bd-ib-ogymgj and bd-ib-kn7ktk share the mechanism.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-15T20:17:44Z
verdict: NO BLOCKERS
proposal_stem: released-item-recovery-routing
content_digest: cbbf3df3f14a5acf6db7f4106a7ab76755f7aa9f4fb45fe3c3fea871ef348881
