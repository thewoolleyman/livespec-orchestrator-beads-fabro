---
topic: tree-can-pass-under-the-harness-judging-it
author: claude-opus-5-5
created_at: 2026-11-07T19:53:21Z
---

## Proposal: A tree a factory run resumes or seeds can pass under the harness judging it

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Require that a tree resumed or seeded by the factory can pass its own test suite under the harness judging it, whatever its age or pin, in every fleet repository, while an agent stage's own publication attempts stay refused.

### Motivation

Measured 2026-11-07 on a host, not in a factory sandbox. Run 01M6VBWZNCDH5WGJM7VQH9M77Z (bd-ib-72hvx5) routed resume and its review_fix@1 commit hook refused, naming six integration test files that pass on a host. On that run's seed tree 4e2cdbbf0, over those six files: with the run's own projected push_origin bytes and LIVESPEC_AGENT_STAGE=review_fix, 13 failed and 15 passed, with 10 LIVESPEC_AGENT_PUBLICATION_DENIED lines. With the variable unset, 28 passed. With the variable set plus master's _hermetic_agent_stage_publication_guard fixture added to the seed's conftest, 28 passed. The mechanism: the dispatching build projects a guard-bearing push_origin into the sandbox, the seed's workflow script calls that helper when it is present, and a tree older than 2b2c55a9d has no fixture clearing the variable, so its own commit hook runs its own tests into the guard. A separate error the run reported, 'sh: 1: {{: not found', does not appear in this reproduction and stays an unreproduced possible second fault.

A recovery route exists to keep work, and this defect spends that work: the run judged the seed tree by a harness newer than the tree, not by whether the tree is sound. legacy-coordinator-agent ruled under R301 on 2026-11-07, recorded as the coordinator's and not the maintainer's, that the requirement is stated as behaviour with no staleness bound by age or by dev-tooling pin. An age bound would refuse sound trees and a pin bound does not reproduce this failure: the same files pass on 4e2cdbbf0 under its own lock.

The requirement reaches every fleet repository because the guard and the stage variable reach every repository's factory runs. On origin/master of seven other fleet repositories no conftest clears the variable. A static read found no test there executing a guarded route, but older seeded trees and indirect calls were not traced, so another repository hitting this is not ruled out.

This section is the requirement. How it is met is the choice between the two option sections below, which is the maintainer's. A revise of this file MUST accept this section and exactly one of the two options; it MUST NOT settle that choice without the maintainer's answer.

### Proposed Changes

In SPECIFICATION/contracts.md, under "## Self-contained plugin dispatch", immediately after the paragraph "**Publication is mechanically confined to the scripted publication stages.**", add this paragraph:

> **A tree a factory run resumes or seeds can pass under the harness judging it.** A tree that a factory run resumes or seeds from MUST be judged on what it contains, not on the difference between its age and the dispatching build's harness. Whatever the tree's age or its dev-tooling pin, in every fleet repository, the tree's own test suite run by a commit hook inside an agent stage MUST NOT fail because a harness mechanism the dispatching build projected into the sandbox acted on that suite. This requirement sets no staleness bound. An agent stage's own call of the projected `gh` wrapper or `push_origin` helper MUST still be refused as the preceding paragraph states.

In SPECIFICATION/scenarios.md, add a new scenario, numbered at revise as the next free number, under the heading "## Scenario NNN — A resumed or seeded tree older than a harness guard passes its own commit hook, and an agent stage's own publication stays refused":

```gherkin
Feature: A tree a factory run resumes or seeds can pass under the harness judging it
  As the maintainer of a repository dispatched to the factory
  I want a recovered tree judged on what it contains
  So that a recovery route does not spend the work it exists to keep

  Scenario: A tree with no fixture clearing the stage variable passes its own commit hook
    Given a factory run resumed or seeded from a tree whose test suite exercises the workflow's push helper and carries no fixture clearing LIVESPEC_AGENT_STAGE
    And that suite passes on a developer host
    When an agent stage's commit runs that suite through the commit hook
    Then no case of the suite reports LIVESPEC_AGENT_PUBLICATION_DENIED

  Scenario: The requirement holds in a repository that has changed nothing
    Given a factory run dispatched against a fleet repository other than this one
    And that repository has merged no change for this requirement
    When an agent stage's commit runs that repository's suite through the commit hook
    Then no case of the suite reports LIVESPEC_AGENT_PUBLICATION_DENIED

  Scenario: An agent stage's own publication attempt stays refused
    Given an implement, fix or review_fix turn
    When the turn itself calls the projected push_origin or a publication action of the projected gh wrapper
    Then the call exits non-zero and prints LIVESPEC_AGENT_PUBLICATION_DENIED with the stage and the refused action
```

Add the new heading to tests/heading-coverage.json and tests/heading-coverage-debt.json in the revise commit, owned by bd-ib-s754le.

## Proposal: Option Scrub (recommended): keep the stage variable away from a tree's test suite

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Meet the requirement from the harness side: a test process started inside an agent stage does not inherit the guard's activation, whatever the tree. RECOMMENDED by the filing plan seat. Mutually exclusive with Option Refresh; the choice is the maintainer's.

### Motivation

Why this is recommended. It is the measured fix: with the variable cleared, 28 passed on the seed unchanged. It needs no edit to the tree, so it preserves a seeded tree byte for byte, which is what a recovery route is for, and it holds in a repository that has merged nothing, which a per-repository fixture cannot. It does not weaken the publication boundary: §"Publication is mechanically confined" rests on an agent stage holding no publication credential, and the guard exists so that an attempt is named rather than surfacing as an authentication failure. A test process that escapes the guard still has no credential to publish with.

What it costs. It fixes this skew only. A different difference between an old tree and a newer harness would need its own fix, and if the unreproduced 'sh: 1: {{: not found' turns out to be such a difference, this option does not cover it. No mechanism has been built or measured in a sandbox. A commit hook's shell is started by the tree's own hook, so the clearing has to come from something the harness owns, and an implementer must prove the route.

### Proposed Changes

In the paragraph added by the requirement section of this file, append:

> The harness MUST meet this by keeping the guard's activation out of test processes: a process running the tree's test suite inside an agent stage, whether a commit hook or the agent started it, MUST NOT inherit `LIVESPEC_AGENT_STAGE`, and the means MUST be harness-owned, requiring no change to the tree or to the repository. A test case that exercises the guard MAY set the variable in its own child environment, and that case MUST still observe the refusal.

Add a scenario step to the requirement's scenario "A tree with no fixture clearing the stage variable passes its own commit hook": "And the seeded tree's bytes are unchanged by the harness".

## Proposal: Option Refresh: bring a resumed or seeded tree up to the default branch before its first commit hook

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Meet the requirement from the tree side: a resumed or seeded tree takes the default branch before its first commit hook, so it holds every harness-facing fix. Not recommended by the filing plan seat. Mutually exclusive with Option Scrub; the choice is the maintainer's.

### Motivation

Why it is offered. It addresses the whole class, not one skew: a refreshed tree holds every harness-facing fix on the default branch, including any behind the unreproduced 'sh: 1: {{: not found'. A refresh-repair path already exists at publication (LIVESPEC_REFRESH_REPAIR), and master's fixture alone passes the measured failure (28 passed).

Why it is not recommended. It changes the tree a recovery route exists to preserve, before the first commit hook. The measured seed's base was 928 commits behind master, so a refresh can conflict, and resolving a conflict takes an agent turn: on bd-ib-akxkza run 01M6RX4RY5CQHJMQYWRSR4G8DK a refresh-repair's first full hook ran about 32 minutes of a 60-minute turn. It also changes what the requirement can promise: a repository whose default branch carries no such fixture, which is every other fleet repository read here on origin/master, needs its own change first, so accepting this option replaces the requirement's scenario "The requirement holds in a repository that has changed nothing" as stated below.

### Proposed Changes

In the paragraph added by the requirement section of this file, append:

> The harness MUST meet this by refreshing the tree: before the first commit hook of a run whose recovery route is `resume` or `seeded`, the run MUST bring its tree up to the default branch, keeping the seed's own commits. A conflict MUST route to the existing refresh-repair path, and the seed ref MUST stay on origin until the run's tree has been preserved. Every fleet repository's default branch MUST carry whatever its suite needs to pass under the harness, so a refreshed tree inherits it.

Add a scenario step to the requirement's scenario "A tree with no fixture clearing the stage variable passes its own commit hook": "And the tree holds the default branch's current head before that hook runs".

Replace the requirement's scenario "The requirement holds in a repository that has changed nothing" with one whose Given reads "a factory run dispatched against a fleet repository other than this one, whose default branch carries what its suite needs to pass under the harness". A revise accepting this option MUST also re-word bd-ib-s754le's Definition of Done assertion that says "without that repository first merging a change of its own".
