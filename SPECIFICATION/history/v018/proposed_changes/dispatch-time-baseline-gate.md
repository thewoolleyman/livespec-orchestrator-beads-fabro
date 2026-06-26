---
topic: dispatch-time-baseline-gate
author: claude-opus-4-8
created_at: 2026-06-26T19:01:54Z
---

## Proposal: Dispatch-time baseline conformance gate

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Add a new contracts.md H2 section 'Dispatch-time baseline conformance gate' that codifies the Conformance Pattern's dispatch-time tier for the Beads/Fabro Dispatcher: before driving any work-item into a Fabro worker sandbox, the prepare chain installs the baseline Mechanism (canonical commit-refuse hook) and Exemption (livespec.sandboxExempt marker) and then MUST run the baseline Verifiers (check-primary-checkout-commit-refuse-hook-installed + check-plugin-resolution), aborting the run on any Verifier failure so every dispatched sandbox is conformant by construction.

### Motivation

livespec-zs22 increment 5 (Conformance Pattern), milestone livespec-zs22.7.7 M6-f. The four-tier enforcement-in-depth needs its dispatch-time tier codified in the orchestrator's own SPECIFICATION. The Fabro prepare chain already installs the commit-refuse hook and the sandboxExempt marker; M6-f adds the two baseline Verifier prepare steps and this normative contract clause they satisfy. Parallel to how the Planning Lane and grooming realizations carry their core patterns here.

### Proposed Changes

1) contracts.md: add a new H2 section 'Dispatch-time baseline conformance gate' (after 'Planning Lane realization', before 'Beads connection model') stating that the Dispatcher's Fabro prepare chain MUST install the baseline Mechanism + Exemption and MUST then run the shared baseline Verifiers (check-primary-checkout-commit-refuse-hook-installed + check-plugin-resolution declaration-integrity mode) over the provisioned sandbox, aborting the run on a non-zero exit (conformant by construction), and that the Verifiers are the shared livespec-dev-tooling checks reused across tiers, invoked from .fabro/workflows/implement-work-item/workflow.toml. 2) tests/heading-coverage.json: add a TODO entry for the new H2 (co-edit). The implementing Fabro prepare steps land in the same change.
