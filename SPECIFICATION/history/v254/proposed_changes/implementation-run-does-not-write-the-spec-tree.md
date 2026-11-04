---
topic: implementation-run-does-not-write-the-spec-tree
author: claude-opus-5-5
created_at: 2026-10-25T01:19:44Z
---

## Proposal: An implementation run never writes the governed repository's spec tree, and publish_draft refuses one that did

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The paragraph "An agent stage's instructions and its publication boundary" gives the `implement`, `fix` and `review_fix` stages three rules. This proposal adds a fourth: those turns MUST NOT change any path under the governed repository's `<spec_root>`, because a spec change reaches the spec only through that repository's own propose-change and revise operations and their independent review. It also makes the rule mechanical: `publish_draft` MUST refuse to publish a run whose change touches `<spec_root>`, naming the paths, in the same way and at the same point at which it already refuses run-owned workflow files.

### Motivation

Work-item bd-ib-2x16 (feature, filed from livespec-overseer; R1 bd-ib-j6uvkj batch 14 routed it to this plan because it bears directly on the plan's own goal). Three confirmed instances in livespec-overseer epic overseer-xkrwm3: PR #996 (2026-08-16), an implementation-only item whose PR also rewrote spec.md, scenarios.md and contracts.md, caught and closed unmerged; run 01M05TF6PKT5H38FJMFWR8R8Z8, whose recovered diff created a fresh SPECIFICATION/history/v016/ unprompted; and PR #1030 (merged 2026-08-17), whose one pipeline cut SPECIFICATION/history/v017/ with a revision file carrying no ratification review at all. Revalidated against the current spec: no clause stops an implementation run from writing the spec tree, and nothing refuses its publication. The workflow already has the right shape for the remedy: `publish_draft` refuses a run whose change includes files under `.github/workflows/`, failing closed with a named reason before any push. The generalization target is the existing publication-boundary paragraph, which already lists what an agent turn in these stages MUST NOT do, so no new section is added. Measured 2026-10-25 against origin/master: no commit whose subject begins feat or fix has touched SPECIFICATION/ since 2026-09-01; every spec-tree commit in that window is a host-side chore(spec) or docs(spec) commit, so the rule breaks no existing factory flow. An independent review (gpt-6-luna) raised the drift run and the dod-gate prompt as possible conflicts; neither is one, because the drift run is a host-side step of the Dispatcher's reconcile pass, not an implement-kind run, and dod-gate.md only reads the spec tree to resolve references. The proposal now says so explicitly.

### Proposed Changes

Two edits, landing in one revision. No `## ` heading is added, renamed or removed; Scenario 202 is extended in place, so `tests/heading-coverage.json` is unchanged.

**1. `contracts.md`, the paragraph that begins "**An agent stage's instructions and its publication boundary.**".** Change "MUST state three rules" to "MUST state four rules", and insert, immediately before the paragraph's closing sentence "Scenario 202 in `scenarios.md` exercises this paragraph.":

```
Fourth, an agent turn in those stages MUST NOT create, change, rename or
delete any path under the governed repository's `<spec_root>`, where
`<spec_root>` is the `spec_root` value of its `.livespec.jsonc`,
including `<spec_root>/history/` and `<spec_root>/proposed_changes/`. A
change to the specification reaches the repository only through that
repository's own propose-change and revise operations and the
independent review they require, never as a by-product of an
implementation run, and an implementation whose Definition of Done
appears to need a spec change MUST end the turn through the needs-human
protocol naming that need rather than editing the spec. The rule is
enforced at publication: before it pushes, `publish_draft` MUST compute
the paths the run's own commits change, relative to the merge base of
its refreshed head with the default branch, so that a spec change that
arrived through the default branch is never counted, and, when any of them is
under `<spec_root>`, MUST refuse to publish, write a needs-human reason
that names every such path and the remedy (drop those changes and file
the spec change through propose-change), and fail closed before any push
or pull request, exactly as it refuses run-owned files under
`.github/workflows/`. The two refusals are independent, and a run that
changed paths of both kinds MUST have both named. The rule governs the
runs of an implement-kind workflow variant only. The spec-side
operations that write `<spec_root>` on the host — propose-change,
revise, critique, prune-history, the drift run of each Dispatcher
reconcile pass, which files spec-side proposed changes, and the
in-session `implement` skill's `capture-spec-drift` handoff — are not
factory runs and are unaffected. The repository's heading-coverage map
is not under `<spec_root>` and is unaffected.
```

**2. `scenarios.md`, `## Scenario 202`.** In the scenario "The stage prompts state the three rules", rename it "The stage prompts state the four rules" and extend its Then step with ", and that the turn never changes a path under the spec root". Add, after the scenario "An agent stage never pushes or publishes":

```gherkin
  Scenario: A run that changed the spec tree is not published
    Given an implement-kind run whose committed change includes a path under the governed repository's spec root
    When publish_draft prepares to publish it
    Then publish_draft pushes nothing and opens no pull request
    And the run ends at needs_human with a reason naming every spec-root path it changed
    And the reason names filing the spec change through propose-change as the remedy

  Scenario: A spec change that arrived through the default branch is not refused
    Given an implement-kind run whose own commits change no spec-root path
    And the default branch gained a ratified spec revision after the run started
    When publish_draft refreshes the run onto the default branch and prepares to publish
    Then no spec-root refusal applies

  Scenario: Spec-root and workflow refusals are reported separately
    Given an implement-kind run whose change includes a path under the spec root and a file under .github/workflows
    When publish_draft prepares to publish it
    Then publish_draft pushes nothing
    And its needs-human reason names the spec-root path and the workflow file, each under its own refusal

  Scenario: The host-side drift run still files proposed changes
    Given a Dispatcher reconcile pass whose drift run finds a merge adding behaviour the spec does not state
    When the drift run files its proposed change
    Then its proposed change is filed through the propose-change handoff
    And no publication refusal applies, because the drift run is not a factory run
```
