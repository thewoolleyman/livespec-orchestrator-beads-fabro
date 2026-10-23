---
topic: fresh-dispatch-ignores-recorded-factory
author: claude-opus-5-5:fabro-currency
created_at: 2026-10-23T13:06:47Z
---

## Proposal: A recorded factory pins only a resume; a fresh dispatch goes to the current default

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Restrict the recorded-factory step of the factory selection order to a dispatch whose route is resume: an explicit resume --item, or a dispatch or loop pass whose recovery routing routes the item resume. Those are the only dispatches that continue the run lineage the recorded factory belongs to. Every other dispatch is a fresh dispatch: it ignores the item's recorded factory and goes to the repository's current dispatcher.default_factory, or through factory overflow selection, unless an explicit --factory or LIVESPEC_FABRO_FACTORY selects a factory.

### Motivation

After the petri cutover moved every repository's dispatcher.default_factory from legacy to petri, any item that ever ran on hp still routes back to hp on its next fresh dispatch. The ratified order in contracts.md, Factory addresses resolved from a host registry (explicit --factory, then LIVESPEC_FABRO_FACTORY, then the item's recorded factory, then overflow selection or the default), puts the recorded factory ahead of the default for EVERY dispatch. Measured 2026-10-23T08:12:33Z: tdd-proof-lv352h (tenant default_factory petri), launched with no factory pinned, resolved --server https://hp-xubuntu.perch-rudd.ts.net:32276 because its metadata recorded legacy from earlier run 01M5FF8M02TN. A read-only fleet count at about 08:40Z found 15 non-closed items across 7 tenants that record legacy. Moving the default therefore does not move these items, which defeats the assertion of plan petri-factory-on-gmktec (epic bd-ib-fyozyd) that no repository resolves to hp, and it leaves pinning as the only route to a default-routing proof, which proves a pin instead. The fleet coordinator ruled (2026-10-23 08:4xZ, relaying the maintainer's cutover direction) that a recorded factory binds only a rework of the same run lineage, never a fresh dispatch, and rejected removing legacy from the factory tables early, because R668 keeps legacy declared as the rollback through the bd-ib-iud52v soak to 2026-10-28T17:31Z. The run lineage a recorded factory belongs to is continued by exactly one route: resume, which finishes the earlier run on its published pull request, whether an operator invokes resume --item or recovery routing (Factory-configurable ACP fallback priority, Recovery from the failed run's preserved work) routes a released item resume inside dispatch or loop. The classification is therefore by route, not by command: dispatch --item, the drive action impl, and a loop drain each carry a resume when recovery routing chose one. Every other route starts a new run at implement, from a sandbox that needs nothing the earlier factory holds. That includes the seeded route, because the preserved work it seeds from lives on a forge ref. Work-item bd-ib-2b2uqa.

### Proposed Changes

Whitespace note: every quoted target below is literal text of the current file. A reviser MAY match it with line wrapping normalized (runs of whitespace, including line breaks, compared as one space).

1. SPECIFICATION/contracts.md, section "Factory addresses resolved from a host registry", the paragraph beginning "The registry refusal applies only to resolving a DECLARED, registry-backed entry". Replace this sentence:

"Neither changes the factory selection order: an explicit `--factory` is taken first, then `LIVESPEC_FABRO_FACTORY` when it is set and non-empty; then the item's recorded factory; then factory overflow selection (§"Factory overflow selection") when `dispatcher.overflow_factories` is non-empty, and otherwise `dispatcher.default_factory`."

with:

"Neither changes the factory selection order: an explicit `--factory` is taken first, then `LIVESPEC_FABRO_FACTORY` when it is set and non-empty; then, for a resume only, the item's recorded factory; then factory overflow selection (§"Factory overflow selection") when `dispatcher.overflow_factories` is non-empty, and otherwise `dispatcher.default_factory`. A *resume* here is a dispatch whose route is `resume`: an invocation of §"Resume from a published pull request (`resume --item`)", or a `dispatch` or `loop` pass whose recovery routing (§"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work") routes the item `resume`. It is the one route that continues the run lineage the item's recorded factory belongs to. Every other dispatch is a FRESH dispatch, whatever entry point carries it: a `dispatch --item`, a `drive` action `impl:<id>` or a loop drain whose item recovery routing routes `seeded` or `fresh`, an item not released for recovery, and an item reopened for rework. The classification is per item and per pass, so one loop wave may carry a resume beside fresh dispatches. A fresh dispatch MUST NOT read the item's recorded factory as a pin. When no explicit selection is made it MUST proceed as an unpinned dispatch, so changing `dispatcher.default_factory` re-routes the next fresh dispatch of every item onto the new default factory, or through factory overflow selection when it is configured. The admission claim stamp MUST apply the same order, using the route recovery routing assigned before the admission valve, so a fresh dispatch is stamped with the factory it will reach and a resume with the factory selected by that same order. Every dispatch MUST still write the item's dispatch-factory record, and every surface that locates an item's live or earlier run through that record or through the run's own recorded target MUST keep reading it unchanged: the reconcile survey, a liveness read, the claim stamp's run target, adapter launch evidence, the acceptance pass, and a resume's read of its earlier run."

2. Same paragraph, the next sentence. Replace:

"A recorded factory name that `dispatcher.factories` no longer declares keeps its existing treatment: when no explicit selection is made it is ignored and the dispatch proceeds as an unpinned one, so renaming a factory re-routes the later unpinned dispatches of every item that recorded the old name onto the default factory, or through factory overflow selection when it is configured."

with:

"A recorded factory name that `dispatcher.factories` no longer declares keeps its existing treatment for a resume: when no explicit selection is made it is ignored and the resume proceeds as an unpinned one, so renaming a factory re-routes the later resumes of every item that recorded the old name onto the default factory, or through factory overflow selection when it is configured."

3. SPECIFICATION/contracts.md, section "Factory overflow selection". Replace:

"Overflow selection applies ONLY to a dispatch, including a resume, that has no explicit `--factory`, no non-empty `LIVESPEC_FABRO_FACTORY`, and no recorded factory that `dispatcher.factories` still declares."

with:

"Overflow selection applies ONLY to a dispatch that has no explicit `--factory` and no non-empty `LIVESPEC_FABRO_FACTORY`, and that is either a fresh dispatch or a resume carrying no recorded factory that `dispatcher.factories` still declares (§"Factory addresses resolved from a host registry")."

In the same section replace "so that a later resume, reconcile or acceptance pass of the same dispatch follows it." with "so that a later resume, reconcile or acceptance pass of the same dispatch follows it; a later fresh dispatch of the item does not."

4. SPECIFICATION/contracts.md, section "Resume from a published pull request (`resume --item`)", paragraph "What a resume does". Replace:

"resolve its factory as `dispatch --item` does (the selection order of §"Factory addresses resolved from a host registry", including `LIVESPEC_FABRO_FACTORY` and factory overflow selection)"

with:

"resolve its factory through the selection order of §"Factory addresses resolved from a host registry", taking that order's resume-only recorded-factory step, and including `LIVESPEC_FABRO_FACTORY` and factory overflow selection"

5. SPECIFICATION/scenarios.md, Scenario 182 (heading unchanged), gherkin case "Switching the default instance renames nothing". Replace its final line "And the item recorded to "petri" is dispatched to "petri"" with these lines:

    And the item recorded to "petri" is dispatched to "next", because a fresh dispatch reads no recorded factory
    And when the item recorded to "petri" is instead resumed with resume --item, the resume is dispatched to "petri"

6. SPECIFICATION/scenarios.md, Scenario 203 (heading unchanged). In the gherkin case "A pinned dispatch reads no capacity and journals no selection", replace the Given line with:

  Given the dispatch is invoked with --factory "A", or LIVESPEC_FABRO_FACTORY names "A", or the item's route is resume and its recorded factory is "A"

Then append these cases to the same gherkin block:

Scenario: A fresh dispatch ignores the item's recorded factory
  Given dispatcher.default_factory names factory "A" and dispatcher.overflow_factories is empty
  And dispatcher.factories declares factories "A" and "B"
  And the item's recorded factory is "B" from an earlier run
  And the item is not released for recovery, as for an item reopened for rework
  And no explicit factory is selected
  When the Dispatcher dispatches the item with dispatch --item, the drive action impl, or a loop drain
  Then the admission claim stamp names factory "A"
  And the run is submitted to factory "A"
  And the item's dispatch-factory record names factory "A"

Scenario: An explicit resume keeps the item's recorded factory
  Given the same configuration and the item's recorded factory is "B"
  And no explicit factory is selected
  When the Dispatcher resumes the item with resume --item
  Then the resumed run is submitted to factory "B"
  And no overflow-selection journal record is written

Scenario: A recovery-routed resume keeps the item's recorded factory
  Given the same configuration and the item's recorded factory is "B"
  And the item is released for recovery and recovery routing routes it resume
  And no explicit factory is selected
  When the Dispatcher dispatches the item with dispatch --item or a loop drain
  Then the admission claim stamp names factory "B"
  And the resumed run is submitted to factory "B"

Scenario: A seeded recovery dispatch goes to the default factory
  Given the same configuration and the item's recorded factory is "B"
  And the item is released for recovery and recovery routing routes it seeded
  And no explicit factory is selected
  When the Dispatcher dispatches the item
  Then the admission claim stamp names factory "A"
  And the seeded run is submitted to factory "A"

Scenario: One loop wave carries a resume and a fresh dispatch
  Given the same configuration
  And item "R" records factory "B" and recovery routing routes it resume
  And item "F" records factory "B" and is not released for recovery
  When one loop wave dispatches both items with no explicit factory
  Then item "R" is stamped with and submitted to factory "B"
  And item "F" is stamped with and submitted to factory "A"

Scenario: A fresh dispatch of a previously pinned item takes overflow selection
  Given dispatcher.default_factory names factory "A" and dispatcher.overflow_factories is ["B"]
  And the item's recorded factory is "A" from an earlier run
  And the item is not released for recovery
  And no explicit factory is selected
  When the Dispatcher dispatches the item with dispatch --item
  Then the Dispatcher reads both candidates' run counts and max_concurrent_runs
  And one overflow-selection journal record is written for the dispatch

No heading is added, renamed or removed, so tests/heading-coverage.json needs no change.
