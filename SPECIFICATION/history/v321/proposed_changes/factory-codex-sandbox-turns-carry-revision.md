---
proposal: factory-codex-sandbox-turns-carry.md
decision: modify
revised_at: 2026-11-08T05:56:23Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accept the parity rule legacy-coordinator-agent ruled on 2026-11-03 (bd-ib-v75dlb): a factory sandbox turn of either runtime carries its Driver's PreToolUse guards at the release the run pins, and on Codex the hooks are trusted only on a byte match to that release tag, with a mismatch failing the prepare step. An untrusted PreToolUse guard fails open on Codex 0.166.0 (livespec-driver-codex-sjwyha), so trust must be established from verified bytes rather than bypassed. The clause, the scope sentence and the Verification sentence land as proposed. The scenario is modified only in form.

## Modifications

The appended scenario is conformed to this file's scenario layout: it takes the next free number (328), a Governing clause line naming constraints.md section "Codex full-access runtime constraints" and its new bullet, a Feature header with its As/I want/So that lines, and two named Scenario blocks. The second block restates the first block's two Given lines instead of "Given the same run", so each scenario stands alone. Every Given, When and Then step is otherwise carried verbatim. The constraints.md inserts are re-wrapped to the section's line width and list indentation; their words are unchanged. tests/heading-coverage.json gains the TODO entry for the new heading, with a reason naming the integration tier and owning work-item bd-ib-v75dlb.

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
reviewed_at: 2026-11-08T05:54:09Z
verdict: NO BLOCKERS
proposal_stem: factory-codex-sandbox-turns-carry
content_digest: 2a4b23a3fdff74bd2b7027a5b90f0f740329a2ba5bf6d256dc549af66c780e3d
