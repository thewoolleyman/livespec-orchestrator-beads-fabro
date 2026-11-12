---
topic: sandbox-driver-kubernetes-reports-a
author: claude-opus-5-5
created_at: 2026-11-12T20:55:00Z
---

## Proposal: A sandbox acquire refused for an exceeded namespace quota is capacity, never a credential fault or a needs-human rest

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

When the cluster refuses a run's sandbox because the namespace's ResourceQuota is full, the refusal is CAPACITY. The same request succeeds once a running sandbox ends. Today nothing states that, and the refusal reaches the Dispatcher as a credential fault: the Kubernetes API answers an exceeded quota with 403 Forbidden, and sandbox-driver-kubernetes v0.8.3 maps every 403 to an authentication error. A capacity refusal then ends the run at `blocked / needs-human` as if its credential were broken.

This proposal adds one paragraph under contracts.md §"Provider-limit permanence and root-cause surfacing", the section that already classifies sandbox-provider terminations (the OOM-kill paragraph). It makes a quota refusal at sandbox acquire typed capacity state, never a credential, authentication or permanent cause and never a needs-human rest. The item is released to `ready` without a human and re-admitted after a backoff. A CONTROL keeps every other 403 a credential fault. One Scenario exercises it.

### Motivation

Work item bd-ib-ko5kxf, held at spec-change tier with this linked topic. legacy-coordinator-agent (session 2420058a) routed it as spec-change on 2026-11-12: no ratified clause states quota-refusal classification. Its References line (## Fabro runtime constraints) governs none of its assertions, and this section's existing classes are all PERMANENT causes, whereas a quota refusal is the opposite.

Measured 2026-11-12 19:31Z by gmktec-factory-placement: bd-ib-t5aju3 run 01M78KW65M3F died at sandbox acquire with `exceeded quota: factory-runs, requested limits.cpu=6, used 114100m, limited 120`. The run was reported as "authentication with kubernetes failed ... the credential lacks permission", so needs-human read a capacity refusal as a credential fault.

The mechanism, read at sandbox-driver-kubernetes origin/main 5720eb8 (v0.8.3), `src/error.rs` `kube_error`: `Some(403) => Error::Auth(...)` maps EVERY 403. An exceeded quota is a 403 whose Status message begins `exceeded quota:`, so the discriminator is the message, not the code.

The driver half is landing ahead of this ratification in sandbox-driver-kubernetes#18, a repository with no spec gate, on the coordinator's ruling. It surfaces the refusal as a retryable provider error with code `quota-exceeded` and keeps the API server's own text. Orchestrator-side classification code waits for this revise.

Fleet scope: every factory node and every sandbox provider build. The paragraph names the Kubernetes form as one instance of a provider-reported capacity refusal, as the OOM paragraph does for its own class.

In-flight survey (open spec PRs and pending in-tree proposals, 2026-11-12 ~20:50Z):
- In-tree `transient-infra-release-and-re-dispatch` (bd-ib-cewr.6) defines its route over failures whose category is `transient_infra` "after every reclassification of §\"Provider-limit permanence and root-cause surfacing\"". This paragraph is one such reclassification and gives capacity refusals their own release, so the two compose in either revise order. Relation: `align`.
- No open spec PR (#5005 through #5088) touches this section or sandbox-acquire classification.

### Proposed Changes

**1. `contracts.md` §"Provider-limit permanence and root-cause surfacing".** Immediately after the paragraph that begins "**A sandbox killed for memory is named.**", insert:

> **A sandbox refused for namespace quota is capacity.** When a run's sandbox acquire is refused because the sandbox provider reports that the namespace's resource quota is exceeded, the refusal is CAPACITY: the same request succeeds once the namespace has room. On the Kubernetes provider, the refusal is a pod create answered 403 Forbidden whose Status message reports an exceeded quota; sandbox-driver-kubernetes surfaces it as a retryable provider error with code `quota-exceeded`. The Dispatcher MUST carry the condition as typed capacity state on the failure detail, naming the quota and the requested, used and limited amounts the provider reported. The dispatch outcome and its journal record MUST name the same.
>
> The Dispatcher MUST NOT classify such a refusal as a credential or authentication fault, MUST NOT classify it permanent under this section, and MUST NOT rest the item at `blocked / needs-human` for it. Instead it MUST release the item to `ready` without a human, by the four ordered steps of §"Factory-configurable ACP fallback priority" → "Adapter launch release and re-dispatch", journaling a `capacity-release` record in place of `adapter-launch-release` that names the quota and amounts. It MUST NOT re-admit the item before the refusal's instant plus a backoff of 60 seconds doubled for each consecutive capacity release of the item, up to 960 seconds.
>
> A capacity release MUST NOT consume any budget of §"The three rework caps", is a known host-attributable terminal under §"Across-dispatch required-result progress", and MUST NOT be surfaced as a needs-human decision. A provider refusal that does NOT report an exceeded quota, including every other 403 Forbidden, keeps the classification it arrived with: a missing permission remains a credential fault. Scenario <number assigned at revise> in `scenarios.md` exercises this paragraph.

**2. Scenario (`scenarios.md`).** Append the scenario below, numbered at revise time.

## Scenario <number assigned at revise> — A sandbox acquire refused for an exceeded namespace quota is released as capacity, not rested as a credential fault

Governing clause: `contracts.md` §"Provider-limit permanence and root-cause surfacing" → "A sandbox refused for namespace quota is capacity."

```gherkin
Feature: A sandbox acquire refused for an exceeded namespace quota is capacity, not a credential fault

  Scenario: A quota refusal releases the item with typed capacity state
    Given a dispatched run whose sandbox acquire the sandbox provider refused because the namespace's resource quota is exceeded
    And the provider reported the quota and the requested, used and limited amounts
    When the Dispatcher derives the run's outcome
    Then the failure detail carries typed capacity state naming the quota and the requested, used and limited amounts
    And the failure is not classified as a credential or authentication fault
    And the item is released to `ready` with a `capacity-release` journal record, and does not rest at `blocked / needs-human`
    And the item is not re-admitted before the refusal's instant plus its backoff

  Scenario: A missing permission is still a credential fault
    Given a dispatched run whose sandbox acquire the sandbox provider refused with 403 Forbidden for a missing permission
    And the provider's refusal does not report an exceeded quota
    When the Dispatcher derives the run's outcome
    Then the failure keeps its classification as a credential fault
    And no typed capacity state is set for the run
```

**3. Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new scenario heading, as numbered at revise. The row carries `test: "TODO"`, `work_item: "bd-ib-ko5kxf"` and a non-empty `reason` naming integration as the owed test's tier, together with the matching `tests/heading-coverage-debt.json` entry, carried through `resulting_files[]` or edited directly in that commit. bd-ib-ko5kxf's References line MUST then be repointed at the new scenario heading.
