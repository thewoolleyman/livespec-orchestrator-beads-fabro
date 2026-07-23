# The review_fix disposition+fix conflation — design archaeology + ecosystem verdict

Question investigated: in the `implement-work-item` graph, the
`review_fix` node BOTH adjudicates each `[BLOCKING]` review finding
(accept it, or reject it with a one-line rationale) AND implements the
accepted fixes, with rejections carried as free text that the next
review visit is prompted to honor. Why are those two responsibilities
in one node — was that justified anywhere, and is it a blessed Fabro
pattern?

Verdict: **the conflation was never a justified design decision, and it
is not a blessed Fabro pattern.** It arrived fully formed with the
review gate (Slice A), was never argued against any alternative, and
every Fabro doc, bundled example, and independent public project keeps
finding-disposition with the reviewer (as a structured verdict) or a
human, separate from fix implementation. Ledger item: `bd-ib-o35rcx`
(child of epic `bd-ib-cvgjop`).

## Part 1 — Repo archaeology (what the history records)

### Origin: born unargued

Commit `c7eaf1c` "chore: add Claude review-gate node + Scenario 20 to
the implement graph (Slice A)" (2026-06-23, PR #148, work-item
`bd-ib-egms32`) introduced the `review` node, the `review_fix` node,
AND both prompts in one change. The entire recorded rationale for the
node's dual role, verbatim from the commit body:

> "Adds a Claude Opus 4.8 review-only node between a green janitor and
> the pr stage in the implement-work-item Fabro graph, plus a
> review_fix node that addresses or rejects the reviewer's blocking
> findings."

It *describes* the behavior; it does not justify housing disposition
and fix in one node.

### The only "separate node" argument answers a different question

`workflow.fabro:144-152` justifies why `review_fix` is separate from
the janitor's `fix` node — budget isolation between the two fix loops:

> "A SEPARATE node from `fix` ON PURPOSE: it keeps the working
> janitor<->fix hard-gate loop and its visit budget completely
> untouched, and decouples the two fix budgets."

That is the review_fix-vs-fix axis, NOT the disposition-vs-fix axis.

### "Implementer owns accept/reject" was asserted once, never defended

The single design-decision appearance is one enumerated guardrail in
`bd-ib-egms32`: "implementer-can-reject-with-rationale." The prompt
encodes it (`prompts/review-fix.md:15-21`):

> "You are the implementer — you may decline a finding you judge
> incorrect or beyond this work-item. State the rationale plainly; the
> next review pass is told to HONOR it unless it is a genuine
> correctness/security defect."

No alternative (a separate triage node, reviewer-owned disposition,
human disposition) was ever recorded as considered-and-rejected. The
"next-review-pass honors the rejection" mechanism
(`prompts/review.md:102-106`) is likewise asserted, never justified;
there is no persisted disposition record — the anti-relitigation
guarantee rests on one sentence in the reviewer prompt with the prior
turn's free text as the only carrier.

### Chronology

- **2026-06-23 — `c7eaf1c` / `bd-ib-egms32` (Slice A), PR #148.**
  review + review_fix + both prompts. Routing was ship-on-cap
  (advisory gate). The conflation is present from here, unchanged.
  Codified as Scenario 20 (spec history v015).
- **2026-07-16 — `bdb84d1` / `bd-ib-6ytmik` ("O8"), PR #680.** Made the
  gate blocking-by-default, cap configurable
  (`dispatcher.review_fix_cap` default 3, `merge_on_review_cap` default
  false). Changed past-cap routing ONLY; node internals untouched.
- **2026-07-16 — `3c832d6`.** Unconditional review→escalate fallback
  edge. Routing hardening only.
- Later prompt hardening (`5d270c8` anti-evasion, `c890acc`, `764f680`,
  `72b08f1`) — all leave the disposition model intact.

### The likely origin is pattern inheritance — and the cited precedent does not match

The parent epic `bd-ib-un226z` records the shape's justification as:

> "Reviewer routing is the idiomatic Fabro approve/fix
> preferred_next_label pattern (confirmed canonical:
> spec-dod-multimodel.fabro does Codex-implements / Opus-reviews)."

But (see Part 2) spec-dod **separates** disposition (audit → triage)
from fix (fix_batch). The approve/fix *routing* was inherited
faithfully; the disposition+fix *coupling* inside `review_fix` was an
unexamined addition on top.

### The spec's own standard flags this

`SPECIFICATION/contracts.md:1270-1281` §"Intent preservation": every
load-bearing semantic "MUST carry its rationale and MUST cite its
design record," and a missing design record "is itself a finding that
MUST be surfaced to the maintainer." The review *gate*'s existence IS
well-justified (`contracts.md:1259-1268`); the *node structure* is an
undocumented default.

## Part 2 — Fabro ecosystem verdict (docs, examples, third-party usage)

Source: the local fabro checkout `/data/projects/fabro` (docs are the
`docs/public/*.mdx` sources of docs.fabro.sh) plus a GitHub code sweep
of public `.fabro` workflows.

### The canonical pattern: reviewer routes, a separate node fixes

`docs/public/workflows/transitions.mdx:100-115` and
`docs/public/agents/outputs.mdx:102-118` teach the review loop as: the
reviewer emits ONLY a structured verdict —
`{"preferred_next_label": "fix"}` / `{"preferred_next_label":
"approve"}` — and "fix" routes to a SEPARATE node (the fixtures route
`review -> implement`, back to the original implementer). The reviewer
never edits.

### The richest example separates disposition even harder

`test/docs/examples/definition-of-done/spec-dod.fabro`:
`audit_llm`/`audit_agent` (disposition, structured JSON verdicts) →
`triage` (merge + prioritize, decides Done vs Fix) → `fix_batch` /
`build_fix` (implement) → `final_audit` (re-verify) → `review_gate`
(human hexagon). Disposition travels as structured JSON in context,
never as free text a later node re-reads. The production `goal`
workflow (`.fabro/workflows/goal/workflow.fabro`) hands "remaining
work" forward as a structured context key
(`context_updates.goal_remaining_work`).

### Human disposition after review is explicitly blessed

`docs/public/workflows/human-in-the-loop.mdx:93-99`: "Where to place
human gates … **After review** — Confirm that a code review's findings
are worth fixing." That is exactly the accept/reject decision the
current graph hands to the implementer as free text.

### No independent project conflates; one does the strict opposite

GitHub sweep of all public workflows using `preferred_next_label`:

- Upstream `fabro-sh/fabro` + doc-copy forks: reviewer-routes /
  implementer-fixes only.
- `dstengle/shopsystem-*` (independent): structural rule is the INVERSE
  of ours — "every state-changing action … is a NATIVE non-LLM script
  node; **agents may ONLY judge and route**"; its reviewer "MUST NOT
  modify source/tests" and emits a structured 3-way verdict.
- `natea/*`, `sundaiclaw/*`: separate review + separate postmortem
  nodes emitting structured verdicts.
- The ONLY graphs with our shape are same-author livespec-family
  siblings (`livespec-console-beads-fabro`, `openbrain`) sharing this
  template — not independent adoption.

### Engine machinery notes (constraints on any restructure)

- Verdict extraction is an engine feature
  (`fabro-workflow/src/handler/structured_output.rs`): the LAST
  balanced JSON object with a recognized routing field
  (`preferred_next_label`, `outcome`, `failure_reason`,
  `context_updates`, …) is applied; edges resolve `preferred_label` and
  `context.<key>` (`src/condition.rs:19-21,40-47`). This best-effort
  extraction IS honored on the ACP backend.
- BUT schema-VALIDATED structured output (`output_schema="routing"`,
  with repair turns) is **not available on ACP**
  (`outputs.mdx:147-149`) — so a fully structured per-finding
  disposition channel is not free under the OAuth-only/ACP posture,
  while moving disposition OWNERSHIP (reviewer-owned at re-review, or a
  human gate) requires no engine features at all.

### Verified-version caveat

The engine/docs reading was done on fabro `main` (v0.289-nightly), not
the pinned v0.254 tag; the machinery matches the live docs, but the
0.254 diff was not taken. No doc RULE forbids a fixer from
adjudicating — the verdict here is "uniformly contradicted by every
example and independent usage," not "explicitly banned."

## Options recorded for the maintainer decision (`bd-ib-o35rcx`)

1. **Status quo + design record** — keep implementer-owned disposition,
   write the rationale (fastest; legitimizes the free-text channel).
2. **Reviewer-owned disposition at re-review** — review_fix only fixes
   or argues; the REVIEWER's next visit issues the per-finding
   accept/reject verdict (structured via `context_updates`). No engine
   work; prompt + edge changes only.
3. **Human disposition gate after review** — the docs-blessed shape;
   adds operator latency (relevant: 40% of failures already die
   unanswered at the existing human gate — see
   failure-telemetry-2026-07-23.md).

Telemetry context: review approves 83% first-pass with ~0 misses, so
this is a correctness-hygiene/intent-preservation question, not a
merge-rate lever.
