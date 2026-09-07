---
proposal: ready-aging-dispatch-tiebreak.md
decision: accept
revised_at: 2026-09-07T06:45:33Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus (control-plane-accounts-and-dispatch-policy)
---

## Decision and Rationale

Ratifies the ready-aging dispatch tiebreak (b5 leg 4, bd-ib-rh3iyd.2). Equal-rank ties break by ready-age past dispatcher.ready_aging_threshold_hours; rank stays primary; aging-aware key lives in the livespec_runtime-owned ready_sort_key, composed identically by next and the Dispatcher (no second Dispatcher sort key), so the impl depends on a livespec_runtime change — per the maintainer's 2026-09-07 rider. Scenario 123 + heading-coverage co-edit. Explicit maintainer ratification go-ahead; local doctor-static and heading-coverage green; independent Sonnet read-only ratification review NO BLOCKERS on the exact resulting bytes.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-09-07T06:44:03Z
verdict: NO BLOCKERS
proposal_stem: ready-aging-dispatch-tiebreak
content_digest: a9203b26ee486c9f7161535b622ad03547fe172c8f324c28191788ca19eeae44
