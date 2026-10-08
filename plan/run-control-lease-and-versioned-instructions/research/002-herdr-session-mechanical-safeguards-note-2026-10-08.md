# Mechanical safeguards for factory-driven plans — the originating session's note

Provenance: written by the Codex session `overseer-herdr-rewrite` (plan `herdr-overseer`, epic `overseer-uzvcbn`, livespec-overseer) and left at `/tmp/herdr-factory-mechanical-safeguards.md` on the vps host, last modified 2026-10-08 10:10 +02:00, 7,801 bytes. Copied verbatim into this plan by the `factory-reliability` session on 2026-10-08 so the record survives the file. Everything below the rule is that session's text, unedited.

---

# Mechanical safeguards for factory-driven plans

Recommendation only, 2026-10-08. This answers the maintainer's prevention question; it does not open another plan or implement these proposals.

Enforce these at the execution and acceptance boundaries. Agent instructions remain useful, but do not constitute enforcement.

| Observed failure | Required enforcement | Acceptance test |
|---|---|---|
| Competing sessions steer the same run | A server-enforced control lease with a generation number. Every mutation checks the current owner and generation; other sessions may submit observations. | A second session and an expired former owner both attempt to steer/cancel. Neither action reaches the worker. |
| Old corrections arrive after the work changed | Each correction has an ID, content hash, target actor/stage, and expected execution revision. Recheck applicability at delivery; expose inspect/cancel/supersede. Track submitted, delivered, acknowledged, and verified effect separately. | Complete the repair before delivering its old correction. Delivery is rejected and causes zero resets, edits, or recommits. |
| Historical instructions become active again on recovery | Build the initial task from one authoritative current instruction revision. Preserve superseded handoffs as historical evidence. Verify the recovery bundle and source before launching the actor. | An incomplete or mismatched recovery upload starts zero actors. A recovered worker adopts the accepted source and receives only the current remaining task. |
| Red is manufactured after implementation | The trusted runner records the failing behavioral test against the unchanged baseline before permitting the corresponding implementation phase, then checks the same frozen regression against Green. | A collection error, retrospective mutation failure, or changed regression cannot satisfy Red-first acceptance. |
| Repeated broad diagnostics consume hours | Mediate validation launches: required checks follow their normal rules; discretionary reruns need an explicit allowance justified by a new failure, change, or unresolved concern. | A duplicate discretionary rerun without an allowance starts zero processes. Required hooks continue to run. |
| Failure output is discarded or never emitted | During the original execution, retain complete stdout/stderr, original exit, source identity, and a useful traceback in immutable digest-addressed artifacts outside the checkout. | Force a hook failure. Recover the actual failing assertion and original exit without rerunning it. If storage fails, preserve the failure verdict and report the storage failure. |
| A coordinator ends its turn and nobody handles completion | Dispatch atomically records a durable obligation, owner, external run reference, and deadline. An independent lifecycle watcher survives the agent turn, observes terminal outcomes, and schedules reconciliation or explicit recovery. | End the coordinator turn, then fail the factory run. A responsible session is resumed and handles the failure within the deadline without a human message. |
| A routine engineering decision is routed to a human and stalls authorized work | Emit a typed recoverable outcome such as needs_groom, with the evidence and remaining requirements. Route it to the authorized coordinator; reserve needs_human for a concrete decision outside that authority. Check requirement coverage and dependencies when replacing a slice. | A worker requests same-scope decomposition under standing autonomous authorization. The coordinator regrooms and resumes without a human prompt, while every original requirement and downstream prerequisite remains represented. |
| Closed children or unsuitable factory tests are mistaken for completion | Check actual sandbox capabilities at admission, bind evidence to the exercised build, and refuse plan closure until all declared assertions have independent proof on the required released host surface. | An image without Herdr cannot discharge Herdr factory assertions. Closing every child without real released Herdr proof still refuses archive. |

A control lease must fence expired controllers, not merely name an owner. Deadlines must not move forward because of cosmetic output. Recovery must respect a real commit/Red–Green boundary; a timeout does not justify blindly checkpointing an open Red pair.

The validation budget is only mechanical when the execution service mediates launches. Prompt rules or command-pattern matching around unrestricted shell execution cannot guarantee it. Likewise, a source hash plus command line alone does not establish that two test environments are equivalent.

The publisher should validate size limits and attach bulky evidence automatically, retaining complete artifacts. A formatting failure should retry publication, without rerunning successful implementation or proof. The current released orchestrator's total record budget is 196,608 UTF-8 bytes, with 32,768 bytes per inline assertion; the supposed 65,536-character ceiling caused unnecessary work in this run.

Ownership belongs primarily in Fabro's control/delivery service; recovery, lifecycle obligations, and acceptance belong in the orchestrator; trusted test execution and failure diagnostics involve dev-tooling as well. These need adversarial integration tests through real CLI/agent sessions, including late delivery, controller disappearance, and partial uploads.

Already released and read back in orchestrator 0.174.0: plan-level proof/archive gates and the proof-record budgets above. The additional lease, conditional delivery, pre-actor recovery, and discretionary execution enforcement described here are requirements, not claimed completed protections. Current single-controller and exact-receipt practices are procedural safeguards while the main Herdr rewrite continues.

Observed after this note was first written: S2 exited through needs_human without product edits, requesting decomposition. Its estimate incorrectly assumed one Red–Green pair per assertion and compared physical file lines with an LLOC ceiling. Neither is a valid mechanical sizing rule. The coordinator selected smaller capability boundaries under existing authorization, preserving requirements; no implementation completion is implied by that decision.

## Enforcement boundary and honest limits

The Red-first gate needs an execution boundary, not just a commit-message convention. Before releasing product-write capability for a declared change, an external runner records the baseline source digest, frozen regression digest, test environment identity, complete output and original status. The worker must not be able to rewrite that receipt or backdate it. The Green result references the same regression and a later product digest. If unrestricted shell writes remain available before the gate, a promise to wait for Red is procedural rather than mechanically enforced.

Chronology and artifact integrity can be enforced mechanically; whether a failure is a meaningful regression for the intended behavior still needs review. Reject collection/setup failures as evidence of the behavior, and require an independent assessment that the failing assertion exercises the requirement. A later reset to an inert stub does not erase earlier implementation: retain the event history and label retrospective testing honestly. Corrections to invalid test expectations likewise remain visible rather than being recast as first-Red evidence.

For incremental changes, admit small declared behavior steps, each with its own baseline and authorization. Do not require one Red commit per Definition-of-Done bullet, and do not count physical lines as an LLOC budget. These false rules caused unnecessary decomposition and validation work in this run.
