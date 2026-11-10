---
topic: a-goal-carries-a-bounded-rider-set
author: claude-opus-5-5:publish-draft-green-work-loss
created_at: 2026-11-09T19:01:13Z
---

## Proposal: A goal carries the riders added since the item's last dispatch, plus standing and stage-scoped riders

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Bound the set of ledger comments that a rendered goal, and therefore the Definition-of-Done judgement subject, carries as riders. Today every ledger comment that is not a receipt is a rider forever, so an item's goal and subject grow with its whole history. This proposal makes a rider CARRIED only when it was added after the item's most recent dispatch claim, when its first line scopes it to stages, or when its first line marks it as standing. Every other comment stays on the ledger as evidence. The goal states how many comments it left out and how to read them.

### Motivation

Carrier: bd-ib-y6tcni. Measured 2026-11-09 on build 456712f1af12. bd-ib-uq2ocd carried 88 ledger comments totalling 1,628,501 characters (about 407k tokens). Every host taking of its Definition-of-Done judgement ended at the 100,000-token input bound (`HOST_JUDGEMENT_INPUT_LIMIT`): dod-preflight printed DID-NOT-RUN input-limit-reached and exited 2 on two consecutive runs, while filing_display on the same text reported no findings. Across 6,687 non-closed items in the nine family beads tenants, ready items carry rider characters p50 1,861, p99 41,577 and max 71,396. 103 items carry over 100k characters, 19 exceed the bound outright, and the active livespec-dev-tooling-e62ss6 (260,576 characters) and livespec-dev-tooling-6lv7ze (245,242 characters) are on the way. Measured spend (token-spend-analysis, 72 h to 2026-11-09, corrected 19:xxZ): riders cost about $17-37 of $2,001 of factory spend and $6.7-27.7 of dod-gate spend. Riders were 91% of e62ss6's judgement prompt. The bound pays in AVAILABILITY: comments are append-only, so an item past the bound can never be judged again. It also pays secondarily in spend. Rule K, the tenants whose Dispatcher builds riders from ledger comments and which this clause therefore governs: livespec, livespec-console-beads-fabro, livespec-dev-tooling, livespec-driver-claude, livespec-driver-codex, livespec-driver-pi, livespec-orchestrator-beads-fabro, livespec-overseer and livespec-runtime. Prior art: bd-ib-40vz and spec v192's rendered-goal size advisory WARN about goal growth but bound nothing. This proposal is the bound, and it leaves the advisory in force.

### Proposed Changes

In `contracts.md` §"Dispatch-brief lessons injection", immediately after the paragraph "**Work-item riders are scoped to the stages they name.** ...", insert this paragraph:

**A goal carries a bounded rider set.** Of the ledger comments that are riders (every comment the receipt rule of "One rubric, one subject" does not omit), the Dispatcher MUST carry into a rendered goal exactly those that are CARRIED. A rider is CARRIED when ANY of the following holds:

- it was appended after the item's most recent dispatch claim, or the item has never been claimed for a dispatch;
- its first line names stages in the form `FOR <stage>[, <stage>...] ONLY:`;
- its first line begins `STANDING RIDER:`.

The stage-scoping rule above then decides which stage's brief each carried rider reaches. A rider that is not carried MUST stay on the item's ledger unchanged and MUST NOT appear in any rendered goal or in any judgement subject. When the Dispatcher leaves out at least one rider, the goal's operator-rider section MUST state, in one line, how many ledger comments it left out, the creation time of the newest one, and the command that lists the item's full ledger comments. That line is the same for every stage of one dispatch. The dispatch claim that bounds the set is the one the dispatch being rendered follows, so the claim a dispatch takes MUST NOT move the bound for that same dispatch's goal.

In `contracts.md` §"Effective acceptance criteria" → "One rubric, one subject", in the GOAL bullet, replace the clause "and every ledger comment except the Definition-of-Done JUDGEMENT RECORDS" with "and every CARRIED rider, as §\"Dispatch-brief lessons injection\" → \"A goal carries a bounded rider set\" defines it, which excludes the Definition-of-Done JUDGEMENT RECORDS". Replace "A ledger comment added after filing that is none of these records remains in the rendered goal's operator-rider section." with "A ledger comment added after filing that is none of these records is a rider, and the rendered goal's operator-rider section carries it while it is CARRIED." A comment that is not carried MUST NOT change any subject digest, so a verdict recorded on identical carried riders remains reusable.

In `scenarios.md` §"Scenario 268 — A work-item rider reaches only the stages it names", append these scenarios inside the existing gherkin block. The H2 heading is unchanged:

```gherkin
  Scenario: a rider appended before the item's last dispatch claim is left out of the next goal
    Given a work item claimed for a dispatch at time T
    And a rider that names no stage, appended before T, whose first line does not begin STANDING RIDER:
    And a second rider that names no stage, appended after T
    When the Dispatcher renders the implement brief for the item's next dispatch
    Then the brief carries the second rider and not the first
    And the operator-rider section states that it left out 1 ledger comment, the first rider's creation time, and the command that lists the item's ledger comments
    And the first rider is still on the item's ledger

  Scenario: standing and stage-scoped riders are carried whatever their age
    Given a work item claimed for a dispatch at time T
    And a rider appended before T whose first line begins STANDING RIDER:
    And a rider appended before T whose first line is FOR proof_capture ONLY:
    When the Dispatcher renders the briefs for the item's next dispatch
    Then the implement and review_fix briefs carry the standing rider
    And the proof_capture brief carries the stage-scoped rider

  Scenario: an item never claimed for a dispatch carries every rider
    Given a work item that has never been claimed for a dispatch, carrying three riders that name no stage
    When the Dispatcher renders the implement brief for its first dispatch
    Then the brief carries all three riders and states no left-out count
```

In `scenarios.md` §"Scenario 239 — Every taking of the Definition-of-Done judgement grades one subject by one rubric", append this scenario inside the existing gherkin block. The H2 heading is unchanged:

```gherkin
  Scenario: A comment that is not carried does not change the subject digest
    Given an item claimed for a dispatch at time T, with a recorded pre-dispatch verdict on subject digest D
    And a rider appended before T that is neither standing nor stage-scoped
    When the pre-dispatch judgement is taken for the item's next dispatch with no rider appended after T
    Then the subject digest is D
    And the recorded verdict is reused without running a judge
```

## Proposal: A rendered goal carries each carried rider once

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

From v0.310.0, the node's rendered goal appends the shared Definition-of-Done judgement subject so that the dod_gate node grades the same subject as the host takings (a311c2391). That subject carries its own riders section, so every rider now reaches every ACP node of a dispatch twice. This proposal requires each carried rider to appear exactly once in a rendered goal, whichever part of the goal carries it.

### Motivation

Carrier: bd-ib-y6tcni. On origin/master and the released v0.310.0, `_dispatcher_goal.py` returns `body + verdict_block + shared_subject`. The body holds the "Ledger comments (operator riders ...)" section, and `shared_subject` is `judgement_subject(...)`, which carries a second riders section over the same comments. Builds up to 456712f1af12 (v0.309.2) carry each rider once, measured on the run.started goal of bd-ib-n4kj4y run 01M6WWJPS09C. Measured 2026-11-09 by rendering bd-ib-qshcwc's goal with v0.310.0's own `render_goal`, because no host had yet registered v0.310.0, so no live run existed to read. The goal grew from 24,910 to 136,040 characters. It carried one 'Ledger comments (operator riders appended ...' heading, one 'operator riders; part of the brief' heading inside the appended '## Definition-of-Done judgement subject', and the probe rider 'RESTORE RIDER + ORDERING' twice. Fabro injects the whole goal into every ACP node, so the duplicate rides in the cached prefix of every request. token-spend-analysis measured the factory rider cost on single rendering at about $17-37 of $2,001 over 72 h; doubling it adds the same again on every dispatch from v0.310.0. No ratified sentence requires the duplicate: "One rubric, one subject" requires the node to grade the subject, not to receive the riders twice. Rule K tenants: as in the first proposal of this file.

### Proposed Changes

In `contracts.md` §"Effective acceptance criteria" → "One rubric, one subject", after the GOAL bullet's sentence "The Dispatcher MUST omit them from the node's rendered goal as well, and recording any of them MUST NOT change any subject digest.", insert:

"A rendered goal MUST carry each carried rider's text exactly once. When the Dispatcher includes the judgement subject in the node's rendered goal, the subject's rider section and the goal's operator-rider section MUST NOT both carry the riders: the rendered goal MUST carry one of the two, and the subject digest MUST be computed over the subject as this paragraph defines it, unchanged by where the rendered goal places the riders."

In `scenarios.md` §"Scenario 239 — Every taking of the Definition-of-Done judgement grades one subject by one rubric", append inside the existing gherkin block. The H2 heading is unchanged:

```gherkin
  Scenario: The node's rendered goal carries each rider once
    Given a ready item carrying one carried rider whose text is unique on the item
    When the Dispatcher renders the dod_gate node's goal for a dispatch of the item
    Then that rider's text occurs exactly once in the rendered goal
    And the subject digest equals the digest a host taking computes for the same item
```

## Proposal: A judgement ended by the input bound is a named did-not-run cause and an unpreflightable hygiene fact

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Name the input bound as a cause for which a Definition-of-Done judgement cannot be run, beside no eligible model, a timeout and an unparseable reply. Require the did-not-run record to state the subject's size. Have needs-attention list an item whose latest host taking was ended by the bound as an unpreflightable hygiene fact, so the condition is surfaced and not merely recorded.

### Motivation

Carrier: bd-ib-y6tcni. The ratified cannot-run causes are "no eligible model, a timeout or an unparseable reply". The bound is already counted by "Every host taking is journaled with its input size" ("each candidate the bound ended"), and the implementation records cause `input-limit-reached`, but no cannot-run sentence names it. On bd-ib-uq2ocd the preflight exited 2 with DID-NOT-RUN input-limit-reached, and nothing told an operator the item had become unjudgeable rather than briefly unlucky. A bound-ended taking is not a transient: comments are append-only, so the next taking of the same item ends the same way until a rider bound or a new dispatch claim shrinks the subject. The coordinator's direction (legacy-coordinator-agent, 2026-11-09) is that such an item be graded as unpreflightable, not silently refused. A did-not-run outcome stays never a refusal, as ratified. Rule K tenants: as in the first proposal of this file.

### Proposed Changes

In `contracts.md` §"Effective acceptance criteria" → "One rubric, one subject", in the TAKING paragraph, replace "When any candidate cannot return a verdict (no eligible model, a timeout or an unparseable reply)" with "When any candidate cannot return a verdict (no eligible model, a timeout, an unparseable reply, or the input bound ending it)". After "the record it appends is a did-not-run record naming that candidate and the cause.", add: "When the cause is the input bound, the record MUST also state the subject's size in characters."

In `contracts.md` §"Dispatcher admission, WIP cap, and post-merge acceptance", in each of the paragraphs "Judged before admission" and "Judged again before dispatch", replace "(no eligible model, a timeout, or an unparseable verdict)" with "(no eligible model, a timeout, an unparseable verdict, or the input bound ending every candidate)". The routes those paragraphs give an unrun judgement are otherwise unchanged.

After the paragraph "**Every host taking is journaled with its input size.**", insert:

"**An item whose judgement the input bound ended is listed as unpreflightable.** When the most recent host taking of an item's Definition-of-Done judgement did not run because the input bound ended every candidate, `needs-attention` MUST list the item as a hygiene fact naming it as unpreflightable, with the subject's size in characters and the number of riders the subject carried. The fact MUST clear once a later host taking of that item runs a judge. Listing the fact MUST NOT change the item's lifecycle state, and MUST NOT be treated as a refusal."

In `scenarios.md` §"Scenario 239 — Every taking of the Definition-of-Done judgement grades one subject by one rubric", append inside the existing gherkin block. The H2 heading is unchanged:

```gherkin
  Scenario: A preflight ended by the input bound did not run and the item is listed as unpreflightable
    Given a ready item whose judgement subject exceeds every candidate's input bound
    When the repository preflight is run for the item
    Then the preflight exits with its cannot-run code 2 and refuses nothing
    And the did-not-run record names the input bound as the cause and states the subject's size in characters
    And needs-attention lists the item as unpreflightable with that size and its rider count

  Scenario: The unpreflightable fact clears when a later taking runs a judge
    Given an item listed as unpreflightable
    When a later host taking of its judgement runs a judge
    Then needs-attention no longer lists the item as unpreflightable
```
