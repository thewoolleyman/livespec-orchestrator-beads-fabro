# Design record — splitting finding-disposition out of `review_fix`

Status: independently adversarially reviewed 2026-07-23 (Codex,
cross-checked against the Fabro engine source; verdict
SOUND-WITH-CHANGES). Both blocking findings are incorporated into the
sections below, and every finding's disposition is recorded in
§"Adversarial review disposition". Supervisor/maintainer approval of
the grooming cut is the remaining design gate.
This document is the design record that resolves `bd-ib-o35rcx`
("review_fix conflates finding-disposition with fix implementation —
record the design or restructure"). The maintainer's decision,
relayed via the thread supervisor on 2026-07-23: **restructure by
splitting** — do not merely write a rationale for the status quo, and
do not fold disposition into the reviewer's next visit.

Companion archaeology and ecosystem survey: `review-fix-conflation.md`
(same directory). Ledger anchors: epic `bd-ib-cvgjop`, design item
`bd-ib-o35rcx`, implementation slices filed per §"Rollout" below.

## The decision

Split the current `review_fix` node's two responsibilities into two
cohesive, separately-owned steps in the `implement-work-item` graph
(`.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro`):

1. **`disposition`** — adjudicates each `[BLOCKING]` review finding:
   ACCEPT it, or REJECT it with a one-line rationale. Read-only
   judgment; it edits no code. Independently promptable
   (`prompts/disposition.md`) and independently model-selectable (its
   own `disposition_adapter` run input, the same env-prefix mechanism
   `review_adapter` uses).
2. **`review_fix`** — implements the ACCEPTED findings, and nothing
   else. It loses all adjudication authority: it may no longer decline
   a finding; if it believes an accepted finding cannot be implemented
   in scope, that is the needs-human `failed` outcome, not a
   unilateral rejection.

This matches the ecosystem-blessed reference shape the research
identified: `spec-dod-multimodel.fabro` separates audit (findings) →
triage (disposition) → fix_batch (implementation). The livespec-family
conflation was an unexamined addition on top of the inherited
approve/fix routing pattern (see `review-fix-conflation.md` §Part 1).

## Target topology

Today:

    janitor --Green--> review --fix (guard)--> review_fix --> janitor
                        |approve -> pr; cap edges; Blocked/unmatched -> escalate

Target (changed edges marked NEW/CHANGED):

    janitor --Green--> review
    review -> disposition   [label="fix",
        condition="preferred_label=fix &&
        context.internal.node_visit_count < {{ inputs.review_fix_visit_cap }}"]
        (CHANGED: same edge as today's review->review_fix — same label,
         same guard on the REVIEW node's own visit count — only the
         target node changes)
    review -> pr            [approve]                       (unchanged)
    review -> pr            [ship on review cap]            (unchanged)
    review -> escalate      [needs-human at cap]            (unchanged)
    review -> escalate      [Blocked, outcome=failed w=100] (unchanged)
    review -> escalate      [unmatched review outcome]      (unchanged)

    disposition -> review_fix [label="fix accepted",
        condition="preferred_label=fix"]                    (NEW)
    disposition -> review     [label="all rejected",
        condition="preferred_label=all_rejected"]           (NEW)
    disposition -> escalate   [label="Blocked",
        condition="outcome=failed", weight=100]             (NEW)
    disposition -> escalate   [label="unmatched disposition outcome"]
                                                            (NEW, unconditional fallback)
    review_fix -> janitor                                   (unchanged)

Node attributes for `disposition`: `backend="acp"`,
`acp.command="{{ inputs.disposition_adapter }}"`, `timeout="1800s"`
(review-class: it reads and judges, it does not build),
`max_retries=1` (the bn4 transient-retry discipline), `max_visits=10`
(runaway-loop backstop; see next paragraph — S2 also raises
`review_fix`'s backstop from 4 to 10 for the same reason).

**Backstop sizing (adversarial finding #4, BLOCKING, accepted).** A
node that reaches `max_visits` hard-aborts the WHOLE run at entry
(`Error::VisitLimitExceeded`) — not a graceful escalate. Under the
default `review_fix_cap=3` (guard `< 4`) a backstop of 4 is never
reached, but `review_fix_cap` is a live per-item-overridable policy
key with NO upper bound in its schema (`_drive_config_schema.py`
`positive_integer`), so any override ≥ 4 would have tripped the old
`review_fix.max_visits=4` — a pre-existing latent defect this design
would otherwise have copied onto a second node. Resolution: both
backstops become 10, comfortably above any sane per-item override
while still bounding a routing-regression runaway (which
`stall_timeout` cannot catch — an active loop streams events). The
graph comment at both nodes names the coupling: the backstop MUST
exceed the largest supported `review_fix_cap` override. Schema-capping
`review_fix_cap` (e.g. ≤ 9) was considered and deferred: an operator
setting a 10-round cap is already off the policy map, and the abort is
then the runaway bound doing its job; a follow-up may cap the schema
if the maintainer wants the coupling mechanical.

### Why "all rejected" routes straight back to `review`

When every blocking finding is rejected, no code changed — the tree
that entered `review` janitor-green is byte-identical. Routing through
the janitor again would (a) burn a full `just check` per all-rejected
round and (b) inflate the janitor's visit count, which the
`janitor -> fix` guard reads (`node_visit_count < 3`) — green
re-validation visits already tighten a later Red's remaining fix
budget today, and this design declines to add a new source of that
inflation. The risk accepted: a misbehaving disposition agent that
edits code despite its read-only prompt would put unvalidated edits in
front of `review`. That tail risk is bounded by two standing gates —
the reviewer itself, and the repo's CI check matrix, which runs the
same `just check` suite on the PR before the rebase-auto-merge can
land — plus a prompt-level tripwire (adversarial finding #3,
ADVISORY, accepted): `review.md`'s re-review section is told that on
an all-rejected round NO new janitor validation occurred, and that a
diff differing from the last-reviewed state despite an "all rejected,
nothing changed" disposition is grounds to DISTRUST the disposition
record (treat as blocking / needs-human) rather than assume the tree
is still green. (Considered and rejected: `disposition -> janitor` on
all-rejected — safe but pays the two costs above for a
prompt-violation tail case CI already backstops.)

One inherent trade-off acknowledged (finding #8): a separate
disposition step judges findings WITHOUT ever attempting the fix
(today's review_fix could "try it and see" before rejecting), which
may shift some over-rejection risk onto the reviewer's
honor-the-rejection rule. This is exactly the ecosystem-blessed
audit → triage → fix separation (spec-dod), and the re-review
re-confirmation authority is the check on it.

## Constraint compliance (the three from the maintainer brief)

**(a) No schema-validated structured output on ACP.** The disposition
verdict rides exactly the engine channel the review node already uses:
best-effort extraction of the LAST balanced JSON object with
recognized routing fields (`preferred_next_label`, `context_updates`,
`outcome`, …), which IS honored on the ACP backend
(fabro `structured_output.rs`; `review-fix-conflation.md` §"Engine
machinery notes"). The disposition node ends its reply with:

    {"preferred_next_label": "fix" | "all_rejected",
     "context_updates": {"finding_dispositions": "<per-finding record>"}}

- `preferred_next_label` routes the two success edges.
- `context_updates` carries the per-finding record (`ACCEPTED <ref>` /
  `REJECTED <ref> — <rationale>`, one per line). **Durability is
  best-effort and prompt-enforced, NOT engine-guaranteed (adversarial
  finding #5, BLOCKING, accepted):** `context_updates` entries are
  last-write-wins (`HashMap::insert`, never merged), so a single key
  re-transcribed each round could be silently narrowed by one bad
  round. Two mitigations: (1) STRUCTURAL — each disposition round
  writes its record under a round-distinct key
  (`finding_dispositions_r<N>`, where N is one more than the count of
  prior `finding_dispositions_r*` keys visible in its preamble), so
  earlier rounds' records survive in run context independent of prompt
  discipline, and non-internal context keys demonstrably surface into
  later nodes' preambles; (2) FLOOR — the record is always ALSO plain
  text in the reply (prior-stage transcript), and the re-review honor
  rule already requires the reviewer to re-confirm a genuine
  correctness/security defect before overriding a rejection, so a lost
  record degrades to the pre-split free-text status quo, never below
  it. Note honestly: the split adds one node-hop per accepted round,
  so a fixed-size stage-history preamble window covers fewer rounds
  than pre-split — the round-keyed context entries (which ride run
  context, not the stage-history window) are the compensation. If
  extraction finds no recognized JSON at all, the unconditional
  fallback edge parks the run at `escalate` exactly as an unmatched
  review outcome does today.
- If disposition cannot do its job (e.g. cannot see the findings), it
  ends with `{"outcome": "failed", "failure_reason": …}` → the
  Blocked edge.

**(b) Janitor↔fix budget isolation untouched.** The `janitor`, `fix`
nodes, the `janitor -> fix` guard (`< 3`), `fix.max_visits=3`, and the
`non_converged` terminal are not touched by this change. `review_fix`
keeps its own backstop (raised 4 → 10 per finding #4, still decoupled
from the janitor loop). The two fix loops' budgets
remain fully decoupled, per the workflow's recorded design intent
(`workflow.fabro` review_fix comment).

**(c) Review gate blocking-by-default + cap semantics preserved.**
The graceful bound stays WHERE it is today: on the `review` node's own
visit count, rendered from the same `{{ inputs.review_fix_visit_cap }}`
input (Dispatcher-supplied, `dispatcher.review_fix_cap + 1`). All four
past-cap/approve edges on `review` are byte-unchanged, including the
`merge_on_review_cap` escape hatch and the needs-human default. An
all-rejected round consumes review-visit budget exactly as it does
today (today it burns a `review_fix` + janitor pass to do so; the
budget accounting is equivalent, the wall-clock is strictly less).
`review_fix_visit_cap` keeps its name and meaning: fix ROUNDS granted
by the reviewer.

## Prompt suite

- **`prompts/disposition.md` (NEW).** Role: implementation-side triage
  — not the reviewer, not the fixer. Reads the `[BLOCKING]` findings
  from prior stage context; MAY read the repo to verify a finding's
  factual claims; MUST NOT edit any file. Per finding, exactly one of
  ACCEPT (in-scope and correct) or REJECT with a one-line rationale
  (out-of-scope / not-applicable / factually wrong / would require
  scope expansion — the current review-fix.md rejection grounds,
  carried over verbatim in substance, including "a fix that expands
  scope is itself wrong; prefer rejecting such a finding"). Output:
  the per-finding record lines, then the routing JSON (§a above) as
  the last line. Needs-human escape for a disposition it cannot make.
- **`prompts/review-fix.md` (REWRITTEN).** Implements ONLY the
  findings the disposition record marks ACCEPTED; rejected findings
  are out of bounds. No adjudication language remains. Keeps: the
  scope discipline, the HONEST-checks/no-detector-evasion block, the
  Red-Green-Replay and hook rules, "re-run `just check` until green",
  the needs-human protocol (now also the route for "an accepted
  finding cannot be implemented within scope" — it may argue there,
  not silently skip).
- **`prompts/review.md` (§"On re-review" REVISED).** Honor rejections
  recorded in the disposition record (`finding_dispositions_r*`
  context + prior stage transcript) unless a genuine
  correctness/security defect is re-confirmable — same honor rule as
  today, with the disposition record replacing "the implementer
  rejected" free text as the source. Adds the all-rejected tripwire
  (finding #3): after an all-rejected round no fresh janitor pass ran;
  an unexpectedly-changed diff invalidates the disposition record.
- **`prompts/fix.md` (opportunistic, finding #7).** Its premise line
  ("the previous stage's `just check` FAILED") is false for
  escalations that parked from `review_fix` (pre-existing) or
  `disposition` (new) and the operator answered [R]. Generalize the
  premise to name its possible origins in the same change — not
  required for correctness (budgets and needs-human backstops bound
  it), but S2 already touches the neighboring prompts.

## Model/adapter independence

New `[run.inputs]` key in `workflow.toml`:

    disposition_adapter = "npx -y @agentclientprotocol/claude-agent-acp"

Default: the un-pinned Claude adapter (implementer-class model), NOT
the Opus-pinned review adapter — adjudication quality matters, but
doubling review-class spend per round is a policy call the maintainer
can make by editing one line; the mechanism (env-prefix pinning,
exactly like `review_adapter`) is documented at the key. This default
was flagged in the grooming cut and DECIDED 2026-07-23 (supervisor,
under maintainer delegation): keep the un-pinned implementer-class
default — bounded triage task, zero measured disposition defects to
justify review-class spend, one-line reversible knob. No
Dispatcher change is required for the default to take effect
(`workflow.toml` supplies inputs the Dispatcher does not override).

## Telemetry

`_dispatcher_review_gate_parse.py` derives `review.fix_rounds` by
counting `edge.selected` events from `review` with
`to_node == "review_fix"` (line 39). Under the new topology that edge
targets `disposition`, so the membership becomes
`to_node in {"review_fix", "disposition"}` — counting rounds GRANTED
by the reviewer (unchanged meaning; an all-rejected round is still a
round, exactly as it is today when it flows through review_fix), and
remaining correct for pre-split historical runs. `visit_count`,
`hit_cap`, `shipped_on_cap`, and the terminal `verdict`
(`preferred_label` ∈ approve/fix) are derived from `review`-sourced
edges only and are unaffected. Scenario 20's telemetry scenario
(`review.verdict`, `review.fix_rounds`, `review.hit_cap`,
`pr.shipped_on_cap`) stays satisfied with unchanged attribute
semantics. The parser change ships in the SAME commit as the graph
change (one RGR unit) so fix-round telemetry is never silently zero.

## Specification impact (spec-change tier — supervisor-re-routed 2026-07-23)

Ratified Scenario 20 codifies the conflation ("When the implementer
addresses or rejects each blocking finding with a rationale",
`SPECIFICATION/scenarios.md:381`). The restructure therefore lands
spec-first:

1. A `propose-change` amending Scenario 20's Gherkin IN PLACE (no new
   `## ` H2 ⇒ no `tests/heading-coverage.json` co-edit): the
   fix-round scenario becomes disposition-step language (disposition
   adjudicates each blocking finding; the fix stage implements each
   accepted finding; the janitor re-validates; the change is reviewed
   again), plus one added Gherkin scenario in the same fence for the
   all-rejected round (routes directly to re-review; asserts
   explicitly that the janitor does NOT re-run — finding #9 — and that
   the rejection record is carried and honored). A design-record citation per
   contracts.md §"Intent preservation" accompanies the review-gate
   text, citing THIS document, `bd-ib-o35rcx`, and the 2026-07-23
   maintainer directive.
2. Only after the revise ratifies does the implementation slice land.

Routing (supervisor disposition, 2026-07-23, under maintainer
delegation): S1 is NOT maintainer-blocked — the maintainer already
made the substantive decision (the split); the Scenario 20 amendment
is its mechanical encoding. It proceeds autonomously:
`propose-change` → independent adversarial Fable review of the
proposal → on a NO-BLOCKERS verdict the revise accept is driven
in-session citing the 2026-07-23 maintainer directive as the design
authority; any review blocker routes up through the supervisor. S1
stays host-only (non-null `factory_safety`) — never drained.

## Alternatives considered and rejected

- **Status quo + rationale** (research option 1): rejected by the
  maintainer 2026-07-23 — the coupling contradicts the ecosystem norm
  and denies per-step prompt/model control.
- **Reviewer-owned disposition at re-review** (option 2): explicitly
  named NOT the target by the maintainer — it merges disposition into
  the reviewer's visit, which is the same coupling one node over, and
  still yields no independently promptable/model-selectable
  disposition step.
- **Human disposition gate** (option 3): docs-blessed but adds
  operator latency at exactly the mechanism where 40% of failures
  already die unanswered (`failure-telemetry-2026-07-23.md`).
- **`disposition -> janitor` on all-rejected**: see §"Why 'all
  rejected' routes straight back to review".

## Rollout, evidence, and closure conditions for `bd-ib-o35rcx`

Slices (children of epic `bd-ib-cvgjop`; ids recorded in the grooming
cut and on the epic):

- **S1 — spec amendment** (`chore(spec)`, maintainer-gated): the
  propose-change + revise of §"Specification impact". Hand/in-session;
  a spec-change-tier item is design-human-gated and never
  factory-dispatched.
- **S2 — the split** (one Red-Green-Replay unit, factory-safe;
  depends on S1): `workflow.fabro` topology, `prompts/disposition.md`,
  `prompts/review-fix.md` rewrite, `prompts/review.md` re-review
  revision, `workflow.toml` `disposition_adapter` input, and the
  `_dispatcher_review_gate_parse.py` membership change with its paired
  test as the Red. `.claude-plugin/.fabro/**` is not gated by the
  GitHub App `workflows` permission, so the push publishes normally.
- **S3 — live-exercise evidence** (supervised, depends on S2): the
  first post-merge dispatch's `fabro events <run-id> --json` shows
  `edge.selected` review→disposition and disposition→review_fix (or
  →review on an all-rejected round), the `finding_dispositions`
  context value is present, and the emitted `livespec-dispatcher` span
  carries a correct `review.fix_rounds`. Evidence is journaled on
  `bd-ib-o35rcx`.

`bd-ib-o35rcx` closes only when BOTH hold: (1) this design record has
had an independent adversarial review (finding-disposition on that
review's findings recorded here or on the item), and (2) S3's
journaled live-exercise evidence exists — the restructure is
behavior-bearing and "landed" is proven by a real run, not by merge.

## Adversarial review disposition (2026-07-23)

Independent review: Codex, cross-checked against the Fabro engine
source (`routing.rs` edge-selection waterfall, `executor.rs` visit
limits, agent/prompt/structured_output handlers, preamble builder)
rather than this document's own claims. Verdict:
**SOUND-WITH-CHANGES**. Per-finding dispositions (all folded into the
sections above and into slice S2/S1 scopes):

1. Edge-condition completeness — CLEARED (engine tier-waterfall
   verified; every (outcome, label) combination fails closed to
   `escalate`). No change.
2. Cap accounting — CLEARED (1:1 round correspondence verified). No
   change.
3. All-rejected janitor skip — ADVISORY, ACCEPTED: `review.md` gains
   the no-fresh-janitor-pass tripwire (§"Why 'all rejected' routes
   straight back to review", §"Prompt suite").
4. `max_visits` "structurally unreachable" claim FALSE under an
   unbounded `review_fix_cap` override — BLOCKING, ACCEPTED: both
   backstops become 10 with the coupling documented; schema cap
   considered and deferred (§"Backstop sizing").
5. Durable-record claim overstated (last-write-wins context;
   truncation window shrinks post-split) — BLOCKING, ACCEPTED: claim
   downgraded to best-effort; round-distinct
   `finding_dispositions_r<N>` keys added as structural hardening;
   floor argument recorded (§"Constraint compliance (a)").
6. Telemetry membership widening — CLEARED (necessary and
   sufficient). No change.
7. `fix.md` false premise for review_fix/disposition-originated [R]
   answers — ADVISORY, ACCEPTED opportunistically into S2
   (§"Prompt suite").
8. Judgment-without-attempting-the-fix trade-off — ADVISORY,
   ACKNOWLEDGED (§"Why 'all rejected' …", closing paragraph).
9. Scenario 20 all-rejected Gherkin must assert the janitor does not
   re-run — ADVISORY, ACCEPTED into S1's scope (§"Specification
   impact").
10. Adapter default / constraints (a)(b) — CLEARED. No change.

Gate per the supervisor's 2026-07-23 direction: S1 (`bd-ib-t5u62i`)
and S2 (`bd-ib-fe574e`) do not proceed until the supervisor has
reviewed these dispositions; everything else in the grooming cut
proceeds in parallel.
