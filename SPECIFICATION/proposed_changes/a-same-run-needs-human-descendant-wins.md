---
topic: a-same-run-needs-human-descendant-wins
author: claude-opus-5-5
created_at: 2026-11-08T01:57:54Z
---

## Proposal: Of several needs-human refs carrying one run, the tip that descends from the others seeds the route

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Replace the same-run preference in contracts.md §"Factory-configurable ACP fallback priority", paragraph "A needs-human tree is recognised by the run it carries, not only by its ref name." When several needs-human refs carry the same run, routing takes the ref whose tip descends from the tips of all the others. When no tip does, it takes the tip newest by committer time. The ref's name decides only between refs whose tips are the same commit. Today's rule prefers a ref named under a run identifier over any other carrying ref, so it can seed a re-dispatch from an ancestor of the run's latest preserved tree and throw away the commits between them. Scenario 185's two tie-break scenarios are reworded to the new rule, and three scenarios are added: a same-commit tie, the measured bd-ib-ofvsr3 instance, and an unreadable ancestry that holds the route. No H2 heading is added or removed.

### Motivation

Plan factory-run-work-preservation (epic bd-ib-nckst7), plan assertion 2: a re-dispatch of an item whose earlier run ended without merging starts from that run's preserved tree instead of redoing the stages it had finished. Measured on 2026-11-08 at about 02:00Z: bd-ib-ofvsr3's run 01M6S83KZH54MR6N8NECJN86Z8 is carried by refs/heads/needs-human/01M6S83KZH54MR6N8NECJN86Z8 at d7f0102e1 and by refs/heads/needs-human/4d5104454d7b406a80014d6d2acc139e at 578a981c2. Both tips hold the trailer `Fabro-Run: 01M6S83KZH54MR6N8NECJN86Z8`, and 578a981c2 descends from d7f0102e1 by 3 commits. The v308 rule (a-plain-dispatch-has-no, bd-ib-ltlg4i) prefers the ref named under the run id, so it mandates d7f0102e1 and drops those 3 commits. v308 added the preference to make otherwise-unread alias refs visible (bd-ib-abbb3j, bd-ib-hap62u) and did not consider an alias holding a LATER tree of the same run. Ruled by legacy-coordinator-agent under R301 on 2026-11-08: take the tip that descends from all the others; otherwise the newest by committer time; the ref name breaks only a tie at the same commit; add a scenario using bd-ib-ofvsr3's refs. publish-draft-green-work-loss, which owns v308, raised no objection. Fleet scope: orchestrator recovery routing serves every fleet member through its pinned build, so the clause lives in one place. In-flight alignment: the pending proposal a-fresh-ruling-routes-a-released-item-fresh only consumes passed_over_needs_human, which this change keeps (align). bd-ib-ltlg4i and bd-ib-7gssim implement the v308 paragraph in live runs; neither is cancelled, and a follow-up carrier conforms the code after the revise. bd-ib-so6fef's rider and bd-ib-qshcwc's 578a981c2 acceptance case already grade against this amended rule.

### Proposed Changes

In SPECIFICATION/contracts.md, §"Factory-configurable ACP fallback priority", in the paragraph that opens **A needs-human tree is recognised by the run it carries, not only by its ref name.**, replace the sentence

> When several needs-human refs carry the same run, routing MUST prefer the one named under one of the item's run identifiers, and otherwise the one whose tip commit is newest by committer time.

with

> When several needs-human refs carry the same run, routing MUST take the ref whose tip commit descends from the tip commit of every other ref carrying that run, where a commit descends from itself. When no tip descends from all the others, routing MUST take the ref whose tip commit is newest by committer time. Only when two or more refs remain tied because their tips are the same commit MAY the ref's name decide: routing MUST then prefer a ref named under one of the item's earlier-run identifiers, and among equally named candidates the ref whose full name sorts first in byte order. Ancestry MUST be read from the same per-pass identification as the tip commit messages; an ancestry that cannot be read is the existing unobservable-measurement hold and MUST NOT be read as the absence of a descendant. Every carrying ref the route did not take MUST still be listed in `passed_over_needs_human` as this paragraph states.

In SPECIFICATION/scenarios.md, inside the gherkin block under `## Scenario 185 — A released item's recovery route is decided before admission and executed per item, and a deferred item keeps its branch`, replace the two scenarios

```gherkin
  Scenario: Of two needs-human refs carrying one run, the one named under a run identifier is taken
    Given an earlier run U of the item carried by needs-human/U and by needs-human/A
    When the Dispatcher grades the item's recovery route
    Then the route is seeded from needs-human/U
    And the recovery-route record lists needs-human/A in passed_over_needs_human

  Scenario: Of two needs-human refs carrying one run under other names, the newer tip is taken
    Given an earlier run U of the item carried by needs-human/A and needs-human/B and by no ref named under a run identifier
    And B's tip commit is newer by committer time than A's
    When the Dispatcher grades the item's recovery route
    Then the route is seeded from needs-human/B
```

with

```gherkin
  Scenario: Of two needs-human refs carrying one run, the tip that descends from the other is taken whatever the refs are named
    Given an earlier run U of the item carried by needs-human/U at commit S1 and by needs-human/A at commit S2
    And S2 descends from S1
    When the Dispatcher grades the item's recovery route
    Then the route is seeded from needs-human/A at S2
    And the recovery-route record lists needs-human/U with S1 in passed_over_needs_human

  Scenario: Of two needs-human refs carrying one run on diverged tips, the newer tip is taken
    Given an earlier run U of the item carried by needs-human/A and needs-human/B
    And neither tip commit descends from the other
    And B's tip commit is newer by committer time than A's
    When the Dispatcher grades the item's recovery route
    Then the route is seeded from needs-human/B

  Scenario: Of two needs-human refs carrying one run at the same commit, the one named under a run identifier is taken
    Given an earlier run U of the item carried by needs-human/U and by needs-human/A, both at commit S
    When the Dispatcher grades the item's recovery route
    Then the route is seeded from needs-human/U at S
    And the recovery-route record lists needs-human/A with S in passed_over_needs_human

  Scenario: A run-id-named ancestor does not outrank a dispatch-id-named descendant of the same run
    Given bd-ib-ofvsr3's earlier run 01M6S83KZH54MR6N8NECJN86Z8 carried by needs-human/01M6S83KZH54MR6N8NECJN86Z8 at d7f0102e1 and by needs-human/4d5104454d7b406a80014d6d2acc139e at 578a981c2
    And both tip commits hold the trailer Fabro-Run: 01M6S83KZH54MR6N8NECJN86Z8
    And 578a981c2 descends from d7f0102e1
    When the Dispatcher grades bd-ib-ofvsr3's recovery route
    Then the route is seeded from needs-human/4d5104454d7b406a80014d6d2acc139e at 578a981c2
    And the recovery-route record lists needs-human/01M6S83KZH54MR6N8NECJN86Z8 with d7f0102e1 in passed_over_needs_human

  Scenario: An unreadable ancestry between refs carrying one run holds the route, even when one is named under a run identifier
    Given an earlier run U of the item carried by needs-human/U and by needs-human/A on different tip commits
    And whether either tip descends from the other cannot be read
    When the Dispatcher grades the item's recovery route
    Then the route is held and the recovery-held record names that measurement
    And the route is not seeded from needs-human/U
```

The change MUST NOT add, rename or remove any `## ` heading, so `tests/heading-coverage.json` needs no edit.
