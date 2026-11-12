---
topic: a-ruled-seed-s-recovery
author: claude-opus-5-5
created_at: 2026-11-12T16:00:00Z
---

## Proposal: A ruled seed's source run is the run that wrote the ruled ref, or reads unobservable; never the item's earliest run

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The ruled-seed paragraph requires the seed record to name the ruled ref and the ruled SHA. The seed-record sentence requires every seed to name a source run. Neither says WHICH run a ruled seed names, and today routing names the item's earliest run, which is a run whose tree the seed does not carry. This proposal requires a ruled seed to name the run that wrote the ruled ref. When no record identifies that run, the source run reads unobservable with its cause. The seed's commit and preservation reference are unchanged in both cases.

### Motivation

Work item bd-ib-6jo7an (plan bd-ib-ax3rds). It is held at spec-change tier for this linked stem: verdict partial, spec 360, generalization target `## Factory-configurable ACP fallback priority`. The topic is the item's linked stem, so the hold links without a relink.

Observed by this plan's seat and REPRODUCED by legacy-dispatcher-agent (session ef2a1927) on 2026-11-12, on bd-ib-mztpy7:
- The seed ruling was written at 09:57:08Z, at `refs/heads/needs-human/3fc9d3d79d1742e1868061cc4fd21e6f` @ `b123e78851510efde8b0f86b53f6ad81536944a0`.
- Every commit on that ref is titled `fabro(01M772BDECHN72Y6VP4D4AC3EK): …`, and the dispatch journal stamps dispatch `3fc9d3d79d17` with run `01M772BDECHN` at 05:06:50Z.
- The route reader nonetheless reports `RecoverySeed source_run_id=01M6NKWGB8H8`, mztpy7's FIRST run (stamped 2026-11-05T10:26:27Z). The seeded commit is correct; only the attribution is wrong.

Cause, measured on build 58fb211b056e: `_dispatcher_recovery_ruled_seed.py:158` builds the seed with `source_run_id=leading_identifier(identifiers=earlier_run_ids)`, the earliest run, and never asks which run wrote the ruled ref. The ref's own name carries a 32-hex dispatch id, and the dispatch journal maps that id to its run, so the writing run is derivable. Whatever reads a seed's source run is then pointed at a run whose tree the seed does not carry: preserved-work attribution, the across-dispatch required-result progress, and triage.

Design choices, stated for the grade:
- **Two sources, in order.** The first is the journal's run stamp for the dispatch id the ref's name carries. That is the measured case, and it needs no extra read. The second is the run the ref carries under the existing "A needs-human tree is recognised by the run it carries" paragraph: its tip's `Fabro-Run:` or `Factory-Run-Id:` trailer. That paragraph's identification is already taken once per routing pass, so the fallback adds no read.
- **Unobservable, never a guess.** When neither identifies a run, the record says so with its cause rather than naming any of the item's runs. A wrong source run is worse than a declared unknown, because every reader trusts it.
- **Attribution only.** Neither choice changes the seeded commit, the preservation reference, or the route.

Adjacent but different: bd-ib-i6wxdw ("Recovery routing seeds from an earlier run's needs-human ancestor") concerns WHICH TREE is seeded, not attribution. In-flight alignment, all `align`: #5054, #5058 and #5060 touch neither recovery routing nor seed records. Fleet scope: recovery routing is the orchestrator Dispatcher's, so every tenant it drives inherits the change.

### Proposed Changes

**1. A ruled seed's source run (`contracts.md` §"Factory-configurable ACP fallback priority", the paragraph "A ruled seed names the tree a released item's next dispatch starts from.").** After the sentence "When the ruled ref exists at the ruled SHA and no non-fallback refusal applies, the route MUST be `seeded`, and the seed record MUST name the ruled ref as its preservation reference and the ruled SHA as its immutable commit.", add:

> The seed record's source run MUST be the run that wrote the ruled ref. It is the run the dispatch journal stamps for the dispatch id the ref's name carries, when the ref is named under `needs-human/` and a journaled dispatch of the item stamps that id. Otherwise it is the run the ref carries, as the paragraph "A needs-human tree is recognised by the run it carries, not only by its ref name" defines it, read from that paragraph's per-pass identification. When neither identifies a run, the source run MUST read unobservable, naming the cause, and MUST NOT name any other of the item's runs, its earliest run included. The source run never changes the seed's commit, its preservation reference, or the route.

**2. Scenario (`scenarios.md`).** Append the scenario below. Its number is the next free one at revise time; 350 to 360 are claimed by pending proposals and peer drafts.

## Scenario 361 — A ruled seed names the run that wrote the ruled ref as its source run

```gherkin
Feature: a ruled seed is attributed to the run whose tree it carries
  Scenario: the ruled ref's writing run is the source run, not the earliest run
    Given an item whose earlier runs are an older run A and a newer run B
    And a current seed ruling names a needs-human ref, named under the dispatch id the journal stamps with run B, at its tip commit
    When recovery routing routes the item
    Then the route is seeded
    And the seed record names run B as its source run
    And the seed record names the ruled ref and the ruled commit unchanged

  Scenario: a ref with no journaled dispatch is attributed by the run it carries
    Given a current seed ruling on a needs-human ref whose name matches no journaled dispatch of the item
    And the ref's tip commit carries a Fabro-Run trailer naming one of the item's earlier runs
    When recovery routing routes the item
    Then the seed record names that run as its source run

  Scenario: an unidentifiable writing run reads unobservable
    Given a current seed ruling on a ref that no journaled dispatch of the item names and that carries none of the item's runs
    When recovery routing routes the item
    Then the seed record's source run reads unobservable, naming the cause
    And it names none of the item's runs
    And the seed record names the ruled ref and the ruled commit unchanged
```

**3. Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new scenario heading. The row is carried through `resulting_files[]` with the path spelled `../tests/heading-coverage.json`, or edited directly in that commit, with `test: "TODO"`, `work_item: "bd-ib-6jo7an"`, and a non-empty `reason` naming integration or above as the owed test's tier. It also adds one matching `tests/heading-coverage-debt.json` entry. If the revise renumbers Scenario 361, the row and entry MUST carry the renumbered heading text.
