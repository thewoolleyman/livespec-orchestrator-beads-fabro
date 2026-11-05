---
topic: a-plain-dispatch-has-no
author: claude-opus-5-5
created_at: 2026-11-05T15:55:04Z
---

## Proposal: A ruled seed ref is carried to the next dispatch, and routing refuses it by name rather than passing it over

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Give recovery routing one sanctioned input through which an operator or coordinator ruling names the preserved tree, as a ref plus its commit SHA, that an item's next dispatch must start from. The ruling is written by a new Dispatcher subcommand as a marked ledger comment and a journal row. Routing honours the current ruling ahead of a resume and ahead of its own preference order. When the named ref is absent or no longer at the named SHA, routing holds the item with a cause naming the ref, and never falls through to an older tree or to fresh. Exactly one launched dispatch consumes a ruling.

### Motivation

Work item bd-ib-ltlg4i (filed 2026-11-04 by the anthropic-burn-mitigation seat; adopted 2026-11-05 by plan publish-draft-green-work-loss, epic bd-ib-acrr56, on coordinator legacy-coordinator-agent ruling R301). Recovery routing chooses an item's seed itself, from the item's journaled run identifiers, in the clause's fixed preference order. No surface carries a ruling that names a specific tree, so rulings are written as item comments that routing never reads, and the dispatch silently takes another tree. Measured instances:

- 2026-11-05, bd-ib-abbb3j. The ruled seed was 9898f741b, a janitor-ready Red+Green tree, hand-aliased at refs/heads/needs-human/6805847ab3c94cde8f5cd10a09fb7bc0. Routing never read the alias. At 15:42:40Z its recovery-route row seeded from refs/livespec/preserved-publish/bd-ib-abbb3j/1e219d3c4079..., the item's oldest attempt, which an earlier triage had ruled reference-only and which sat on a stale base. Run 01M6P62T6XV0 launched on it and had to be cancelled by hand at about 15:48Z.
- 2026-11-05, bd-ib-hap62u. The ruled seed dac6da8b, aliased at refs/heads/needs-human/4e601a2e..., was likewise unread, and the item routed fresh at 15:42:04Z.
- 2026-11-04, bd-ib-nesy77. A ruling to seed from refs/heads/needs-human/64c73cf3... (ac50799a1, about 166 added test lines) routed fresh at 05:53:36Z, and run 01M6JJ1BEK8X's tree lacked those tests.
- 2026-11-04, bd-ib-ff5ohb. After the two-resume cap a plain dispatch was ruled to carry commits c69d01701 and f07320511 from a backup ref. Only a rider comment carried that ruling.

The same day, four further items (bd-ib-d2qm5d, bd-ib-welwbc, bd-ib-dznxgv, bd-ib-rhivsm) were caught before launch only because a peer session read the routing code. The coordinator ruled the two assertions this proposal carries: routing refuses with a named cause instead of falling through when a ruled seed ref would not be read; and a needs-human ref holding the item's work is honoured or reported, never silently ignored. The second is the companion proposal in this file. The anthropic-burn-mitigation seat confirmed its earlier hold on bd-ib-ltlg4i was procedural, with no objection to this direction.

In-flight alignment: this aligns with the pending proposal a-plain-re-dispatch-of, which widens the release condition of the same paragraph. That proposal decides WHICH items are released, and this one decides WHICH tree a released item's seed is taken from. No sentence is edited by both.

### Proposed Changes

**1. `SPECIFICATION/contracts.md`, §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work".** Insert the following paragraph immediately after the paragraph that opens "The seed record MUST name the source run, remote, immutable commit SHA, and preservation reference.", leaving every existing sentence unchanged.

> **A ruled seed names the tree a released item's next dispatch starts from.** An operator or a delegated coordinator MAY rule that an item's next dispatch start from a named preserved tree by running `dispatcher.py seed-ruling --repo <path> --item <id> --ref <ref> --sha <commit-sha> --reason <text>`. `<ref>` MUST be a full ref name on the item's repository, and `<commit-sha>` MUST be a full 40-character commit id. The command MUST verify, by one remote read, that `<ref>` exists at `<commit-sha>`. When it does, the command MUST write one ledger comment on the item that opens with the marker line `livespec-seed-ruling` and names the ref, the commit SHA, the invoker, the reason and the UTC instant, and MUST journal one `seed-ruling` record carrying the same fields. When the ref is absent or stands at a different commit, it MUST refuse (exit `3`) naming the ref, the expected commit and the observed one, and MUST write nothing. A ruling is CURRENT from the instant it is written until a dispatch consumes it or a later ruling for the same item replaces it. The latest ruling governs. While an item carries a current ruling, recovery routing MUST treat the item as released for recovery, and MUST take its seed from the ruling ahead of a `resume` and ahead of the preference order this clause states. When the ruled ref exists at the ruled SHA and no non-fallback refusal applies, the route MUST be `seeded`, and the seed record MUST name the ruled ref as its preservation reference and the ruled SHA as its immutable commit. When the ruled ref is absent, or stands at a commit other than the ruled SHA, the route MUST be `held`, and the `recovery-held` record MUST name the ref, the ruled SHA and the observed commit (or its absence). Routing MUST NOT fall through to another preserved tree, to the observed published head, or to `fresh`. An unreadable ref is the existing unobservable-measurement hold. A non-fallback refusal keeps its precedence over a ruling. The dispatch that launches seeded from a ruling MUST journal one `seed-ruling-consumed` record naming the ruling's instant and the run id, and a consumed ruling MUST NOT govern any later dispatch. The `resume` precedence stated above applies only when no ruling is current.

**2. `SPECIFICATION/scenarios.md`, `## Scenario 185 — A released item's recovery route is decided before admission and executed per item, and a deferred item keeps its branch`.** Append these scenarios at the end of its existing gherkin fence. No `## ` heading is added or changed, so `tests/heading-coverage.json` MUST NOT need an edit for this finding.

```gherkin
  Scenario: A dispatch honours a current seed ruling ahead of the automatic preference order
    Given an item resting ready whose earlier run left an older preserved-publish ref P
    And a seed ruling names ref R at commit S for that item, and R exists on origin at S
    When the Dispatcher next dispatches the item
    Then its recovery route is seeded with R as the preservation reference and S as the immutable commit
    And its sandbox checks out S, not P's commit
    And the journal carries one seed-ruling-consumed record naming the ruling and the run

  Scenario: A seed ruling whose ref moved or vanished holds the item by name
    Given an item resting ready that carries a current seed ruling naming ref R at commit S
    And R is absent on origin, or stands at a commit other than S
    When the Dispatcher next grades the item's recovery route
    Then the route is held and no run is launched
    And the recovery-held record names R, S and the commit observed at R, or R's absence
    And the item is not seeded from any other preserved tree and is not routed fresh

  Scenario: A consumed seed ruling does not govern a later dispatch
    Given a dispatch launched seeded from a seed ruling and journaled seed-ruling-consumed
    When the item is later released for recovery again with no newer ruling
    Then its recovery route is graded by the clause's ordinary order without that ruling
```

## Proposal: A needs-human ref holding an item's work is honoured or reported, never silently ignored

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Recovery routing finds a run's terminal tree only at needs-human/<earlier run id>. A needs-human ref holding the same run's tree under any other name is never read, so routing silently takes an older tree or routes fresh. Routing must also recognise a needs-human ref by the run its tip commit names, through the engine checkpoint trailer `Fabro-Run: <run id>` or the `Factory-Run-Id: <id>` trailer. It honours such a ref as that run's terminal tree, and names every such ref it passed over in the recovery-route record.

### Motivation

The same 2026-11-05 measurements as the companion proposal. bd-ib-abbb3j's alias refs/heads/needs-human/6805847a... held tree 9898f741b, whose tip commit carries the trailer `Fabro-Run: 01M6N7XWBTQDVFF2J4700P1WPD`, a run id routing already holds for the item. Because the ref was not NAMED under that id, `_needs_human_seed` never asked for it, and routing fell through to the oldest preserved-publish ref. bd-ib-hap62u's alias was likewise unread, and the item routed fresh. Nothing in the recovery-route record said a needs-human tree for the item existed and was passed over, so the loss was found only by a peer reading the routing code. The interim remedy, renaming each alias under the source run's id, works only for operators who know the naming rule. The coordinator ruled the requirement: such a ref is either honoured or reported, never silently ignored.

### Proposed Changes

**1. `SPECIFICATION/contracts.md`, §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work".** Insert the following paragraph immediately after the ruled-seed paragraph that the companion proposal adds, or, when that proposal is rejected, immediately after the paragraph that opens "The seed record MUST name the source run, remote, immutable commit SHA, and preservation reference.".

> **A needs-human tree is recognised by the run it carries, not only by its ref name.** A needs-human ref is any ref under `refs/heads/needs-human/`. A needs-human ref CARRIES a run when its tip commit's message holds a `Fabro-Run: <run id>` trailer or a `Factory-Run-Id: <id>` trailer naming one of the earlier-run identifiers routing holds for the item. When routing looks for a run's terminal tree, it MUST treat every needs-human ref that carries that run as the run's terminal tree, exactly as it treats `needs-human/<run id>`. When several needs-human refs carry the same run, routing MUST prefer the one named under one of the item's run identifiers, and otherwise the one whose tip commit is newest by committer time. The identification MUST take a bounded number of forge reads per routing pass, independent of how many items the pass routes. An identification that cannot be taken is the existing unobservable-measurement hold and MUST NOT be read as absence. Every `recovery-route` record of a `seeded`, `fresh` or `resume` route MUST carry a `passed_over_needs_human` field listing each needs-human ref that carries one of the item's earlier runs and was not the ref the route took, with its commit. The field MUST be an empty list when there is none, and MUST NOT be omitted.

**2. `SPECIFICATION/scenarios.md`, `## Scenario 185 — A released item's recovery route is decided before admission and executed per item, and a deferred item keeps its branch`.** Append these scenarios at the end of its existing gherkin fence, after those of the companion proposal when both are accepted. No `## ` heading is added or changed, so `tests/heading-coverage.json` MUST NOT need an edit for this finding.

```gherkin
  Scenario: A needs-human ref named outside the run id is honoured as the run's terminal tree
    Given an item released for recovery whose earlier run has run id U
    And no ref needs-human/U exists, while ref needs-human/A's tip commit carries the trailer Fabro-Run: U
    And the item also has an older preserved-publish ref P
    When the Dispatcher grades the item's recovery route
    Then the route is seeded with needs-human/A as the preservation reference and its tip as the immutable commit
    And the route is not seeded from P and is not fresh

  Scenario: A recovery route names every needs-human tree it passed over
    Given an item released for recovery whose route resumes its published pull request
    And needs-human ref N's tip commit carries the trailer Fabro-Run naming one of the item's earlier runs
    When the Dispatcher journals the item's recovery-route record
    Then the record's passed_over_needs_human field lists N with its commit

  Scenario: An unreadable needs-human identification holds rather than routing fresh
    Given an item released for recovery for which no needs-human ref is named under a run id
    And the forge read that identifies needs-human refs by their tip commit cannot be taken
    When the Dispatcher grades the item's recovery route
    Then the route is held and the recovery-held record names that measurement
```
