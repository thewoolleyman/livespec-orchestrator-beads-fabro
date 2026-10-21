---
proposal: committed-admission-setting-wins-over-item-label.md
decision: modify
revised_at: 2026-10-21T18:38:11Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:spec-implementation-lockstep
---

## Decision and Rationale

Modified under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session spec-implementation-lockstep (plan bd-ib-ax3rds, R1 batch 10), adopting the proposal for work-item bd-ib-pz7x with the repairs an earlier independent review required. A committed dispatcher.auto_approve_ready now decides every item's effective admission_policy over any stored per-item admission label; where the key is not committed the stored label governs and an unlabelled item inherits the shipped default; a deliberate per-item hold is status blocked with its reason recorded, never an admission label; and the spec-change-tier floor is unchanged. DESIGN-RECORD DEPARTURE, deliberate and confirmed: this narrows the design record cited by contracts.md "## Dispatcher policy settings", repo thewoolleyman/livespec, plan/archive/autonomous-mode/handoff.md, its "CORRECTION / ADDENDUM" section, which records that every setting is per-item overridable EXCEPT wip_cap. Admission is now a second exception while the setting is committed, because the maintainer's later ruling of 2026-08-21 ("the config file setting should always be respected") makes the committed configuration authoritative over a stale admission:manual label. The decision is fleet coordinator ruling R448 (livespec-dev-tooling-dfixhe, 2026-10-21T11:19:30Z): the committed setting wins over every per-item admission label, and deliberate holds move to blocked with a recorded reason, migrated BEFORE the implementing change ships. The maintainer confirmed it, as recorded verbatim in coordinator record R487 (2026-10-21T15:09:06Z): "(7) R448 stands; the maintainer says such decisions are the coordinator's and are escalated only if important." Coordinator record R499 (2026-10-21T17:12:52Z) answered this proposal's confirmation picker "1. Yes, confirm" on that authority and directed landing. The configured ratification reviewer, gpt-6-astra, in a separate read-only session, returned NO BLOCKERS on the exact resulting bytes (digest 0e5279016109a9d99bb1b212b5dcf51e33b9d9d3752b2c96d61f1a419b753e29) on master d4a6733cb (spec v192).

## Modifications

contracts.md "## Dispatcher policy settings": the per-item-over-global intro states the admission exception, and the rationale paragraph names the departure from the CORRECTION / ADDENDUM design record and the 2026-08-21 ruling. "### The five policy settings": the lead limits the auto_approve_ready label override to an uncommitted setting; the auto_approve_ready bullet replaces the two Per-item override sentences with the precedence rule and the blocked-hold rule, keeping the spec-change-tier floor sentence verbatim. "### Admission valve": the Permission bullet resolves through the precedence rule and names effective manual. "`drive`": the policy-edit paragraph reconciles the former "fires only once, at capture/groom time" with the Dispatcher-pass approval the admission valve already states, and adds the set-admission committed-setting result statement. spec.md "## Dispatcher policy settings": the admission exception. scenarios.md: Scenario 33 renamed to "auto_approve_ready governs admission, and a committed setting wins over a per-item label" with seven cases each carrying its own premise (no shared Background), keeping the spec-change-tier case; Scenario 31's flip case gains the uncommitted-setting premise and states that the valve does not move the item by itself while a later Dispatcher pass or an explicit approve can.

## Resulting Changes

- contracts.md
- scenarios.md
- spec.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-21T18:36:47Z
verdict: NO BLOCKERS
proposal_stem: committed-admission-setting-wins-over-item-label
content_digest: 0e5279016109a9d99bb1b212b5dcf51e33b9d9d3752b2c96d61f1a419b753e29
