# Disposition stage — triage the review's blocking findings on the cut

## Your assignment

{{ goal }}

## What you are doing

This is a READ-ONLY triage. The reviewer raised blocking findings against
this groom run's decomposition; you decide which of them the revision
node must actually address, before any rework is spent. You change
nothing — not the draft, not the filing plan, not the phase file, not a
tracked file, and certainly not the ledger.

## What to read

1. The review findings for this round, from the workflow run context:
   the highest-numbered visible `review_findings_r*` key. That record is
   the reviewer's own text; prefer it over any summary.
2. `/tmp/livespec-groom-phase`, then whichever product the phase names —
   `/tmp/livespec-groom-draft` for `propose`, `/tmp/livespec-groom-plan`
   for `apply`.
3. The ledger comments in the assignment above, when a finding turns on
   what the approved draft or the approving answer actually said.

## How to decide

For EACH `[BLOCKING]` finding, record exactly one disposition:

- `ACCEPTED <slice title or finding reference> — <one-line rationale>`
  when the finding is correct and in scope for this work-item's cut.
- `REJECTED <slice title or finding reference> — <one-line rationale>`
  when the finding is out-of-scope, not applicable, factually wrong, or
  would require expanding the cut beyond what the original item asked
  for. Do NOT expand scope to satisfy a finding: a "fix" that adds
  slices the item did not ask for is itself wrong, so prefer rejecting
  such a finding with that rationale.

One rejection is specific to this workflow and worth naming: in the
APPLY phase, a finding that asks for a slice the approving human did not
approve must be REJECTED. The approval is the consent for what gets
filed, and a review round is not a route around it. The correct answer
to "the approved cut is wrong" is to park for a human, not to file a
different cut.

## Output (required, exact)

List your disposition lines, then:

1. Determine the round number N: count prior visible
   `finding_dispositions_r*` run-context keys, then use the next
   integer. If none are visible, use `finding_dispositions_r1`.
2. End your reply with routing JSON on the LAST line:
   - At least one ACCEPTED finding:
     `{"preferred_next_label": "fix", "context_updates": {"finding_dispositions_r<N>": "<the exact disposition record lines>"}}`
   - Every BLOCKING finding rejected:
     `{"preferred_next_label": "all_rejected", "context_updates": {"finding_dispositions_r<N>": "<the exact disposition record lines>"}}`

Use those exact lowercase routing labels. The JSON is best-effort routing
text; do not use or request schema-validated structured output.

## When you cannot proceed (needs-human protocol)

If you cannot see the review findings, cannot confidently disposition a
finding, or need a human decision, do NOT guess. End instead with the
structured needs-human ending, as a JSON object on the last line:

    {"outcome": "failed", "failure_reason": "<what blocked disposition and what is needed>"}
