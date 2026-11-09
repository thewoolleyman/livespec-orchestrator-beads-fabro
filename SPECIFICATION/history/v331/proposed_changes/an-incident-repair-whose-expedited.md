---
topic: an-incident-repair-whose-expedited
author: claude:expedited-incident-response-flag
created_at: 2026-11-09T07:22:10Z
---

## Proposal: A repair whose expedited PR closed unmerged after a failed fast check opens a corrected attempt

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds the missing successor for an incident `repair` attempt whose `pr-bound` expedited pull request failed a retained fast check on its exact head and was then closed without merging. The same canonical item opens a corrected `repair` attempt as the next generation on a fresh `branch-reserved` carrier under a different target ref, retaining the failed run as the corrected attempt's failure evidence. The writer MUST first observe through the forge that the bound pull request is closed unmerged at its bound head and that the named run concluded failure on that head, and MUST refuse by name otherwise. The failed bound carrier stays in history as written; the correction is an appended successor, not a rewrite.

### Motivation

Measured 2026-11-08 on livespec-dev-tooling incident livespec-dev-tooling-e62ss6 (plan expedited-incident-response-flag, epic livespec-dev-tooling-bqnzcm), attempt 3: expedited PR livespec-dev-tooling#3828 (carrier `pr-bound`, generation 18) failed its retained fast check `check-file-lloc` in run 42520940297 and was closed unmerged. The ratified text admits a corrected repair only after a merged attempt is reverted and its failures collected (`collecting-failures`), and §"Carrier identity before and after PR creation" freezes a carrier once it leaves `branch-reserved` and pins its PR once `pr-bound`. A repair whose bound PR fails before merge therefore has no sanctioned successor, and the incident item can reach neither repayment nor closure. Any real incident whose expedited PR trips a retained fast check stops in the same place. Work item bd-ib-elq5ry.

### Proposed Changes

In `contracts.md` §"Carrier identity before and after PR creation", append one paragraph after the paragraph that ends "Unsupported carrier schema/state MUST produce a named capability/configuration refusal, never normal-mode fallback or an improvised second parser.":

```diff
+A `repair` attempt whose `pr-bound` expedited pull request failed a retained fast check before merge MAY be followed by a corrected `repair` attempt on the same canonical item. The successor MUST be the next generation under a new attempt id and a new operation id, with a fresh `branch-reserved` carrier on a fully qualified `refs/heads/...` target ref different from the failed carrier's, no PR number, no landed identities, and normal repayment still owed. The failed attempt and its `pr-bound` carrier MUST remain in the authority history exactly as recorded: the correction is an appended successor, never a rewrite of the bound carrier, and a `branch-reserved` successor on the failed carrier's own target ref MUST still be refused. Before committing that successor, the writer MUST observe through an authenticated forge read that the attempt's bound pull request is closed and not merged at the carrier's exact head and target ref, and that the operator-named workflow run completed with conclusion failure on that exact bound head. When the forge does not show the pull request closed unmerged at that head, or the named run is unreadable, incomplete, not a failure, or ran on another head, the writer MUST refuse by name and record nothing. The failed run, its head and the closed pull request MUST be retained in the item's recovery record as the corrected attempt's failure evidence and MUST join the item's retained failures. The unchanged-reland rule of §"Expedited incident lifecycle" applies: the correction MUST carry fresh repair or measured-resolution evidence, a repair's head MUST NOT equal any retained failed head, and its evidence MUST NOT reuse a retained failed run.
```

No other clause changes. The phase table row for `repair` ("Authorized canonical entry or corrected repair with fresh evidence.") already admits a corrected repair and is unchanged.

In `scenarios.md`, under `## Scenario: an attributable regression fences repayment and reopens the same incident`, append two gherkin scenarios to its feature block, after its existing scenario:

```gherkin
  Scenario: an expedited repair PR closed unmerged after a failed fast check opens a corrected attempt
    Given an incident repair attempt whose carrier is pr-bound to an expedited pull request
    And a retained fast check run concluded failure on that pull request's exact bound head
    And the forge shows that pull request closed and not merged
    When the operator opens a corrected repair attempt naming that run with fresh repair evidence on a new target ref
    Then the same incident item records a new repair attempt at the next generation on a fresh branch-reserved carrier
    And the failed pr-bound attempt remains in the authority history as recorded
    And the failed run and its head are retained as the corrected attempt's failure evidence
    And final normal factory repayment remains owed on that item

  Scenario: a corrected attempt from an unmerged expedited PR is refused without forge proof or fresh evidence
    Given an incident repair attempt whose carrier is pr-bound to an expedited pull request
    When the forge shows that pull request open or merged, the named run did not conclude failure on its bound head, or the correction's head equals that failed head or its evidence reuses that failed run
    Then opening the corrected repair attempt MUST be refused by name
    And no generation and no recovery record is written
```

No H2 heading is added or removed, so heading coverage is unchanged.
