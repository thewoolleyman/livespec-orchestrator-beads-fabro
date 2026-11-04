---
topic: dispatch-pre-launch-steps-are-attributed-concurrent-and-once-per
author: claude-opus-5-5
created_at: 2026-11-03T19:46:55Z
---

## Proposal: Attribute, parallelize and de-duplicate the dispatch pre-launch chain

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Add `## Dispatch pre-launch step attribution and concurrency` to contracts.md. Every pre-launch step journals its start and end, with no unattributed gap over five seconds. Independent steps run concurrently, keeping the ordering the contract already requires. Facts that are the same for every item in one loop pass are computed once per pass. The source-checkout preflight tests the default branch's ref first instead of spawning one git process per remote ref.

### Motivation

Measured 2026-11-03 by claude:fabro-currency and recorded on bd-ib-bpkqan. The 7 to 14 minutes between a launcher's LAUNCH and the run's creation are spent on the dispatching host, not on the factory: petri creates each run within 215 to 380 ms of the POST. For bd-ib-3i3j3k, LAUNCH was at 19:09:38Z, the first item-scoped journal record at 19:15:41Z (about 5.5 minutes unattributed), and the run was created at 19:22:48Z. The steps ran one after another at 10 to 90 s each while the host sat at load 80 to 108. source_checkout_preflight alone walks 922 origin refs alphabetically with `git merge-base --is-ancestor`, and origin/master is ref 476, so it spawns about 475 git processes. This latency has bound fleet throughput all day (legacy-coordinator-agent, priority 7). The only ratified clause on pre-launch work, "Pre-launch reads" under "Bounded Fabro event reads", bounds journal and inspect reads per dispatch pass. No clause states attribution, concurrency or once-per-loop-pass facts, so bd-ib-bpkqan's Definition of Done had no governing heading to reference.

### Proposed Changes

One edit to `SPECIFICATION/contracts.md`: insert a new H2 section immediately before `## Dispatcher successful terminal evidence` (that is, at the end of `## Dispatcher admission, WIP cap, and post-merge acceptance`). No existing sentence changes. The section reads, in full:

````markdown
## Dispatch pre-launch step attribution and concurrency

A dispatch's pre-launch chain is every step one Dispatcher process runs for a work-item from the moment the process starts until it submits `fabro run` for that item, or until it refuses, defers or abandons the dispatch without submitting. It includes admission, the Definition-of-Done judgement, the ACP checks, the dispatch-claim stamp, recovery routing and the source-checkout preflight. Time spent in this chain is time a launched dispatch holds a launch slot while no run exists on any factory, so the chain MUST be fully attributed, MUST NOT serialize work that does not need to be serialized, and MUST NOT recompute a fact that cannot change within one loop pass.

**Attribution.** For every pre-launch step it runs, the Dispatcher MUST journal one record when the step starts and one when it ends. Each record names the step, the work-item (or, for a step that serves a whole loop pass, the pass), the instant, and on the end record the elapsed seconds and the step's outcome. Process start-up, configuration and ledger reads that precede the first item-scoped step are steps under this rule and are journaled the same way. Between the Dispatcher process's start and its `fabro run` submission for an item, no interval longer than five seconds MAY go uncovered by a journaled step.

**Concurrency.** Pre-launch steps whose inputs do not depend on another pre-launch step's result MUST be started without waiting for one another, and the dispatch MUST NOT wait on a step whose result it does not need. Every ordering between two steps that another section of this contract requires is unchanged, and nothing is submitted to a factory before every step whose refusal would withhold the dispatch has completed. A step that fails or refuses MUST still journal its end record, and the dispatch MUST apply that step's existing refusal rule exactly as it would had the steps run one after another.

**Once per loop pass.** A loop pass is one iteration of `dispatcher.py loop` over the items it selects; a single-item dispatch is a loop pass of one item. A fact whose answer is the same for every item one loop pass dispatches MUST be computed at most once in that loop pass and reused by every dispatch in it. Such facts include the default branch's master-CI state, the sandbox container sweep, the GitHub App reach probe and the ACP session-headroom baseline. A per-pass fact MUST NOT be carried into the next loop pass. This rule does not relax §"Bounded Fabro event reads" → "Pre-launch reads": the dispatch journal and each run's `fabro inspect` are still read at most once per dispatch pass, and a dispatch pass still makes its own first read of each.

**Source-checkout ancestry.** When the source-checkout preflight looks for a remote-tracking ref that contains the dispatch's head, it MUST test the default branch's remote-tracking ref first, and it MUST NOT start one process per remote-tracking ref to answer the question.
````

The new H2 needs a `tests/heading-coverage.json` entry in the revise commit, owned by bd-ib-bpkqan.
