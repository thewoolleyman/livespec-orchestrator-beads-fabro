---
topic: exhaustion-record-per-credential-identity
author: claude-opus-5-5-plan-bd-ib-jxvgq5
created_at: 2026-10-16T18:38:16Z
---

## Proposal: Scope an observed provider-exhaustion record to the credential identity that observed the limit

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

An observed provider-exhaustion record today names only a vendor, so it refuses every dispatch that renders a candidate on that vendor. When the credential behind a candidate is rotated to a fresh account of the same vendor, a record minted by a run that used the exhausted account goes on refusing dispatches that would run on the fresh one. This proposal has the record carry the opaque non-secret credential identity that the observing dispatch's admission headroom assessment projected, makes that record cover only a dispatch projecting the same identity, keeps records distinct per identity, and keeps a record that carries no identity at its current vendor-wide coverage. The v127 typed domain holds keep their `availability_key` scoping under the ratified rule that different accounts use different keys; the same rotation blind spot in typed domain holds for built-in candidates is an explicit deferral of plan bd-ib-jxvgq5, reconsidered after this record lands (no typed hold was minted in the measured incident).

### Motivation

Measured 2026-10-16 (freeze-driver ruling R73, work-item bd-ib-b53dhr). The Anthropic selection was rotated from one account to another at 16:52Z. Four runs already in flight on the first account then ended on its session limit between 17:35Z and 17:41Z (01M52QRP5WZH, 01M52R2WND7Y, 01M52Q98H4DF, 01M52Q014P6T). Their closes minted an `anthropic` record that refused dispatches on the freshly selected account until 17:50:19Z, although that account had headroom. `record_provider_exhaustion_if_observed` in `_dispatcher_provider_exhaustion.py` writes only `provider`, and `covering_provider_exhaustion` matches on it, so the gauge cannot tell an exhausted account from a fresh one. The opaque non-secret credential identity is already journaled by the admission session-headroom assessment (the rotation is visible there: 4cdcd2d377925269 at 16:48:26Z, aad1734c0ce2713f at 16:53:36Z), so this clause reuses that ratified identity rather than coining a new one, and reads no credential material beyond what that clause already fingerprints. The operator clearance valve (Scenario 116) remains the remedy for a record minted before this change.

### Proposed Changes

1. In SPECIFICATION/contracts.md, the paragraph beginning "**Every observed availability record is scoped, versioned, and expires.**": after the sentence "Legacy provider-only records remain readable and effective until retirement as domain holds against candidates whose built-in compatibility alias names that provider, plus identity-less legacy candidates under §"Factory-configurable ACP fallback priority", which every live legacy record covers; they MUST NOT be ignored or broadened to unrelated explicitly identified candidates.", insert: "A provider-exhaustion record minted from a dispatch's typed provider usage-limit outcome MUST also carry the opaque non-secret credential identity that the dispatch's admission session-headroom assessment journaled under the "Admission filters candidates by projected Claude session headroom" clause of this section, when that assessment journaled one; a record for a dispatch whose admission journaled no such identity carries none. An absent identity is not a credential identity: a record minted for a dispatch whose projected identity was absent carries none. A record carrying a credential identity covers only a dispatch whose admission projects that same identity for a covered candidate; a dispatch projecting a different identity, including one admitted after the credential behind the candidate was rotated to another account of the same vendor, MUST NOT be refused by it. Records are distinct per provider and credential identity: a newer record for one identity neither supersedes nor retires a live record for another. The identity is a fingerprint of one credential snapshot, so a refreshed snapshot of the same account projects a new identity and is not covered until a new observation is recorded against it. A provider-exhaustion record that carries no credential identity, including every record minted before this clause, keeps the vendor-wide coverage stated above until it expires or is cleared. When a dispatch's projected credential identity is absent, the record covers it, so that a blinded gauge fails closed."

2. In SPECIFICATION/contracts.md, the paragraph beginning "**An operator may retire a record early.**": after "retain the existing provider valve for legacy records only.", insert: "The provider valve retires every live provider-exhaustion record of the named provider, whether or not the record carries a credential identity."

3. In SPECIFICATION/scenarios.md, append a new heading after the highest-numbered scenario on master at filing time (Scenario 185), numbered 186 unless a pending proposal has reserved that number, in which case it takes the next free number:

## Scenario 186 — A provider exhaustion observed on one credential account does not refuse dispatch on another account of the same vendor

```gherkin
Feature: An exhaustion record observed under one credential identity does not hold out another account of the same vendor
  As a maintainer whose credential rotation moves a vendor's candidates onto an account with headroom
  I want an exhaustion record to refuse only dispatches on the account that observed the limit
  So that a rotation is not defeated by records minted by runs still finishing on the exhausted account

  Scenario: A record names the credential identity the observing dispatch projected
    Given a dispatch whose admission projected credential identity "A" ends with a typed provider usage-limit outcome for provider "anthropic"
    When the Dispatcher mints the observed provider-exhaustion record
    Then the record names provider "anthropic" and credential identity "A"

  Scenario: A newer record for one identity does not retire another identity's record
    Given an unexpired provider-exhaustion record for provider "anthropic" naming credential identity "A"
    And a newer unexpired provider-exhaustion record for provider "anthropic" naming credential identity "B"
    When the Dispatcher reads the live provider-exhaustion records
    Then both records are live

  Scenario: A dispatch on another credential identity is admitted while the record is live
    Given an unexpired provider-exhaustion record for provider "anthropic" naming credential identity "A"
    And a ready work-item whose covered candidates project credential identity "B"
    When the Dispatcher evaluates the admission valve
    Then the record does not refuse the item

  Scenario: A dispatch on the same credential identity is refused while the record is live
    Given an unexpired provider-exhaustion record for provider "anthropic" naming credential identity "A"
    And a ready work-item whose covered candidates project credential identity "A" with no eligible fallback
    When the Dispatcher evaluates the admission valve
    Then the item is refused naming the record and its expiry

  Scenario: A record without a credential identity keeps vendor-wide coverage
    Given an unexpired provider-exhaustion record for provider "anthropic" that names no credential identity
    And a ready work-item whose covered candidates project credential identity "B" with no eligible fallback
    When the Dispatcher evaluates the admission valve
    Then the item is refused naming the record and its expiry

  Scenario: An unreadable credential identity fails closed
    Given an unexpired provider-exhaustion record for provider "anthropic" naming credential identity "A"
    And a ready work-item whose projected credential identity is absent
    When the Dispatcher evaluates the admission valve
    Then the record refuses the item
```

4. Scenario 60 and Scenario 94 are unchanged: Scenario 60's legacy case names no credential identity and keeps its vendor-wide coverage under change 1, and Scenario 94 concerns how expiry is computed, which this proposal does not alter. Scenario 116 is unchanged apart from the coverage stated by change 2, which its existing legacy-valve case already exercises.

5. tests/heading-coverage.json gains an entry for the new Scenario 186 heading with `"test": "TODO"`, `"work_item": "bd-ib-b53dhr"` and a non-empty reason.
