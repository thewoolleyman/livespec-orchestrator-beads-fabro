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
- **The existing belonging rules, not a new order** (the coordinator's simpler fix). The source run is the run the ruled ref BELONGS to under the run-age bound's rules. Those rules already attribute every kind of ref `seed-ruling` accepts: a needs-human ref by its name or by the run it carries, a preserved-publish ref by its `livespec-preserved-tree` comment, and a work-in-progress capture by the run whose branch it preserves. That makes a `needs-human/<run-id>` ref with no trailer and a preserved-publish ref attributable, not unobservable. A needs-human ref named under a dispatch id belongs to the run the dispatch journal stamps for that id, which is the measured case.
- **Unobservable, never a guess.** When neither identifies a run, the record says so with its cause rather than naming any of the item's runs. A wrong source run is worse than a declared unknown, because every reader trusts it.
- **Attribution only.** Neither choice changes the seeded commit, the preservation reference, or the route.

Adjacent but different: bd-ib-i6wxdw ("Recovery routing seeds from an earlier run's needs-human ancestor") concerns WHICH TREE is seeded, not attribution. In-flight alignment, all `align`: #5054, #5058 and #5060 touch neither recovery routing nor seed records. Fleet scope: recovery routing is the orchestrator Dispatcher's, so every tenant it drives inherits the change.

### Proposed Changes

**1. A ruled seed's source run (`contracts.md` §"Factory-configurable ACP fallback priority", the paragraph "A ruled seed names the tree a released item's next dispatch starts from.").** After the sentence "When the ruled ref exists at the ruled SHA and no non-fallback refusal applies, the route MUST be `seeded`, and the seed record MUST name the ruled ref as its preservation reference and the ruled SHA as its immutable commit.", add:

> The seed record's source run MUST be the run the ruled ref belongs to under this clause's run-age bound. For a needs-human ref, that is the run its name names, either as a run id or as a dispatch id the dispatch journal stamps with its run, or else the run it carries under the paragraph "A needs-human tree is recognised by the run it carries, not only by its ref name". For a preserved-publish ref, it is the run its `livespec-preserved-tree` ledger comment names. For a work-in-progress capture ref, it is the run whose branch it preserves. When the ref belongs to no run under those rules, the source run MUST read unobservable, naming the cause, and MUST NOT name any other of the item's runs, its earliest included. The source run never changes the seed's commit, its preservation reference, or the route.

**2. The seed-record sentence (`contracts.md`, same section).** Change "The seed record MUST name the source run, remote, immutable commit SHA, and preservation reference." to:

> The seed record MUST name the source run, remote, immutable commit SHA, and preservation reference. A ruled seed's source run MAY instead read unobservable, as the ruled-seed paragraph states. Every reader of a seed's source run, including preserved-work attribution, the across-dispatch required-result progress of §"Across-dispatch required-result progress" and triage, MUST treat an unobservable source run as unknown. It MUST NOT attribute the seed's tree to any run, and MUST NOT read the unknown as a run that preserved no work.

**3. Scenario (`scenarios.md`).** Append the scenario below. Its number is the next free one at revise time; 350 to 360 are claimed by pending proposals and peer drafts.

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

  Scenario: a run-id-named needs-human ref with no trailer is attributed by its name
    Given a current seed ruling on needs-human/<run B's id> whose tip commit carries no run trailer
    When recovery routing routes the item
    Then the seed record names run B as its source run

  Scenario: a preserved-publish ref is attributed by its preserved-tree comment
    Given a current seed ruling on a refs/livespec/preserved-publish/ ref that a livespec-preserved-tree comment on the item names with run B
    When recovery routing routes the item
    Then the seed record names run B as its source run

  Scenario: an unidentifiable writing run reads unobservable
    Given a current seed ruling on a ref that belongs to none of the item's runs under the run-age bound's rules
    When recovery routing routes the item
    Then the seed record's source run reads unobservable, naming the cause
    And it names none of the item's runs
    And the seed record names the ruled ref and the ruled commit unchanged
```

**4. Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new scenario heading. The row is carried through `resulting_files[]` with the path spelled `../tests/heading-coverage.json`, or edited directly in that commit, with `test: "TODO"`, `work_item: "bd-ib-6jo7an"`, and a non-empty `reason` naming integration or above as the owed test's tier. It also adds one matching `tests/heading-coverage-debt.json` entry. If the revise renumbers Scenario 361, the row and entry MUST carry the renumbered heading text.
