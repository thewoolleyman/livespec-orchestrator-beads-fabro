---
topic: a-spec-change-tier-record
author: claude-opus-5-5
created_at: 2026-11-12T16:40:00Z
---

## Proposal: A spec-change tier record names the build and tier rule that wrote it, and says so when that rule is older than the ratified clause

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A `livespec-spec-change-tier` record carries a stage, a behaviour digest and a spec identity, but not the plugin build that wrote it or the tier rule that build applied. A stale build therefore stamps the current spec version on a decision taken under an older rule, and the record cannot be told apart from a correct one. This proposal makes every tier record name its build and its tier rule. A record whose rule is older than the ratified autonomy-tier clause must say so, naming both versions.

### Motivation

Work item bd-ib-bowuak (plan bd-ib-ax3rds), filed on the fleet coordinator's ruling (legacy-coordinator-agent 599f41e5, 2026-11-12), priority band 2. It is held at spec-change tier for this linked stem: verdict unstated, spec 356, generalization target `## Grooming and slice-size calibration`. The topic is the item's linked stem, so the hold links without a relink.

Measured: spec v354, ratified on 2026-11-11 at 19:28Z (Scenario 344), made the verdict decide the hold for every classification.
- 7860c6a9f implements it and ships in v0.320.0. Hosts were still dispatching on v0.317.0 (37e012335), which exempts bug, chore and non-functional items without a judgement.
- That build still stamps the CURRENT spec version. bd-ib-ag633q's filing and dispatch records read "spec-version: 356 | tier: none | classification: bug | verdict-kind: (not taken)". That reads as if the v356 clause had been applied and found nothing to hold.
- Across all 20 beads tenants on 2026-11-11, 20 items in 9 tenants were dispatched after the v354 ratification on records like that.

Design choices, stated for the grade:
- **The rule is a version the build declares.** Each build carries, as a constant, the orchestrator spec version of the newest revision that amended the autonomy-tier bullet and that the build implements. That is decidable at build time and needs no model.
- **Staleness is read from the forge, like a release.** The writer compares that version with the newest ratified orchestrator revision amending the bullet, read from the orchestrator repository's default branch on its forge remote. A tenant's own spec version cannot answer this, because the tier clause lives in the orchestrator's spec, not the tenant's.
- **Flag, never refuse.** A stale-rule record keeps every existing field and adds the flag. This proposal changes what the record SAYS, not whether a dispatch proceeds. Whether a stale rule should refuse is a separate fleet decision.
- **Unobservable is its own reading.** It is distinct from both current and stale, as the plugin-currency check already distinguishes "could not determine" from "current".

In-flight alignment, all `align`: #5058 amends the same bullet's hold reading, not the record's fields; #5036, #5042 and the-spec-change-tier-judgement change how the judgement is taken, not what the record names. Fleet scope: every tenant's tier records are written by the orchestrator plugin, so every tenant inherits the change.

### Proposed Changes

**1. The record names its build and rule (`contracts.md` §"Grooming and slice-size calibration", the "An autonomy tier is assigned" bullet).** Immediately before the bullet's last sentence, "Plan-child disposition refuses a held spec-change-tier child and admits an implementation follow-up.", add:

> Every `livespec-spec-change-tier` record, whatever its stage, MUST name the plugin build that wrote it, as the build's commit, and its TIER RULE. The tier rule is the orchestrator specification version of the newest revision amending this bullet that the build implements, carried by the build as a constant. The writer MUST compare that version with the newest ratified orchestrator revision amending this bullet, read from the orchestrator repository's default branch on its forge remote. When the build's tier rule is older, the record MUST say that its tier rule predates the ratified clause, naming the build's rule version and the ratified version, so it cannot be read as a judgement made under the spec version it names. When the comparison cannot be taken, the record MUST say the rule's currency is unobservable, distinctly from saying it is current. When the build's tier rule equals the ratified version, the record reads exactly as it would without this sentence, plus the build and tier-rule fields. Naming a stale rule is a statement on the record. It neither refuses a dispatch nor changes the recorded tier.

**2. Scenario (`scenarios.md`).** Append the scenario below. Its number is the next free one at revise time; 350 to 361 are claimed by pending proposals and peer drafts.

## Scenario 362 — A spec-change tier record names its build and tier rule, and a record written under an older tier rule says so

```gherkin
Feature: a tier record cannot claim a clause its build did not apply
  Scenario: a current build's record names its build and rule
    Given a plugin build whose tier rule equals the newest ratified orchestrator revision amending the autonomy-tier bullet
    When it writes a livespec-spec-change-tier record at any stage
    Then the record names the build's commit and its tier rule
    And the record otherwise reads as it did before this scenario

  Scenario: a stale build's record says its rule predates the ratified clause
    Given a plugin build whose tier rule is older than the newest ratified orchestrator revision amending the autonomy-tier bullet
    When it writes a livespec-spec-change-tier record
    Then the record says its tier rule predates the ratified clause, naming the build's rule version and the ratified version
    And the recorded tier and the dispatch outcome are unchanged by that statement

  Scenario: an unreadable comparison reads unobservable
    Given the orchestrator repository's default branch cannot be read from its forge remote
    When a build writes a livespec-spec-change-tier record
    Then the record says the tier rule's currency is unobservable
    And it does not say the rule is current
```

**3. Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new scenario heading. The row is carried through `resulting_files[]` with the path spelled `../tests/heading-coverage.json`, or edited directly in that commit, with `test: "TODO"`, `work_item: "bd-ib-bowuak"`, and a non-empty `reason` naming integration or above as the owed test's tier. It also adds one matching `tests/heading-coverage-debt.json` entry. If the revise renumbers Scenario 362, the row and entry MUST carry the renumbered heading text.
