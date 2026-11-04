---
topic: expedited-incident-lifecycle
author: codex:expedited-incident-response-flag/orchestrator-carrier
created_at: 2026-11-03T19:45:17Z
---

## Proposal: Expedited incident identity, fenced ownership and same-item normal repayment

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add an incident-only lifecycle contract that preserves one item across fast host repair, exact provenance, recovery and mandatory normal factory repayment while preserving ordinary admission and acceptance.

### Motivation

Maintainer priority-1 implementation continuation for livespec-dev-tooling-bqnzcm requires local incident repair without factory/slow admission, followed by same-item normal proof. Current complete_and_accept and merged-PR resolution assume a single normal carrier; claim replacement retains only the current stamp. Existing bd-ib-q3ejtp remains the generic explicit multi-PR prerequisite. Dev-tooling and core own execution/forge and inherited policy respectively.

### Proposed Changes

Add the following new section to contracts.md. This is an incident-only exception to Work-item state semantics, Dispatcher admission, WIP cap, and post-merge acceptance, and the ordinary factory provenance/routing contracts; all ordinary and normal-repayment paths retain their existing gates. Core owns inherited incident policy; livespec-dev-tooling owns execution selection, CI observation and the scoped forge recovery principal.

## Expedited incident lifecycle

For an authorized recorded incident only, this section MUST take precedence over conflicting ordinary admission, factory provenance, WIP, reconciliation and completion clauses. It MUST preserve the ordinary policy for every other item and for normal repayment. The incident phase is context on the canonical ledger item, not a second work-item store or lifecycle authority.

The plugin MUST preserve one canonical incident work-item id through repair, revert, corrected attempts, normal factory repayment and later reopening. Each attempt MUST bind its repository, immutable operation id, attempt id, phase/generation, exact base/head, carrier PR, complete landed commit/tree identities and cumulative original scope. Claim stamps, branch recovery, merged-PR resolution, proof publication, acceptance and closure MUST select that explicit current identity; the first merged branch match, latest title mention, or marker-removal diff alone MUST NOT select it. Existing explicit multi-PR selection work remains a prerequisite; this contract does not replace its general ambiguity refusals.


The sanctioned incident transition MUST publish the following phase and canonical lifecycle-state pair. Host-owned active phases MUST carry the incident owner rather than a factory claim and MUST NOT consume a factory slot. Unknown phase/state combinations MUST produce a named configuration refusal. Only the incident transition may establish these exceptional host phases; flags alone MUST NOT mutate lifecycle state. Ordinary factory admission and acceptance govern the repayment phases.

| Incident phase | Canonical lifecycle state | Transition condition |
| --- | --- | --- |
| repair | active | Authorized canonical entry or corrected repair with fresh evidence. |
| master-observation | active | The exact expedited repair carrier merged. |
| reverting | active | A current incident failure requires the recorded inverse recovery. |
| rollback-conflict | blocked | The controller records an owned inverse-patch conflict with its release condition. |
| collecting-failures | active | Revert receipt exists and original failed CI evidence remains incomplete. |
| repayment-admission | pending-approval | Complete normal master CI succeeded and ordinary repayment admission remains owed. |
| repayment-ready | ready | Ordinary admission approved the unchanged incident behavioral Definition of Done. |
| repayment-active | active | One fresh normal factory claim is admitted. |
| repayment-acceptance | acceptance | The current normal repayment carrier merged and awaits final proof. |
| closed | done | All incident completion requirements below are satisfied. |

Canonical entry MUST preserve the item's original behavioral Definition of Done, or its initially recorded incident behavioral intent until normal grooming authors that section, across all phases. A current attributable regression after closure MUST reopen the same item into reverting, fenced against the closed generation; a completed revert and collected failure evidence permit a new repair phase only with the fresh evidence required below.

Incident entry MUST reuse an existing item or canonically file a minimal identified incident with impact, owner, scope and behavioral intent, recording ordinary model-backed admission and spec debt as deferred to normal repayment. Slow Definition-of-Done/governing-heading judgement, factory capacity, provider probes and green-master preconditions MUST NOT delay that authorized host repair or recorded emergency revert. This is not permission for ordinary implementation to evade admission. A missing tenant MUST use a previously recorded canonical incident id and trusted receipt; it MUST NOT invent a second work-item identity or treat a failed read as absence.

Before local ownership begins, the sanctioned transition MUST record immutable intent, cancel or fence the item's live factory attempt, disarm queued duplicate dispatch and preserve the prior run/claim history. One current generation and operation identity MUST govern writes. Lifecycle mutation exclusion MUST be enforced by a server-side conditional operation available to all tenant writers, never a host-local lock or client read-modify-write. The transition MUST refuse with a named capability error rather than pretend it fenced writers when no such conditional operation is available. Every proof, completion, claim recovery and dispatch effect MUST revalidate current generation immediately before its side effect; a late old run MUST NOT publish proof, consume a claim, merge cleanup or close the item. Recovery intent and receipt reconciliation across tenant failure MUST interoperate with the independently available trusted controller receipt/fence owned by dev-tooling; the plugin MUST reconcile exact receipts back idempotently without creating a second lifecycle truth or requiring the failed tenant to authorize emergency rollback.

A valid incident repair receipt MUST admit only the exact authorized local repair carrier through factory provenance and the retrospective bypass audit; a valid emergency-revert receipt MUST admit only the recorded complete inverse carrier. The receipt MUST record deferred verification honestly and remain distinct from normal factory/TDD proof. Historical validation MUST bind exact PR/head/landed identities after environment and labels disappear. An arbitrary label, caller environment, Factory-Override trailer or code marker alone MUST NOT confer an exception. Workflow-edit authorization remains separately scoped; factory workers MUST retain their existing credential boundary. Normal factory repayment MUST require normal provenance and complete validation.

After the expedited merge's complete normal master CI succeeds, the incident MUST remain unfinished and enter one same-item normal factory repayment. Its eligibility MUST derive from the recorded successful attempt and outstanding repayment, even though an earlier PR already merged. Before dispatch, normal Definition-of-Done and governing-heading admission MUST be completed and deferred spec obligations resolved through their normal owners. Both incident flags MUST be absent before provider selection and before sandbox/hooks/PR execution, including malformed inherited values. The fresh factory run and carrier PR MUST remove the original code/test marker and exercise cumulative original incident paths, relevant tests, deferred validation and spec debt. Acceptance MUST receive that original change/evidence corpus plus follow-up changes, not only marker removal. Cancellation, restart or duplicate delivery MUST resume the same recorded operation rather than create a second repayment run.

A defect found only by deferred factory verification while deployed master remains healthy MUST be repaired in that normal repayment PR without reverting the successful expedited merge solely for the deferred finding. A demonstrated incident-attributable regression on master, another PR or an adopted consumer MUST instead request recovery through the trusted controller and fence stale repayment before a corrected expedited attempt. First-failure recovery semantics belong to the controller contract and MUST NOT be delayed by acceptance classification or ordinary rework budgets. Failed original master runs MUST remain attributable and retained to terminal evidence; a corrected attempt MUST carry fresh repair or measured resolution evidence on the same item, rather than an unchanged reland to retry a broken base.

No accept, reconcile-merged, close/no-change-needed, proof-only resume or automatic completion path MAY discharge an incident from its expedited merge alone. Closure MUST require the current normal factory repayment PR merged, its normal master CI successful, original behavioral proof and manual outcome satisfied, marker removal, repaid spec/verification debt and disposition of related consumer/PR failures. Missing, cancelled or unreadable CI and absent proof MUST remain named outstanding obligations. Incident recovery attempts MUST be accounted separately from ordinary acceptance rework/nonconvergence budgets. Durable incident-to-change attribution MUST survive closure; a later demonstrated related regression MUST reopen the same item, increment/fence the generation and restore recovery plus normal repayment obligations.

Inspection MUST report the item's attempts, owner/generation, current carrier, merge/revert SHAs, CI run identities, skipped work, focused evidence, retained failures, deferred debt, recovery receipts and final normal proof. Readers and installed consumers MUST be released and verified to preserve this context before enablement; developing and adopting this feature MUST use normal gates.

Add the following scenarios to scenarios.md in the same revision. Their descriptive headings are exact References targets for the owning implementation carriers; normal heading registry/debt co-edits remain required when ratified.

## Scenario: an incident keeps one item with explicit current operation ownership

```gherkin
Feature: an incident keeps one item with explicit current operation ownership

  Scenario: an incident keeps one item with explicit current operation ownership
    Given an identified incident item with a queued or live factory attempt
    When the authorized host claims an expedited repair
    Then canonical identity and prior attempt evidence remain on the same item
    And its repair phase is active under the host owner without a factory slot
    And the sanctioned server-side conditional transition fences the old generation and duplicate dispatch
    And a late old run cannot write proof or close the incident
    And absent conditional capability produces a named refusal instead of an apparent fence
```

## Scenario: incident entry defers slow admission without creating another identity

```gherkin
Feature: incident entry defers slow admission without creating another identity

  Scenario: incident entry defers slow admission without creating another identity
    Given an authorized incident repair and a reachable tenant
    When no existing incident item covers its identified scope
    Then canonical intake records its impact owner scope and behavioral intent without slow model judgement
    And ordinary admission and spec debt remain owed before normal factory repayment

  Scenario: Recovery resumes a previously recorded incident during tenant failure
    Given the tenant is unavailable and a trusted canonical incident receipt already exists
    When recovery resumes
    Then that same identity is used without a new item or a fresh dependency on the failed tenant
```

## Scenario: incident provenance exceptions remain exact and repayable

```gherkin
Feature: incident provenance exceptions remain exact and repayable

  Scenario: incident provenance exceptions remain exact and repayable
    Given a recorded incident repair or emergency revert carrier and exact PR head and landed identities
    When provenance and retrospective bypass audit inspect it after its labels and environment disappear
    Then its trusted incident receipt is recognized as deferred verification with normal repayment outstanding
    And an arbitrary flag label trailer or marker does not admit another carrier
    And normal factory repayment still requires normal factory provenance
```

## Scenario: a successful incident merge reenters normal factory on the same item

```gherkin
Feature: a successful incident merge reenters normal factory on the same item

  Scenario: a successful incident merge reenters normal factory on the same item
    Given a merged expedited repair whose complete normal master CI succeeded
    And current ordinary admission is complete for its outstanding repayment
    When the dispatcher resumes the incident
    Then normal repayment admission passes through pending-approval and ready before one active factory claim
    And one fresh normal factory run and carrier PR use the same work-item id with a new phase identity
    And both incident flags are removed before provider and sandbox execution
    And the PR removes the marker while validating cumulative original incident scope and debt
    And restart or duplicate delivery resumes that operation without another repayment run
```

## Scenario: a deferred-proof-only finding is repaired without reverting healthy master

```gherkin
Feature: a deferred-proof-only finding is repaired without reverting healthy master

  Scenario: a deferred-proof-only finding is repaired without reverting healthy master
    Given a successful incident master merge and its normal factory repayment in progress
    When deferred factory verification alone reveals a defect while deployed master remains healthy
    Then that defect is repaired in the repayment PR under normal validation
    And the original successful merge is not reverted solely for that deferred finding
```

## Scenario: incident completion requires final normal proof rather than an old repair merge

```gherkin
Feature: incident completion requires final normal proof rather than an old repair merge

  Scenario: incident completion requires final normal proof rather than an old repair merge
    Given an incident with an earlier expedited merge and a marker-removal follow-up
    When acceptance reconcile-merged close no-change or proof-only resume evaluates it
    Then it grades cumulative original incident behavior and the current normal carrier
    And it leaves the incident unfinished until the normal factory PR and its master CI succeed
    And it requires marker removal manual outcome repaid debt and disposition of related failures
    And missing cancelled or unreadable evidence remains an explicit obligation
```

## Scenario: an attributable regression fences repayment and reopens the same incident

```gherkin
Feature: an attributable regression fences repayment and reopens the same incident

  Scenario: an attributable regression fences repayment and reopens the same incident
    Given an incident whose normal repayment is live or whose item is already closed
    When a related failure on master another PR or an adopted consumer is attributed with change evidence
    Then the same incident item is reopened with a new fenced generation and recovery requested
    And stale cleanup cannot merge or close the corrected attempt
    And failed original CI evidence is retained while a corrected attempt requires new repair or resolution evidence
    And final normal factory repayment remains owed on that item
```

