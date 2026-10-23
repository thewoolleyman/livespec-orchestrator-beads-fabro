---
topic: proof-fidelity-recapture
author: claude-opus-5-5:fabro-currency
created_at: 2026-10-23T01:11:42Z
---

## Proposal: A not_reproduced verdict caused only by record fidelity routes to recapture, and fix receives only the graded record

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

When proof_verify finds that every non-reproduced assertion differs from its captured proof only in the record's fidelity (output ordering or formatting, with the same behavioural result), the run re-captures the proof instead of entering fix. When fix is entered on a proof finding, its work order is the record proof_verify graded in that visit, never a capture an earlier proof_capture visit superseded.

### Motivation

Run 01M5JME62ZF8 of bd-ib-7k7re5 (2026-10-22) had a green implementation and a review@2 approval. proof_verify still recorded not_reproduced on assertions 1 and 2, only because the captured program buffered stdout and not stderr, so on replay its refusal line printed first; the behavioural result was identical. The ratified text sends every not_reproduced to fix (contracts.md §"Self-contained plugin dispatch", the proof_verify paragraph). fix was also handed the FIRST capture's superseded finding, correctly refused to make an artificial code change, and the run ended needs_human on correct, approved work, costing a full re-dispatch. Work-item bd-ib-v3uksp, whose dispatch the R316 preflight refused on 2026-10-22 because this route is unratified. Coordinator ruling R659 approved this remedy.

### Proposed Changes

Amend SPECIFICATION/contracts.md §"Self-contained plugin dispatch" → "### Definition-of-Done and Proof-of-Done stages".

1. In the `proof_verify` paragraph, after "... or `not_reproduced` naming each assertion that did not; the record header renders the verdict verbatim.", add:

"For each assertion it names as not reproduced, the record MUST classify the difference as either FIDELITY, where the replay's observable behavioural result equals the captured one and only the record's rendering differs (the interleaving or ordering of output streams, whitespace, or formatting), or BEHAVIOUR, where the behavioural result differs or cannot be compared. A difference the node cannot positively show to be fidelity MUST be classified behaviour."

2. Replace "`not_reproduced` routes to `fix` while the node's own visit count is below three" with:

"A `not_reproduced` verdict whose every classified difference is fidelity is a FIDELITY verdict: it MUST end `proof_verify` with `preferred_label=recapture`, which MUST route to `proof_capture` with the record's per-assertion findings as the recapture work order, and MUST NOT route to `fix`. It counts against the same two-lap recapture bound as a review recapture verdict, so the third recapture in one run, from either source, MUST route to the existing `non_converged` terminal. Any other `not_reproduced` routes to `fix` while the node's own visit count is below three."

The test-suite-output backstop that follows stays unchanged and takes precedence: a record whose proof of a behavioural assertion is test-suite output alone still ends through the structured needs-human ending.

3. In "**Proof findings are the fix stage's work order.**", replace "MUST read the latest proof record on the pull request when the preamble carries no finding" with:

"MUST take as its work order the record the entering stage graded in that visit: on entry from `proof_verify`, the `not_reproduced` record that visit published; on entry from `proof_capture`, that visit's `not_captured` record. When the preamble carries no finding, it MUST read the latest proof record on the pull request. A finding from a capture that a later `proof_capture` visit superseded MUST NOT be presented to `fix` as its work order."

4. Add to Scenario 137 in SPECIFICATION/scenarios.md ("## Scenario 137 — A behavioural assertion is proved by exercising the behaviour, and a sandbox that cannot exercise it says so") two cases:
- Given a captured record whose replay differs from the capture only in the interleaving of stdout and stderr, with the same behavioural result. When proof_verify replays it, then the record classifies the difference as fidelity, the run routes to proof_capture with preferred_label=recapture, and the run does not enter fix on that verdict.
- Given a replay whose behavioural result differs from the capture. When proof_verify replays it, then the record classifies the difference as behaviour, and the run routes to fix with that visit's not_reproduced record as its work order.

Add to Scenario 138 ("## Scenario 138 — A proof finding reaches the fix stage, and a parked acceptance verdict is recorded with its reason and its pointer") one case: given a run in which proof_capture published a capture, a later proof_capture visit superseded it, and proof_verify then published not_reproduced with a behaviour difference, the finding fix receives names that proof_verify record and not the superseded capture.

The implement-work-item workflow graph MUST gain the matching `proof_verify -> recapture_route` edge for the recapture label; that is implementation scope for bd-ib-v3uksp, not a spec edit.

**Amendment after independent review (gpt-6-astra round 1, BLOCKERS 1):**

5. The existing replay bounds apply to behaviour verdicts only. In the `proof_verify` paragraph and in "**Proof findings are the fix stage's work order.**", restrict three rules to BEHAVIOUR verdicts, meaning a `not_reproduced` that is not a fidelity verdict:
- "the third `not_reproduced` routes to the existing `non_converged` terminal" becomes "the third behaviour `not_reproduced` in one run routes to the existing `non_converged` terminal";
- "A `not_reproduced` proof loop re-enters `review`, and those review visits count toward the review-fix budget" applies to behaviour verdicts only;
- the closing bound sentence ("the third `not_reproduced` from `proof_verify` ... route[s] to `non_converged`") likewise counts behaviour verdicts only.

A fidelity verdict, and any `review` visit it leads back to, MUST consume only the shared two-lap recapture allowance. It MUST NOT count toward the behaviour `not_reproduced` bound or the review-fix budget. Where a fidelity verdict and the recapture bound both apply, the recapture bound decides: a fidelity verdict that would be the run's third recapture routes to `non_converged`.

Add to Scenario 137 one case: given a run whose proof_verify has already published two behaviour not_reproduced verdicts, the third proof_verify visit publishes a fidelity verdict. Then the run routes to proof_capture with preferred_label=recapture, not to non_converged, provided the run's recapture allowance is not exhausted.

**Amendment after independent review (gpt-6-astra round 2, BLOCKERS 1):**

6. The fix-entry guard counts behaviour verdicts, not visits. In change 2, replace "Any other `not_reproduced` routes to `fix` while the node's own visit count is below three." with "The first and second behaviour `not_reproduced` verdicts in one run MUST route to `fix`, and the third MUST route to the existing `non_converged` terminal." A fidelity verdict MUST NOT advance that count.

Add to Scenario 137 one case: given a run whose first proof_verify verdict was fidelity and whose second was a behaviour not_reproduced, when the third proof_verify visit publishes a second behaviour not_reproduced, then the run routes to fix and not to non_converged.

**Amendment after ratification review on the exact resulting bytes (gpt-6-astra, BLOCKERS 2):**

7. Two existing sentences of the same section must be narrowed to match the new routes, and one phrase clarified.
- In "**Proof findings are the fix stage's work order.**", the opening condition "When `proof_capture` ends with `preferred_label=fix`, or `proof_verify` publishes `not_reproduced`," becomes "When `proof_capture` ends with `preferred_label=fix`, or `proof_verify` publishes a first or second behaviour `not_reproduced` and so routes to `fix`,". A fidelity verdict, and a third behaviour verdict that ends at `non_converged`, owe no `fix` work order.
- In the same paragraph, "The proof loops stay bounded by the two visit caps above" becomes "The proof loops stay bounded by the two finding-count bounds above".
- The recapture delivery rule becomes source-specific. "`proof_capture` entered on a recapture verdict MUST receive the verdict's findings by two routes, the engine's preamble of preceding stage output and the review record on the pull request, MUST read that review record when the preamble carries no finding," becomes "`proof_capture` entered on a recapture verdict MUST receive the verdict's findings by two routes: the engine's preamble of preceding stage output, and the issuing visit's record on the pull request — the review record for a recapture verdict from `review`, and the `not_reproduced` record that `proof_verify` visit published for a fidelity verdict. It MUST read that record when the preamble carries no finding,".

In Scenario 137, the existing case "proof_capture reads the review record when the preamble is empty" is qualified to a review-origin recapture: its first Given becomes "Given a recapture entry from review whose engine preamble carries no review finding". Add one case: given a recapture entry from a proof_verify fidelity verdict whose engine preamble carries no finding, when the proof_capture node runs, then it reads that proof_verify visit's not_reproduced record and the new captured record addresses each fidelity finding.
