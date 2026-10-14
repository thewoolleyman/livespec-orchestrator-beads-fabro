---
proposal: factory-run-wall-budget.md
decision: modify
revised_at: 2026-10-14T00:41:57Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted under this repository's maintainer-armed delegated revise-decision mode (spec_governance.revise_decision_mode: delegated) and the coordinator's standing directive (plan gitops-fleet-capacity-monitoring, livespec-dev-tooling-dfixhe) to drive plan factory-run-wall-budget (epic bd-ib-hqt3s5) to completion. Nothing bounds a whole factory run today: per-node timeouts and the stall window bound one node and one quiet stretch, and the fabro run subprocess ceiling is a derived worst case (145800 s here). On hp, runs that ended at needs_human held slots 200-390 minutes against a 99-minute successful median. The default of 21600 s is sized above every ImplementWorkItem success since 2026-10-07 (max 348 min of 94), so it is not a false kill of a measured healthy run. The cancel reuses ratified rails: export-then-terminate from 'A factory run never awaits a human', the progress watchdog's cancel-record fields and resume anchoring, and its not-non-convergence rule. No design record is contradicted; the command-node guard and the stall cancel record are scoped to stalled-no-progress in place, and the resume clause's cancel anchor is widened in place to admit the budget record under its unchanged restrictions.

## Modifications

Three independent read-only review passes by OpenAI Codex gpt-6-astra (the configured ratification_reviewer_model). Pass 1 raised four blockers, all applied: (1) the Progress paragraph's open-command-node guard now applies to stalled-no-progress cancels only, and the budget paragraph says it does not defer a budget cancel; (2) the cancel record paragraph is scoped to stalled-no-progress cancels, a budget cancel journals run-wall-budget-exceeded and never watchdog-stall-cancel, and the resume clause's anchor admits either record under its existing stage, head and proof-precedence restrictions; (3) the budget key resolves through its own three layers (built-in default 21600, the target's .livespec.jsonc, a per-dispatch --run-wall-budget-seconds argument; the workflow graph declares none) with invalid values refused before any run; (4) Scenario 175 gained the non-progress count, no automatic admission, exact-budget, start-instant fallback, unreadable-head, resume-anchor and precedence sub-scenarios. Pass 2 raised three, all applied: a measured exceeded budget takes precedence over a simultaneous stall (including while an export is held); the queue-time sub-scenario asserts no cancel on the budget only; the held-export sub-scenario asserts a retry on the immediately following poll, and an outline covers invalid values from both sources. Pass 3 (Codex session 01a137d9-6ad7-7831-9dfc-fcd972e3c035) returned NO BLOCKERS on the final bytes. The contracts.md budget key is placed as its own paragraph after the Keys paragraph rather than inside its sentence. tests/heading-coverage.json and tests/heading-coverage-debt.json gain a TODO row for Scenario 175 owned by bd-ib-sdxfsn in the same change.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-14T00:40:30Z
verdict: NO BLOCKERS
proposal_stem: factory-run-wall-budget
content_digest: f18c3a6006b8e9c2dfac46c59f304519b0c5853b0b8d0b2f03b2c9e71c9ddee4
