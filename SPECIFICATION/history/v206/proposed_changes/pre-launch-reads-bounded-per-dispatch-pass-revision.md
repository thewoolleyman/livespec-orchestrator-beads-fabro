---
proposal: pre-launch-reads-bounded-per-dispatch-pass.md
decision: modify
revised_at: 2026-10-24T15:56:02Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted in substance. The proposal extends the bounded-read principle already ratified in the same subsection (Bounded Fabro event reads; the Dispatcher progress watchdog's rule that a poll's cost MUST NOT grow with run history) to the Dispatcher's pre-launch phase, and states it as call counts a unit test can assert. The mechanism it called suspected has since been confirmed: a live py-spy profile on 2026-10-24 (bd-ib-6bbcda, comment 02:25:45Z) put 98.0% of one pre-launch dispatcher's samples in read_model_fallback_warnings, which re-parsed the 307 MB dispatch journal once per run x warning x attempt from the selection replay. Revised on coordinator ruling (gitops-fleet-capacity-monitoring, 2026-10-24 ~03:45Z) as a single-proposal pass, because it governs the fleet's current throughput limit. Modified, not accepted verbatim, because the first independent ratification review found one blocker: the growth sentence bounded journal reads and fabro inspect calls together as non-growing with earlier runs, which contradicted the per-distinct-run inspect rule and the three-run scenario. Drift-origin floor: this proposal was filed from a capture-spec-drift ledger-intent finding, so drift_acceptance_mode (human) governs; the maintainer confirmed ratifying it as modified, in session 569d6a43, on 2026-10-24. Ratification review: gpt-6-astra in a separate read-only codex exec session (detached gate 20261024T155254Z-200442), NO BLOCKERS on the exact final bytes; two earlier takes (gates 20261024T034537Z-3628584: one blocker, fixed by the modifications; 20261024T034828Z-3699731: NO BLOCKERS before a resulting_files path-key correction re-bound the digest).

## Modifications

(a) The sentence bounding both read kinds together is split. Dispatch-journal reads in one pass MUST NOT grow with earlier runs, warnings, ACP candidates or attempts. fabro inspect calls in one pass MUST NOT exceed the number of distinct factory and run-id pairs the pass needs, and MUST NOT grow with warnings, ACP candidates or attempts evaluated for those runs. This resolves the reviewer's blocker and matches the scenario that expects one inspect per run for three runs. (b) The paragraph's last sentence now says each pass "makes its own first read of the journal and of each run it needs", instead of "observes the journal and the factory as they stand when it starts". The old wording implied a snapshot-time guarantee stronger than a first read establishes (the reviewer's advisory). The five scenarios are unchanged from the proposal.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-24T15:55:38Z
verdict: NO BLOCKERS
proposal_stem: pre-launch-reads-bounded-per-dispatch-pass
content_digest: 361e697ba17e4e06e2a9fcea52b91bd7fdc5a828fd82ce68885130f95ed7d525
