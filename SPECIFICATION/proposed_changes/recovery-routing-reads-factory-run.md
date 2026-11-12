---
topic: recovery-routing-reads-factory-run
author: claude-opus-5-5:factory-run-work-preservation
created_at: 2026-11-12T09:01:13Z
---

## Proposal: Factory reads take the Dispatcher's own factory credential, outside any tenant credential wrapper

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

§"Dispatcher policy settings" makes every surface that reads a declared factory — the liveness question asked of each factory a journal names, the reconcile survey, plan run liveness, the merge-hold liveness guard, the run-event projection, the needs-human valve enrichment and the availability-evidence reads — resolve the factory through `dispatcher.factories`, and it reports an unanswering factory as unobservable. Recovery routing and `resume --item` then hold or refuse on that unobservable answer. No clause says WHICH credential such a read uses, or whether it runs inside the dispatch target's credential wrapper. So a tenant whose wrapper builds its child's environment afresh and drops every `FABRO_*` variable (a sealed wrapper) makes every such read unobservable, even while the factory itself reports the run ended. This proposal adds one paragraph. The Dispatcher MUST take every factory read on those surfaces, recovery routing's and `resume --item`'s earlier-run liveness read included, with that factory's own per-name dev token and resolved server as the default family wrapper (the default wrapper its host value in `fleet-launch/config.sh` names) injects them, outside any tenant's credential wrapper — in the outer default-family-wrapper environment the Dispatcher was launched under, or through the default family wrapper invoked for the read, when the Dispatcher itself runs inside a tenant wrapper's child. It MUST run the tenant's work-items store reads and writes under the tenant's declared wrapper and MUST NOT pass any factory credential into that wrapper's child. And a factory variable a tenant wrapper withheld MUST NOT be the cause of an unobservable factory read. Three new scenarios in Scenario 182 exercise it.

### Motivation

Owning work item bd-ib-comnk4, "Recovery routing reads factory run liveness with the dispatcher's own factory credential, outside the target tenant's credential wrapper", filed under plan factory-run-work-preservation (epic bd-ib-nckst7) by plan bootstrap-credentials-and-onboarding (hetzner-xubuntu-info) at legacy-coordinator-agent's direction on 2026-11-12. legacy-coordinator-agent (session c8c6cc4b) held the item for this topic at spec v359 as unstated: contracts.md asks liveness of every factory a journal names "resolved through dispatcher.factories", and an unanswering factory refuses the resume, but the spec says nothing about which credential the read uses or whether it runs inside the tenant's wrapper.

Measured case (legacy-dispatcher-agent, 2026-11-12 about 08:46Z): hetzner-xubuntu-info item hxi-wv762e's earlier run 01M778HJT951KC7G0BSC0V3MVW on petri ended blocked with exit 4 at 07:31:31Z, and petri's GET /api/v1/runs/<id> returned 200 with lifecycle failed/workflow_error. After a recorded fresh ruling at 08:46:37Z, the route read through the hxi wrapper was route='held' with RecoveryHold factory-run-liveness. Inside that wrapper FABRO_DEV_TOKEN__petri and FABRO_SERVER read back as 0 bytes, against 75 bytes through the family wrapper. The wrapper cannot carry them, by design. homelab's shared sealer refuses any child-environment passthrough name outside its reviewed non-secret list ("passthrough-refused"), and hetzner-xubuntu-info's own specification forbids credentials reaching the child except as declared bindings. legacy-coordinator-agent ruled out declaring the factory token as a per-tenant binding, because that is a credential copy. legacy-dispatcher-agent also measured that plugin build 58fb211b0 has no ended-run attestation route, and that `_dispatcher_recovery_measurements.py` routes every unobservable liveness read to `held`. So every resume, seeded and fresh-after-a-run route for a sealed-wrapper tenant is held for good, and this is the only way back for that tenant's recovery path.

Fleet scope, per the ruling: every tenant whose credential wrapper seals its child's environment. In-flight survey (2026-11-12 about 09:05Z): the eleven remote `spec/*` branches and the five open spec-touching pull requests (#5025 revise v360, #5021, #5019, #5018, #5005) touch no factory-read credential text. The in-tree pending proposals credential-requirements-follow-resolved-provider-routes (the dispatch credential set a target's wrapper injects) and a-needs-human-rest-overwrites (§"Dispatcher policy settings", a different paragraph) are compatible, and this proposal aligns with them. It changes neither the dispatch credential set nor how a dispatch submits a run.

### Proposed Changes

1. contracts.md, §"Dispatcher policy settings": IMMEDIATELY AFTER the paragraph that begins "Every surface that turns a declared factory into an address MUST use this one resolution" and ends "A factory's per-name settings — its dev token, its secret-channel declaration, its `bin` and its `environment` — stay keyed by the factory name, unchanged.", and BEFORE the paragraph that begins "The registry refusal applies to resolving a DECLARED, registry-backed entry", insert this paragraph, separated from each by one blank line:

"**Factory reads take the Dispatcher's own factory credential.** Every read the Dispatcher takes of a declared factory on a surface the preceding paragraph lists MUST authenticate with that factory's own per-name dev token and MUST reach the server this one resolution names, both taken from the Dispatcher's own factory credential: the factory variables the default family wrapper (the default wrapper its host value in `fleet-launch/config.sh` names) injects. When the Dispatcher process itself runs inside a dispatch target's `credential_wrapper` child, as the tenant-wrapper rule of §"Provisional fleet launch scripts" starts it, it MUST take each such read in an environment the default family wrapper establishes for it, and not in the tenant wrapper's child environment. Because §"Provisional fleet launch scripts" runs a tenant wrapper nested inside the default family wrapper, the Dispatcher MAY take such a read in the outer default-family-wrapper environment it was launched under, and need not invoke the default family wrapper again for each read. The same holds for the earlier-run liveness read of recovery routing (§"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work") and of `resume --item` (§"Resume from a published pull request (`resume --item`)"), and for every other recovery measurement that reads a factory. Such a read MUST NOT depend on the dispatch target's `credential_wrapper` forwarding any factory variable. When the dispatch target declares a `credential_wrapper` other than the host's default wrapper, the Dispatcher MUST take its reads and writes of that target's work-items store under that declared wrapper and MUST take every factory read this paragraph governs outside it. It MUST NOT pass a factory dev token, a factory server address or any other `FABRO_`-prefixed value into that wrapper's child in order to take such a read. A tenant wrapper that builds its child's environment afresh and drops `FABRO_`-prefixed variables (a *sealed* wrapper) MUST therefore leave every such factory read exactly as observable as it is for a tenant whose wrapper forwards them. A factory read MAY be reported unobservable only when the factory cannot be resolved, or cannot answer under the Dispatcher's own credential; a factory variable that a tenant wrapper withheld MUST NOT be the cause of an unobservable factory read, and so MUST NOT, by itself, hold a recovery route or refuse a resume. This paragraph governs factory READS only: it does not change the dispatch credential set a target's `credential_wrapper` injects (§"Self-contained plugin dispatch" → "The dispatch credential set"), or how a dispatch submits a run, and it does not change which wrapper §"Provisional fleet launch scripts" runs a launch-time command under. It applies to every tenant whose `credential_wrapper` seals its child's environment. Scenario 182 in `scenarios.md` exercises this paragraph."

No other paragraph of the section changes.

2. scenarios.md, §"Scenario 182 — A registry-backed factory resolves its address from the host registry, and an unresolvable one refuses before claim": inside that section's gherkin block, insert these three scenarios IMMEDIATELY AFTER `Scenario: Switching the default instance renames nothing` (whose last step is "And when the item recorded to "petri" is instead resumed with resume --item, the resume is dispatched to "petri"") and BEFORE the closing fence, separated from it by one blank line:

```gherkin
  Scenario: A sealed tenant wrapper does not make an ended run's liveness unobservable
    Given the factory registry maps "petri" to a server address
    And the default family wrapper (the default wrapper its host value in `fleet-launch/config.sh` names) injects the dev token of "petri"
    And a tenant repository whose credential_wrapper builds its child's environment afresh and drops every FABRO_ variable
    And an item of that tenant released for recovery whose earlier run on "petri" the factory reports as ended
    And the Dispatcher process runs inside that tenant wrapper's child
    When recovery routing grades the item
    Then the earlier run's liveness is read from "petri" with the dev token the default family wrapper injects, in a default-family-wrapper environment and not in the tenant wrapper's child environment
    And the run is observed as ended
    And the item is not routed held for the factory-run-liveness measurement

  Scenario: A sealed tenant's ledger IO still runs under its own wrapper, and no factory credential enters it
    Given a tenant repository whose credential_wrapper builds its child's environment afresh and drops every FABRO_ variable
    And an item of that tenant released for recovery whose earlier run's liveness the Dispatcher reads from a factory
    When recovery routing grades the item
    Then every read and write of that tenant's work-items store runs under the tenant's declared credential_wrapper
    And no factory dev token, factory server address or other FABRO_ value is passed into that wrapper's child

  Scenario: A factory that cannot answer under the Dispatcher's own credential is still unobservable
    Given the default family wrapper (the default wrapper its host value in `fleet-launch/config.sh` names) injects the dev token of "petri"
    And "petri" does not answer a run-liveness read
    And an item released for recovery whose earlier run was dispatched to "petri"
    When recovery routing grades the item
    Then the earlier run's liveness is reported unobservable, naming "petri"
    And the item is routed held
```

No H2 heading is added, removed or renamed, so `tests/heading-coverage.json` needs no co-edit.
