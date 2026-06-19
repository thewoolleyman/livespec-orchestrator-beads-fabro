---
proposal: grooming-gherkin-and-gap-detectability.md
decision: accept
revised_at: 2026-06-19T17:34:37Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Accept as-written, maintainer-authorized. Proposal 1 converts Scenarios 1-7 to Gherkin (form-only for 1-6, semantics preserved). Proposal 2 adds the ### Gap-detectable behavior clauses H3 subsection in contracts.md with 8 MUST/SHOULD clause lines and Scenarios 8-15 in scenarios.md, written against observable behavior; the two open realization choices stay unresolved.

## Resulting Changes

- scenarios.md
- contracts.md
- ../tests/heading-coverage.json
