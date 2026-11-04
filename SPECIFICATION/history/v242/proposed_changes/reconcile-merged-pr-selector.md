---
topic: reconcile-merged-pr-selector
author: claude-opus-5-5
created_at: 2026-10-27T02:32:18Z
---

## Proposal: reconcile-merged accepts an explicit pull-request selector, and post-host-record targets the reconciled pull request of an item no factory run merged

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

reconcile-merged gains an optional --pr <number> selector that names one merged pull request of the item. It reconciles against that pull request's merge commit instead of refusing on several merged candidates, refuses a pull request that is not merged onto the default branch or does not identify the item by head ref or title, and journals the selection. For an item that no factory run merged, the host leg defines its pull request as the one its latest journaled reconcile-merged resolved or selected. The posting primitive targets that pull request rather than refusing for the missing run, and passes it back as the --pr selector when it drives reconcile-merged.

### Motivation

Spec-first for work-item bd-ib-q3ejtp (coordinator gitops-fleet-capacity-monitoring ranks it normal-high; requested by petri-factory-on-gmktec; bd-ib-a3dzii folded in and closed as superseded). Today the reconcile-merged ranking refuses when the highest tier holds more than one candidate (Scenario 244), which is correct when nothing names the right merge, but the verb has no way to name it. The host leg sends host records to 'the pull request of the latest merged run for the item', which a host-routed item lacks. So a host-routed item that landed through sequenced pull requests can never reach acceptance or take its host-captured proof, and a replay verdict re-drives reconcile-merged into the same refusal. Measured instances: openbrain ob-kncfu3 (PRs 22 and 23; reconcile-merged exited 3 with 'ambiguous merged PR candidates', gate 20261021T154713Z-1225989), livespec-overseer overseer-twtw55 (PRs 2571 and 2572; post-host-record refused), and livespec-dev-tooling-3e3tlw (PRs 2880 and 2883; post-host-record refused with 'no single merged pull request resolves'). Each item had to be closed through close_work_item without its proof leg. Renaming a merged pull request's title to remove the item id would blind the resolver rather than satisfy it, so the selector is explicit. Relation to the pending proposal post-host-record-refuses-an-item-without-its-own-merged-pull-req: that proposal restricts the posting target to pull requests a dispatch of the item produced. This proposal's definitional sentence makes a reconciled pull request the item's own for an item that no factory run merged, so a later revision of that proposal must read the two together.

### Proposed Changes

Four coordinated edits; all MUST land together in a single revision. No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.

**1. `SPECIFICATION/contracts.md` §"Dispatcher loop invocation surface", the reconcile-merged resolution paragraph (it begins "The valve MUST resolve the PR number and merge SHA from GitHub").** Immediately after the sentences

```
rather than silently choosing the first result. Scenario 244 in `scenarios.md`
exercises this ranking.
```

insert

```
The valve MUST also accept an optional `--pr <number>` selector naming one
merged pull request of the item, for an item that landed through more than one
merged pull request. With the selector, the valve MUST resolve that pull request
and its merge SHA from GitHub instead of ranking candidates, and MUST NOT refuse
because other merged pull requests identify the item. It MUST refuse, naming the
pull request, when that pull request is not merged onto the default branch or
does not identify the item by head ref or title. A selected pull request then
stands in every later step of the valve exactly as a resolved one does, and the
valve MUST journal the selected pull request's number and merge SHA in the
reconciliation's journal record. Without the selector the ranking above is
unchanged.
```

**2. `SPECIFICATION/contracts.md` §"Self-contained plugin dispatch" → "Proof of Done record" → "The host leg." paragraph.** Immediately after the sentence "Host records MUST be published on the pull request of the latest merged run for the item; a host record on an earlier pull request, or one naming a build identity that does not contain the latest merge, is not evidence." and before "The implementation MUST provide one posting primitive", insert

```
For an item that no factory run merged, the pull request of its latest merged
run is, throughout this specification, the pull request of the latest
`reconcile-merged` that journaled a green janitor against that pull request and
merge SHA and moved the item into `acceptance`; a refused or failed
reconciliation MUST NOT replace that pull request. The posting primitive MUST target that
pull request for such an item and MUST NOT refuse for the missing run, and when
it drives `reconcile-merged` for such an item it MUST pass that pull request as
the `--pr` selector. When the item has neither a merged run nor such a
reconciliation, the primitive MUST refuse before posting anything, naming the
item.
```

**3. `SPECIFICATION/scenarios.md`.** In §"Scenario 244 — reconcile-merged resolves a merged pull request by head ref, then title, then body mention", append inside the gherkin block, after the scenario "A tie in the highest tier holding a candidate refuses":

```gherkin
  Scenario: An explicit pull-request selector reconciles one of several merged pull requests
    Given an item that landed through two merged pull requests on the default branch, both carrying the work-item id in their titles
    When reconcile-merged runs for the item with --pr naming one of them
    Then it reconciles against that pull request's merge commit without an ambiguous-PR refusal
    And its journal record names the selected pull request and its merge SHA

  Scenario: A selector naming a pull request that is unmerged or does not identify the item refuses
    Given an item and a pull request that is not merged onto the default branch, or that carries the work-item id in neither its head ref nor its title
    When reconcile-merged runs for the item with --pr naming that pull request
    Then it refuses with a message naming the pull request
    And the item's status is unchanged

  Scenario: A selector naming a different pull request than the journaled janitor ran against refuses
    Given an item resting in acceptance whose journaled green janitor ran against one merged pull request of the item
    When reconcile-merged runs for the item with --pr naming another of its merged pull requests
    Then it refuses before running acceptance, naming the mismatched janitor evidence
    And the item's status is unchanged
    And the host-record posting target remains the pull request its journaled green janitor ran against
```

In §"Scenario 136 — A host-captured assertion holds the item in acceptance until an independent host replay verifies it against the released build", insert inside the gherkin block, immediately before the scenario "A host-routed item keeps its declared modes":

```gherkin
  Scenario: A host-routed item with no factory run posts on its reconciled pull request
    Given a host-routed item with a host-captured assertion that no factory run merged
    And the item has never had a factory dispatch
    And reconcile-merged reconciled the item with --pr naming one of its merged pull requests, journaled a green janitor, and parked it in acceptance
    When a session drives the posting primitive to publish host_recorded for the item
    Then the record is posted on the selected pull request and the primitive does not refuse for the missing run
    And when a different session publishes host_verified, the primitive drives reconcile-merged for the item with that same --pr selector
    And reconcile-merged reads that reconciliation's green janitor record and re-runs only the acceptance pass, without refusing for the missing dispatch
```

**4. `SPECIFICATION/contracts.md` §"Dispatcher loop invocation surface", the reconcile-merged entry and its janitor-evidence rule.** Replace the two invocation forms

```
`reconcile-merged --repo <path> --item <work-item-id> [--json]` and, only after
an operator has confirmed the original dispatcher process is dead,
`reconcile-merged --repo <path> --item <work-item-id> --force [--json]`.
```

with

```
`reconcile-merged --repo <path> --item <work-item-id> [--pr <number>] [--json]`
and, only after an operator has confirmed the original dispatcher process is
dead, `reconcile-merged --repo <path> --item <work-item-id> [--pr <number>]
--force [--json]`.
```

and, in the acceptance-item cases, replace

```
The valve MUST decide which case applies from the dispatch journal's record of
the janitor, never from the item's status alone. When the journal cannot be
read, or carries no janitor record for the latest dispatch, it MUST refuse and
name the missing evidence rather than guess either way.
```

with

```
The valve MUST decide which case applies from journaled janitor evidence, never
from the item's status alone. For an item that a factory run merged, that
evidence is the latest dispatch's janitor record. For an item that no factory
run merged, it is the janitor record of the reconciliation that established the
item's current reconciled pull request and merge SHA, which that reconciliation
MUST journal with the pull request and merge SHA it ran against. For an item
resting in `acceptance`, that evidence MUST concern the pull request and merge
SHA this invocation resolves or selects. When the journal cannot be read,
carries no such janitor record, or carries one for a different pull request or
merge SHA, the valve MUST refuse before running acceptance, name the missing or
mismatched evidence, and leave the item's status unchanged.
```

(Edit 4 was added after the first read-only review, which found that an item no factory run merged had no defined janitor evidence for its acceptance-only re-run. A no-factory-run item is a locally built item, whose pull request already resolves only from the head-ref or title tier, so a reconciled target always satisfies the selector it is replayed through.)
