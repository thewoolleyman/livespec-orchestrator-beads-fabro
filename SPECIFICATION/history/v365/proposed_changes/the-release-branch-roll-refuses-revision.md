---
proposal: the-release-branch-roll-refuses.md
decision: accept
revised_at: 2026-11-13T03:10:25Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:gmktec-factory-placement
---

## Decision and Rationale

The proposal makes the maintainer's 2026-11-13 direction mechanical at the one place every fleet clone's build moves. After 171ca17b2 (PR #4989) left fix_commit_settle's settled-success path ending in a bare exit 0 under output_schema="routing", six factory runs died RoutingBlocked even though the v0.321.0 canary had passed, because no sample completed a fix stage through its success edge. The coordinator named the rule CANARY-COVERS-CHANGED-PATHS (livespec-dev-tooling-6tgd2z) and ruled that the roll enforce it. The accepted text amends contracts.md §"Self-contained plugin dispatch": the release channel requires a canary coverage record, and a new **Canary coverage.** block defines the workflow scope, the base (the commit `release` names), the changed workflow paths including each changed node's success edge, the `canary-coverage.json` release asset with its journal citations and routing tests, the refusal cases, and the corrective roll-forward's binding to the record. Scenario 331 gains a coverage precondition on its advance case and five new cases (four refusals and one advance) inside its existing gherkin fence. Placement is correct: the roll workflow and the release channel are this orchestrator's own realization, so they belong in its contracts.md, and the dev-tooling sibling livespec-dev-tooling-faetyh (topic the-fleet-install-recipes-refuse) carries the install-recipe half. No `## ` heading is added, removed or renamed. legacy-coordinator-agent graded the proposal on livespec-orchestrator-beads-fabro#5107 and graded this pass's draft PASS on 2026-11-13, accepting the four edits verbatim with a minimal diff. Co-edit, ruled by the coordinator: Scenario 331's heading-coverage TODO row is re-owned from bd-ib-sghxlk, which is at acceptance and will close, to bd-ib-5psq3e, with an integration-tier reason naming both the release-channel cases and the canary-coverage cases; the debt register is regenerated.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-13T03:07:34Z
verdict: NO BLOCKERS
proposal_stem: the-release-branch-roll-refuses
content_digest: c5e53370852ebc91cdb3c75825ea55027e4fc8c699acc16e2e7fa7bb6a927bca
