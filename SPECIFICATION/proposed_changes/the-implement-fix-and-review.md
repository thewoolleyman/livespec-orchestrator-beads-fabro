---
topic: the-implement-fix-and-review
author: claude-opus-5-5
created_at: 2026-11-12T11:25:24Z
---

## Proposal: An agent turn closes each Red before it opens another and never rewrites below HEAD

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The implement, fix and review_fix prompts MUST direct the agent to complete an open Red commit's Green amend before it authors another Red commit, and MUST direct it never to start `git rebase -i`, or any other rebase that rewrites a commit below HEAD, during its turn. This is the prompt-side prevention for a rebase left open across a turn end, which the engine's per-stage checkpoint then breaks.

### Motivation

No ratified clause governs these prompt contents (the filing-stage spec-change-tier record on bd-ib-mx2h62). Measured 2026-11-12 over the 5 instances in bd-ib-ebwpxw's 72 h census: in all 5, the turn ended with a rebase of the run branch open, the engine then wrote 2-3 new checkpoint commits to that ref, and the settle's `git rebase --continue` failed. In 2 of the 5 (5lhafp in implement, xtofr3 in fix) the open rebase was the agent's own `git rebase -i` edit of a non-HEAD Red, after it had authored a second Red above the first. This rule prevents those 2. The other 3 were refresh rebases onto master, which only the engine-side prevention bd-ib-rhv4lo (a Fabro fork change awaiting the maintainer) reaches. legacy-coordinator-agent (session 245a3c34) ruled at about 11:25Z on 2026-11-12 that this interim be filed. Work item bd-ib-mx2h62. Related in-flight proposals a-commit-settle-node-whose (#5035) and a-commit-settle-abort-preserves-the-in-progress-resolution govern the settle node's handling of the symptom, not these prompts, so they do not overlap.

### Proposed Changes

Two edits. No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.

**Edit 1 — `SPECIFICATION/contracts.md`.** Insert this paragraph immediately AFTER the paragraph that begins **A fix turn grades each tree once, through its commit hook.** and BEFORE the paragraph that begins **An implement, fix or review_fix turn's commits run the affected-tests gate.**:

> **An agent turn closes each Red before it opens another and never rewrites below HEAD.** This paragraph governs the `implement`, `fix` and `review_fix` turns of the implement-work-item workflow. Each of those three prompts MUST direct the agent to complete an open Red commit's Green amend before it authors another Red commit, so that the Red being amended is always the run branch's HEAD or sits only below engine checkpoint commits that the sandbox commit runner folds. Each MUST also direct the agent never to start `git rebase -i`, nor any other rebase that rewrites a commit below HEAD, during its turn, because a turn can end while the hook of a commit made inside that rebase is still running, leaving the rebase open across the turn end. A refresh or repair that the brief directs the turn to integrate by rebase onto the default branch is outside this rule, because it rewrites no commit the turn authored below HEAD for a Green amend. Measured 2026-11-12: on livespec-dev-tooling-5lhafp run 01M770EZV522AZ4R2A7R29VCHH (implement) and livespec-dev-tooling-xtofr3 run 01M73RDP7C30CD8379HYPBJQ9Q (fix), the agent edited a non-HEAD Red through `git rebase -i`, the turn ended with that rebase open, engine checkpoint commits then moved the run branch, and the commit settle node's `git rebase --continue` did not complete. The runs ended wall-cancelled at 363 minutes and blocked at 143 minutes. Scenario 199 in `scenarios.md` exercises this paragraph.

**Edit 2 — `SPECIFICATION/scenarios.md`, §"Scenario 199 — A fix turn grades each tree once, through its commit hook".** Append these scenarios to the end of that scenario's Gherkin block, inside the same fenced block, after the scenario "An open Red at the stage's visit limit ends at needs_human naming it". The scenario's heading is unchanged.

```gherkin
  Scenario: Each agent prompt closes an open Red before another Red is authored
    Given the rendered implement, fix and review_fix prompts of the implement-work-item workflow
    When an agent reads any one of them
    Then the prompt directs it to complete an open Red commit's Green amend before it authors another Red commit

  Scenario: Each agent prompt forbids a rebase that rewrites a commit below HEAD
    Given the rendered implement, fix and review_fix prompts of the implement-work-item workflow
    When an agent reads any one of them
    Then the prompt directs it never to start git rebase -i, nor any other rebase that rewrites a commit below HEAD, during its turn
```

After ratification, bd-ib-mx2h62's `References:` line is repointed from Scenario 179 to Scenario 199.
