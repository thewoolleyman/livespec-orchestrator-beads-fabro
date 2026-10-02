I'll review the change on this branch. Let me start by examining the diff.This is a large diff. Let me read the key files. First the goal-relevant new modules.I'm already in the sandbox. Let me work from the current directory.Let me read the new modules and key changed files.This is a large, well-documented change. Let me verify a few integration points and check for issues.Let me verify whether zero-token spans can reach the observation path (relevant to a model_resolved edge case), and check the calibration caller impact.I've completed a thorough review of the diff. Let me summarize my assessment.

## Review

I read every new module (`_acp_model_identity`, `_acp_model_prices`, `_acp_model_catalog`, `_acp_attempt_windows`, `_acp_attempt_price`, `_dispatcher_cost_attempts`, `_dispatcher_cost_chain`) and all modified modules (`_dispatcher_cost_pricing`, `_dispatcher_cost_report`, `_dispatcher_cost_gate`, `_dispatcher_cost_sink`, `_dispatcher_cost_sink_span`, `_acp_fallback_events`, `_acp_fallback_event_types`), and traced the integration against each acceptance criterion.

**Verification against the acceptance criteria:**
1. ✅ Per-attempt attribution by window from `candidate_index` (started) + `attempted_durations_ms` (failover) — `_acp_attempt_windows`, with the measured-vs-derived elapsed distinction and the successful-attempt-unbounded decision handled deliberately.
2. ✅ Sum every attempt incl. failed ones (`chain_cost`); single-candidate priced as before via the preserved legacy sink path (no `agent.acp.started` → `run_chain_cost` returns `None` → sink aggregate decides).
3. ✅ Catalog-first then candidate table; manual-form no-match → table only (`attempt_price`), with the ratified-text tension documented and localized to one function.
4. ✅ Exact identity: one `-\d{8}` strip, no prefix match; the old longest-prefix bug in `normalize_model_id` is removed, both tables share one normalizer.
5. ✅ Unpriceable nonzero component poisons the whole total (`_spent_tokens` + `unpriced_usage` → `usd_micros=None`), never a partial/default/zero; gate reads it as absent.
6. ✅ `claude-opus-5` added with its four prices (base 5.00/25.00 → cache rates derived) to both the price table and catalog.
7. ✅ Reuses the existing `--item`-keyed fail-closed gate (no second policy); terminally-unsuccessful runs are never read (`outcome.status != "green"` short-circuits).
8. ✅ `model_basis` names every priced identity comma-separated; `model_resolved` False when any attempt unpriceable.

**Quality:** The decomposition is cohesion-driven (pure arithmetic / pure windows / pure pricing / one impure composition seam), fail-soft is consistent with the existing post-verdict cost posture, `chains` is resolved once and shared between gate and report (avoiding the two-reads-disagree trap), and the sink's `-1` sentinel vs. absent-key handling is correct. No workflow files touched. No detector evasion — no `dev-tooling/checks/**` edits, no banned-call rewrites, no suppression comments; the shared base-rate table de-duplicates the two pricing paths rather than forking them.

**No blocking findings.**

[ADVISORY] `_dispatcher_cost_attempts.py:147` — a zero-usage observation carrying an unpriceable/blank model flips `model_resolved` to False while the run total stays observable, so the report appends "(an attempt was unpriceable)" even when every real-cost attempt priced cleanly. This matches the criterion literally and is the honest/conservative direction, so it's fine — noting only because the darkened flag could read as alarming for a fully-priced run.

[ADVISORY] `_dispatcher_calibration_emit.py:180` — the second `derived_costs` caller doesn't pass `chains`, so the calibration path keeps sink-aggregate pricing rather than per-attempt pricing. Backward-compatible and likely intentional (out of this item's scope), but worth confirming the calibration emitter is meant to stay on the legacy aggregate.

{"preferred_next_label": "approve"}