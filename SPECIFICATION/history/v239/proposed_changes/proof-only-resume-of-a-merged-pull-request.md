---
topic: proof-only-resume-of-a-merged-pull-request
author: claude-opus-5-5
created_at: 2026-10-27T00:39:28Z
---

## Proposal: A merged item parked on its proof leg is re-proven by a proof-only resume on its merged pull request

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

In 'Resume from a published pull request': a merged item parked NEEDS_ATTENTION by the proof evidence leg (missing proof on the merged head, or a record-wide verdict) takes a proof-only arm instead of the merged-pull-request refusal. The arm runs only proof_capture, proof_verify and proof_grade read-only against the merged head, posts records bound to the item, that pull request and the merged head, and re-runs acceptance. Every other merged item still refuses.

### Motivation

Routed by petri-factory-on-gmktec under coordinator gitops-fleet-capacity-monitoring rulings R76 and R77(C), spec-first for work-item bd-ib-opd3hq (backlog, spec-change first). That item was filed 2026-10-18 under ruling R192 for a merged item parked on a RECORD-WIDE proof verdict: resume --item refuses a merged pull request, reconcile-merged re-reads the stale record and parks again, and a hand-posted record is not factory evidence. Its rider of 2026-10-26T23:53Z widens it to a merged item parked NEEDS_ATTENTION for MISSING proof. Instances: bd-ib-svm3fe, whose pull request 3731 merged at 22:30:05Z with zero Proof of Done records, was parked by reconcile-merged on its proof leg and had to be accepted by hand as human:cwoolley; and the bd-ib-q156 / bd-ib-hu67v5 class, where v226's merged-reconcile ending writes no proof record by design, so its merged head is always unproven unless this route exists. The arm reuses v230's binding and record reader, and v237's broker carries its record posts.
A first read-only Codex review raised three blockers, folded in: the arm's explicit exemptions from refusals that assume an unmerged ready item (with its own anchor and journal provenance, keeping the liveness, lock, observability and two-resume refusals); an amendment to 'The binding' permitting the arm's new factory records after merge bound to the pull request's head at merge; and an acceptance-disposition exception so a not-reproduced assertion parks the item without rework under any policy.
A second pass required the arm's routing to be stated per outcome (capture to verify, verified to grade, every other outcome to the end), which is folded in.

### Proposed Changes

1. In `SPECIFICATION/contracts.md`, §"Dispatcher loop invocation surface" → "### Resume from a published pull request (`resume --item`)", after the paragraph that ends "A refusal leaves the item, the branch and the pull request exactly as they stood.", insert immediately after the text

```
MUST NOT proceed on an unobservable answer. A refusal leaves the item,
the branch and the pull request exactly as they stood.
```

the following new paragraph (separated by one blank line):

```
**A proof-only resume of a merged pull request.** When the item's pull request is merged and the item rests in `acceptance` parked NEEDS_ATTENTION by the proof evidence leg of the acceptance pass because no applicable counted `proof_verify` record grades each of its `factory_captured` assertions on the merged head, whether no such record exists or the record it was graded on carries no per-assertion verdict, `resume --item` MUST take the proof-only arm instead of refusing on the merged pull request. An item parked for an `unbindable` record is not in this case; its clearing action is a superseding record. The arm is exempt from the refusals that assume an unmerged item resting in `ready`: the item rests in `acceptance` and stays there throughout, it needs no open pull request, no anchoring proof record and no published-head match, and it makes no claim through admission. Its anchor is the confirmed merged pull request, that pull request's head commit at merge, and the parking record that names the proof leg, and the dispatch journal MUST record those three as the resume's provenance. The refusals for a live earlier run, a live ownership lock, a measurement the resume cannot take, and the two-resume limit still apply. The arm MUST check out the pull request's head commit at merge, never the default-branch merge commit, read-only, and MUST run only `proof_capture`, `proof_verify` and `proof_grade` against it: a successful capture routes to `proof_verify`, a `verified` outcome routes to `proof_grade`, and every outcome of `proof_grade` and every other outcome of capture or verification ends the run. The arm's graph MUST carry no edge to any stage outside those three, apart from ending the run. It MUST run no implement, review, janitor, publication or merge stage, MUST push nothing and MUST open no branch or pull request. The run is associated with the existing pull request, so that the proof broker of "Publication is mechanically confined to the scripted publication stages" posts its records there. Every record the arm publishes MUST be posted as a new comment on the existing merged pull request through the posting primitive, bound by "Proof of Done record" → "The binding" to the item, that pull request and its head commit at merge, and carrying the resumed run's identifier. A `proof_verify` record the arm publishes MUST carry each `factory_captured` assertion's own `Reproduced:` line, graded by the same `proof_grade` node the implement workflow uses. When the arm ends, the Dispatcher MUST re-run the acceptance pass for the item, as `reconcile-merged` does, and that pass reads the new records by their binding through the same Proof of Done record reader that grades them. The acceptance pass that follows the arm is a re-run of a parked item. When it fails an assertion the arm did not reproduce, the item MUST stay in `acceptance` with a parking record naming each such assertion and the arm's record. That pass MUST NOT stamp rework, move the item to `blocked`, or count toward the rework cap, whatever the item's acceptance policy, and the arm never routes to `fix`. The arm counts toward the pull request's two-resume limit. Measured 2026-10-26: bd-ib-svm3fe's pull request 3731 merged with no Proof of Done record, reconcile-merged parked it NEEDS_ATTENTION on its proof leg, and it had to be accepted by hand; the merged-reconcile ending of "A pull request merged before its refresh" writes no proof record by design, so every item it ends leaves its merged head unproven unless this arm exists. Scenario 257 in `scenarios.md` exercises this paragraph.
```

2. In `SPECIFICATION/contracts.md`, replace

```
binding to that pull request resolves the fault of the record it names. The
acceptance pa
```

with

```
binding to that pull request resolves the fault of the record it names. A
proof-only resume of a merged pull request (§"Dispatcher loop invocation
surface" → "A proof-only resume of a merged pull request") MAY also post new
factory records after merge on that pull request, each carrying the resumed
run's identifier and binding the pull request's head commit at merge. The
acceptance pa
```

3. In `SPECIFICATION/contracts.md`, replace

```
- the pull request is closed or merged, naming the state. For a merged
  pull request the remedy is
```

with

```
- the pull request is closed, or it is merged and the item is not in the
  case of "A proof-only resume of a merged pull request" below, naming the
  state. For a merged
  pull request the remedy is
```

4. In `SPECIFICATION/scenarios.md`, replace

```
  Scenario: The pull request is merged
    Given an item whose earlier run's pull request is merged
```

with

```
  Scenario: The pull request is merged
    Given an item whose earlier run's pull request is merged, and that is not parked in acceptance on its proof evidence leg
```

5. In `SPECIFICATION/scenarios.md`, append:

````
## Scenario 257 — A merged item parked on its proof leg is re-proven by a proof-only resume on its merged pull request

```gherkin
Feature: A merged item whose proof is missing or record-wide is re-proven without republishing
  Scenario: A merged item with no verified record is re-proven on its merged head
    Given an item whose pull request merged with no Proof of Done record on its merged head
    And the item rests in acceptance parked NEEDS_ATTENTION by the proof evidence leg
    When the operator drives resume for the item
    Then the resume takes the proof-only arm and runs only proof_capture, proof_verify and proof_grade against the merged head
    And it pushes nothing and opens no branch or pull request
    And its records are posted on the merged pull request bound to the item, that pull request and the merged head
    And the acceptance pass then reads the new verified record and grades each factory_captured assertion from it

  Scenario: The proof-only arm visits its three stages in order and nothing else
    Given a proof-only arm whose capture succeeds and whose verification returns verified
    When the run executes
    Then it visits proof_capture, then proof_verify, then proof_grade, and then ends
    And it visits no other stage

  Scenario: A merged item parked on a record-wide verdict is re-proven per assertion
    Given an item whose pull request is merged and whose only verified record carries no per-assertion Reproduced lines
    And the item rests in acceptance parked NEEDS_ATTENTION by the proof evidence leg
    When the operator drives resume for the item
    Then the proof-only arm publishes a verified record with a Reproduced line in each factory_captured assertion's section

  Scenario: A merged item not parked on its proof leg still refuses
    Given an item whose pull request is merged and that is not parked in acceptance on its proof evidence leg
    When the operator drives resume for the item
    Then the resume refuses with exit code 3, naming the pull request state and reconcile-merged as the remedy

  Scenario: An assertion the arm does not reproduce leaves the item parked under every policy
    Given a proof-only arm whose proof_verify lists one factory_captured assertion as not reproduced
    And the item's acceptance policy is ai-only, ai-then-human or human-only
    When the acceptance pass re-runs
    Then the item stays in acceptance with a parking record naming that assertion and the arm's record
    And no rework is stamped, the rework cap is unchanged, and no fix stage runs

  Scenario: The proof-only arm needs no proof record and no open pull request
    Given a merged item parked on its proof leg whose publish branch was deleted and which has no Proof of Done record at all
    When the operator drives resume for the item
    Then the resume takes the proof-only arm, anchored on the merged pull request, its head commit at merge and the parking record
    And the item stays in acceptance

  Scenario: A third resume of the same pull request is refused
    Given a merged pull request that has already anchored two resumes
    When the operator drives resume for its item parked on its proof leg
    Then the resume refuses naming the two earlier resumes
```
````

6. Add a TODO row for the new heading to `tests/heading-coverage.json` and a matching debt row to `tests/heading-coverage-debt.json`, both owned by the implementing work-item bd-ib-opd3hq.
