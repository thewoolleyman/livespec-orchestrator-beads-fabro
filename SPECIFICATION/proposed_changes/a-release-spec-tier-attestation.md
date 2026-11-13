---
topic: a-release-spec-tier-attestation
author: claude-opus-5-5
created_at: 2026-11-13T09:18:05Z
---

## Proposal: A release-spec-tier attestation is keyed on the clause text the human cited, so an edit elsewhere under its heading keeps the release

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A `release-spec-tier` attestation is keyed today on a digest of the WHOLE cited H2 heading, so any revise that edits anything under that heading voids every attestation recorded against it, even when the sentences the human actually read are unchanged. This proposal lets the human cite the clause text that states the item's behaviour: one or more consecutive whole lines of the attested heading's body, supplied to `drive` through `--cited-text-file <path>`. An attestation that carries cited text is keyed on that text and its digest. An edit elsewhere under the heading keeps the release, and an edit to the cited text voids it. An attestation that carries no cited text, including every attestation recorded before this change, keeps today's whole-heading identity.

### Motivation

Work item bd-ib-otes2s (plan bd-ib-ax3rds). legacy-coordinator-agent (session e7605d67) routed it to this seat on 2026-11-13, because it uses the same mechanism as this seat's proof-mode carry-forward of a recorded tier decision: the reuse identity of a spec-change tier outcome. Measured on bd-ib-t5aju3. It was released by attestation at 2026-11-12T15:43:00Z against "Dispatcher admission, WIP cap, and post-merge acceptance" at spec v360. That heading's body is byte-identical from v359 to v361, and v362 (topic the-spec-change-tier-judgement) changed it from 232,608 to 236,114 characters. The dispatch of 2026-11-13T09:05:43Z, at v366 on build 0.326.0, re-took the classification and got the same behaviour digest b03f3b72, yet the item was refused with exit 5 for an unratified topic, and the coordinator had to release it by hand a second time. The heading is about 236,000 characters and was edited within a day of the release, so a release against it has a short life. The defect is in the ratified sentence, not only in the code. "A change to the attested input or to the cited clause voids it" and "the cited clause's heading and body" make the whole H2 body the reuse identity, and `commands/_spec_tier_attestation.py` `clause_digest` implements exactly that. Narrowing it is therefore a spec change. Fleet scope: every repository that uses the release-spec-tier valve inherits the behaviour through this plugin. Prior art: bd-ib-otl2ey (closed, #4262) extended clause-provenance reuse to the model's tier verdict, but left the human attestation keyed on the whole heading. bd-ib-lrjdlo addresses why the judge misses a stated clause, which reduces how often a release is needed but does not make a release durable. bd-ib-tgkx5f concerns the attestation's actor only. In-flight alignment, all `align`: an-inherited-clause-releases-the-hold (pending revise; it lets the valve attest an inherited heading, and cited text applies to that heading's body in the same way), #5058 the-approve-valve-refuses-an (its exemption for a non-void attestation inherits whatever voids one), and #5068 a-spec-change-tier-record (it edits the same bullet but no attestation sentence).

### Proposed Changes

**1. The attestation may cite clause text within its heading (`contracts.md` §"Grooming and slice-size calibration" → "The four maintainer touchpoints", touchpoint 1, "An autonomy tier is assigned").** Replace the sentence

> It MUST record a durable ledger comment on the item, and a dispatch-journal entry, each carrying the actor, the heading, its spec file, the spec version and a digest of the clause's heading and body.

with

> The human MAY also cite the clause text that states the behaviour: one or more consecutive whole lines of `<heading>`'s body, verbatim, supplied to `drive` through `--cited-text-file <path>`. The valve MUST refuse cited text that is empty, or that is not consecutive whole lines of that heading's body, naming the reason, and MUST then leave the item held and record nothing. It MUST record a durable ledger comment on the item, and a dispatch-journal entry, each carrying the actor, the heading, its spec file, the spec version and a digest of the clause's heading and body. When cited text was supplied, each also carries the cited text in full and a digest of it, the cited-text digest.

**2. The reuse identity follows the citation (same bullet).** Replace the two sentences

> While that attested input and the cited clause's heading and body are unchanged, every taking, the pre-dispatch wall and the `dod_gate` node included, MUST use the attested `stated` verdict without requiring model agreement, and its clause provenance is the cited clause, as both the selected and the named clause of each attested assertion. A change elsewhere in the specification does not void it; a change to the attested input or to the cited clause voids it, and an item held again may be released again by a fresh attestation.

with

> The attested clause is the cited text when the attestation carries one, and the heading's whole heading and body when it does not. While the attested input is unchanged and the attested clause is unchanged, every taking, the pre-dispatch wall and the `dod_gate` node included, MUST use the attested `stated` verdict without requiring model agreement. Its clause provenance is the cited heading, as both the selected and the named clause of each attested assertion. Cited text is unchanged while the heading still resolves and its body still contains, as consecutive whole lines, text whose digest equals the recorded cited-text digest. A heading and body are unchanged while their digest equals the recorded clause digest. A change elsewhere in the specification does not void an attestation. Nor does a change to other text under the attested heading when the attestation carries cited text. A change to the attested input voids it, as does a change to the attested clause or the removal of its heading. An item held again may be released again by a fresh attestation. An attestation recorded without cited text, including every attestation recorded before cited text existed, keeps the whole-heading identity and is void when the heading's body changes.

These rules apply unchanged to an attestation of a declared inherited heading: its cited text is lines of that inherited heading's body.

**3. Scenario (`scenarios.md`).** Append:

## Scenario 366 — A release-spec-tier attestation that cites clause text survives an edit elsewhere under its heading

```gherkin
Feature: a human release is keyed on the text the human attested
  Scenario: the attestation records the cited clause text and its digest
    Given a feature held as spec-change tier
    And an existing H2 heading whose body contains lines that state the item's asked-for behaviour
    When a human drives release-spec-tier for the item naming that heading, with those lines in a file passed as --cited-text-file
    Then the hold is released
    And the ledger comment and the dispatch-journal entry each carry the cited text in full and its cited-text digest, beside the heading, its spec file, the spec version and the clause digest
  Scenario: cited text that is not whole lines of the heading's body is refused
    Given a feature held as spec-change tier
    When a human drives release-spec-tier naming an existing heading with cited text that is not consecutive whole lines of that heading's body
    Then the valve refuses naming the reason
    And the item stays held and no attestation is recorded
  Scenario: an edit elsewhere under the heading keeps the release
    Given a feature released by an attestation that carries cited text
    When a later revision changes other text under the attested heading, leaving the cited lines and the item's attested input unchanged
    Then the item's next taking uses the attested stated verdict
    And the pre-dispatch wall does not hold the item
  Scenario: an edit to the cited text voids the release
    Given a feature released by an attestation that carries cited text
    When a later revision changes the cited lines
    Then the attestation is void and the item's next taking is judged again against the new revision
  Scenario: a whole-heading attestation keeps its present behaviour
    Given a feature released by an attestation that carries no cited text
    When a later revision changes any text under the attested heading
    Then the attestation is void and the item's next taking is judged again against the new revision
```

**4. Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new scenario heading, carried through `resulting_files[]` with the path spelled `../tests/heading-coverage.json` or edited directly in that commit. The row carries `test: "TODO"`, `work_item: "bd-ib-otes2s"` and a non-empty `reason` naming the tier the owed test runs at, integration or above. The same commit MUST add one matching `tests/heading-coverage-debt.json` entry carrying the key three, `work_item: "bd-ib-otes2s"` and `first_seen` set to the revise date. If the revise renumbers Scenario 366, the row and the entry MUST carry the renumbered heading text.
