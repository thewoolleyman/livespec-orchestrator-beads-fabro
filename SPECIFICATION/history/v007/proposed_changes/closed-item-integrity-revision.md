---
proposal: closed-item-integrity.md
decision: accept
revised_at: 2026-06-19T21:53:19Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

User pre-authorized acceptance of the single pending proposed change closed-item-integrity.md. Both ## Proposal sections are applied as written: (1) the ## Closed-item integrity invariant in constraints.md (BCP14 MUST: a closed gap-tied resolution:completed item carries the label AND binds its acceptance scenario to a real integration-tier test, never TODO; closed-but-unproven is forbidden), cross-referencing the existing §Forbidden patterns silent-close rule; (2) the ### Closed-item-integrity check H3 in contracts.md (always-wired, always-running, severity lever LIVESPEC_CLOSED_ITEM_INTEGRITY=warn|fail default warn, reuses the shared livespec_spec_clauses extractor + clauses[] map + beads reader) plus ## Scenario 16 in scenarios.md (the failing + passing Gherkin cases). heading-coverage co-edit adds the two new H2 entries (Scenario 16, ## Closed-item integrity) as TODO+reason; clauses[] links are DEFERRED to the implementation step per the proposal's own precondition (impl-beads ships no clauses[] map or extractor yet — adopting it is the first impl work-item).

## Resulting Changes

- constraints.md
- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
