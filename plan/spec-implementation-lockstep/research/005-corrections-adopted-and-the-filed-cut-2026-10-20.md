# Corrections adopted from the independent review, and the cut as filed (2026-10-20 UTC)

Note 004 is the reviewer's verbatim output. This note records, per finding, what was verified
against source and what the plan now does differently, then the cut as it is filed on the ledger.
Where this note and note 003 differ, this note governs.

## 1. Verdict per finding

| # | Finding (short) | Verified against | Verdict and change |
|---|---|---|---|
| 1 | Archived proposal presence is not ratification | core `spec.md` revision-file format: `history/vNNN/proposed_changes/` holds accept, modify AND reject records | ADOPTED. The release condition for a spec-change-tier item is: the linked topic's revision record carries decision `accept` or `modify`, AND the spec-stated judgement re-run against the ratified spec returns `stated` for the item's asked-for behaviour. Both are mechanical reads plus the one shared judgement. Dependency and admission gates still apply after release. |
| 2 | Feature gate keyed on stored type admits unjudged work; fail-open contradicts assertion 1 | audit: 111 tasks, 22 of 29 actionable UNGOVERNED items typed `bug`; v132/v141 fail open | ADOPTED. Every implement-kind item is classified by the judgement at filing, at groom and again on each dispatch path (stored type is evidence, not the answer). The hold itself is MECHANICAL once an item is labelled spec-change tier: the ratification read needs no model, so it fails CLOSED. Only the classification of an unlabelled item fails open, and for that case the `dod_gate` node, which runs the same judgement in-run, refuses an unstated feature before implement. So assertion 1 holds as written. |
| 3 | A later successful pass can skip a failed merge | `_detection_coverage.completed_coverage_point` reads the newest completed record; contract forbids partial clearing | ADOPTED. The drift coverage point is a CONTIGUOUS processed-merge frontier. A failed or held merge stops the frontier; later successes do not advance past it; a completed record is written only after every finding of the merge is durably handed off (proposal filed) or held on the anchor; finding identities are stable so a retry files no duplicate. Backfill (R2) and the live loop (C4) share the one frontier. |
| 4 | The post-merge janitor is not an every-merge binding | hand merges, spec PRs and externally merged PRs never pass through a dispatch janitor; the root `reconcile-runs.timer` fires every ten minutes | ADOPTED. C4's enumerator is the reconcile pass: each `reconcile-runs` tick enumerates default-branch merges after the frontier and processes them; the post-merge janitor is one caller of the same primitive. |
| 5 | C3 narrows Scenario 38's ratified population | `contracts.md` §`capture-spec-drift`: every live item plus every item captured since the last version, all four intent fields, excluding only intent already stated | ADOPTED. C3 scans the ratified population and the four intent fields. Bug/chore/non-functional is a DISPATCH exemption (C2), never a detection exclusion. A successful full invocation writes a completed record. C3 depends on C1b (the vendored runtime bump), not on P2. |
| 6 | Counts cannot discharge the anti-bloat assertions; `partial` needs proposals too | the drafts recorded heading and clause counts only | ADOPTED. `partial` and `unstated` verdicts both require a proposal naming the generalization target. The size measure is reproducible: the count of BCP14 clauses and the word count of the live `SPECIFICATION/*.md` files, recorded per batch, with every net addition attributed to a finding; a batch that adds clauses it cannot attribute revises them before it completes. Assertion 3 is carried by C2, C4, R1 and R2. |
| 7 | P1 must not replace the full Definition-of-Done judgement | `contracts.md` "Judged before admission": the judgement grades effective criteria, referenced headings AND sandbox capabilities; Scenarios 131 and 174 | ADOPTED. The spec-stated judgement is a COMPONENT the Definition-of-Done judgement consults for the governing-heading verdict and the classification; coherence, proof-mode feasibility, riders and every existing remedy stay graded. P1's wording is corrected. |
| 8 | C6 couples a detector with a live migration | `detect_impl_gaps.py` derives ids from file, heading and rule text; 22 live clause-derived ids | ADOPTED. C6 is split: C6a (factory) is the detector and the filing change; C6b (host) migrates the 22 live ids many-to-one, preserves provenance in a comment per item, and verifies core's two doctor invariants on the live tenant. C6a is the smallest canary. |
| 9 | A coverage entry naming an existing test does not prove it exercises the heading | `tests/heading-coverage.json` carries `spec_root`, `spec_file`, `heading`, `test` | ADOPTED. C6a matches entries fully qualified, requires the named test to exist, and reports a dangling or malformed entry as an uncovered heading plus a surfaced finding, never as a clean absence. |
| 10 | C1 cannot prove consumers; the persisted tier shape must be shared | runtime `contracts.md` owns the shared WorkItem schema; the cross-repo subprocess funnel is `cross_repo`'s constraint, not the library's whole architecture | ADOPTED. C1 proves only its importable API. P4 also declares the persisted shape (`spec_change_tier`, `linked_proposal_topic`, verdict provenance) so both orchestrators store the same fields. A new child C1b bumps this repository's vendored runtime pin, and every consumer child blocks on it. Assertion 6 is carried by C1, C1b, C2, C3 and C7. C7 includes git-jsonl's impl-drift front-end. Note 003's reading of the subprocess constraint was over-broad; injection stays because it keeps the library model-agnostic, not because the constraint forbids a call. |
| 11 | Several bullets are not gradeable as routed | `plan.md` §"Routing a child's Definition of Done" | ADOPTED. C2's private-function bullet is restated as behaviour (a ratified follow-up carrying `spec_commitment_hint` is not held; an unratified feature is). C1's parser bullet is split. C7, R1, R2 and C6b carry a `### Host-captured` sub-heading with a `Reason:` line. |
| 12 | R1's dispositions differ from assertion 7 | assertion 7 text; the known false positive `bd-ib-5vtqaq` | ADOPTED through a scope correction decided by the coordinator for the maintainer under the 2026-10-18 ruling (an internal-consistency repair): assertion 7 now ends with "a recorded citation of the current ratified clause that governs it (spec version and heading), a ratified clause, a linked proposal, a recorded reclassification as a bug, a chore or a non-functional item, or a recorded closure as obsolete or duplicate (naming the item it duplicates)". R1 revalidates each audit verdict before disposing it. |
| 13 | `pending-approval` is not a hold | `.livespec.jsonc` sets `auto_approve_ready: true`; `drive impl:<id>` admits a pending item | ADOPTED. Every lockstep hold is a `blocks` edge: one tracker task per proposal (T1 to T4, host-routed, closed by the plan session when the revision lands) and the vendored-runtime bump C1b. A child blocked by an open tracker is invisible to `next` and to the drain. R1 starts now; P5 is drafted beside P1 to P4. |
| 14 | One proposal per finding is not a queue cap | note 002's volume tradeoff; human drift acceptance | ADOPTED. P2 adds `dispatcher.drift_proposal_queue_cap` (positive integer, default 5): findings beyond the open-proposal cap are HELD on the detection-coverage anchor as pending findings with stable identities, the frontier does not advance past a merge with held findings, and `needs-attention` lists held findings. Acceptance stays human at `revise`. |

## 2. The cut as filed

Fifteen children. Ids are recorded in the carrier-map scope event on the epic and in the first
handoff after filing. "Tracker" tasks are the ledger record of a spec-op; they are closed by this
session with the revision that ratified them, and nothing else closes them.

| Key | Title (short) | Tenant | Route | Blocks edges (depends on) |
|---|---|---|---|---|
| T1 | Tracker: proposal `spec-stated-judgement-and-spec-change-tier` ratified | this repo | host | none |
| T2 | Tracker: proposal `per-merge-drift-run-and-coverage-baseline` ratified | this repo | host | none |
| T3 | Tracker: proposal `gap-signal-from-heading-coverage` ratified | this repo | host | none |
| T4 | Tracker: livespec-runtime proposal `spec-stated-judgement` ratified | this repo | host | none |
| C1 | The spec-stated judgement module | livespec-runtime | factory | T4 (sibling) |
| C1b | Bump the vendored livespec-runtime to the release carrying `spec_stated` | this repo | factory | T4, C1 (sibling) |
| C2 | Spec-change tier decided by the judgement; a feature waits for ratification before dispatch | this repo | factory | T1, C1b, bd-ib-7f66ar |
| C3 | The ledger-intent scan (Scenario 38) over the judgement | this repo | factory | C1b |
| C4 | The per-merge drift run with a contiguous coverage frontier | this repo | factory | T2, C1b |
| C5 | Citation checks consult the judgement at every call site | this repo | factory | T1, C1b, bd-ib-7f66ar |
| C6a | `detect-impl-gaps` reports headings without an exercising test | this repo | factory | T3 |
| C6b | Migrate the 22 live clause-derived gap ids and verify core's invariants | this repo | host | C6a |
| C7 | git-jsonl runs the same judgement | git-jsonl (filed here) | host | C1b |
| R1 | Reconcile the audit's open UNGOVERNED and PARTIAL items in subsystem batches | this repo | host | none (C1b improves it; the audit data suffices to begin) |
| R2 | Reconcile merged unspecified behaviour and record the baseline frontier | this repo | host | C4 |

## 3. The carrier map as recorded

| Ordinal | Carriers |
|---|---|
| 1 | C2 |
| 2 | C2 |
| 3 | C2, C4, R1, R2 |
| 4 | C4 |
| 5 | C3 |
| 6 | C1, C1b, C2, C3, C7 |
| 7 | R1 |
| 8 | R2 |
| 9 | R2, C4 |
| 10 | C6a, C6b |
| 11 | R1, R2, plan-level proof |

## 4. Sequencing after filing

Now, in parallel: P3 (the typed next action), P1, P2, P4 and the P5 draft; R1's first batch by
hand. P3 ratifies: close T3, dispatch C6a as the canary. P4 ratifies: close T4, dispatch C1 in
the runtime tenant, then C1b. P1 ratifies: close T1; C2 and C5 wait on `bd-ib-7f66ar` as well.
P2 ratifies: close T2; C4 after C1b. Then C3, C6b, C7, R2, the plan proof, the independent
completeness review and the archive.
