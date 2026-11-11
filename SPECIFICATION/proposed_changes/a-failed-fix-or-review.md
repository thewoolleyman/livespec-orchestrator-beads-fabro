---
topic: a-failed-fix-or-review
author: claude-opus-5-5 (sandbox-commit-gate-ceiling plan session)
created_at: 2026-11-11T11:34:20Z
---

## Proposal: A failed commit run settled by a fix or review_fix settle is recorded with its cause and handed to the re-entered turn

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add one contracts.md paragraph under '## ACP node timeouts', directly after 'A commit leg completes past one tool call.', and two Gherkin scenarios inside the existing '## Scenario 179 — A sandbox commit whose hook outlasts one tool call completes with the hook's own verdict'. When fix_commit_settle or review_fix_commit_settle settles a commit run as failed, the node's own recorded output MUST state that run's cause: the run id, the exit status, the failed target names or 'failed targets: none', whether the hook ran or passed, Git's recorded refusal line when the hook passed, and the final lines of the run's own recorded output. When review_fix_open_red_route or fix_open_red_route re-enters the stage after such a settle, the re-entry brief MUST carry the same failed targets and final lines. No new H2 heading is added, so tests/heading-coverage.json is unchanged. This gives work-item bd-ib-wotls4 the clause and scenario its Definition of Done references.

### Motivation

A failing open-Red Green amend currently leaves no observable cause. Measured 2026-11-11 on livespec-dev-tooling-4zjjx4, run 01M74ZKKRG5E (orchestrator v0.317.0): review_fix_commit_settle@2 and @3 recorded only '{"settled": [{"run_id": "commit-84ae0322...", "state": "failed"}]}' and the same for commit-1815c0a2, and the run ended REVIEW_FIX_OPEN_RED_VISIT_BOUND_EXHAUSTED. livespec-dev-tooling-5lhafp, run 01M740ZWBG48 (v0.315.1), ended the same way. In both runs the agents had already restored the open Red by hand, so engine checkpoints above the Red (bd-ib-gisyvv) were not the cause, and what did fail the amends cannot be determined from the run record.

The commit runner already composes the cause. Its settle writes the failed targets, exit status, hook state, Git's refusal line and the tail of the run's own output into the stage's live-commit brief file inside the sandbox. But neither settle node prints that brief, so it never reaches the run record and is lost with the sandbox. review_fix_open_red_route then writes its own open-Red brief without it, so the re-entered agent is not told why its amend failed. implement_hook_route already surfaces the same brief for the implement stage. Today's contract states what a terminal report carries ('A terminal report MUST carry the exit status ... and the final lines of the commit's combined output') but not that a settle node records it. legacy-coordinator-agent ruled at 11:36Z on 2026-11-11 that this be fixed ('a cause that cannot be observed cannot be fixed'). The settle code runs in every factory member repository.

### Proposed Changes

1. contracts.md, under '## ACP node timeouts', insert this paragraph immediately after the paragraph that begins '**A commit leg completes past one tool call.**':

**A settled failed commit run is recorded with its cause.** When the `fix_commit_settle` or `review_fix_commit_settle` node settles a commit run whose terminal state is `failed`, that node's own recorded output MUST state, for that commit run: its identity; its recorded exit status; the failed target names the hook's recorded output reports, or the literal `failed targets: none` when it reports none; whether the repository commit hook ran, and whether it passed; Git's recorded refusal line when the hook passed and Git then refused the commit; and the final lines of the commit run's own recorded output. All of these MUST be read from the records the commit run's own process wrote, never from the agent's account. The node MUST state them in its output before any line that routes the stage onward, so the run's exported record carries them after the sandbox is gone. When `fix_open_red_route` or `review_fix_open_red_route` re-enters its stage after its settle reported a `failed` commit run, the re-entry brief MUST carry that commit run's failed target names, or `failed targets: none`, and the same final lines, so the re-entered turn is told why its commit failed. A settled run whose state is `passed`, `no-verdict` or `running` is reported as before. This paragraph changes no commit run's state and no route the settle takes. Scenario 179 in `scenarios.md` exercises it.

2. scenarios.md, inside '## Scenario 179 — A sandbox commit whose hook outlasts one tool call completes with the hook's own verdict', append these two scenarios to its gherkin block, after 'Scenario: A second commit does not start while one is running':

```gherkin
  Scenario: A settled failed Green amend names its cause in the settle node's output
    Given a review_fix-stage agent whose Green amend through the sandbox commit runner is refused by a commit hook that names the failed target check-types
    And the agent ended its turn while that commit run was still running
    When the review_fix_commit_settle node settles that commit run as failed
    Then the node's recorded output names the commit run's identity and its recorded exit status
    And it names the failed target check-types and states that the hook ran and did not pass
    And it carries the final lines of that commit run's own recorded output
    And those lines are read from the commit run's own records, not from the agent's reply

  Scenario: A re-entered review_fix turn is told why its Green amend failed
    Given a review_fix_commit_settle node that settled a Green amend as failed, naming the failed target check-types
    And the last authored commit is still an open Red
    When review_fix_open_red_route re-enters review_fix
    Then the re-entered turn's open-Red brief names the failed target check-types
    And it carries the final lines of that commit run's own recorded output
```

No H2 heading is added or removed, so tests/heading-coverage.json is unchanged.
