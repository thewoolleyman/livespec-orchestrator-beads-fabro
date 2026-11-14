---
topic: a-drain-pass-relinks-a
author: claude-opus-5-5
created_at: 2026-11-13T01:28:05Z
---

## Proposal: An intake or drain pass relinks a held item to the proposal its deposit commit names

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A held spec-change-tier item's linked topic is the stem the Dispatcher derived when it classified the item. The proposal that is later filed for it often carries a different stem, and nothing binds the two. The hold then waits for a ratification it can never read. This proposal makes each intake or drain pass bind the item to its DEPOSIT: the one proposed-change topic that a default-branch commit naming the item's id ADDED. The pass writes exactly what the `relink-spec-tier` route writes. A relink never releases the hold. Two or more deposited topics, or any ambiguous one, produce one needs-attention fact and no relink, and a linked topic that already names a proposed change is never replaced.

### Motivation

Implementation item bd-ib-d7vppg. legacy-coordinator-agent (session 56ce1bcd, 2026-11-13) accepted this design as the fleet-scope root fix for orphaned spec-tier holds.

Measured by legacy-dispatcher-agent at 2026-11-13 00:59Z, over 159 READY items in five tenants: 29 screen as a spec-tier hold.

- 10 are legitimately pending.
- 3 are orphans RATIFIED under a different slug: livespec-dev-tooling-2zb3gk, livespec-dev-tooling-ln7q3b and bd-ib-z7ckf4.
- 16 are orphans with no deposit anywhere.
- Earlier the same night, donph5, faetyh (wrong slug on #5107) and nuswku (#5108's slug differs from its tier record) were the same class.

Cause: classification records the stem it derives from the item's title, and `/livespec:propose-change` canonicalizes whatever topic hint its caller passes. Nothing ties the second to the first. The `relink-spec-tier` route repairs one item by hand. The existing relink-candidate fact (Scenario 206) names only a RATIFIED revision that amended the item's generalization-target heading, so it never sees a pending deposit, or a ratified deposit that amended a different heading.

The binding datum already exists. Fleet proposal and revise commits name their item in the subject, for example `chore(spec): propose a-drift-pass-reuses-one (bd-ib-kojs3t)`, and rebase-merge keeps the subject. Measured 2026-11-13:

- 138 of the last 200 commits that added a file under this repository's `SPECIFICATION/proposed_changes/` name an item id.
- livespec-dev-tooling's propose commits name 2zb3gk (d92f3931b) and ln7q3b (285cb6b2c).
- donph5 is named only by its revise commit 118e617a8, which ADDED the archived copy under `history/vNNN/proposed_changes/`. That is why a history addition counts as a deposit too.

Alternatives rejected:

- propose-change takes the item id and writes the linked stem. propose-change is livespec core, which reads no work-item ledger, so this would put orchestrator realization into core.
- The hold releases on a ratified proposal whose front matter names the item. Proposal front matter is core's format, and the hold read must stay model-free and fail closed.

Two guards are stated on the coordinator's ruling. First, only a commit that ADDED the proposal file counts: a commit that names the id while editing other proposals binds nothing. Second, a relink never releases.

A third guard comes from a measured shape. A revise commit can add the archived copies of several topics while naming one item, so a single commit that adds two or more topics is ambiguous evidence, never a binding.

In-flight alignment: this aligns with `a-spec-change-tier-hold` (#5080). That proposal makes the derived stem unique and says a recorded topic "is repaired only through the `relink-spec-tier` route". The pass below repairs through exactly that route's recording, never by re-deriving the stem.

### Proposed Changes

**1. `SPECIFICATION/contracts.md` §"Work-item state semantics".** Directly after the paragraph that begins "`relink-spec-tier:<work-item-id>:<topic>` is valid in every lane except `done`", insert:

> **An intake or drain pass binds a held item to its deposit.** A commit's ADDED files are the paths its diff against its first parent reports as added, computed with rename detection OFF. So a revise that moves `<spec-root>/proposed_changes/<topic>.md` into `<spec-root>/history/vNNN/proposed_changes/` ADDS the history path. A commit DEPOSITS a topic for an item when it is on the governed repository's default branch, its subject names the item's id as a whole token, and its added files include exactly one proposed-change file: `<spec-root>/proposed_changes/<topic>.md` or `<spec-root>/history/vNNN/proposed_changes/<topic>.md`. A file whose stem ends in `-revision` is a revision record and MUST NOT be counted as a proposed-change file. A commit whose added files include no proposed-change file MUST NOT deposit anything, whatever proposals it edits. A commit whose added files include two or more proposed-change files with distinct topics MUST NOT deposit any of them: each of those topics is AMBIGUOUS for every item the commit names.
>
> Each intake or drain pass MUST, for every held spec-change-tier item whose linked topic names neither a pending proposed change nor a revision record, collect the item's deposited topics and its ambiguous topics. When exactly one topic is deposited and no topic is ambiguous, the pass MUST relink the item only as `relink-spec-tier:<work-item-id>:<topic>` would. It applies each of that route's refusal conditions, and on success writes exactly that route's success recording: the durable ledger comment carrying the actor, the previous linked topic and the replacement topic, and the replacement spec-change tier record. The pass is named as the actor. A topic the route would refuse MUST be reported, never relinked. The pass MUST NOT re-derive the item's stem.
>
> When two or more topics are deposited, or any topic is ambiguous, the pass MUST NOT relink. `needs-attention` then MUST carry ONE `hygiene:spec-tier-relink:<work-item-id>` fact for the item. It replaces, and never duplicates, the fact the autonomy-tier bullet already requires for a ratified generalization-target relink candidate. Its `summary` names the linked topic and the union of the deposited topics, the ambiguous topics and that ratified relink candidate when there is one. It carries one `handoff` per topic, each naming `relink-spec-tier:<work-item-id>:<topic>`. A pass MUST NOT replace a linked topic that names a pending proposed change or a revision record. The binding is a read of git history and the spec tree, and it needs no model.
>
> A relink by a pass MUST NOT release the hold, exactly as a relink by the route does not. The hold is released only when the replacement topic carries a revision record with decision `accept` or `modify` and a re-run judgement returns `stated` on a later intake or drain pass, exactly as the `relink-spec-tier` clause states.

**1a. `SPECIFICATION/contracts.md` §"Work-item state semantics", the `relink-spec-tier` paragraph.** Replace "the route MAY be driven by a human or by an agent session." with "the route MAY be driven by a human, an agent session, or an intake or drain pass under the deposit binding below."

**2. `SPECIFICATION/scenarios.md`, `## Scenario 206 — The spec-change tier is decided by the spec-stated judgement, and a feature waits for ratification`.** Inside that scenario's Gherkin block, after the scenario `A rejected revision is never named as a relink candidate` and before the block's closing fence, add:

```gherkin
  Scenario: A drain pass relinks a held item to the one proposal its deposit commit added
    Given a held spec-change-tier item whose linked topic names neither a pending proposed change nor a revision record
    And a default-branch commit whose subject names the item's id added SPECIFICATION/proposed_changes/<topic>.md and no other proposed-change file
    When the next intake or drain pass runs
    Then the item's linked topic is <topic>
    And a durable ledger comment on the item records the pass as actor, the previous topic and <topic>
    And the item still carries its spec-change-tier hold

  Scenario: A deposit found only in the spec history binds the item
    Given a held spec-change-tier item whose linked topic names neither a pending proposed change nor a revision record
    And the only default-branch commit naming the item's id is a revise commit that added SPECIFICATION/history/vNNN/proposed_changes/<topic>.md and its revision record
    When the next intake or drain pass runs
    Then the item's linked topic is <topic>
    And once the re-run judgement returns stated against the ratified specification, a later intake or drain pass releases the hold

  Scenario: A commit that names the item without adding a proposal binds nothing
    Given a held spec-change-tier item whose linked topic names neither a pending proposed change nor a revision record
    And the only default-branch commit naming the item's id edits an existing proposed-change file and adds none
    When the next intake or drain pass runs
    Then the item's linked topic and ledger comments are unchanged

  Scenario: Two deposited topics produce one needs-attention fact and no relink
    Given a held spec-change-tier item whose linked topic names neither a pending proposed change nor a revision record
    And two default-branch commits naming the item's id, each adding exactly one proposed-change file, with different topics
    When the next intake or drain pass runs and needs-attention is composed
    Then the item's linked topic and ledger comments are unchanged
    And needs-attention carries one hygiene:spec-tier-relink:<work-item-id> fact naming both topics, with one relink-spec-tier handoff per topic

  Scenario: One commit that adds two topics makes each ambiguous and never a deposit
    Given a held spec-change-tier item whose linked topic names neither a pending proposed change nor a revision record
    And the only default-branch commit naming the item's id added two proposed-change files with different topics
    When the next intake or drain pass runs and needs-attention is composed
    Then the item's linked topic and ledger comments are unchanged
    And needs-attention carries one hygiene:spec-tier-relink:<work-item-id> fact naming both topics

  Scenario: A linked topic that names a proposed change is never replaced by a pass
    Given a held spec-change-tier item whose linked topic names a pending proposed change
    And a default-branch commit naming the item's id added a proposed-change file under a different topic
    When the next intake or drain pass runs
    Then the item's linked topic is unchanged
```

This edits an existing scenario and adds no `## ` heading, so `tests/heading-coverage.json` is unchanged.
