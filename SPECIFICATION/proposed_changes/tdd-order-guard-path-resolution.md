---
topic: tdd-order-guard-path-resolution
author: claude-opus-5-5 (sandbox-commit-gate-ceiling plan session)
created_at: 2026-11-11T04:13:07Z
---

## Proposal: The test-first order guard judges each write against the repository it lands in

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a contracts.md H2, 'Test-first order guard write-target resolution', and Scenarios 345 and 346. The guard MUST resolve every write target to an absolute path: a relative shell target resolves against the reported working directory as changed by any preceding cd in the same command. It MUST judge the target against the git repository whose working tree contains it, whether the session repository, a linked worktree or a separate clone, and MUST NOT refuse a write that lands in no repository. A relative write with no cd keeps today's session-repository decision, and an unresolvable cd falls back to the session repository (fail-closed). This gives bd-ib-zharek's Definition of Done a heading to reference and ends the false refusals measured on 2026-10-18 and 2026-11-11.

### Motivation

The repository's test-first order guard (`.claude/hooks/livespec_tdd_order_guard.py`) is unspecified: no H2 heading of `SPECIFICATION/` governs it (searched 2026-11-11 for 'order guard', 'test-first' and 'PreToolUse' headings). As a result, work-item bd-ib-zharek, the measured fix for its path-resolution defect, has rested at pending-approval since 2026-10-18 behind a mechanical Definition-of-Done finding: its References line names no H2 heading. legacy-coordinator-agent ruled on 2026-11-11 that the sandbox-commit-gate-ceiling plan seat files this proposal so that zharek has a heading to reference.

The defect: the guard resolves a relative write target against the session repository (`CLAUDE_PROJECT_DIR`), never against the directory a `cd` earlier in the command moved to, so it judges a write in another repository by the session repository's HEAD.

Measured instances:
1. 2026-10-18, livespec-driver-claude-cb2mzo (PR 845): with an open Red at a linked worktree's HEAD, a `cd <worktree> && ...` relative product write was refused with 'HEAD state: no-trailers'. The same write by absolute path passed.
2. 2026-11-11, bd-ib-fde4ie run 01M741D6MJP278H3Y5HQ1RSN4T on petri: proof_capture changed into a scratch clone under $TMPDIR and created `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/proof_widget.py` by a relative path. The guard refused it (stub-without-pending-test, HEAD no-trailers) against /workspace, refused it again after the agent wrote the test first in the clone, and the run ended at needs_human. Reproduced on the dev host the same day by feeding the real guard both forms: the relative form after cd is refused, and the absolute form is allowed.

Scope: this governs the repository-local guard only, which is repository-local enforcement and not plugin-distributed (see `.claude/hooks/CLAUDE.md`). It changes no decision table: open Red, new-module carve-out and unmerged-path admission are untouched. It changes only which repository's state feeds that table.

### Proposed Changes

Add one new H2 to `contracts.md`, immediately before `## ACP turn stop reasons are recorded`, carrying exactly this paragraph (the heading text is load-bearing: work-item bd-ib-zharek's Definition of Done will name it in its References line):

## Test-first order guard write-target resolution

**The test-first order guard judges each write against the repository the write lands in.** This repository commits a PreToolUse hook, `.claude/hooks/livespec_tdd_order_guard.py`, registered in `.claude/settings.json` on `Write`, `Edit`, `MultiEdit` and `Bash`, that refuses an out-of-order write to a product path. In this paragraph the *session repository* is the repository whose root the hook's `CLAUDE_PROJECT_DIR` names, falling back to the repository containing the hook process's working directory when that variable is unset. A *product path* of a repository is a path ending in `.py` that begins with a source prefix that repository's configuration declares, lies outside its `tests/` tree and is not vendored; this is the same classification the `red_green_replay` commit-msg hook applies to its implementation bucket. Before it decides, the guard MUST resolve every write target it extracts to an absolute path. A structured tool's `file_path` and an absolute shell write target resolve as given. A relative shell write target resolves against the directory the command's shell is in when that segment runs: the working directory the hook payload reports, as changed by every `cd` segment that precedes the write in the same command. The guard MUST then judge the resolved path against the git repository whose working tree contains it, reading that repository's HEAD commit message, the path's existence at that HEAD, that repository's uncommitted test changes, its in-progress merge, rebase or cherry-pick state, and the product-path prefixes that repository's own configuration declares. This holds whether that repository is the session repository, a linked worktree of it, or a separate clone. A resolved path that lies in no git repository's working tree is not a product path, and the guard MUST NOT refuse a write to it. A relative write target in a command that changes directory nowhere, issued while the reported working directory is in the session repository, MUST be judged against the session repository with the same allow or refuse decision the guard returned before this paragraph was ratified. When the guard cannot determine the directory a `cd` segment moves to, such as a target computed by command substitution or naming a variable absent from the hook's own environment, it MUST judge every later relative write target in that command against the session repository; that is the fail-closed reading. A refusal message MUST name the repository root the write was judged against. Scenarios 345 and 346 in `scenarios.md` exercise this paragraph.

Append two scenarios to `scenarios.md`, after the highest ratified scenario at revise time, numbered 345 and 346 (the highest number reserved by any pending proposal or unlanded `spec/*` branch at filing was 344):

## Scenario 345 — A write after a cd into another repository is judged against that repository

```gherkin
Feature: The test-first order guard judges a write against the repository it lands in
  As an agent working in a linked worktree or a scratch clone during a factory run
  I want the test-first order guard to read the repository my write actually lands in
  So that a write that repository's own test-first state permits is not refused by the session repository's state

  Scenario: A cd into a linked worktree judges the write by that worktree's HEAD
    Given a linked worktree of the session repository whose HEAD is an open Red commit
    And the session repository's own HEAD carries no Red trailer
    When an agent's Bash command changes directory into that worktree and then writes an existing product path given relative to it
    Then the test-first order guard allows the write

  Scenario: A cd into a separate clone judges a new module by that clone's pending test
    Given a separate clone outside the session repository whose HEAD carries no Red trailer
    And that clone has an uncommitted test change and does not yet contain a product module M
    And the session repository has no uncommitted test change
    When an agent's Bash command changes directory into that clone and then creates M by a relative path
    Then the test-first order guard allows the write

  Scenario: An absolute write into a separate clone is judged by that clone
    Given a separate clone outside the session repository whose HEAD carries no Red trailer and which has no uncommitted test change
    When an agent's Bash command writes an existing product path of that clone by its absolute path
    Then the test-first order guard refuses the write
    And the refusal names that clone's root as the repository it judged

  Scenario: A write that lands in no repository is not refused
    Given a directory in no git repository's working tree
    When an agent's Bash command changes directory into it and writes a .py path whose relative form begins with a product-path prefix of the session repository
    Then the test-first order guard allows the write
```

## Scenario 346 — A relative write with no cd is judged against the session repository

```gherkin
Feature: The test-first order guard keeps judging an in-place relative write against the session repository
  As the maintainer of this repository's test-first discipline
  I want a relative write that changes no directory to be judged exactly as before
  So that resolving writes by repository widens no permission inside the session repository

  Scenario: A relative write without a cd keeps the session repository's decision
    Given the working directory the hook payload reports is in the session repository
    When an agent's Bash command writes a product path given relative to that directory without changing directory
    Then the test-first order guard judges the write against the session repository
    And it returns the same allow or refuse decision it returned before Scenario 345 was ratified

  Scenario: A cd the guard cannot resolve falls back to the session repository
    Given the session repository's HEAD carries no Red trailer
    When an agent's Bash command changes directory to a target computed by command substitution and then writes an existing product path of the session repository by a relative path
    Then the test-first order guard refuses the write
    And the refusal names the session repository's root as the repository it judged
```

The same revise MUST add three entries to `tests/heading-coverage.json`, one per new H2 (`## Test-first order guard write-target resolution` in `contracts.md`, and the two scenario headings in `scenarios.md`). Each MUST carry `test: "TODO"`, `work_item: "bd-ib-zharek"`, and a `reason` stating that bd-ib-zharek owes an exercising test that drives `.claude/hooks/livespec_tdd_order_guard.py` with a Bash payload against a linked worktree, a separate clone and a non-repository directory.

This proposal deliberately makes one behaviour change beyond relative paths, and the reviser SHOULD weigh it explicitly. Today an ABSOLUTE write target outside the session repository is never judged: `livespec_tdd_order_policy.relative_path` returns it unchanged, so it fails the product-prefix test. Under this paragraph an absolute target inside a separate clone is judged by that clone, as the third scenario of Scenario 345 states. Without this, a relative write and an absolute write to the same file in the same clone would receive different verdicts. The `MAY`-level alternative, judging only the session repository and its linked worktrees and leaving every other repository unjudged, was considered and not proposed: it would also stop judging a relative write after a cd into a separate clone, where the coordinator's routing asks for that clone to be judged.

