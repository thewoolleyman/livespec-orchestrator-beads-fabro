---
topic: declared-merge-gate-suite-runs-in-the-sandbox
author: claude-opus-5-5
created_at: 2026-10-25T01:19:41Z
---

## Proposal: A repository MAY declare a merge-gate suite that the in-sandbox janitor gate runs as its own command step

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The paragraph "Janitor check-suite resolution" makes the in-sandbox janitor hard gate run exactly the repository's declared `dispatcher.janitor.check_suite`. A repository can legitimately keep merge-blocking gates out of that local aggregate (a mutation gate needs a base ref the local aggregate cannot supply), so a factory run can publish a pull request it can never merge and fail later at merge-poll. This proposal adds an optional committed key, `dispatcher.janitor.merge_gate_suite`, that the in-sandbox gate runs as a separate command step after the check suite passes, with the dispatch base supplied to it and its failure routed exactly as a janitor failure is. A repository that declares nothing is unaffected.

### Motivation

Work-item bd-ib-ckocwc (feature, no owning plan; R290 triage hold 2026-10-20 and R1 bd-ib-j6uvkj batch 11 routed it here as needing a linked proposal). Measured 2026-09-12 in livespec-console-beads-fabro: its `just check` excludes check-mutants and check-fuzz under a ratified requirement whose stated reason is that a local aggregate has no base ref to diff against, while its ci-green requires both. Two consecutive dispatches (runs 01M2AA66D8M6JQQTJX4Q3HY4ZW and 01M2AX3MTQGB8H4VK04Y1ARN64) each lost a full cycle, failing only after a PR existed. A sandbox run HAS the base ref the local aggregate lacks, so the gate belongs there. And it cannot be an instruction to an agent turn: runs 01M2B3MWF9ZSRBMWNBTZTPY8Y7 (44m36s, on check-mutants) and 01M2B6BJWSP4FYA8HVZ0FZJBTC (40m18s, on a tool install) were each terminated when the long command was moved to a background task. The generalization target is the existing "Janitor check-suite resolution" paragraph, which already governs what the in-sandbox gate runs; this proposal extends it rather than adding a section.

### Proposed Changes

Three edits, landing in one revision. No `## ` heading changes in `contracts.md`; one scenario is added to `scenarios.md`, so `tests/heading-coverage.json` gains one entry for it.

**1. `contracts.md`, the paragraph that begins "**Janitor check-suite resolution.**".** Append, after its last sentence ("...and joins the ratified committed-configuration-only class."):

```
A repository MAY also declare `dispatcher.janitor.merge_gate_suite`: the
merge-blocking checks its own aggregate legitimately omits. Its value
MUST be a JSON string holding one shell command line, the form in which
the declared check suite reaches the in-sandbox gate, and it is invoked
verbatim under the same no-wrapper rule. When the key is absent, or its
value is the empty string, the factory workflow MUST behave exactly as it
does without it. A value that is JSON `null` or is not a string is an
unresolvable declaration and MUST refuse the dispatch exactly as an
unresolvable check suite refuses, naming the key. The declared check suite reaches the factory workflow as its
`sandbox_check_suite` input; the merge-gate command MUST reach it as a
separate input, `sandbox_merge_gate_suite`, resolved from this key in
the same way. When the key declares a command, the in-sandbox janitor
gate MUST run it after `sandbox_check_suite` passes, on the same tree, as a separate command within the janitor
stage and under that stage's resolved timeout; it MUST NOT be delegated
to an agent turn, and an agent stage prompt MUST NOT direct a turn to run
it. Before running it, the gate MUST resolve `origin/<default branch>` in
the run's clone and supply it to the command as the environment variable
`LIVESPEC_MERGE_GATE_BASE`; when that ref cannot be resolved, the janitor
gate MUST fail with a named cause rather than run the command without a
base. A non-zero exit of the merge-gate command MUST fail the janitor
gate with the command's output in the stage log and MUST take exactly the
route a failing check suite takes, so the run fails inside its own janitor
stage rather than at merge-poll after a pull request exists. The
obligation of "A fix turn runs the check suite once per tree" covers
`sandbox_check_suite` only and does NOT extend to the merge-gate command,
because the janitor visit that follows a successful `fix` turn runs both.
When `pr_refresh` runs the repository-declared gate on a refreshed head,
that gate MUST consist of `sandbox_check_suite` followed, when it
passes, by `sandbox_merge_gate_suite`, with `LIVESPEC_MERGE_GATE_BASE`
naming the default-branch commit that `pr_refresh` just fetched and
refreshed the head onto, and a failure
of either is a refreshed head the repository-declared gate rejects, which
takes the existing refresh-repair route. The post-merge host janitor MUST
NOT run the merge-gate command, because the merge it follows was already
gated. `dispatcher.janitor.merge_gate_suite` joins the
committed-configuration-only class with the rest of `dispatcher.janitor`.
```

**2. `contracts.md`, the paragraph that begins "**Scripted publication and proof-head integrity.**".** In its sentence "When the default branch has advanced beyond the current base, `pr_refresh` MUST rebase, run the existing repository-declared `sandbox_check_suite` as a foreground command with its own timeout, and push only after that gate passes.", replace "run the existing repository-declared `sandbox_check_suite` as a foreground command with its own timeout, and push only after that gate passes" with:

```
run the existing repository-declared `sandbox_check_suite` and then,
when the repository declares one, `sandbox_merge_gate_suite` (with
`LIVESPEC_MERGE_GATE_BASE` naming the default-branch commit it just
refreshed onto), each as a foreground command with its own timeout, and
push only after both pass; a failure of either is a refreshed head the
repository-declared gate rejects
```

**3. `scenarios.md`.** Add one scenario after the highest-numbered scenario, numbered by the revise pass:

```gherkin
Feature: A declared merge-gate suite runs inside the factory run
  Scenario: A changeset that fails a declared merge-gate check fails in the janitor stage
    Given a repository that declares a merge_gate_suite running its mutation check against LIVESPEC_MERGE_GATE_BASE
    And a work item whose change passes the declared check suite but leaves a surviving mutant
    When the factory runs the item
    Then the janitor stage fails with the mutation check's output in its stage log
    And the run routes to fix as it does for a failing check suite
    And no pull request is opened for a head that failed the merge-gate suite

  Scenario: A repository that declares no merge-gate suite is unchanged
    Given a repository that does not declare merge_gate_suite
    When the factory runs a work item
    Then the janitor stage runs only the declared check suite, exactly as before

  Scenario: A refreshed head that fails the merge-gate suite takes the refresh-repair route
    Given a repository that declares a merge_gate_suite and a run whose default branch moved before publication
    When pr_refresh rebases and the refreshed head passes the check suite but fails the merge-gate command
    Then pr_refresh pushes nothing and takes the refresh-repair route with the merge-gate output

  Scenario: A missing base fails the gate with a named cause
    Given a repository that declares a merge_gate_suite and a run whose clone cannot resolve origin of its default branch
    When the janitor gate reaches the merge-gate command
    Then the janitor gate fails naming the unresolved base and the command is not run

  Scenario: The merge-gate suite is a command step, not an agent instruction
    Given a repository that declares a merge_gate_suite
    When the implement, fix and review_fix prompts of the run are read
    Then none of them directs the turn to run the merge-gate suite
```
