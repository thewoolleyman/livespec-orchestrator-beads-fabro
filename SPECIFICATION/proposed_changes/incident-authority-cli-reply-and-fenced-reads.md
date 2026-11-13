---
topic: incident-authority-cli-reply-and-fenced-reads
author: claude-opus-5-5:expedited-incident-hardening
created_at: 2026-11-13T03:07:46Z
---

## Proposal: The incident authority CLI defines its reply, the full fenced identity and read-current once, and reports an absent item by a status no consumer can mistake for a reading or a refusal

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds one paragraph to contracts.md §"Expedited incident lifecycle", immediately BEFORE the v364 paragraph that begins "The incident authority writer's command-line interface MUST offer an item-only head read, `read-head`". It defines three things the spec already relies on but never states. (1) The CLI's reply: one schema-1 JSON object on stdout carrying `status`, `result`, `authorizes_current_effects` and `normal_factory_proof: false`, exiting 0 unless the reply is refused and 78 when it is. (2) An attempt's full fenced identity: repository, canonical incident item id, attempt id, incident phase, generation, operation id and owner. (3) `read-current`, the fenced current-head read: it requires the full fenced identity, verifies only when every field equals the current head, refuses `incident-authority-identity-mismatch` otherwise and `incident-authority-changed` when the head moves after selection, and is the only action whose verified reply sets `authorizes_current_effects` true. It also pins how `read-head` reports an absent item: `status` `absent`, exit 0, the repository and item id, and no phase or generation. Scenario 364 is reworded to assert those observables, and one new scenario exercises read-current's fence.

### Motivation

The coordinator's PASS grade on livespec-orchestrator-beads-fabro#5116 (revise v364, the-incident-authority-cli-has, bd-ib-txbv7i, 2026-11-13) left one advisory finding from the pre-merge doctor pass, and ruled that it be settled by ONE follow-up proposal rather than in v364, which would have voided a clean ratification review. The finding: v364's paragraph names `read-current` and "the full fenced identity", and neither appears anywhere else in the specification. The grade added a second gap: v364 says an item with no incident authority genesis reads absent and is not refused, but it does not say how a machine tells absent apart from a reading or a refusal.

The behaviour defined here is already shipped, apart from the absent status, which only `read-head` (unbuilt, bd-ib-txbv7i) will emit. `commands/incident_authority.py` on orchestrator master prints one `{"schema": 1, "status": "verified" | "refused", "result", "authorizes_current_effects", "normal_factory_proof": false}` object and returns 78 for a refusal and 0 otherwise (`_reply`). `read-current` takes `--repository`, `--item`, `--attempt`, `--phase`, `--generation`, `--operation` and `--owner`. `_incident_authority_payload.query_matches` requires that whole set ("A consumer must select the whole fenced identity, including its owner"). `_incident_authority_reader._select` refuses `incident-authority-identity-mismatch` unless exactly the current head matches, and `_reading` refuses `incident-authority-changed` when the head's standing token has moved after selection. Only `read-current` passes `authorizes=True`.

Why a distinct `absent` status at exit 0, rather than `verified` with a presence flag or a distinct exit code. Absent is not a refusal (v364), so it cannot exit 78. livespec-dev-tooling's shared client (`livespec_dev_tooling/incident_authority_client.py`, `_check_reply`/`_verified`) accepts only exit 0 or 78 and treats an exit-0 reply whose `status` is not `verified` as the refusal `incident-authority-not-verified`. A distinct `absent` status therefore fails closed in every existing consumer, while a `verified` reply carrying a presence flag would pass through that client as a reading with no phase. The one consumer that wants absence, livespec-dev-tooling's incident fleet audit (livespec-dev-tooling-io6hyk), reads `status` directly when it adopts `read-head`.

The grade asked for the definitions "where the writer CLI's actions are listed". The specification lists none of the CLI's actions; it names `commit-transition` and `drill-close` in the drill-close paragraph and, after v364, `read-head` and `read-current`. This proposal places the definitions immediately before the `read-head` paragraph, the first place the CLI's reads are specified, so every later sentence can use the defined terms.

Coherence with pending proposal incident-read-history-returns-only (livespec-orchestrator-beads-fabro#5048, open), which inserts after the same inspection paragraph and spells the fenced identity inline for `read-history` as "attempt id, phase, generation, operation id and owner". The set defined here is the same five fields plus the repository and item id that every action already names. Whichever of the two revises second may replace that inline list with "the full fenced identity"; nothing here depends on #5048 landing.

### Proposed Changes

### contracts.md

In `SPECIFICATION/contracts.md`, section `## Expedited incident lifecycle`, insert the following paragraph immediately BEFORE the paragraph that begins "The incident authority writer's command-line interface MUST offer an item-only head read, `read-head`":

> The incident authority writer's command-line interface MUST answer every action with exactly one JSON reply object on stdout carrying `schema` 1, a `status`, a `result`, `authorizes_current_effects` and `normal_factory_proof` false. `status` MUST be `refused` for a named refusal, whose `result` carries the refusal's named reason, and the process MUST then exit 78; every reply that is not refused MUST exit 0. An attempt's full fenced identity is its repository, canonical incident item id, attempt id, incident phase, generation, operation id and owner. `read-current` is the fenced current-head read: it MUST require the full fenced identity and MUST reply `verified` with the current head's attempt only when every field of that identity equals the current head's. It MUST refuse with the named reason `incident-authority-identity-mismatch` when any field differs, including when a later generation has superseded the named one, and with `incident-authority-changed` when the head moves after it was selected. `read-current` MUST be the only action whose reply sets `authorizes_current_effects` true, and only when the reply is `verified`; a caller MUST take it immediately before the side effect it authorizes. Scenario 365 in `scenarios.md` exercises this paragraph.

In the `read-head` paragraph that follows, replace the sentence "It MUST report the item as absent only when no incident authority genesis exists for that item; every other chain fault, ..." up to its semicolon with:

> It MUST report the item as absent only when no incident authority genesis exists for that item, by a reply whose `status` is `absent`, which exits 0, whose `result` carries the repository and item id and no phase or generation, and whose `authorizes_current_effects` is false;

so that the sentence continues unchanged with "every other chain fault, including an ambiguous chain, ...". A reading of a present item replies `verified`. No other sentence of the paragraph changes.

### scenarios.md

In `## Scenario 364 — An item-only head read reports an incident item's current phase and generation and authorizes nothing`, make these case changes and no others:

- In "read-head reports the current phase and generation, drill-closed included, and authorizes nothing", add after the first Then line: `And the reply's status is verified and the process exits 0`.
- In "An item with no incident authority genesis reads absent, not refused", replace `Then the reply reports the item as absent` with `Then the reply's status is absent and the process exits 0`, and add `And the reply carries the repository and item id and no phase or generation` and `And authorizes_current_effects is false`.
- In "Every other chain fault stays a named refusal and never reads absent" and in "An unreadable authority store refuses as unavailable with no phase", add `And the reply's status is refused and the process exits 78`.

Append this scenario. Its number is the lowest scenario number neither ratified on master nor claimed by an open pull request at revise time; 365 is written here, and the revise renumbers it and the contracts.md pointer together if 365 is taken.

## Scenario 365 — read-current verifies only the current head's full fenced identity and is the only action that authorizes a side effect

```gherkin
Feature: The fenced current-head read authorizes exactly the attempt it names
  Scenario: The full fenced identity of the current head verifies and authorizes
    Given an incident item whose current head is attempt A at incident phase P, generation G, operation O and owner W
    When a caller runs read-current with the repository, the item id, A, P, G, O and W
    Then the reply's status is verified and the process exits 0
    And authorizes_current_effects is true
  Scenario: A stale or partial fence is refused and authorizes nothing
    Given the same item
    When a caller runs read-current naming generation G after a later generation has superseded it, or naming a different owner or operation
    Then the reply refuses with the named reason incident-authority-identity-mismatch
    And the reply's status is refused and the process exits 78
    And authorizes_current_effects is false
  Scenario: A head that moves after selection is refused
    Given read-current has selected the current head of an item
    When that head's standing token is closed by a successor before the reply is returned
    Then the reply refuses with the named reason incident-authority-changed
    And authorizes_current_effects is false
  Scenario: No other action authorizes a side effect
    Given an incident item with a current head
    When a caller runs read-head or read-history for it
    Then authorizes_current_effects is false whatever the reply's status
```

### Co-edit at revise

`tests/heading-coverage.json` gains a TODO row for the new scenario, at the integration tier or above, owned by bd-ib-txbv7i, and `tests/heading-coverage-debt.json` gains the matching debt entry. The Scenario 364 row's reason gains the absent status, exit 0 and exit 78 observables.
