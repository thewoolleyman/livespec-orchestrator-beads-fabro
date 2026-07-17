---
proposal: enumerate-per-item-override-and-move-drive-actions.md
decision: accept
revised_at: 2026-07-17T06:03:00Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

De-drifting ratification: contracts.md and README.md are amended so the drive action-id enumerations reflect the ten shipped human operator actions (approve, accept, reject, resolve-blocked, set-admission, set-acceptance, the three per-item cap overrides with the clear-to-inherit sentinel, and the guarded move), the config family is named in the grammar sentence, scenarios 46 and 47 are appended, and tests/heading-coverage.json is co-edited for the two new H2 headings. Passed independent Fable review with NO BLOCKERS; all four replace-targets matched the live tree verbatim.

## Resulting Changes

- contracts.md
- README.md
- scenarios.md
- ../tests/heading-coverage.json
