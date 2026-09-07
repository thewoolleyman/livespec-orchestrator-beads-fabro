# Review-fix stage — revise the cut for ACCEPTED findings only

## Your assignment

{{ goal }}

## What to do

The disposition record says which of the reviewer's blocking findings
are in scope. Address exactly those and nothing else.

1. Read the disposition record from the workflow run context: the
   highest-numbered visible `finding_dispositions_r*` key. Lines marked
   `ACCEPTED` are your task list; lines marked `REJECTED` are decided
   and are NOT to be revisited, argued with, or quietly implemented
   anyway.
2. Read `/tmp/livespec-groom-phase`, then revise the product it names:
   `/tmp/livespec-groom-draft` in the `propose` phase, or
   `/tmp/livespec-groom-plan` in the `apply` phase.
3. Re-write that file in place. Do not create a second copy and do not
   leave the old version behind under another name — the downstream
   nodes read exactly those two paths.

## The draft encoding still binds

If you are revising `/tmp/livespec-groom-draft`, the revision must still
be ONE line and must still carry NO BRACE CHARACTER. A revision is
exactly where those two rules get broken, which is why this node
re-enters the conformance gate rather than going straight back to
review. Keep ` ;; ` between slices and ` | ` between a slice's fields.

## Scope discipline

- Do not widen the cut. A revision that adds slices no accepted finding
  asked for is a new decomposition, not a repair.
- In the APPLY phase, do not revise the plan away from what the human
  approved. If an accepted finding cannot be satisfied without departing
  from the approved cut, that is a human's decision, not yours — use the
  needs-human protocol below.
- Do not modify any tracked file. Do not commit, push, or branch.
- File nothing. Do not call the filing seam and do not run any `bd`
  write command.

## Output

Summarize which accepted findings you addressed and how. No routing JSON
is needed: this node always re-enters the conformance gate, which
re-proves the revised product mechanically before it returns to review.

If you cannot legitimately address an accepted finding, do NOT paper
over it. End your reply with the failed outcome as a JSON object on the
LAST line:

    {"outcome": "failed", "failure_reason": "<what is blocked; what you tried; what decision is needed>"}
