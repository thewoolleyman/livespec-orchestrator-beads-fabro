# Groom stage — derive the phase, then draft the cut or plan the filing

## Your assignment

{{ goal }}

## What this run is

This is a GROOM run, not an implementation run. Its product is a
DECOMPOSITION of the work-item above — or the filing of one that a human
has already approved. It is a two-phase workflow and this node decides
which of the two phases is running.

You will not write code. You will not modify a single tracked file in
this repository. A later node proves that mechanically: it fails the run
if the working tree differs at all from `origin/{{ inputs.default_branch }}`.

## Step 1 — derive the phase from the assignment above (required, first)

The phase is NOT passed to you as an input. It is derived from the
ledger comments the assignment already carries, under its
"Ledger comments" heading. Read them in the order they appear.

- A comment whose FIRST LINE opens with `livespec-groom-draft (` is a
  DRAFT this workflow produced on an earlier run. Only the first line
  counts: a comment that merely quotes or discusses that marker further
  down is not a draft.
- A comment whose FIRST LINE opens with `livespec-human-answer` is an
  operator's answer recorded through the `resolve-blocked` valve. That
  first line ENDS with the action id the answer was written under, in
  the form `resolve-blocked:<work-item-id>:ready` or
  `resolve-blocked:<work-item-id>:backlog`. The trailing word is the
  operator's DISPOSITION and you must read it: `ready` approves the
  draft, `backlog` sends it BACK for re-drafting. An answer is not an
  approval — a `ready` answer is.

Now decide:

- **APPLY** — the assignment carries a draft comment AND the NEWEST
  answer comment appearing AFTER the NEWEST draft comment carries the
  `ready` disposition. Only a `ready` disposition is consent for
  filing.
- **PROPOSE** — anything else. No draft at all; a draft with no answer
  after it; a draft whose newest following answer carries the `backlog`
  disposition (that answer is a REJECTION, and an operator who bounces
  a cut and explains why in the same breath must never have the
  explanation read as consent to file the cut they just rejected); or a
  draft that was re-drafted after an earlier approval (the newer draft
  invalidates the older consent — that is deliberate, it is how a
  send-back for re-drafting works).

Write your answer, and nothing else, to the phase file:

    printf propose > /tmp/livespec-groom-phase
    # or
    printf apply > /tmp/livespec-groom-phase

Write exactly one of those two words, with no newline and no other
text. The two script nodes downstream route on this file, and a value
they do not recognize fails the run rather than guessing.

State in your reply which phase you derived and the evidence you
derived it from (which comment indices carried the draft and the
answer). If you cannot tell — the comments are ambiguous, or a draft
comment is present but unreadable — do NOT guess a phase. End with the
needs-human protocol at the bottom of this file.

## Step 2A — the PROPOSE phase: draft the cut, file nothing

Draft the decomposition exactly as the repository's own `groom`
front-end drafts it. Read `.claude-plugin/prose/groom.md` in this clone
and follow its drafting step; the summary below is a reminder, not a
replacement for it.

Each candidate slice is pre-filled with all of:

- **acceptance** — exactly one coherent, autonomously-verifiable "done".
- **autonomy tier** — `factory` (autonomously dispatchable) or
  `human-gated`. A spec-change slice is `human-gated` and routes to the
  `propose-change` operation, NOT to the factory.
- **dependency links** — the draft-local titles of the EARLIER slices
  this one is blocked by. Arrange the draft so blockers precede the
  slices they block; that arrangement is the dependency layering.
- **repo target** — the one ledger the slice lands in.
- **scope** — the slice body.

When the draft discovers required workflow-file wiring, split that
wiring into an explicitly maintainer-side step: factory slices never
create or update files under the forge's own workflow directory, so the
factory slice carries the product change and reports the workflow diff
for maintainer-side landing.

**YOU FILE NOTHING.** Do not call the filing seam. Do not create,
update, close or comment on any work-item. Do not run any `bd` write
command. The draft is read-only until a human approves it, and the
graph enforces that structurally: the propose phase never reaches the
node that can file.

### Writing the draft (the encoding is load-bearing)

Write the draft as ONE LINE to `/tmp/livespec-groom-draft`.

One line is not a style preference. The Dispatcher recovers your draft
from this run's needs-human sentinel, which is a single stderr line, and
records the text following that sentinel ON THAT LINE as a ledger
comment. A draft spanning several lines reaches the ledger truncated to
its first line, silently. The conformance node downstream refuses a
multi-line draft rather than letting that happen.

The draft must also contain NO BRACE CHARACTER of any kind. A ledger
comment is append-only — there is no edit and no delete — so a comment
carrying a template opening delimiter poisons every future dispatch of
this item permanently. Braces are refused outright because that is the
cheap, checkable rule; write "layer 1" and "see slice 3", never a
braced token.

Encode the layered cut like this, on the one line:

    slice=<draft-local title> | layer=<integer> | tier=<factory or human-gated> | repo=<repo name> | acceptance=<one assertion> | blockers=<comma-separated earlier slice titles, or none> | scope=<the slice body> ;; slice=<next slice> | ...

Use ` ;; ` between slices and ` | ` between a slice's fields. Keep it
readable: a human reads this line in the ledger and decides on it.

## Step 2B — the APPLY phase: plan the filing, still file nothing

The approved cut is the NEWEST `livespec-groom-draft` comment in the
assignment above, as amended by anything the approving answer comment
says. The answer is authoritative where the two differ: the operator
may have edited the cut, the acceptance, the dependencies or the tiers
while approving.

Produce a FILING PLAN and write it as ONE LINE to
`/tmp/livespec-groom-plan`.

The plan crosses the SAME single-line sentinel channel the draft crosses,
for the same reason and with the same consequence: the Dispatcher reads
the terminated run's needs-human sentinel, which is a stderr LINE, and a
plan spanning several lines would arrive truncated to its first. A
truncated plan is worse than a truncated draft — it is a cut the
Dispatcher would FILE with slices missing, and the ledger has no undo. It
must also contain NO BRACE CHARACTER, exactly as the draft must not.

Encode it like this, on the one line:

    livespec-groom-plan | approver=<who> | route=<how> ;; slice=<title> | tier=<factory or human-gated> | repo=<repo name> | acceptance=<one assertion> | blockers=<comma-separated earlier slice titles, or none> | spec=<yes or no> | scope=<the slice body> ;; slice=<next slice> | ...

- The leading `livespec-groom-plan` token is required and is what tells
  the Dispatcher this is a plan to FILE rather than a draft to record. A
  plan missing it is read as a fresh draft, which would revoke the very
  approval you are applying.
- `approver` and `route` are read off the approving answer comment —
  WHO approved, and HOW (the `resolve-blocked` valve plus the ledger
  comment the answer landed as). **Do NOT synthesize either value.** An
  identity you invented attributes a maintainer-tier mutation to someone
  who never approved it. If the answer comment names no approver, use
  the needs-human protocol.
- Every slice field is required except `blockers` and `spec`, which
  default to `none` and `no`. An empty acceptance parses to zero
  gradeable assertions and the filed slice is later refused at dispatch.
- `spec=yes` marks a spec-change slice: it is NOT filed into the factory
  ledger and is returned for `propose-change` routing instead.
- Use ` ;; ` between records and ` | ` between a record's fields, so a
  human reading the plan reads it the same way they read a draft.

**YOU STILL FILE NOTHING IN THIS NODE, AND NEITHER DOES ANY LATER NODE.**
This sandbox holds no ledger credential by design; the Dispatcher files
the plan host-side once this run terminates. Your job is to make the plan
correct and reviewable, because it is executed verbatim.

## Hard rules (non-negotiable)

- Do not modify any tracked file. Do not commit. Do not push. Do not
  create or switch branches.
- Never run `bd init`. Never write to any `.beads/` directory.
- Never pass `--no-verify` to any git command.
- The assignment may name a `Repo:` path. That is the dispatcher's
  host-side checkout; it does NOT exist in this sandbox, and you must
  never `cd` to it. Work in your current working directory.
- `{{ inputs.sandbox_check_suite }}` is this repository's declared check
  suite. A groom run does NOT run it and must not: the suite gates code
  changes, and this run makes none. If you ever find yourself wanting to
  run it, you have written code, which a groom run must not do — stop
  and re-read Step 2.

## When you are genuinely stuck (needs-human protocol)

If the phase is underivable, the item is not decomposable as briefed, or
the approved draft is unreadable, do NOT guess and do NOT file
anything. End your reply with the failed outcome as a JSON object on the
LAST line:

    {"outcome": "failed", "failure_reason": "<what is blocked; what you tried; what decision is needed>"}

## Output

On success, summarize the phase you derived, the evidence for it, and
what you wrote to the phase file and to the draft or plan file. No
routing JSON is needed: a successful groom node always proceeds to the
conformance gate, which re-proves your output mechanically. Emit the
failed-outcome object above ONLY when you are genuinely stuck.
