---
topic: factory-run-work-preserved-on-progress
author: claude-opus-5-5
created_at: 2026-11-05T06:35:38Z
---

## Proposal: Every node visit that moves a run's branch tip is preserved to a work-in-progress ref

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a paragraph to contracts.md §"Dispatcher admission, WIP cap, and post-merge acceptance" requiring that, after every node visit of the implement-work-item workflow whose engine checkpoint moved the tip of the run branch `fabro/run/<run-id>`, and before the next agent turn starts, the run puts that tip on origin under `refs/livespec/wip/<work-item-id>/`. The push never moves a ref to a commit that does not descend from it: it fast-forwards the work-in-progress ref the tip descends from, or writes a new SHA-suffixed sibling ref when the run branch was rewritten. It pushes the run branch's tip, never a detached workspace HEAD. The step is a command step (or workflow run hook) that changes nothing locally, runs with repository hooks disabled, uses Dispatcher-materialized tooling outside the working tree, and never fails the run. The Dispatcher's receipt records ancestry, not only presence. Amend the credential-confinement clause so this preservation step, like the needs-human preservation step, keeps a push credential limited to its own refs. Add Scenario 314.

### Motivation

Maintainer ruling of 2026-11-05 on plan factory-run-work-preservation (epic bd-ib-nckst7), verbatim: "I like this direction. It prioritizes simplicity. And I am fine accepting the loss of a single node if the entire server crashes or the run is cancelled." Measured losses: bd-ib-yuwftp run 01M6KBH30NJA lost about six hours of committed work at its wall-budget cancel and a later fabro rm -f; bd-ib-ac5lgi run 01M6KNR090B2 lost janitor checkpoint 30fdbeca at a stall-watchdog cancel; bd-ib-uq2ocd run 01M6JSNVH32S8CDNX0P4TS7DWB lost a janitor-green commit at a restart cancel. Today only the needs-human ending and the Scenario 183/306 publications put a run's tree on origin, and only at the run's end, so every ending that has no live driver (a server crash, an operator fabro rm, a cancel outside the Dispatcher) loses the whole run. The engine's own run_branch push was rejected because its refspec is never forced, so any rewrite of the run branch (an amend, a rebase) makes every later push non-fast-forward and preservation stalls silently. Forcing the update instead is also wrong, measured 2026-11-05 06:20Z (relayed by legacy-coordinator-agent): an interim preserve pass for bd-ib-rhivsm run 01M6MHQE92Q4 force-pushed the workspace HEAD, which refresh_repair had left detached on master df5df9c86, moving both preserve refs off the run's real tip and stranding the reviewed tree 63afe28e (52 files) on no origin ref; `git ls-remote` reported the wrong SHA as verified because it proves presence, not that the SHA is the run's latest work. Hence: preserve the run branch's tip, never a detached HEAD; never move a ref to a non-descendant, write a sibling instead; record ancestry in the receipt. The interim reference implementation is the kubernetes-sandbox-backend session's preserve_runs.sh. The paragraph names no node, because the maintainer has directed a revert of the split red/green graph back to the single implement node, and the rule must hold for either graph. Research: plan/factory-run-work-preservation/research/003 and 004.

### Proposed Changes

Three edits.

**1. `SPECIFICATION/contracts.md`, §"Dispatcher admission, WIP cap, and post-merge acceptance": insert a new paragraph immediately after the paragraph that opens "**A janitor-green run that a factory restart or an outside cancel ends is published to a preservation ref.**"**

> **Every node visit that moves a run's branch tip is preserved to a work-in-progress ref.** A run's *work-in-progress refs* are the refs under `refs/livespec/wip/<work-item-id>/` whose name is `<run-id>` or `<run-id>-<sha12>`, where `<sha12>` is the first twelve hexadecimal digits of the first commit written to that ref. When a node visit of the implement-work-item workflow ends, whatever its outcome, and the engine's checkpoint for that visit moved the tip of the run's branch `fabro/run/<run-id>`, the run MUST put that tip on the item's repository before the next agent turn of the run starts, as follows. The commit preserved MUST be the tip of the run branch, never the workspace `HEAD`, which a node can leave detached on another commit. When the tip descends from the commit an existing work-in-progress ref of the run holds, the run MUST fast-forward that ref to the tip. When no work-in-progress ref of the run exists, the run MUST create `refs/livespec/wip/<work-item-id>/<run-id>`. When work-in-progress refs exist and the tip descends from none of them, because the run branch was rewritten, the run MUST create the sibling ref `refs/livespec/wip/<work-item-id>/<run-id>-<sha12>` for the tip and MUST leave every existing ref where it is. No update of a work-in-progress ref MAY be forced, and no work-in-progress ref MAY ever be moved to a commit that does not descend from the commit it holds. The push MUST be made by a command step of the workflow or by a run hook the workflow configuration declares, never by an agent turn. It MUST NOT create a commit, move `HEAD`, change the index or change the working tree, so that every later node sees exactly the state it would see without it. It MUST run with the repository's hooks disabled, and the tooling that holds the push credential MUST be the Dispatcher-materialized sandbox tooling outside the run's working tree, which no agent stage can modify. A push that fails MUST NOT change the visit's outcome, MUST NOT stop the run, and MUST be reported in the run's event stream naming the ref and the failed step; the next visit's push retries it. A work-in-progress ref is a recovery artifact, not a branch to publish: no pull request is opened from it, and no publication stage reads it. The run's *newest* work-in-progress ref is the one whose commit has the latest committer time. When the Dispatcher records a run's ending, or reports a run that ended outside the Dispatcher, it MUST read the run's work-in-progress refs from the forge and add one `livespec-preserved-tree` ledger comment to the item naming the run id, the factory name, the newest work-in-progress ref and its commit id, and every other work-in-progress ref of the run with its commit id, or stating that no work-in-progress ref exists for the run. A ref's presence on the forge MUST NOT by itself be reported as preservation of the run's latest work: the comment MUST state, for the newest ref, whether its commit is the run branch tip the run last reported, and the Dispatcher MUST NOT name a ref whose commit is reachable from the item's base commit alone as preserving the run. That comment MUST obey the template-opener and failure rules the checkpoint-failed paragraph above states for its own comment. Scenario 314 in `scenarios.md` exercises this paragraph.

**2. `SPECIFICATION/contracts.md`, §"Self-contained plugin dispatch", paragraph "**Publication is mechanically confined to the scripted publication stages.**":**

- Replace "Publication-capable credentials MUST be available only to the command stages `publish_draft`, `pr_refresh` and `pr`, which keep every publication action they are specified to take, and within those stages only to their own publication steps." with "Publication-capable credentials MUST be available only to the command stages `publish_draft`, `pr_refresh` and `pr`, which keep every publication action they are specified to take, and to the two preservation steps this paragraph names below, and within each of them only to its own publication or preservation step."
- Replace "A command node that preserves a run's work, such as the needs-human preservation step, therefore keeps the credentials its own contract requires." with "A command step that preserves a run's work, namely the needs-human preservation step and the work-in-progress preservation step of §\"Dispatcher admission, WIP cap, and post-merge acceptance\" → \"Every node visit that moves a run's branch tip is preserved to a work-in-progress ref\", therefore keeps the credential its own contract requires, and MUST use it only to push the run's own `refs/heads/needs-human/<run-id>` ref or the run's own work-in-progress refs respectively. Such a step MUST run no repository-controlled code while it holds the credential."

**3. `SPECIFICATION/scenarios.md`: append a new scenario after the last one.**

```markdown
## Scenario 314 — Every node visit that moves a run's branch tip is preserved to a work-in-progress ref

Governing clause: `contracts.md` §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Every node visit that moves a run's branch tip is preserved to a work-in-progress ref".

```gherkin
Feature: A run's work reaches origin as it progresses
  As the maintainer of a repository dispatched through the factory
  I want each finished node visit of a run on origin before the next agent turn starts
  So that a cancel, a server crash or an operator removal costs at most the node visit in progress

  Scenario: an implement visit's checkpoint is preserved before the next agent turn
    Given a run of work item W whose implement visit ended
    And the engine's checkpoint for that visit moved the tip of fabro/run/<run-id> to commit I
    When the run reaches its next agent turn
    Then origin's ref refs/livespec/wip/W/<run-id> points at commit I
    And the run's HEAD, index and working tree are the same as they were before the push
    And no repository hook ran for the push

  Scenario: a later visit fast-forwards the ref
    Given origin's ref refs/livespec/wip/W/<run-id> points at commit I
    When a fix visit ends with the run branch tip at commit F, which descends from I
    Then origin's ref refs/livespec/wip/W/<run-id> points at commit F

  Scenario: a rewritten run branch opens a sibling ref and moves nothing
    Given origin's ref refs/livespec/wip/W/<run-id> points at commit F
    When a refresh_repair visit rebases the run branch so that its tip, commit G, does not descend from F
    Then origin's ref refs/livespec/wip/W/<run-id> still points at commit F
    And origin's ref refs/livespec/wip/W/<run-id>-<first twelve digits of G> points at commit G

  Scenario: a detached workspace HEAD is not preserved in place of the run branch
    Given a node visit left the workspace HEAD detached on the default branch's commit D
    And the tip of fabro/run/<run-id> is commit G
    When the preservation runs
    Then the newest work-in-progress ref of the run points at commit G
    And no work-in-progress ref of the run points at commit D

  Scenario: a failed preservation push does not fail the run
    Given the forge refuses the push of the run's work-in-progress ref
    When a node visit of the run ends
    Then the visit keeps its own outcome and the run continues
    And the run's event stream names the ref and the failed step

  Scenario: the Dispatcher names every preserved commit on the item
    Given a run of work item W whose work-in-progress refs are refs/livespec/wip/W/<run-id> at commit F and refs/livespec/wip/W/<run-id>-<sha12> at the newer commit G
    When the Dispatcher records that the run ended, or reports that it ended outside the Dispatcher
    Then W carries a livespec-preserved-tree ledger comment naming the run id, the factory, refs/livespec/wip/W/<run-id>-<sha12> with commit G as the newest, and refs/livespec/wip/W/<run-id> with commit F
```
```

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new Scenario 314 heading (`test` MAY be "TODO" with a non-empty reason naming the owning work item).

## Proposal: Every Dispatcher path that destroys a run records its preserved work first

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a paragraph requiring that every Dispatcher code path that cancels a factory run, removes a run record or deletes a run's sandbox goes through one preserve-then-destroy step: it records on the item the run's preserved refs (its work-in-progress refs, and any needs-human or preserved-publish ref the existing clauses already create), then performs the destroy even when nothing was preserved. An enforcement check fails a Dispatcher module that reaches a destroying engine or sandbox call any other way. Add Scenario 315.

### Motivation

Plan factory-run-work-preservation Definition of Done assertion 3 (adding a run-ending or run-removal path that skips preservation is caught by a check before it merges) and work item bd-ib-xdhe5z. The Dispatcher has nine destroying call sites (wall-budget cancel, stall-watchdog cancel, cancel-for-restart, reconcile-runs, stale-item reap, ended-run collection, orphan reconcile, sandbox container and Kubernetes sandbox sweeps), and only two export anything first. With the work-in-progress refs of Scenario 314 carrying every finished node visit, the destroy step no longer has to read a live sandbox to preserve the run: it only has to name what is preserved before it destroys, which is what makes one wrapper sufficient. The maintainer accepted losing the node visit in progress.

### Proposed Changes

Two edits.

**1. `SPECIFICATION/contracts.md`, §"Dispatcher admission, WIP cap, and post-merge acceptance": insert a new paragraph immediately after the paragraph added by the proposal "Every node visit that moves a run's branch tip is preserved to a work-in-progress ref".**

> **Every Dispatcher path that destroys a run records its preserved work first.** Every Dispatcher code path that cancels a factory run, removes a run's record from a factory, or deletes a run's sandbox container or Kubernetes sandbox MUST do so through one preserve-then-destroy step. Before the destroying call, that step MUST perform every publication an existing clause of this section already requires for that ending (the checkpoint-failed publication and the janitor-green publication above), MUST read the run's work-in-progress refs from the forge, and MUST add the `livespec-preserved-tree` ledger comment of the work-in-progress paragraph above, naming every ref that preserves the run with its commit id, or stating that no ref preserves the run. It MUST then perform the destroying call even when no ref preserves the run or a publication failed, and the comment MUST name any step that failed. When a `livespec-preserved-tree` comment written after the run's last node visit already names the run's refs, the step MUST NOT add a second one. The step adds no new read of a live sandbox and MUST NOT delay a destroy on one: the work in progress that no ref carries is the bounded loss this section accepts. A repository check MUST fail when any Dispatcher module, other than the module that implements this step, calls a Fabro operation that cancels or deletes a run, or a container or Kubernetes operation that deletes a run's sandbox. Scenario 315 in `scenarios.md` exercises this paragraph.

**2. `SPECIFICATION/scenarios.md`: append a new scenario after Scenario 314.**

```markdown
## Scenario 315 — Every Dispatcher path that destroys a run records its preserved work first

Governing clause: `contracts.md` §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Every Dispatcher path that destroys a run records its preserved work first".

```gherkin
Feature: No Dispatcher destroy forgets what a run preserved
  As the maintainer of a repository dispatched through the factory
  I want every cancel, removal and sandbox deletion the Dispatcher makes to name the run's preserved work first
  So that a re-dispatch finds the work and no destroy path can quietly skip preservation

  Scenario: a wall-budget cancel names the preserved ref before it cancels
    Given a run of work item W past the whole-run wall budget whose newest work-in-progress ref points at commit C
    When the Dispatcher cancels the run
    Then W carries a livespec-preserved-tree ledger comment naming the run id, the factory, that ref and commit C
    And that comment was written before the cancel request

  Scenario: a destroy proceeds when nothing preserves the run
    Given an orphaned run with no work-in-progress ref and no other preservation ref
    When reconcile-runs removes the run
    Then the run is removed
    And its item carries a livespec-preserved-tree ledger comment stating that no ref preserves the run

  Scenario: a destroy that bypasses the step fails the check
    Given a Dispatcher module, other than the preserve-then-destroy module, that calls the Fabro run delete operation directly
    When the repository's checks run
    Then the check fails and names that module and call
```
```

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new Scenario 315 heading.

## Proposal: A run's newest work-in-progress ref is preserved work for recovery routing

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Extend the preference order of §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work" so a run's newest work-in-progress ref counts as that run's preserved work: a needs-human or preserved-publish ref published at the same run's ending is preferred over it, and it is preferred over the observed published head and over every preservation ref of an earlier run. A seed taken from it is taken exactly as a seed from a needs-human ref. Add Scenario 316.

### Motivation

Plan factory-run-work-preservation Definition of Done assertion 2: a re-dispatch of an item whose earlier run ended without merging starts from that run's preserved tree instead of redoing the stages that run had finished. Recovery routing already seeds from a needs-human ref and a preserved-publish ref; without this edit it would not know the work-in-progress refs exist, so the run endings that only those refs cover (a server crash, an operator fabro rm, a cancel outside the Dispatcher) would still route fresh. A work-in-progress ref has the same shape as a needs-human ref (the run branch tip, engine checkpoint commits included), and bd-ib-lmwyfj fixed how a seed carrying an earlier run's checkpoint commits is treated.

### Proposed Changes

Two edits.

**1. `SPECIFICATION/contracts.md`, §"Factory-configurable ACP fallback priority", paragraph "**Recovery from the failed run's preserved work.**": after the sentence that begins "Its preserved work MUST be taken in the preference order this clause states below", insert:**

> A run's newest work-in-progress ref under §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Every node visit that moves a run's branch tip is preserved to a work-in-progress ref" MUST count as that run's preserved work in that order: a needs-human ref or a preservation ref published at the same run's ending MUST be preferred over it, and it MUST be preferred over the observed published head and over every preservation ref of an earlier run of the item. The run's other work-in-progress refs MUST NOT be taken as its preserved work. A seed taken from a work-in-progress ref MUST be taken exactly as a seed from the needs-human ref of §"A factory run never awaits a human" is taken, including how the earlier run's checkpoint commits it carries are treated.

**2. `SPECIFICATION/scenarios.md`: append a new scenario after Scenario 315.**

```markdown
## Scenario 316 — A re-dispatch starts from the latest run's newest work-in-progress ref

Governing clause: `contracts.md` §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work".

```gherkin
Feature: A re-dispatch does not redo a lost run's finished node visits
  As the maintainer of a repository dispatched through the factory
  I want a re-dispatch to start from the newest tree the item's latest run preserved
  So that a run lost to a crash or a removal costs only the node visit that was in progress

  Scenario: a run removed without a terminal publication is seeded from its newest work-in-progress ref
    Given work item W whose latest run was removed by an operator fabro rm after its fix visit
    And that run's newest work-in-progress ref points at the checkpoint of that fix visit
    And no needs-human ref or preservation ref was published at that run's ending
    When W is released for recovery and routed
    Then the route is seeded from that newest work-in-progress ref
    And the dispatch brief names that ref as the tree to start from

  Scenario: a terminal publication of the same run is preferred
    Given work item W whose latest run has both a work-in-progress ref and a preserved-publish ref published at its ending
    When W is released for recovery and routed
    Then the route is seeded from the preserved-publish ref
```
```

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new Scenario 316 heading.

## Proposal: Preservation refs are deleted when their item closes

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a retention paragraph: when the Dispatcher observes that a work item is closed, it deletes that item's refs under refs/livespec/wip/<work-item-id>/ and refs/livespec/preserved-publish/<work-item-id>/ and the refs/heads/needs-human/<run-id> refs of the item's runs. Refs whose item closed before the rule took effect are outside its scope. Add Scenario 317.

### Motivation

Plan factory-run-work-preservation Definition of Done assertion 4: preserved run refs on origin are removed by a stated retention rule once they are no longer needed, so they do not accumulate. On 2026-11-04 origin held 617 preservation refs (420 needs-human, 197 preserved-publish) and no rule removed any; work-in-progress refs add at least one more per dispatch. A closed item never re-dispatches, so its preserved work is no longer needed. Tying deletion to item closure, rather than to an age limit, never deletes the seed of an item that is still waiting on a human. Deleting the existing 617 refs is an irreversible outward-facing act the maintainer has not separately authorized, so the rule does not reach refs whose item closed before it took effect.

### Proposed Changes

Two edits.

**1. `SPECIFICATION/contracts.md`, §"Dispatcher admission, WIP cap, and post-merge acceptance": insert a new paragraph immediately after the paragraph added by the proposal "Every Dispatcher path that destroys a run records its preserved work first".**

> **Preservation refs are deleted when their item closes.** When the Dispatcher observes that a work item is `closed`, on its own close or accept path or on any later pass that reads the item, it MUST delete from the item's repository every ref under `refs/livespec/wip/<work-item-id>/` and `refs/livespec/preserved-publish/<work-item-id>/`, and the `refs/heads/needs-human/<run-id>` ref of every run its dispatch journal or the item's `livespec-preserved-tree` comments attribute to that item. It MUST NOT delete a ref of an item that is not `closed`. A deletion that fails MUST be retried on a later pass and MUST NOT change the item's state. Refs whose item was already `closed` before this paragraph took effect are outside its scope. Scenario 317 in `scenarios.md` exercises this paragraph.

**2. `SPECIFICATION/scenarios.md`: append a new scenario after Scenario 316.**

```markdown
## Scenario 317 — Preservation refs are deleted when their item closes

Governing clause: `contracts.md` §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Preservation refs are deleted when their item closes".

```gherkin
Feature: Preserved run refs do not accumulate on origin
  As the maintainer of a repository dispatched through the factory
  I want an item's preserved run refs removed once the item is closed
  So that origin keeps only the preserved work that a re-dispatch can still use

  Scenario: closing an item deletes its preservation refs
    Given work item W with refs under refs/livespec/wip/W/ and refs/livespec/preserved-publish/W/ and a needs-human ref of one of its runs
    When W is closed and the Dispatcher next reads it
    Then none of those refs exists on origin

  Scenario: an open item keeps its preservation refs
    Given work item W, blocked for a human, with a ref under refs/livespec/wip/W/
    When the Dispatcher reads W
    Then that ref still exists on origin
```
```

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new Scenario 317 heading.
