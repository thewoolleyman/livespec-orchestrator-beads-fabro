## The maintainer's statement of what done means

2026-10-19 (UTC), maintainer, in the definition-and-proof-of-done session:
"The whole goal and vision of LiveSpec is that the implementation and the specification are kept in sync in a virtuous feedback loop. So, something pointing to a wrong citation is a wrong specification, or at best a mismatch between the implementation and the specification, and we absolutely do not want to just ignore it."
"" implementation work was filed ahead of the spec."  This is the absolutely most concerning and dangerous day. Why is this happening, and why is it even possible?"
"blocked for features that are expanding the spec.  This should not apply to bugs . Chores and non-functional requirements are also have leeway, not every single thing must be or should be overspecified. Same with features too, actually, rejection should not turn into overspecification.  That is counterproductive.  The spec should be generalized to be correct rather than always expanded.  But actual new behavior should get new spec."
"also what to do about the existing drift/gap noise and debt?"
"Yes create it"

## Definition of Done assertions derived from that statement

- A feature whose asked-for behaviour no ratified clause states cannot be dispatched until a linked proposed change for that behaviour has been ratified.
- A bug fix, a chore or a non-functional item is dispatched without requiring a new spec clause.
- When an existing clause, generalized, would state a new behaviour, the proposed change filed for it amends that clause instead of adding a new one.
- After each merge, a drift pass over the merged change files a proposed change for any new behaviour the spec does not state, and records a completed coverage point.
- The ledger-intent scan lists the open items whose asked-for behaviour the spec does not state.
- Both orchestrators, livespec-orchestrator-beads-fabro and livespec-orchestrator-git-jsonl, run the same is-this-stated-by-the-spec judgement from livespec-runtime.
- Every open item the 2026-10-19 spec-governance audit classified as unspecified ends with a ratified clause, a linked proposal, or a recorded reclassification as a bug, a chore or a non-functional item.
- Every merged change found to add unspecified behaviour ends specified, removed, or recorded as accepted implementation detail.
- A completed drift coverage point is recorded after reconciliation, and later drift runs report only merges after it.
- Gap detection reports only spec headings that have no exercising test, not clauses that lack a work item.
- Each reconciliation batch's ratified spec changes do not increase the spec's total size beyond the clauses that state genuinely new behaviour.

# Spec-implementation lockstep: why implementation runs ahead of the spec, and how to stop it

Opened 2026-10-19 (UTC) by the `definition-and-proof-of-done` session. The plan grew out of the
R258 root-cause investigation of `bd-ib-3now6p`, and the maintainer moved it into this new plan.
Companion notes:
- `002-archaeology-drift-and-core-orchestrator-split-2026-10-19.md`: the evidence from
  livespec core and from this repository.
- `data/audit-2026-10-19-open.jsonl` and `data/audit-2026-10-19-merged.jsonl`: the per-item
  audit verdicts.

## 1. How this started: two Definition-of-Done gate refusals on one item

`bd-ib-3now6p` was refused twice by the factory's `dod_gate` node:
- Run `01M5AWN154ED` (hp): check 4, coherence.
- Run `01M5B2G99FB0` (gmktec): check 6. The `References:` line named `## Dispatcher policy
  settings`, but Scenario 182 governs the item.

Before each dispatch, the host-side filing display (`filing_display`, build 0.224.0) reported
`definition-of-done findings: none`. I reproduced that against the exact description each run
was dispatched with, read from the run exports. Three causes:
1. Check 4 has no host-side counterpart, and the two sides read different inputs. The wall reads
   only `item.description`. The gate reads the assembled goal, which includes the ledger-comment
   riders, and the contradiction was between a Definition-of-Done bullet and riders [1] and [3].
2. Check 6's host-side form is advisory only, and its matcher cannot find this case:
   - It compares assertion vocabulary with scenario heading titles and needs 4 shared distinctive
     terms. The best overlap with Scenario 182's title was 3.
   - An advisory finding never withholds dispatch anyway.
3. The gate is a model judgement, so it does not always give the same answer. Run 1's description
   carried the same non-scenario reference line, and run 1's gate did not flag it.

## 2. What the gate actually refuses for

I surveyed every `dod_gate` ending recorded in this tenant's `livespec-needs-human-cause`
comments. There were 37 in all:
- 23 are infrastructure endings: a graph defect, or the session limit.
- 14 are real judgements:
  - 10 were about the `References:` citation;
  - 1 was a contradiction (3now6p, run 1);
  - 3 were about proof mode or test-existence.

The 11 citation-class refusals (3now6p's second run included) fall into two groups.
- **Group 1, the spec did not state the behaviour at all:** `bd-ib-fd26sc`, `bd-ib-nsrgxl` and
  `bd-ib-7rnipp`.
  - The first two were resolved by writing the spec before the code merged (revise v152 /
    Scenario 189 and revise v154 / Scenarios 190–191).
  - `bd-ib-7rnipp` is still blocked, and no spec exists for it.
- **Group 2, the right clause existed and the filer cited a different one:** `bd-ib-vim5gc`,
  `bd-ib-yw7otf`, `bd-ib-ptnxyg`, `bd-ib-bmbmlt`, `bd-ib-xdmkhf` and `bd-ib-3now6p` (run 2).

The cause common to both groups: the filer types the `References:` line from memory, and the
filing check only verifies that the heading exists. Nothing at filing asks whether the spec
states the behaviour at all.

## 3. Why implementation can be filed ahead of the spec

There are two filing routes.
- The spec-first route, `detect-impl-gaps` then `capture-impl-gaps`, files work tied to a spec
  clause.
- The freeform route, `capture-work-item`, is ratified as "No gap detection runs; no
  closure-verification rules attach".

Of the 1,504 items ever filed in this tenant, 1,190 carry `origin:freeform` and 22 carry
`origin:gap-tied`.

`capture-spec-drift`, the operation that should catch implementation outrunning the spec, has never
completed a run here. All 18 records on the detection-coverage anchor `bd-ib-j5fzyo` are
`capture-impl-gaps`, and the last one covered v122 while the spec is at v165. The ledger-intent
scan, ratified in v026 at the maintainer's request, was never built.

## 4. The audit (2026-10-19 UTC)

Ten read-only reviewers shared one brief and one model. They asked of every item: "Is the behaviour
this work-item asks to build (or built) stated by a clause of the current ratified specification?"

**Open items (304 not closed):**

| Verdict | Items |
|---|---|
| UNGOVERNED | 88 |
| PARTIAL | 54 |
| GOVERNED | 79 |
| NOT_BEHAVIOUR | 81 |
| UNCLEAR | 2 |

- 29 of the UNGOVERNED items were in `ready`, `pending-approval`, `active` or `acceptance`.
- 57 of the open items cite a reference that does not govern them.

**Merged sample (60 chosen at random, seed 20261020, from the 210 completed since 2026-10-04):**

| Verdict | Items |
|---|---|
| GOVERNED | 38 |
| PARTIAL | 9 |
| UNGOVERNED | 4 |
| NOT_BEHAVIOUR | 9 |

16 of the 60 cite a reference that does not govern them.

**How far to trust these numbers:**
- All the verdicts come from one method on one model. By AGENTS.md verification Rule 4, that makes
  them one measurement, not ten.
- Four UNGOVERNED verdicts were spot-checked with independent searches, and all four held.
- One verdict is known to be wrong: `bd-ib-5vtqaq` is governed by v117 / Scenario 151. Treat the
  per-item verdicts as candidates, not findings.

## 5. Maintainer rulings in the originating session (2026-10-19 UTC), verbatim

> The goal of it is to ensure that what is being built is what actually should be built and that
> it actually works as intended and needed.

> The whole goal and vision of LiveSpec is that the implementation and the specification are kept
> in sync in a virtuous feedback loop. So, something pointing to a wrong citation is a wrong
> specification, or at best a mismatch between the implementation and the specification, and we
> absolutely do not want to just ignore it.

> " implementation work was filed ahead of the spec."  This is the absolutely most concerning and
> dangerous day. Why is this happening, and why is it even possible?

> we still want to keep everything as dry as possible around the drift concept. We shouldn't
> duplicate the prompts, rules, code, tooling, or skills. There should be a single implementation
> of it, just like the current skill is, and everything else should delegate to it or the
> underlying CLI as appropriate.

> The reason the drift lives on the orchestrator side is because that's the implementation side
> of things. There should be a hard boundary that implementation never leaks into livespec core.

> blocked for features that are expanding the spec. This should not apply to bugs . Chores and
> non-functional requirements are also have leeway, not every single thing must be or should be
> overspecified. Same with features too, actually, rejection should not turn into
> overspecification. That is counterproductive. The spec should be generalized to be correct
> rather than always expanded. But actual new behavior should get new spec.

> also what to do about the existing drift/gap noise and debt?

## 6. Direction, reconciled with the archaeology in note 002

1. **One judgement, defined once, on the implementation side.**
   - The judgement is: "is this behaviour stated by the ratified spec, and by which clause?"
   - Per the maintainer's 2026-08-25 rule, behaviour common to the orchestrators lives in
     `livespec-runtime`, because git-jsonl carries the same drift contract. It never lives in core.
   - `capture-spec-drift` remains the attended front-end, and every checkpoint delegates to the
     same judgement.
   - The existing no-prompt `orchestrator.py drift-capture` command is the routing half that
     already exists.
2. **No core contract change mandating checkpoints.** Core "defines NONE of their behavior" and
   never names the Dispatcher.
3. **Build what the maintainer already ruled:**
   - the ledger-intent scan (v026);
   - the per-merge drift binding (2026-08-25, threshold 1), as real runs scoped to the merged
     diff, not as a reminder flag.

   Detection and proposal filing may run unattended: core `spec.md:458` reads "Orchestrators MAY
   file drift (the machine path)". Acceptance stays at `revise`. The agent-written sentence in
   v078, "nothing in this section runs a detector headlessly", is corrected through
   `propose-change`.
4. **Make the Definition-of-Ready spec-change tier real at filing, in the maintainer's 2026-05
   two-deposit form.**
   - A feature that asks for behaviour no clause states must carry a linked `propose-change`, filed
     beside it.
   - Dispatch waits until that proposal is ratified. Waiting on ratification is a mechanical fact.
   - Bugs, chores and non-functional work are exempt.
   - Prefer generalizing an existing clause over adding one.
   - The tier's classifier was never ratified, and its code stand-in is inverted (`bd-ib-yykjko`).
5. **The `dod_gate` citation checks delegate to the shared judgement.** They keep their second
   duty: the referenced scenario still steers which steps the proof stage follows.
6. **Already covered, so not re-proposed:**
   - The repeat-failure breaker is ratified in v117 (Scenario 151, `bd-ib-s5idxj`, `bd-ib-5vtqaq`).
   - The host-side LLM pre-admission pattern exists in v132 and v141, and fails open.

## 7. Existing debt and noise

1. **Gap capture.** Today's detector lists every clause that has no work item (752–1,233
   candidates per run), which is noise. Replace that signal with the mechanical one that already
   exists: a heading with no exercising test in `tests/heading-coverage.json`.
2. **Open items.** Triage the audit's 88 UNGOVERNED and 54 PARTIAL items in batches by subsystem,
   under the maintainer's ruling:
   - bugs, chores and non-functional items are reclassified;
   - features generalize an existing clause, or get one new clause via a linked proposal;
   - obsolete items are closed.
3. **Merged drift.** Run one scoped drift pass by subsystem. Each finding ends one of three ways:
   - specified, preferring generalization;
   - removed, which is a conformance fix under `constraints.md:583`;
   - accepted as implementation detail.
4. **Baseline.** After reconciliation, record a completed drift coverage point, so that later runs
   see only new merges.
5. **Generalize while reconciling.** Measure the spec's net size per batch.

## 8. Relation to `definition-and-proof-of-done` (epic `bd-ib-7sjdzv`)

That plan keeps its own narrow Definition of Done and finishes its remaining children, proof and
archive. Before it hands off, it also owns the immediate factory-instability stopgaps the maintainer
asked for on 2026-10-19.

The work that consumes the shared judgement transfers to this plan:
- the citation-at-filing assistance;
- the spec-change gate;
- the `dod_gate` delegation.

`bd-ib-3now6p` stays held under the coordinator's R258(3) until this plan's gate ships or its
citation is corrected.
