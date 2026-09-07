# Review stage — review the CUT, not a diff

## Your assignment

{{ goal }}

## What you are reviewing

This is a groom run. It produced no code. What you review is a
DECOMPOSITION: either a drafted cut awaiting a human's approval, or the
plan for filing a cut a human has already approved.

Read, in this order:

1. `/tmp/livespec-groom-phase` — one word, `propose` or `apply`. It tells
   you which of the two products below exists.
2. `/tmp/livespec-groom-draft` — the propose phase's one-line draft, when
   the phase is `propose`.
3. `/tmp/livespec-groom-plan` — the apply phase's one-line filing plan,
   when the phase is `apply`. The Dispatcher executes this plan verbatim
   host-side once the run terminates; no node in this run files anything,
   because the sandbox holds no ledger credential by design.
4. The ledger comments in the assignment above — the earlier draft and
   the approving answer, when there are any.

## What to look for

Bring the senior-engineer lens to the cut itself. A BLOCKING finding is
one that would make the filed backlog wrong:

- **Coherence.** Each slice has exactly ONE coherent "done". A slice with
  two dones is an epic wearing a slice's clothes and will not converge.
- **Autonomous verifiability.** Each slice's acceptance is something a
  factory run can verify by itself. Acceptance that requires a human to
  look at something is a `human-gated` slice, not a factory one.
- **Layering.** Every blocker precedes what it blocks, and no cycle
  exists. A slice whose blocker is filed after it deadlocks.
- **Routing.** A spec-change slice is `human-gated` and routes to the
  `propose-change` operation, never to the factory.
- **Coverage.** Between them the slices cover the original item's scope.
  A cut that quietly drops part of the work is worse than no cut.
- **Filing plan fidelity (apply phase only).** The plan matches the
  APPROVED draft as amended by the answer comment, and does not add,
  drop or reshape a slice the human did not approve. Its header names
  the approving invoker's identity (`approver=`) and the route the
  approval arrived on (`route=`), both read off the answer comment and
  neither synthesized — the filing seam refuses a call carrying neither,
  and an invented identity is worse than that refusal. Every
  `blockers=` handle names an EARLIER slice in the same plan. This is
  BLOCKING: the plan is executed verbatim against a ledger with no undo.

An ADVISORY finding is a real improvement that would not make the filed
backlog wrong. Say so and move on.

Do NOT expand scope. A finding that asks the cut to solve more than the
original item asked for is itself a defect; prefer not raising it.

## Output (required, exact)

List each finding on its own line:

    [BLOCKING] <slice title or file> — <defect + why it matters>
    [ADVISORY] <slice title or file> — <suggestion>

When at least one `[BLOCKING]` finding is present, also persist the
complete findings text for this round in workflow context:

1. Determine the round number N: count prior visible `review_findings_r*`
   run-context keys, then use the next integer. If none are visible, use
   `review_findings_r1`.
2. The context value MUST be the exact finding lines you listed above,
   preserving both `[BLOCKING]` and `[ADVISORY]` lines in their original
   order.
3. Include that value under `review_findings_r<N>` in the routing JSON's
   `context_updates`.

Then end your reply with a single JSON object on the LAST line:

- sound cut, no blocking findings: `{"preferred_next_label": "approve"}`
- at least one BLOCKING finding:   `{"preferred_next_label": "fix", "context_updates": {"review_findings_r<N>": "<the exact finding lines>"}}`

Use those exact lowercase tokens. An empty blocking list means approve.

There is NO ship-on-cap escape hatch in this workflow, deliberately. If
the review loop reaches its cap with your objections unresolved, the run
parks for a human rather than filing the cut anyway: a filed cut becomes
the backlog other work is planned against, so it is not cheap to undo.
Review accordingly — an objection you raise at the cap costs a human's
attention, and an objection you withhold costs the backlog.

If you genuinely CANNOT perform the review — the phase file is missing,
or neither product file exists — do NOT guess. End instead with the
structured needs-human ending, as a JSON object on the last line:

    {"outcome": "failed", "failure_reason": "<what blocked the review and what is needed>"}
