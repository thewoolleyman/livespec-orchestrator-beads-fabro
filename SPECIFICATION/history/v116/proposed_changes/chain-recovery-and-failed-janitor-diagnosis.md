---
topic: chain-recovery-and-failed-janitor-diagnosis
author: claude-fable-5-1
created_at: 2026-10-08T05:37:24Z
---

## Proposal: Resume a terminated run from its published pull request at its first unfinished stage

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds a Dispatcher `resume --item` surface, specified as a new H3 under §"Dispatcher loop invocation surface" beside `reconcile-merged`, that finishes a run which published a pull request and then terminated: the new run enters the item's workflow at the first stage the earlier run did not complete, on the published branch at the head the proof record names, with the earlier run's captured and verified records attributed to it, and no implement stage. It refuses, naming the mismatch, when the pull request head moved, the earlier run is live, the pull request is closed or merged, or there is nothing to resume from, and refuses rather than proceeds on an unobservable answer. Two supporting amendments: the Proof of Done record names the head it was captured on, and a resume-kind registered variant may leave the nodes before its entry unreached. Scenarios 142 and 143 state the behaviour.

### Motivation

Work item bd-ib-fngpwg (plan definition-and-proof-of-done, epic bd-ib-7sjdzv, requirement carrier R7) was refused at the Definition-of-Done gate on 2026-10-08 (run 01M4CZ739SCMPN5CXRCJCP8EWD) because three of its four assertions — the resume at the first unfinished stage with no implement, the three refusal conditions, and the plain re-dispatch still reclaiming the branch — are governed by no heading: Scenario 138 covers only the acceptance pass and the pointer. Measured three times in two days (bd-ib-qm4luz run 01M44F9E56XCEWZNMVJX4M14Z6, bd-ib-ocjy4t run 01M49TZ44210GSEC8VTFR8VHKP, bd-ib-gp2nt5): a run that published, captured and verified its proof and then died at pr or review had no recovery that kept the proof, because reconcile-merged requires a real merge and a re-dispatch starts at implement. The gate is right; the spec must say the behaviour first.

### Proposed Changes

**1. New H3 in `SPECIFICATION/contracts.md`, under `## Dispatcher loop invocation surface`, inserted immediately after the paragraph ending "`acceptance`, `done`, `pending-approval`, and `active` remain forbidden `move` targets." and immediately after the sibling H3 "Stale publish-branch reclaim before a re-dispatch" proposed below (so the order is reclaim, then resume, then `### Fail-closed cost gate`):**

### Resume from a published pull request (`resume --item`)

The Dispatcher's recovery surface for an item whose earlier run published
a pull request and then terminated before merging it is
`resume --repo <path> --item <work-item-id> [--factory <name>] [--invoker <id>] [--json]`.
A plain re-dispatch of such an item starts at `implement` and spends a
full sandbox rebuilding, re-capturing and re-verifying work that already
exists on the pull request; the resume FINISHES the earlier run instead.
It is a published state-changing entry point and inherits `--invoker`
(§"Journal invoker attribution"). `drive` gains no new action for it;
the `impl:<id>` action remains a plain dispatch.

**What it resumes.** The *earlier run* is the dispatch whose identifier
the latest proof record on the item's open pull request carries, resolved
through the dispatch journal exactly as the acceptance pass attributes a
record (§"Post-merge acceptance (`acceptance → done`)" → "The proof
evidence leg"). The *published head* is the full commit sha that record
names (§"Proof of Done record" → "The record"). The *resumed-at stage* is
the first node of the item's workflow, in graph order, that the earlier
run did not complete with a succeeded outcome. The Dispatcher MUST read
it from the earlier run's record on its factory; when the factory no
longer holds that record it MUST derive it from the records on the pull
request — a `verified` record present: `pr`; a `captured` record present
and no `verified`: `review`; neither: `proof_capture` — and the resume
record MUST name which source decided it.

**What a resume does.** A resume MUST admit the item through the
ordinary admission valve (`ready → active`), hold the dispatch-scoped
ownership lock, declare a dispatch id to the sandbox and journal exactly
as a dispatch does, and MUST additionally journal one `resume` record
before the run exists naming the earlier run's identifiers, the pull
request number, the published head, the resumed-at stage and the source
that decided it. It MUST NOT run the stale publish-branch reclaim above:
the surviving publish branch is the branch the run resumes on, and no
preservation ref is created. The resumed run MUST be a run of the item's
workflow whose sandbox checks out the publish branch at the published
head and which enters the graph at the resumed-at stage; it MUST NOT
visit `dod_gate`, `implement`, or any other node the earlier run
completed, and its run record MUST show no such visit. Whether the
engine is entered at that node directly or through a registered variant
whose entry edge targets it is implementation surface, bounded by
`constraints.md` §"Fabro runtime constraints" (the entry choice MUST NOT
be an `inputs.*` token in an edge condition); a resume-kind registered
variant MAY leave the nodes before its entry unreached by its edges, on
the terms a groom-kind variant may (§"Self-contained plugin dispatch").
Every stage from the resumed-at stage onward MUST run exactly as it does
in a first run: a `review` that requests changes still re-enters
`janitor`, `publish_draft` and `proof_capture` before `review`
(§"Definition-of-Done and Proof-of-Done stages"), and the `pr` node still
rebases and force-pushes only its own branch.

**Attribution.** The earlier run's `captured` and `verified` records are
the resumed dispatch's own: when the journal's `resume` record links the
two, the acceptance pass MUST attribute a record carrying the earlier
run's identifier to the resumed dispatch, so a `verified` record the
earlier run published grades the resumed run's merge, and the Proof of
Done pointer written for a resumed item MUST name the resumed run's
identifier beside the record's own run id (§"Proof of Done record" →
"The pointer"). A record the resumed run publishes carries the resumed
run's identifier as any record does. Nothing else about acceptance
changes: a resumed item closes through §"Post-merge acceptance
(`acceptance → done`)" and Scenario 138 as any other.

**Refusals.** The resume MUST refuse — before any run exists and before
touching any ref — as a precondition error (exit `3`, §"Dispatcher exit
codes"), naming the mismatch and the remedy, when:

- the item's publish branch carries no open pull request, or no proof
  record on it names a head (remedy: a plain dispatch);
- the pull request's current head does not equal the published head,
  naming both shas (remedy: a plain dispatch, which reclaims the
  branch). A `pr` node that rebased and pushed before terminating leaves
  exactly this state, and the refusal is deliberate: proof verified on
  one tree is not proof of another;
- the earlier run is live on its factory, naming the run id and its
  status (remedy: wait for the run to end, or reconcile it per §"A
  factory run never awaits a human");
- the pull request is closed or merged, naming the state. For a merged
  pull request the remedy is `reconcile-merged --item`, which requires a
  real merge and stays the only valve for one.

When the forge cannot report the pull request's head or state, or the
factory cannot report the earlier run's liveness, the resume MUST refuse
naming the measurement it could not take; it MUST NOT proceed on an
unobservable answer. A refusal leaves the item, the branch and the pull
request exactly as they stood.

**Unchanged.** `publish_draft` still pushes a plain fast-forward and
rewrites no other ref; the `pr` node's lease-guarded force push stays the
only rewrite of a publish branch; `reconcile-merged` still refuses an
unmerged pull request; and a plain `dispatch` or `loop` of the same item
still reclaims the stale publish branch under the section above.
Scenario 142 and Scenario 143 in `scenarios.md` exercise this section.

**2. Amendment to `SPECIFICATION/contracts.md` §"Proof of Done record":**

In §"Proof of Done record" → "The record", the sentence beginning "The body MUST contain, per assertion in Definition of Done order:" is preceded by this new sentence:

The body MUST name, once, the full commit sha of the publish-branch head the reproduction steps were executed on; a record whose head is absent cannot anchor a resume (§"Dispatcher loop invocation surface" → "Resume from a published pull request").

**3. Amendment to `SPECIFICATION/contracts.md` §"Self-contained plugin dispatch":**

In §"Self-contained plugin dispatch" → "A registered variant is the reserved workflow's peer, not its exception.", the sentence "A groom-kind variant MUST declare the nodes so the layers resolve but MAY leave `dod_gate`, `publish_draft`, `proof_capture` and `proof_verify` unreached by its edges (§"Definition-of-Done and Proof-of-Done stages")." gains this continuation:

A resume-kind variant (§"Dispatcher loop invocation surface" → "Resume from a published pull request") MUST likewise declare the nodes and MAY leave the nodes before its entry stage unreached by its edges.

**4. New scenarios appended to `SPECIFICATION/scenarios.md` after Scenario 141:**

## Scenario 142 — A run that terminated after publishing is resumed at its first unfinished stage from its pull request, and nothing it completed runs again

```gherkin
Feature: A published run is finished, not rebuilt
  Scenario: The resume enters at the first stage the earlier run did not complete
    Given an item whose earlier run published a draft pull request, published a captured record and a verified record on it, and then terminated at the pr stage
    And the pull request's current head equals the head the verified record names
    And the factory reports the earlier run as terminal
    When the operator drives resume for the item
    Then the item is admitted through the ordinary admission valve and a new run starts
    And the new run's sandbox is a checkout of the publish branch at that head
    And the new run enters the workflow at the pr stage
    And the new run's record shows no visit to dod_gate, implement, janitor, publish_draft, proof_capture, review or proof_verify
    And the dispatch journal carries one resume record naming the earlier run's identifiers, the pull request number, the head and the resumed-at stage
  Scenario: A run that terminated during review resumes at review on the captured record
    Given an item whose earlier run published a draft pull request and a captured record and then terminated while the review node was running
    When the operator drives resume for the item
    Then the new run enters the workflow at the review stage
    And the review node reviews the captured record the earlier run published
    And no implement stage runs
  Scenario: The resumed-at stage falls back to the pull request's records when the factory no longer holds the earlier run
    Given an item whose earlier run was removed from its factory after publishing a draft pull request carrying a captured record and no verified record
    When the operator drives resume for the item
    Then the new run enters the workflow at the review stage
    And the resume record names the pull request's records as the source that decided the stage
  Scenario: The earlier run's records are attributed to the resumed run and the pointer names both
    Given an item resumed from a pull request whose verified record carries the earlier run's identifier
    When the resumed run merges the pull request and the acceptance pass runs
    Then the pass attributes the verified record to the merging dispatch and grades each factory-captured assertion from it
    And the Proof of Done pointer names that record, its run id and the resumed run's identifier
  Scenario: A resume leaves the surviving publish branch alone
    Given an item whose earlier run's publish branch survives on origin with its draft pull request open
    When the operator drives resume for the item
    Then no preservation ref is created and the publish branch is not deleted
    And the dispatch journal carries no publish-branch-reclaim record for the resume
  Scenario: A resumed run's later stages behave as in a first run
    Given a resumed run entered at the review stage whose review requests changes
    When the review_fix node ends with a tree change
    Then the run re-enters janitor, publish_draft and proof_capture before review, exactly as a first run does
```

## Scenario 143 — A resume refuses, naming the mismatch, when the head moved, the earlier run is live, or the pull request is closed or merged

```gherkin
Feature: A resume never continues from a state the records do not describe
  Scenario: The pull request head no longer equals the head the record names
    Given an item whose pull request head differs from the head its latest proof record names
    When the operator drives resume for the item
    Then the resume refuses with a precondition error before any run exists
    And the refusal names both heads and names a plain dispatch as the remedy
    And the item, the publish branch and the pull request are unchanged
  Scenario: The earlier run is still live
    Given an item whose earlier run the factory reports as not terminal
    When the operator drives resume for the item
    Then the resume refuses before any run exists, naming the run id and its status
  Scenario: The pull request is closed
    Given an item whose earlier run's pull request is closed without merging
    When the operator drives resume for the item
    Then the resume refuses before any run exists, naming the pull request state and a plain dispatch as the remedy
  Scenario: The pull request is merged
    Given an item whose earlier run's pull request is merged
    When the operator drives resume for the item
    Then the resume refuses before any run exists, naming the pull request state and reconcile-merged as the remedy
    And reconcile-merged for the item still requires that real merge
  Scenario: Nothing to resume from
    Given an item whose publish branch carries no open pull request, or whose pull request carries no proof record naming a head
    When the operator drives resume for the item
    Then the resume refuses before any run exists, naming what is missing and a plain dispatch as the remedy
  Scenario: An unanswerable measurement is a refusal, not a proceed
    Given the forge cannot report the pull request head, or the factory cannot report whether the earlier run is live
    When the operator drives resume for the item
    Then the resume refuses before any run exists, naming the measurement it could not take
```

**5. Rulings respected.** Records stay append-only pull request comments and the item carries a pointer; `publish_draft` MUST NOT rewrite any other ref and the `pr` node's lease-guarded force push stays the only publish-branch rewrite; `reconcile-merged` MUST still require a real merge; the publish-branch reclaim stays host-side and holds when a run is live. The resume MUST NOT weaken any of these.

**6. Co-edit.** `tests/heading-coverage.json` gains one row per new `## Scenario` heading with `test: "TODO"`, `work_item: "bd-ib-7sjdzv"` and a reason acknowledging the owed integration-tier test; `tests/heading-coverage-debt.json` gains one entry per TODO row with `first_seen: "2026-10-08"`.

## Proposal: A plain re-dispatch reclaims a dead run's stale publish branch, and holds when it cannot measure

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

States, as a new H3 under §"Dispatcher loop invocation surface" and as Scenario 144, the pre-dispatch publish-branch reclaim that bd-ib-yebrb7 shipped and no heading governs: before a re-dispatch's run exists the Dispatcher preserves a dead run's surviving publish branch head on a ref named by the item and the head, deletes the branch, and journals the reclaim; a first dispatch asks origin nothing; and every arm that cannot measure — origin unaskable, factory unaskable, a live run, a failed preserve or delete — leaves the branch alone, journals which measurement stopped it, and never refuses the dispatch. `publish_draft` is unchanged.

### Motivation

bd-ib-fngpwg's fourth assertion — a plain re-dispatch still works and still reclaims the stale publish branch — is ungoverned: the behaviour exists since bd-ib-yebrb7 (PR 2591) but was referenced to Scenario 138, which does not state it, and the only re-dispatch contract in contracts.md is the rework-pending one. The resume surface above is defined against this reclaim (a resume MUST NOT run it), so the reclaim must be ratified in the same revision for the pair to read coherently.

### Proposed Changes

**1. New H3 in `SPECIFICATION/contracts.md`, under `## Dispatcher loop invocation surface`, inserted immediately after the paragraph ending "`acceptance`, `done`, `pending-approval`, and `active` remain forbidden `move` targets." and before the resume H3:**

### Stale publish-branch reclaim before a re-dispatch

A run that terminates AFTER `publish_draft` pushed its branch leaves that
branch on origin. The next dispatch of the same item is a NEW run whose
head is not a descendant of the dead run's tip, so `publish_draft`'s plain
fast-forward push is refused non-fast-forward, and the only remedy that
refusal can name — clear the branch by hand — discards the dead run's
published head and every record attached to it. The Dispatcher therefore
reclaims the branch on the host, before the run exists, as a pre-dispatch
act of both `dispatch` and `loop` for every selected item:

- **Only a re-dispatch asks.** For an item the dispatch journal records
  no earlier dispatch of, the Dispatcher MUST NOT query origin for a
  surviving publish branch: a first dispatch has no possible yes, and a
  remote probe on that path would put a forge outage on the critical path
  of every dispatch. For any other item it MUST ask origin (`ls-remote`,
  never a local remote-tracking ref) whether the item's publish branch
  survives and at which head.
- **A dead run's branch is preserved, then cleared.** When the branch
  survives and the factory reports no live run for the item, the
  Dispatcher MUST first create a preservation ref on origin, named by the
  item id and the surviving head, pointing at that head, and only then
  delete the publish branch. Because the head is part of the ref name,
  preserving the same head twice is a no-op and two different dead heads
  of one item preserve to two refs; the preservation ref MUST NOT be
  updated to a different object. The journal MUST carry one
  `publish-branch-reclaim` record naming the branch, the head and the
  preservation ref. `publish_draft` is unchanged: it still pushes a plain
  fast-forward and rewrites no other ref; the reclaim is a HOST-side act
  because the host is the one party that can answer whether the run that
  pushed the branch is still alive, and the stages clause grants the
  lease-guarded force push to the `pr` node alone.
- **Every arm that cannot measure holds, and says so.** When origin
  cannot be asked, when the factory cannot report the item's run liveness,
  when the factory reports a live run for the item, or when the preserve
  or the delete fails, the Dispatcher MUST leave the branch exactly as it
  stands and MUST journal one `publish-branch-reclaim-held` record naming
  the reason (one of `origin-unobservable`, `factory-unobservable`,
  `live-run`, or the failed ref operation), the branch and head where
  established, and the live run ids on the live-run arm. A hold MUST NOT
  refuse the dispatch: the dispatch proceeds and `publish_draft` refuses
  the non-fast-forward push exactly as it did before the reclaim existed,
  so the worst outcome of the reclaim is the refusal it was added to
  remove. A reclaim MUST NOT proceed on an unobservable answer, because a
  gauge that proceeds when blinded turns an honest refusal into a silent
  ref deletion whose record reads like a healthy reclaim.
- **Acceptance attribution survives the reclaim.** A verified record the
  dead run published on the pull request the reclaim closes remains
  attributable to that dead dispatch under §"Post-merge acceptance" →
  "The proof evidence leg"; the reclaim changes which branch the NEXT run
  publishes, never which dispatch a record belongs to.

Scenario 144 in `scenarios.md` exercises this section. The resume surface
below is the route that KEEPS the dead run's work; this reclaim is the
route that makes a fresh start possible without a hand edit, and a resume
MUST NOT run it.

**2. New scenario appended to `SPECIFICATION/scenarios.md` after Scenario 143:**

## Scenario 144 — A plain re-dispatch of an item whose run died after publishing reclaims the stale publish branch and holds when it cannot measure

```gherkin
Feature: A dead run's publish branch does not block the item's next dispatch, and is never deleted blind
  Scenario: The dead head is preserved and the branch cleared before the run exists
    Given an item the dispatch journal records an earlier dispatch for
    And origin carries the item's publish branch at the head that dispatch pushed
    And the factory reports no live run for the item
    When the item is dispatched again through dispatch or loop
    Then before the run exists a preservation ref named by the item and that head is created on origin at that head
    And the publish branch is deleted on origin
    And the dispatch journal carries a publish-branch-reclaim record naming the branch, the head and the preservation ref
    And the new run's publish_draft stage pushes a plain fast-forward and opens a draft pull request
  Scenario: Reclaiming the same head twice rewrites nothing
    Given a preservation ref already exists for the item at the surviving head
    When the reclaim runs again for that head
    Then the preservation ref is unchanged and the reclaim completes
  Scenario: A first dispatch asks origin nothing
    Given an item the dispatch journal records no dispatch for
    When the item is dispatched
    Then no query to origin for a surviving publish branch is made
  Scenario: A live earlier run holds the reclaim
    Given an item whose earlier run the factory reports as not terminal
    When the item is dispatched again
    Then the publish branch is left exactly as it stands
    And the dispatch journal carries a publish-branch-reclaim-held record naming the reason live-run and the live run id
    And the dispatch proceeds and publish_draft refuses the non-fast-forward push as it did before the reclaim existed
  Scenario: Every measurement that cannot be taken holds
    Given origin cannot be asked whether the branch survives, or the factory cannot be asked whether the run is live, or the preserve or the delete fails
    When the item is dispatched again
    Then the publish branch is left exactly as it stands
    And the dispatch journal carries a publish-branch-reclaim-held record naming which measurement stopped the reclaim
    And the dispatch is not refused by the reclaim
  Scenario: The reclaim is a host-side act and publish_draft is unchanged
    Given a dispatched run whose publish_draft stage runs
    When it pushes the publish branch
    Then the push is a plain fast-forward and no other ref is rewritten
```

**3. Co-edit.** One `tests/heading-coverage.json` TODO row and one `tests/heading-coverage-debt.json` entry for Scenario 144, as for the resume scenarios.

## Proposal: A failed post-merge janitor retains its complete output and exit code as a private artifact the journal names

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds, as a new H3 under §"Dispatcher admission, WIP cap, and post-merge acceptance" placed after §"Dispatch preflight and post-merge step discipline", and as Scenario 145, the retention of a failed post-merge janitor's complete stdout, stderr and exit code as a private artifact outside the disposable checkout, under the dispatch-journal directory, at a path unique to the dispatch, the stage and the retention; the journal row names the path and the artifact's sha256 beside the existing tail; a retained artifact is never overwritten; a write failure is journaled with its reason and changes neither the verdict nor the command's argv, environment, umask or exit code; a passing janitor retains nothing extra; and the artifact's content never reaches a ledger comment, pull request comment or dispatch result.

### Motivation

Work item bd-ib-nezrrh (plan definition-and-proof-of-done, epic bd-ib-7sjdzv, requirement carrier R7, chain breakages and their diagnosis) is referenced to Scenario 138, which does not state it, and would be refused at the Definition-of-Done gate on the same ground as bd-ib-fngpwg. Measured on gate 20261007T142403Z-3604049 (reconcile-merged of overseer-ssjzmo, failed 2026-10-07T14:37:09Z): the retained journal carried no failing-check traceback and the check cache was empty, so the cause of a red post-merge janitor on an already-merged item could not be established from the record. bd-ib-eh6xaa (closed) fixed which stream the tail keeps; the kept checkout remains the deep-diagnosis route; neither survives the checkout's removal.

### Proposed Changes

**1. New H3 in `SPECIFICATION/contracts.md`, under `## Dispatcher admission, WIP cap, and post-merge acceptance`, inserted immediately before `### Repository integration contract` (that is, at the end of §"Dispatch preflight and post-merge step discipline"):**

### Failed post-merge janitor output retention

A post-merge janitor's journal row carries a TAIL of each captured
stream, which is enough to see that the janitor was red and not enough
to see why: the failing target of an aggregate check suite is named once,
on whichever stream the tail did not keep, and the disposable checkout
the janitor ran in is the only other place the diagnosis lived. The
Dispatcher therefore retains a failed janitor's complete output:

- **A non-zero exit retains everything the runner captured.** When the
  post-merge janitor command — on the dispatch path or under
  `reconcile-merged` — exits non-zero, the Dispatcher MUST write one
  artifact carrying the command's complete captured stdout, its complete
  captured stderr and its exit code, as the text the runner captured
  (text mode; no claim of raw byte identity), to a path OUTSIDE the
  janitor checkout, under the directory that holds the dispatch journal,
  unique to the dispatch id and the stage, and the journal row for the
  stage MUST carry, beside the existing tail and detail, the artifact's
  path and the digest of the artifact's bytes (`sha256`), so a reader can
  prove the artifact is the one the row names.
- **An artifact is never overwritten.** The path MUST be unique per
  retention, not merely per stage: a second non-zero exit of the same
  stage in the same dispatch retains a second artifact under its own
  path, each journal row naming its own, and a retained artifact MUST
  NOT be modified or replaced afterwards.
- **A write failure is journaled and changes nothing else.** When the
  artifact cannot be written, the journal row MUST say so and name the
  reason; the stage's verdict, the item's disposition, and the janitor
  command's argv, environment, umask and exit code MUST be exactly what
  they are without retention. Retention observes the command; it never
  shapes it.
- **A zero exit retains nothing extra.** A janitor command that exits
  zero MUST retain no artifact, and its row carries no artifact path.
- **The artifact is private to the dispatch.** Its content MUST NOT be
  copied into a ledger comment, a pull request comment or the dispatch
  result; those surfaces carry the row's path and digest at most. The
  journal tail stays as it is, and the kept checkout remains the
  deep-diagnosis route; the artifact is what survives the checkout's
  removal.

This clause changes no step outcome of §"Dispatch preflight and
post-merge step discipline": a red janitor leaves the item exactly as it
did. Scenario 145 in `scenarios.md` exercises this section.

**2. New scenario appended to `SPECIFICATION/scenarios.md` after Scenario 144:**

## Scenario 145 — A failed post-merge janitor retains its complete output and exit code as a private artifact the journal names

```gherkin
Feature: A red post-merge janitor can be diagnosed from what it retained
  Scenario: A non-zero janitor retains both complete streams and the exit code
    Given a post-merge janitor command that writes distinct stdout and stderr each longer than the journal tail and exits with a distinctive non-zero code
    When the Dispatcher runs the post-merge janitor for a dispatch
    Then an artifact exists outside the janitor checkout under a path unique to the dispatch and the stage
    And the artifact carries the complete captured stdout, the complete captured stderr and that exit code
    And the journal row for the stage carries the existing tail, the artifact path and the artifact's content digest
    And the digest of the artifact's bytes equals the digest the row names
  Scenario: A second failure retains a second artifact
    Given a dispatch whose post-merge janitor stage already retained an artifact
    When the same stage fails again in the same dispatch
    Then a second artifact exists under its own path and the first is byte-identical to what it was
    And each journal row names its own artifact
  Scenario: A write failure is journaled and changes nothing else
    Given the artifact location cannot be written
    When a post-merge janitor command exits non-zero
    Then the journal row for the stage says the artifact was not retained and names the reason
    And the stage's verdict is what it would be without retention
    And the command's argv, environment, umask and exit code are what they would be without retention
  Scenario: A passing janitor retains nothing extra
    Given a post-merge janitor command that exits zero
    When the Dispatcher runs the post-merge janitor
    Then no artifact is written for the stage and the journal row carries no artifact path
  Scenario: The reconcile-merged janitor is covered the same way
    Given reconcile-merged driven for an item whose post-merge janitor exits non-zero
    When the janitor stage is journaled
    Then the row names a retained artifact exactly as the dispatch path's row does
  Scenario: The artifact stays private to the dispatch
    Given a retained artifact
    When the dispatch completes
    Then no ledger comment, pull request comment or dispatch result carries the artifact's content
```

**3. Co-edit.** One `tests/heading-coverage.json` TODO row and one `tests/heading-coverage-debt.json` entry for Scenario 145.
