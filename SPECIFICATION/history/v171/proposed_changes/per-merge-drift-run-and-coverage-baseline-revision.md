---
proposal: per-merge-drift-run-and-coverage-baseline.md
decision: modify
revised_at: 2026-10-20T13:33:24Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-fable-5-1:spec-implementation-lockstep
---

## Decision and Rationale

Accepted with modifications under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by session spec-implementation-lockstep for plan epic bd-ib-ax3rds (Definition of Done assertions 4 and 9). The drift run files unattended, which livespec core's spec.md permits ('Orchestrators MAY file drift (the machine path)'), and it never accepts: acceptance stays at revise's human gate or the opt-in consensus tier. The judgement it consults is livespec_runtime.spec_stated (livespec-runtime v027), and the spec-change tier that consumes the same judgement is ratified in v170. The configured ratification reviewer, gpt-6-astra, in a separate read-only session, returned NO BLOCKERS on the exact resulting bytes.

## Modifications

Four repairs to text the proposal left untouched. M1, the Records bullet names the drift run of a reconcile pass or a post-merge janitor as a recorded invocation, and its completed-record disposal admits a finding filed through the propose-change handoff or held on the anchor alongside the consent-flow outcomes; M2, the self-bookkeeping exception admits the drift run's held-finding records as anchor writes; M3, dispatcher.drift_proposal_queue_cap is placed after the threshold it is declared like, and carries the full API-configurable completeness sentence its sibling carries; M4, Scenario 82's heading-coverage entry keeps its bound test, which still exercises the unchanged gap-capture case, and its reason names bd-ib-yvjxo4 as owing the re-bind to a test of the amended drift case, because that test cannot exist before the drift run is implemented. Three repairs from three ratification-review rounds: M5, a held finding is not a disposal and blocks the frontier, and the drift run is all-or-nothing over its declared scope (the merges after the previous frontier), writing a completed record only when every one is processed with every finding filed, so Scenario 81 and the Records rule hold unchanged for it, and the frontier is defined by durable disposal, so an attended capture-spec-drift survey that explicitly declines a finding advances it exactly as Scenario 81 requires, while the machine run, which cannot decline, advances it only by filing; M6, the run never accepts a proposal while the ratified unanimous cross-vendor consensus tier under spec_governance.drift_acceptance_mode keeps its acceptance exception, and Scenario 207 says the pass takes no decision; M7, every exclusive statement of a write boundary admits detection-coverage self-bookkeeping: the Dispatcher machine-path exemption (opening and closing sentences) admits the drift run's anchor records and says its proposals are spec-side; the constraints.md SOLE-exemptions sentence names the anchor records of capture-impl-gaps, capture-spec-drift and the drift run; and the Out-of-scope surfaces sentence that capture-spec-drift writes nothing to the store excepts its anchor records. Scenario 207 gains a TODO coverage entry and a debt row owned by bd-ib-yvjxo4.

## Resulting Changes

- constraints.md
- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: gpt-6-astra
reviewer_identity: gpt-6-astra
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-20T13:32:50Z
verdict: NO BLOCKERS
proposal_stem: per-merge-drift-run-and-coverage-baseline
content_digest: 49157a0cdcca59d9dcc1490e4b2059d1d1be061ce4acd7464ff85577ef1e3552
