---
proposal: the-incident-authority-cli-has.md
decision: modify
revised_at: 2026-11-13T01:55:44Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:expedited-incident-hardening
---

## Decision and Rationale

The proposal closes the gap the dispatch-stage spec-change tier named when intake held bd-ib-txbv7i (verdict-kind partial, linked topic the-incident-authority-cli-has): §"Expedited incident lifecycle" requires standing, provenance, closure and inspection readers to accept a drill-closed head and preserve incident authority history, but states no item-only read that takes just a repository and an item id, reports phase and generation, authorizes nothing, and keeps absent distinct from unavailable. The need is measured: livespec-dev-tooling-io6hyk's factory run 01M78HQ4VS6E4PMFH73AFQJQEW ended BLOCKED at review_fix@2 on 2026-11-12T23:10:20Z because livespec-dev-tooling's incident fleet audit has no production phase read, and the released CLI offers only read-current and read-history, which need the full fenced identity plus --operation and --owner. The package already holds the reader: read_incident_head selects the chain's current generation from the item alone, refuses incident-authority-missing when no genesis exists (which read-head reports as absent), keeps ambiguous, invalid-genesis, item-mismatch and identity-mismatch as named refusals, and maps an outage to incident-authority-unavailable; the new paragraph exposes exactly that through the CLI and forbids treating the reply as authority for a side effect. Placement is correct under split (iii): the incident authority CLI is this plugin's realization and ships once here; the proposal's fleet sweep found only livespec-dev-tooling calling the CLI, with every existing caller keeping its fenced reads. legacy-coordinator-agent graded the proposal PASS at fd02fcc9 (livespec-orchestrator-beads-fabro#5106, merged 2026-11-13T01:38:05Z) after three grade fixes, and acked this seat's claim of the revise slot after v363 (queue order v363 immkx7, then txbv7i, then vpvdn4). Coherence with pending proposal incident-read-history-returns-only (livespec-orchestrator-beads-fabro#5048, open), which inserts at the same spot: there a no-genesis read-chain refuses incident-authority-missing, while read-head reports absent. That is a deliberate difference between two actions, not a contradiction. No existing H2 heading is added, removed or renamed in contracts.md.

## Modifications

One modification, under core revise split (i) (behaviour needs a scenario): (a) contracts.md takes the proposal's paragraph verbatim, inserted immediately after the §"Expedited incident lifecycle" paragraph that ends "developing and adopting this feature MUST use normal gates.", with one sentence appended: "Scenario 364 in `scenarios.md` exercises this paragraph." (b) scenarios.md gains `## Scenario 364 — An item-only head read reports an incident item's current phase and generation and authorizes nothing`, a Gherkin Feature with four cases: read-head reports phase and generation as read_incident_head selects them, drill-closed included, and authorizes no side effect; an item with no incident authority genesis reads absent, not refused; every other chain fault stays the canonical reader's named refusal, never absence and never a phase; an unreadable store refuses incident-authority-unavailable with no phase. 364 is the lowest number neither ratified on master (which tops at Scenario 363) nor claimed by any of the 70 open pull requests scanned at 2026-11-13T01:52Z (360-362 are claimed by #5060, #5067 and #5068). Co-edit outside the spec target, in the same commit: tests/heading-coverage.json gains a TODO row for Scenario 364 owned by bd-ib-txbv7i (integration tier or above), and tests/heading-coverage-debt.json gains the matching debt-register entry.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-13T01:54:02Z
verdict: NO BLOCKERS
proposal_stem: the-incident-authority-cli-has
content_digest: a0f97978aa0c1d20159ef18159a043ae4084fec30b2c4bf83bbf74627088d9bc
