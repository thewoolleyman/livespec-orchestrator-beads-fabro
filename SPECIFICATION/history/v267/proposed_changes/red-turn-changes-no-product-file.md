---
topic: red-turn-changes-no-product-file
author: claude-opus-5-5
created_at: 2026-11-01T13:41:09Z
---

## Proposal: The red turn changes no product file, and commit_red refuses a red turn that did

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

In contracts.md "The implement stage runs Red and Green as separate nodes", require the red prompt to direct the agent to create, change or delete no product file, and require commit_red to refuse when the working tree after a red turn carries a product-file change, naming each path, so the run re-enters red. Add one Gherkin scenario to Scenario 285.

### Motivation

The fleet's Honeycomb alert "Factory post-hoc Red share" reported 96% over the trailing eight hours on 2026-11-01. After the v227 test-discipline change, new Codex-ACP calibrations still showed first_product_write_before_red=true, with 152 of 228 refusals. v262 makes the Red COMMIT test-only, because commit_red stages only the one test file, but it does not stop a red turn from WRITING product code. Product edits a red turn leaves behind are not staged by commit_red and are carried into the green turn, so the implementation is still written before its failing test has been observed, and the alert keeps firing after the split ships. Requiring the red prompt to forbid product writes, and having commit_red refuse a red turn that made them, makes test-first a property of the graph instead of a request the agent can ignore. The term product file is the one v262's fifth commit rule already uses, under the repository's product-path classification.

### Proposed Changes

In `contracts.md`, paragraph **The implement stage runs Red and Green as separate nodes.**, after the sentence `The red prompt MUST direct the agent to write the failing test the work item's Definition of Done needs, to run only that test, and to make no commit.`, insert:

```markdown
The `red` prompt MUST also direct the agent to create, change or delete no product file, because the implementation belongs to the `green` turn. A product file is a path that the repository's product-path classification counts as product, the same classification that "a Red commit MUST stage exactly one test file and no product file" relies on. Before it stages anything, `commit_red` MUST compare the working tree and the index against the dispatch base, with engine checkpoint commits already folded. When any product file differs, `commit_red` MUST refuse without committing and append a handoff section that names each such path. That refusal re-enters `red` exactly as any other `commit_red` refusal does, and the re-entered turn starts from the dispatch base.
```

In `scenarios.md`, inside the `## Scenario 285 — Red and Green run as separate nodes and every implement commit is made by a command node` Gherkin block, after `Scenario: A refused Red commit re-enters red`, add:

```gherkin
  Scenario: A red turn that changes a product file is refused at commit_red
    Given a red turn that wrote a failing test and also changed a product file
    When commit_red runs
    Then commit_red makes no commit
    And the handoff file's newest section names the changed product file
    And the run re-enters red from the dispatch base
```
