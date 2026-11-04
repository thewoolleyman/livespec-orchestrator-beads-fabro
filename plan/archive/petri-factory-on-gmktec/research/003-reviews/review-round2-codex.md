VERDICT: BLOCKERS

Paths below are relative to `/home/ubuntu/.worktrees/livespec-orchestrator-beads-fabro/spec-factory-registry-amend`. **P** denotes `SPECIFICATION/proposed_changes/factory-addresses-from-a-gitops-registry.md`; **C** denotes `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/`.

Round-1 findings:

1. **BLOCKER — RESOLVED: recorded-pin fallback precedence.** P:81–90 limits fallback to absent explicit selection; P:128 unsets the environment override and P:195 excludes the flag. This agrees with `SPECIFICATION/contracts.md:4280` and C`_dispatcher_factory_ledger.py:132`.

2. **BLOCKER — RESOLVED, with explicitly weaker fleet scope.** P:41–44 now requires this repository’s committed entries to be registry-backed and recommends that form for fleet members. P:37–39 preserves external-adopter compatibility. This addresses the requested scoped requirement; it does **not** mandate fleet-wide migration.

3. **SHOULD-FIX — RESOLVED: telemetry classification.** P:62–68 explicitly includes remote classification and run-turn telemetry, covering the literal-server read in C`_dispatcher_run_turn_telemetry_export.py:190`.

4. **SHOULD-FIX — RESOLVED: additional readers and failure semantics.** P:68–76 names the additional consumers, preserves their failure behavior, and isolates reconcile failures per factory. The enrichment exception matches `SPECIFICATION/contracts.md:6775–6777`. Implementation must still handle resolution failures at sites such as C`_plan_run_liveness.py:110`; this is implementation work required by the proposal, not a contradiction in it.

5. **SHOULD-FIX — RESOLVED: validation scope.** P:46–56 specifies JSON parsing, object root, selected-entry validation, whitespace-only rejection, and independence from unrelated invalid entries.

6. **SHOULD-FIX — NOT RESOLVED fully: scenario coverage.** P:136–189 adds substantial coverage, but still omits default-path selection with an unset/empty override, an existing unreadable file, invalid selected-entry types, journal/watchdog liveness, availability reads, and enrichment failure. Only P:152 checks unchanged status, metadata, and comments; the other refusal cases do not establish the same guarantee. P:156 combines alternatives in one `Given`, rather than requiring each through an outline/examples table. Expand these cases and reuse the no-write assertions.

7. **SHOULD-FIX — RESOLVED: token variable.** `plan/petri-factory-on-gmktec/research/003-hostname-free-factory-registry-2026-10-15.md:29–32` now identifies `FABRO_DEV_TOKEN__<name>` and corrects the earlier observation. P:78–79 preserves per-name settings.

8. **NIT — RESOLVED: scenario placement.** P:115 correctly inserts 182 before 183; `SPECIFICATION/scenarios.md:6445` and `:6462` contain 181 and 183 respectively.

New findings:

9. **BLOCKER — The final scenario promises successful dispatch without establishing resolvable `petri`.** P:126–128 declares `petri` but does not give it a registry mapping. P:199 supplies a mapping only for `next`, while P:202 requires the pinned item to dispatch to `petri`. With no `petri` mapping, P:52–60 requires refusal. Earlier scenarios do not supply fixtures to later scenarios.

   Add a valid registry mapping for **both** factories and explicitly dispatch both items without `--factory`. The precedence expectation itself is correct: a recorded pin to still-declared `petri` beats `default_factory`; it does not bypass registry validation.

10. **SHOULD-FIX — The conflicting-entry scenario contradicts its Background fixture.** P:127 establishes `petri` “with … no server”; P:172 establishes the same entry with a server. Make the latter an explicit replacement of the Background entry so the fixture is unambiguous.

11. **SHOULD-FIX — Reconcile success needs an observable second factory.** P:178 declares `legacy` with a server value, but P:183 assumes its runs can be read. Declare that server reachable with a known run inventory. A configured address alone does not establish observability.

The remaining Scenario 182 steps are consistent with the clause, subject to the coverage gaps above. I found no new contradiction with the reconcile rules, needs-human enrichment, or watchdog treatment of failed reads: P:70–76 preserves unobservability rather than interpreting it as absence, consistent with `SPECIFICATION/contracts.md:1521–1532`, `:6704–6708`, and `:6775–6777`.

REVIEW-COMPLETE
