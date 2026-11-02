VERDICT: BLOCKERS

I could not write `tmp/registry-review/review.md`: this session permits filesystem reads only. The review follows. No files, hosts, or ledger records were changed.

Paths below are repository-relative. `P` means `SPECIFICATION/proposed_changes/factory-addresses-from-a-gitops-registry.md`; `C` means `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/`.

1. **BLOCKER — Recorded-pin fallback contradicts explicit selection precedence.**

   P:57–61 says an undeclared recorded name “is ignored and the dispatch falls back to `dispatcher.default_factory`” and that renaming reroutes “every item.”

   Ratified `SPECIFICATION/contracts.md:4280` instead specifies “`--factory`, then the item's recorded factory, then `dispatcher.default_factory`.” Code agrees: `C/_dispatcher_factory_ledger.py:132` uses `explicit or _usable_recorded_factory(...)`; its `_explicit_factory` also honors `LIVESPEC_FABRO_FACTORY`.

   Qualify the fallback with **absence of an explicit flag or environment selection**. Scenario 182’s final case must also unset the environment override; “without an explicit factory” currently leaves that ambiguous.

2. **BLOCKER — The normative change enables the governing goal but does not require it.**

   P:28 says entries “MAY declare `"registry": true`”; P:36 says an entry carrying `server` “keeps its existing meaning unchanged.” Consequently, every fleet repository could retain its committed machine URL while satisfying the proposed contract.

   The research explicitly limits literal-server compatibility to “repositories outside the fleet” (`plan/petri-factory-on-gmktec/research/003-hostname-free-factory-registry-2026-10-15.md:66–67`). That scope distinction is absent from the normative proposal.

   Add a scoped fleet requirement—or identify a separately governing fleet contract—requiring hostname-free committed entries and inventory-owned machine bindings. Preserve literal-server support for other adopters explicitly.

3. **SHOULD-FIX — Address-dependent telemetry bypasses the shared resolver.**

   P:47 requires every surface that “turns a declared factory into an address” to share resolution. This misses a consumer that classifies the target without resolving it.

   `C/_dispatcher_run_turn_telemetry_export.py:190` reads:

   > `server = _factory_entry(block=block, factory=factory).get(_SERVER_KEY)`

   At lines 151–154, an absent export declaration returns observable unless that literal field names a server. Registry-backed remote entries omit the field and therefore acquire local observability semantics.

   Extend the requirement to address-dependent classification and telemetry observability. Updating `_config.resolve_fabro_factory` alone cannot fix this path.

4. **SHOULD-FIX — Explicitly cover non-Dispatcher readers and their failure behavior.**

   P:47–52 names Dispatcher surfaces and requires unresolved reads to report the factory as unobservable. Additional consumers already use the resolver but need deliberate error handling:

   - `C/_plan_run_liveness.py:110`: resolves a ledger-stamped factory for plan liveness.
   - `C/_needs_attention_needs_human_question.py:156`: resolves the factory for valve enrichment.
   - `C/_drive_merge_hold_arm_guard.py:278`: resolves the factory for merge-hold liveness.
   - `C/_acp_projection_run.py:148`: resolves the factory for run-event projection.

   For example, `_plan_run_liveness.py:110` directly calls `resolve_fabro_factory`; introducing a resolution exception does not automatically produce its existing `unobservable` result.

   Preserve the ratified enrichment rule in `SPECIFICATION/contracts.md:6774`: “an unreadable config or an unreachable factory costs the ENRICHMENT and never the valve.” State that all factory consumers share resolution while retaining their established failure semantics.

5. **SHOULD-FIX — Registry validation has an unresolved whole-file versus selected-entry distinction.**

   P:33 requires an object mapping names to objects, “each carrying a non-empty `server` string.” P:40–41 prescribes refusal when the selected entry is missing or invalid.

   For `{"petri":{"server":"https://example"},"legacy":null}`, must dispatch to `petri` fail because the registry violates the whole-file requirement, or succeed because its selected entry is valid? Both readings are plausible.

   Specify validation scope, malformed-JSON handling, and whether whitespace-only strings count as non-empty. These are readily testable once defined.

6. **SHOULD-FIX — Scenario 182 does not exercise every new MUST.**

   P:97–129 covers successful dispatch, missing entry, absent file, one reconcile failure, and recorded-pin fallback. It omits:

   - Registry-path override and default selection.
   - Malformed JSON, non-object roots, invalid entry values, and conflicting `registry`/`server`.
   - Resume, journal liveness, and availability-evidence reads.
   - No ledger mutation: “status is unchanged” at P:109 does not exclude metadata or comment writes.
   - Default switching without renaming.

   These behaviors are testable; none inherently requires human attestation. Actual provisioning and fleet-convergence proof may require host capture.

   This matters to `dod_gate`: `SPECIFICATION/contracts.md:3405` rejects a Definition of Done that cannot be recognized as satisfied from its referenced scenario. References must name existing **H2** headings (`contracts.md:5738–5749`); the proposed registry subsection is H3. Ratify Scenario 182 before dispatching children that reference it, and expand its behavior coverage.

7. **SHOULD-FIX — Research names the wrong dev-token variable.**

   Research:29 says:

   > `LIVESPEC_FABRO_DEV_TOKEN_<name>`

   Actual code uses `FABRO_DEV_TOKEN__`: `C/_config.py:124`, consumed with the factory name at line 490. `C/_fabro_port_auth.py:64–68` then falls back to URL-keyed login credentials.

   The research’s “none is set” observation does not establish absence of the variable actually consumed. Correct this before the rename/sweep children are authored. Also preserve per-name secret-channel declarations: `C/_dispatcher_secret_channel.py:472` traverses `("factories", factory)`.

8. **NIT — Scenario insertion instructions are stale.**

   P:86 says 180 is pending and 181 is in use. Master contains Scenario 180 at `SPECIFICATION/scenarios.md:6406` and runs through Scenario 199 at line 7144.

   **182 remains unused in current scenarios; no competing current proposal reserves it.** Keep 182, but correct the insertion instructions.

The shared resolver covers dispatch/pinning, resume, reconcile targets, targeted reconciliation, preflight, telemetry wiring, and the additional readers listed above. The reconciler’s tuple construction (`C/_dispatcher_reconcile_runs_factories.py:62`) also needs per-factory failure handling so one unresolved entry produces a named observation.

For an actually selected, declared registry-backed entry, P:38–45 clearly forbids fallback. Existing undeclared-name behavior remains a separate escape: `_config.py:478` returns `"default"` for an undeclared configured default, and `_factory_entry` returns `{}` for an undeclared name. Clarify that these cases remain outside the registry guarantee; do not describe the proposal as eliminating all ambient-local routing.

The registry is a reasonable mechanism under the research’s stated TLS and provisioning constraints. An inventory-rendered environment mapping would relocate the same indirection rather than materially simplify it. The main work is making ownership, validation, and consumer behavior precise.

REVIEW-COMPLETE
