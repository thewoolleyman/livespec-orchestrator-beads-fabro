---
proposal: relay-delivery-and-progress-deadline.md
decision: modify
revised_at: 2026-10-08T09:27:54Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: codex
---

## Decision and Rationale

Accept the approved result/deadline/relay amendment with precise shared-consumer and real Codex-in-Herdr scenarios. Original deadlines and sender obligations remain authoritative across activity, and causal recovery never equates execution with fulfillment. D6 keeps epic metadata as the resume authority and explicitly leaves the exact next_action schema open in its section 8; the two bounded fields preserve that authority rather than contradict it. This decision selects only the relay proposal and leaves other pending proposals untouched. It preserves the chain-recovery candidate at bfab811744dda4bd5c18164cec9956e8b28e7acc; application requires its actual merged bytes to match this reviewed base. Independent read-only Sonnet session cebf646e-c33b-4b50-8bf5-8b50b35e3e88 completed the full research context review at 2026-10-08T06:39:18Z and returned NO BLOCKERS for the exact digest. The same session independently recomputed that digest in its preceding follow-up. Author verified merged PR2665 base 9662c138 matches the reviewed chain candidate in all five resulting-file base blobs. Implementation, released admission tooling, normal gates and runtime proof remain pending. Review refresh at 2026-10-08T08:48:51Z by the same independent read-only Sonnet session supersedes the earlier digest for current bytes: NO BLOCKERS for 70d7bb3ffc0d96ae47c56fae928e7949a3868845fe5c4c58670bc7a1b3ba16dc. Exactly four inherited Scenario142–145 first_seen dates change from October8 to October7 to match commit9662c138 recorded committer calendar date, as independently confirmed against narrow correction4ac7d72e. No relay normative or acceptance content changes. Application requires this exact correction and released tooling1.93.0 pin landed; all original implementation and released-host proof obligations remain outstanding.

## Modifications

Materialize the approved clauses as Planning Lane and Dispatcher subsections; co-edit Scenario111 and add Scenarios146–152 with owned heading coverage. Make quantitative settings dispatcher-scoped and reuse the existing attention envelope. Include the maintainer-required real Codex/Herdr incident and explicit unsupported verdict. Retain all admission and safety guards. Mechanically generate debt entries for the seven genuinely new scenario headings; preserve the existing Scenario111 routing-test binding, while new tracking behavior is separately governed by Scenarios147 and148.

## Resulting Changes

- contracts.md
- spec.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-08T08:48:51Z
verdict: NO BLOCKERS
proposal_stem: relay-delivery-and-progress-deadline
content_digest: 70d7bb3ffc0d96ae47c56fae928e7949a3868845fe5c4c58670bc7a1b3ba16dc
