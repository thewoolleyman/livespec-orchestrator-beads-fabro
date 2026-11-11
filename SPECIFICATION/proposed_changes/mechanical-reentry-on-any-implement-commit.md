---
topic: mechanical-reentry-on-any-implement-commit
author: claude-opus-5-5 (sandbox-commit-gate-ceiling plan session)
created_at: 2026-11-11T18:36:21Z
spec_commitments:
  impl_followups:
    - id_hint: mechanical-reentry-single-implement-node
      description: |
        Implement the generalized mechanical re-entry budget on the single implement node: implement_hook_route takes a mechanical re-entry when every failed target is in dispatcher.implement.mechanical_targets, with the capped failing-file brief, the wall-time guard and a visit bound derived from both budgets; and declare mechanical_targets (check-lint, check-format, check-keyword-only-args, check-file-lloc, check-per-file-coverage) in this repository's .livespec.jsonc. Filed as a child of plan bd-ib-qy5wol.
---

## Proposal: A purely mechanical refusal of any implement-stage commit, including the single implement node's, re-enters on its own capped and wall-guarded budget

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Generalize contracts.md's 'A purely mechanical commit refusal has its own re-entry budget' from commit_red/commit_green to every implement-stage commit the repository hook refuses, explicitly including the single `implement` node the workflow runs today. Add three behaviours: the mechanical re-entry's handoff names the failing files with their uncovered lines or size, capped at the first 40 plus an omitted count; a mechanical re-entry is withheld when the remaining whole-run wall budget is less than the longest completed implement-stage turn; and the engine visit bound is derived from the ordinary plus the resolved mechanical re-entries. Three scenarios are appended inside Scenario 285, whose heading is unchanged.

### Motivation

The ratified mechanical re-entry budget is written only against the split red/commit_red/green/commit_green graph. That graph was reverted to a single `implement` node in v0.288.0 (067118d96), and its re-land (plan livespec-dev-tooling-sv6m5p, slices bd-ib-ohlkz7 and bd-ib-n5e5py blocked since 2026-11-08) is not close. So no factory repository has a mechanical budget today: the single node runs at max_visits=3, which is two ordinary re-entries, and its hook-refusal brief carries the failed target names plus only the last 80 lines of the hook output. Measured by token-spend-analysis over the 7 days to 2026-11-11T18:12Z: the aggregate-check blocked class (implement hook refused, re-entry budget exhausted, failing ONLY on check-per-file-coverage and/or check-file-lloc) had 18 endings in 16 items, $358.83 in ended runs plus at least $121.52 in relaunches, a $480 footprint and 2.1% of factory spend. It is rising: 6 of the 18 were on 2026-11-11, against about 2 a day before. Example: lbinx7 run 01M75PY8FA6V was blocked on check-per-file-coverage at 99.96%. Each of those endings is by definition a purely mechanical refusal, which is the case the ratified budget exists for. legacy-coordinator-agent ruled the port conformance plus a generalization (2026-11-11 about 18:2xZ), with three conditions, two of which are spec behaviour: (1) a mechanical re-entry must not convert an aggregate-blocked ending into a wall-budget cancel, the class ranked above it, so it is withheld when the remaining wall budget cannot fit one more implement turn; (2) the failing-file list is capped, because an uncapped embed caused the 2026-11-10 workflow.toml 512 KiB overflow. implement-test-performance, owner of the split-graph re-land, agreed the shape: the same config keys, not keyed per node; a visit bound derived from both budgets rather than a fixed number; the Scenario 285 heading text unchanged; the handoff's three fields and the both-budgets cause wording kept.

### Proposed Changes

1. contracts.md, under '## Self-contained plugin dispatch': REPLACE the whole paragraph that begins '**A purely mechanical commit refusal has its own re-entry budget.**' with this paragraph:

**A purely mechanical commit refusal has its own re-entry budget.** A repository MAY declare `dispatcher.implement.mechanical_targets`, a list of commit-hook target names whose failures an implement turn can repair mechanically, such as lint, formatting, keyword-only-argument, file-size and per-file-coverage targets, and `dispatcher.implement.mechanical_reentries`, a non-negative integer that defaults to 2 when the list is declared and to 0 when it is not. Both keys apply to the implement stage as a whole and are not declared per node. This paragraph governs every implement-stage commit that the repository's commit hook refuses: a refusal at `commit_red` or `commit_green`, and, while the workflow runs a single `implement` node in place of separate Red and Green nodes, a refusal of that node's commit as its hook route reads it. When every failed target name such a refusal's recorded hook output reports belongs to the declared list, the run MUST re-enter the ACP node whose change was refused (`red`, `green` or `implement`) without spending that node's ordinary re-entry, while mechanical re-entries remain for the implement stage in the run. A refusal that names any target outside the list, or whose recorded output names no failed target, MUST spend the ordinary re-entry exactly as before. The handoff that carries a mechanical re-entry, which is the commit node's handoff section in the split graph or the re-entry brief of the single `implement` node, MUST say the refusal was mechanical and MUST name the failed targets and the mechanical re-entries remaining. It MUST also name each failing file that the failed targets' recorded output reports, with the uncovered lines or measured size that output gives for it, for at most the first 40 such files in that output's order, and when the output reports more it MUST state how many further files it omitted. A mechanical re-entry MUST NOT be taken when the time remaining in the run's resolved whole-run wall budget is less than the duration of the longest implement-stage turn the run has completed. Such a refusal is then handled exactly as one whose mechanical re-entries are spent, and its handoff MUST say that the mechanical re-entry was withheld for wall time, naming the remaining time and that turn's duration. When the mechanical re-entries are spent, a further purely mechanical refusal MUST spend the ordinary re-entry, and when that is also spent the stage MUST end with a failed outcome whose cause names both the mechanical and the ordinary re-entry budgets as exhausted. The engine visit bound that the materialized workflow declares for each re-entered node MUST be derived as one visit plus that node's ordinary re-entries plus the resolved mechanical re-entries, so that neither budget is cut short by that bound and a change to `dispatcher.implement.mechanical_reentries` needs no workflow edit. Scenario 285 in `scenarios.md` exercises this paragraph.

2. scenarios.md, inside '## Scenario 285 — Red and Green run as separate nodes and every implement commit is made by a command node' (heading text UNCHANGED), append these three scenarios to the end of its first gherkin block, after 'Scenario: Spent mechanical and ordinary re-entries end the stage failed naming both budgets':

```gherkin
  Scenario: A purely mechanical refusal of the single implement node's commit re-enters implement on its mechanical budget
    Given a workflow that runs a single implement node in place of separate Red and Green nodes
    And a repository that declares check-file-lloc and check-per-file-coverage as mechanical targets
    And the implement turn's commit is refused by a hook whose recorded output names only check-file-lloc
    When the implement hook route routes the refusal
    Then the run re-enters implement with one fewer mechanical re-entry remaining
    And the implement node's ordinary re-entry is unspent
    And the re-entry brief names the refusal as mechanical, names check-file-lloc and names the mechanical re-entries remaining

  Scenario: A mechanical re-entry's handoff names the failing files, capped at forty
    Given a repository that declares check-per-file-coverage as a mechanical target
    And an implement-stage commit refused by a hook whose recorded output names only check-per-file-coverage and reports 55 files below the coverage threshold
    When the run takes a mechanical re-entry for that refusal
    Then the handoff names the first 40 of those files in the output's order, each with its uncovered lines
    And it states that 15 further files were omitted

  Scenario: A mechanical re-entry is withheld when the wall budget cannot fit another implement turn
    Given a repository that declares check-per-file-coverage as a mechanical target and mechanical re-entries remain
    And a run whose longest completed implement-stage turn took 50 minutes and whose whole-run wall budget has 30 minutes remaining
    When an implement-stage commit is refused by a hook whose recorded output names only check-per-file-coverage
    Then no mechanical re-entry is taken
    And the refusal is handled as one whose mechanical re-entries are spent
    And the handoff says the mechanical re-entry was withheld for wall time, naming the 30 minutes remaining and the 50-minute turn
```

No H2 heading is added, removed or renamed, so tests/heading-coverage.json is unchanged. The three existing mechanical scenarios of Scenario 285 stay as they are and remain true under the generalized paragraph.
