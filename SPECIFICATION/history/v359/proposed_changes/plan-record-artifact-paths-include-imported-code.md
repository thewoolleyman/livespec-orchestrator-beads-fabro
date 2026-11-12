---
topic: plan-record-artifact-paths-include-imported-code
author: claude-opus-5-5
created_at: 2026-11-12T01:55:41Z
---

## Proposal: A plan record's artifact paths include released library code its artifact imports

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

v350 requires a record in a component-declaring repository to name "the repository paths of each artifact its steps ran", but does not say whether library code an artifact imports from another declared component counts. The two readings give opposite verdicts on the same run: an artifact whose own paths lie under no component passes with release none if its imports are ignored, and must name the importing component's release tag if they count. This proposal states that every executed repository path counts, imported library code included. Where a record names a component's tag only because of such an import, it must say so and state whether that code at the commit is byte-identical to the tag's tree.

### Motivation

Found while posting the Proof of Done for homelab plan secret-writer-stored-key-alias (epic homelab/hl-bvycoc), the first record judged under v350's per-component rule (consumed at v0.320.0). homelab declares shared-credentials (tag_prefix shared-credentials-v, paths tools/shared_credentials/; mi-homelab/homelab#1165). The plan's artifact is the canonical secret writer, infra/shared-credentials/write-secret.sh, which runs `python3 -m shared_credentials_provisioning write` from tools/shared_credentials_provisioning/ on main. That path lies under no component. But the writer's CLI import loads shared_credentials.{awscli,manifest,material,refusal,trust} from tools/shared_credentials/, measured through sys.modules after importing the CLI. Those modules are byte-identical to shared-credentials-v0.2.0's source (git diff ca3f65b2d origin/main -- tools/shared_credentials/ is empty). Under v0.320.0, naming only the writer's own paths with release none is ACCEPTED, though it omits code the run executed. Naming tools/shared_credentials/ too forces release shared-credentials-v0.2.0, a release that does not contain the writer. legacy-coordinator-agent ruled (R301, 2026-11-12) that the record take the second form with a byte-identity disclosure, because v350's wording does not exempt imported code, and directed this finding be filed so the rule says so.

### Proposed Changes

In SPECIFICATION/contracts.md, §"Planning Lane realization" → "### Plan Definition of Done and Proof of Done", in the plan Proof of Done record paragraph, replace the sentence

> With it, each release tag belongs to the declared component whose `tag_prefix` it begins with, and a record MUST name, beside the default-branch commit, the repository paths of each artifact its steps ran from that tree, on an `artifact paths:` line in its build identity.

with:

> With it, each release tag belongs to the declared component whose `tag_prefix` it begins with, and a record MUST name, beside the default-branch commit, the repository paths of each artifact its steps ran from that tree, on an `artifact paths:` line in its build identity. Those paths MUST include every repository path whose code the steps executed from that tree, including library code an artifact imports or invokes from another declared component's `paths`, not only the artifact's own entry point. Where a record names a component's release tag only because its artifact imports or invokes that component's code from the default-branch tree, the record MUST say so, and MUST state whether that code at the named commit is byte-identical to the named tag's tree under that component's `paths`.

In SPECIFICATION/scenarios.md, append one scenario with an unnumbered heading:

## Scenario: a plan record's artifact paths include released library code its artifact imports

```gherkin
Feature: a plan record's artifact paths include released library code its artifact imports

  Scenario: an unreleased artifact importing a released component's code names that component's release
    Given a governed repository declaring release components shared-credentials with tag_prefix shared-credentials-v and paths tools/shared_credentials/
    And the repository carries the release tag shared-credentials-v0.2.0
    And a plan's artifact infra/shared-credentials/write-secret.sh runs tools/shared_credentials_provisioning/ from the default-branch tree
    And that artifact imports modules from tools/shared_credentials/
    When the plan's captured record is judged
    Then a record whose artifact paths omit tools/shared_credentials/ does not satisfy the artifact paths requirement
    And a record naming tools/shared_credentials/ among its artifact paths and stating release none is rejected for component shared-credentials
    And a record naming tools/shared_credentials/ and release shared-credentials-v0.2.0 with the default-branch commit, stating that the imported code is byte-identical to that tag's tree under tools/shared_credentials/, satisfies the release rule
```

Spec size: two sentences added, one scenario added.
