---
proposal: preserve-runs-sh-keeps-every.md
decision: modify
revised_at: 2026-11-13T17:11:49Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Ratified under delegated decision. legacy-coordinator-agent graded it PASS and gave the GO for this revise (2026-11-13 about 17:0xZ, the orchestrator slot after v370 = 447bc06c6). It releases bd-ib-yw7yot's spec-change-tier hold (refused at dispatch 2026-11-13T16:55:40Z, verdict unstated, linked topic preserve-runs-sh-keeps-every). The revise applies decisions in created_at order, so each later decision's resulting files carry every earlier decision's edits and the last full-file write keeps all four.

## Modifications

The scenario number is assigned: "## Scenario:" becomes "## Scenario 370 —", and the paragraph's closing sentence names Scenario 370. 370 is the next free number: master's highest is 369, and no pending proposal or open spec pull request claims 370 or above (checked 2026-11-13 about 17:06Z over 20 open branches). The heading's first word is capitalized to "An", following the convention of every numbered scenario heading. The tests/heading-coverage.json row carries the numbered heading, and tests/heading-coverage-debt.json is regenerated with `uv run python -m livespec_dev_tooling.heading_coverage_debt` in the same commit. The text is otherwise as graded.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-13T17:08:59Z
verdict: NO BLOCKERS
proposal_stem: preserve-runs-sh-keeps-every
content_digest: 9fe35a6fc6b68479382267c39504e0935d661a4014f6b85634ed2e027bd416d0
