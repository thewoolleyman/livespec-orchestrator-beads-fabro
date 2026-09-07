# Publish stage — file the approved slices and regroom out the original

## Your assignment

{{ goal }}

## Where you are, and what "publish" means here

You are in the same isolated Fabro sandbox clone the earlier nodes ran
in; your CURRENT WORKING DIRECTORY is that clone. The assignment above
may name a `Repo:` path — that is the dispatcher's host-side checkout, it
does NOT exist in this sandbox, and you must never `cd` to it.

**This run publishes to the LEDGER, not to the forge.** There is no diff,
no branch to push and no pull request to open. Do not run `git push` and
do not run any `gh pr` command. The repository's merge discipline
(`{{ inputs.merge_mode }}`) and its per-item merge hold
(`{{ inputs.merge_hold }}`) govern the publication of CODE and are not
exercised by a groom run; they are named here so you can recognize that
none of the usual publish machinery applies to you.

You are reached only in the APPLY phase — the graph routes the propose
phase to the human gate instead — so a human has already approved this
cut. Your job is to make that approval real in the ledger, exactly once.

## What to do, in order

1. Confirm the phase: `/tmp/livespec-groom-phase` must read `apply`. If
   it does not, STOP and use the needs-human protocol below — reaching
   this node in any other phase is a routing fault, not something to
   work around.
2. Read the reviewed filing plan at `/tmp/livespec-groom-plan`. That plan,
   as reviewed, is what you file. Do not re-derive the cut from the draft
   comment and do not improve it here.
3. Re-read the approving answer comment in the assignment above and take
   from it the two values the filing seam requires: WHO approved (the
   approving invoker's identity) and HOW the approval was obtained (the
   `resolve-blocked` valve plus the ledger comment the answer landed as).
   **Do NOT synthesize either value.** An identity you invented
   attributes the cut to someone who never approved it, which is far
   worse than the refusal you would otherwise get. If the answer comment
   does not name an approver, use the needs-human protocol.
4. File the approved slices and close the original in ONE call:

   ```python
   from pathlib import Path

   from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
   from livespec_orchestrator_beads_fabro.commands.groom import (
       CandidateSlice,
       GroomApproval,
       file_approved_slices,
   )

   config = resolve_store_config(cwd=Path.cwd(), work_items_arg=None)
   result = file_approved_slices(
       path=config,
       regroom_item_id=...,          # the work-item id from your assignment
       local_repo=...,               # this repository's ledger name
       approval=GroomApproval(
           approver=...,             # WHO — read off the answer comment
           route=...,                # HOW — the valve plus that comment
       ),
       slices=[
           CandidateSlice(
               title=...,
               description=...,
               acceptance=...,
               autonomy_tier="factory",   # or "human-gated"
               repo_target=...,
               depends_on=(...,),         # earlier factory-slice TITLES
               is_spec_change=False,      # True means routed, not filed
           ),
           ...
       ],
   )
   ```

   The seam files each factory slice through the same intake routing the
   capture front-end uses, links the dependency edges, stamps the
   approval record on every filed slice, closes the original against the
   filed slice ids, and stamps the approval on that closed original too.
   That closure IS the regroom-out disposition; there is no second call.

5. Report `result.filed_slice_ids`, every line of
   `result.criteria_parses` (each slice's effective-criteria parse — a
   slice whose criteria parse to zero gradeable assertions is later
   refused at dispatch, so this must be visible), and
   `result.spec_change_slices` and `result.cross_repo_slices`, which are
   NOT filed here and need maintainer-side routing.

## Refusals you must surface rather than route around

- `GroomApprovalRequiredError` — the approval record is absent or names
  no approver or no route. Nothing was filed. Do not retry with a value
  you made up; use the needs-human protocol.
- `GroomDraftError` — a slice has an empty repo target, or a
  `depends_on` handle names no earlier factory slice. The cut is
  malformed; surface it.
- `GroomExitRefusedError` — the cut files no local factory slice at all.
  The original stays where it is, deliberately: escalate, do not drop.

Every one of these leaves nothing half-filed. Report the exception
verbatim and end with the needs-human protocol.

## Hard rules

- Call the filing seam exactly ONCE. A second call after a partial
  failure files duplicates into a ledger that has no undo.
- Do not modify any tracked file. Do not commit, push, or branch.
- Never run `bd init`. Never write to any `.beads/` directory, and do not
  hand-roll ledger writes around the seam — the approval stamping is the
  seam's job and a hand-rolled write loses it.

## Output

On success, end your reply with a single JSON object on the LAST line:

    {"preferred_next_label": "done"}

If you could not file, end instead with the structured needs-human
ending, as a JSON object on the last line:

    {"outcome": "failed", "failure_reason": "<what is blocked; what you tried; what decision is needed>"}
