---
topic: a-failed-forge-comparison-in
author: claude-opus-5-5
created_at: 2026-11-14T04:50:58Z
---

## Proposal: An unread forge ancestry comparison refuses currency as unobservable, never as an older base

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

§"Fabro currency admission" already requires the upstream base to be the latest-published release tag whose tagged commit is an ancestor of the serving integration commit. It does not say what the predicate does when it cannot read one of those ancestry comparisons. This proposal makes an unread comparison (non-zero exit, timeout, or no recognisable status) a distinct refusal before any mutation: an unobservable ancestry read that names the unread tag and the failure, carries a retry corrective route rather than a re-pin route, and never resolves an older tag as the base. Scenario 130 gains one scenario exercising it.

### Motivation

On 2026-11-14 orchestrator v0.329.0 refused a petri dispatch (livespec-dev-tooling-pxqxti, 04:31:21Z) as base-out-of-window, resolving serving commit d22808f to base v0.312.0-nightly.0 (2026-08-01). That base is wrong: the forge compare of v0.408.0-nightly.0...d22808f8e reads `ahead` (43 ahead, 0 behind), and v0.408.0-nightly.0 (published 2026-11-05) sits at publication index 2 of the 161-release observation, ahead of v0.312.0-nightly.0 at index 55. The implementation treats a failed `gh` comparison as "not an ancestor" and walks on to the next-older tag. The evaluation straddled the host's hourly core REST budget reset at about 04:31, so the comparisons at indices 2-54 failed, v0.312's was the first that succeeded, and the window rule then refused a current engine. The refusal's corrective route told operators to re-pin petri's Fabro build, which would have been a needless production restart. The same item passed currency six minutes later. Linked work-item: bd-ib-kvy72t (plan bd-ib-6tcjfx, fabro-currency). Its spec-change-tier verdict was partial: the selection rule already excludes the older base, but the unobservable refusal, its evidence and its retry route are not stated.

### Proposed Changes

In SPECIFICATION/contracts.md §"Fabro currency admission", in the second paragraph, immediately after the sentence ending "or the base is outside the 30-calendar-day window.", insert:

> A forge ancestry comparison that exits non-zero, times out, or returns no recognisable comparison status is an UNREAD comparison; it is not evidence that the compared tag is not an ancestor. When any comparison is unread before the predicate has found a release-tag ancestor of the serving integration commit, the predicate MUST refuse before any mutation as an unobservable ancestry read. The refusal MUST name the release tag whose comparison was unread and the comparison's failure. The predicate MUST NOT resolve any older release tag as the upstream base past an unread comparison, and MUST NOT refuse that dispatch on the 30-calendar-day window rule with such a base. The corrective route of an unobservable ancestry read MUST direct the operator to retry the dispatch once the forge comparison can be read, and MUST NOT direct a re-pin or rebuild of the factory's Fabro build.

The third paragraph's evidence list ("Every refusal MUST name the factory target; ...; the failed currency condition; and the corrective route.") is unchanged and applies to this refusal too; for it, the resolved upstream base is reported as unresolved.

In SPECIFICATION/scenarios.md, inside the gherkin block of "## Scenario 130 — Dispatch admits only a current, identifiable Fabro base", immediately after the scenario "Stale release evidence and a failed refresh refuse" (before "Stable and nightly releases use the same publication-time rule"), insert the following scenario. It adds no H2 heading, so tests/heading-coverage.json is unchanged:

```gherkin
  Scenario: An unread ancestry comparison refuses as unobservable rather than resolving an older base
    Given the selected factory target serves an integration commit descended from an in-window published release tag
    And the forge comparison of that tag against the serving integration commit fails or times out
    And the comparison of an older published release tag succeeds
    When dispatch evaluates currency
    Then dispatch refuses before claim, ledger mutation, or run creation as an unobservable ancestry read
    And the refusal names the tag whose comparison was unread and the comparison's failure
    And the older release tag is not resolved as the base and the dispatch is not refused as out of window
    And the corrective route directs a retry once the comparison can be read, not a re-pin of the factory's Fabro build
```

The implementation MUST realize this through the existing shared predicate and its sources module; no new dispatch path is added.
