---
topic: a-hand-commit-s-passing
author: claude-opus-5-5
created_at: 2026-11-11T16:40:40Z
---

## Proposal: A hand commit's passing delegated pre-commit verdict stands in at this repository's pre-push gate

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

Add a refinement to constraints.md §"Pre-push gate refinements". This repository sets both `delegated_gate` and `delegated_pre_commit`, so its pre-push gate MUST accept a qualifying delegated pre-commit run as the full-suite verdict for the tree that run judged. It reaches that verdict through livespec-dev-tooling's shared same-tree library command, placed before its own green-token check. On a qualifying push it submits no pre-push gate Job and runs no local fall-through; it still runs on the pushing host the members the verdict does not cover, every world-reading member and every authorization-reading member. It prints what it accepted, and it gates exactly as today when no verdict qualifies. The change also adds one scenario.

### Motivation

Carrier: orchestrator work item bd-ib-3k3xh7. That item is the adoption follower of livespec-dev-tooling-yud7rc, and its filing tier is spec-change/partial against this spec's v353 '## Pre-push gate refinements' (linked topic a-hand-commit-s-passing; legacy-coordinator-agent holds approval until this topic ratifies, 2026-11-11 16:37Z). The ratified source is livespec-dev-tooling SPECIFICATION/contracts.md §"Delegated pre-push gate", bullet **Same-tree delegated pre-commit verdict** (revise v186, livespec-dev-tooling-73ocxb, released in livespec-dev-tooling v1.196.0). Its fleet-scope paragraph binds every consuming repository that sets both keys, including one whose pre-push gate reads the green token through a script of its own, and says such a gate MUST NOT refuse a qualifying run's evidence because it carries pre-commit provenance. Measured on this repository's master on 2026-11-11: pyproject.toml sets `delegated_gate = true` and `delegated_pre_commit = true` and pins livespec-dev-tooling v1.197.0. But `dev-tooling/just-check-pre-push.sh` consults only `dev-tooling/green-token-scope.sh`, which refuses every token carrying `pre_commit_aggregate`, before `gate_remote_delegate run`. So a hand commit's passing delegated pre-commit Job is followed by a second full-suite gate Job at push, about 37 minutes per hand-landed Green amend (check-per-file-coverage 2,222 s on a gmktec gate, as measured in that v186 proposal). The section today states the shared green-aggregate principle, but not the delegated pre-commit Job as an evidence source, the qualification, skipping both the pre-push gate Job and the local aggregate, the printed Job name and tree hash, or the fallback. The mechanism is livespec-dev-tooling's, so this text names the library command and states only this repository's obligations. The heading-coverage co-edit for the new scenario lies outside the spec target and lands in the revise commit.

### Proposed Changes

In SPECIFICATION/constraints.md §"Pre-push gate refinements", after the paragraph **A green aggregate on the exact tree carries to its push.**, add:

> **A hand commit's passing delegated pre-commit verdict carries to its push.** This repository sets both `delegated_gate = true` and `delegated_pre_commit = true`, so livespec-dev-tooling `SPECIFICATION/contracts.md` §"Delegated pre-push gate" **Same-tree delegated pre-commit verdict** binds its pre-push gate. Before it consults its own green token (`dev-tooling/green-token-scope.sh`), the pre-push gate MUST run livespec-dev-tooling's same-tree delegated pre-commit library command (livespec-dev-tooling-yud7rc), passing the member names of its own check set. A delegated pre-commit run qualifies only when livespec-dev-tooling recorded pre-push evidence for it naming its gate Job, and at push time the pushing worktree is clean and its `HEAD` tree is the tree that evidence names. When a run qualifies, the pre-push gate MUST NOT submit a pre-push gate Job and MUST NOT run the local fall-through aggregate. It MUST still run, on the pushing host against the same tree, every member of its check set that the evidence does not name as run and passed, every world-reading member, and every member that reads an authorization held outside the tree. It MUST refuse the push, naming the member, when any of them fails. It MUST print the gate Job's name, the tree hash whose verdict it accepted, the name of each member it ran, and the number of members it skipped because that verdict covered them. When no run qualifies, the pre-push gate MUST gate exactly as the rest of this section requires. `dev-tooling/green-token-scope.sh` MUST NOT be the reason a qualifying run's evidence is refused: its refusal of tokens carrying `pre_commit_aggregate` still applies to the green token, and does not apply to the library command's evidence. A pre-commit aggregate that ran on the committing host never qualifies. A deletion-only push still skips the aggregate as the first paragraph of this section requires, and that rule takes precedence. This paragraph is spec-first: as of its ratification this repository's pre-push gate never consults delegated pre-commit evidence, and work item bd-ib-3k3xh7 owns the change.

In SPECIFICATION/scenarios.md, add after the last scenario:

```gherkin
## Scenario: a hand commit's passing delegated pre-commit verdict stands in at the pre-push gate

Given this repository sets delegated_gate = true and delegated_pre_commit = true
And a hand commit's delegated pre-commit gate Job J passed the full aggregate of clean staged tree T and recorded pre-push evidence naming J, T and the members it ran and passed
And the pushing worktree is clean and its HEAD tree is T
When the pre-push gate runs for that push
Then it MUST NOT submit a pre-push gate Job and MUST NOT run the local fall-through aggregate
And it MUST run on the pushing host every check-set member the evidence does not name as passed, every world-reading member and every authorization-reading member
And it MUST print J, T, the name of each member it ran and the number it skipped
And when the worktree is dirty or its HEAD tree is not T, it MUST gate the push exactly as it does with no such evidence
```
