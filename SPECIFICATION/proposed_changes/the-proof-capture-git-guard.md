---
topic: the-proof-capture-git-guard
author: claude-opus-5-5
created_at: 2026-11-10T22:07:20Z
---

## Proposal: The proof_capture git launcher refuses writes to the run's checkout and network remotes, and admits a scratch push to a local bare repository under the temporary directory

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Generalize the proof_capture paragraph under §"Self-contained plugin dispatch" so it states the git launcher's write rules, which the spec leaves unstated today. The rules are: refuse commit and push in the run's checkout and every route to it; let a scratch repository commit; let a scratch repository push only to a local filesystem path naming a repository under the system temporary directory; and refuse every other push with a LIVESPEC_PROOF_CAPTURE_READ_ONLY line. A matching scenario is added. This lets a factory_captured proof exercise a local git fixture with a scratch bare origin without weakening the read-only guarantee on the run's tree.

### Motivation

Work-item bd-ib-ffw4q3 (fabro checkpoint and merge commits reach master under rebase-merge) ended needs-human at proof_capture@1, run 01M73HR5VAFGCZH9WGG9BVS3FM, on 2026-11-10. All four of its factory_captured assertions need publish_draft run in a local git fixture with a scratch bare origin. The launcher at .claude-plugin/.fabro/workflows/implement-work-item/proof-capture-bin/git refuses git push in EVERY repository. Commit was already scoped to the run's checkout in bbc4df37b; push never was. The owning plan session (epic bd-ib-acrr56) decided, on legacy-coordinator-agent's recommendation, to narrow the guard rather than re-mode the assertions to host_captured. Filing bd-ib-7e6uzu classified it spec-change tier, because the spec does not state the launcher's push rules; this is its linked proposal, topic the-proof-capture-git-guard. Fleet scope: the launcher serves every tenant's proof_capture.

### Proposed Changes

In SPECIFICATION/contracts.md §"Self-contained plugin dispatch", in the **`proof_capture`.** paragraph, the sentence "It MUST NOT modify the tree; a capture that requires a code change is an implementation defect ..." keeps its meaning. Immediately after that paragraph, a new paragraph MUST be added that states how the node's git launcher enforces "MUST NOT modify the tree":

**The `proof_capture` git launcher.** The Dispatcher MUST put a git launcher ahead of `git` on the `proof_capture` node's PATH. The launcher MUST decide every `commit` and `push` from the full command line before Git parses it, so a refused write runs no repository hook.

- **Protected repository.** The protected repository is the run's checkout, named by `LIVESPEC_PROOF_CAPTURE_PROTECTED_CHECKOUT`. A repository is protected when Git resolves its common git directory to the protected checkout's. That covers the checkout itself, any linked worktree of it, and any `-C`, `--git-dir` or `GIT_DIR` route to either.
- **Protected writes.** The launcher MUST refuse `commit` and `push` in a protected repository. It MUST refuse both when either the protected checkout or the target repository cannot be resolved.
- **Scratch commit.** A scratch repository is one whose common git directory is not the protected checkout's. It MAY `commit`. Its own hooks run, because the launcher drops only the stage's private `core.hooksPath` override.
- **Scratch push.** A scratch repository MAY `push` only when the remote is a local filesystem path, after Git has resolved any remote name to its URL. The path MUST carry no URL scheme and no scp-style `host:path` form. With symlinks followed, it MUST resolve to a repository under the system temporary directory (`TMPDIR`, else `/tmp`) whose common git directory is not the protected checkout's. An admitted push drops only the same private `core.hooksPath` override.
- **Refused pushes.** The launcher MUST refuse every other `push`. That includes any remote carrying a URL scheme (`https://`, `ssh://`, `git://`, `file://`), any scp-style remote, any path outside the system temporary directory, any remote that does not resolve, and any `push` carrying `--receive-pack` or `--exec`.
- **Refusal output.** Every refusal MUST print a line beginning `LIVESPEC_PROOF_CAPTURE_READ_ONLY:` on stderr and exit non-zero.

A push the launcher admits writes only into a repository under the temporary directory. It modifies neither the run's tree nor anything published. So a `factory_captured` assertion whose surface is a local git fixture with a scratch bare origin MUST remain capturable, and the launcher MUST NOT be the reason such a capture ends at needs-human.

In SPECIFICATION/scenarios.md a new scenario MUST be added. The revise pass MAY renumber it to the next free number:

## Scenario 341 — proof_capture's git launcher refuses writes to the run's checkout and to network remotes, and lets a scratch repository push to a local bare repository under the temporary directory

```gherkin
Feature: proof_capture is read-only on the run's checkout but can exercise a local git fixture
  Scenario: A scratch repository pushes to a bare repository under the temporary directory
    Given the proof_capture git launcher with LIVESPEC_PROOF_CAPTURE_PROTECTED_CHECKOUT naming the run's checkout
    And a scratch repository and a bare repository both created under the system temporary directory
    When the launcher runs push from the scratch repository to the bare repository by path or by a configured remote name
    Then the pushed ref arrives in the bare repository
  Scenario: A push from the run's checkout is refused
    Given the same launcher
    When it runs push from the protected checkout, a linked worktree of it, or a -C or --git-dir route to either
    Then it prints a LIVESPEC_PROOF_CAPTURE_READ_ONLY line, exits non-zero, and the remote is unchanged
  Scenario: A push to a network remote or outside the temporary directory is refused
    Given a scratch repository under the system temporary directory
    When the launcher runs push to an https, ssh, git or file URL, an scp-style host:path remote, a path outside the temporary directory, or with --receive-pack or --exec
    Then it prints a LIVESPEC_PROOF_CAPTURE_READ_ONLY line and exits non-zero
```

Per this repository's revise co-edit discipline, the same revise pass MUST add a tests/heading-coverage.json entry for the new heading through resulting_files[]. Its test MAY be "TODO", with reason naming bd-ib-7e6uzu as the owning work-item.
