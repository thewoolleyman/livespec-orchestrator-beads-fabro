---
topic: incident-authority-genesis-and-pre-pr-carrier
author: codex:incident-genesis-carrier
created_at: 2026-11-04T09:04:50Z
---

## Proposal: Safe first incident authority and an explicit pre-PR carrier

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Specify atomic first incident publication and branch-to-PR authority so real initial hooks and first publication can proceed without a circular requirement for a PR, while all server-side ownership and retry fences remain effective.

### Motivation

Complete safe canonical incident first-root ownership and pre-PR carrier identity so authorized initial local hooks and first push can run before a PR exists, while preventing multi-host root races, stale factory writes, duplicate effect retry and alternate lifecycle authority. Current public fixed-id creation reopens records and metadata updates race. The currently serving reader build466707 and primary schema require an existing authority root and a positive PR number. The pending PR4350 receipt increment can represent repair with PRnumber0, but still has no atomic first-root publication or canonical carrier-ref identity; that incremental support is not claimed absent. Generic claim-token behavior is already ratified, including its deliberately accepted residual races. This focused amendment deliberately adds a stronger incident-only capability plus publication boundaries; it neither restates those residuals as a generic conformance defect nor duplicates their implementation owner.

### Proposed Changes

Amend `contracts.md` under `## Expedited incident lifecycle` with the following bounded incident-specific requirements. This amendment does not replace the ordinary claim-token protocol under `### Stranded claim release`, admit a duplicate generic ownership project, or claim that its currently accepted residual races satisfy a stronger incident capability. Existing incident entry work remains `bd-ib-dzbwaq`; the generic all-writer prerequisite remains `bd-ib-jjws2`, whose claim-token design was ratified in v254 and Scenario 263. These ids explain delivery ownership; runtime behavior MUST NOT depend on their literal values.

### First incident authority publication

A first incident authority is the canonical item's initial immutable incident snapshot together with its one named transition root. Before authorizing an incident hook, host repair or publication, the public canonical writer MUST atomically establish that root, generation, owner and initial phase against the exact expected item/lifecycle/dispatch-claim state. An existing item with no root MUST NOT be initialized by observing absence followed by `bd update --metadata`, an insert-only comment, a fixed-id `bd create`, or a host-scoped lock. A fixed-id create is an upsert and can reopen a closed token; metadata updates are client read-modify-write. Neither is a server-side exclusion. A fresh random root record alone MUST NOT authorize effects before its canonical publication is confirmed.

The writer MUST expose a named `incident-genesis-capability-unavailable` refusal when its installed PUBLIC store capability cannot condition first publication on absent incident authority AND the exact expected claim state in the same server-enforced operation. It MUST write no activation projection or incident effect in that case. A fully migrated existing current-token protocol MAY provide the exclusion only when all applicable writers participate and the provider establishes the required atomic publication semantics; merely calling `bd close` on an unrelated new record or accepting the ordinary protocol's delayed-write residual MUST NOT advertise that capability. The implementation MUST use the public guarded ledger/provider boundary, never a private Beads delegate, direct ungoverned SQL or a host-local authority file. A genuinely new canonical incident may be filed minimally under existing intake policy, but its identity MUST remain the same through initialization and repayment; failure to initialize an existing item MUST NOT cause another incident item to be created.

The immutable initialization request MUST bind schema version, tenant/repository, canonical item id, authorizing principal, immutable operation id, expected absent incident root, expected lifecycle/claim identity, and the complete proposed initial snapshot. A successful reply MUST bind that exact request digest and committed root/generation. The caller MUST read authoritative current state before treating activation as usable. Two hosts racing different operations for one item MUST observe at most one committed initial root; a loser MUST perform no incident effects. Same-operation retry with identical bytes MUST recover the original root and result. Reuse with a different request MUST refuse `incident-operation-conflict`. Timeout, unreadable outcome or an unavailable provider MUST remain unknown until exact operation-receipt lookup establishes committed, confirmed-absent or still-unknown status; an unknown outcome MUST NOT cause another root or blind initialization attempt. Immutable predecessor and operation receipts MUST survive any projection refresh.

### Carrier identity before and after PR creation

Canonical attempt identity MUST represent the carrier as a discriminated state: `branch-reserved`, `head-published`, or `pr-bound`. `branch-reserved` binds the exact repository, fully qualified `refs/heads/...` target ref, authorized base/input parent commit, and current staged tree. It has no PR number. A first local commit MUST validate that current input boundary before its effects; the resulting actual commit id, parent and tree MUST be verified and recorded under the same attempt before push. An autofix or other source/index change MUST obtain a fresh current boundary receipt rather than reusing one for different bytes. This permits a real pre-commit entrance without inventing the future commit SHA or requiring a PR that can only be created after publication.

The first push MUST revalidate current owner/generation and bind the exact authorized commit/tree and target repository/ref. Publication MUST use a compare-and-swap against the recorded remote-ref precondition: confirmed absent for a new branch, or the exact expected prior SHA for a recorded retry/update. It MUST NOT overwrite unrelated branch contents, infer ownership from a matching branch basename, or use an unconstrained force push. Lost publication replies MUST be reconciled by exact repository/ref/head and operation receipt before another effect. `head-published` MUST retain the confirmed remote head and the complete earlier branch reservation; it still has no PR number.

Only an authenticated forge observation of a real PR with that repository, target ref, exact published head and intended base MUST advance the carrier to `pr-bound` with a positive PR number. Zero, a placeholder PR, a guessed next PR number, first branch match or title mention MUST NOT stand in for the observation. A conflicting PR/head/base MUST refuse the binding without replacing the original branch authority. Initial hooks and push may consume only the permissions granted by the current pre-PR state; PR CI, observer arming, merge and post-merge readers MUST require their real `pr-bound` identity and existing independent observer contract. Later states MUST append retained observations rather than rewriting earlier identity/history. Unsupported carrier schema/state MUST produce a named capability/configuration refusal, never normal-mode fallback or an improvised second parser.

### Factory transfer and recovery of the initial operation

The initial host takeover of an item that has queued or live factory work MUST win the same server-enforced current-claim transition used by every factory admission, valve, proof, terminal and recovery writer. It MUST durably record the expected prior claim/run and invalidating generation before host effects, prevent queued old admission, and retain cancel/fence intent plus exact receipts. An unobserved cancellation MUST NOT be reported as a canceled run. No stale completion, proof, branch recovery or cleanup publisher may proceed after losing that current generation, even if a delayed ordinary metadata write arrives. Where the installed all-writer capability cannot provide that exclusion, incident entry MUST refuse rather than claiming the factory is fenced. Returning ownership for normal repayment MUST use the same canonical conditional boundary, restore ordinary admission/provenance and retain the host attempt; it MUST NOT manufacture factory proof or reuse a stale factory run.

All these requirements MUST be demonstrated against the installed public provider with independent concurrent clients that share only the server before incident enablement. An in-process mock or same-host lock race alone is insufficient. The proof MUST include first-root races, operation retry after a lost reply, an unobservable outcome, queued/live factory transfer and a late old terminal write; pre-PR commit and first push with no PR record; stale source/tree/ref refusal; forged PR binding refusal; and successful exact PR binding followed by ordinary normal factory repayment. Missing provider capability remains an explicit rollout obligation, not authority granted by the flag.

Add `## Scenario: incident entry owns one initial authority before a carrier PR exists` to `scenarios.md` with the following behavior:

```gherkin
Feature: Safe initial incident authority and a carrier before PR creation
  Scenario: Independent hosts race the first incident publication
    Given one canonical item has no incident root and its exact current claim is observable
    And two clients share only the public ledger server and request different initial incident operations
    When both condition publication on that same absent root and claim
    Then at most one immutable initial root and host generation becomes current
    And the loser performs no incident hook, push or lifecycle effect

  Scenario: A lost initialization reply recovers the same operation
    Given initial publication committed but its reply was lost
    When the same operation and identical request are retried
    Then exact authoritative lookup recovers the original root and result without another root
    And a changed payload under that operation id is refused as incident-operation-conflict
    And an unavailable lookup remains unknown without a blind initialization effect

  Scenario: Missing server capability never becomes host-local authority
    Given the installed provider cannot atomically publish the absent root and expected claim state
    When authorized incident entry is requested for an existing item
    Then it reports incident-genesis-capability-unavailable and performs no activation or incident effect
    And it neither creates another incident item nor uses metadata read-modify-write or a local lock as authority

  Scenario: A real first commit and push precede PR creation
    Given current branch-reserved authority names the exact repository, target ref, input parent and staged tree
    And no carrier PR exists
    When its authorized local commit records the verified resulting commit and its first push wins the recorded remote-ref compare-and-swap
    Then canonical head-published authority retains that exact remote head and branch history without a fabricated PR number
    And changed input bytes, changed generation or an unrelated existing ref refuse before publication

  Scenario: PR binding requires the actual authorized forge identity
    Given head-published authority has no PR number
    When an authenticated forge observation reports the real matching repository, head ref, head commit and intended base
    Then that attempt advances to pr-bound with the real positive PR number
    And a foreign PR, stale head, wrong base or unsupported carrier schema refuses without replacing its existing authority

  Scenario: Factory takeover fences delayed work and normal repayment retains history
    Given the item has a current queued or live factory claim
    When the sanctioned incident transition conditionally invalidates that exact claim and records host ownership plus cancel or fence intent
    Then queued old admission and a delayed old completion or proof writer perform no current effect
    And an unknown cancel result is retained as unknown rather than claimed canceled
    And later normal repayment transfers current ownership conditionally, retains the host attempt and uses ordinary factory validation
```

During ratifying revise, co-edit the existing heading-coverage map/debt register under their normal policy; no implementation or test coverage is claimed by this proposal alone.

