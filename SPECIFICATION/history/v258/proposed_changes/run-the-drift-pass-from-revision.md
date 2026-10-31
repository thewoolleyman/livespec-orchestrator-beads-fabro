---
proposal: run-the-drift-pass-from.md
decision: accept
revised_at: 2026-10-31T16:17:52Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:split-drift-check-from-cleanup-timer
---

## Decision and Rationale

Accepted as filed. The proposal generalizes §"The skill surface" → "The drift run." bullet, the target the spec-change tier classifier named when it held work-item bd-ib-dwzkjg at dispatch on 2026-10-31 against v257. It states the drift job's entry point `dispatcher.py drift-run --repo <path> --invoker <role:name>`, its `--json` outcome (the drift lane outcome a reconcile pass carried under its `drift` key before v219 split it out), and a `--dry-run` that runs no drift lane, invokes no model judgement and writes neither the frontier nor the detection-coverage anchor; it also forbids any repository installer from enabling a drift-run schedule, carrying the maintainer's 2026-10-25 ruling that the drift job stays stopped until the token-waste fixes land and the maintainer turns it on. The behaviour is exercised by a new gherkin scenario inside the existing Scenario 207, so no H2 heading and no heading-coverage entry changes. It extends, and contradicts nothing in, the v219 text. The Step 3.5 stale-branch check was skipped with narration: its two findings are other sessions' branches that touch none of this text (spec/host-judgement-isolation, whose content landed as v222, and the WIP spec/reprove-merged-item-v2).

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-31T16:16:00Z
verdict: NO BLOCKERS
proposal_stem: run-the-drift-pass-from
content_digest: 8a9f48433496125c988f82925cb1a38edd3aa948ed35ca7063a74ce9ae20d870
