---
proposal: factory-addresses-from-a-gitops-registry.md
decision: accept
revised_at: 2026-10-18T16:11:09Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by a fork of session petri-factory-on-gmktec under the maintainer's binding ruling recorded on plan epic bd-ib-fyozyd at 2026-10-17T21:55Z (a spec proposal that fixes a measured defect blocking plan work is session-ratifiable after an independent review). It carries plan Definition of Done item 4: no committed factory entry names a machine hostname. The configured ratification reviewer, gpt-6-astra in separate read-only Codex sessions, reviewed it in six rounds (records under plan/petri-factory-on-gmktec/research/003-reviews/): round 1 BLOCKERS, round 2 BLOCKERS, round 3 NO BLOCKERS on revision 2 with one nit since applied, round 4 NO BLOCKERS on that revision's resulting bytes, round 5 NO BLOCKERS on revision 3 (docker_host, its should-fix and nit applied), and round 6 (codex session 01a14fc3-3b1a-7932-b5ba-1003837ccd17) NO BLOCKERS on these exact resulting-file bytes on the v160 base, with an independently recomputed digest. The proposal was amended to revision 3 before this revise, answering rounds 1, 2 and 5, so the resulting files carry its two blocks verbatim; the Scenario 182 coverage entry is a TODO owned by work-item bd-ib-fubkcv, with its debt row.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-18T16:08:08Z
verdict: NO BLOCKERS
proposal_stem: factory-addresses-from-a-gitops-registry
content_digest: 7ec5114f7aaa8e593497ed3ee406dfd4638b3c96ec96eb471cf5f6cf8f3b775e
