---
topic: install-the-ci-fabro-binary
author: claude-opus-5-5
created_at: 2026-11-10T08:09:28Z
---

## Proposal: CI's factory-graph gate installs the pinned fabro release asset for the runner's architecture

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

Add one clause to the Fabro runtime constraints. CI's factory-graph gate installs the pinned upstream fabro release asset that matches the CI runner's architecture, and verifies it against the sha256 that release publishes for that asset. Any other architecture is refused by name. Add one scenario that states the behaviour.

### Motivation

CI's factory-graph gate (check-fabro-graph-validity, reached through check-metadata-batch at .github/workflows/ci.yml:1105 and dev-tooling/install-ci-fabro.sh) installs only fabro-x86_64-unknown-linux-musl from the pinned upstream fabro-sh/fabro v0.254.0 release. Because of that, livespec-dev-tooling's ci-runner/k3s/phase2/workload-arch.conf keeps livespec-orchestrator-k3s amd64-only, and this repository is excluded from the arm64 CI overflow that went live 2026-11-10T07:57Z. Measured 2026-11-10: the same release publishes fabro-aarch64-unknown-linux-musl.tar.gz (asset 438318044) with a published sha256 (asset 438318058), so no build is needed. The ratified specification says nothing about this CI installer or its architecture. Work item bd-ib-jjmywv was therefore filed at the spec-change tier with linked-proposal-topic install-the-ci-fabro-binary, and its admission is held until this topic ratifies (legacy-coordinator-agent, 2026-11-10). This clause governs only the CI gate's validation binary. It changes nothing about which Fabro build the factory's own servers pin, which the rest of the section governs.

### Proposed Changes

In `SPECIFICATION/constraints.md`, section "## Fabro runtime constraints", add this bullet after the section's existing bullets:

- **CI graph-gate binary.** CI's factory-graph gate is the `check-fabro-graph-validity` check, which validates the repository's committed Fabro workflow graphs during CI. It validates with the pinned upstream `fabro-sh/fabro` release, not with the factory's carrier build, and that binary is outside "the factory" as this section scopes it. The gate's installer MUST install the pinned release's static Linux asset whose architecture matches the CI runner's own (`x86_64` or `aarch64`). It MUST verify the downloaded asset against the sha256 that release publishes for that asset, pinned beside the version, before installing it. On any other runner architecture it MUST exit non-zero with a message naming that architecture and MUST NOT install a binary.

In `SPECIFICATION/scenarios.md`, at the end of the file, add:

## Scenario <next free number> — CI's factory-graph gate installs the pinned fabro asset for the runner's architecture

```gherkin
Feature: CI's factory-graph gate installs the pinned fabro asset for the runner's architecture

  Scenario: An x86_64 or aarch64 runner gets its own verified asset
    Given CI's factory-graph gate pins one upstream fabro release
    And that release publishes a static Linux asset and its sha256 for the runner's architecture
    When the gate's installer runs on an x86_64 or aarch64 runner
    Then it installs that architecture's asset after verifying the published sha256

  Scenario: Any other architecture is refused by name
    Given CI's factory-graph gate pins one upstream fabro release
    When the gate's installer runs on a runner whose architecture is neither x86_64 nor aarch64
    Then it exits non-zero with a message naming that architecture
    And no fabro binary is installed
```

The revise pass that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new scenario heading in the same change, per the repository's revise co-edit discipline.
