---
topic: checkpoint-commit-failure-attribution
author: claude-opus-5-5
created_at: 2026-10-12T17:31:00Z
---

## Proposal: Attribute a failed engine checkpoint commit and rest its item at needs-human

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add an H3, "Failed engine checkpoint commit attribution", to contracts.md under "## Dispatcher admission, WIP cap, and post-merge acceptance", immediately after "### Failed post-merge janitor target attribution", and append Scenario 170. When a Fabro run ends because the engine's own checkpoint of a node failed or ran out of its checkpoint budget, the Dispatcher names the node and what failed: the failed targets and hook commands read from the run's `checkpoint.failed` output tail under the janitor's structured-summary rule, a labelled observation when no summary exists, or the configured budget beside the engine's measured elapsed time for a budget expiry. The dispatch outcome becomes `blocked`, the item rests at `blocked / needs-human` through the existing needs-human transition, one `checkpoint-failure` journal row and one `livespec-checkpoint-failure` ledger comment carry the attribution, and the run's terminal patch is recorded by size and digest so that preservation by reference is visible.

### Motivation

Plan checkpoint-commit-hook-failures (epic bd-ib-hcwmnq) item bd-ib-6jkjzm was refused by the factory Definition-of-Done gate because no heading governs engine-checkpoint-commit failure reporting. Scenario 103 governs the needs_human terminal only, and Scenario 167 with §"Failed post-merge janitor target attribution" governs the janitor only.

Measured 2026-10-12 on hp: of the 215 runs that ended `workflow_error` since 2026-10-08, 41 ended on a checkpoint failure. There were 28 `git commit failed (exit 1)` failures, 8 checkpoint budget expiries and 5 `git add failed` failures. Each one reached the dispatch journal only as `git checkpoint commit failed for node <n>: git commit failed (exit 1); category=deterministic` or the budget equivalent. The hook output that names the cause exists only in the run's `checkpoint.failed` event, as an 8192-byte tail. Of the 28 commit failures, 23 tails carry the aggregate's `Failed targets (N):` summary and 5 are commit-msg refusals that only lefthook's per-command summary names. Because no blocked outcome is produced, the item stays `active` with no reason, `drive` exits 1, and the item is re-dispatched unchanged: bd-ib-z46mth was re-dispatched four times, and bd-ib-4ipmub and bd-ib-pwqxso twice each.

The `needs-human` disposition follows from the contracts text. `blocked` is for an impediment from outside the factory, and `blocked_reason` stays `needs-human | infra-external` (§"Rework-pending re-dispatch", "Vocabulary non-extension"). No actor clears `infra-external` on its own, and every surface that routes a decision to a human is keyed on `needs-human`. The decision this failure leaves is the needs-human answer set of §"A factory run never awaits a human": retry, re-implement from the preserved work, or abandon.

Sibling bd-ib-jb53pu sets `skip_git_hooks = true` and `commit_timeout = "5m"`, which should remove most hook refusals in this repository. This clause is the defense in depth for every checkpoint failure that still happens: a workflow that keeps its hooks, a commit timeout, or a `git add` failure.

### Proposed Changes

Insert the following H3 into SPECIFICATION/contracts.md under "## Dispatcher admission, WIP cap, and post-merge acceptance". It goes immediately after "### Failed post-merge janitor target attribution" and before "### Repository integration contract". Append Scenario 170 to SPECIFICATION/scenarios.md after Scenario 169.

Co-edit tests/heading-coverage.json in the same change. It needs one new entry for `## Scenario 170 — A failed engine checkpoint commit names its node and cause and rests the item at needs-human`, with `spec_root` `SPECIFICATION`, `spec_file` `scenarios.md`, `test` `"TODO"`, `work_item` `bd-ib-6jkjzm`, and the reason "A real integration-tier test is owed for checkpoint-failure attribution, the needs-human disposition and the journal and ledger records through the actual Dispatcher; existing child bd-ib-6jkjzm owns it." The contracts.md H3 is not tracked by the coverage map.

### Failed engine checkpoint commit attribution

A Fabro run ENDS ON A FAILED ENGINE CHECKPOINT when its terminal failure is the engine's own checkpoint of a node: the `git add` and `git commit` the engine performs on the run branch after a node finishes, outside every workflow node. Such a checkpoint either fails or exceeds its checkpoint operation budget. The failure is an engine error rather than a node outcome, so the workflow graph cannot route it and the `needs_human` terminal never fires.

The Dispatcher MUST recognize such a run from the run's event stream: a `checkpoint.failed` event for the node at which the run ended. Only when that stream cannot be read MAY it recognize the run from the engine's terminal failure message, which names a checkpoint commit failure or a checkpoint operation budget expiry. Recognition MUST NOT pre-empt an outcome that the Dispatcher already classifies otherwise. A run parked at a human gate, a run carrying the `needs_human` terminal's sentinel, and a run classified as provider-limit keep their existing routes.

The Dispatcher MUST read the run's events from the dispatch's resolved factory target before it renders the dispatch outcome. It MUST do so whether or not any node of the workflow is fallback-enabled, and it MUST NOT read them from a local default target. It MUST name the node from the `checkpoint.failed` event's node identifier. When the events cannot be read, it MUST take the node from the engine's failure message. When neither names a node, it MUST say that the node was not reported rather than infer one. The Dispatcher MUST also carry the engine's checkpoint error exactly as the engine reported it, for example `git commit failed (exit 1)`, `git add failed` or `git commit timed out after 900004ms`.

When the `checkpoint.failed` event carries an output tail, the Dispatcher MUST apply the structured-summary rule of the preceding subsection to the whole tail exactly as the engine recorded it, before applying any bound of its own. It MUST name every target in a structured `Failed targets` summary. It MUST NOT present a passing target or recipe printed outside that summary as the cause. A summary whose lines end in carriage-return line-feed pairs is the same summary. When the tail also carries the hook runner's own per-command run summary and that summary marks individual hook commands as failed, the Dispatcher MUST name each failed hook command beside the targets.

When the tail carries neither summary, the Dispatcher MUST label a bounded excerpt of the tail as an observation. It MUST NOT assert that any hook, target or recipe in that excerpt caused the failure. The tail is the engine's bounded suffix of the hook output, so a summary whose header the engine's bound cut away is absent rather than partial, and the Dispatcher MUST NOT reconstruct it. When the event carries no output tail at all, as with `git add failed`, the engine's checkpoint error is the whole attribution.

When the engine reports that the checkpoint operation budget was exceeded, the Dispatcher MUST name three things: the node, the git operation that timed out as the engine names it, and the checkpoint commit budget configured for that dispatch. The configured budget, in seconds, is the `[run.checkpoint] commit_timeout` of the run configuration that the Dispatcher submitted, or the engine's stock budget when that key is absent. The elapsed time that the engine reports MUST be carried beside the budget, labelled as the engine's measurement, and MUST NOT be presented as the configured budget. When the configured budget cannot be read, the Dispatcher MUST say so and name the reason, and it MUST NOT substitute the stock budget.

The dispatch outcome MUST be `blocked` at stage `fabro-run`. The Dispatcher MUST rest the item at `blocked` with `blocked_reason: needs-human`, through the same transition and `needs-human-blocked` journal row that a `needs_human` terminal produces. The item MUST NOT be left `active`, and the claim MUST NOT be released to `ready`. This failure leaves a decision that only the ledger's valves express (retry, re-implement from the preserved work, or abandon), and nothing outside the factory clears it on its own. It therefore rests at `needs-human` and never at `infra-external`, and `blocked_reason` gains no member. The dispatch reports exit code 4 under §"Dispatcher exit codes". No exit code is added or redefined.

The outcome detail MUST name the run, the node, the engine's checkpoint error and the attribution. The attribution is one of: the failed targets and failed hook commands; the labelled observation; or the configured budget with the engine's measurement. The detail MUST state that the decision lives in the ledger and MUST name the `resolve-blocked:<work-item-id>:ready` valve. The Dispatcher's own detail bound MUST NOT drop a named target or hook command.

The Dispatcher MUST journal exactly one `checkpoint-failure` row for each such dispatch. The row carries these keys:

- `work_item_id`, `fabro_run_id` and `node`.
- `checkpoint_error`.
- `attribution`, which is one of `failed-targets`, `observation`, `budget-expiry` or `engine-error`.
- `failed_targets` and `failed_hook_commands`, as lists that are empty when none were named.
- `observation_excerpt`, which is non-null only for `observation`.
- `configured_budget_seconds` and `engine_reported_elapsed`, both non-null only for `budget-expiry`.
- `events_read`, which is `read` or the reason the events could not be read.
- `terminal_patch_bytes` and `terminal_patch_sha256`.

Before the item's blocked transition, the Dispatcher MUST add one ledger comment to the item. The comment opens with the marker line `livespec-checkpoint-failure` and carries the run id, the factory name, the node, the engine's checkpoint error, the failed targets and failed hook commands, and, for a budget expiry, the configured budget and the engine's measurement. The comment MUST carry names and figures only, and never an excerpt of captured output. Every target and hook-command name in it MUST be identifier-shaped as §"Dispatch trace correlation" defines that term. A name that is not identifier-shaped MUST be left out, and the comment MUST state how many names were left out. The comment MUST pass the shared template-opener detector before it is written. A comment that fails the detector, or that cannot be written, MUST be journaled with its reason and MUST NOT prevent the blocked transition.

The run's work is preserved by reference through the existing preserve-by-reference pointer. A failed checkpoint leaves the node's uncommitted work outside every stage diff artifact, because the run's terminal `run.failed` event carries that work as its terminal patch. When that event carries a terminal patch, the journal row and the ledger comment MUST record the patch's byte size and sha256 digest, so that a pointer reporting no checkpointed diff artifact is not read as no work. When the event carries no terminal patch, both records MUST say so.

When the events cannot be read, the Dispatcher MUST still apply the disposition above. It MUST take the node and the error from the engine's failure message, record the reason in `events_read`, and MUST NOT invent a target, a hook command or a cause.

These obligations apply equally to member and adopter repositories. A hook runner or aggregate whose summary is not recognized falls back to the labelled observation. A workflow that skips git hooks at checkpoint produces no hook output, so its attribution is the engine error or the budget. This subsection changes no run reconciliation rule, no artifact retention rule and no other terminal outcome. Scenario 170 in `scenarios.md` exercises this section.


## Scenario 170 — A failed engine checkpoint commit names its node and cause and rests the item at needs-human

Governing clause: `contracts.md` §"Dispatcher admission, WIP cap, and post-merge acceptance" → "Failed engine checkpoint commit attribution".

```gherkin
Feature: attribute a failed engine checkpoint commit and route its decision to the ledger
  Scenario Outline: a hook refusal names the node, the failed hook command and every failed target
    Given a dispatched run ends workflow_error because the engine checkpoint commit of node <node> failed
      And the run's checkpoint.failed event carries an output tail with carriage-return line-feed line endings
      And that tail carries a structured Failed targets summary naming <targets>
      And the hook runner's summary marks hook command <hook> failed
      And recipe error lines outside the summary name other recipes
    When the Dispatcher reports the dispatch result
    Then the outcome is blocked at stage fabro-run
      And the outcome detail names the run, node <node>, the engine's checkpoint error, hook command <hook> and every one of <targets>
      And it does not attribute the failure to a recipe outside the summary
      And the checkpoint-failure journal row carries node <node>, attribution failed-targets, failed_hook_commands <hook> and failed_targets <targets>
      And the item rests blocked with blocked_reason needs-human and a needs-human-blocked journal row
      And a livespec-checkpoint-failure ledger comment on the item names the same node, hook command and targets
      And the dispatch reports exit code 4
    Examples:
      | node       | hook                | targets                                    |
      | implement  | 03-check-pre-commit | check-master-ci-green                      |
      | review_fix | 03-check-pre-commit | check-per-file-coverage and check-coverage |

  Scenario: a commit-msg refusal without a Failed targets summary names only the failed hook command
    Given a dispatched run's engine checkpoint commit of node fix failed with git commit failed (exit 1)
      And its checkpoint.failed tail has no Failed targets summary
      And the hook runner's summary marks hook command 01-red-green-replay failed
    When the Dispatcher reports the dispatch result
    Then the outcome detail and the checkpoint-failure journal row name node fix and hook command 01-red-green-replay
      And failed_targets is empty
      And the item rests blocked with blocked_reason needs-human

  Scenario: a tail with no recognized summary is labelled as an observation
    Given a dispatched run's engine checkpoint commit failed with git commit failed (exit 1)
      And its checkpoint.failed tail carries neither a Failed targets summary nor a recognized hook runner summary
    When the Dispatcher reports the dispatch result
    Then the checkpoint-failure journal row has attribution observation and a bounded observation_excerpt
      And the outcome detail labels the excerpt as an observation
      And it does not claim any hook, target or recipe in the excerpt caused the failure
      And the ledger comment carries no excerpt of the captured output

  Scenario: a checkpoint budget expiry names the node, the configured budget and the engine's measurement
    Given the dispatch submitted a run configuration whose run.checkpoint commit_timeout is 15m
      And the run ends because the checkpoint operation budget was exceeded on node fix with git commit timed out after 900004ms
    When the Dispatcher reports the dispatch result
    Then the outcome detail and the checkpoint-failure journal row name node fix, the timed-out operation git commit, configured_budget_seconds 900 and engine_reported_elapsed 900004ms
      And the engine's figure is labelled as the engine's measurement, not as the configured budget
      And the checkpoint-failure journal row has attribution budget-expiry
      And the item rests blocked with blocked_reason needs-human

  Scenario: a git add failure with no output tail is attributed to the engine error alone
    Given a dispatched run's engine checkpoint of node dod_gate failed with git add failed
      And its checkpoint.failed event carries no output tail
    When the Dispatcher reports the dispatch result
    Then the checkpoint-failure journal row has attribution engine-error, node dod_gate and checkpoint_error git add failed
      And failed_targets and failed_hook_commands are empty
      And the item rests blocked with blocked_reason needs-human

  Scenario: the uncommitted work is recorded by reference
    Given a run ended on a failed engine checkpoint
      And its run.failed event carries a terminal patch
      And the run's export holds no stage diff artifact
    When the Dispatcher records the dispatch
    Then the checkpoint-failure journal row and the livespec-checkpoint-failure comment carry the terminal patch's byte size and sha256 digest
      And the preserve-by-reference pointer for the run is written as for any non-green run

  Scenario: unreadable events still produce the disposition without invented targets
    Given a run's terminal failure message reads git checkpoint commit failed for node implement: git commit failed (exit 1)
      And the run's events cannot be read from the dispatch's resolved factory
    When the Dispatcher reports the dispatch result
    Then the outcome is blocked and names node implement and the engine's checkpoint error
      And the checkpoint-failure journal row records events_read as the failure reason
      And failed_targets is empty and no cause is asserted
      And the item rests blocked with blocked_reason needs-human

  Scenario: an earlier classification keeps its route
    Given a run whose output carries the needs_human terminal's sentinel
    When the Dispatcher reports the dispatch result
    Then no checkpoint-failure journal row is written
      And the needs_human terminal's existing outcome stands
```
