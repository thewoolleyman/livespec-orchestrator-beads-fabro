---
topic: design-record-archived-path
author: claude-opus-4-8
created_at: 2026-07-20T04:01:00Z
---

## Proposal: Design-record citations name a path that no longer exists

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Both `Design record:` citations in contracts.md name `plan/autonomous-mode/handoff.md` in repo `thewoolleyman/livespec`. That plan thread was ARCHIVED 2026-07-20 to `plan/archive/autonomous-mode/handoff.md`, so both citations now name a path that does not resolve. This repoints them. Path-only: the archive move preserved the cited section byte-for-byte under its original heading, so both section-name references stay valid and only the directory changes.

### Motivation

The livespec-core plan thread `plan/autonomous-mode/` was superseded and archived on 2026-07-20 as part of splitting a 3220-line thread that had become coupled and non-cohesive. Two citations in this repo name that path as the DESIGN RECORD for the six dispatcher policy settings. This matters more than an ordinary broken link: per the intent-preservation discipline the cited design record is the TIEBREAKER over shipped spec text when the two disagree, so a dangling design-record citation silently removes the tiebreaker for those settings. Citation fidelity here is review-enforced only — no mechanical check catches a dangling design-record path, which is exactly why this is being repaired deliberately rather than left to be discovered. The repair is landed in the same window as the archive move so no period exists in which the citations dangle.

### Proposed Changes

--- CHANGE 1: SPECIFICATION/contracts.md, the Dispatcher policy settings rationale ---
REPLACE the line reading VERBATIM:

`plan/autonomous-mode/handoff.md`, the "SESSION UPDATE — 2026-07-14 (cont. 12)" section

with VERBATIM:

`plan/archive/autonomous-mode/handoff.md`, the "SESSION UPDATE — 2026-07-14 (cont. 12)" section

--- CHANGE 2: SPECIFICATION/contracts.md, the wip_cap no-per-item-override clause ---
REPLACE the line reading VERBATIM:

`plan/autonomous-mode/handoff.md`, the "SESSION UPDATE — 2026-07-14 (cont. 12)"

with VERBATIM:

`plan/archive/autonomous-mode/handoff.md`, the "SESSION UPDATE — 2026-07-14 (cont. 12)"

--- CLAUSE-COUNT NOTE for the revise step ---
PATH-ONLY change. Neither line carries a whole-word MUST or SHOULD, so no
normative clause is added, removed, or reworded, and this repo's ground-truth
rule counts are UNCHANGED. No tests/heading-coverage.json co-edit is required:
no `## ` heading changes and no clause gap-id changes.

