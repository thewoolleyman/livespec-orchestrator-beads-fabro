---
topic: factory-run-work-preserved-on-progress
author: claude-opus-5-5
created_at: 2026-11-05T06:58:06Z
---

## Proposal: Each committing step of a run preserves the run branch's tip to an ordered work-in-progress ref

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a paragraph to contracts.md §"Dispatcher admission, WIP cap, and post-merge acceptance": at the end of every command step that settles or makes an agent stage's commits, and in the needs_human preservation step, the run pushes the tip of its run branch `fabro/run/<run-id>` to a new, never-rewritten ref `refs/livespec/wip/<work-item-id>/<run-id>/<n>`, numbered in capture order. A tip whose tree equals the run's base tree or the default branch's tree is never preserved, which defeats the engine's reset of the run branch to a detached HEAD. The push is never forced, changes nothing locally, runs with repository hooks and repository-controlled git configuration neutralized, uses Dispatcher-materialized tooling, and never fails the run. The needs_human step preserves the run branch tip under the same guard. Amend the credential-confinement clause to name the step. Add Scenario 314.

### Motivation

Maintainer ruling of 2026-11-05 on plan factory-run-work-preservation (epic bd-ib-nckst7), verbatim: "I like this direction. It prioritizes simplicity. And I am fine accepting the loss of a single node if the entire server crashes or the run is cancelled." Measured losses: bd-ib-yuwftp run 01M6KBH30NJA (about six hours, wall-budget cancel then fabro rm -f); bd-ib-ac5lgi run 01M6KNR090B2 (janitor checkpoint 30fdbeca, stall-watchdog cancel); bd-ib-uq2ocd run 01M6JSNVH32S8CDNX0P4TS7DWB (janitor-green commit, restart cancel). The engine's run_branch push was rejected because it is never forced and stalls after any rewrite. A forced push was ruled out by a measured regression (bd-ib-rhivsm run 01M6MHQE92Q4, 2026-11-05 06:20Z, relayed by legacy-coordinator-agent): forcing a detached workspace HEAD moved the preserve refs off the run's work. Two independent reviews (Astra gpt-6-astra and Fable 5.1, 2026-11-05, plan/factory-run-work-preservation/research/005) then established, against the serving fork lineage: (1) the engine's checkpoint runs `git checkout -q -B <run-branch>` whenever HEAD is not on the run branch (fabro-petri checkpoint.rs:766-790), so after a node leaves HEAD detached on the default branch the run branch itself becomes that commit plus an empty checkpoint; preserving 'the branch tip' alone, or choosing the newest ref by committer time, would then preserve and seed from a work-free tree, hence the tree guard; (2) committer time cannot order captures, hence immutable numbered refs; (3) the agent stages' commits all land through the detached commit runner and are settled by the implement, fix and review_fix commit-settle command steps of the single-implement graph the maintainer directed a revert to, so pushing at the end of those steps covers every committed change with three to six pushes a run, adds no graph node, moves no edge condition, and keeps the credential in a command step the confinement clause can name; (4) Petri reports checkpoint_saved hooks as unsupported, and a run hook has no stage identity for a credential scope to key on. A failed push leaves the run preserved through its last successful capture; that is stated, recorded and reported rather than hidden.

### Proposed Changes

Three edits.

**1. `SPECIFICATION/contracts.md`, §"Dispatcher admission, WIP cap, and post-merge acceptance": insert a new paragraph immediately after the paragraph that opens "**A janitor-green run that a factory restart or an outside cancel ends is published to a preservation ref.**"**

> **Each committing step of a run preserves the run branch's tip to an ordered work-in-progress ref.** A run's *work-in-progress refs* are the refs `refs/livespec/wip/<work-item-id>/<run-id>/<n>`, where `<n>` is a decimal capture ordinal starting at 1. A *preserving step* is every command step of the implement-work-item workflow that settles or makes an agent stage's commits (in the single-implement graph, `implement_commit_settle`, `fix_commit_settle` and `review_fix_commit_settle`) and the needs-human preservation step of §"A factory run never awaits a human". At its end, before the run takes its next transition or ends, a preserving step MUST preserve the tip of the run branch `fabro/run/<run-id>`, as follows. It MUST read the run branch's tip, never the workspace `HEAD`. It MUST NOT preserve a tip whose tree equals the tree of the run's base commit or the tree of the default branch's head on origin, because the engine's checkpoint moves the run branch onto the workspace `HEAD` whenever a node leaves `HEAD` detached, and such a tip carries none of the run's work. It MUST NOT preserve a tip equal to the commit of the run's highest-numbered work-in-progress ref. Otherwise it MUST create the run's next work-in-progress ref, numbered one above the highest existing one, at that tip. A work-in-progress ref MUST be created once and never updated, deleted or force-written while its item is open, so every capture stays fetchable in order. The push MUST NOT create a commit, move `HEAD`, change the index or change the working tree; it MUST run with the repository's hooks disabled and with repository-controlled git configuration that could redirect or observe the push ignored; and the tooling that holds the push credential MUST be the Dispatcher-materialized sandbox tooling outside the run's working tree, which no agent stage can modify. A preservation that fails or is skipped MUST NOT change the step's outcome or stop the run, and MUST be reported in the step's own recorded output naming the ref, the tip and the reason. The run is then preserved through its last successful capture, and a later capture retries. The needs-human preservation step keeps its own `refs/heads/needs-human/<run-id>` ref, and the commit it pushes there MUST be built on the run branch's tip under the same tree guard, never on a detached `HEAD`. A work-in-progress ref is a recovery artifact, not a branch to publish: no pull request is opened from it, and no publication stage reads it. The run's *latest preserved capture* is its highest-numbered work-in-progress ref. A repository check MUST fail when the workflow declares a step that settles or makes an agent stage's commits without this preservation. Scenario 314 in `scenarios.md` exercises this paragraph.

**2. `SPECIFICATION/contracts.md`, §"Self-contained plugin dispatch", paragraph "**Publication is mechanically confined to the scripted publication stages.**":**

- Replace "Publication-capable credentials MUST be available only to the command stages `publish_draft`, `pr_refresh` and `pr`, which keep every publication action they are specified to take, and within those stages only to their own publication steps." with "Publication-capable credentials MUST be available only to the command stages `publish_draft`, `pr_refresh` and `pr`, which keep every publication action they are specified to take, and to the preserving steps this paragraph names below, and within each of them only to its own publication or preservation step."
- Replace "A command node that preserves a run's work, such as the needs-human preservation step, therefore keeps the credentials its own contract requires." with "A command step that preserves a run's work, namely each preserving step of §\"Dispatcher admission, WIP cap, and post-merge acceptance\" → \"Each committing step of a run preserves the run branch's tip to an ordered work-in-progress ref\", the needs-human preservation step included, therefore keeps the credential its own contract requires, and its preservation MUST push only the run's own `refs/heads/needs-human/<run-id>` ref or the run's own work-in-progress refs. Such a step MUST run no repository-controlled code while it holds the credential."

**3. `SPECIFICATION/scenarios.md`: append a new scenario after the last one.**

```markdown
## Scenario 314 — Each committing step of a run preserves the run branch's tip to an ordered work-in-progress ref

Governing clause: `contracts.md` §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Each committing step of a run preserves the run branch's tip to an ordered work-in-progress ref".

```gherkin
Feature: A run's committed work reaches origin as it progresses
  As the maintainer of a repository dispatched through the factory
  I want each settled agent stage's commits on origin before the run moves on
  So that a cancel, a server crash or an operator removal costs at most the node visit in progress

  Scenario: a settled implement visit is preserved as the run's first capture
    Given a run of work item W whose implement visit committed through the detached commit runner
    When implement_commit_settle ends with the tip of fabro/run/<run-id> at commit I
    Then origin's ref refs/livespec/wip/W/<run-id>/1 points at commit I
    And the run's HEAD, index and working tree are the same as they were before the push
    And no repository hook ran for the push

  Scenario: a later settled visit adds the next capture and rewrites nothing
    Given origin's ref refs/livespec/wip/W/<run-id>/1 points at commit I
    When fix_commit_settle ends with the run branch's tip at commit F
    Then origin's ref refs/livespec/wip/W/<run-id>/2 points at commit F
    And origin's ref refs/livespec/wip/W/<run-id>/1 still points at commit I

  Scenario: a tip the engine reset onto the default branch is not preserved
    Given origin's ref refs/livespec/wip/W/<run-id>/2 points at commit F
    And a node left the workspace HEAD detached on the default branch's head D, and the engine's next checkpoint moved fabro/run/<run-id> to an empty commit on D
    When the next preserving step runs
    Then no work-in-progress ref of the run is created at that tip
    And the step's recorded output names the tip and states that its tree carries none of the run's work
    And the run's latest preserved capture is still refs/livespec/wip/W/<run-id>/2

  Scenario: a failed preservation push does not fail the run
    Given the forge refuses the push of the run's next work-in-progress ref
    When fix_commit_settle ends
    Then the step keeps its own outcome and the run continues
    And the step's recorded output names the ref, the tip and the failure

  Scenario: needs-human preserves the run branch, not a detached HEAD
    Given a run whose workspace HEAD is detached on the default branch's head while fabro/run/<run-id> holds the run's work
    When the run reaches needs_human
    Then origin's ref refs/heads/needs-human/<run-id> holds a tree that carries the run's work

  Scenario: a committing step without preservation fails the check
    Given a workflow that declares a step settling an agent stage's commits without the preservation
    When the repository's checks run
    Then the check fails and names that step
```
```

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new Scenario 314 heading (`test` MAY be "TODO" with a non-empty reason naming the owning work item).

## Proposal: A run's ending names its latest preserved capture on the item

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a paragraph requiring the Dispatcher, wherever it records a run's non-green ending (its terminal disposition) or releases an item whose run is absent, to list the run's work-in-progress refs on the forge and add one livespec-preserved-tree ledger comment naming the latest preserved capture and its commit, or stating that none exists. No wrapper around destroy call sites and no live-sandbox read. Add Scenario 315.

### Motivation

Plan factory-run-work-preservation Definition of Done assertion 1 (the preserved tree's commit id is recorded on the item's ledger). Both independent reviews (research note 005) found the earlier draft's preserve-then-destroy wrapper over nine Dispatcher call sites unnecessary once every settled capture is already on origin: recovery routing discovers preserved refs by `git ls-remote` on the run id (`_dispatcher_recovery_preserved.py:221-248`), and every non-green ending already passes one terminal disposition (`_dispatcher_terminal_routing.py:100-160`). The wrapper's proposed caller check could not be built on fabro_port_seam, which confines transport rather than callers, and would have flagged thread-handle `.cancel(` calls and probe-run removals. A receipt at the one place an ending is recorded gives the human the commit id at a fraction of the surface.

### Proposed Changes

Two edits.

**1. `SPECIFICATION/contracts.md`, §"Dispatcher admission, WIP cap, and post-merge acceptance": insert a new paragraph immediately after the paragraph added by the proposal "Each committing step of a run preserves the run branch's tip to an ordered work-in-progress ref".**

> **A run's ending names its latest preserved capture on the item.** When the Dispatcher records a run's ending that is not a merge, or releases an item whose run is absent from its factory, it MUST list the run's work-in-progress refs on the forge and add one `livespec-preserved-tree` ledger comment to the item naming the run id, the factory name, the run's latest preserved capture and its commit id, or stating that the run has no work-in-progress ref. When the forge cannot be read, the comment MUST say that the preservation could not be determined, which is distinct from the run having none. When a `livespec-preserved-tree` comment already names the same run and the same latest capture, the Dispatcher MUST NOT add a second one. The comment MUST obey the template-opener and failure rules that the checkpoint-failed paragraph above states for its own comment, and writing it MUST NOT delay or prevent any cancel, removal or state transition. Scenario 315 in `scenarios.md` exercises this paragraph.

**2. `SPECIFICATION/scenarios.md`: append a new scenario after Scenario 314.**

```markdown
## Scenario 315 — A run's ending names its latest preserved capture on the item

Governing clause: `contracts.md` §"Dispatcher admission, WIP cap, and post-merge acceptance" → "A run's ending names its latest preserved capture on the item".

```gherkin
Feature: The ledger says where a lost run's work is
  As the maintainer of a repository dispatched through the factory
  I want every run that ended without merging to name its latest preserved capture on its item
  So that I can find the work without reading the forge's refs

  Scenario: a wall-budget cancel names the latest capture
    Given a run of work item W whose highest-numbered work-in-progress ref is refs/livespec/wip/W/<run-id>/3 at commit C
    When the Dispatcher records the run's wall-budget cancel
    Then W carries a livespec-preserved-tree ledger comment naming the run id, the factory, refs/livespec/wip/W/<run-id>/3 and commit C

  Scenario: a run with no capture is named as having none
    Given a run of work item W that ended before any preserving step ran
    When the Dispatcher records the run's ending
    Then W carries a livespec-preserved-tree ledger comment stating that the run has no work-in-progress ref

  Scenario: an unreadable forge is not reported as no capture
    Given the forge refuses the Dispatcher's listing of the run's work-in-progress refs
    When the Dispatcher records the run's ending
    Then W carries a livespec-preserved-tree ledger comment stating that the preservation could not be determined
```
```

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new Scenario 315 heading.

## Proposal: Recovery routing seeds from the latest run's latest preserved capture

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Extend the preference order of §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work" so a run's latest preserved capture counts as that run's preserved work: a needs-human or preserved-publish ref published at the same run's ending is preferred over it, and it is preferred over the observed published head and over every preservation ref of an earlier run. The existing preference for a valid published-PR resume is unchanged. Add Scenario 316, including an end-to-end continuation case.

### Motivation

Plan factory-run-work-preservation Definition of Done assertion 2: a re-dispatch of an item whose earlier run ended without merging starts from that run's preserved tree instead of redoing the stages that run had finished. Recovery routing already seeds from needs-human and preserved-publish refs; it must also find work-in-progress refs, which it can discover by name exactly as it discovers needs-human refs. The Astra review (research note 005) found that naming a ref in a brief does not prove continuation, so the scenario carries one case that restores a capture into a fresh sandbox and continues through the real commit gates. A seeded dispatch preserves code, not Fabro's execution position; required validation and review still run.

### Proposed Changes

Two edits.

**1. `SPECIFICATION/contracts.md`, §"Factory-configurable ACP fallback priority", paragraph "**Recovery from the failed run's preserved work.**": after the sentence that begins "Its preserved work MUST be taken in the preference order this clause states below", insert:**

> A run's latest preserved capture under §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Each committing step of a run preserves the run branch's tip to an ordered work-in-progress ref" MUST count as that run's preserved work in that order: a needs-human ref or a preservation ref published at the same run's ending MUST be preferred over it, and it MUST be preferred over the observed published head and over every preservation ref of an earlier run of the item. A `resume` that every precondition of §"Resume from a published pull request (`resume --item`)" admits keeps its precedence over any seed. A seed taken from a work-in-progress ref MUST be taken exactly as a seed from the needs-human ref of §"A factory run never awaits a human" is taken. A seeded dispatch restores the captured code, not the earlier run's position in the workflow: every stage the workflow requires still runs.

**2. `SPECIFICATION/scenarios.md`: append a new scenario after Scenario 315.**

```markdown
## Scenario 316 — A re-dispatch starts from the latest run's latest preserved capture

Governing clause: `contracts.md` §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work".

```gherkin
Feature: A re-dispatch does not redo a lost run's settled work
  As the maintainer of a repository dispatched through the factory
  I want a re-dispatch to start from the newest work the item's latest run preserved
  So that a run lost to a crash or a removal costs only the node visit that was in progress

  Scenario: a run removed without a terminal publication is seeded from its latest capture
    Given work item W whose latest run was removed by an operator fabro rm after its fix visit settled
    And that run's highest-numbered work-in-progress ref holds the settled fix commit
    And no needs-human ref or preservation ref was published at that run's ending
    When W is released for recovery and routed
    Then the route is seeded from that work-in-progress ref
    And the dispatch brief names that ref as the tree to start from

  Scenario: a terminal publication of the same run is preferred
    Given work item W whose latest run has both a work-in-progress ref and a preserved-publish ref published at its ending
    When W is released for recovery and routed
    Then the route is seeded from the preserved-publish ref

  Scenario: a seeded run carries the preserved work through the commit gates
    Given work item W seeded from a work-in-progress ref that holds a settled implement commit and a later settled fix commit
    When the seeded run reaches publication in a fresh sandbox
    Then the published branch carries both preserved changes
    And every commit on it passed the repository's commit and pre-push gates
```
```

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new Scenario 316 heading.

## Proposal: Preservation refs are deleted when the Dispatcher closes or collects an item's runs

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a retention paragraph: when the Dispatcher itself closes or accepts a work item, and when its ended-run collection removes an ended run of a closed item, it deletes the item's work-in-progress and preserved-publish refs and the needs-human refs of the runs it acts on. Because the rule fires only on those Dispatcher actions, items closed before it shipped are untouched without any cutoff date. Add Scenario 317.

### Motivation

Plan factory-run-work-preservation Definition of Done assertion 4: preserved run refs on origin are removed by a stated retention rule once they are no longer needed, so they do not accumulate. On 2026-11-04 origin held 617 preservation refs and no rule removed any. A closed item never re-dispatches, so its preserved work is no longer needed; tying deletion to closure rather than age never deletes the seed of an item waiting on a human. Both reviews (research note 005) found the earlier 'refs whose item closed before this took effect' boundary ungradeable, since nothing records when a paragraph took effect; firing only on the Dispatcher's own close or accept and on its ended-run collection, which already acts only on runs of closed items (`_dispatcher_ended_run_collection.py:36-72`), gives the same boundary with nothing to record, and runs after the run can no longer push. Deleting the existing 617 refs needs a separate maintainer go.

### Proposed Changes

Two edits.

**1. `SPECIFICATION/contracts.md`, §"Dispatcher admission, WIP cap, and post-merge acceptance": insert a new paragraph immediately after the paragraph added by the proposal "A run's ending names its latest preserved capture on the item".**

> **Preservation refs are deleted when the Dispatcher closes or collects an item's runs.** When the Dispatcher itself moves a work item to `closed`, including by acceptance, it MUST delete from the item's repository every ref under `refs/livespec/wip/<work-item-id>/` and `refs/livespec/preserved-publish/<work-item-id>/`. When its ended-run collection removes an ended run of a `closed` item, it MUST delete that run's work-in-progress refs, its `refs/heads/needs-human/<run-id>` ref, and the item's refs under `refs/livespec/preserved-publish/<work-item-id>/`. It MUST NOT delete a preservation ref of an item that is not `closed`. A deletion that fails MUST be journaled with the ref and retried on the Dispatcher's next pass, and MUST NOT change the item's state. Scenario 317 in `scenarios.md` exercises this paragraph.

**2. `SPECIFICATION/scenarios.md`: append a new scenario after Scenario 316.**

```markdown
## Scenario 317 — Preservation refs are deleted when the Dispatcher closes or collects an item's runs

Governing clause: `contracts.md` §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Preservation refs are deleted when the Dispatcher closes or collects an item's runs".

```gherkin
Feature: Preserved run refs do not accumulate on origin
  As the maintainer of a repository dispatched through the factory
  I want an item's preserved run refs removed once the Dispatcher closes it or collects its ended runs
  So that origin keeps only the preserved work that a re-dispatch can still use

  Scenario: accepting an item deletes its preservation refs
    Given work item W with refs under refs/livespec/wip/W/ and refs/livespec/preserved-publish/W/
    When the Dispatcher accepts W
    Then none of those refs exists on origin

  Scenario: collecting a closed item's ended run deletes that run's refs
    Given a closed work item W whose ended run R has work-in-progress refs and a needs-human ref
    When the Dispatcher's ended-run collection removes R
    Then neither R's work-in-progress refs nor refs/heads/needs-human/R exists on origin

  Scenario: an open item keeps its preservation refs
    Given work item W, blocked for a human, with a ref under refs/livespec/wip/W/
    When the Dispatcher's ended-run collection runs
    Then that ref still exists on origin

  Scenario: a failed deletion is retried
    Given the forge refuses the deletion of a closed item's preservation ref
    When the Dispatcher's next pass runs
    Then it attempts the deletion again and the item's state is unchanged
```
```

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new Scenario 317 heading.
