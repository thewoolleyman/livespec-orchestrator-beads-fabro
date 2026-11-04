# Archaeology: drift, freeform filing, and the core/orchestrator split (2026-10-19 UTC)

The maintainer asked for "archaeology" to establish whether the proposals in note 001 conform to the
original livespec decisions on drift and the core/orchestrator split. Two independent read-only
investigators covered the evidence:
- livespec core at `/data/projects/livespec`, commit `e59bb8ab`;
- this orchestrator at `a61fa69c` (spec v165), plus `livespec-orchestrator-git-jsonl` at `de29110`.

Labels used below:
- **MAINTAINER**: the maintainer's own words or decision, read from a primary record.
- **RATIFIED**: accepted spec text, usually drafted by an agent.
- **AGENT**: a session's proposal or inference.

## Q1. Where drift lives, and the boundary

**MAINTAINER, 2026-05 brainstorm** (core
`archive/research/workflow-processes/conversation-transcript.html:1036,1167`). The maintainer
named the hole: "now that we have a hard wall between spec and implementation, that can no longer
be Critique's job. So we have a hole." The answer:
> Keeping this concept on the implementation side makes sense. And it can always be part of the
> exposed API of the implementation side if we want doctor to be able to call it.

**MAINTAINER, transcript `:1398`.** The spec reader is an implementation-side,
implementation-dependent API:
> The only interface that the spec side is exposing is the canonical locations of the
> specifications and the spec history files.

**MAINTAINER, 2026-06-09** (core v103 decision 7, "decided by the user"):
> The interactive gap/drift dialogue is **orchestrator-owned** … The Driver ↔ orchestrator
> zero-dependency invariant is preserved

**RATIFIED, core `contracts.md:52,58`.**
- LiveSpec "defines NONE of their behavior, only that they are named in `.livespec.jsonc` and
  callable".
- "LiveSpec MUST NOT read the orchestrator's work-item store, prompts, or internal state."

**RATIFIED, core `spec.md:460`.** Core "never names Ledger/Loop/Dispatcher".

**AGENT, beside the maintainer's 2026-08-25 ruling** (homelab
`plan/steady-state-loop-hardening/research/002-problem-and-fix-matrix.md:297-299` @ 1126d5d).
Enforcement was kept in the orchestrator "so livespec core's `revise` stays unaware of any
orchestrator concern."

**MAINTAINER, 2026-08-25** (homelab `research/008-core-review-triage-and-shared-runtime-rule.md:25-37`
@ e68b19f):
> `livespec-runtime` is a shared library. Any plan work that touches behavior COMMON to core /
> orchestrator(s) ... routes its shared piece to ... livespec-runtime ... A plugin-local
> implementation of a shared shape forks the schema; a core-side definition reverses the
> established source-of-truth direction. Both are refusals.

git-jsonl carries the same `capture-spec-drift` contract and ledger-intent scan (git-jsonl
`contracts.md:56-83`, v016).

## Q2. Consent, attended dialogues, and "headless"

**The sentence "nothing in this section runs a detector headlessly, and no policy setting MAY do
so" (this repo's `contracts.md:182-185`) is AGENT text.**
- It was written on 2026-08-25 by `claude-fable-5` in v078
  (`history/v078/proposed_changes/detector-coverage-records.md:53`).
- It was ratified under delegated revise authority on epic `bd-ib-ujihbw`.

**What the maintainer actually ruled that day** (homelab matrix `:291-294`, in bold): "gap capture
is bound to EVERY revise. Drift capture is bound to a merge count ... default 1." The next
sentence, "Both skills are consent-gated attended dialogues; the mechanical fix is therefore a
surfaced, owned TRIGGER, never a headless run", is the agent's inference. No separate maintainer
ruling against headless detection was found in the ledger or in any file.

**Unattended filing is already permitted:**
- Core `spec.md:458` reads "Orchestrators MAY file drift (the machine path); an orchestrator
  executor MUST NOT accept it". This is the maintainer's design record of 2026-08-03.
- This repo's `spec.md:150`: "the Dispatcher MAY file impl→spec drift (the machine path)".
- `_orchestrator_drift_capture.py:1-7`: "Filing is a machine path; acceptance stays human".

**Consent origins (core):**
- Per-gap consent exists so detection never "silently file[s] 12 new issues from a spec edit".
- The store-write consent rule comes from `livespec-1f5` (bd auto-commit on master).
- Detection quality concern: "impl → spec is heuristic and fuzzy (every line of impl is 'doing
  something'; signal-to-noise is brutal)" (`tool-agnostic-workflow.md:617-620`).

**Rejected alternatives:**
- **An LLM consenting on the human's behalf.**
  - git-jsonl ratified `--autonomous` drift auto-consent in v015 and retired it in v018 as "the
    riskiest" part.
  - This repo retired the consent waiver in v034; that retirement was "ACCEPTED by the maintainer
    (2026-07-14)".
- **Bulk consent.** Rejected in homelab `003-reasoning-and-rejected-alternatives.md` §2.4.
- **A drift survey on the closure path.** Rejected and replaced by the mechanical targeted
  `--for-work-item` trigger (`contracts.md:120-133`).

**Supporting the opposite direction:**
- MAINTAINER `livespec-zodb` (2026-06-26): "the doctor is a GATE. If capturing the out-of-band
  drift … were opt-in, it would never happen — defeating the gate."
- MAINTAINER transcript `:857`: "we are not going to rely on the user to manually do anything."

## Q3. Freeform filing and spec-first

**MAINTAINER, transcript `:1215`.** Freeform filing exists for "(1) a well-formed implementation
bug ... (2) a feature that spans spec + non-spec impl directives — forcing this through Capture Spec
Drift is awkward and over-process-heavy."

The agent's reply was adopted: routing proactive features through drift is "a category error". A
feature is filed as **two parallel deposits**: a `propose-change` for the spec part and a
`capture-work-item` for the implementation part.

**No rule in core or here requires implementation work to trace to a spec clause.**
- Spec-first has been applied item by item, without a global rule. Examples:
  - `bd-ib-w3nwz5`: "Maintainer approved the spec-first cut".
  - `bd-ib-opbzv3`: "no ratified clause states the behaviour, so a propose-change ... must land
    first".
- The Definition-of-Ready already routes a spec-change slice to `propose-change`
  (`contracts.md:1405-1408`; groom's `is_spec_change`).
- That tier has no ratified classifier, and its code stand-in `spec_commitment_hint` is "its
  near-opposite" (`bd-ib-yykjko`).

**MAINTAINER, 2026-08-23** (homelab 003 §2.3) on the opposite failure: "isn't the real problem that
you prematurely wrote the entire specification rather than implementing it as you went?" The answer
was "Substantially right": v004 alone added 30 clauses, a 77% jump.

**RATIFIED, `constraints.md:583`.** Removing implementation behaviour that no ratified clause
requires is a conformance fix.

## Q4. Triggers surfaced, not run

- **Core v082 revise Step 13.** Gap capture runs after every revise, opt-out, scoped to the new
  version so users would not "train themselves to dismiss it". Filing behind it stays consent-gated.
- **This repo's v078.** Detection-coverage records, all-or-nothing completed coverage, and
  staleness facts that are "a surfaced, owned TRIGGER".
- **Measured here:**
  - zero `capture-spec-drift` records;
  - the ledger-intent scan (v026) never built, with Scenario 38 still `TODO` (owner `bd-ib-heat`);
  - gap capture last recorded at v122;
  - unattended sessions skipped the gap dialogue because there was "nobody present to consent".

## Q5. Model judgement in gating paths

**Against gating on a model's judgement:**
- Core `spec.md:269`: "Python MUST NOT invoke the LLM" (core's own scripts).
- Core v083: matching by free text is "LLM-judgment-grade and unsafe to gate on".
- Core NFR `:170` (2026-06-19): uncertain, data-derived gates are ADVISORY. The open question,
  whether intake should hard-refuse or warn with an override, was recorded and never answered.

**Precedent for gating:**
- This repo's v132 (2026-10-13) runs the `dod_gate` judgement on the host before an item is routed
  to `ready`.
- v141 (2026-10-15) refuses before claim, reusing the verdict while the inputs are byte-unchanged.
- Both fail open when the model cannot run.

**Still in force:** v115, "Filing stays consent-gated and a front-end MUST NOT refuse on a finding"
(`contracts.md:5841`).

## Q6. The Definition-of-Done split

- **MAINTAINER, 2026-09-30** (research 001 of `definition-and-proof-of-done`): the Definition of
  Done must be the required first heading and must reference an existing spec heading, and there
  must be an entry gate.
- **AGENT design, ratified v114/v115:** the mechanical half runs on the host, the semantic half in
  the node, and scenario-reference findings are advisory.
- The gate's citation judgement also steers the proof stage to the referenced scenario's steps
  (v115, Scenario 141).

## Q7. The feedback loop

- Core `spec.md:169`: the process "is a **revision loop**, not a one-way waterfall".
- `tool-agnostic-workflow.md:602`: "without explicit detection of this direction of drift, the spec
  slowly atrophies as ground truth shifts beneath it and no skill is responsible for catching the
  divergence."
- The maintainer's 2026-08-25 merge-count binding was the mechanism meant to keep the loop turning.
  It was implemented as a reminder flag, and no drift pass has ever completed here.

## Verdicts on the session's proposals

| Proposal | Verdict |
|---|---|
| One drift implementation, every checkpoint delegating to it | ALIGNED with orchestrator ownership. Its shared part belongs in `livespec-runtime` under the 2026-08-25 rule, not plugin-local. |
| Checking an item's intent at filing, framed as drift | Redefines drift. Frame it as the Definition-of-Ready spec-change tier, which shares the judgement. |
| Item cannot be FILED until the spec is ratified | CONFLICTS with the maintainer's 2026-05 two-parallel-deposits design and with v115's "MUST NOT refuse on a finding". Revised: filing stays parallel; DISPATCH waits for ratification of the linked proposal. |
| Unattended detection, decision kept at `revise` | Permitted by core and by this repo's `spec.md`. It conflicts only with the agent-written v078 sentence and with v026's per-finding consent wording in `constraints.md:688-691`. |
| Core mandates the checkpoints | CONFLICTS (core defines none of the orchestrator's behaviour). Withdrawn. |
| A judgement CLI in core | CONFLICTS. Withdrawn. |
| Repeat-failure breaker | Already ratified in v117 (Scenario 151). Not re-proposed. |

## Tradeoffs the direction must carry

1. **Volume and noise.** Past runs surfaced 752–1,233 candidates, and drift is noisier still. Every
   proposal costs a mandatory independent review at `revise`. Detection must be scoped to the diff,
   and the proposal queue needs a cap.
2. **Rubber-stamping.** Moving consent pressure to `revise` invites bulk approval.
3. **Spec bloat.** Writing spec far ahead of implementation caused the 2026-08 clause pile-up.
   Generalize; do not expand.
4. **Fail open or fail closed.** v132 and v141 fail open on purpose. This plan's spec-change gate
   waits on a mechanical fact (ratification), so only the classification is a model judgement.
5. **"A factory run never awaits a human" (v093).** Detection inside a run cannot hold a dialogue.
6. **The `freeform` label over-counts unspecified work.** Spec-tied children were sometimes filed
   as freeform to avoid enormous consent dialogues, so audits must read each item.
