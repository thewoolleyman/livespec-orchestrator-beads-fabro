---
topic: a-fleet-launcher-honours-a
author: claude-sonnet-5-5
created_at: 2026-11-04T08:09:32Z
---

## Proposal: a-fleet-launcher-honours-a

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A fleet-launch launcher honours a named per-item exemption in a repository hold file, so a master-red restoration fix can launch while the hold keeps every other item of that repository held.

### Motivation

On 2026-11-04 the master-red restoration fix bd-ib-ohuuy7 had to launch past hold-repo-livespec-orchestrator-beads-fabro. The launcher had no per-item exemption, so the hold file was moved aside from 06:11:56Z to 06:15:34Z and restored when ohuuy7 logged LAUNCH, opening a window in which every item of the repository could launch. The §"Provisional fleet launch scripts" clause says an impl or resume launcher MUST hold while the hold file exists. That covers a hold file naming no exempt item, but it says nothing about a hold file that names an exempt work-item id, launching that one item while the hold is set, or every other item staying held and keeping its queue place. Linked work item: bd-ib-aibd3u.

### Proposed Changes

In SPECIFICATION/contracts.md §"Provisional fleet launch scripts", after the paragraph that ends "...a launcher MUST NOT add any ordering rule beside the FIFO ticket..." and before the launch-time preflight paragraph, add this paragraph:

"A repository hold file MAY name exempt work-item ids, each on a line of its own that begins with `exempt:` followed by the work-item id. A `fleet-launch/` launcher, impl or resume, MUST launch a work item that its repository's hold file names as exempt while that hold file exists. An exemption line exempts exactly the one work item it names and no other item. Every other work item of a repository whose hold file names an exempt item MUST stay held and MUST keep its place in the launch queue. A hold file that names no exempt item holds every work item of the repository, exactly as before."

In the same section, replace the resume-launcher bullet "It MUST hold while the hold file exists, as an impl launcher does." with "It MUST hold while the hold file exists, except for a work item the hold file names as exempt, as an impl launcher does."

In the `check-fleet-launch` harness case list, add three cases after "holding a launch while the hold file exists": launching an exempt item while the hold file exists; holding every other item of the repository, and keeping its queue place, while the hold file names an exempt item; and holding every item of the repository when the hold file names no exempt item.

In SPECIFICATION/scenarios.md add a scenario titled "Scenario NN — A repository hold file with an exempt item launches only that item" (NN is the next free number): Given a repository hold file that names bd-x as exempt and a queue holding tickets for bd-x and bd-y; When the launcher runs; Then it launches bd-x, holds bd-y, and bd-y keeps its queue place. The co-edit of tests/heading-coverage.json (one entry for the new scenario heading, `test` MAY be the literal "TODO" with a non-empty `reason`) belongs in the same revise pass.
