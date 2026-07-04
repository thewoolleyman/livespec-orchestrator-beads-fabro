---
proposal: lessons-brief-injection.md
decision: accept
revised_at: 2026-07-04T09:42:53Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Accept as filed. Codifies the consumer half of the reflection gate's human-ratified lessons loop (epic livespec-impl-beads-29f decision 7): dispatch-brief composition sources lessons exclusively from the committed loop-reflection-gate/lessons.md, injects ratified text into every subsequent brief, leaves briefs unchanged when the file is absent/placeholder-only/unreadable (fail-open), and never lets unmerged reflector-PR content influence a brief. This is the spec anchor for work-item livespec-impl-beads-29f.10, which implements TO these clauses (the bd-ib-umno37 / SPECIFICATION v024 spec-first precedent). Scenario numbers finalized to 39 and 40: the pending orchestrate-plan-surfaces-unarchived-plan-threads proposal that claimed 39 is intentionally left unprocessed this pass, so 39 is free. Behavior carries a BCP14 clause set plus the two Given/When/Then scenarios; tests/heading-coverage.json is co-edited for the new contracts H2 and the two new scenario H2s.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
