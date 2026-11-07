---
topic: workflow-declared-node-timeouts
author: claude-opus-5-5
created_at: 2026-11-07T16:08:10Z
---

## Proposal: A workflow-declared node timeout stands unless configuration names the node

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Make the workflow's declared timeout the value a node renders when neither a repository's dispatcher.node_timeouts nor a per-dispatch argument names it, keep 1800 seconds as the default only for a node that declares none, require the execution allowance and subprocess ceiling to read the same rendered values, require a commit settle node to end its own wait before its rendered timeout, and require a declared value below 1800 seconds to rest on a recorded measurement.

### Motivation

A timeout added to the workflow graph never reaches a dispatched run. §"ACP node timeouts" says "A node with no configured value MUST resolve to **1800** seconds", and the Dispatcher obeys it: `render_workflow_graph` overwrites every node's timeout attribute with the repository's named value or the 1800-second default, and never reads what the node declared. The same section's "Resolution layers" paragraph names "the workflow's own declared defaults" as the lowest layer, so the section contradicts itself; this proposal resolves that in favour of the layers.

Measured 2026-11-07. Run 01M6V85A0CM5QXY0RJFRSK8XAP (bd-ib-gusugi, build 0.300.0): its rendered graph carries timeout="1800s" on implement_commit_settle, fix_commit_settle and review_fix_commit_settle, while the shipped workflow.fabro declares 3900s on all three (bd-ib-csbito, bd-ib-mr7673). Run 01M6V7EPQRHAR7P0N0N7ERZG22 (livespec-dev-tooling-4pchid): fix_commit_settle@1 failed with "Script timed out after 1800000ms", the fix turn's rebase stayed in progress, and janitor@2 died with exit 128 on rebase-merge. That is a regression and not only a missing raise: those two items also moved the settle script's own bound from 1500 to 3600 seconds, so a settle that used to give up cleanly inside its 1800-second node is now killed by the engine before its failure handling runs.

The fix belongs in one place (legacy-coordinator-agent ruling R301, 2026-11-07, to be ratified through this proposal), because the Dispatcher is shared by every repository and one change needed in several is itself the finding. Fleet scope, read 2026-11-07 from the primary checkouts under /data/projects: livespec-orchestrator-beads-fabro, livespec-dev-tooling, homelab, livespec-console-beads-fabro, livespec-overseer and livespec-tdd-proof carry a dispatcher.node_timeouts table, and none of them names a commit settle node before the interim dials of this date. dolt-server, hetzner-xubuntu-info, livespec, livespec-driver-claude, livespec-driver-codex, livespec-driver-pi, livespec-orchestrator-git-jsonl, livespec-runtime, openbrain and resume carry no table, so any of them dispatched through this Dispatcher runs every node at the default until this lands.

The maintainer's 2026-08-26 ruling (bd-ib-cnkf) is preserved. It set a default of 1800 seconds and made timeouts configurable; 18 nodes declare exactly 1800 today, and an undeclared node keeps that default.

Honouring declared values also LOWERS nodes, which is why the measurement clause exists. The same render has raised every low-declared node to 1800 seconds since 2026-08-26, so these declarations have never been in force: fix_progress_route, janitor_failure_route, janitor_refresh_route and refresh_repair declare 60 seconds, and dod_gate_mutation_guard, implement_amendment_route, implement_completion, needs_human, pr_refresh_head, pr_refresh_merged_reconcile_route, pr_route, proof_grade, proof_grade_route, publish_merged_reconcile_route, recapture_route and review_fix_admission declare 600. Three sampled v0.297.0 and v0.300.0 runs read seven of those under 5 seconds and hold no sample for the rest; needs_human, the node that preserves a failed run's work, is among those with none. Work item bd-ib-2eyiwy therefore keeps the seven unmeasured nodes at 1800 seconds or more.

Pending proposals node-timeout-cut-retry-carries-the-cut-state and transient-infra-release-and-re-dispatch touch this section and are compatible: the first keys off the resolved timeout under either rule, and the second only cites the section. Implementation is bd-ib-2eyiwy, filed under plan bd-ib-qy5wol.

### Proposed Changes

In SPECIFICATION/contracts.md, under "## ACP node timeouts", make these changes.

(1) Replace the section's opening paragraph with:

> Every node timeout of the `implement-work-item` workflow, and the run's stall watchdog, MUST resolve through the resolution layers of this section. A timeout attribute in the workflow graph is that workflow's declared default for the node: it is the lowest layer and never overrides configuration.

(2) In "**Keys.**", replace the sentence "A node with no configured value MUST resolve to **1800** seconds; the stall watchdog with no configured value MUST resolve to **7200** seconds." with:

> A node that no repository table entry and no per-dispatch argument names MUST resolve to the timeout its workflow graph declares for it. A node that declares none MUST resolve to **1800** seconds. The stall watchdog with no configured value MUST resolve to **7200** seconds. The table MAY name any node of the graph; the names above are the ones the shipped configuration most often sets, not a closed set.

(3) Replace "**Resolution layers.**" with:

> **Resolution layers.** The same three layers and precedence as §"ACP node adapter configuration" apply: the workflow's own declared defaults, the dispatch target's `.livespec.jsonc`, then a per-dispatch `--node-timeout <node>=<seconds>` argument that MUST be journaled on the dispatch record. The record MUST name the supplying layer per node, and MUST name the workflow for a node that renders its declared value and the built-in default for a node that declares none.

(4) Replace "**The subprocess ceiling follows the graph.**" with:

> **The run's budgets follow the graph.** The Dispatcher's `fabro run` subprocess ceiling MUST be derived from the resolved node timeouts and the resolved stall timeout — the graph's worst-case path plus a fixed margin — rather than from a hard-coded constant, so that lengthening a node cannot outrun the poller and shortening one is not masked. The ceiling and the execution allowance MUST read the same per-node values the rendered graph carries, so a value that reaches the run cannot be billed at a different one.

(5) Immediately after that paragraph, add:

> **A commit settle node ends its own wait first.** The wait a commit settle node's script performs MUST end before that node's rendered timeout, by the rendered timeout less a fixed margin of 300 seconds, so the script's failure handling runs rather than the engine ending the node. The Dispatcher MUST write that bound into the rendered graph as a literal, as it writes the timeout.

(6) Replace "**The 30-minute default is a deliberate reduction.**" with:

> **The 30-minute default is a deliberate reduction.** It lowers `implement` from the previously shipped 14400 seconds and `janitor`/`fix` from 3600 seconds, against recorded legitimate turns near 120 minutes. The workflow graph therefore MUST declare no more than 1800 seconds for those nodes. A repository that needs longer turns sets them; the default is the maintainer's ruling and the reduction is recorded in the implementing item's triage record.

(7) Immediately after that paragraph, add:

> **A low declaration rests on a measurement.** A node's declared timeout below 1800 seconds MUST rest on a recorded run's measured duration for that node, named in a comment beside the declaration. A node with no such measurement MUST declare at least 1800 seconds, because a declared value that has never been in force and is too tight fails in every repository at once.

In SPECIFICATION/scenarios.md, append the scenario below, and add its `tests/heading-coverage.json` row in the same revise pass (`test` MAY be "TODO" with a non-empty reason naming bd-ib-2eyiwy). The `## ACP node timeouts` heading itself does not change.

## Scenario 323 — A workflow-declared node timeout stands unless configuration names the node

Governing clause: `contracts.md` §"ACP node timeouts" → "Keys." and "A commit settle node ends its own wait first."

```gherkin
Feature: A node timeout the workflow declares reaches the run unless configuration names that node
  As the maintainer of a repository dispatched through the factory
  I want a node's declared timeout to be the value its run renders when nothing configures it
  So that a timeout a change adds to the workflow applies on a dispatched run

  Background:
    Given a workflow graph declaring timeout "3900s" on fix_commit_settle and "600s" on pr_route
    And a workflow graph node undeclared_node carrying no timeout attribute

  Scenario: a node no configuration names renders its declared value
    Given a repository whose dispatcher.node_timeouts does not name fix_commit_settle
    When the Dispatcher renders the dispatch's workflow graph
    Then fix_commit_settle carries the literal timeout "3900s"
    And the dispatch record names the workflow as the layer supplying fix_commit_settle

  Scenario: a repository's table outranks the workflow's declared value
    Given a repository whose dispatcher.node_timeouts sets pr_route to 900
    When the Dispatcher renders the dispatch's workflow graph
    Then pr_route carries the literal timeout "900s"
    And the dispatch record names the repository as the layer supplying pr_route

  Scenario: a per-dispatch argument outranks both
    Given a repository whose dispatcher.node_timeouts sets pr_route to 900
    And a dispatch carrying --node-timeout pr_route=1200
    When the Dispatcher renders the dispatch's workflow graph
    Then pr_route carries the literal timeout "1200s"

  Scenario: a node nothing declares or names takes the default
    Given a repository whose dispatcher.node_timeouts does not name undeclared_node
    When the Dispatcher renders the dispatch's workflow graph
    Then undeclared_node carries the literal timeout "1800s"

  Scenario: the run's budgets read the values the graph carries
    Given a repository whose dispatcher.node_timeouts does not name fix_commit_settle
    When the Dispatcher derives the dispatch's execution allowance and its subprocess ceiling
    Then each bills fix_commit_settle at 3900 seconds per visit

  Scenario: a settle node below its declared timeout ends its own wait first
    Given a repository whose dispatcher.node_timeouts sets fix_commit_settle to 1800
    And a fix turn that left a commit run still running past 1500 seconds
    When fix_commit_settle runs
    Then its wait ends at 1500 seconds
    And the node runs its failure handling
    And the engine does not end the node on its timeout
```
