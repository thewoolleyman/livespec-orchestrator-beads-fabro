---
proposal: credential-probe-reprobe.md
decision: modify
revised_at: 2026-09-07T05:46:36Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Ratify the bounded credential re-probe carrier with the scenario renumbered to 121 (the next free number; 118/119/120 taken by sibling revises and Carrier A). Intent unchanged. The open question the charter flagged -- whether a usable probe should retire an unexpired exhaustion record -- is resolved NO directly from ratified text (a probe is a non-dispatch-outcome host-side signal; the Dispatcher trusts only a dispatch outcome, and host/sandbox credential state diverge by construction). Independent read-only sonnet reviewer returned NO BLOCKERS on the exact resulting bytes.

## Modifications

Scenario renumbered 119->121 (next free at ratification: Carrier A landed 120, and 118/119 were taken by sibling revises v100/v101); heading-coverage entry renumbered and the explanatory numbering note updated. No change to the two clauses' substance.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-09-07T05:46:30Z
verdict: NO BLOCKERS
proposal_stem: credential-probe-reprobe
content_digest: cafe25842e99b6e51277187237eb595926f417801ac5212000a1d9cfbd399a92
