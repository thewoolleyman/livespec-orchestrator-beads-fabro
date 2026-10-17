---
topic: janitor-inherits-no-routing-variables
author: claude-opus-5-5:fabro-currency
created_at: 2026-10-17T10:53:51Z
---

## Proposal: The janitor check run inherits none of the dispatcher's routing and attribution variables

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a clause to contracts.md §"Dispatcher admission, WIP cap, and post-merge acceptance", beside the existing "Post-merge and reconcile janitor venue" clause, and a new Scenario 189. The post-merge janitor's and the reconcile-merged janitor's check run MUST NOT inherit the dispatcher's factory-routing and invoker-attribution environment variables, and the janitor-post-merge journal row MUST name each variable removed. The co-edit adds a tests/heading-coverage.json entry for the new scenario heading.

### Motivation

The post-merge janitor runs the target repository's check aggregate with the DISPATCHER's own process environment. The dispatcher is routed and attributed through environment variables: LIVESPEC_FABRO_FACTORY selects the factory, and it is the ONLY route to a non-default factory through drive; LIVESPEC_INVOKER stamps journal attribution. A repository's test suite legitimately exercises the code that reads those same variables, so their presence in the janitor's check run changes test outcomes. A merge whose default-branch CI is green is then reported red, and the item strands at active with no merge audit.

Measured on 2026-10-17 (work-item bd-ib-fd26sc). bd-ib-o6aeji ran as Fabro run 01M546F896H5 on hp-candidate, routed with LIVESPEC_FABRO_FACTORY=hp-candidate, and merged PR #3157 as 0766415e; master ci-green on 0766415e was success. The janitor went red with 25 failed tests in its check-coverage and check-per-file-coverage targets. Controlled in the kept janitor checkout, one variable at a time: test_dispatch_records_factory_and_retry_reuses_it passes with neither variable set and fails with only LIVESPEC_FABRO_FACTORY set; test_omitted_repo_resolves_to_the_current_working_directory passes with neither and fails with only LIVESPEC_INVOKER set. A clean-shell just check in the same checkout passed all 93 targets, and a reconcile-merged from a clean shell reported the janitor green. Every merge dispatched through the documented environment-variable route to a non-default factory therefore strands, which blocks an honest factory cutover. The maintainer directed fixing this root cause on 2026-10-17. Nothing in the spec currently governs the janitor check run's environment: the existing venue clause governs only WHERE the checkout is provisioned.

### Proposed Changes

### contracts.md — §"Dispatcher admission, WIP cap, and post-merge acceptance"

Insert directly after the paragraph that begins **Post-merge and reconcile janitor venue.**:

**Post-merge and reconcile janitor environment.** The post-merge janitor and the reconcile-merged janitor MUST run the target repository's check aggregate in an environment from which the dispatcher's own factory-routing and invoker-attribution variables have been removed. That set is at least `LIVESPEC_FABRO_FACTORY` and `LIVESPEC_INVOKER`, and it MUST include any later variable the dispatcher reads to select a factory or attribute a journal record. Those variables describe how THIS dispatch was routed and attributed. They are not part of the merged code under test, and a repository's suite legitimately exercises the code that reads them, so inheriting them makes the janitor's verdict depend on the dispatch route rather than on the merge. The janitor MUST NOT otherwise alter the environment the check aggregate receives: credentials and the toolchain path the check needs are retained. The `janitor-post-merge` journal row MUST name each variable it removed, and it MUST record an empty list when none was present, so a reader can tell a scrubbed run from one that inherited nothing. This clause governs only the check run's ENVIRONMENT. It is not a new step of the closed set and adds no pre-dispatch refusal.

### scenarios.md — new scenario, appended after Scenario 188

```
## Scenario 189 — The post-merge and reconcile janitor's check run inherits none of the dispatcher's routing and attribution variables

```gherkin
Feature: The janitor's check verdict depends on the merge, not on how the dispatch was routed,
  so a dispatcher routed or attributed through its environment cannot turn a green merge red

  Scenario: A dispatch routed through LIVESPEC_FABRO_FACTORY reports a green janitor for a green merge
    Given a dispatcher whose environment carries LIVESPEC_FABRO_FACTORY and LIVESPEC_INVOKER
    And a merged item whose default-branch CI is green
    When the post-merge janitor runs the repository's check aggregate
    Then the check run's environment carries neither LIVESPEC_FABRO_FACTORY nor LIVESPEC_INVOKER
    And the janitor reports green
    And the janitor-post-merge journal row names LIVESPEC_FABRO_FACTORY and LIVESPEC_INVOKER as removed

  Scenario: The reconcile-merged janitor applies the same scrub
    Given a reconcile-merged invocation whose environment carries LIVESPEC_INVOKER
    When the reconcile janitor runs the repository's check aggregate
    Then the check run's environment does not carry LIVESPEC_INVOKER

  Scenario: A dispatcher with no routing variables records an empty removal list
    Given a dispatcher whose environment carries neither variable
    When the post-merge janitor runs
    Then the janitor-post-merge journal row records an empty list of removed variables
```
```

### tests/heading-coverage.json — co-edit (resulting_files)

The revise MUST add one entry for the new heading: `spec_root` `SPECIFICATION`, `spec_file` `scenarios.md`, heading `## Scenario 189 — The post-merge and reconcile janitor's check run inherits none of the dispatcher's routing and attribution variables`. `test` MAY be the literal `TODO` with the reason `implementation owed by bd-ib-fd26sc, which binds an exercising integration test`.
