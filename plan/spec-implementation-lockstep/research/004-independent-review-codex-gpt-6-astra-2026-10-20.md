# Independent review of note 003 by a read-only Codex reviewer (gpt-6-astra, 2026-10-20 UTC)

Verbatim output of the reviewer launched from this session as a split pane with a read-only brief
(the brief asked for omissions, holes, conflicts, sequencing, the shared-judgement shape, the carrier
map and the big picture). Each finding was verified against source before adoption; the verdicts and the
corrected cut are in note 005. This file is the record, not the decision.

# Ranked critique of lockstep scoping note 003

References to **003** mean `plan/spec-implementation-lockstep/research/003-scoping-child-cut-and-proposal-outlines-2026-10-20.md`; **001/002** mean its two preceding research notes. Review is read-only except for this file.

## 1. Blocking: archived proposal presence is not ratification

**Claim.** C2 can authorize implementation of a rejected proposal, failing plan assertion 1.

**Evidence.** 003:122–123: “Once the linked topic is present under a ratified version, the next intake or drain pass routes the item to `ready` without a human valve.” Core `/data/projects/livespec/SPECIFICATION/spec.md`, revision-file format, explicitly archives both proposal and revision record under `history/vNNN/proposed_changes/`; the revision decision can be `accept | modify | reject`. A modified acceptance can also omit the particular behaviour the item asks for. A topic name alone proves neither acceptance nor coverage.

**Change.** Resolve the exact proposal/revision pair in the correct spec tree, require an accepted/modified decision and verify the current item is covered by the resulting ratified clauses. Rejected, unrelated, narrowed and missing proposals must not release the hold. Preserve ordinary dependency and manual-admission gates after releasing this particular hold.

## 2. Blocking: the feature gate misses the existing population and admits unjudged work

**Claim.** C2 does not discharge assertion 1; its most likely failure is that unspecified behaviour continues through items labelled `task` or `bug`.

**Evidence.** 003:120 only judges an item “typed `feature`”; :121 exempts typed bugs/chores, although C1 introduces a semantic classifier. The audit at :19 contains 111 tasks and 22 of the 29 immediately actionable UNGOVERNED items are typed bug. The plan supplies no classification path for tasks, legacy ready items, or changed intent after filing. :125 explicitly routes as today when judgement cannot run. Assertion 1 in 001 is unconditional. The v132/v141 fail-open precedent (`contracts.md:5861–5918`) retains an in-run DoD backstop; neither C2 nor C5 requires that backstop to verify feature ratification.

**Change.** Classify effective requested behaviour, treating stored type as evidence, and validate classification freshness on every dispatch path, including legacy ready and edited items. Preserve actual bug/chore/non-functional exemptions. Explicitly reconcile fail-open with assertion 1: either retain a mandatory pre-implementation ratification backstop, or obtain a change to the assertion rather than claiming the unconditional guarantee.

## 3. Blocking: C4 can erase an unprocessed merge from coverage

**Claim.** A successful later pass can manufacture a false all-clear, breaking assertions 4 and 9.

**Evidence.** 003:141 scopes each pass to one merge; :143 retains no completion for failure; :144 promises “After a successful pass the drift-staleness fact reports zero merges since the recorded point.” If merge A fails and B succeeds, B's point skips A. `_detection_coverage.py::completed_coverage_point` selects the latest completed comment; its completion guard checks the supplied scope, not gaps between merge SHAs. `contracts.md:145–158` forbids partial coverage from clearing staleness. C4 explicitly requires completion only for the no-finding case (:142), omitting successful proposal-filing completion. R2 backfill can interleave with ongoing C4 completions.

**Change.** Track a contiguous processed merge frontier, durable retries and idempotent finding/proposal identities. Require completion after every candidate is durably handed off, while a failed earlier merge prevents advancing past it. Define how backfill and live runs share the frontier. Prove failed A/successful B/retry A, duplicate invocation and out-of-order completion cases.

## 4. High: a post-merge janitor is not an every-default-branch-merge binding

**Claim.** C4's chosen trigger does not establish assertion 4 for merges outside a Dispatcher-owned run.

**Evidence.** P2 promises “after each default-branch merge” (003:58–59), but C4 assigns the act to “the post-merge janitor” (:141). No child requires discovery/recovery of human, spec-operation or externally merged PRs, or a restart after a missed callback. The old failure in 001 §3 was zero completed drift runs despite an existing trigger fact.

**Change.** Give C4 a durable default-branch merge enumerator/reconciliation trigger, with the janitor as one caller. Require an externally merged PR and a missed-callback restart to be detected and processed without an attended session. Without this, shipping the detector can reproduce the original dormant-tooling outcome.

## 5. High: C3 narrows a ratified scan while claiming no proposal is needed

**Claim.** C3 contradicts Scenario 38's governing contract and weakens assertion 5.

**Evidence.** 003:131 lists live items only; :132 excludes bugs, chores and non-functional items. `contracts.md:101–118` requires intent from title, description, acceptance criteria and closure reason; the default population includes every live item **plus every item captured since the latest version**, including recently closed ones. It excludes already-stated intent, not item types. Exemption from a new-clause dispatch gate does not imply that observable drift in a bug is invisible. 003:23 calls C3 already ratified, yet :89 gives it only C1 as a dependency while P2 changes its judgement binding.

**Change.** Preserve the ratified population, all four intent fields and semantic finding rule. Distinguish dispatch exemptions from detection exclusions. If exclusions are intentional, propose and ratify that change before dispatch; update the dependency table. Require completed bookkeeping for successful full capture invocations as well as attempt records, per the existing coverage contract.

## 6. High: recording counts cannot discharge the anti-bloat requirement

**Claim.** Assertions 3 and 11 have incomplete carriers.

**Evidence.** C2 records a verdict/topic; it never requires production of an amendment. C1 merely names a generalization target. R1 and R2 require before/after H2 and MUST/SHOULD counts (003:184,195), not a size bound or a response to unjustified growth. Those counts can remain constant while paragraphs grow arbitrarily. The carrier map assigns assertion 3 to C2/R1 and assertion 11 to R1/R2/“plan-level proof” (:207,215); proof cannot repair missing delivery requirements. P1/C4 also omit a proposal requirement for `partial` verdicts even though partial means some behaviour remains unstated.

**Change.** Assign proposal authoring/generalization to a concrete shared handoff consumer and cover partial as well as unstated findings. Require each reconciliation batch to attribute net spec growth to genuinely new behaviour and revise redundant expansions before the batch completes. Define a reproducible size measure, not just heading/keyword counts, and include the amendment-producing child in assertion 3's map.

## 7. High: P1 risks replacing the full DoD gate with a narrower judgement

**Claim.** The shared spec-stated judgement cannot replace the existing admission judgement wholesale.

**Evidence.** P1 says “the one judgement the Dispatcher runs is the spec-stated judgement” (003:45–56). C1's verdict reports coverage and classification; it cannot express incoherence, unsupported proof mode or malformed DoD. `contracts.md:5861–5918` requires the same complete `dod_gate` judgement against effective criteria, referenced headings **and sandbox capabilities**. Scenarios 131/174 retain these duties. C5 covers only governing headings. The deferral at :222–224 says rider coherence remains elsewhere, which does not resolve the proposed replacement wording.

**Change.** Make the runtime judgement a shared component of the full DoD evaluation. State explicitly that coherence, proof feasibility, effective riders and all existing refusal remedies remain graded. Keep the existing runner dependency but avoid redefining its entire output as C1's verdict.

## 8. High: C6 couples a new detector, a many-to-one identity migration and live acceptance

**Claim.** C6 is not a safe smallest factory canary and its migration promise is underspecified.

**Evidence.** 003:163: “The 22 live gap-tied items carry heading-derived gap ids after the migration the change ships, and livespec core's `gap-tracking-one-to-one` and `no-stale-gap-tied` invariants pass on this repository.” A factory implementation can ship a migration, but cannot establish a completed live-tenant migration merely by doing so. Existing `detect_impl_gaps.py` derives IDs from file, heading and **rule text**, with parity against the shared clause extractor; replacing this with one ID per H2 is not stable across the transition (P3:69). Multiple clauses/items can collapse to one heading; covered headings disappear from the new gap set altogether. Renaming all 22 IDs cannot by itself prove either invariant.

**Change.** Separate the detector's public behavior from a host migration/verification child. Define many-to-one consolidation, already-covered items, provenance preservation, closure checks and rollback before migrating. Exercise the actual doctor consumer contract with fixtures. Use the smaller C1 after P4 as a candidate canary, or a detector-only slice after P3, rather than the combined live migration.

## 9. High: the coverage proxy can claim an unexercised heading is covered

**Claim.** C6 does not yet establish assertion 10's “exercising test” condition.

**Evidence.** 003:160 treats absent/TODO entries as gaps; :161 says “A heading whose coverage entry names an existing test produces no gap.” Existing file/test existence does not establish that it exercises the heading; a non-TODO entry naming a deleted test is also unspecified. `tests/heading-coverage.json` includes `spec_root`, `spec_file` and `heading`, so matching by heading text alone would collide across roots/files.

**Change.** Specify the canonical coverage check that validates fully qualified entries and exercising-test bindings, including dangling and malformed references. Declare invalid/unverifiable coverage as a surfaced failure or uncovered heading, never a clean absence. These detector assertions concern its output and are legitimate; they are not forbidden test-existence DoD bullets merely because the detector reads tests.

## 10. High: C1's ownership is right, but its acceptance and shared stored schema are incomplete

**Claim.** Injection is compatible with the shared-runtime rule; the current cut still permits divergent persisted tier/proposal shapes and assigns cross-repo proof to the wrong child.

**Evidence.** C1:114 says “The prompt text and the verdict schema are importable constants that both orchestrators read from this one module.” C1 cannot make two downstream repositories consume its release. C2/C7 introduce stored tiers and proposal topics (:120,124,173), but P4 declares only judgement APIs. Runtime `contracts.md:197–266` owns the shared WorkItem schema. Its constraints require minor-version bumps for API additions, frozen/slotted/kw-only public dataclasses, keyword-only functions and direct-Exception public error types. No inherent violation follows from a synchronous injected runner; the cross-repo resolver's threading/process restrictions should not be misquoted as the entire library's sole subprocess architecture. Core's “Python MUST NOT invoke the LLM” governs core scripts, not an orchestrator calling this library.

**Change.** Keep the judgement in runtime, with explicit runner/result/error types and the required release/vendor-pin uptake. Specify shared persisted tier/proposal provenance there if both consumers use it; let adapters map it to storage. Limit C1 proof to its callable/importable API and assign actual consumer use to C2–C5/C7. Assertion 6's map must include a beads consumer, not only C1/C7. Add git-jsonl's impl-drift frontend to C7 if the promised single drift judgement includes that frontend, as P5 says it does.

## 11. Medium: several DoD bullets cannot be graded as currently routed

**Claim.** The drafts do not yet satisfy the four authoring rules they cite.

**Evidence.** Besides C1:114 and C6:163 above:

- C2:124: “`_is_spec_change_tier` and `_refuse_spec_change_tier` read the recorded tier and no longer read `spec_commitment_hint`.” This specifies private implementation rather than a delivered behavioral outcome.
- C1:113: “`parse_verdict` round-trips the verdict JSON a model returns, and a malformed response yields a typed failure naming the field.” This combines success/error assertions and gives no serialization surface or treatment of errors with no field (invalid JSON).
- C7/R1/R2 use plain “Host-captured. Reason:” paragraphs (003:169,179,190); the parser requires a `### Host-captured` subsection with a `Reason:` line before the affected bullets (`.claude-plugin/prose/plan.md:112–116`).
- C6:163 combines a live mutation outcome and passing checks; that check-passing claim does not describe the migration outcome and cannot substitute for it.

**Change.** Rewrite C2 around a ratified-follow-up hint no longer causing a false hold and an actual unratified feature remaining held. Separate parser cases and specify their API outcomes. Render proper proof-mode headings. Move live migration proof to its host child. I found no explicit plan-carrier bullet inside these child sections; do not invent that finding.

## 12. Medium: R1's permitted dispositions differ from assertion 7

**Claim.** R1 can pass while its parent assertion fails, and can demand new proposals for already-governed items.

**Evidence.** Assertion 7 in 001 permits a ratified clause, linked proposal or recorded bug/chore/non-functional reclassification. R1:182 instead permits obsolete closure and omits the ratified-clause outcome. 001 §4 explicitly records a known false-positive audit verdict (`bd-ib-5vtqaq`). R1:183 asks features to amend where possible, but the initial audit verdict is not itself a validated finding.

**Change.** Revalidate the audit candidates and explicitly allow a governing current clause with evidence. Reconcile obsolete closure with the parent assertion through an authorized scope correction, rather than treating the current carrier map as proof that different disposition sets are equivalent.

## 13. Medium: pending-approval is not an enforceable pre-C2 proposal hold

**Claim.** The plan's own lockstep protection is not implemented by its proposed temporary state.

**Evidence.** 003:81–83 says proposal holds are prose “enforced today by the `pending-approval` rest.” Scenario 8 and `contracts.md:1387–1393` explicitly auto-approve pending items under effective auto policy. `.ai/plan-session-lessons.md` also records that `drive --action impl:<id>` admits and dispatches a pending item in one step. P5 is delayed until C7 even though its spec preparation can run beside P1–P4. R1 can begin immediately but is scheduled as Wave 4.

**Change.** Before C2 exists, use an actual enforced dependency/manual hold with a recorded release condition; do not rely on prose or pending state. Start independent R1 triage and P5 preparation now. Keep C3 behind whichever ratification changes its actual contract. No numeric ceiling was found in this checkout's `.livespec.jsonc` or runtime's; do not infer the adopted value from Scenario 153's example of six. C2 has six top-level bullets, but calibration/coherence still require evaluating its multiple surfaces; a low bullet count does not make C6's combined migration a small slice.

## 14. Medium: one proposal per finding is not a queue cap

**Claim.** C4 defers a known volume constraint without supplying the promised bound.

**Evidence.** 003:230–231 calls “one proposal per unstated behaviour, scoped to the merge diff” a proposal-queue cap. A diff can contain arbitrarily many findings, retries can duplicate them, and R2 deliberately processes roughly 210 merges. 002's tradeoffs require a cap because every proposal costs an independent review. Core `spec.md:458` leaves drift acceptance human by default; filing more proposals does not dispose that queue.

**Change.** Specify a bounded pending queue or bounded batch with duplicate suppression, durable backlog and visible deferred findings. Deferral must retain incomplete coverage rather than report completion. Preserve human drift acceptance; neither injected judgement nor plan-origin relabelling may approve detected drift. R2 already requires terminal dispositions for historical findings; give the ongoing loop an explicit owner/handoff for pending findings so it does not stop at proposal production.

REVIEW-COMPLETE
