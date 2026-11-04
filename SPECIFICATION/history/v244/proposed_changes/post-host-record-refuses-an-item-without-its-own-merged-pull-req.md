---
topic: post-host-record-refuses-an-item-without-its-own-merged-pull-req
author: claude-opus-5-5
created_at: 2026-10-24T01:34:43Z
---

## Proposal: post-host-record-refuses-item-without-own-merged-pr

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a pre-post refusal to the host-record posting primitive. Today the host leg of `### Proof of Done record` (under `## Self-contained plugin dispatch` in contracts.md) says host records MUST be published on the pull request of the latest merged run for the item, and that one posting primitive renders them, but nothing says what the primitive does when the item has no merged pull request of its own. The proposal states that the primitive MUST resolve its target only among pull requests that a dispatch of the named item produced, MUST refuse before posting anything when no such merged pull request exists, and MUST name the work item and the missing pull request in that refusal. It MUST NOT post onto a pull request that no dispatch of the named item produced. Two new scenarios inside the existing Scenario 136 state the refusal and the positive target case.

### Motivation

The generalization target is `## Self-contained plugin dispatch` in SPECIFICATION/contracts.md: its `### Proof of Done record` subsection carries the paragraph **The host leg.**, which is the only place the spec governs where a host record is published and which posting primitive publishes it. That paragraph says "Host records MUST be published on the pull request of the latest merged run for the item" and "The implementation MUST provide one posting primitive that renders these records", and the acceptance pass's host-captured leg treats a record on any other pull request as not evidence. So the spec already forbids the wrong outcome, but it states no duty for the primitive in the case where the item has no merged run at all, and the implementation filled that gap by posting somewhere.

Measured instance (work item bd-ib-56ruqk): on 2026-10-23 at 18:55:57Z, `dispatcher.py post-host-record --repo /data/projects/livespec-tdd-proof --item tdd-proof-lv352h --verdict host_recorded` (orchestrator build 48b64a682cff, v0.239.2) exited 0 and posted the record on livespec-tdd-proof pull request 4, "chore: register the project-scoped livespec plugins and expose ensure-plugins". tdd-proof-lv352h has never had a pull request: its only dispatch, run 01M5N1FVZ6W6, ended at needs_human with zero files changed. `host_record_target` resolved "the pull request of the item's latest merged run" through `resolve_merged_pr`, which returned an unrelated merged pull request instead of nothing, so the primitive's own no-target refusal never fired. The record then reads as proof for an unrelated pull request, and an acceptance pass could grade the wrong pull request. A correction comment had to be posted on pull request 4 by hand.

The judge's rationale is that no clause requires the primitive to refuse, before posting, when the item has no merged pull request of its own, nor requires that refusal to name the work item and the missing pull request. This proposal adds exactly that duty in the host-leg paragraph and binds it with scenarios in Scenario 136, which already governs the posting primitive's other refusal (the self-replay refusal). It is distinct from the several-merged-pull-requests selection cases (bd-ib-a3dzii, bd-ib-q3ejtp) and from host-only merges without a run id (closed bd-ib-juvega); this is the zero-own-pull-request case only.

### Proposed Changes

Two coordinated edits. Both MUST land together in a single revision.

**1. `SPECIFICATION/contracts.md` §"Self-contained plugin dispatch" → `### Proof of Done record`, the paragraph beginning **The host leg.**.** The paragraph currently contains these two consecutive sentences:

> The implementation MUST provide one posting primitive that renders these records, so that no session hand-formats one. The primitive MUST compute the publishing identity itself — the invoking agent session's id, or the forge login for a human — and MUST NOT accept it as a caller-supplied string;

Insert the following text between them, that is, immediately after "so that no session hand-formats one." and before "The primitive MUST compute the publishing identity itself":

```
The primitive MUST resolve the pull request it posts on only from the
pull requests that a dispatch of the named work item produced, and it
MUST take the pull request of the latest such dispatch whose pull request
merged. When no dispatch of the named work item has a merged pull request,
the primitive MUST refuse before it posts anything, and the refusal MUST
name the work item and state that the item has no merged pull request of
its own. The primitive MUST NOT post a host record onto a pull request
that no dispatch of the named work item produced, and MUST NOT fall back
to any other merged pull request in the repository, however that pull
request was found. A host record already posted on such a pull request is
not evidence for the item, and it is not evidence for the pull request it
was posted on.
```

Nothing else in the paragraph changes. In particular, the sentence "Host records MUST be published on the pull request of the latest merged run for the item; a host record on an earlier pull request, or one naming a build identity that does not contain the latest merge, is not evidence." stays as written; the inserted text states how the posting primitive satisfies it and what it does when that pull request does not exist.

**2. `SPECIFICATION/scenarios.md` §"Scenario 136 — A host-captured assertion holds the item in acceptance until an independent host replay verifies it against the released build".** Inside the existing gherkin block, immediately after the scenario "A self-replayed host record is refused" (whose last step is "And a host_verified record with that same identity posted by any other route leaves the assertion pending and is reported as not independent") and before the scenario "A host replay that does not reproduce is rework input", insert:

```gherkin
  Scenario: The posting primitive refuses an item that has no merged pull request of its own
    Given a work item carrying a host-captured assertion whose only dispatch ended without a pull request
    And the repository holds other merged pull requests that no dispatch of that item produced
    When a session drives the posting primitive to publish host_recorded for the item
    Then the posting primitive refuses before posting anything
    And the refusal names the work item and states that it has no merged pull request of its own
    And no host record is posted on any pull request in the repository
  Scenario: The posting primitive posts on the pull request the item's own dispatch merged
    Given a work item carrying a host-captured assertion whose latest dispatch merged a pull request
    And the repository holds a more recently merged pull request that no dispatch of that item produced
    When a session drives the posting primitive to publish host_recorded for the item
    Then the host_recorded record is posted on the pull request that the item's own dispatch merged
    And no record is posted on the more recently merged pull request
```

No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.
