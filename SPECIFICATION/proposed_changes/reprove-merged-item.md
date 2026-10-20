---
topic: reprove-merged-item
author: claude-opus-5-5
created_at: 2026-10-20T04:21:33Z
---

## Proposal: reprove-merged-item

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

Add a narrow re-prove arm to resume (`resume --item --reprove`) so a merged item parked `NEEDS_ATTENTION` on its proof of done records can obtain fresh, per-assertion factory evidence on its existing merged pull request. The arm runs only `proof_capture`, `proof_verify`, `proof_grade` and `proof_grade_route` against the merge commit, pushes nothing, and then re-runs the acceptance pass; a resume without `--reprove` still refuses a merged pull request. The same arm re-proves a hand-carried merge, a merged pull request that no journaled dispatch published, against the pull request that `reconcile-merged` attributes to the item. Scenario 208 exercises it.

### Motivation

Work-item bd-ib-rszkjc merged as pull request 3130 with a verified record whose only `Reproduced:` line was record-wide, and the acceptance pass parked it `NEEDS_ATTENTION`. Revision v156 (bd-ib-kcq6pu, released in v0.215.0) now grades records per assertion before a run advances, but an item already merged under the old grading has no sanctioned route to fresh evidence: `resume --item` MUST refuse a merged pull request, `reconcile-merged` re-reads the stale record, a fresh dispatch cuts an empty branch, and a hand-posted record is not factory evidence for a `factory_captured` assertion. Filed as bd-ib-opd3hq under the stability-freeze driver's ruling R192.

The hand-carried arm comes from fleet coordinator ruling R275 (2026-10-20, option (B), carrier bd-ib-hbt5b6). Two merges wait on it: bd-ib-5guqmt (pull request 2990), whose factory run ended at `needs_human` and whose amend was finished by hand, and livespec-dev-tooling-yapwva (pull request 2383). Neither has a journaled dispatch whose pull request merged, so the first draft's definition of the merging dispatch excluded them. One route for both shapes is ratified in one pass. The host-leg generalization (option (A)) is not proposed: a `host_verified` record is no substitute for a `factory_captured` assertion.

bd-ib-5guqmt's parking record also names a pending host-captured record beside its factory proof records, so precondition (c) admits pending host-captured and human-attested legs beside at least one pending factory leg. A re-prove supplies only the factory legs; the others stay pending under their own rules.

### Proposed Changes

In `contracts.md`, under `### Resume from a published pull request (\`resume --item\`)`, the following paragraph MUST be inserted before **Refusals.**:

**Re-proving a merged item (`resume --item --reprove`).** A merged item
whose acceptance pass parked it `NEEDS_ATTENTION` because no graded proof
of done record reached it has no other route to fresh factory evidence: a
plain dispatch would cut an empty branch, and `reconcile-merged` re-reads the
records already on the pull request. The `--reprove` flag of `resume` is
that route, and only that route; a resume without it MUST refuse a merged
pull request exactly as the refusals below state.

*The merging dispatch and the merged pull request.* The item's *merging
dispatch* is its latest journaled dispatch whose pull request merged,
re-prove dispatches excluded. It stays authoritative for the merged diff, the
merge commit and the run/telemetry leg of every later acceptance pass, and
every re-prove of the item, the first or a later one, resolves the same
merging dispatch. An item that rests at `acceptance` with no merging
dispatch is a *hand-carried merge*: its pull request merged without a
journaled dispatch that published it. Its re-prove target is the merged pull
request that `reconcile-merged --item` attributes to the item, with that pull
request's merge commit as the published head. A re-prove's *target* is
the repository, the merged pull request's number and its merge commit sha;
the first re-prove of an item MUST record it, and every later re-prove of the
item MUST resolve the same target and MUST refuse, naming both values, when
the forge reports a different one. Below, the *merged pull
request* is the merging dispatch's pull request, or for a hand-carried merge
the attributed one; *Hand-carried merges* states what a hand-carried
re-prove uses where a merging dispatch's records would otherwise decide.

*Preconditions.* Under `--reprove` the following preconditions REPLACE the
ordinary resume's refusals for an item that is not `ready`, for a publish
branch with no open pull request or no proof record naming a head, for a
moved head, and for a closed or merged pull request: (a) the item rests at
`acceptance`; (b) the merged pull request is merged and the forge reports its
merge commit sha; and (c) the item's latest acceptance parking record is
`NEEDS_ATTENTION`, every pending leg it names is a proof of done record for a
`factory_captured` assertion, a host-captured record or a human-attested
record, and at least one is a proof of done record for a `factory_captured`
assertion. The refusals for a changed Definition of Done (measured against
the merging dispatch's dispatch-time snapshot, and not applied to a
hand-carried merge), a live ownership lock and an unanswerable measurement
apply unchanged. In place of the ordinary refusal for a live earlier run,
before launching a re-prove the Dispatcher MUST query, on its recorded
factory, every run the journal records for the item, earlier re-proves
included, and MUST refuse, naming the run and its factory, when any of them is
live or its liveness cannot be observed; an item whose journal records no run
needs no such query. The third-resume refusal applies as *Bounds* below
states. A
re-prove MUST refuse under the same precondition-error discipline as the
refusals below, naming each failed condition, with `reconcile-merged --item`
as the remedy for a failed (c).

*What a re-prove does.* A re-prove MUST NOT pass the admission valve or
change the item's status. It MUST otherwise do what "What a resume does"
requires except where this paragraph says otherwise: hold the dispatch-scoped
ownership lock, resolve its factory, declare a dispatch id to the sandbox and
journal as a dispatch does, including one `resume` record before the run
exists that carries `reprove: true`, the merging dispatch's identifiers (or,
for a hand-carried merge, `hand_carried: true` in their place), the pull
request number, the merge commit sha as the published head and
`proof_capture` as the resumed-at stage. Its run MUST check out the merge
commit. Neither the re-prove run nor the Dispatcher's handling of its
ending MUST create, update or delete any forge ref: the publication of a
preservation ref after a failed engine checkpoint (§"Failed engine
checkpoint commit attribution" → "A tree that nothing else carries is published to a
preservation ref") does not apply to a re-prove run, whose failures are
preserved by the exported artifacts and the preserve-by-reference pointer
only.

*The re-prove graph.* The run MUST run a graph the Dispatcher derives, for
that one run, from the workflow the merging dispatch's record names, and that
graph's edges override §"Definition-of-Done and Proof-of-Done stages" for the
re-prove run only: `start` leads to `proof_capture`; a `captured` record from
`proof_capture` leads to `proof_verify` rather than `review`; its `not_captured`
ending leads to `non_converged`; a `verified` outcome of `proof_verify` leads
to `proof_grade` and a `not_reproduced` one to `non_converged`; `proof_grade`'s
success edge leads to `exit`; and its failure edge leads to `proof_grade_route`,
which re-enters `proof_verify` below three recorded `proof_grade` failures and
leads to `non_converged` at the third. Any failed ACP outcome routes to
`needs_human` as in every run. The graph MUST consist of exactly `start`,
`proof_capture`, `proof_verify`, `proof_grade`, `proof_grade_route`, `exit`,
`non_converged` and `needs_human`, and MUST NOT carry any other node, in
particular no `dod_gate`, `implement`, `janitor`, `publish_draft`, `review`,
`fix`, `pr_refresh` or `pr`. Because
the graph has no implementer, in a re-prove run `proof_verify` MUST run on an
adapter distinct from the adapter that executed that run's `proof_capture`;
this replaces, for that run only, the comparison with the implementer's
adapter that §"Definition-of-Done and Proof-of-Done stages" → "`proof_verify`"
states.

*Records and head.* Its `captured` and `verified` records MUST be posted as
new comments on the merged pull request, and MUST name the merge commit sha
the `resume` record names where a first run's record names the publish-branch
head. In a re-prove run `proof_grade` MUST additionally fail, naming both
shas, when the newest attributed `verified` record does not name that merge
commit sha, and MUST fail closed when it cannot read the sha; such a failure
counts as a `proof_grade` failure.

*Attribution and selection.* A `reprove` `resume` record links the re-prove
run's identifiers back to the merging dispatch, or for a hand-carried merge to
the merged pull request. A re-prove is *eligible* when the journal's
`reprove-ending` record shows its run ending at `exit` and its `verified`
record names the merge commit sha its `resume` record names. For a re-proven
item the acceptance pass (§"Post-merge acceptance (`acceptance → done`)" →
"The proof evidence leg") MUST exclude every record of a re-prove that is
running, ended anywhere other than `exit`, or has no `reprove-ending` record,
and MUST then take as the item's `proof_verify` record the newest `verified`
record, by the forge's comment creation time, of the eligible re-prove whose
`resume` record is latest in journal order, in place of any record of the
merging run. When no re-prove is eligible, the leg's ordinary rules apply
unchanged. An assertion of the item's current effective Definition of Done
that the selected re-prove's snapshot does not carry with the same text is
UNOBSERVED in that pass, whatever identifier it shares with an assertion the
snapshot carries. Within a re-prove run, `proof_grade` MUST read only records
carrying that run's own identifiers. For a re-proven item the Proof of Done
pointer's verified-record link, run identifier, timestamp and freshness
comparison, and the detection of a missing pointer, MUST use the record this
paragraph selects, beside the selected re-prove run's identifier; a later
record that this paragraph excludes MUST NOT make that pointer stale.

*Hand-carried merges.* For a hand-carried merge, a re-prove MUST derive its
graph from the workflow the ordinary variant precedence of §"Self-contained
plugin dispatch" → "Named workflow variants" selects for the item at the time
of the re-prove, the item's `dispatch_workflow` metadata included, and MUST
record that workflow's name in its `resume` record. Because no dispatch-time
snapshot exists, it MUST grade the item's effective Definition of Done as it
stands at the re-prove and MUST record that Definition of Done in its `resume`
record as the re-prove's snapshot. Its proof evidence is selected as *Attribution and
selection* states.

*Evidence a re-prove does not supply.* In both arms a re-prove supplies
evidence to the proof evidence leg only, and MUST NOT supply or replace
merged-diff or run/telemetry evidence. For a hand-carried merge the
run/telemetry leg's evidence is the journaled outcome of the
`reconcile-merged --item` invocation that attributed the merged pull request to
the item and ran its post-merge janitor, naming that pull request and its merge
commit sha: a green outcome is observed-passing, a failing one observed-failing,
and an absent one UNOBSERVED. A re-prove's success MUST NOT stand in for that
outcome. A parking record that names the merged-diff leg or the run/telemetry
leg as pending fails precondition (c).

*After the run.* The Dispatcher MUST journal one `reprove-ending` record
naming the re-prove run's identifiers, the node at which it ended and its
classified cause. Neither the re-prove run nor the disposition of its ending
changes the item's status, though the acceptance pass it runs after `exit`
keeps its ordinary transitions:
every ending other than `exit` (`non_converged`, `needs_human`, a provider-limit
failure, an adapter launch failure, or a cancel) leaves the item at
`acceptance`, the provider-limit release, the adapter launch release and the
watchdog's stall recovery (§"Factory-configurable ACP fallback priority",
§"Dispatcher progress watchdog") do not apply to a re-prove run, and the
re-prove exits `1` as a terminal failed dispatch (§"Dispatcher exit codes").
When the run ends at `exit`, the Dispatcher MUST run the acceptance pass for
the item as `reconcile-merged --item` does, and the re-prove exits as that
pass does. After any other ending the Dispatcher MUST NOT run the acceptance
pass; the item rests at `acceptance` until the next pass, which grades it under
its ordinary rules and the re-prove restriction of its proof evidence leg. *Bounds.* A re-prove MUST count as a resume of the merged pull request:
ordinary resumes and re-proves of the same item and pull request are counted
together, a merge does not reset the count, and the third-resume refusal
applies to that combined count. A re-prove refused on that bound MUST name
maintainer intervention as the remedy, not a plain dispatch, which would cut
an empty branch. Pending host-captured and human-attested legs are graded by their
own rules in every pass and are never supplied by a re-prove. Scenario 208 in
`scenarios.md` exercises this arm.

Conforming edits elsewhere in `contracts.md`:

- The `resume` synopsis MUST gain `[--reprove]`.
- The merged-pull-request refusal bullet MUST gain the exception "except that a resume given `--reprove` is governed by \"Re-proving a merged item\" above", and its statement that `reconcile-merged --item` "stays the only valve" for a merged pull request MUST except the re-prove.
- The third-resume refusal's remedy, a plain dispatch, MUST except a re-prove, whose remedy is maintainer intervention.
- The `proof_verify` routing paragraph of §"Definition-of-Done and Proof-of-Done stages" MUST state that a re-prove run's derived graph overrides its edges for that run only.
- The record clause MUST state that a re-prove run's record names the merge commit in place of the publish-branch head, and that an identifier a `reprove` `resume` record links back to a merging dispatch, or to the merged pull request of a hand-carried merge, is attributable to it.
- The proof evidence leg of §"Post-merge acceptance" MUST accept such an identifier for the merging dispatch of a re-proven item, and for the merged pull request of a re-proven hand-carried merge, and MUST take such a record as evidence only when the re-prove run ended at `exit` and the record names the merge commit sha.
- The run-inventory invariant of §"A factory run never awaits a human" MUST count a live re-prove run whose item rests at `acceptance` as matched, not as an orphan.
- The `proof_verify` paragraph's distinct-adapter rule MUST state that in a re-prove run the comparison is with the adapter that ran that run's `proof_capture`.
- §"Failed engine checkpoint commit attribution" → "A tree that nothing else carries is published to a preservation ref" MUST state that it does not apply to a re-prove run.

In `scenarios.md`, the H2 heading `Scenario 208 — A merged item parked on its proof records is re-proven per assertion on its merged pull request, and nothing else runs` MUST be appended after the last existing scenario, numbered with the next free scenario number at revise time; the assigned number MUST be used consistently in the ratified contract text, the scenario heading and both coverage rows, the heading and this body MUST be added to `scenarios.md` in the same change, and this proposal stays as written as the historical artifact:

```gherkin
Feature: A merged item parked on its proof of done records can obtain fresh factory evidence
  As the maintainer of a factory whose acceptance pass parks an item that merged without graded proof
  I want one bounded route that re-proves that item on its merged pull request
  So that a merged item is accepted on real per-assertion evidence, never on a stale or hand-posted record

  Background:
    Given work item "bd-ib-x1" rests at "acceptance" with acceptance policy "ai-only"
    And its pull request 4000 has merged and the forge reports merge commit "m1"
    And its latest acceptance parking record is "NEEDS_ATTENTION" naming pending proof of done records for factory_captured assertions "A1" and "A2" and no other pending leg
    And no run recorded for "bd-ib-x1" is live, no ownership lock for it is live, and pull request 4000 has anchored no resume

  Scenario: A re-prove captures, verifies and grades on the merge commit, then runs the acceptance pass
    Given "bd-ib-x1" has a merging dispatch whose pull request is 4000
    When "resume --item bd-ib-x1 --reprove" runs and its proof_capture, proof_verify and proof_grade nodes succeed
    Then the run checks out "m1" and visits only start, proof_capture, proof_verify, proof_grade and exit
    And a captured record and a verified record listing "A1" and "A2" as reproduced are posted as new comments on pull request 4000, each naming "m1"
    And the journal holds a "resume" record carrying "reprove: true" and a "reprove-ending" record naming "exit"
    And the acceptance pass runs and judges "A1" and "A2" passing from that verified record

  Scenario: A re-prove pushes nothing and leaves the item's status alone
    When "resume --item bd-ib-x1 --reprove" runs
    Then a re-prove run exists for "bd-ib-x1" on its resolved factory
    And no forge ref is created, updated or deleted
    And "bd-ib-x1" does not pass the admission valve and stays at "acceptance" until the acceptance pass disposes of it

  Scenario: A resume without --reprove still refuses a merged pull request
    When "resume --item bd-ib-x1" runs without "--reprove"
    Then the resume refuses with exit code 3 before any run exists
    And the refusal names the item's "acceptance" status and pull request 4000's merged state, each with its remedy, the latter "reconcile-merged --item"

  Scenario Outline: A re-prove refuses when a precondition fails, naming each failed condition
    Given <changed fact>
    When "resume --item bd-ib-x1 --reprove" runs
    Then the re-prove refuses with exit code 3 before any run exists
    And the refusal names <named condition>
    And the item, its branches and pull request 4000 are unchanged

    Examples:
      | changed fact                                                                      | named condition                                              |
      | "bd-ib-x1" is moved from "acceptance" to "ready" before the re-prove              | the item's status                                            |
      | the parking record instead names an unobservable merged-diff leg as pending       | the pending merged-diff leg and "reconcile-merged --item"    |
      | the parking record instead names only a pending host-captured record              | the absence of a pending factory_captured proof record       |
      | pull request 4000 has already anchored one resume and one re-prove                | the two earlier resumes and maintainer intervention          |
      | an earlier re-prove run for "bd-ib-x1" is still live on its factory               | that run and its factory                                     |

  Scenario: A re-prove's verify adapter differs from its capture adapter
    When "resume --item bd-ib-x1 --reprove" runs
    Then the adapter that runs proof_verify differs from the adapter that ran proof_capture in that run

  Scenario: A verified record naming another commit fails proof_grade
    Given a re-prove run whose newest verified record carrying its own identifiers names a commit other than "m1"
    When proof_grade runs
    Then proof_grade fails naming both commit shas
    And the failure counts as one recorded proof_grade failure

  Scenario: An unreadable merge commit fails proof_grade closed
    Given a re-prove run whose proof_grade cannot read the commit its newest verified record names
    When proof_grade runs
    Then proof_grade fails and the failure counts as one recorded proof_grade failure

  Scenario: The third recorded proof_grade failure ends the re-prove at non_converged
    Given a re-prove run whose proof_grade fails on every visit
    When the run proceeds
    Then the first and second failures re-enter proof_verify through proof_grade_route
    And the third failure ends the run at non_converged

  Scenario: A re-prove that does not reach exit leaves the item at acceptance and changes no ref
    Given a re-prove run that ends at non_converged after a failed engine checkpoint carrying no terminal patch
    When the Dispatcher records its ending
    Then the journal holds a "reprove-ending" record naming non_converged and its classified cause
    And "bd-ib-x1" stays at "acceptance", no acceptance pass runs and the re-prove exits 1
    And no preservation ref or any other forge ref is created

  Scenario: The acceptance pass takes the latest eligible re-prove's record and ignores ineligible ones
    Given pull request 4000 carries the merging run's record-wide verified record
    And a first re-prove that ended at "exit" whose verified record names "m1" and lists "A1" and "A2" as reproduced
    And a later re-prove that ended at non_converged whose verified record lists "A1" as not reproduced
    When "reconcile-merged --item bd-ib-x1" runs the acceptance pass
    Then the pass judges "A1" and "A2" passing from the first re-prove's verified record
    And the Proof of Done pointer names the first re-prove's run identifier

  Scenario: A live re-prove whose item rests at acceptance is not an orphan
    Given a re-prove run for "bd-ib-x1" is live on its factory
    When the run-inventory reconciliation runs
    Then that run is counted as matched and is not cancelled

  Scenario: A pending host-captured leg does not block a re-prove and stays pending after it
    Given the parking record also names a pending host-captured record for assertion "H1"
    And no host_verified record for "H1" is posted
    When "resume --item bd-ib-x1 --reprove" runs and ends at exit with "A1" and "A2" verified
    Then the acceptance pass judges "A1" and "A2" passing
    And "H1" is still pending and "bd-ib-x1" stays at "acceptance"

  Scenario: A hand-carried merge is re-proven against the pull request reconcile-merged attributes to it
    Given "bd-ib-x1" has no journaled dispatch whose pull request merged
    And "reconcile-merged --item bd-ib-x1" attributes pull request 4000 to it
    When "resume --item bd-ib-x1 --reprove" runs
    Then the run checks out "m1"
    And the "resume" record carries "hand_carried: true", pull request 4000, "m1" and the workflow the variant precedence selects for "bd-ib-x1"
    And the captured and verified records are posted on pull request 4000 naming "m1"

  Scenario: A hand-carried re-prove is graded on the current Definition of Done
    Given "bd-ib-x1" has no journaled dispatch whose pull request merged
    And its Definition of Done was edited after pull request 4000 merged and still parses to gradeable assertions "A1" and "A2"
    When "resume --item bd-ib-x1 --reprove" runs and ends at exit with "A1" and "A2" verified
    Then the re-prove is not refused for a changed Definition of Done
    And its "resume" record names the edited Definition of Done as the re-prove's snapshot
    And the acceptance pass judges "A1" and "A2" passing from the re-prove's verified record
```

`tests/heading-coverage.json` and `tests/heading-coverage-debt.json` MUST gain one owned TODO row each for the Scenario 208 heading, naming bd-ib-opd3hq.
