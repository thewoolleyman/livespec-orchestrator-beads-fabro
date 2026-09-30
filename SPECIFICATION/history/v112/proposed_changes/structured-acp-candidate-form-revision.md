---
proposal: structured-acp-candidate-form.md
decision: modify
revised_at: 2026-09-30T02:50:59Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude (factory-configurable-model-fallback-priority)
---

## Decision and Rationale

Accept with one modification. All four proposals are realized: the structured candidate form (agent, model, effort) with the manual form kept as the escape hatch and identity derived from (agent, model); the committed agent and model catalogs seeded from the ACP registry snapshot and upstream Fabro's model catalog; in-protocol model and effort selection through ACP session/set_config_option with a typed pre-turn refusal for an unadvertised value and the additive capability acp.candidate_config_options.v1; and the retirement of dispatcher.codex_models and the class-shaped Codex pins into per-node structured entries, with Scenarios 64, 86, 90, 91, 117 and 127 re-expressed and Scenario 129 added. Design-record departure, acknowledged deliberately: v107 ratified dispatcher.codex_models as the per-class Codex shorthand and the fleet defaults as class tiers, and v109 kept that shorthand valid beside acp_nodes. This revision retires both on the maintainer's 2026-09-30 ruling that the two keys are the same functionality spelled twice and that the plan owns that functionality; measured at ratification no fleet repository set codex_models. The surviving Codex rules (every Codex candidate pinned, the baked path, the CODEX_CONFIG shape, the un-pinned base string) are restated against the codex-acp catalog entry rather than dropped.

## Modifications

Two small departures from the proposal text. (1) The proposal implied the built-in Claude defaults would immediately move to in-protocol selection; the ratified text keeps the claude-acp catalog entry on the environment mapping at this ratification so the v107 bytes stay byte-identical, and makes switching it to the protocol mechanism a committed catalog change that triggers the verification-run rule. (2) The un-pinned Codex opt-out is expressed only in the manual form (baked path with no model key in CODEX_CONFIG) and has no structured spelling, so disabling a pin is visible in the escape-hatch form; Scenario 91 was re-expressed accordingly, and Scenario 117's variant scenario now names an acp_nodes structured entry. The heading-coverage entries for the new section and scenario carry integration-tier reasons owned by plan epic bd-ib-jxvgq5, and the retitled section keeps its existing unit-tier binding.

## Resulting Changes

- contracts.md
- scenarios.md
- constraints.md
- ../tests/heading-coverage.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-09-30T02:50:23Z
verdict: NO BLOCKERS
proposal_stem: structured-acp-candidate-form
content_digest: e4966eab044c0f45914bcd98f64722d971bb41129c706748c7776254b408d4ae
