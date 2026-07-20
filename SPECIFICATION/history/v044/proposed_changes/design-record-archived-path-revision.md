---
proposal: design-record-archived-path.md
decision: accept
revised_at: 2026-07-20T04:10:24Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Independent Fable review returned NO BLOCKERS on this proposal's own content: all replace-targets verified verbatim and unique as whole lines, the destination section verified byte-identical in the archived file, clause counts verified unperturbed (no MUST/SHOULD on any affected line), and completeness verified (these are two of exactly three live-spec citations fleet-wide). The one blocker the review raised was an orphaned untracked history/v044 doctor auto-backfill left in this worktree by an earlier direct-edit attempt; it was deleted before this revise so the ratification mints v044 genuinely rather than committing a fabricated snapshot. CHANGE 1 applied before CHANGE 2 per the review's substring-hazard note (CHANGE 2's target is a strict prefix of CHANGE 1's line); both were asserted unique and the post-state asserted to carry zero old-path and exactly two new-path references.

## Resulting Changes

- contracts.md
