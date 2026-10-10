---
topic: plan-continuation-and-typed-kinds
author: claude-fable-5-1
created_at: 2026-10-10T02:13:23Z
spec_commitments:
  impl_followups:
    - id_hint: plan-resume-continuation
      description: |
        Realize the continuation ruling, the four new next_action kinds, the attended no-picker path under a current ruling, pointer reconciliation before continuation, and the two conformance checks in the plan package (commands/_plan_next_action.py, plan.py, _plan_record_conformance), with the plan prose and the three runtime bindings updated to drive the new kinds.
---

## Proposal: Plan continuation: recorded authorization satisfies the attended picker, and the typed next action can name every step to the archive

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A plan epic records the maintainer's authorization to continue as a scope ruling; while it is current, an attended resume takes a dispatchable typed next action without presenting the picker. The typed next_action gains the kinds proof, review, archive and await so the steps after the last child closes are executable pointers, and every resume reconciles the pointer against the ledger and the factory before taking it.

### Motivation

Maintainer direction of 2026-10-10 on plan definition-and-proof-of-done (epic bd-ib-7sjdzv): frame the Definition of Done and Proof of Done as the goal of every skill prompt so that a model does not stall before the plan is complete and archived. An independent Codex (gpt-6-astra) critique of the prompt rewrite (plan/definition-and-proof-of-done/research/007-codex-gpt6-astra-critique-of-prompt-goal-framing-2026-10-10.md, sections A1 and C) found that the strongest stall cause is ratified text, not prose: an attended resume MUST present the picker, and the typed next_action has no kind for the work that remains after the last child closes (the plan-level proof, its independent replay, the completeness review, the archive, or a bounded wait on a live run or another plan's record), so a session that has finished its children can only record kind human and stop. Measured on this plan: Handoff 21 of 2026-10-09 recorded kind human to say 'wait for plan overseer-uzvcbn to publish its host record', and the maintainer's standing directive to continue had to be re-applied by hand at every resume.

### Proposed Changes

In contracts.md §"Typed `next_action` and `last_session`":

1. Replace `kind MUST be one of impl, spec-op, human, or none.` with `kind MUST be one of impl, spec-op, proof, review, archive, await, human, or none.` and add, after the `spec-op` sentence: `proof` means the next step is the plan-level Proof of Done leg, and `ref` MUST be `capture:<epic-id>` (the plan session captures the plan record against the released build through the posting primitive of §"Plan Definition of Done and Proof of Done") or `verify:<epic-id>` (a separately started session replays the latest captured record); `review` means the next step is commissioning the independent completeness review of §"Archive on completion", and `ref` MUST be the epic id; `archive` means the next step is `archive_thread`, and `ref` MUST be the epic id; `await` means the next step is a bounded wait on one named obligation outside this session's control, and `ref` MUST be one of `run:<fabro-run-id>`, `gate:<gate-run-id>`, `item:<work-item-id>` or `epic:<epic-id>` naming the run, detached gate, work item or other plan whose terminal state or record the plan needs. Each of `proof`, `review`, `archive` and `await` MUST carry `required_result` and `budget` exactly as `impl` does (§"Required result, budget and progress epoch"); for `await` the required result is the observable terminal state or record the pointer waits for, and the budget deadline is the wait's deadline.

2. Add a paragraph **Recorded continuation authorization.** A plan epic MAY carry a continuation ruling: a scope event (a ruling, not a carrier-map event) whose first line is `plan-continuation: authorized` followed by a line `until: <archive|<UTC timestamp>>` and a line `by: <maintainer identity>`, recorded ONLY by an attended session in the same turn in which the maintainer gave the directive, and recorded VERBATIM beside the maintainer's words. A later ruling whose first line is `plan-continuation: revoked` ends it; a ruling with `until: <timestamp>` expires at that instant; `until: archive` lasts until the plan archives. The ruling authorizes CONTINUATION ONLY: it does not waive store-write consent (§"Store-write consent discipline"), does not admit a work item, and does not authorize any action the sanctioned next-action kinds cannot express.

3. Replace `An attended resume MUST present next_action as the default choice of its picker.` with: An attended resume MUST present `next_action` as the default choice of its picker, EXCEPT that while a current continuation ruling exists and `kind` is `impl`, `spec-op`, `proof`, `review`, `archive` or `await` with a non-empty `ref` and the required-result checks permit continuation, the resume MUST take the pointer without presenting the picker, reporting the ruling it acted under; `human` and `none` MUST raise the picker in every case. `resume_directive` MUST return the ruling's identity in its `reason` when it acts under one.

4. Add a paragraph **Pointer reconciliation before continuation.** Before taking any pointer, attended or not, the resume MUST read the pointer's target from the authoritative source (the ledger for `impl`, `item` and `epic` references; the factory for `run`; the gate store for `gate`) and MUST NOT execute a pointer whose target is already in its required terminal state or is being driven by a live run: it MUST report the pointer as STALE with the observed state, and MUST advance it — a satisfied obligation advances to the next step the plan prose derives from the ledger (the next ready child, the proof leg, the review, the archive); a live run becomes `await` with `run:<id>`. A stale pointer is a tracking finding under §"Required result, budget and progress epoch", not a human escalation.

In contracts.md §"Plan-record conformance checks", add: a `plan_next_action_kind` check MUST report an open live plan whose `next_action.kind` is not one of the eight kinds, and a `plan_continuation_ruling` check MUST report a continuation ruling recorded by an unattended session or lacking the `until:` or `by:` line.

In the Planning Lane restraint budget paragraph of §"Required result, budget and progress epoch", add the four kinds and the continuation ruling to the fixed shapes the budget includes; no new file, table or queue.

In scenarios.md add `## Scenario 168 — An authorized plan resume continues to the archive without a picker, and the typed next action names every remaining step`:

```gherkin
Feature: a plan session drives to the archive under a recorded authorization
  As a maintainer who has told a plan session to finish the plan
  I want every resume to take the recorded next step until the plan archives
  So that the plan does not stop at the last closed child or wait on a question nobody asked

  Scenario: a continuation ruling lets an attended resume take the pointer
    Given an open plan epic carrying a current continuation ruling until archive
    And next_action kind impl with a non-empty ref and an unexpired budget
    When the plan operation resumes attended
    Then resume_directive returns ask false and the action impl:<ref>
    And the reason names the continuation ruling

  Scenario: without a ruling the attended picker still shows the default
    Given the same epic with no continuation ruling
    When the plan operation resumes attended
    Then resume_directive returns ask true
    And the picker's default is the recorded next_action

  Scenario: a human pointer raises the picker even under a ruling
    Given the same epic with a current ruling and next_action kind human
    When the plan operation resumes attended
    Then resume_directive returns ask true with the kind as the reason

  Scenario: the proof, review and archive steps are typed pointers
    Given a plan whose children are all closed and whose epic has no verified plan record
    When the session records the next action
    Then the pointer is kind proof with ref capture:<epic-id>
    And after a captured record exists the pointer is kind proof with ref verify:<epic-id>
    And after a verified record exists the pointer is kind review, then kind archive

  Scenario: a wait on another plan's record is a typed pointer with a deadline
    Given a plan assertion carried by another plan's host record that does not exist yet
    When the session records the next action
    Then the pointer is kind await with ref epic:<other-epic-id>, a required result naming that record and a budget deadline
    And a resume after the deadline reports the obligation expired rather than waiting again

  Scenario: a stale pointer is reconciled, not executed
    Given next_action kind impl whose ref names a work item already closed
    When the plan operation resumes
    Then the pointer is reported stale with the observed status closed
    And the resume advances to the next step derived from the ledger instead of dispatching the closed item

  Scenario: a pointer at a live run reattaches instead of re-dispatching
    Given next_action kind impl whose ref names a work item with a live factory run
    When the plan operation resumes
    Then the pointer becomes kind await with ref run:<id> and the run's deadline
    And no second dispatch is started

  Scenario: a ruling recorded without the maintainer present is a finding
    Given a continuation ruling recorded by an unattended session
    When the plan_continuation_ruling check runs
    Then it reports the ruling and the resume does not act under it
```

The revise pass MUST co-edit tests/heading-coverage.json and tests/heading-coverage-debt.json for the new Scenario 168 heading as an owned TODO naming epic bd-ib-7sjdzv until the implementing child is filed.
