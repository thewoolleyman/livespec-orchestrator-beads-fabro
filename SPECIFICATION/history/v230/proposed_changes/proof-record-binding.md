---
topic: proof-record-binding
author: claude-opus-5-5
created_at: 2026-10-26T20:10:56Z
---

## Proposal: Each Proof of Done record carries its own binding, and acceptance selects records by it

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

Every factory and host Proof of Done record carries a one-line binding (work item, pull request, head sha) written by the posting primitive. The acceptance pass selects records by that binding and never by inferring which runs merged the pull request; it gives every record on the pull request a bind verdict (human-attested, superseded, bound, bound-elsewhere, legacy-host, legacy-matched, unbindable), requires a verified record to apply to the merged head, matches a legacy record by run id against every dispatch of the item, refuses loudly on an unbindable record rather than reporting it as absent, and lists every record with its verdict on the parking record.

### Motivation

The maintainer, attended on 2026-10-26 at about 19:5x UTC, said of the defect below: "This should not be possible. The wrench should always be mechanically linked, fail-safe, and discoverable." Coordinator gitops-fleet-capacity-monitoring routed this clause spec-first as ruling R53, naming bd-ib-poh6jg as the implementing item.

Today §"The proof evidence leg" takes "the `proof_verify` record of the run whose pull request merged", so whether a record counts depends on which runs a resolution step infers merged the pull request. Measured 2026-10-26: the acceptance pass on bd-ib-tixpma (pull request 3164) resolved run ids 01M4SHF18VGK3PV7ZR3ZFSB7P7, 0240450f8edf..., 01M4Q7GDZZ... and 1cb6d72e86..., did not include 0498841858ff4cb185b42d12ff26e8b4, and parked the item with "proof of done record: NOT OBSERVED", although "Proof of Done — verified — run 0498841858ff4cb185b42d12ff26e8b4" had been on the pull request since 2026-10-17T17:16Z and the 2026-10-18 pass, whose run set did include it, graded it. The parking records at 19:14Z and 19:23Z on 2026-10-26 show the miss. Nothing in the record linked it to the item, the miss was reported as an absence, and the parking record did not list what was on the pull request, so a reader could not see why the record did not count. Controls: bd-ib-be5r7o (pull request 3134, captured but never verified) and bd-ib-fisgni (pull request 3155, hand-landed with no factory record) are genuine absences and still report one under this clause.

Boundary: the pending proposal post-host-record-refuses-an-item-without-its-own-merged-pull-req edits the host-leg paragraph's posting-primitive sentences; this proposal adds a separate paragraph and does not touch them. The human-attested leg is unchanged. No `## ` heading changes other than the new Scenario 252.

An independent read-only Codex review of the first draft raised eight blockers, all folded in here: a correction mechanism (`Supersedes:`) so an unbindable record cannot park an item forever; a `legacy-host` verdict so unbound host records keep their existing host-leg rules; a head-applicability rule so a record proving an earlier head does not prove the merged head without a carry-forward; the pointer, the parking-comment deduplication identity, the record's run-attribution sentence, the resume run resolution, and Scenarios 132, 133 and 138 brought onto the same binding-based selection; host-only scope for the posting primitive's pull-request resolution, so the pending post-host-record proposal cannot forbid factory posting before merge; and an explicit outcome when the selected record has no evidence for an assertion.
A second Codex pass confirmed those resolved and raised three narrower points, also folded in: a correcting factory record may be posted after merge; each assertion is graded from its own `Reproduced:` line whatever the record-wide verdict; and counting is defined for factory, host and human-attested records alike and governs every record the pointer names or compares.

### Proposed Changes

1. In `SPECIFICATION/contracts.md`, §"Self-contained plugin dispatch" → "### Proof of Done record", insert this new paragraph immediately before the paragraph beginning "**The host leg.**":

```
**The binding.** Every record the implementation posts, each factory record
and each host record, MUST carry its own binding to the subject it proves. The
binding is written by the implementation's posting primitive, the one §"The
host leg" below names, which every stage and every host leg MUST use to
publish a record, so that no stage or session hand-formats a binding. The
binding is exactly one line, placed immediately after the record's first line
and outside any fenced block, of the form `Binds: <work-item-id> — pull
request #<number> — head <full commit sha>`. It names the work item the record
proves, the pull request the record is posted on, and the full commit sha of
the pull request head the record proves: for a factory record, the
publish-branch head the record names; for a host record, the head commit of
that pull request at its merge, which is not the default-branch commit the
merge produced. The primitive's resolution of which pull request a record is
posted on, and any refusal it makes for an item that has no merged pull
request of its own, govern host records only: a factory record is posted,
before merge, on the pull request of the run that produced it, and its binding
names that pull request. A correcting record that supersedes a factory record
MAY be posted through the primitive after merge, on the same pull request; it
carries the superseded record's run identifier on its first line and binds the
head the superseded record proves. A record that carries no binding line is a
legacy record. A human-attested record is posted by a human and is outside
this rule; the human-attested leg of the acceptance pass governs it. A
correction is a new record: a record the primitive posts MAY carry, on the
line after its binding, `Supersedes: <comment link>` naming one earlier record
on the same pull request, and only a record that itself carries a well-formed
binding to that pull request resolves the fault of the record it names. The
acceptance pass selects records by binding (§"Dispatcher admission, WIP cap,
and post-merge acceptance" → "The proof evidence leg"). Measured 2026-10-26:
the acceptance pass on bd-ib-tixpma, pull request 3164, resolved four run ids
as the merging runs, did not include run 0498841858ff4cb185b42d12ff26e8b4, and
reported its proof of done record NOT OBSERVED, although that run's `verified`
record had been on the pull request since 2026-10-17 and the pass of
2026-10-18 had graded it. Scenario 252 in `scenarios.md` exercises this
paragraph and the selection it governs.
```

2. In `SPECIFICATION/contracts.md`, §"Dispatcher admission, WIP cap, and post-merge acceptance", replace the opening of the paragraph "**The proof evidence leg.**", from its start through "The pass MUST NOT apply merged-diff vocabulary", which today reads

```
  **The proof evidence leg.** For every effective assertion whose proof
  mode is `factory_captured` (§"Effective acceptance criteria" →
  "Per-assertion proof mode"), the acceptance pass MUST take as its
  criteria-leg evidence the `proof_verify` record of the run whose pull
  request merged, observed from the pull request (§"Proof of Done
  record"): the assertion is judged passing when that record's verdict is
  `verified` and the assertion is listed as reproduced, failing when the
  record lists it as not reproduced, and UNOBSERVED — yielding
  NEEDS_ATTENTION per the evidence rule — when no `verified` record exists
  for the merging run. A record identifies the merging run by the run
  identifier on its first line, and the pass MUST accept either
  identifier the Dispatcher can attribute to the merging dispatch — the
  Fabro run id, or the dispatch id the Dispatcher declared to the
  sandbox — so a `verified` record stamped with the dispatch id is
  attributed to the merging run exactly as one stamped with the Fabro
  run id is; for a resumed dispatch the pass MUST also accept any
  identifier the journal's `resume` records link to it, transitively
  (§"Dispatcher loop invocation surface" → "Resume from a published
  pull request"). The pass MUST NOT apply merged-diff vocabulary
```

with

```
  **The proof evidence leg.** For every effective assertion whose proof mode
  is `factory_captured` (§"Effective acceptance criteria" → "Per-assertion
  proof mode"), the acceptance pass MUST take its criteria-leg evidence from
  the Proof of Done records on the pull request whose merge it grades,
  selected by each record's binding (§"Proof of Done record" → "The binding").
  It MUST NOT select a record by inferring which runs merged that pull
  request. The pass MUST read every Proof of Done record on that pull request
  and give each one exactly one bind verdict, taking the first rule below that
  applies:

  - `human-attested`: it is a human-attested record, which the human-attested
    leg below governs.
  - `superseded`: a later record on the pull request carries a well-formed
    binding to this pull request and a `Supersedes:` line naming it. It is not
    evidence, and it is never a refusal.
  - `bound`: its binding is well-formed and names this work item and this pull
    request.
  - `bound-elsewhere`: its binding is well-formed and names another work item
    or another pull request. It is not evidence for this item.
  - `legacy-host`: it is a host record that carries no binding. The
    host-captured leg judges it by the host-leg rules of §"Proof of Done record"
    → "The host leg", unchanged.
  - `legacy-matched`: it is a factory record that carries no binding, and its
    run identifier is one the Dispatcher attributes to a dispatch of this item.
    The pass MUST match it against EVERY dispatch of the item that the item's
    dispatch records name, never against a subset resolved as the merging run.
    For each dispatch it MUST accept the Fabro run id, the dispatch id the
    Dispatcher declared to that dispatch's sandbox, and every identifier the
    journal's `resume` records link to that dispatch, transitively (§"Dispatcher
    loop invocation surface" → "Resume from a published pull request").
  - `unbindable`: any other record, that is, one whose binding line is
    malformed or incomplete, one that carries more than one binding line, or a
    factory record without a binding whose run identifier matches no dispatch of
    this item.

  A record COUNTS for this item when it is a factory record whose verdict is
  `bound` or `legacy-matched`, a host record whose verdict is `bound` or
  `legacy-host`, or a human-attested record; a `reproof_required` record that
  counts is still never evidence, as §"Proof of Done record" → "The record"
  requires. A counted record proves the head its binding names, or, for a
  legacy record, the head the record names. A counted `proof_verify` record
  (verdict `verified` or `not_reproduced`) APPLIES to the merge when the head
  it proves is the pull request's head commit at merge, or when a counted
  `carried_forward` record names that merged head and links that
  `proof_verify` record. A legacy record that names no head applies as it did
  before this paragraph was ratified. A counted `proof_verify` record that
  does not apply is reported as stale-head and is not evidence. Each assertion
  is judged on its own section of the newest applicable counted `proof_verify`
  record, whatever that record's record-wide verdict: passing when the section
  carries `Reproduced: yes`, and failing when it carries `Reproduced: no`.
  When that record has no section for the assertion, or its section carries no
  `Reproduced:` line, the assertion is NEEDS_ATTENTION naming that record and
  the missing evidence, and the pass MUST NOT fall back to an older record.
  When no applicable counted `proof_verify` record exists, the record is
  ABSENT, and the assertion is UNOBSERVED, yielding NEEDS_ATTENTION per the
  evidence rule. The host-captured leg MUST take as evidence only host records
  whose verdict is `bound` or `legacy-host`, and keeps the host-leg rules on
  which pull request, build identity and session identity count. When any
  record on the pull request is `unbindable`, the pass MUST NOT grade any of
  the item's `factory_captured` or `host_captured` assertions and MUST NOT
  report any of them UNOBSERVED. Its verdict is NEEDS_ATTENTION for the reason
  that a proof record is unbindable, which is a reported state distinct from
  an ABSENT record; the rework counter is unchanged. The parking record MUST
  name each `unbindable` record by its comment link, state its fault, and name
  the action that clears it: posting, through the posting primitive, a
  correcting record that supersedes it. `needs-attention` MUST surface the
  refusal as an attention fact naming the item, the pull request and each such
  record. The parking record of every pass that parks the item, and the pass's
  journal record, MUST list every Proof of Done record found on the pull
  request with its kind, its run or session identifier, its comment link, its
  bind verdict, the fault of each `unbindable` record and each stale-head
  report, so that a reader sees why each record did or did not count. The pass
  MUST NOT apply merged-diff vocabulary
```

The rest of that paragraph is unchanged.

3. In `SPECIFICATION/contracts.md`, Proof of Done record → The record, replace

```
carries MUST be one the Dispatcher can attribute to the merging dispatch: the
```

with

```
carries MUST be one the Dispatcher can attribute to the dispatch of the item that produced the record: the
```

4. In `SPECIFICATION/contracts.md`, Proof of Done record → The pointer, replace

```
comment link of the latest `verified` record, its run id and timestamp, its
```

with

```
comment link of the latest `verified` record counting for the item, its run id and timestamp, its
```

5. In `SPECIFICATION/contracts.md`, Proof of Done record → The pointer, replace

```
NOT copy proof content. The pointer MUST be written whenever a `verified`
record exists for the merging run, independently of the acceptance verdict: a
```

with

```
NOT copy proof content. Every record the pointer names, and every record a
staleness check compares it with, MUST be one that counts for the item under
the proof evidence leg's bind verdicts (a factory, host or human-attested
record, as that leg defines counting). The pointer MUST be written whenever a
`verified` record counting for the item exists, independently of the
acceptance verdict: a
```

6. In `SPECIFICATION/contracts.md`, Proof of Done record → The pointer, replace

```
`carried_forward`, `host_verified`, `human_attested`) on the pull request is
stale
```

with

```
`carried_forward`, `host_verified`, `human_attested`) on the pull request that
counts for the item under the proof evidence leg's bind verdicts is stale
```

7. In `SPECIFICATION/contracts.md`, Proof of Done record → The pointer, replace

```
pointer stale. An item in `acceptance` whose merging run has a `verified`
record and whose description has no pointer
```

with

```
pointer stale. An item in `acceptance` that has a `verified` record counting for
it and whose description has no pointer
```

8. In `SPECIFICATION/contracts.md`, Resume from a published pull request → What it resumes, replace

```
through the dispatch journal exactly as the acceptance pass attributes a
record (
```

with

```
through the dispatch journal by the run identifier on its first line, accepting
for each journaled dispatch the identifiers the legacy match accepts (
```

9. In `SPECIFICATION/contracts.md`, post-merge acceptance → A parking verdict is recorded, replace

```
record one comment per DISTINCT (verdict, pending-leg set): a re-run
  whose verdict and pending-leg set are unchanged appends nothing.
```

with

```
record one comment per DISTINCT (verdict, pending-leg set, proof-record
  inventory), where the inventory is the list of Proof of Done records with
  their bind verdicts, faults and stale-head reports that the proof evidence
  leg requires: a re-run whose verdict, pending-leg set and inventory are
  unchanged appends nothing.
```

10. In `SPECIFICATION/scenarios.md`, Scenario 132, replace

```
    Given an item whose Proof of Done pointer names a run id that is not the latest verified record on its pull request
```

with

```
    Given an item whose Proof of Done pointer names a run id that is not the latest verified record counting for the item on its pull request
```

11. In `SPECIFICATION/scenarios.md`, Scenario 133, replace

```
    Given a merged item whose factory_captured assertion has no verified record for the merging run
```

with

```
    Given a merged item whose factory_captured assertion has no applicable proof_verify record counting for the item
```

12. In `SPECIFICATION/scenarios.md`, Scenario 138, replace

```
    Given an item parked in acceptance whose ledger carries the parking comment for its verdict and pending-leg set
    When the acceptance pass is re-run and returns the same verdict and pending-leg set
```

with

```
    Given an item parked in acceptance whose ledger carries the parking comment for its verdict, pending-leg set and proof-record inventory
    When the acceptance pass is re-run and returns the same verdict, pending-leg set and proof-record inventory
```

13. In `SPECIFICATION/scenarios.md`, Scenario 138, replace

```
  Scenario: A record stamped with the dispatch id is attributed to the merging run
    Given a merged item whose verified record's first line carries the dispatch id the Dispatcher declared to the sandbox
    When the acceptance pass looks for the merging run's verified record
    Then the record is attributed to the merging run and each factory-captured assertion is graded from it
```

with

```
  Scenario: A legacy record stamped with the dispatch id is matched to the item's dispatch
    Given a merged item whose verified record carries no binding and whose first line carries the dispatch id the Dispatcher declared to the sandbox
    When the acceptance pass gives the record its bind verdict
    Then the record is legacy-matched to that dispatch and each factory-captured assertion is graded from it
```

14. In `SPECIFICATION/scenarios.md`, append:

````
## Scenario 252 — The acceptance pass selects each Proof of Done record by the binding the record carries

```gherkin
Feature: A Proof of Done record is mechanically linked to the item it proves
  As the maintainer of a factory
  I want the acceptance pass to select proof records by the binding each record carries
  So that a verified record is never reported missing because a run resolution left out the run that produced it

  Scenario: A bound verified record counts whichever run produced it
    Given a merged pull request whose verified record lists a factory_captured assertion as reproduced
    And the record's binding names that work item and that pull request
    And no merging-run resolution would select the run that produced the record
    When the acceptance pass grades the item
    Then the assertion is judged passing on that record
    And the pass's journal record lists that record with the bind verdict bound

  Scenario: A legacy record is matched against every dispatch of the item
    Given a verified record with no binding line whose run identifier is the Fabro run id of the item's first dispatch
    And the item has been dispatched three more times since that dispatch
    When the acceptance pass grades the item
    Then the record's bind verdict is legacy-matched
    And the assertion is judged on that record

  Scenario: An unbindable record is a loud refusal and not an absence
    Given a merged pull request carrying a verified record whose binding line names no head commit sha
    When the acceptance pass grades the item
    Then the pass grades none of the item's factory_captured assertions
    And no assertion is reported UNOBSERVED
    And the item parks with a refusal naming that record's comment link and its fault
    And needs-attention surfaces the refusal naming the item, the pull request and the record

  Scenario: An absent record stays distinct from an unbindable one
    Given a merged pull request whose only Proof of Done record is bound to another work item
    When the acceptance pass grades the item
    Then each factory_captured assertion is UNOBSERVED and the item parks with NEEDS_ATTENTION
    And the parking record lists that record with the bind verdict bound-elsewhere

  Scenario: A correcting record clears an unbindable one
    Given a merged pull request carrying an unbindable verified record
    And a later record posted through the posting primitive whose binding names the item and the pull request and whose Supersedes line names the unbindable record
    When the acceptance pass grades the item
    Then the earlier record's bind verdict is superseded
    And the item's factory_captured assertions are graded from the correcting record

  Scenario: A verified record for an earlier head does not prove the merged head
    Given a bound verified record proving head H1
    And the pull request merged at head H2 with no counted carried_forward record naming H2
    When the acceptance pass grades the item
    Then the record is reported stale-head and is not evidence
    And each factory_captured assertion is UNOBSERVED
```
````

15. Add a TODO row for the new heading to `tests/heading-coverage.json` and a matching debt row to `tests/heading-coverage-debt.json`, both owned by the implementing work-item bd-ib-poh6jg.
