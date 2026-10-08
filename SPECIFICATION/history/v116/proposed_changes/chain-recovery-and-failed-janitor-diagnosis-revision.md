---
proposal: chain-recovery-and-failed-janitor-diagnosis.md
decision: modify
revised_at: 2026-10-08T06:09:30Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-fable-5-1
---

## Decision and Rationale

Accept all three proposals together (the resume is defined against the reclaim, so they ratify as one), modified by an independent adversarial critique (23 findings: 11 blocking, 12 advisory), every finding accepted. Ratifies: a Dispatcher resume surface that finishes a run which published a pull request and then terminated, entering the earlier run's recorded workflow at the node it was executing when it died, on the published branch at the head the proof record names, with the earlier run's records attributed through the journal's resume record and no implement stage; its refusals (not ready, moved head, changed Definition of Done, live run, live lock, closed or merged pull request, nothing to resume from, third resume, unobservable forge or factory); the pre-dispatch stale publish-branch reclaim bd-ib-yebrb7 shipped, with its preservation ref, its per-factory liveness question and its hold-when-unmeasurable arms; and retention of a failed post-merge janitor's complete output and exit code as a private artifact the journal names. Scenarios 142-145 added; tests/heading-coverage.json and tests/heading-coverage-debt.json co-edited with four owned TODO rows naming epic bd-ib-7sjdzv. Motivation: bd-ib-fngpwg was refused at the Definition-of-Done gate (run 01M4CZ739SCMPN5CXRCJCP8EWD) because no heading governed three of its four assertions, and bd-ib-nezrrh would be refused on the same ground.

## Modifications

Relative to the filed proposal: (1) the resumed-at stage is the node the earlier run was executing when it terminated, or the target of the edge its last succeeded node's outcome selected, and the factory-less fallback keys on the VERDICT of the latest record carrying the earlier run's id (verified: pr; captured: review; not_captured or not_reproduced: fix; none: proof_capture); an authoritative not-found answer from the factory is an observation, not an outage; (2) the resume-kind registered variant is dropped: the resumed run runs the workflow the earlier run's dispatch record names, never writes or clears dispatch_workflow, and any derived graph is not a registered variant; (3) a resume is a hand-picked dispatch subject to every dispatch-eligibility rule, runs the host-side mechanical wall, resolves its factory as dispatch --item does, and refuses an item that is not ready, a live ownership lock, a Definition of Done that differs from the earlier run's snapshot, and a third resume from the same pull request; the live-run check runs after the preamble's orphan reconciliation; (4) the record, the proof evidence leg and the pointer are amended in place so a linked identifier attributes transitively and the pointer list names the resumed run; the record-head duty is scoped to factory records; (5) the reclaim asks every factory the journal names for the item, defines an earlier dispatch as a journaled run or dispatch id in this checkout's journal, names the preservation ref form refs/livespec/preserved-publish/<item>/<head>, and states that deleting the branch closes its draft pull request with the records still readable; (6) janitor retention names the covered commands (venue provisioning, janitor-bootstrap, janitor-core-provisioning, janitor-check-suite), the JSON artifact shape and 0600 mode, signal and timeout as non-zero, the reconcile-merged invocation identifier as the path key, the bounded excerpt the row already carries, and the artifact's lifetime; (7) scenario steps rewritten to observables (item status in every Given, exit code 3 on every refusal, the held record excluded on a resume, the review step phrased as the absence of a preceding proof_capture visit).

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-08T06:06:46Z
verdict: NO BLOCKERS
proposal_stem: chain-recovery-and-failed-janitor-diagnosis
content_digest: 5300bd26aaa97c065a27b6ca06b40ce918750fd39835de3f1ef3ccc26257500f
