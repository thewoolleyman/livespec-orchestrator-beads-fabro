---
topic: janitor-failed-target-attribution
author: codex
created_at: 2026-10-09T15:01:08Z
---

## Proposal: Attribute janitor failure to the aggregate summary

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Complete existing plan assertion 4 and child bd-ib-ma3fvj: a failed janitor must identify the runner summary targets rather than a passing recipe in its stderr tail. Scenario145 already governs private retention under sibling bd-ib-nezrrh; add the missing diagnostic attribution contract and controls without duplicating retention or widening implementation scope.

### Motivation

The user authorized autonomous completion of run-lifecycle-false-verdicts. A related child failed its specification-reference gate, prompting a scoped audit of the queued janitor item. Its sole Scenario145 reference covers retained logs but not the diagnostic attribution assertions. This amendment fills that existing requirement, with ma3fvj retaining its dependency on nezrrh.

### Proposed Changes

Insert this subheading immediately after the existing failed-janitor retention clause and append Scenario167. Co-edit tests/heading-coverage.json with a Scenario167 TODO owned by existing bd-ib-ma3fvj. Existing v122 terminal-evidence bytes remain unchanged.

### Failed post-merge janitor target attribution

When a failed post-merge janitor's aggregate runner emits a structured
`Failed targets` summary, the Dispatcher MUST name every target in that summary
in both the dispatch outcome detail and the `janitor-post-merge` journal row.
It MUST inspect the complete captured output before applying any diagnostic
tail bound: a summary on stdout or before later output MUST NOT be replaced by
the last recipe printed on stderr, and a long target list MUST NOT be truncated
into an incomplete failure attribution. Passing recipe output outside the
structured summary MUST NOT be presented as the cause of failure.

When no structured failed-target summary is present, the Dispatcher MUST label
its bounded stdout and stderr excerpts as observations, without asserting that
a recipe in an excerpt failed. The full private artifact's path and digest
remain the deep-diagnosis reference governed by the retention clause above.
Extracted failed-target names are permitted diagnostic metadata on the outcome
and journal surfaces; this exception to the bounded-excerpt limit permits only
those target names, not additional captured command output. It MUST NOT change
artifact privacy, retention-failure behavior, exit codes or item disposition.
These reporting obligations apply equally to member and adopter repositories;
an aggregate with no recognized summary uses the labelled-excerpt fallback.
Scenario 167 in `scenarios.md` exercises this section.


## Scenario 167 — A failed janitor names the aggregate runner's failed targets

Governing clause: `contracts.md` §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Failed post-merge janitor target attribution".

```gherkin
Feature: report failure attribution from the aggregate summary
  Scenario Outline: complete failed-target names survive unrelated later output
    Given a real janitor command exits nonzero and emits a structured Failed targets summary
      And its summary names <targets> on stdout before later output exceeds the diagnostic tail bound
      And its stderr tail names a passing recipe not in that summary
    When the Dispatcher reports the post-merge janitor result
    Then the outcome detail and janitor-post-merge journal row name every summarized failed target
      And they do not attribute the failure to the passing recipe
      And the journal names the retained private complete-output artifact and its digest
      And the original nonzero exit and ordinary item disposition are preserved
    Examples:
      | targets                                  |
      | two distinct failing targets             |
      | a target list longer than the tail bound |

  Scenario: absence of a structured summary does not invent a cause
    Given a real failed janitor emits distinct stdout and stderr without a structured Failed targets summary
    When the Dispatcher reports its result
    Then it labels bounded excerpts from both streams as observations
      And it does not claim a recipe in either excerpt caused the failure
      And the full private artifact remains the deep-diagnosis reference when retention succeeds

  Scenario: retention failure does not erase the observed attribution
    Given a failed janitor emitted a structured Failed targets summary
      And its private artifact cannot be written
    When the Dispatcher reports its result
    Then it still names the observed failed targets and journals the retention-write failure reason
      And the command exit code and ordinary non-green disposition are unchanged
      And it does not fabricate a retained artifact path or digest
```

