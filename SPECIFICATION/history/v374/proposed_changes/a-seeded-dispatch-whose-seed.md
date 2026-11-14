---
topic: a-seeded-dispatch-whose-seed
author: claude-opus-5-5:factory-run-work-preservation
created_at: 2026-11-12T10:50:21Z
---

## Proposal: A seed taken from the item's own publish branch is read from the reclaim's preservation ref

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Two clauses meet head-on when a dispatch routed `seeded` takes its seed from the item's own publish branch. §"Factory-configurable ACP fallback priority" → "A ruled seed names the tree a released item's next dispatch starts from" makes the seed record name the ruled ref as its preservation reference. §"Stale publish-branch reclaim before a re-dispatch" makes the same dispatch preserve that branch's head at `refs/livespec/preserved-publish/<work-item-id>/<head>` and then delete the branch, before the run exists. No clause says which ref a later read of the seed uses, so the run fetches a ref its own dispatch already deleted, and fails at seed checkout. This proposal adds one paragraph after the ruled-seed paragraph. For such a dispatch the seed record MUST name the reclaim's preservation ref as its preservation reference, keeping the seed commit as its immutable commit. Every later read of the seed commit for that dispatch — the sandbox's seed fetch and any host-side read — MUST read it from that preservation ref. A preservation ref that does not stand at the seed commit holds the item by name, exactly as a moved ruled ref does. Three scenarios in Scenario 185 exercise it.

### Motivation

Owning work item bd-ib-anou6d, "A seeded dispatch whose seed ref is the item's own publish branch fetches that branch after the same dispatch's reclaim deleted it, so the run fails at seed checkout", under plan factory-run-work-preservation (epic bd-ib-nckst7, plan assertion 2). legacy-coordinator-agent (session 245a3c34) approved it at 2026-11-12T10:42Z and reverted it to backlog, because its spec-change-tier judgement holds it as partial for this topic at spec v360. The coordinator directed this seat to author the resolution as a draft for grade: when the ruled ref is the item's own publish branch, the seed record names the reclaim's preserved-publish ref, and the seed is fetched from it.

Measured on bd-ib-ngyfmi (legacy-dispatcher-agent, session ef2a1927):
- A seed ruling named refs/heads/feat/bd-ib-ngyfmi at b9c572d0e194242c9117a502831ba925b8dc60d0, the head of open draft PR #5023. The route read seeded.
- The dispatch launched at 10:19:42Z. Its reclaim closed PR #5023 and deleted the branch at 10:24:55Z. Run 01M77MN6B1NAG6B330M0F80Y4D was listed at 10:25:46Z.
- The run failed at 10:28:01Z with `LIVESPEC_SETUP_STEP_FAILED: run_prepare_51`, category deterministic. That step was `git fetch --no-tags origin refs/heads/feat/bd-ib-ngyfmi && git checkout --detach b9c572d0e`.
- This seat's ls-remote at about 10:40Z shows refs/livespec/preserved-publish/bd-ib-ngyfmi/b9c572d0e194242c9117a502831ba925b8dc60d0 at that same commit, and the feat branch absent. The reclaim did preserve the head; only the seed's read target was wrong.

The interim seat rule agreed by the coordinator is never to seed from an item's own feat/ branch. That rule is the remedy this paragraph retires.

In-flight survey (2026-11-12 about 10:50Z): the nine remote spec/* branches and the two open spec-touching pull requests (#5031 the-spec-change-tier-judgement, #5005 a-needs-human-rest-overwrites) touch neither the ruled-seed paragraph nor the reclaim. Two pending in-tree proposals overlap, and this one aligns with both:
- a-stale-seed-is-rebased-before-it-runs: its item 1b rewrites the ruled-seed sentence and its new paragraph rebases a seed host-side. This proposal leaves that sentence untouched, so the two edits do not collide. It anchors at a different place: after the whole ruled-seed paragraph. Its "every later read" rule covers a host-side rebase read of the seed as well as the sandbox fetch.
- a-plain-re-dispatch-of: it decides which items are released for recovery, not where a seed is read from.

### Proposed Changes

1. contracts.md, §"Factory-configurable ACP fallback priority": IMMEDIATELY AFTER the paragraph that begins "**A ruled seed names the tree a released item's next dispatch starts from.**" and ends "The `resume` precedence stated above applies only while no ruling is current.", and BEFORE the paragraph that begins "**A fresh ruling routes a released item's next dispatch fresh.**", insert this paragraph, separated from each by one blank line:

"**A seed taken from the item's own publish branch is read from the reclaim's preservation ref.** This paragraph governs a dispatch routed `seeded` whose seed ref is the item's own publish branch, whether a current seed ruling names that branch or the preference order above selected the observed published head on it, when the stale publish-branch reclaim of §"Stale publish-branch reclaim before a re-dispatch" preserves and deletes that branch for the same dispatch. For such a dispatch, the seed record MUST name the preservation ref that reclaim wrote, `refs/livespec/preserved-publish/<work-item-id>/<head>`, as its preservation reference, in place of the publish branch. This holds notwithstanding the ruled-seed paragraph's requirement that the seed record name the ruled ref. The seed record MUST keep the seed's commit as its immutable commit, and MUST also name the publish branch the seed was selected from. Every read of the seed commit for that dispatch that follows the reclaim — the run's seed fetch and checkout in its sandbox, and any host-side read of the seed — MUST read it from that preservation ref, and MUST NOT name the deleted publish branch. Before the run is launched, the Dispatcher MUST verify, by the reclaim's own remote read or by one further remote read, that the preservation ref stands at the seed commit. When it does not, the run MUST NOT be launched, and the item MUST be routed `held` exactly as an item whose ruled ref moved is held: the `recovery-held` record MUST name the preservation ref, the seed commit and the commit observed at the preservation ref. A current seed ruling MUST then stay current. When the reclaim held and left the publish branch in place, the seed MUST be read from the publish branch as the preceding paragraphs state. The dispatch MUST consume a seed ruling it was seeded from exactly as the ruled-seed paragraph requires, whichever ref it read the seed from. Scenario 185 in `scenarios.md` exercises this paragraph."

No other paragraph of the section changes. In particular, the ruled-seed paragraph's own sentences, including "the seed record MUST name the ruled ref as its preservation reference and the ruled SHA as its immutable commit", stay as they are.

2. scenarios.md, §"Scenario 185 — A released item's recovery route is decided before admission and executed per item, and a deferred item keeps its branch": inside that section's gherkin block, insert these three scenarios IMMEDIATELY AFTER `Scenario: A consumed seed ruling does not govern a later dispatch` (whose last step is "Then its recovery route is graded by the clause's ordinary order without that ruling") and BEFORE `Scenario: A needs-human ref named outside the run id is honoured as the run's terminal tree`, each separated from its neighbours by one blank line:

```gherkin
  Scenario: A seed ruled on the item's own publish branch is read from the reclaim's preservation ref
    Given an item resting ready whose earlier run's publish branch feat/<item> stands on origin at commit S with no live run
    And a livespec-seed-ruling comment on the item names refs/heads/feat/<item> at S
    When the Dispatcher next dispatches the item
    Then the stale publish-branch reclaim preserves S at refs/livespec/preserved-publish/<item>/S and deletes feat/<item>
    And the seed record names refs/livespec/preserved-publish/<item>/S as its preservation reference and S as its immutable commit
    And the run's sandbox fetches S from refs/livespec/preserved-publish/<item>/S and checks out S
    And the item carries one livespec-seed-ruling-consumed comment naming the ruling and the run

  Scenario: A seed taken from the observed published head is read from the reclaim's preservation ref
    Given an item released for recovery whose route is seeded from the observed published head S on its publish branch feat/<item>
    When the Dispatcher dispatches the item and the reclaim preserves S and deletes feat/<item>
    Then the seed record names refs/livespec/preserved-publish/<item>/S as its preservation reference
    And the run's sandbox fetches S from that preservation ref, not from feat/<item>

  Scenario: A preservation ref that does not stand at the seed commit holds the item
    Given an item routed seeded from its own publish branch at commit S
    And the reclaim's preservation ref for the dispatch stands at a commit other than S
    When the Dispatcher verifies the preservation ref before launch
    Then no run is launched and the item is routed held
    And the recovery-held record names the preservation ref, S and the commit observed at the preservation ref
    And a current seed ruling for the item stays current
```

No H2 heading is added, removed or renamed, so `tests/heading-coverage.json` needs no co-edit.
