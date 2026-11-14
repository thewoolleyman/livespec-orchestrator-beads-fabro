---
topic: the-review-fix-open-red
author: claude-opus-5-5
created_at: 2026-11-14T09:59:23Z
---

## Proposal: The review_fix open-Red visit limit counts only consecutive passes on an open Red, and resets when no Red is open

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

State the scope and size of the review_fix stage's open-Red visit limit. It counts only consecutive passes of review_fix_open_red_route that find the stage's last commit an open Red. A pass that finds no open Red resets the count to zero. The stage ends at needs_human with a LIVESPEC_REVIEW_FIX_OPEN_RED_VISIT_BOUND_EXHAUSTED cause naming the open Red on the third such consecutive pass, which allows two re-entries per open Red.

### Motivation

The ratified paragraph 'A fix turn grades each tree once, through its commit hook.' says 'When the stage's visit limit is reached while its last commit is still an open Red, the run MUST end at needs_human with a cause naming the open Red commit', but it does not say what the limit counts or how large it is.

The workflow counts every pass of review_fix_open_red_route, before it checks for an open Red, and never resets the count. So review_fix visits spent and passed in EARLIER review rounds use up the limit, and a later round's FIRST hook-refused Green amend ends the run.

Measured 2026-11-13/14 (MEASUREMENT comment on plan epic bd-ib-3goerg; factory-run-yield's measurement):
- livespec-dev-tooling-g3mnat run 01M7AVFMTHA1 (232 run-min) and bd-ib-hofndb run 01M7AX6ZJRED (234 run-min). Their earlier rounds' visits passed, and a later round's first refusal hit the limit.
- bd-ib-jaaya5 run 01M7BQC0B37A and livespec-dev-tooling-ie7fas run 01M7BKMKTXME ended the same way.
The limit exists to stop a loop on ONE open Red, not to cap review rounds; review rounds have their own cap.

The dispatch-time spec-change-tier judgement on the carrier item bd-ib-nkyeve (2026-11-14T00:22:24Z, linked topic the-review-fix-open-red) holds it because the ratified text does not state this scope.

### Proposed Changes

1. In SPECIFICATION/contracts.md, paragraph '**A fix turn grades each tree once, through its commit hook.**', after the sentence 'When the stage's visit limit is reached while its last commit is still an open Red, the run MUST end at needs_human with a cause naming the open Red commit.' insert:

'For the `review_fix` stage, that visit limit MUST count only the consecutive passes of `review_fix_open_red_route` that find the stage's last commit an open Red, and a pass that finds no open Red MUST reset the count to zero. Review_fix visits spent in earlier review rounds, or on an open Red whose Green amend has since passed, therefore never count against a later open Red. The limit is reached on the third such consecutive pass, which allows two re-entries per open Red, and the cause MUST carry the marker `LIVESPEC_REVIEW_FIX_OPEN_RED_VISIT_BOUND_EXHAUSTED`. Measured 2026-11-13/14: a count kept across review rounds ended four runs at their first refusal in a later round (livespec-dev-tooling-g3mnat 01M7AVFMTHA1, bd-ib-hofndb 01M7AX6ZJRED, bd-ib-jaaya5 01M7BQC0B37A, livespec-dev-tooling-ie7fas 01M7BKMKTXME).'

2. In SPECIFICATION/scenarios.md, under '## Scenario 199 — A fix turn grades each tree once, through its commit hook', inside the existing gherkin block, after the scenario 'An open Red at the stage's visit limit ends at needs_human naming it', add:

```gherkin
  Scenario: Review_fix visits in earlier review rounds do not count against a later open Red
    Given a run whose review_fix visits in two earlier review rounds each ended with no open Red
    And a later review round's review_fix turn ends on an open Red whose Green amend its commit hook refused
    When review_fix_open_red_route runs
    Then the run re-enters review_fix to complete that open Red's Green amend
    And the run does not end at needs_human for the visit limit

  Scenario: Three consecutive passes on one open Red reach the review_fix visit limit
    Given a review_fix stage whose last commit stays the same open Red across three consecutive passes of review_fix_open_red_route
    When the third such pass runs
    Then the run ends at needs_human with a LIVESPEC_REVIEW_FIX_OPEN_RED_VISIT_BOUND_EXHAUSTED cause naming that open Red
```

No H2 heading is added, changed or removed, so tests/heading-coverage.json is unchanged.
