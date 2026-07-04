---
topic: lessons-brief-injection
author: claude-fable-5
created_at: 2026-07-04T06:57:54Z
spec_commitments:
  impl_followups:
    - id_hint: lessons-brief-injection-consumer
      description: |
        Implement the dispatch-brief lessons-injection consumer per the new contracts.md section 'Dispatch-brief lessons injection' and the two new scenarios: brief composition reads ONLY the committed loop-reflection-gate/lessons.md, injects ratified lesson text into every subsequently composed dispatch brief, leaves briefs unchanged when the file is absent / placeholder-only / unreadable, and never reads unmerged reflector-PR content. The impl-side work-item ALREADY EXISTS: livespec-impl-beads-29f.10 (this repo's tenant). Pair that item to this commitment via its spec_commitment_hint field and update its description/notes to cite the new spec clauses instead of the epic-description sketch (the bd-ib-umno37 / SPECIFICATION v024 precedent: the spec captures the contract, the item the mechanism).
---

## Proposal: Dispatch-brief lessons injection contract (ratified lessons only)

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a contracts.md section codifying the consumer half of the reflection gate's human-ratified lessons loop: the Dispatcher's dispatch-brief composition sources lessons exclusively from the committed loop-reflection-gate/lessons.md (the merged, human-ratified file), injects ratified lesson text into every subsequently composed dispatch brief in a delimited lessons section, leaves briefs unchanged when the file is absent or carries no ratified lessons (no header or placeholder bleed-through), treats an unreadable or malformed lessons file as absent rather than failing dispatch (fail-open), and never lets unmerged reflector proposals or any other uncommitted edit influence a brief. Two new scenarios ratify the inject and never-inject halves. This is the spec anchor for work-item livespec-impl-beads-29f.10, which implements TO these clauses.

### Motivation

Epic livespec-impl-beads-29f decision 7 and the design-of-record (loop-reflection-gate/best-practices-and-design.md section 7 question 10; loop-reflection-gate/lessons.md ratification model) fix the lessons loop as human-ratified: the reflector PROPOSES via PR, a human ratifies by MERGING, and only merged content ever injects, because auto-injection of unreviewed LLM lessons into every future brief is prompt-injection-shaped and dilutes briefs. The proposer half shipped (GitPrLessonsProposer); NO code reads the merged file, and the live spec is silent on both lessons and dispatch-brief composition (zero occurrences of either term), while contracts.md specifies adjacent dispatcher behavior in detail (admission valve, WIP cap, post-merge acceptance, grooming bounce). Implementing the consumer before amending the contract would manufacture impl-to-spec drift that capture-spec-drift would then flag; the repo's own precedent runs the other way (bd-ib-umno37: contract codified as SPECIFICATION v024, item implements TO the clauses). This proposal originated from the plan/loop-reflection-gate planning thread's spec-first resequencing (2026-07-04). In-flight alignment, surveyed 2026-07-04: zero open spec-touching PRs; all six remote spec/* branches are stale (content already landed on master or in history/v024-v026). The two pending proposals are orthogonal and this proposal ALIGNS with both: approval-is-the-pending-approval-to-ready-transition amends admission/valve and autonomous-mode text, and orchestrate-plan-surfaces-unarchived-plan-threads amends the orchestrate composition and claims Scenario 39 - neither touches brief composition, so this proposal claims Scenarios 40-41 (renumber at revise if the queue order shifts).

### Proposed Changes

**A. New section — `SPECIFICATION/contracts.md`, inserted as a new `## Dispatch-brief lessons injection` H2 section immediately after §"Full autonomous mode" (before §"Beads connection model").** Body:

> This section codifies the consumer half of the reflection gate's human-ratified lessons loop (design-of-record: `loop-reflection-gate/lessons.md` §"Ratification model — proposal → PR → merge" and `loop-reflection-gate/best-practices-and-design.md` §7 question 10; the proposer half is the reflector's `LessonsProposer` seam). Ratification is a HUMAN act: the reflector proposes a lesson by opening a PR that edits `loop-reflection-gate/lessons.md`, and a lesson is ratified if and only if a human merges that PR. No autonomous path MAY ratify a lesson.
>
> - The Dispatcher's dispatch-brief composition MUST source lessons EXCLUSIVELY from the committed content of `loop-reflection-gate/lessons.md` as present in the working tree it dispatches from — the merged, human-ratified file.
> - When that file carries at least one ratified lesson, every subsequently composed dispatch brief MUST include the ratified lesson text, carried in a clearly delimited lessons section of the brief.
> - When the file is absent, or present but carrying NO ratified lessons (for example only its header and placeholder), brief composition MUST leave the brief unchanged: no lessons heading, placeholder text, or file boilerplate may bleed into the brief.
> - A lessons file that cannot be read or parsed MUST be treated as absent (briefs unchanged). Lessons injection MUST NOT block, fail, or alter the disposition of any dispatch (fail-open), matching the reflection gate's stability posture that reflection never changes a dispatch verdict.
> - Content proposed on an unmerged reflector PR — or any other uncommitted edit to the lessons file — MUST NOT influence brief composition.

**B. New scenario — `SPECIFICATION/scenarios.md`, appended as `## Scenario 40 — Ratified lesson injects into dispatch briefs`** (number provisional against the pending proposal claiming 39; renumber at revise if needed):

```gherkin
Feature: dispatch-brief lessons injection
  As the factory operator
  I want human-ratified lessons to reach every dispatch brief
  So that the ratified improvement loop actually changes future dispatch behavior

Scenario: a merged ratified lesson appears in composed briefs
  Given loop-reflection-gate/lessons.md is committed and carries ratified lesson text "L"
  When the Dispatcher composes a dispatch brief for an admitted work-item
  Then the composed brief contains lesson text "L" in its delimited lessons section
```

**C. New scenario — `SPECIFICATION/scenarios.md`, appended as `## Scenario 41 — Unratified or absent lessons never alter briefs`:**

```gherkin
Feature: unratified lessons are inert
  As the maintainer supervising the improvement loop
  I want unratified or absent lessons to leave briefs untouched
  So that only content I merged can steer future dispatches

Scenario: absent or placeholder-only lessons leave the brief unchanged
  Given loop-reflection-gate/lessons.md is absent, or present with no ratified lessons
  When the Dispatcher composes a dispatch brief
  Then the composed brief is identical to one composed with no lessons file
  And no lessons heading or placeholder text appears in the brief

Scenario: an unmerged reflector proposal never injects
  Given an open reflector PR proposes lesson text "M" against loop-reflection-gate/lessons.md
  And the committed loop-reflection-gate/lessons.md does not contain "M"
  When the Dispatcher composes a dispatch brief
  Then the composed brief does not contain "M"

Scenario: an unreadable lessons file fails open
  Given loop-reflection-gate/lessons.md exists but cannot be read or parsed
  When the Dispatcher composes a dispatch brief
  Then the composed brief is identical to one composed with no lessons file
  And the dispatch proceeds normally
```

**D. Heading-coverage co-edit — `tests/heading-coverage.json`.** The revise pass accepting this proposal MUST add entries for the three new `## ` headings (`Dispatch-brief lessons injection` in contracts.md; Scenarios 40 and 41 in scenarios.md) via its `resulting_files[]` mechanism, per the repo's revise co-edit discipline (`test` MAY be the literal "TODO" with a non-empty reason until the consumer lands its tests).
