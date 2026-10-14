---
topic: sandbox-hook-time-limits
author: claude-opus-5-5-plan-publish-draft-green-work-loss
created_at: 2026-10-14T01:56:59Z
---

## Proposal: Make publish_draft's limit configurable, reap an over-limit hook before the next commit, and name the over-limit hook as the cause

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds publish_draft to the dispatcher.node_timeouts keys so a loaded factory can give the publishing push room, requires that a commit or push hook still running when an agent's tool call is ended at its limit be fully terminated before the agent's next commit or push, and requires a hook-over-limit dispatch-journal row and a named needs-human cause whenever a hook is ended by the agent tool-call limit or a command node's resolved timeout.

### Motivation

Work-item bd-ib-xi63mq (plan publish-draft-green-work-loss, epic bd-ib-acrr56) carries plan assertion 2. Its dispatch run 01M4VXXDDG4B1A5SDX497TXNVK was rested at dod_gate on 2026-10-14 because two of its assertions name behaviour no ratified clause states: the spec tree has no clause about an agent's per-tool-call limit, git hooks or orphaned hook processes, and no record that classifies an over-limit hook. Measured instances on hp: run 01M4TZQKSKWFWAZZ3QX6ZM3D8N (2026-10-13), whose Green-amend commit hit the agent's 1202 s tool-call limit while the lefthook suite kept running, so the agent's retry ran a second full suite concurrently and the item ended at needs-human; and four publish_draft or pr_refresh stages ended at exactly 1800000 ms while their pre-push or check suite was still running (bd-ib-jqvqlf 01M4T1ZM6BEQ, bd-ib-vlctc3 01M4TYK09SRP, bd-ib-zddbkq 01M4VQP22484, bd-ib-s6bowj 01M4VQV7APGJ in pr_refresh at about 96 percent of its suite). pr_refresh is already a configurable node; publish_draft is not, so a repository cannot give its publishing push the room its own gate needs. Each stop was reported as a needs-human decision with no named cause, which is what hid them. The proposal keeps every stop fail-closed and adds no blocked_reason member; it adds a configurable limit, a reaping obligation and a name.

### Proposed Changes

In SPECIFICATION/contracts.md, section "ACP node timeouts":

(1) In the paragraph beginning "**Keys.**", extend the node-name list of `dispatcher.node_timeouts` from "(`dod_gate`, `implement`, `fix`, `review_fix`, `proof_capture`, `review`, `disposition`, `proof_verify`, `pr_refresh`, `pr`, `janitor`)" to "(`dod_gate`, `implement`, `fix`, `review_fix`, `proof_capture`, `review`, `disposition`, `proof_verify`, `publish_draft`, `pr_refresh`, `pr`, `janitor`)". The 1800-second default, the three resolution layers and the literal rendering apply to `publish_draft` exactly as to every other listed node.

(2) Append a new paragraph at the end of the section:

"**Repository hooks that outlive a limit.** A governed repository's commit and push hooks run inside the factory sandbox under one of two limits: the agent's per-tool-call limit, when an ACP agent runs `git commit` or `git push` inside its own turn, or the resolved timeout of a command node that commits or pushes, such as `publish_draft` or `pr_refresh`. When an agent tool call that runs a git commit or push is ended by the agent's per-tool-call limit while the hook run it started is still executing, every process of that hook run MUST be terminated before the agent's next git commit or push in the same sandbox starts, so that two hook runs never execute concurrently in one sandbox. In that case, and whenever a command node's commit or push is ended by the node's resolved timeout, the run MUST record a `hook-over-limit` row in the dispatch journal naming the node, the git operation, the limit that ended it in seconds, and the elapsed milliseconds of the hook run at termination. When such a run ends at needs-human, the needs-human cause recorded on the item MUST name `hook-over-limit`, the node and the git operation, so that the stop is not presented as an agent's decision; `blocked_reason` gains no member and the run still preserves its work under \"A factory run never awaits a human\". Scenario 177 in `scenarios.md` exercises this paragraph."

In SPECIFICATION/scenarios.md, append:

## Scenario 177 — A repository hook that outlives its limit is reaped and named, and publish_draft's limit is configurable

```gherkin
Feature: Repository hooks inside a sandbox stay within, and are named against, their limits
  As the maintainer of a repository whose full gate runs in its commit and push hooks
  I want an over-limit hook reaped, recorded by name, and its stage limit configurable
  So that a loaded factory host does not turn a green run into an unexplained needs-human

  Scenario: publish_draft resolves its timeout from configuration
    Given a dispatch target whose "dispatcher.node_timeouts" sets publish_draft to 3600
    When the Dispatcher renders the dispatch payload's workflow graph
    Then the publish_draft node's timeout attribute is the literal duration 3600s

  Scenario: An over-limit commit hook is reaped before the next commit
    Given an implement-stage agent whose git commit tool call is ended by its tool-call limit while the commit hook is still running
    When the agent starts its next git commit in the same sandbox
    Then no process of the earlier hook run is still running
    And the dispatch journal carries a hook-over-limit row naming the implement node, the commit operation, the limit and the elapsed milliseconds

  Scenario: A command node's over-limit push is named
    Given a publish_draft push whose pre-push hook is still running when the node's resolved timeout ends it
    When the run ends at needs-human
    Then the dispatch journal carries a hook-over-limit row naming publish_draft, the push operation and the resolved timeout
    And the needs-human cause recorded on the item names hook-over-limit, publish_draft and the push operation
    And the run's work is preserved before it terminates
```

The revise pass MUST add `tests/heading-coverage.json` and `tests/heading-coverage-debt.json` entries for Scenario 177 (test "TODO" with a reason naming bd-ib-xi63mq).
