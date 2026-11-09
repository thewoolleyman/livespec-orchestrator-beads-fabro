---
topic: a-sandbox-runs-tools-from-a-pinned-clone-and-works-in-the-latest
author: claude-opus-5-5
created_at: 2026-11-09T09:16:21Z
---

## Proposal: A factory sandbox runs its tools from pinned clones and does its work in the latest clones

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A factory sandbox today executes cross-repository tooling (for example livespec core's doctor checker) out of the same sibling clones it works in: /livespec-siblings holds each sibling's default-branch tip as of the run's prepare step, frozen for the run. The checker's version is therefore uncontrolled and can differ from the version CI runs for the same tree. This proposal splits the sandbox's clones into two kinds. RUN-FROM clones carry every tool the sandbox executes: separate, shallow, read-only, and checked out at the release the governed tree under test declares, which is the version CI runs, re-resolved when the janitor refreshes the tree. WORK clones (the target repository and /livespec-siblings) stay at the latest default branch, writable, with enough history for archaeology and debugging. It adds one paragraph to contracts.md §"Self-contained plugin dispatch" and one scenario.

### Motivation

Maintainer ruling (human:thewoolleyman, 2026-11-09 ~09:15Z, recorded as a scope event on plan epic bd-ib-nmuyjc at 09:13:18Z), verbatim: "Clearly the fix is to always RUN everything from a separate clone (shallow, pinned, read-only, etc), pinned at the known good latest version, and do WORK from the latest clone:non-shallow or at least deep enough to do proper archeology and debugging, writeable ( I assume)". Incident: on 2026-11-08, factory run 01M6Y1Q7ZFWZ (bd-ib-bacahf) failed check-doctor-static at fix@1 (22:15:04Z) with a RecursionError in livespec's out_of_band_edits._probe_v_dirs. Its pod (created 17:02:49Z) had cloned the livespec sibling at a 0.47.0-era tip. The fix shipped in livespec v0.47.1 at 19:47:54Z. This repository bumped its pin to v0.47.1 in f71217d51 (20:21:56Z), and the tree the run had refreshed onto, 94d98b696, already contains that bump. CI on that tree checks livespec out at .livespec.jsonc compat.pinned (ci.yml's doctor-static job, the separate .livespec-core checkout) and passes. The root problem is that the sandbox's checker version was set by when the pod started, not by the tree under test, so it differed from CI's checker for the same tree. A pin alone would not have saved that run: its run-start tree pinned v0.45.1. Re-resolving the run-from clone from the refreshed tree would have. Work clones are deliberately left at the latest default branch: cross-repository reads such as livespec's wiring-completeness-cross-repo check compare against a sibling's CURRENT state, and an agent needs history to debug. bd-ib-rzkhqv (re-take /livespec-siblings at the janitor refresh) stays valid for the work clones. This supersedes the 'Option (a)' recorded on bd-ib-rzkhqv, which would have pinned /livespec-siblings in place. In-flight survey: two pending proposals edit OTHER paragraphs of the same section (a-review-fix-turn-grades-each-tree-once, orchestrator-currency-surfaces-push-agents). The relationship to both is align, because this proposal adds an independent paragraph.

### Proposed Changes

In SPECIFICATION/contracts.md §"Self-contained plugin dispatch", insert this paragraph immediately after the paragraph headed **Default-branch resolution.** (before the `### Definition-of-Done and Proof-of-Done stages` sub-heading):

> **A sandbox runs its tools from pinned clones and works in the latest clones.** A factory sandbox MUST hold two kinds of clone of other repositories, and it MUST NOT use one kind for the other's purpose.
>
> - *Run-from clones.* Every tool the sandbox EXECUTES that comes from a repository other than the target (for example livespec core's checker, resolved through `LIVESPEC_CORE_PLUGIN_ROOT`) MUST run from a run-from clone of that repository. A run-from clone MUST be separate from every work clone. It MUST be checked out at the release the governed tree under test declares for that repository (for livespec core, `.livespec.jsonc` `compat.pinned`), which is the same release the repository's CI runs for that tree. It MUST be shallow, and it MUST be read-only to the run's agent and gate processes. Where the governed tree declares no release for that repository, the run-from clone MUST be taken at that repository's newest release tag, never at its default-branch tip. When the janitor refreshes the run's tree, the Dispatcher MUST re-resolve each run-from clone's release from the refreshed tree's declaration and MUST re-clone any whose declared release changed, before the refreshed tree is checked. A tool MUST NOT execute from a work clone.
> - *Work clones.* The target repository's clone and the sibling clones under `/livespec-siblings`, which the run reads for cross-repository state and the agent reads and edits, MUST be taken at the default branch's latest commit at the moment they are cloned. They MUST be writable, and MUST carry enough history for archaeology and debugging: non-shallow, or a depth the repository declares sufficient. A cross-repository conformance read, such as livespec's `wiring-completeness-cross-repo`, MUST read the work clones.
>
> Scenario NNN in `scenarios.md` exercises this paragraph.

In SPECIFICATION/scenarios.md, add a new H2 at the end of the file, numbered with the next free scenario number at revise time (NNN above is that number), with a matching tests/heading-coverage.json row (test "TODO", reason naming plan epic bd-ib-nmuyjc):

## Scenario NNN — A sandbox checks a tree with the tooling release that tree pins, and works in the latest clones

Governing clause: contracts.md §"Self-contained plugin dispatch", paragraph "A sandbox runs its tools from pinned clones and works in the latest clones."

```gherkin
Feature: A sandbox checks a tree with the tooling release that tree pins, and works in the latest clones

  Scenario: An executed tool runs from a pinned, shallow, read-only clone
    Given a governed tree whose .livespec.jsonc compat.pinned names livespec release vA
    And livespec's default branch is ahead of vA
    When a factory run executes livespec core's doctor checks
    Then the checks run from a run-from clone of livespec checked out at vA
    And that clone is shallow
    And a write into that clone by the run's agent or gate processes fails
    And LIVESPEC_CORE_PLUGIN_ROOT does not resolve under /livespec-siblings

  Scenario: A janitor refresh re-resolves the run-from clone from the refreshed tree
    Given a factory run whose run-from clone of livespec is at vA, the release its run-start tree pins
    When the janitor refreshes the run onto a default branch whose .livespec.jsonc compat.pinned names vB
    Then the next doctor check of the refreshed tree runs from a run-from clone of livespec at vB

  Scenario: A repository with no declared release runs from its newest release tag
    Given a factory run that executes a tool from a repository the governed tree declares no release for
    When the sandbox takes that repository's run-from clone
    Then the clone is checked out at that repository's newest release tag, not its default-branch tip

  Scenario: Work clones are the latest, writable and deep enough to debug
    Given a factory run
    When the sandbox takes the target repository's clone and the sibling clones under /livespec-siblings
    Then each is at its default branch's latest commit at the moment it was cloned
    And each is writable by the run's agent
    And each is non-shallow or carries the depth its repository declares sufficient
    And livespec's wiring-completeness-cross-repo check reads the sibling clones under /livespec-siblings
```
