---
topic: valve-summary-from-cause-comment
author: claude-opus-5-5
created_at: 2026-10-27T01:56:16Z
---

## Proposal: The valve summary renders the run account from the needs-human cause comment, without a factory read

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

In 'Run account in the valve summary': when a blocked needs-human item carries the livespec-needs-human-cause comment its termination wrote for its latest run, the needs-attention valve summary renders from it (and the preserve-by-reference comment) and runs no fabro inspect or other factory read; without such a comment it falls back to the existing factory read.

### Motivation

Routed by petri-factory-on-gmktec, spec-first for work-item bd-ib-ltfh5p (coordinator rulings R24 and R73, released from scratch), whose launch-time Codex screen at 2026-10-27T01:44Z found its two assertions ungoverned by Scenario 125 and "## Dispatcher policy settings": comment-sourced rendering with no inspect call, and the missing-comment fallback. The item exists because needs-attention runs `fabro inspect` on every blocked needs-human item's run on every pass, although each such item already carries the durable `livespec-needs-human-cause` comment its termination wrote (§"A factory run never awaits a human"), which holds the run account; the preserved reference sits in the item's preserve-by-reference comment. The fail-soft rule is unchanged, and items terminated before the comment existed keep the factory read.
A first read-only Codex review raised two blockers, folded in: the factory identity, preserved reference and valve actions keep their local sources (only missing run-reported details are omitted), and Scenario 125's unreachable-factory case is scoped to items without a cause comment, with a new case where the comment keeps the account.

### Proposed Changes

1. In `SPECIFICATION/contracts.md`, §"Dispatcher policy settings" → "### The human answer route: marker, poison preflight, run account, and write-before-transition ordering", bullet "**Run account in the valve summary.**", replace

```
  The enrichment MUST fail soft: an unreadable config or an unreachable factory
  costs the ENRICHMENT and never the valve — the valve item is surfaced regardless,
  and each factory is addressed by its declared server target.
```

with

```
  The enrichment MUST fail soft: an unreadable config or an unreachable factory
  costs the ENRICHMENT and never the valve — the valve item is surfaced regardless,
  and each factory is addressed by its declared server target.
  When the item carries the needs-human cause comment its termination wrote
  (§"Dispatcher policy settings" → "A factory run never awaits a human"), the
  summary MUST render the run account from that comment, take the preserved
  reference from the item's preserve-by-reference comment for the same run,
  resolve the factory name and its server from the item's recorded factory and
  the committed configuration as before, and list the available valve actions
  as before, and the surface MUST run no `fabro inspect`, and no other factory
  read, for that item.
  When the item carries more than one such comment, the newest one written for
  the item's latest run governs. When the item carries no such comment, or none
  for its latest run, the summary MUST fall back to reading the run from its
  factory exactly as before, so an item whose run was terminated before that
  comment existed renders as it did. A run-reported detail that the governing
  comment does not carry, such as what the run reported, is omitted from the
  summary rather than read from the factory.
  Measured 2026-10-26: `needs-attention` ran `fabro inspect` on every blocked
  needs-human item's run on every pass, although each carried the comment that
  already held that account.
```

2. In `SPECIFICATION/scenarios.md`, Scenario 125, scenario "An unreachable factory costs the enrichment and never the valve", replace

```
    Given a blocked needs-human work-item whose factory is unreachable
```

with

```
    Given a blocked needs-human work-item whose factory is unreachable and that carries no needs-human cause comment for its latest run
```

3. In `SPECIFICATION/scenarios.md`, inside the gherkin block of "## Scenario 125 — The needs-attention valve item carries the terminated run's account and fails soft", append after its last scenario:

```gherkin

  Scenario: The valve summary renders from the needs-human cause comment without a factory read
    Given a blocked needs-human work-item carrying the livespec-needs-human-cause comment its termination wrote for its latest run
    When needs-attention renders the item's resolve-blocked valve item
    Then the summary carries the run account from that comment and the preserved reference from the item's preserve-by-reference comment
    And no fabro inspect or other factory read is run for the item

  Scenario: An item without the cause comment falls back to the factory read
    Given a blocked needs-human work-item whose run was terminated before the needs-human cause comment existed
    When needs-attention renders the item's resolve-blocked valve item
    Then the summary carries the run account read from the factory exactly as before

  Scenario: A cause comment keeps the run account when the factory is unreachable
    Given a blocked needs-human work-item carrying the needs-human cause comment for its latest run, whose factory is unreachable
    When needs-attention renders the item's resolve-blocked valve item
    Then the summary carries the run account from that comment
    And no factory read is attempted for the item
```

No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.
