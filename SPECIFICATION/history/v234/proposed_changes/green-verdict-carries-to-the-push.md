---
topic: green-verdict-carries-to-the-push
author: claude-opus-5-5
created_at: 2026-10-26T22:59:57Z
---

## Proposal: A green aggregate on the exact tree carries to its push, even when the aggregate skipped declared targets

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

In 'Pre-push gate refinements': a passing just check aggregate records a green verdict keyed on the tree even when it skipped declared targets (naming them), the pre-push gate honours it for a byte-identical tree and prints what it excluded, and a push of any other tree runs the full gate.

### Motivation

Routed by petri-factory-on-gmktec under coordinator ruling R69 (throughput, R67 ratification), spec-first for work-item bd-ib-n4twqd, whose Codex-first Definition-of-Done screen found that its cited "## Self-contained plugin dispatch" does not govern its assertions; Codex named "## Pre-push gate refinements" as the home. dev-tooling/just-check.sh writes the green token only when no target was skipped. In the factory sandbox the janitor skips targets that cannot run there (for example check-master-ci-green), so it writes no token, and publish_draft's pre-push (dev-tooling/just-check-pre-push.sh, which begins with the green-token check) re-runs the whole aggregate on the tree the janitor passed minutes earlier; measured on gmktec on 2026-10-26 at about 24 minutes per pass at two test workers. Prior art bd-ib-zxqf7g (closed 2026-10-16) measured the token skip working (run 01M52B4W32MABC3V0047XQGSX9, hook 0.27 s) and established that publish_draft's own refresh legitimately changes the tree and must run the full gate; this clause keeps that case. The existing green token keys on the HEAD tree id with a clean worktree and re-runs members that read state outside the tree, which "the aggregate members that verdict covers" preserves.
The first read-only Codex review raised blockers that are folded in here.

### Proposed Changes

1. In `SPECIFICATION/constraints.md`, §"Pre-push gate refinements", after the paragraph "**A deletion-only push skips the pre-push aggregate.**", insert immediately after the text

```
Scenario 188 in `scenarios.md` exercises this section.
```

the following new paragraph (separated by one blank line):

```
**A green aggregate on the exact tree carries to its push.** When the `just check` aggregate passes, it MUST record a green verdict for the tree it checked, keyed on that commit's tree object id, even when it skipped declared targets. A verdict whose aggregate skipped targets MUST name them. A verdict vouches only for the targets that ran and passed and whose result the committed tree alone decides, the tree-pure members; a member that reads state outside the tree is never covered by a verdict. The pre-push gate MUST honour a recorded green verdict whose tree is byte-identical to the tree being pushed, with a clean worktree, in place of running again the members that verdict covers, MUST still run every member of the pre-push check set that reads state outside the tree and refuse the push when one fails, and MUST print one line naming the honoured verdict and every target the verdict skipped. A push whose tree differs from the recorded verdict's tree, such as a `publish_draft` push after its own refresh rebase onto a moved default branch, MUST run the full pre-push gate exactly as before. Like the deletion-only skip, honouring a verdict MUST NOT be reachable by `--no-verify`, by an environment variable or by any flag; the recorded verdict and the tree are its only inputs. Measured 2026-10-26: the factory janitor skips targets that cannot run in the sandbox, so it recorded no verdict, and each `publish_draft` pre-push re-ran the whole aggregate, about 24 minutes at two test workers, on the tree the janitor had just passed. Scenario 253 in `scenarios.md` exercises this paragraph.
```

2. In `SPECIFICATION/scenarios.md`, append:

````
## Scenario 253 — A green aggregate on a tree carries to a push of the same tree, and a push of any other tree runs the gate

```gherkin
Feature: A push of a tree the aggregate just passed does not run the aggregate again
  As the operator of a factory
  I want publish_draft to reuse the janitor's green verdict on the same tree
  So that a run does not pay a second full check aggregate for bytes already checked

  Scenario: A janitor pass that skipped targets carries to a push of the same tree
    Given the just check aggregate passed on a tree while skipping a declared target
    When publish_draft pushes a commit whose tree is byte-identical to that tree with a clean worktree
    Then the pre-push gate honours the recorded green verdict and does not run the tree-pure members again
    And it prints one line naming the honoured verdict and the skipped target

  Scenario: A member that reads outside the tree still runs on a byte-identical push
    Given the just check aggregate passed on a tree and recorded a green verdict
    And state outside the tree that a pre-push member reads has since changed so that member now fails
    When a commit whose tree is byte-identical to that tree is pushed with a clean worktree
    Then the pre-push gate runs that member and refuses the push

  Scenario: A push of a different tree runs the full gate
    Given the just check aggregate passed on a tree
    When publish_draft refreshes onto a moved default branch and pushes a commit whose tree differs
    Then the pre-push gate runs the full pre-push gate

  Scenario: No flag or variable reaches the verdict skip
    Given no recorded green verdict for the tree being pushed
    When a push sets an environment variable or passes a flag
    Then the pre-push gate runs the full pre-push gate
```
````

3. Add a TODO row for the new heading to `tests/heading-coverage.json` and a matching debt row to `tests/heading-coverage-debt.json`, both owned by the implementing work-item bd-ib-n4twqd.
