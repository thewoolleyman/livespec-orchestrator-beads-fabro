---
topic: claude-fable-5-critique
author: claude-fable-5
created_at: 2026-07-02T09:35:01Z
---

## Proposal: app-auth-dispatch-scenarios-missing

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The v022 factory GitHub App auth block in contracts.md's Self-contained plugin dispatch section introduced load-bearing MUST behaviors — every dispatch-path GitHub operation authenticates with an App installation token injected by the dispatch target's credential_wrapper; resolution is FAIL-CLOSED (refuse with an actionable diagnostic when the App environment is absent and no credential_wrapper exists, never falling through to a fleet credential or ambient gh login); token acquisition is re-mintable at any time so long operations survive expiry; and the sandbox receives only an EPHEMERAL freshly-minted token, never the durable private key — but scenarios.md contains no scenario exercising any of them. Scenarios 18 and 19 cover the provider-subscription worker credential, a different credential class on a different seam.

### Motivation

Load-bearing error paths and invariants left without an acceptance scenario are silently unverifiable — the doctor since-version delta review flagged the v022 changed region as uncovered behavior, and without a scenario the fail-closed refusal path stays undefined at the acceptance tier the heading-coverage discipline binds tests to.

### Proposed Changes

scenarios.md MUST gain App-auth dispatch scenarios covering at least: (a) the fail-closed refusal — given no App environment and a dispatch target with no credential_wrapper, when a dispatch is attempted, then the Dispatcher refuses with an actionable diagnostic and does not fall through to a fleet credential or ambient gh login; (b) remint across a long operation — given a merge-poll outliving a single token's validity, then every spawned subprocess resolves a currently-valid token and the operation survives; (c) ephemeral-only projection — given a dispatched sandbox, then its environment carries a freshly-minted installation token and neither the App private key nor any long-lived PAT. The new scenario H2s MUST be co-registered in tests/heading-coverage.json in the same revise.

## Proposal: conformance-gate-scenario-missing

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

contracts.md's Dispatch-time baseline conformance gate section mandates that the Dispatcher's prepare chain provisions every Fabro sandbox to the baseline profile, runs the shared Verifiers over it, and that a Verifier's non-zero exit MUST abort the run before any work is driven — yet scenarios.md contains no scenario exercising the gate, neither the green provisioning path nor the abort-on-baseline-violation path.

### Motivation

The abort path is the load-bearing half of the gate (a baseline violation surfacing as a failed dispatch rather than silently non-conformant work), and leaving it scenario-less makes the behavior unverifiable at the acceptance tier and its intended failure mode unclear to the console and to future implementers.

### Proposed Changes

scenarios.md SHOULD gain a dispatch-time conformance-gate scenario pair: given a sandbox the prepare chain provisioned, when the baseline Verifiers pass, then the work-item is driven; and given a Verifier exiting non-zero, when the prepare chain gates, then the run aborts before any work is driven and the dispatch surfaces the baseline violation. The new scenario H2 MUST be co-registered in tests/heading-coverage.json in the same revise.
