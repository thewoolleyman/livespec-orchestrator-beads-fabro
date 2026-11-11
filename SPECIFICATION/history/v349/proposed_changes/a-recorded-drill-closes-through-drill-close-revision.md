---
proposal: a-recorded-drill-closes-through-drill-close.md
decision: accept
revised_at: 2026-11-11T10:22:24Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accept as filed. The orchestrator companion of livespec-dev-tooling v188 (livespec-dev-tooling#4117, work item livespec-dev-tooling-io6hyk), which ratified that ending a drill incident chain belongs to this orchestrator and that its spec MUST govern the drill-closed phase, the drill-close verb and its fencing. As ratified here through v348 a drill can never end: the phase table stops at closed, the closure rule forbids discharging an incident from its expedited merge alone, and an unknown phase is a named configuration refusal. The four dev-tooling drills feh3s4, lli7hc, sdxw2v and wxeybc rest at reverting with repayment owed. The proposal adds the drill-closed row, makes drill-close the only writer of that phase (commit-transition refuses it with incident-drill-close-requires-action), fixes the forge-evidence drill test and its two named refusals, keeps drill-closed distinct from closed, repayment and completion, keeps reopen refused, and requires every incident reader released before any drill-close write. One Feature/Scenario covers it, with a spec-first TODO coverage row and debt row owned by bd-ib-z7ckf4. Plan expedited-incident-hardening (epic livespec-dev-tooling-dh3hub). The anchors it names are unchanged on master after v346-v348, so the text applies as written.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-11T09:55:56Z
verdict: NO BLOCKERS
proposal_stem: a-recorded-drill-closes-through-drill-close
content_digest: ef88454f4c6dc4c6993683350516cb822718513a74afa4f209a95be60e7f7a3d
