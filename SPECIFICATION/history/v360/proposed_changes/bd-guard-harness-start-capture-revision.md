---
proposal: bd-guard-harness-start-capture.md
decision: modify
revised_at: 2026-11-12T08:22:08Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Modify, as filed but for punctuation. The proposal generalizes the lifecycle guard test-harness bullet of "Beads substrate constraints" and Scenario 269 with three things the ratified text left unstated: (a) a liveness probe that fails while the capture server may still be alive, such as `kill -0` refused with a permission error, is not an exit, and the start wait keeps its 30-second bound; (b) every wait on the server is bounded, with a 10-second stop bound observed through the harness's diagnostic rather than by timing the harness, like the existing start bound; (c) a server still running after its stop fails the case with a line naming it, so the run ends red instead of never ending. Measured in livespec-dev-tooling-ddy5xu: on gamingpc-xubuntu, AppArmor denied kill(2) inside the gate container. bd-guard/test/run-tests.sh start_capture read the refused `kill -0` as an exit and called an unbounded `wait` on a live capture.py, and stop_capture's `kill; wait` had no bound either, so check-bd-guard held 3 of 3 full-suite gates open to the client's 3600 s bound. legacy-coordinator-agent (session c8c6cc4b) graded the proposal PASS (livespec-orchestrator-beads-fabro#5009) and confirmed that no other fleet repository carries the harness. The new stop scenario states an event, not elapsed time, so it is compatible with Scenario 304's ban on wall-clock tests. No H2 heading changes. The Scenario 269 heading-coverage row keeps its integration-tier test and is owned by implementation item bd-ib-w4bbbd until that test covers the three new cases. The debt register is unchanged on regeneration, because the row is not a TODO.

## Modifications

Punctuation only: in the constraints bullet, the em-dash pair around the `kill -0` example is rendered as commas. No normative word, bound or scenario differs from the proposal.

## Resulting Changes

- constraints.md
- scenarios.md
- ../tests/heading-coverage.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-12T08:21:16Z
verdict: NO BLOCKERS
proposal_stem: bd-guard-harness-start-capture
content_digest: 5f6389068dcc55b4f267bfa281622ac2a30f84e1175ca68909d59019c63045a4
