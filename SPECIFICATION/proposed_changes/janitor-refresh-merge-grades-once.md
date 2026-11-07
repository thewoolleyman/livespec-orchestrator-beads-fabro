---
topic: janitor-refresh-merge-grades-once
author: claude-opus-5-5
created_at: 2026-11-07T23:20:38Z
---

## Proposal: A janitor refresh merge grades the merged tree once

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

When the janitor's pre-aggregate refresh makes a merge commit, the janitor creates the merge without committing and commits it through the repository's commit hooks. A passing full check aggregate in that commit's pre-commit hook, on exactly the merged tree, is the janitor visit's grading of that tree, so the janitor does not run the aggregate on it a second time. Commit-time verification is kept, and it runs once.

### Motivation

Work item bd-ib-yqjaut, plan sandbox-commit-gate-ceiling, filed on legacy-coordinator-agent's R301 ruling of 2026-11-07. Measured on bd-ib-hap62u run 01M6VBZF4371P4VHY6FBTW0T9D. janitor@1 (no merge) took 2535 s and janitor@2 (refresh already up to date) took 3800 s. janitor@3's refresh made a real merge commit, and git merge fires no pre-commit hook, so only the commit-msg red_green_replay hook ran. Its suite-green leg ran the full suite in 1611.80 s. The janitor's own full aggregate then started with about 2728 s left, and the visit was cut at its 4340 s node ceiling, losing a $20.76 run whose work was done. The same merge visit pays the suite twice even at 2026-11-06's suite times. livespec-dev-tooling's ratified suite-green leg already has the conforming mechanism, its "Same-tree reuse" bullet: when the same commit's pre-commit hook has just run the FULL check aggregate to a pass on exactly the tree being committed, the leg records its trailers from that run and starts no second suite. A plain git merge never gives that bullet a pre-commit run to reuse. This repository's janitor paragraph says the aggregate runs once, in full, on the tree that is pushed, but says nothing about the merge commit's hooks.

### Proposed Changes

In SPECIFICATION/contracts.md, in the paragraph titled "**The run refreshes before the janitor, and publish_draft pushes the janitor-passed head.**", insert after the sentence "A refresh that applies cleanly onto an unchanged tip is a no-op, and the janitor then runs exactly as before.":

"When the refresh integrates the default branch's tip by a merge commit, the janitor MUST create the merge without committing it and MUST then commit it through the repository's commit hooks; it MUST NOT bypass a hook. When that commit's pre-commit hook ran the repository's full check aggregate, the same aggregate `sandbox_check_suite` names, to a passing result on exactly the merged tree the commit records, that hook run IS the janitor visit's full check aggregate for that tree: the janitor MUST record its green verdict for that tree as it records its own, and MUST NOT run the aggregate on that tree a second time in the same visit. A merge-gate command that `dispatcher.janitor.merge_gate_suite` declares MUST still run after that verdict, on the same tree, exactly as it runs after a passing `sandbox_check_suite`. When the hook ran only part of the aggregate, or the janitor cannot establish that the hook's run judged exactly the committed tree, the janitor MUST run its own full aggregate on the merged head exactly as before. When the hook's aggregate fails, the merge is not committed, and the janitor MUST take the route an aggregate failure on a changed refreshed head takes: it restores the pre-refresh head and records a refresh-repair brief naming each failed target. The commit-msg replay gate's suite-green leg on that merge commit is governed by livespec-dev-tooling's contract, whose Same-tree reuse bullet reuses the pre-commit aggregate run instead of starting a second suite; this paragraph does not change that leg. Measured 2026-11-07 on bd-ib-hap62u run 01M6VBZF4371: a refresh merge made by a plain merge ran no pre-commit hook, its commit-msg suite-green leg ran the full suite in 1611.80 s, and the janitor's own aggregate then outran the 4340 s janitor ceiling."

In SPECIFICATION/scenarios.md, in Scenario 305 (heading unchanged), append:

```gherkin
  Scenario: A refresh merge commit's passing hook aggregate is the janitor's grading of the merged tree
    Given the janitor's pre-aggregate refresh integrates the default branch's tip by a merge commit
    When the janitor creates the merge without committing and commits it through the repository's commit hooks
    And the commit's pre-commit hook runs the full check aggregate to a pass on exactly the merged tree
    Then the janitor records the green verdict for that tree
    And the janitor does not run the full check aggregate on that tree a second time in the same visit

  Scenario: A partial hook run on a refresh merge leaves the janitor's own aggregate in place
    Given the janitor's refresh merge commit whose pre-commit hook ran only part of the full check aggregate
    When the janitor continues the visit
    Then the janitor runs its own full check aggregate on the merged head

  Scenario: A failing hook aggregate on a refresh merge takes the refresh-repair route
    Given the janitor's refresh merge whose pre-commit hook's full check aggregate fails
    When the janitor continues the visit
    Then the merge is not committed
    And the janitor restores the pre-refresh head and records a refresh-repair brief naming each failed target
```

No H2 heading changes, so `tests/heading-coverage.json` needs no edit. The implementing work item bd-ib-yqjaut MUST NOT be released before livespec-dev-tooling-z5fwwn ships the Same-tree reuse bullet, because until then the suite-green leg still starts its own full suite on the merge commit.
