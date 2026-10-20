---
topic: gap-signal-from-heading-coverage
author: claude-fable-5-1:spec-implementation-lockstep
created_at: 2026-10-20T00:58:39Z
---

## Proposal: Gap detection reports spec headings with no exercising test, not clauses with no work-item

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The gap signal changes from "a MUST/SHOULD clause not yet tracked by a work-item" to "an H2 heading of the governed spec tree with no exercising test", read from tests/heading-coverage.json. detect-impl-gaps enumerates headings whose coverage entry is absent or carries the literal test value TODO, derives one stable gap id per heading from the spec file and the heading path, and keeps its --since-version file-scoping. capture-impl-gaps files one gap-tied item per uncovered heading, naming the heading and the coverage entry to fill. The clause-enumeration signal is retired, because every clause has no work-item until one is filed, so that signal surfaced 752 to 1,233 candidates per run and no run completed.

### Motivation

Plan spec-implementation-lockstep (epic bd-ib-ax3rds), Definition of Done assertion 10: gap detection reports only spec headings that have no exercising test, not clauses that lack a work item. Measured 2026-10-19 in this repository: the detection-coverage anchor bd-ib-j5fzyo carries 18 capture-impl-gaps attempt records, the last completed point is v122 against a spec at v165, and past runs surfaced between 752 and 1,233 candidates. The heading-without-test signal already exists mechanically: tests/heading-coverage.json holds 251 entries, 128 of them marked TODO, each with an owner work-item. Maintainer ruling 2026-10-19: existing drift and gap noise is debt to be reconciled, and the spec is to be generalized rather than expanded.

### Proposed Changes

In SPECIFICATION/contracts.md, section "The skill surface" → "Heavyweight authored skills" → "capture-impl-gaps":

1. Replace the first paragraph ("Surface untracked spec clauses as candidate work-items ...") with: "Surface spec headings that no test exercises as candidate work-items by invoking the sibling `/livespec-orchestrator-beads-fabro:detect-impl-gaps --json` thin-transport skill (no in-skill duplication of the detection logic; both this skill and doctor consume the same canonical surface)."

2. Replace the "Naming note" paragraph with: "**Naming note.** Despite the `-impl-gaps` name, this operation performs NO spec↔impl comparison. `detect-impl-gaps` (below) enumerates the H2 headings of the governed spec tree whose entry in the repository's heading-coverage map (`tests/heading-coverage.json`) is absent or names no exercising test, and never reads implementation state. A returned gap-id means \"this heading has no exercising test\", never \"this heading's behaviour is verified absent from the implementation\"."

3. In the paragraph beginning "The returned gap-ids are presented to the user one at a time", after "carrying the `origin:gap-tied` and `gap-id:<stable-id>` labels" insert: ", whose title names the uncovered heading verbatim and whose description names the coverage entry the implementing change MUST fill with the exercising test". The remainder of the paragraph MUST remain unchanged.

In SPECIFICATION/contracts.md, section "The skill surface" → "Thin-transport skills" → "detect-impl-gaps":

4. Replace the "Naming note" paragraph with: "**Naming note.** This is a heading-coverage enumerator, not a spec→impl comparator — despite the `-impl-gaps` name, it never reads implementation state. It reads the spec tree and the heading-coverage map and nothing else."

5. Replace the paragraph beginning "The skill reads the live Specification via the Spec Reader, enumerates every MUST/SHOULD rule" with: "The skill MUST read the live Specification's H2 headings via the Spec Reader and the repository's heading-coverage map, and MUST emit exactly one gap per H2 heading whose map entry is absent or whose `test` value is the literal `TODO`. A heading whose entry names an exercising test MUST NOT produce a gap. The skill MUST compute a stable `gap_id` per heading as a pure function of the spec file path and the canonical heading path, so the same heading always yields the same gap-id across runs. It MUST NOT enumerate MUST/SHOULD clauses, because a clause with no work-item is the ordinary state of every ratified clause and that signal surfaced 752 to 1,233 candidates per run in this repository without one completed pass. This skill is substrate-agnostic — it reads the spec tree and the coverage map, never the work-items store."

6. In the "`--since-version <vN>`" paragraph, replace "For each such file, only MUST / SHOULD clauses present in the live version are considered (clauses removed by the diff are not gaps — they were spec content that no longer exists)." with "For each such file, only H2 headings present in the live version are considered (headings removed by the diff are not gaps — they were spec content that no longer exists)." In the "Caller caution" paragraph, replace "resurfaces EVERY live MUST/SHOULD clause it contains" with "resurfaces EVERY uncovered live H2 heading it contains" and replace "a diff of newly-introduced clauses" with "a diff of newly-introduced headings".

7. Add, after the "Caller caution" paragraph: "**Migration of clause-derived gap ids.** A gap-tied work-item filed under the retired clause enumeration carries a clause-derived `gap-id:` label. The change that lands this clause MUST re-label every live such item with the heading-derived gap-id of the heading its clause sits under, so livespec core's `gap-tracking-one-to-one` and `no-stale-gap-tied` invariants pass on this repository against the new enumeration. A closed item keeps its historical label."

In SPECIFICATION/scenarios.md, under "## Scenario 1 — Gap-tied fix cycle" (the heading is unchanged, so tests/heading-coverage.json needs no change for it):

8. Replace the lines "And enumerates every MUST/SHOULD rule from spec text alone (no read of the impl)" and "And surfaces every rule not yet tracked by a work-item, one at a time" with "And enumerates every H2 heading whose heading-coverage entry names no exercising test (no read of the impl)" and "And surfaces every such heading not yet tracked by a work-item, one at a time".

9. Add, at the end of SPECIFICATION/scenarios.md, a new scenario heading (tests/heading-coverage.json MUST gain an entry for it in the same revise):

## Scenario 205 — Gap detection enumerates headings without an exercising test

```gherkin
Feature: The gap signal is heading coverage, not clause tracking
  As a maintainer keeping the spec and its tests in lockstep
  I want gap detection to name the spec headings no test exercises
  So that every candidate it surfaces is a real, bounded piece of work

  Scenario: An uncovered heading is a gap and a covered one is not
    Given a governed spec tree whose heading-coverage map marks one H2 heading TODO and names an existing test for another
    When detect-impl-gaps runs with --json
    Then it emits exactly one gap, whose gap-id derives from the uncovered heading's spec file and heading path
    And the covered heading produces no gap
    And no MUST or SHOULD clause is enumerated

  Scenario: A filed gap names the heading and the coverage entry to fill
    Given the uncovered heading above
    When the user consents to file it through capture-impl-gaps
    Then the filed item carries the origin:gap-tied label and the heading-derived gap-id label
    And its title names the heading verbatim and its description names the coverage entry to fill

  Scenario: Clause-derived gap ids are migrated to heading-derived ones
    Given a live gap-tied item filed under the clause enumeration
    When the change landing this clause runs its migration
    Then the item carries the heading-derived gap-id of the heading its clause sits under
    And livespec core's gap-tracking-one-to-one and no-stale-gap-tied invariants pass
```
