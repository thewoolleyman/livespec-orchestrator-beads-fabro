# Fix stage — repair what the groom conformance gate refused

## Your assignment

{{ goal }}

## What failed

The conformance gate refused this run's output. Its stderr names the
cause behind a `LIVESPEC_GROOM_MALFORMED:` sentinel. Read that message
first; it is the whole specification of your task. The message names the
PRODUCT it refused — `/tmp/livespec-groom-draft` in the propose phase,
`/tmp/livespec-groom-plan` in the apply phase — and the gate checks five
things, reporting exactly one:

1. **No phase named.** `/tmp/livespec-groom-phase` is missing or holds
   something other than `propose` or `apply`. Re-derive the phase from
   the ledger comments in the assignment above — a draft comment whose
   first line opens with `livespec-groom-draft (`, followed by a comment
   whose first line opens with `livespec-human-answer` AND ends with an
   action id whose disposition is `ready`, means APPLY. Anything else
   means PROPOSE, including an answer whose action id ends in
   `:backlog`: that is a send-back for re-drafting, never a consent to
   file. Write that one word to the file with `printf`, with no newline
   and no other text.
2. **The tree differs from the dispatch base.** A groom run files into
   the LEDGER and must change no tracked file. Something wrote into the
   working tree. Restore it: `git checkout -- .` and remove any
   untracked file the run created inside the repository. Scratch files
   belong under `/tmp`, never in the clone.
3. **The product spans more than one line.** Re-encode it onto ONE line.
   The Dispatcher recovers both the draft and the filing plan from a
   single stderr line, so only the first line of a multi-line product
   would ever reach it, truncated silently. In the apply phase that
   truncation is a cut the Dispatcher would FILE with slices missing, and
   the ledger has no undo. Use ` ;; ` between records and ` | ` between a
   record's fields.
4. **The product carries a brace.** Remove every brace character. A
   ledger comment is append-only, so a comment carrying a template
   opening delimiter would poison every future dispatch of this item
   permanently. Rewrite the offending text in words — "layer 2", "see
   slice 3" — rather than escaping it.
5. **The filing plan does not open with `livespec-groom-plan`.** That
   leading token is what tells the Dispatcher the line is a plan to FILE
   rather than a draft to record; without it the plan lands as a fresh
   draft comment and revokes the approval it was published under. Put
   the token first, followed by ` | approver=<who> | route=<how>`, then
   the slice records.

## Hard rules

- Fix ONLY the refused condition. Do not re-draft a cut the gate did not
  object to, and do not widen the decomposition while you are here.
- Do not modify any tracked file, and do not commit, push, or branch.
- File nothing. Do not call the filing seam and do not run any `bd`
  write command; this node cannot file and must not try.
- `{{ inputs.sandbox_check_suite }}` is this repository's declared check
  suite. It is NOT the gate that refused you and running it will not
  clear this failure — the gate's own stderr is the only thing you need.

## Output

Summarize what you changed and why it satisfies the refused condition.
No routing JSON is needed: this node always re-enters the conformance
gate, which re-proves the repair mechanically.

If you cannot legitimately satisfy the gate — the refusal names a
condition you believe is wrong, or the draft cannot be encoded on one
line without losing meaning — do NOT paper over it. End your reply with
the failed outcome as a JSON object on the LAST line:

    {"outcome": "failed", "failure_reason": "<what is blocked; what you tried; what decision is needed>"}
