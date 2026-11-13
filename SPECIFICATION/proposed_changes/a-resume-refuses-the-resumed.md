---
topic: a-resume-refuses-the-resumed
author: claude:factory-run-work-preservation plan seat session 82a995
created_at: 2026-11-13T13:41:13Z
---

## Proposal: A publication is bound to its run on the pull request, so a resume never refuses the resumed run's own published head

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add one paragraph to contracts.md §"Self-contained plugin dispatch", directly after "**Scripted publication and proof-head integrity.**". Each push of a run's publish branch by `publish_draft` or `pr_refresh` posts one *publication record* on the item's pull request. The record names the run id, the commit the push ACTUALLY placed at the branch tip (the folded commit when the pending factory-engine-checkpoint-commits-fabro proposal folds), the pull request, the pushing stage and the UTC push time. It lives on the forge, so every host reads the same attribution whatever its own dispatch journal holds. Amend the attribution sentence of §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work" so the publication record attributes a published head first, the existing proof-record and journal readings remain the fallback, and a head attributed to the compared ref's own run needs no journal order. Add six scenarios to Scenario 323; no heading changes. FLEET SCOPE: the shared Dispatcher and the bundled implement-work-item publication stages, so every factory-target repository.

### Motivation

bd-ib-st4obs (plan factory-run-work-preservation, epic bd-ib-nckst7) is at pending-approval at spec-change tier. Its tier record (spec version 368) reads verdict partial, generalization target ## Factory-configurable ACP fallback priority, linked topic a-resume-refuses-the-resumed. legacy-coordinator-agent (2026-11-13 about 13:35Z) ordered this seat to cut the proposal under that topic. The clause must define the publication binding `publish_draft` writes (run id, the sha it ACTUALLY pushed, the pull request, the time), and the binding must be durable beyond the dispatching host's journal.

THE INCIDENT. On livespec-dev-tooling-2zb3gk, run 01M7ABYWTMN298MYP6HZK7NE21's `publish_draft` opened livespec-dev-tooling#4515 at 40fd82b25 (factory bot, 2026-11-13T12:37:00Z). The resume at `proof_capture` was refused at 13:22:42Z with rc=3 on build f4c05ab80e4e: "publishing-run-unobservable: the published head and preserved ref could not be ordered by run, so the preserved-descendant comparison could not be taken". The same refusal hit livespec-dev-tooling-a4w7qr on 2026-11-11T00:39Z. Each such resume drops to a seeded relaunch, and the run's in-flight proof work is lost.

WHY THE SPEC PRODUCES IT. The recovery paragraph says "The observed published head belongs to the run whose publication record or journal record names that head", and the `resume --item` refusal list grades a ref whose run cannot be established by that paragraph's `publishing-run-unobservable` reading. No clause defines a publication record that a publication stage writes. The shipped reader fills the gap with factory PROOF records: `_dispatcher_resume_observation._publications_of` pairs a head with a run only when a proof record on the pull request declares it, and `_dispatcher_recovery_run_age.published_head_relation` otherwise needs a dispatch-journal row whose `published_head` names it. A run resumed after its own push but before any proof record has neither, so its own head ranks unattributed. A journal row could never close the gap on its own, because the journal is local to the dispatching host.

DESIGN CHOICES, settled here:
- (a) Forge, not ledger. The record is a pull request comment because the publication stages already hold the forge identity that pushes, and every host that can resume the item already reads that pull request's records. A sandbox stage holds no ledger credential.
- (b) The pushed commit, read back. The record names what the push placed at the tip, read from the push result or origin, never the janitor-passed head. That covers the folded commit of the pending factory-engine-checkpoint-commits-fabro proposal (PR 5159) and any other commit a stage creates in place of that head.
- (c) `pr_refresh` too. `pr_refresh` also moves the publish branch's tip, and a resume after a refresh push meets the same gap. The coordinator's order named `publish_draft`; this proposal extends the same record to `pr_refresh` for the same reason, and the grade may strike that half.
- (d) Identity-checked. Only a record authored by the identity that pushed counts, so a hand-written comment cannot re-attribute a head.
- (e) Best effort. A failed post never changes the stage's outcome; that head then stays unattributed, and the existing `publishing-run-unobservable` refusal still applies to it.
- (f) Not a proof record. No proof reader, gate or budget reads or counts it.

RELATIONSHIP TO IN-FLIGHT WORK (survey 2026-11-13 about 13:40Z: all 22 open `spec/` pull requests and every pending proposal on master). Only factory-engine-checkpoint-commits-fabro (PR 5159) touches what `publish_draft` pushes. This proposal aligns with it and inserts at a different anchor, so the two compose in either revise order. publish-draft-fails-closed-when (PR 5160) adds pull-request adoption after a failed create; a pull request adopted that way is one the record is posted on. No pending proposal edits the attribution sentence.

### Proposed Changes

### 1. `SPECIFICATION/contracts.md` §"Self-contained plugin dispatch": add one paragraph

Insert this paragraph directly AFTER the paragraph that begins "**Scripted publication and proof-head integrity.**" and ends "Scenario 226 in `scenarios.md` exercises this sentence.", and BEFORE the paragraph that begins "**A pull request merged before its refresh.**", separated by one blank line on each side. No existing paragraph changes:

```markdown
**A publication is bound to its run on the pull request.** Each time `publish_draft` or `pr_refresh` pushes a run's publish branch and the push moves that branch's tip on origin, the stage MUST, once the push has succeeded and the item's pull request exists (whether the stage created it, adopted it, or found it open), post on that pull request one *publication record*. A publication record is a pull request comment whose first line is the marker `livespec-publication-record` and which names, one per line, the run id, the full id of the commit the push placed at the publish branch's tip, the pull request number, the stage that pushed, and the UTC time of the push. The commit it names MUST be the commit the push actually sent, read back from the push's result or from origin, and never the head the `janitor` passed. So when a stage pushes a commit it created in place of that head, the record names the commit it created. A publication record MUST be posted through the same forge identity that made the push, and every reader MUST ignore a comment carrying the marker whose author is any other identity. Posting it MUST NOT change the stage's outcome, its exit code or the head it pushed. When the post fails, the stage MUST report in its own recorded output the run, the pushed commit and the failed step, and the run continues; the head is then attributed only as an unbound head is, under §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work". A push that leaves the publish branch's tip unchanged posts no record. The publication record is the publication record that paragraph reads to attribute a published head to its run. Because it lives on the forge, every host that can read the pull request reads the same attribution whatever its own dispatch journal holds. It is not a proof record: no reader of proof records, acceptance pass, proof gate or record budget reads or counts it. Scenario 323 in `scenarios.md` exercises this paragraph.
```

### 2. `SPECIFICATION/contracts.md` §"Factory-configurable ACP fallback priority", section "Recovery from the failed run's preserved work": amend one sentence

In the paragraph that contains the sentence "The observed published head belongs to the run whose publication record or journal record names that head.", replace exactly that sentence with the following text. Nothing else in the paragraph changes:

```markdown
The observed published head belongs to the run whose publication record, as §"Self-contained plugin dispatch" → "A publication is bound to its run on the pull request" defines it, names that head; when more than one publication record names it, the head belongs to the run of the most recently posted one. When no publication record names the head, it belongs to the run whose factory proof record on the pull request declares it or whose journal record names it. A head that this attribution assigns to the same run as the ref it is compared with is that run's own head, and the comparison MUST be taken without a journal order between the two; a dispatch journal that holds no record of that run MUST NOT make the head unattributed. A head that no publication record, proof record or journal record names remains unattributed, and the `publishing-run-unobservable` reading applies to it unchanged.
```

### 3. `SPECIFICATION/scenarios.md` §"Scenario 323 — An earlier run's preserved ref never outranks a newer run's published head": add six scenarios

Append these scenarios at the END of that heading's `gherkin` block, after the scenario "a preserve that does not descend from the published head does not refuse the resume" (whose last step is "Then the route is resume onto H"), separated by one blank line. No existing scenario changes:

```gherkin
  Scenario: a resumed run's own published head is attributed by its publication record
    Given run R's publish_draft pushed head H to the item's open pull request and posted a publication record naming R and H
    And no proof record on the pull request declares H and no dispatch-journal record names H
    And the item's only preserved ref is run R's latest preserved capture
    When the Dispatcher resumes the item
    Then H is attributed to run R
    And the resume does not refuse with publishing-run-unobservable

  Scenario: the attribution does not depend on the resuming host's journal
    Given the same pull request and publication record
    And the Dispatcher resuming the item runs on a host whose dispatch journal holds no record of run R
    When the Dispatcher resumes the item
    Then H is attributed to run R exactly as on the host that dispatched R
    And the resume does not refuse with publishing-run-unobservable

  Scenario: the publication record names the commit the push actually sent
    Given run R's janitor passed head J
    And publish_draft pushed a commit F that it created in place of J, with J's tree
    When publish_draft posts the run's publication record
    Then the record names F as the pushed commit
    And no publication record names J

  Scenario: recovery routing ranks a head bound by a publication record as it ranks one named by a proof record
    Given an item released for recovery whose pull request's current head H is named only by run R's publication record
    When recovery routing grades the item
    Then H is ranked as run R's published head, exactly as when a proof record of run R declares H

  Scenario: a head that nothing attributes still refuses the resume
    Given run R's latest preserved capture on the item and an open pull request whose current head H no publication record, proof record or dispatch-journal record names
    When the Dispatcher resumes the item
    Then the resume refuses with publishing-run-unobservable, naming that measurement

  Scenario: a marker comment from another identity is not a publication record
    Given a pull request comment that opens with livespec-publication-record and names run R and head H
    And its author is not the forge identity that pushed the publish branch
    When the Dispatcher attributes H
    Then that comment is ignored
    And H is attributed only by the other records that name it
```

### 4. Heading coverage

This proposal MUST NOT add, rename or remove any `## ` heading. Change 1 adds a paragraph inside an existing section, change 2 amends one sentence, and change 3 adds scenarios inside an existing scenario heading. `tests/heading-coverage.json` and `tests/heading-coverage-debt.json` therefore MUST NOT change in the revise that ratifies it.
