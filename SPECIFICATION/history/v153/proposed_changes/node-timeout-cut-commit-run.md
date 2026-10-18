---
topic: node-timeout-cut-commit-run
author: claude-opus-5-5
created_at: 2026-10-18T01:46:08Z
---

## Proposal: A turn cut by its node timeout leaves its commit run to finish or be named, and a hook still executing at the cut is a hook-over-limit event

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

Extend contracts.md "Repository hooks that outlive a limit" to a third limit, an ACP agent node's resolved node timeout ending its turn while an in-turn git commit or push hook is executing. Add a paragraph stating that a turn ended by its node timeout does not terminate a commit run it started through the commit runner, that needs_human waits on it with bounded waits and stops it before the preservation commit, that a passed commit run is in the preserved history, and that the needs-human cause names node-timeout, the node, its resolved timeout and each commit run's identity and state. The orderly end-of-turn rule is unchanged. Add Scenario 192.

### Motivation

Work item bd-ib-ptnxyg (admitted by driver ruling R132 of gitops-fleet-capacity-monitoring as an R34-class root-cause fix). The fix node's resolved timeout (dispatcher.node_timeouts.fix = 3600) cut two fix stages on hp on 2026-10-16 while each was inside a long hook-driven commit or rebase repair (bd-ib-sufca7 run 01M51FDQ0NP67QMM3VR1VXHR37 and bd-ib-jgedjo run 01M51FY06J35), and again on 2026-10-18 (qg6qkz resume 01M563W6CWYQ, fix@2). Each cut reported only the engine's generic ACP turn timeout. Run 01M56ADHDA7R's dod_gate (2026-10-18T01:40Z) refused bd-ib-ptnxyg because no ratified text governs a turn the node timeout cuts: contracts "A commit leg completes past one tool call" governs only an orderly final message, and "Repository hooks that outlive a limit" enumerates only the per-tool-call limit and a command node's timeout. Its remedy was to ratify the stage-level case as a new scenario with its clause under ACP node timeouts and to extend the hook-over-limit limits. Raising the timeout instead is bounded by tests/test_factory_checkpoint_declaration.py's freshness bound, measured on bd-ib-ptnxyg (3600 is at the ceiling).

### Proposed Changes

In SPECIFICATION/contracts.md, section "## ACP node timeouts", replace the opening of the paragraph "**Repository hooks that outlive a limit.**" (from its first word through "A `hook-over-limit`\nevent is a git commit or push ended by one of those two limits while a hook run") with:

**Repository hooks that outlive a limit.** A governed repository's commit and
push hooks run inside the factory sandbox under one of three limits: the agent's
per-tool-call limit, when an ACP agent runs `git commit` or `git push` inside
its own turn; the resolved node timeout of that ACP agent node, when it ends the
agent's turn while such a `git commit` or `git push` is still executing; or the
resolved timeout of a command node that commits or pushes, such as
`publish_draft` or `pr_refresh`. When an agent tool call that runs a git commit
or push is ended by the agent's per-tool-call limit or by its node's resolved
timeout while the hook run it started is still executing, every process of that
hook run MUST be terminated before the next git commit or push in the same
sandbox starts, so that two hook runs never execute concurrently in one sandbox.
A `hook-over-limit` event is a git commit or push ended by one of those three
limits while a hook run

The rest of that paragraph is unchanged.

Immediately after the paragraph "**A commit leg completes past one tool call.**" and before "**The run's working tree survives the agent.**", insert this paragraph:

**A commit run outlives a node-timeout cut.** The preceding paragraph's end-of-turn rule governs a turn that ends with the agent's final message, and that rule is unchanged. A turn that its node's resolved timeout ends is a separate case, because the agent sends no final message and cannot stop what it started. When an `implement`, `fix` or `review_fix` turn is ended by its node's resolved timeout while a commit run it started through the commit runner is still `running`, ending the turn MUST NOT terminate that commit run. Before the `needs_human` node makes its preservation commit, it MUST wait on every commit run still `running` in the sandbox with bounded waits, ending that wait early enough to preserve and push the tree within the `needs_human` node's own timeout, and MUST then stop any commit run still `running`, so that no commit run executes concurrently with the preservation commit; a commit run stopped this way is `no-verdict`. A commit run that reached `passed` before preservation began MUST be in the preserved tree's history. When such a cut is the cause of the run's needs-human ending, the needs-human cause recorded on the item MUST name `node-timeout`, the node whose turn was cut, that node's resolved timeout in seconds, and, for each commit run the cut turn had started, its identity and its terminal state when preservation began. Scenario 192 in `scenarios.md` exercises this paragraph.

In SPECIFICATION/scenarios.md, after Scenario 189 (Scenarios 190 and 191 are reserved by the pending proposal janitor-check-suite-venue), append:

## Scenario 192 — A turn cut by its node timeout leaves its commit run to finish or be named, and a hook still executing at the cut is a hook-over-limit event

```gherkin
Feature: A node-timeout cut neither discards a commit under way nor hides its cause
  As an operator recovering a needs-human run
  I want a commit run interrupted by a node timeout to finish or be named, and the cut to name its limit
  So that a proved repair is preserved and the stop is not presented as an agent's decision

  Scenario: A commit run that passes after the cut is preserved and named
    Given a fix turn that started a commit run through the commit runner
    And the fix node's resolved timeout ends the turn while that commit run is running
    When the commit run reaches passed before the needs_human node begins preservation
    Then the preserved tree's history contains the commit run's resulting commit
    And the item's needs-human cause names node-timeout, the fix node, its resolved timeout in seconds, and the commit run's identity with state passed

  Scenario: A commit run still running when the bounded wait ends is stopped before preservation
    Given a fix turn ended by its node's resolved timeout while a commit run it started is running
    When the needs_human node's bounded wait ends with that commit run still running
    Then the commit run is stopped before the preservation commit starts
    And the item's needs-human cause names the commit run with state no-verdict

  Scenario: An in-turn commit whose hook is still executing at the cut is a hook-over-limit event
    Given a fix turn that runs git commit inside its own tool call rather than through the commit runner
    And the fix node's resolved timeout ends the turn while that commit's hook run is executing
    When the run records the event
    Then the dispatch journal has a hook-over-limit row naming the fix node, the git commit operation and the node's resolved timeout in seconds
    And every process of that hook run is terminated before the next git commit or push in the sandbox starts
```

The revise pass that accepts this proposal MUST add a tests/heading-coverage.json entry for the Scenario 192 heading in the same change, with test "TODO" and a reason stating that an integration-tier test is owed and that work-item bd-ib-ptnxyg implements it and owns that binding, plus the matching tests/heading-coverage-debt.json row.
