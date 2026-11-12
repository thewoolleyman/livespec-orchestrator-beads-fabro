---
topic: bd-guard-refuses-a-raw
author: claude-opus-5-5
created_at: 2026-11-12T10:14:21Z
---

## Proposal: The lifecycle guard refuses a raw create of a non-closed item in a claim-token tenant

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

After a tenant commits `dispatcher.claim_tokens: true`, every non-closed item must name a current claim token, and the store's creation seam names the first one in the creating write. A raw `bd create` through the lifecycle guard bypasses that seam and creates an item no claim writer can ever write. This proposal makes the guard refuse such a create before the delegate runs, recognising a sanctioned create by the `dispatch_claim_token` key in its metadata, and never minting a token itself.

### Motivation

Work item bd-ib-x4b4ht (plan bd-ib-ax3rds), routed by legacy-coordinator-agent (session cb187a57) on 2026-11-12, which agreed the fix shape. A raw `bd create` in a claim-token tenant creates an item naming no first token; every claim writer then refuses it with `claim-token-missing`, and before bd-ib-4lbu3z the only remedy is a tenant-wide writer stop. bd-ib-ufot43 (closed) fixed only the orchestrator's own creation seam (`_store_claim_token_creation`). Related: bd-ib-m7hj (the guard's create normalization skips child creates). Fleet survey 2026-11-12 (read-only migrate_claim_tokens.py; the 2 of 16 /data/projects repositories that commit `dispatcher.claim_tokens: true`): livespec-dev-tooling held 10 tokenless non-closed items from raw `bd create`; legacy-coordinator-agent (session cb187a57) closed bqnzcm.1 out-of-band after its acceptance write was refused, leaving 9. livespec-orchestrator-beads-fabro held 2 (bd-ib-ax3rds.1 and .2), since re-filed through the creation seam as bd-ib-f5jaa7 and bd-ib-hjqx65. Fix shape: REFUSE, not mint. The creation seam mints FIRST and names the token in the creating write's metadata ("THE TOKEN IS NAMED IN THE CREATING WRITE, never in a second one"), so the guard can recognise a sanctioned create by that key with no token logic of its own. A guard that minted would duplicate the token protocol outside its owner, would be the create-then-name pair the seam rules out, and racing the seam's own mint could name two tokens. In-flight alignment: none of the open spec PRs (#5019, #5021) touches the connection model or claim tokens (align).

### Proposed Changes

**1. The guard refuses a raw create in a claim-token tenant (`contracts.md` §"Beads connection model").** After the bullet "**Pinned lifecycle-guarded entry point.**", add:

> - **A raw create in a claim-token tenant is refused at the guard.** When the lifecycle guard is asked to run `bd create` from a working directory inside a repository whose committed `dispatcher.claim_tokens` is `true` (§"Dispatcher policy settings"), and the create would make a non-closed issue whose metadata does not name the `dispatch_claim_token` key, the guard MUST exit non-zero without invoking its delegate, MUST create nothing, and MUST print one line naming the missing first claim token and the sanctioned filing seam (`capture-work-item`, or the store's creation seam). The refusal MUST apply equally to a create carrying `--parent`. A create whose metadata names `dispatch_claim_token`, the creation of a claim-token record itself (the record titled `livespec dispatch claim token`), a create of an issue born closed, and every create from a repository whose `dispatcher.claim_tokens` is unset or `false` MUST pass the guard exactly as before. When the guard cannot read the setting from the repository it runs in, it MUST refuse the create, naming the read failure, and MUST NOT treat the setting as `false`. The guard MUST NOT mint a claim token: the creation seam names the first token in the creating write, and a token minted by the guard would be a second, unfenced writer of the protocol.

**2. Scenario (`scenarios.md`).** Append:

## Scenario 353 — The lifecycle guard refuses a raw create of a non-closed item in a claim-token tenant

```gherkin
Feature: a claim-token tenant creates items only through the seam that names their first token
  Scenario Outline: the guard refuses a raw create
    Given a repository whose committed dispatcher.claim_tokens is true
    When an operator runs bd create <args> with no dispatch_claim_token in its metadata
    Then the guard exits non-zero and no issue is created
    And the line it prints names the missing first claim token and the sanctioned filing seam

    Examples:
      | args                       |
      | a top-level issue          |
      | a child issue with --parent |

  Scenario: a sanctioned create passes
    Given a repository whose committed dispatcher.claim_tokens is true
    When the store's creation seam runs bd create with dispatch_claim_token in its metadata
    Then the issue is created naming that token

  Scenario: a tenant before its cutover is unaffected
    Given a repository whose dispatcher.claim_tokens is unset
    When an operator runs bd create with no dispatch_claim_token in its metadata
    Then the issue is created exactly as before
```

**3. **Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new scenario heading, carried through `resulting_files[]` with the path spelled `../tests/heading-coverage.json` or edited directly in that commit, with `test: "TODO"`, `work_item: "bd-ib-x4b4ht"` and a non-empty `reason` naming the tier the owed test runs at, integration or above; and one matching `tests/heading-coverage-debt.json` entry carrying the key three, `work_item: "bd-ib-x4b4ht"` and `first_seen` set to the revise date. If the revise renumbers Scenario 353, the row and entry MUST carry the renumbered heading text.
