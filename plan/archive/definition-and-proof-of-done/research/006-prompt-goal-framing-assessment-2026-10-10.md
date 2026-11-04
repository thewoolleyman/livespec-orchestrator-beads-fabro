# Goal-framing assessment of the orchestrator plugin's prompts (2026-10-10)

Status of this note: research note 006 of plan `definition-and-proof-of-done`. It records
the maintainer's direction of 2026-10-10, the measurements behind it, the proposed edits,
and which findings of the independent Codex critique (note 007, verbatim) were adopted. The
carrier is work item `bd-ib-5eibzp`; where this note and that item's Definition of Done
differ, the item governs.

## The maintainer's direction (verbatim, 2026-10-10)

"I want the prompts baked into the plan skill (and any other relevant skills) to explicitly
frame the definition of done and proof of done as the goals. The intent is to minimize the
tendency of models to stall and stop working before the plan is fully complete. The
overriding goal should be to complete the plan and see the final proof of done successfully
passing with the plan ready to archive. [...] rewrite all the skills so that the summary and
intent are clearly stated in first 100 lines, and delete any unnecessary cruft [...] without
blowing up context or compromising/weakening existing important prompt contents."

## Scope

This repository's operation prose (`.claude-plugin/prose/*.md`, seven files, 182 to 610
lines), the fourteen skill bindings per runtime (`.claude-plugin/skills/*/SKILL.md`, the
Codex mirrors under `.claude-plugin/.codex-plugin/skills/`, the pi mirrors under
`.claude-plugin/.pi-plugin/skills/`), and the nine factory stage prompts under
`.claude-plugin/.fabro/workflows/implement-work-item/prompts/`. Livespec CORE's spec-side
prose lives in the `livespec` repository and is out of scope; the same treatment belongs
there and is noted at the end.

## The problem in one sentence

The prompts describe the MACHINERY of each operation (stores, package calls, gates,
refusals) accurately and at length, but almost none states, where a model reads first, what
the operation is FOR and what finishing looks like; a model that loses the thread falls back
to "do one step and report", which is the stall shape measured on this plan three times
(waits of one and three hours with nobody consuming the result, and a next action pointing
at a completed step).

## Measurements (master `dfd9855c`)

| file | lines | first goal sentence | Definition of Done / Proof of Done / archive mentions |
|---|---|---|---|
| prose/plan.md | 610 | line 298 ("A plan is done when the outcome ... was OBSERVED") | 14 / 5 / 36 |
| prose/implement.md | 274 | none | 0 / 0 / 0 |
| prose/groom.md | 291 | none (implicit) | 6 / 1 / 0 |
| prose/capture-work-item.md | 335 | none | 5 / 2 / 2 |
| prose/capture-impl-gaps.md | 372 | none | 5 / 1 / 0 |
| prose/capture-spec-drift.md | 221 | none | 0 / 0 / 0 |
| prose/discuss-work-item.md | 182 | line 12 ("STANDS BY by default") — correct for that operation | 0 / 0 / 2 |
| Claude bindings skills/*/SKILL.md | 25 to 76 | frontmatter description | plan's omits the proof leg |
| Codex binding .codex-plugin/skills/plan/SKILL.md | 153 | frontmatter description | reads the 610-line prose with one `cat` |
| stage prompts | 86 to 551 | lines 1 to 8 (goal-first already) | not applicable |

Structural findings:

1. Every prose file opens with the same thirteen-line architecture paragraph ("Harness-neutral
   driving prose ... each per-runtime SKILL.md is a THIN binding ..."). It is true and
   constraint-mandated, and it is the first thing a model reads seven times over. One line
   naming the constraint carries the rule.
2. plan.md puts reference material before purpose: pre-requisites, the two stores and
   twelve package signatures occupy lines 17 to 113; the Flow starts at 114; the Definition
   of Done at 296; the archive gates — the finish — at 432.
3. No prose names the stall as a failure, and two sentences invite it: Step 3's "perform one
   action at a time" and the attended-resume rule "Present the picker and wait" (lines 164
   to 167 and 391 to 400). AGENTS.md carries the maintainer-declared counter-rules ("a
   recorded next action is an instruction, not a menu"; "an operator-flow step that says
   present options and let the user select is satisfied by a standing directive — do not
   re-prompt"), but a session driving the plan from the skill never reads them.

## What the Codex critique (note 007) changed in this assessment

Adopted:

- **The attended picker is the strongest stall cause, not the absence of goal language**
  (critique A1). The prose commands it, and `resume_directive` returns `ask=True` for every
  attended resume. The contract ratifies the picker ("An attended resume MUST present
  `next_action` as the default choice of its picker") and fixes `kind` to `impl`, `spec-op`,
  `human`, `none`. So the item reconciles the PROSE with AGENTS.md's standing-directive rule
  — present the default; a standing maintainer directive to continue satisfies the picker,
  so take the default without re-prompting — and the code change (no picker under a
  recorded authorization) plus new typed kinds for host proof, independent replay,
  completeness review, archive and a live dispatch are a PROPOSED CHANGE to the plan clause,
  filed separately (follow-up 1 below).
- **Handoff is not progress** (A2): the rewrite makes a handoff accompany a state change and
  adds the exit audit (critique F3): before ending, report the archive, the specific
  unresolved input or refusal, or the run and the verified mechanism supervising remaining
  work; if continuation cannot be armed, report the work as incomplete.
- **The stop taxonomy is three CATEGORIES, not three reasons** (B row 2): successful
  completion; authorized suspension (a recorded human gate, or a bounded wait on something
  already launched with its deadline and supervising mechanism named); an explicit
  incomplete-or-failure report. Never force a failure into a fictitious human decision.
- **implement.md's "dispatch and stop"** (A3, F4) is rewritten to route through `drive` and
  retain supervision; and its obsolete substrate instructions (a JSONL store, a hardcoded
  `work-items.jsonl`, refusing every status but `open`; A4) are corrected to the beads store
  and the lifecycle statuses in the same item, because a rewrite that leaves a manufactured
  refusal in the runnable path has not removed the stall.
- **Do not re-ask supplied inputs** (A5, F5): capture and plan consume the invocation's
  values and ask only for what is missing, then obtain the write consent the contract
  requires; consent and input collection are separated, never merged.
- **The Codex read can truncate** (A6, F8): the Codex binding instructs bounded-range reads
  and treats a truncation notice as an incomplete read.
- **Outcome lines corrected** (B rows): implement — closed with its Definition of Done
  proved, OR an administrative resolution, OR resting in acceptance on a pending host leg,
  each reported as what it is; groom — approved slices filed and their ACTUAL routed states
  reported (pending-approval is legitimate), the original disposed, an all-spec cut refused
  as today; capture — the consented item filed with every finding displayed (a finding may
  remain; filing is not admission); drift — the coverage attempt and any withheld reason
  reported, including zero findings. "Ready to archive" becomes "archived, or the named
  reason it is not"; "midpoint" becomes "child closure alone never proves plan completion";
  "where a release applies" is kept on the released-build requirement.
- **drive** (B row): a valve action is complete when it returns; an `impl:` dispatch spans
  run → merge → janitor → acceptance and is complete when the gate reports, with the item
  then closed, resting in acceptance on a pending leg, or blocked needs-human — reported as
  observed. No closure loop is taught to the bindings; outcome decisions stay in the wrapper.
- **Do-not-cut list** (D) and **cruft list** (E) are adopted verbatim as constraints of the
  item; the acceptance bar replaces the keyword extractor with a reviewer-produced inventory
  of normative sentences listed in the pull request (reworded ones beside their replacement)
  and keeps the structural parity checks.

Not adopted, with reasons:

- Model behaviour probes as the acceptance bar (critique C, last bullet): they are the right
  instrument but not a factory-provable assertion of this item; they belong to the
  agent-session-stall-prevention plan (`bd-ib-jnpvh4`), which owns stall measurement.
- Dropping the line ceiling: the maintainer's direction includes "without blowing up
  context", so plan.md keeps a ceiling (450 lines, from 610); the risk the critique names
  (reflow to fit) is countered by the normative-sentence inventory.

## The edits (what bd-ib-5eibzp will do)

### plan.md (610 → at most 450 lines)

1. A first section immediately under `# plan`, about thirty lines: **Goal / Continue /
   Suspend / Fail.** Goal: carry the plan from the maintainer's statement of done through
   child disposition, current independent completeness-review evidence and a `verified` plan
   Proof of Done record (taken against the released, normally installed artifact where a
   release applies, with required human attestations) to a successful archive; the plan's
   Definition of Done is the goal statement; child closure or a verified record alone is not
   the finish. Continue: after each action, re-read current state; when the maintainer has
   authorized continuation and one current eligible next action is recorded, take it without
   reopening the selection question (AGENTS.md decision authority); ask only when selection
   is unresolved or authorization is missing; store-write consent stays governed by the
   consent contract. Suspend: a recorded human gate, or a bounded wait with run id, observed
   state, deadline and the mechanism that resumes supervision named. Fail: report the
   specific unresolved input, refusal or outage as incomplete work — never as a fictitious
   human decision. The three archive legs are listed as the evidence the session is working
   toward, with every Step 5 gate (including the path-reference sweep) still binding.
2. Flow (Steps 1 to 5) follows immediately. Step 3's opener and the attended-resume
   paragraph are reworded per the reconciliation above; the contract's "present
   `next_action` as the default" is preserved verbatim. Step 4 gains the exit audit.
3. Pre-requisites, The Plan Store and Package Commands move to a `## Reference` section at
   the end, with a one-line prerequisite check kept before the first mutation and the
   reviewer-own-session requirement kept beside the review action.
4. Important Properties and What This Operation Does Not Do merge into one exit-audit list;
   the non-transferability rule (today's lines 597 to 599) is kept; the stale "one research
   note plus one epic anchor and nothing else" is corrected (creation also writes the anchor
   file).
5. The four anecdotes (record rate, truncated prose line, stale l3nptz evidence, the
   beads-v1-1-2 archive breakage) become one sentence each keeping the discriminator and the
   remedy; the ledger ids or AGENTS.md sections that hold the detail are named.

### implement.md, groom.md, capture-work-item.md, capture-impl-gaps.md, capture-spec-drift.md, discuss-work-item.md

- The thirteen-line architecture paragraph becomes one sentence naming
  `SPECIFICATION/constraints.md` "Skill orchestration constraints" and the harness-neutral
  tool-mapping rule.
- A short "What done looks like" block before Pre-requisites, with the corrected outcome
  lines above; discuss-work-item keeps its stand-by framing and its explicit-instruction gate.
- implement.md: the "dispatch and stop" paragraph and the obsolete JSONL / `open`-status
  instructions are corrected; everything else in the six bodies is untouched except the cruft
  spans the critique lists (E), each removed only where the rule it duplicates remains.

### Bindings (Claude, Codex, pi — in parity)

- `plan` description names the outcome: child disposition, independent completeness review,
  verified plan Proof of Done with required attestations, archive; released-build proof where
  applicable.
- `drive` gains the two outcome lines above (valve returns; `impl:` spans to acceptance and
  is reported as observed; bounded gate wait).
- The Codex `plan` binding reads the prose in bounded ranges and treats a truncation notice
  as an incomplete read.

### Stage prompts

No reframing. implement.md's "The Definition of Done is the brief" sentence, with its
dispatch-snapshot sentence, moves up into "Where you are"; the amendment and refusal rules
stay where they are.

## Follow-ups to file (not part of bd-ib-5eibzp)

1. **Proposed change to the plan clause** (spec-change tier): an attended resume with a
   recorded standing authorization takes the typed next action without a picker; typed
   `kind` values for host proof, independent replay, completeness review, archive and a live
   dispatch; and resume reconciles the pointer with ledger and run state (advance a pointer
   naming a closed item, reattach to a live run). Today's contract fixes the four kinds and
   mandates the picker, so this is `propose-change` work, then code in `resume_directive`.
2. **Wake-up mechanism**: a recorded deadline does not schedule another turn; that is the
   agent-session-stall-prevention plan's subject and is referenced, not solved, here.
3. **Livespec CORE**: the spec-side prose (`revise`, `propose-change`, ...) has the same
   shape; file the same treatment in the `livespec` repository.
