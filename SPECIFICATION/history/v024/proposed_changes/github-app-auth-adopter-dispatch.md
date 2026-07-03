---
topic: github-app-auth-adopter-dispatch
author: claude-fable-5
created_at: 2026-07-03T02:48:55Z
---

## Proposal: dispatch-credential-set

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Codify the FULL per-dispatch credential set a dispatch target's credential_wrapper must inject — the GitHub App environment (GITHUB_APP_ID + GITHUB_PRIVATE_KEY, optional GITHUB_APP_INSTALLATION_ID), the tenant work-items store secret (BEADS_DOLT_PASSWORD on the beads substrate), and the engine LLM credential (CLAUDE_CODE_OAUTH_TOKEN today) — with every credential-consuming seam failing closed naming the specific missing variable and the TARGET's own configured wrapper (never a fleet wrapper) in its diagnostic, and the full set surfaced up front rather than one failure at a time. Surfaced by the openbrain adopter dogfood (github-app-auth p3icf6, 2026-07-03).

### Motivation

Maintainer-ordered spec wave codifying the github-app-auth adopter-dogfood learnings: today the CLAUDE_CODE_OAUTH_TOKEN requirement only surfaces at dispatch time and refusals name the fleet wrapper, so the contract must pin the architecture the implementation items (bd-ib-3m44nx, bd-ib-ls32yb) build to.

### Proposed Changes

Extend contracts.md §"Self-contained plugin dispatch" with a clause paragraph: the dispatch TARGET's configured credential_wrapper MUST inject the full per-dispatch credential set (App environment + tenant store secret + engine LLM credential); each seam MUST fail closed naming the specific missing variable; every such diagnostic MUST name the dispatch TARGET's own configured credential_wrapper, never a fleet wrapper; the full required set is surfaced up front (preflight + adopter docs). Extend Scenario 29's fail-closed sub-scenario with the diagnostic-content Then lines. Cross-cite implementation items bd-ib-3m44nx and bd-ib-ls32yb.

## Proposal: per-tenant-engine-identity

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Codify that the Fabro server serving a dispatch MUST hold the dispatch TARGET tenant's own GitHub App identity: a server instance holds exactly one App integration, so adopter dispatch runs against a per-tenant server instance (e.g. a dedicated FABRO_HOME), and a preflight SHOULD verify the serving App can reach the target repo before launch, refusing with an actionable diagnostic instead of failing inside the engine run. Surfaced by the openbrain adopter dogfood: dispatching an adopter repo through the shared host server fails because the fleet App is not installed for the target.

### Motivation

Maintainer-ordered spec wave: the per-tenant engine identity is architecture (one App per server instance is a structural fact), and the contract must exist before the implementation items (bd-ib-z2ctra deliverables a/b, bd-ib-w4iaaf) build the recipe docs and preflight to it.

### Proposed Changes

Extend contracts.md §"Self-contained plugin dispatch" with a clause paragraph: the serving engine instance MUST hold the target tenant's own App identity; adopter dispatch runs against a per-tenant server instance; a dispatch preflight SHOULD verify App-to-target-repo reachability before launch. Add the per-tenant-identity/preflight sub-scenario to a new Scenario 32 (adopter-target dispatch compatibility). Cross-cite bd-ib-z2ctra and bd-ib-w4iaaf.

## Proposal: app-workflows-permission

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Codify that workflow-file-touching pushes structurally require the GitHub App's workflows read-write permission grant, and that the dispatch preflight and adopter docs MUST surface that grant among the App-installation requirements — otherwise the push is host-rejected regardless of dispatch correctness.

### Motivation

Maintainer-ordered spec wave: the workflows-RW grant is a structural GitHub-host fact an adopter cannot discover until a workflow-touching push fails deep inside a run; the contract pins it as a preflight/docs requirement.

### Proposed Changes

Extend contracts.md §"Self-contained plugin dispatch" with a clause sentence on the workflows RW grant and its preflight/docs surfacing; fold the grant into Scenario 32's preflight sub-scenario. Cross-cite bd-ib-z2ctra (preflight scope).

## Proposal: target-local-workflow

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Codify that an adopter MAY carry its own implement-work-item workflow in the TARGET repo (<target>/.fabro/workflows/implement-work-item/, supplied today via the dispatcher's explicit --workflow override), and that prepare steps are TARGET-TOOLCHAIN facts, not fleet constants — the plugin-default payload's uv/lefthook/livespec_dev_tooling prepare chain is the FLEET toolchain realization, which fails structurally on a pnpm/TS adopter. Surfaced by openbrain dogfood attempt 3 (run 01KWJP95QZ9WDTZPAAVBMFQ85E).

### Motivation

Maintainer-ordered spec wave: the architecture point (prepare steps are per-target facts; the target may own its workflow) must be contract before the durable mechanism (automatic target-local resolution + parameterized prepare steps, bd-ib-z2ctra deliverable d) is designed — that mechanism amends the plugin-root resolution rule when it ships.

### Proposed Changes

Extend contracts.md §"Self-contained plugin dispatch" with a clause paragraph: an adopter MAY carry a target-local workflow supplied via the --workflow escape hatch; prepare steps are target-toolchain facts, not fleet constants; any future automatic target-local resolution amends this section's plugin-root resolution rule before shipping. Add the target-local-workflow sub-scenario to Scenario 32. Cross-cite bd-ib-z2ctra deliverables (c)/(d).

## Proposal: pull-primary-default-branch

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Codify that every dispatch-path stage referencing the target's primary branch — the post-merge janitor's pull-primary refresh above all — MUST resolve the TARGET repo's default branch (git symbolic-ref refs/remotes/origin/HEAD, or gh repo view --json defaultBranchRef) and MUST NOT hardcode master; adopter repos commonly default to main. Surfaced by the openbrain dogfood (PR #3, stage pull-primary: fatal: could not find remote ref master).

### Motivation

Maintainer-ordered spec wave: the compat-block canonical_branch key already documents the symbolic-ref resolution for merge-evidence checks; the dispatch path must reuse that single resolution rather than carrying its own hardcoded ref, and the contract pins that before bd-ib-hkzcfb implements it.

### Proposed Changes

Extend contracts.md §"Self-contained plugin dispatch" with a clause paragraph mandating default-branch resolution (reusing the canonical_branch resolution) and forbidding a hardcoded master on the dispatch path. Add the default-branch pull-primary sub-scenario to Scenario 32. Cross-cite bd-ib-hkzcfb.
