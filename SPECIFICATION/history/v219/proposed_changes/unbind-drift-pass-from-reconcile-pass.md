---
topic: unbind-drift-pass-from-reconcile-pass
author: claude-opus-5-5
created_at: 2026-10-25T18:52:35Z
---

## Proposal: Run the drift pass from its own drift job, never from a reconcile pass

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The drift run is unbound from the Dispatcher's reconcile pass and becomes its own drift job. A reconcile pass MUST NOT run the drift pass and MUST NOT invoke any model judgement, and the drift job runs only on a schedule an operator explicitly enables.

### Motivation

Maintainer ruling 2026-10-25 (plan split-drift-check-from-cleanup-timer, epic bd-ib-oi2nyu): "The cleanup job only does cleanup, no LLM spend, and it runs as intended. The drift check should be split out to its own separate job, but then it also needs to be improved so it doesn't waste tokens. It needs to be stopped after the split-out." Since 357919fd7 the 10-minute reconcile-runs timer ran the drift pass on every tick because this clause bound it to every reconcile pass. With the drift frontier stalled behind held findings, every tick re-judged 76 merges with a full spec-tree model call: about $135 of Anthropic spend in 25 minutes on 2026-10-25. The timer was stopped and disabled, which also took down stranded-run completion and claim release for every factory run. Separating the two jobs lets the deterministic cleanup restart at once while the drift job stays stopped until it is made cheap.

### Proposed Changes

In SPECIFICATION/contracts.md §"Detection coverage records and staleness facts":

1. In the **Records.** bullet, replace "every drift run of a reconcile pass or a post-merge janitor" with "every drift run of the drift job or a post-merge janitor".

2. In **The drift run.** bullet, replace "Each reconcile pass of the Dispatcher MUST enumerate every default-branch merge after the recorded frontier" with "Each run of the Dispatcher's drift job MUST enumerate every default-branch merge after the recorded frontier", and replace "is processed by the next reconcile pass" with "is processed by the next drift-job run".

3. Append to **The drift run.** bullet: "The drift job is separate from the reconcile pass: a reconcile pass MUST NOT run the drift pass and MUST NOT invoke any model judgement. The drift job MUST run only on a schedule an operator explicitly enables; nothing MAY enable it implicitly."

In SPECIFICATION/scenarios.md:

4. Under `## Scenario 207 — The drift run processes each merge behind a contiguous frontier and files proposals it never accepts`, replace the steps "When the reconcile pass runs" with "When the drift job runs", "When the reconcile pass processes the merge again" with "When the drift job processes the merge again", and "When the next reconcile pass runs" with "When the next drift job runs".

5. Under the same heading, append one scenario to the gherkin block:

```gherkin
  Scenario: A reconcile pass runs no drift pass
    Given default-branch merges after the recorded drift frontier
    When a reconcile pass runs
    Then no drift pass runs and no model judgement is invoked
    And the drift frontier and the detection-coverage anchor are unchanged
```

6. In the detection-recency scenario "Merges past the threshold surface the drift fact while the run has not caught up", replace "the reconcile pass is what runs the drift pass" with "the drift job is what runs the drift pass".

No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` is unchanged.
