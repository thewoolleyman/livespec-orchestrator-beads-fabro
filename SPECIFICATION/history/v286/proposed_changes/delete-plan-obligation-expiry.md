---
topic: delete-plan-obligation-expiry
author: claude-opus-5-5
created_at: 2026-11-03T13:54:50Z
---

## Proposal: An overdue plan obligation is reported and never blocks the plan

### Target specification files

- SPECIFICATION/spec.md
- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Delete plan progress-obligation expiry as an enforcement rule. A plan obligation's budget (deadline and max_handoffs) becomes a reporting datum only. An obligation past its deadline or at its handoff ceiling is OVERDUE: that is reported as a finding and in needs-attention, but it never refuses a handoff or pointer write, never requires a typed causal recovery attempt, a continuation ruling or a human decision to continue, and never makes resume_directive withhold an executable action or rewrite it to diagnose-plan-progress. resume_directive takes or presents the six executable kinds whenever the required result is unsatisfied, whatever the deadline or handoff count. No toggle or flag is added; the rule is removed.

### Motivation

Maintainer ruling, attended, recorded verbatim on livespec-dev-tooling-6tgd2z at 2026-11-03T13:48:23Z: "Whatever 'stall' rule is in effect here, completely delete it and make it not in effect. It was intended to stop yak shaving under prior foreman/supervisor approaches, but now it is just causing stalls. Delete this asap." The fleet coordinator (legacy-coordinator-agent, R301) scoped it to this repository's plan progress-obligation expiry.

Measured live cases:
- bd-ib-6tcjfx: resume_directive(unattended) returns diagnose-plan-progress with 'expired; limit=handoffs; deadline=2026-10-20T16:00:00Z; handoffs=11/6', while its required result (bd-ib-reapbq closed) has nothing to do with the plan's current work.
- bd-ib-acrr56: the plan cannot re-aim an expired pointer, so it carried the pending reprioritised-plan-obligation-budget proposal and bd-ib-d5ncjh just to work around expiry.

The rename refusal and the evidenced-causal-supersession requirement exist only to stop a rename from 'evading expiry'. Without expiry they are pure stall rules, because a stale required result could never be re-aimed, so they are deleted with it.

### Proposed Changes

contracts.md §"Required result, budget and progress epoch":
- Paragraph 1: replace "the first limit reached expires the obligation" with a statement that the budget is a reporting datum only. An obligation whose deadline has passed, or whose accepted handoffs have reached max_handoffs, is OVERDUE. Being overdue MUST NOT cause any write to be refused, any continuation to require a recovery attempt, a continuation ruling or a human decision, or any executable action to be withheld.
- Paragraph 2: replace the sentence beginning "A replacement or renaming of an unmet result MUST preserve the original obligation" (and its "cannot evade expiry" tail) with: a sanctioned write MAY replace an unmet result with a different typed required result. The replacement MUST be recorded as a plan-progress-event of kind replacement, naming the replaced obligation's canonical result identity and epoch, before the pointer changes, so the replaced obligation stays in the progress history. The new obligation begins under the write's own budget.
- Delete the "An evidenced causal supersession" paragraph, its closed cause list (misderived, disposed, subsumed) and the paragraph that follows it ("Any other claimed cause MUST be refused ... Scenario 211 in scenarios.md exercises this paragraph.").
- The "All sanctioned pointer writers" paragraph keeps the read-before-write, handoff-unit and satisfied-advance rules. It replaces the after-expiry refusal with: at the exact deadline, or when accepted handoffs reach max_handoffs, the obligation is overdue; an overdue obligation MUST be visible even when no new handoff is written; and same-obligation continuation, a replacement and a handoff MUST each be accepted on an overdue obligation exactly as on one within budget. Unobservable results still refuse any transition claiming completion.
- The changed-approach paragraph: a typed causal recovery event MAY be recorded and is never required by any write. Its attempt budget still never replaces the original deadline. Delete the sentence saying that a prose approach line, an acknowledgment, a repair-child milestone or a cosmetic rewrite MUST NOT qualify. Keep the receipts, serialization and retry rules.
- The resume_directive paragraph: it MUST report missing, overdue and unobservable tracking findings. A budget's deadline or handoff count MUST NOT change whether it takes or presents an executable action: it takes or presents each of the six executable kinds whenever the required result is unsatisfied, exactly as within budget, reports an overdue obligation as a finding, and never rewrites it to a diagnosis action. It still MUST NOT automatically dispatch an unobservable obligation; an unattended unobservable resume retains the obligation and exposes an authorized diagnosis action. The human-escalation, progress-check-order, picker and missing-Definition-of-Done rules remain.

contracts.md "Pointer reconciliation before continuation": replace "when the obligation expires while the run is still live the existing expiry rules apply" with: an obligation that becomes overdue while the run is still live keeps waiting on that run and reports the overdue finding. Drop "within budget" and "in-budget" from the not-stale await sentence.

spec.md Planning Lane paragraph: replace "and expired obligations trigger bounded causal recovery without inventing a human decision" with "and an overdue obligation is reported without ever blocking the plan or inventing a human decision".

scenarios.md:
- Scenario 147 keeps its heading. Its first scenario's budget-boundary steps say that continuation, handoffs and pointer writes are accepted and the obligation is reported overdue, including a same-obligation handoff past max_handoffs. A new second scenario says an unmet result, within budget or overdue, is re-aimed by a replacement write that records a replacement event and starts a new obligation under the write's own budget, with no supersession cause, recovery attempt or ruling. Its third scenario says a typed causal recovery attempt is optional and never required.
- Scenario 148 keeps its heading. Its first scenario says an overdue obligation is reported and its executable action is taken without a rewrite to a diagnosis action; a second scenario says an unobservable one is not auto-dispatched and exposes an authorized diagnosis action.
- Scenario 211 (the evidenced-causal-supersession scenario) is deleted, because the behaviour it exercises is deleted; its re-aim and overdue-continuation replacements live in Scenarios 147 and 148.
- Scenario 111's Background and Scenario 168's first scenario drop "and an unexpired budget".
- Scenario 168's await scenario ends with the resume after the deadline continuing to wait and reporting the obligation overdue.
- Scenario 150's wording changes from expired to overdue.

tests/heading-coverage.json and tests/heading-coverage-debt.json drop the Scenario 211 row and register entry; Scenario 147 and 148 headings are unchanged, so their rows stand.

The pending reprioritised-plan-obligation-budget proposal is rejected in the same revise as superseded: it only existed to work around expiry. Unchanged and explicitly out of scope: the overseer-owned independent consumer's deadline-triggered diagnosis (§"Independent consumer across active and parked states", §"Launch obligations and consumed recovery", Scenarios 152, 161 and 164), which acts in addition to the plan and never withholds its recorded action, and the report-only needs-attention overdue-result fact.
