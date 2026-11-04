---
topic: implement-gate-preview-and-mechanical-budget
author: claude-opus-5-5
created_at: 2026-11-03T15:06:22Z
---

## Proposal: An implement turn previews its commit gate before it ends, and a purely mechanical refusal has its own re-entry budget

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add two paragraphs to contracts.md after 'An implement turn that ends incomplete does not succeed.': (a) the red and green prompts direct the agent to run a Dispatcher-materialized gate preview, which runs the commit hooks' checks over exactly the paths the commit node would stage without committing, and to fix what it refuses before the turn ends; (b) a repository-declared set of mechanical hook targets gives a commit_red or commit_green refusal naming only those targets its own re-entry budget, separate from the ordinary re-entry that max_visits bounds. Add four scenarios inside Scenario 285's gherkin block.

### Motivation

Maintainer ruling recorded on livespec-dev-tooling-6tgd2z at 15:00:49Z 2026-11-03, relayed by legacy-coordinator-agent and assigned to plan sandbox-commit-gate-ceiling (epic bd-ib-qy5wol), which owns the sandbox commit gate: 'Make a plan for both of these ... do them asap, they are a big lever.' Evidence the same day: crxcy4 (run 01M6GVFTX08S, failed targets check-keyword-only-args and check-per-file-coverage), d2qm5d (run 01M6GQFBQTTJ) and jzwgjw each ended at LIVESPEC_IMPLEMENT_HOOK_REFUSED_BUDGET_EXHAUSTED at the very end of a full 1 to 2 h run. Earlier measurement (scope event 2026-11-02T13:19Z on bd-ib-qy5wol): with a single re-entry and a hook of about 15 minutes a run gets about 3 to 5 hook verdicts in total, and the refusals were genuine gate failures (coverage, types, lint, trailer shape), not timeouts. Today an implement turn first learns the gate's verdict when the commit node runs the hook after the turn has ended, and a refusal that is purely mechanical spends the same single re-entry as a substantive one.

### Proposed Changes

Three edits. Every other sentence of the edited sections is unchanged.

**1. `SPECIFICATION/contracts.md`, §"Definition-of-Done and Proof-of-Done stages".** Insert this paragraph immediately after the paragraph that begins "**An implement turn that ends incomplete does not succeed.**" and before the paragraph that begins "**An implement turn that reports completion with no diff ends as already satisfied.**":

> **An implement turn sees its commit gate's verdict before it ends.** The `red` and `green` prompts MUST direct the agent, before it ends its turn, to run the gate preview over the changes its turn leaves, to fix every failed target the preview names that the turn can fix within its own scope, and to run the preview again after each fix. The gate preview is a program the Dispatcher materializes into the sandbox beside the commit runner. It MUST run the same checks the repository's commit hooks would run when the turn's commit node commits, over exactly the paths that commit node would stage, and MUST NOT create a commit, move `HEAD` or change the index the commit node will read. It MUST report its exit status and the failed target names, read from the checks' own output. It MUST NOT pass `--no-verify`, set any variable that skips or relaxes a check, or change the severity of any check. A preview run MUST NOT count as a commit attempt and MUST NOT consume any re-entry budget. Each `red` and `green` handoff section MUST record the exit status and failed target names of the turn's last preview run, or state that the turn ran no preview and why. When the preview program is absent from the sandbox, the turn MUST state that in its handoff section and end its turn as it otherwise would; the commit node's own hook run stays the only verdict that decides a commit. Scenario 285 in `scenarios.md` exercises this paragraph.

**2. `SPECIFICATION/contracts.md`, same section.** Insert this paragraph immediately after the paragraph inserted by edit 1:

> **A purely mechanical commit refusal has its own re-entry budget.** A repository MAY declare `dispatcher.implement.mechanical_targets`, a list of commit-hook target names whose failures an implement turn can repair mechanically, such as lint, formatting, keyword-only-argument, file-size and per-file-coverage targets, and `dispatcher.implement.mechanical_reentries`, a non-negative integer that defaults to 2 when the list is declared and to 0 when it is not. When `commit_red` or `commit_green` refuses and every failed target name its recorded hook output reports belongs to the declared list, the run MUST re-enter that node's ACP node without spending the re-entry that its `max_visits` bounds, while mechanical re-entries remain for that node in the run. A refusal that names any target outside the list, or whose recorded output names no failed target, MUST spend the ordinary re-entry exactly as before. The handoff section of a commit node whose refusal took a mechanical re-entry MUST say so and MUST name the failed targets and the mechanical re-entries remaining. When the mechanical re-entries are spent, a further purely mechanical refusal MUST spend the ordinary re-entry, and when that is also spent the stage MUST end with a failed outcome whose cause names both budgets as exhausted. The engine visit bound the workflow declares for each re-entered node MUST admit both budgets, so that neither budget is cut short by that bound. Scenario 285 in `scenarios.md` exercises this paragraph.

**3. `SPECIFICATION/scenarios.md`, `## Scenario 285 — Red and Green run as separate nodes and every implement commit is made by a command node`.** Insert these four scenarios inside the existing gherkin fence, immediately after the "Scenario: An exhausted test-wrong route ends the stage failed with both sides' sections" block and before the closing fence. No `## ` heading is added or changed, so `tests/heading-coverage.json` needs no edit.

```gherkin
  Scenario: A green turn repairs what its gate preview refuses before it ends
    Given a green turn whose change fails the repository's check-keyword-only-args target
    When the turn runs the gate preview before ending
    Then the preview names check-keyword-only-args as failed and creates no commit
    When the turn fixes the change and runs the preview again
    Then the preview passes and the turn's handoff section records that last preview run
    And no re-entry budget was spent on either preview run

  Scenario: A purely mechanical Green refusal re-enters green without spending its ordinary re-entry
    Given a repository that declares check-lint and check-per-file-coverage as mechanical targets
    And commit_green's hook refuses naming only check-per-file-coverage
    When the run routes the refusal
    Then the run re-enters green with one fewer mechanical re-entry remaining
    And the green node's ordinary re-entry is unspent
    And commit_green's handoff section names the refusal as mechanical and names check-per-file-coverage

  Scenario: A refusal naming a substantive target spends the ordinary re-entry
    Given a repository that declares check-lint as a mechanical target
    And commit_green's hook refuses naming check-lint and check-types
    When the run routes the refusal
    Then the run re-enters green spending its ordinary re-entry
    And no mechanical re-entry is spent

  Scenario: Spent mechanical and ordinary re-entries end the stage failed naming both budgets
    Given a repository that declares check-lint as a mechanical target with one mechanical re-entry
    And green has spent its mechanical re-entry and its ordinary re-entry
    When commit_green's hook refuses naming only check-lint
    Then the implement stage's outcome is failed
    And the needs-human cause names both the mechanical and the ordinary re-entry budgets as exhausted
```

