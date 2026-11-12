---
topic: a-single-tokenless-item-in
author: claude-opus-5-5
created_at: 2026-11-12T10:14:23Z
---

## Proposal: One tokenless item can be given its first claim token without stopping the tenant's claim writers

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The claim-token cutover bullet sanctions the migration pass only before the cutover, and only with every claim writer of the tenant stopped. After the cutover, an item that names no current token can be recovered only by a tenant-wide writer stop, which a continuously dispatching tenant never reaches. This proposal adds a per-item recovery that names a first token on one tokenless item while the writers keep running, with its re-read and naming write made atomic against every other recovery by a tenant-wide recovery fence, won through the claim-token protocol's own compare-and-swap.

### Motivation

Work item bd-ib-4lbu3z (plan bd-ib-ax3rds), routed by legacy-coordinator-agent (session cb187a57) on 2026-11-12, which agreed the fencing argument. contracts.md §"Dispatcher policy settings" requires the migration pass to run "while every claim writer of the tenant ... is stopped". In a tenant with continuous dispatch, the coordinator will not force or falsely attest such a window; on 2026-11-12 it ruled instead to re-file two tokenless items and to close one out-of-band. Fleet survey 2026-11-12 (read-only migrate_claim_tokens.py; the 2 of 16 /data/projects repositories that commit `dispatcher.claim_tokens: true`): livespec-dev-tooling held 10 tokenless non-closed items from raw `bd create`; legacy-coordinator-agent (session cb187a57) closed bqnzcm.1 out-of-band after its acceptance write was refused, leaving 9. livespec-orchestrator-beads-fabro held 2 (bd-ib-ax3rds.1 and .2), since re-filed through the creation seam as bd-ib-f5jaa7 and bd-ib-hjqx65. Why no writer stop is needed for ONE item: once the key is `true`, a claim writer that finds no current token on a non-closed item already MUST write nothing and report `claim-token-missing`. So no protocol writer can race a recovery on a tokenless item; the only racer is a second recovery. A plain mint, re-read and name-if-still-tokenless sequence does NOT fence it, because both re-reads can see the item tokenless (coordinator grade, session 245a3c34). So the re-read and the naming write hold one tenant-wide recovery fence won through the protocol's own compare-and-swap. A hand `bd update` stays the separate residual the subsection already names. Companion: bd-ib-x4b4ht stops new tokenless items being created. In-flight alignment: none of the open spec PRs touches claim tokens (align).

### Proposed Changes

**1. A per-item recovery after the cutover (`contracts.md` §"Dispatcher policy settings", the claim-token cutover bullet).** After the sentence "Once the key is `true`, a claim writer that finds no current token on a non-closed item MUST write nothing and MUST report `claim-token-missing`, and `needs-attention` MUST surface the item." add:

> After the cutover, `dispatcher.py recover-claim-token --repo <path> --item <work-item-id>` MUST name a first token on that one item without requiring the tenant's claim writers to stop. It MUST act only on a non-closed item that names no open token, and MUST report any other item unchanged, naming the open token it names or that it is closed. The re-read that finds the item tokenless and the write that names its token MUST be atomic against every other recovery of the tenant. A store write that names a token only if the item still names none would be atomic, but `bd update` offers no such conditional write. So the recovery MUST first win the tenant's single recovery fence, a token record won through the claim-token protocol's own server-mediated compare-and-swap (closing the fence's current token and naming its successor), and MUST hold that fence from its re-read through its naming write. Holding it, the recovery MUST re-read the item. Only when that re-read shows the item naming no open token MUST it mint a fresh token and name it as the item's current token. Otherwise it MUST mint nothing and report the item unchanged. It then releases the fence. A recovery that cannot win the fence MUST write nothing to the item and MUST report it busy, naming the fence. Minting only after the fenced re-read means no minted token is ever left unnamed. Inside the fenced window no protocol claim writer can act on the item, because every such writer writes nothing on an item that names no current token; and a late recovery cannot overwrite a token a claim writer has since moved, because it re-reads under the fence before it writes. It MUST change no other item. It MUST journal one `claim-token-recovered` record naming the item, the token and the invoker. Running it twice on one item MUST leave the item naming exactly one open token. A hand write outside the protocol remains the separate residual this subsection names. The pre-cutover migration pass is unchanged.

**2. Scenario (`scenarios.md`).** Append:

## Scenario 354 — One tokenless item is given its first claim token while the tenant's claim writers keep running

```gherkin
Feature: per-item claim-token recovery after the cutover
  Scenario: a tokenless item is recovered with the writers running
    Given a tenant whose committed dispatcher.claim_tokens is true and whose Dispatchers are running
    And a non-closed item that names no open token
    When the operator runs dispatcher.py recover-claim-token for that item
    Then the item names exactly one open token
    And no other item changes
    And a later claim writer claims the item through the token protocol instead of reporting claim-token-missing
  Scenario: a second recovery leaves one token
    Given an item that a recovery has just given an open token
    When the operator runs dispatcher.py recover-claim-token for that item again
    Then the item still names exactly that one open token
    And the report names the item as unchanged
  Scenario: two concurrent recoveries name one token
    Given a tokenless item
    When two recoveries of that item run at the same time
    Then exactly one of them wins the tenant's recovery fence and names a token
    And the item names exactly one open token
    And the other recovery either reports the item unchanged after the winner released the fence, or reports it busy
    And no minted claim token is left open that no item names
```

**3. **Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new scenario heading, carried through `resulting_files[]` with the path spelled `../tests/heading-coverage.json` or edited directly in that commit, with `test: "TODO"`, `work_item: "bd-ib-4lbu3z"` and a non-empty `reason` naming the tier the owed test runs at, integration or above; and one matching `tests/heading-coverage-debt.json` entry carrying the key three, `work_item: "bd-ib-4lbu3z"` and `first_seen` set to the revise date. If the revise renumbers Scenario 354, the row and entry MUST carry the renumbered heading text.
