---
topic: pr-refresh-s-post-rebase
author: claude-opus-5-5
created_at: 2026-11-14T03:40:08Z
---

## Proposal: pr_refresh's post-rebase gate runs within a deadline below its node timeout, and an expired gate takes refresh repair with a brief instead of ending at needs_human

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

After a rebase onto an advanced default branch, pr_refresh runs sandbox_check_suite and then sandbox_merge_gate_suite, each as a foreground command with its own timeout. Nothing bounds the two together below the pr_refresh node timeout. On a loaded host the gate can therefore outrun the node limit, and the engine kills the stage with no gate outcome, no output and no brief. refresh_repair then prints LIVESPEC_REFRESH_REPAIR_ABSENT and a green run ends at needs_human. This proposal adds a gate deadline that leaves a fixed reserve before the node timeout, and requires the gate's output to stream into the stage output as it is produced. A gate the deadline cuts off becomes a refreshed head the gate rejected. The stage restores the pre-refresh head and records a refresh-repair brief naming the expired deadline and the gate's last completed target. The run then takes the existing refresh-repair route, so the janitor's full aggregate, under its own larger limit, grades the repaired head.

### Motivation

Work item bd-ib-hap62u, a child of plan publish-draft-green-work-loss (epic bd-ib-acrr56). It is the pr_refresh counterpart of that plan's publish-stage time-limit losses, and no plan assertion's carrier map names it. The Dispatcher held it at the spec-change tier on 2026-11-14T03:34:27Z: verdict partial against spec v373, linked topic pr-refresh-s-post-rebase, generalization target ## Self-contained plugin dispatch, whose pr_refresh paragraph this proposal edits. The tier judgement's rationale reads: the ratified text says pr_refresh runs the declared check suite and merge gate as foreground commands, each with its own timeout, and that a gate-rejected refreshed head takes the refresh-repair route to fix. It does not say that the gate budget sits below the pr_refresh node timeout, or that an expired budget makes the stage name the last completed target and the expired budget in its output and brief. MEASURED 2026-11-04 on livespec-dev-tooling-243dzr run 01M6K1MAX0A19AKS0YH2NPEHMJ (petri): pr_refresh@1 rebased cleanly (b97f118e..0d76fe79). Its check suite then ran with output buffered until completion and hit the node's timeout="1800s" (wall 1,800,129 ms; failure_reason "Script timed out after 1800000ms"). With no output and no brief, refresh_repair@2 printed LIVESPEC_REFRESH_REPAIR_ABSENT and the run ended at needs_human, although the item's PR #3386 was green with a clean merge-tree. PR #4639 (bd-ib-qy5wol) raised this repository's dispatcher.node_timeouts.pr_refresh to 5400 s. That is a per-repository mitigation of the measured instance, not a rule: any repository whose gate outgrows its pr_refresh limit still loses a green run the same way. The work item's third Definition-of-Done bullet (a pr_refresh visit whose refreshed tree is byte-identical to a tree a green janitor verdict covers carries that verdict to its push) is already ratified by constraints.md §"Pre-push gate refinements" ("A green aggregate on the exact tree carries to its push") and Scenarios 253 and 305, so this proposal does not restate it. DESIGN CHOICES: (1) The deadline is measured from the visit's start, not from the gate's first command, so a slow rebase cannot push the gate past the node limit. (2) The reserve is the smaller of 600 seconds and one quarter of the node timeout. That covers terminating the gate, restoring the pre-refresh head, writing the brief and, for a passing gate, the leased push, whose pre-push hook carries the green verdict and does not re-run the aggregate. (3) An expired gate routes to refresh repair rather than re-running the gate. A second gate in the same visit would face the same deadline. The janitor that follows a refresh-repair round runs the full aggregate under its own node limit, which is the grading the push needs. (4) An expired gate counts as a counted refresh and as a refresh-repair round, so the existing three-refresh bound and "Refresh-repair accounting" bound it with no new budget. In-flight alignment: default-align. On 2026-11-14 this session surveyed 28 spec/* branches and 26 open spec-touching pull requests. None changes pr_refresh's gate or the refresh-repair brief. The pending proposals that mention pr_refresh (a-needs-human-cause-comment, a-proof-captured-before-the, a-commit-time-check-refuses, groom-reserved-nodes-guarded-entry) concern visit-indexed reading, proof currency, routing-directive shape and groom variants, and are compatible.

### Proposed Changes

**1. `contracts.md` §"Self-contained plugin dispatch", the pr_refresh refresh paragraph.** Immediately after the sentence that ends "push only after both pass; a failure of either is a refreshed head the repository-declared gate rejects.", insert:

> **The refresh gate runs within a deadline below the node timeout.** The `pr_refresh` visit's *gate deadline* is the instant the visit started plus its resolved node timeout (§"ACP node timeouts", `dispatcher.node_timeouts.pr_refresh`) minus a *reserve*. The reserve is the smaller of 600 seconds and one quarter of that resolved node timeout. `pr_refresh` MUST run `sandbox_check_suite` and, when declared, `sandbox_merge_gate_suite` so that neither runs past the gate deadline. Each command's own timeout still applies, and whichever bound comes first governs. `pr_refresh` MUST write each gate command's output to the stage's own output as the command produces it. It MUST NOT hold that output back until the command ends, so a gate that is cut off still leaves its output on record. When the gate deadline arrives while a gate command is running, `pr_refresh` MUST terminate that command and every process it started. It MUST NOT start a further gate command, and MUST treat the refreshed head as a refreshed head the repository-declared gate rejects, for the *gate-deadline-expired* cause. `pr_refresh` MUST then take "Refresh repair" below: it restores the pre-refresh head and records a refresh-repair brief that, in place of the failed gate targets, names all of the following:
>
> - the cause `gate-deadline-expired`;
> - the gate deadline as a UTC instant, the resolved node timeout and the reserve, in seconds;
> - the gate command that was running when the deadline arrived (`sandbox_check_suite` or `sandbox_merge_gate_suite`) and the seconds it had run;
> - the gate's last completed target, which is the last target whose completion the gate's streamed output reports, or the statement that the output reports no completed target;
> - the last 80 lines of the gate's output.
>
> The stage's own output MUST carry the same cause, deadline, running command and last completed target before the stage ends. A gate that ended through the deadline MUST NOT end the run at `needs_human` with `LIVESPEC_REFRESH_REPAIR_ABSENT`. A gate-deadline-expired refresh is a counted refresh for the three-refresh bound below. Its repair round is a refresh-repair round for "Refresh-repair accounting", with no separate budget. The `fix` turn entered on such a brief integrates the default branch into the run's work exactly as for any refresh-repair brief. Under "A fix turn grades each tree once, through its commit hook", it MUST NOT run the full check aggregate beyond what its commit hook runs, because the `janitor` visit that follows runs that aggregate under its own node timeout. When the visit cannot read its own start instant or its resolved node timeout, `pr_refresh` MUST fail closed before it rebases, naming the value it could not read. It MUST NOT run the gate without a deadline. This paragraph does not change a gate that reaches a verdict before the deadline, the leased push, or any other stage. Scenario NNN in `scenarios.md` exercises this paragraph.

**2. `contracts.md` §"Self-contained plugin dispatch", the "Refresh repair" paragraph.** In the sentence that lists what the brief MUST name, after "or each failed gate target," insert "or, for a `pr_refresh` gate that ended through its gate deadline, the fields the refresh-gate deadline paragraph above lists,". In the sentence beginning "only a conflict, a commit-hook refusal of the refresh's own commit, or a gate rejection takes this route", the gate-deadline-expired cause MUST be read as a gate rejection. Add after that sentence: "A `pr_refresh` gate that ended through its gate deadline is a gate rejection for this paragraph."

**3. New scenario (`scenarios.md`, appended at the next free Scenario number when revised; the revise pass replaces NNN in both places):**

```gherkin
## Scenario NNN — pr_refresh's gate that outruns its deadline below the node timeout takes refresh repair with a brief instead of ending at needs-human

Feature: A slow refresh gate never loses a green run at needs-human
  As an operator whose repository's gate can outgrow the pr_refresh node limit on a loaded host
  I want pr_refresh to cut its gate off before the node limit and hand the run to refresh repair
  So that a green run is repaired and published instead of ending at needs_human with no brief

  Scenario: A gate still running at the gate deadline takes refresh repair with a named brief
    Given a run whose pr_refresh node timeout resolves to 1800 seconds
    And pr_refresh rebased the run cleanly onto an advanced default branch
    And sandbox_check_suite has reported completing target T and is still running when the visit reaches 1350 seconds
    When the gate deadline arrives
    Then pr_refresh terminates sandbox_check_suite and every process it started, and starts no further gate command
    And pr_refresh restores the pre-refresh head
    And the refresh-repair brief names gate-deadline-expired, the deadline, the 1800-second node timeout, the 450-second reserve, sandbox_check_suite, target T and the last 80 lines of the gate output
    And the stage output names the same cause, deadline, running command and target T
    And the run routes to fix, not to needs_human with LIVESPEC_REFRESH_REPAIR_ABSENT

  Scenario: The reserve is capped at 600 seconds
    Given a run whose pr_refresh node timeout resolves to 5400 seconds
    When pr_refresh computes its gate deadline
    Then the deadline is the visit's start plus 4800 seconds

  Scenario: Gate output reaches the stage output while the gate runs
    Given a pr_refresh gate command that prints a line naming a completed target
    When the command is still running
    Then that line is already in the stage's output

  Scenario: A gate that passes before the deadline publishes as before
    Given pr_refresh rebased the run cleanly onto an advanced default branch
    And both gate commands pass before the gate deadline
    When pr_refresh continues
    Then it pushes the refreshed head under its explicit lease exactly as before

  Scenario: An expired gate counts toward the refresh bounds
    Given a run that has already made two counted refreshes
    When a third pr_refresh gate ends through its gate deadline
    Then that refresh is the run's third counted refresh
    And the run is bounded by the existing non-convergence and refresh-repair accounting rules

  Scenario: An unreadable deadline input fails closed before the rebase
    Given a pr_refresh visit that cannot read its resolved node timeout
    When pr_refresh begins its refresh
    Then it fails closed before rebasing, naming the node timeout as the value it could not read
```

**4. Heading coverage.** The revise pass that adds the scenario MUST add its `## Scenario NNN` heading to `tests/heading-coverage.json` in the same change. Because this proposal adds no `## ` heading to `contracts.md`, that file's heading set is unchanged.
