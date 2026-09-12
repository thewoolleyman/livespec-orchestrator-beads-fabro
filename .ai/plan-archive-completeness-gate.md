# The plan-archive completeness-review gate

Read this before archiving a plan, and before closing any plan epic whose
directory has already been moved under `plan/archive/`.

## The trap

`archive_thread(...)` has TWO gates:

1. **Mechanical child disposition** — refuse while any linked plan member is
   not `closed`.
2. **Independent completeness-review evidence** — recorded durably through
   `record_completeness_review_evidence(...)`.

Performing the `git mv` into `plan/archive/<slug>/` **by hand in a pull
request runs NEITHER**. The move merges, master looks archived, the plan
directory is where it belongs — and the second gate was never executed.
Nothing anywhere reports that it was skipped. The next session sees a merged
archive move and reasonably concludes the archive is complete.

It is not. **A hand-moved plan directory means the epic is NOT archived.**
Keep the epic open and commission the review.

## Why the gate is not ceremony — a measured instance

Plan `pluggable-factory-workflow-configs` (epic `bd-ib-yqpdrt`), 2026-09-07.
The outgoing session moved the directory by hand in PR #2331 and self-reported
that it had skipped the review gate. Commissioning the review returned
**NOT-COMPLETE on a real defect**:

Scenarios 118 and 119 — the two scenarios that plan's **own** v100 and v101
revise passes added — carried `test: "TODO"` entries in
`tests/heading-coverage.json` whose `work_item` was `bd-ib-yqpdrt` and whose
own `reason` text named the plan **by slug** as the owed party. Both stated
preconditions had since been discharged. No live carrier existed anywhere:
zero hits across all 1005 ledger records over `title` / `description` /
`acceptance_criteria` / `notes`, and a `git grep` over `tests/` on
`origin/master` hit only `heading-coverage.json` itself.

**Nothing mechanical would ever have caught it.** An *owned* TODO entry passes
`check-no-todo-registry` (the release tier arms only on an *unowned* TODO), and
the child-disposition gate reads only children, never file entries. Closing the
epic on the strength of the merge would have orphaned that debt onto a closed
epic under `plan/archive/`, where nothing would surface it again.

## Calibration, so this is not overweighted

TODO entries owned by closed items are **common**: 12 of the 20 owned TODO
entries in `heading-coverage.json` name a closed owner. **"Owner is closed" is
not by itself a finding.** What distinguished these two is narrower — the
`reason` text named the PLAN as the owed party against a precondition that had
since been met, and the same plan had already filed `bd-ib-vc3j4p` for the
word-for-word identical Scenario 117 debt, so it had demonstrably understood
the obligation and simply not applied it twice.

## Commissioning the review

The reviewer must have had **no role in the plan's implementation**, must
compare every research requirement and explicit deferral against the complete
child set, must spot-check closure evidence **against the forge**, and must be
read-only — recording the evidence is the archiving session's job, not the
reviewer's.

Give it a genuinely adversarial brief: a rubber stamp is worthless, and say so.
Hand it the beads read-surface traps (`bd comments` not `bd show --json`; the
`text` key; `--status all`; the child-enumeration union) or it will reach a
confident wrong answer through a surface this repo has already measured.

Two mechanics worth knowing before you start:

- A long report can be **truncated in transit**. Have the reviewer write its
  verdict to a file and reply with a short confirmation instead. A truncation
  that lands mid-report can silently drop the finding.
- Verify the reviewer's conclusions rather than relaying them. When it asks for
  carriers, file them and send them **back** for independent re-verification
  rather than asserting the discharge yourself.

## Discharging a blocking finding

The archive rule is that remaining work is acceptable **if and only if** it is
transferred to NAMED follow-up plans or work-items, and the archive record
states those names exactly. So the deciding question is not "is there residual
work" but "**is this residual NAMED in a live carrier**".

When filing carriers to discharge a finding:

- File them **STANDALONE** — no `parent-child` edge, no dotted id. A carrier
  filed as a child of the epic reopens the mechanical gate you just passed.
- Route each through `apply_intake_dor` or it sits at `backlog` and
  `drive --action impl:<id>` refuses it.
- Keep `## Scenario NN` **out of** `acceptance_criteria` — a scenario reference
  there makes the item unsatisfiable against merged-diff evidence (defect class
  `bd-ib-99a1`). Put the traceability in the **description** instead, and verify
  the separation mechanically in both directions rather than by intent.
- Execute the criteria parse through `effective_criteria(item=...).parse_display()`
  rather than counting bullets by eye; bullet count and parse count are exactly
  what diverge when criteria drafting goes wrong.
- Prefer positive criteria. A negative assertion ("the entry no longer names
  `<epic>`") can pass, because the removed line supplies the diff vocabulary,
  but if a dispatch fails acceptance on it the fix is to reword it positively by
  naming the new owner — not to conclude the work is undone.

## Recording the evidence

Record **both** attestations when a review flips. The false one is accurate
history and must not be retracted; the successor supersedes it. This is
verifiable rather than a matter of taste:
`valid_completeness_review_evidence_id(...)` REJECTS an
`attests-complete-requirement-coverage: false` record (returns `None`) and
ACCEPTS the successor — which is the proof the gate actually reads what you
wrote. Run it against both ids before closing the epic, and confirm
`undisposed_plan_child_ids(...)` is still empty after any carrier filing.

`reviewer-identity` must differ from the archive actor (`plan-archive`), and
`separate-reviewer` must be `true`, or the record is not evidence.

## The gate is honest-actor dependent

`_is_valid_evidence` checks exactly four things: the evidence id matches,
`reviewer-identity` differs from `plan-archive`, `separate-reviewer` is `true`,
and `attests-complete-requirement-coverage` is `true`. **Nothing in it can tell
a genuine independent review from an archiving session writing those four
fields about its own work.** The gate records the claim; it cannot verify the
independence the claim asserts. The load-bearing act is therefore commissioning
a reviewer that actually had no role in the implementation — the mechanism only
certifies that you say you did.

Measured 2026-09-12 on `bd-ib-uy4lp7`: the independent reviewer caught two
instrument failures the implementing session could not see in its own work (a
discriminator naming a field no dispatch writes, and a "verified discharged"
claim proved on a green run that cannot enter the fail-fast branch it tested),
and disclosed one of its own — a `grep -rl` probe returning a clean zero that
would have falsified a requirement. See `AGENTS.md` Rule 4's second-party
corollary for why that symmetry is the argument for the split.

## The evidence decays — re-measure before quoting it

A recorded attestation is **a claim with a timestamp, not a standing
guarantee**: it attests a measurement taken on one day against the tree as it
stood then. This is Rule 3's case — the danger is not writing something false,
it is writing something true that STOPS being true while still reading as
authoritative in the place a successor trusts instead of checking, and a closed
plan's evidence comment is exactly such a place.

Before citing an evidence id, re-measure whatever that plan's claims actually
turn on. For an archived factory-graph plan that means the graph's unconditional
edges and a `fabro validate` exit 0 (shape alone does not discriminate — the
broken build had the same node and edge counts as the fixed one), the CI gate's
fail-closed wiring read from the JOB LOG rather than the job's green (a skipped
check and a passing check are the same colour), and whether any nominal
follow-up carrier is still undispatchable.
