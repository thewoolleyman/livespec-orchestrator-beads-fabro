---
topic: drift-job-publishes-filed-proposals-through-a-pull-request
author: claude-opus-5-5
created_at: 2026-11-01T13:49:35Z
---

## Proposal: A drift-job run publishes its filed proposals through a pull request and never writes into the --repo working tree

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The drift run clause says a pass files each partial or unstated behaviour as a proposed change through the propose-change handoff, but it never says how that file reaches a commit. The implementation (`file_drift_proposal` in `commands/_drift_run_proposals.py`) writes it straight into the `--repo` working tree, which for this tenant is the primary checkout, and nothing commits it. This change amends the drift run bullet: a drift-job run MUST write in a fresh worktree of the fetched default branch and publish one pull request per run. A finding counts as filed only once that pull request exists. Open drift-run pull requests count toward the already-filed set and toward `dispatcher.drift_proposal_queue_cap`. It amends Scenario 207 in place and adds no heading.

### Motivation

Item bd-ib-mztpy7 ("The drift lane leaves its filed proposals as untracked files in the primary checkout, which nothing ever commits"), a bug held at the specification-change tier, under plan spec-implementation-lockstep (epic bd-ib-ax3rds), which owns this proposal and its revise. Measured 2026-10-24 to 2026-10-30: the then-reconcile-run drift lane left the primary checkout dirty with five untracked drift-*.md files, against the repository mutation protocol that the primary checkout stays clean. Its factory run 01M66V2ACN0K ended at implement_amendment_route because no ratified clause said how a machine-filed proposal is published. The defect is live again rather than latent: `dispatcher.py drift-run --repo <path>` is now the drift job's entry point (contracts.md, the drift run), and the metered drift batch this plan runs next would deposit its proposals into the primary checkout. `filed_finding_identities` and `open_drift_origin_proposals` read only the local tree, so a published but unmerged proposal would be invisible to dedupe and to the queue cap. Generalization target: the existing "The drift run." bullet of contracts.md and Scenario 207; this amends both and adds no new heading.

### Proposed Changes

In SPECIFICATION/contracts.md, in the "**The drift run.**" bullet under `#### capture-spec-drift`, immediately after the sentence

> The pass MUST NOT accept, modify or reject any proposal.

insert:

> A drift-job run MUST NOT write into the working tree of its `--repo` path. It MUST write the proposals it files in a fresh worktree of the default branch as fetched from the forge at the start of the run, commit them on one `spec/` branch, and publish them as ONE pull request per run, so a machine-filed proposal reaches the default branch only through that pull request's merge. A finding is filed only once that pull request exists: a run whose commit or publication fails MUST treat every finding it wrote as not filed, so the frontier MUST NOT advance past their merges. The already-filed finding identity set MUST include the proposals on every open drift-run pull request, beside the open and archived proposals of the fetched default branch, so a retried run MUST NOT file a second pull request for a finding whose pull request is open or merged. The open count that `dispatcher.drift_proposal_queue_cap` bounds MUST include the drift-origin proposals on open drift-run pull requests.

In SPECIFICATION/scenarios.md, in `## Scenario 207 — The drift run processes each merge behind a contiguous frontier and files proposals it never accepts`, replace the Then line of "Scenario: The pass never accepts a proposal"

    Then the proposal rests under proposed_changes for revise and the pass takes no decision on it

with

    Then the proposal rests under proposed_changes on the run's pull request for revise and the pass takes no decision on it

and append these two scenarios to the same gherkin block, after "Scenario: The drift-run subcommand is the drift job, and a dry run writes nothing":

    Scenario: A filed proposal reaches the default branch only through a pull request
      Given one default-branch merge after the frontier whose diff adds a behaviour the spec-stated judgement reports unstated
      When dispatcher.py drift-run runs against the repository's primary checkout
      Then one pull request on a spec branch carries the drift-origin proposal
      And git status --short in the primary checkout reports no file under SPECIFICATION/proposed_changes/

    Scenario: A retried run files no second pull request for an open or merged finding
      Given a drift-origin proposal whose pull request is open or merged under its finding identity
      When the drift job processes the merge again
      Then no second pull request is opened for that finding
      And the open drift-run pull request's proposals count toward dispatcher.drift_proposal_queue_cap

No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` MUST NOT need an edit; Scenario 207's existing coverage entry covers the amended scenario. Spec size: four sentences added to one bullet, one Then line amended, two scenarios added inside Scenario 207, no new H2 heading.
