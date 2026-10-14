---
topic: pr-refresh-reproof-relevance
author: claude-opus-5-5-plan-pr-refresh-reproof-relevance
created_at: 2026-10-14T04:42:04Z
---

## Proposal: Carry a verified Proof of Done across a pr_refresh whose incoming commits cannot affect it, and re-prove otherwise

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A changed-head pr_refresh that applied cleanly, without a refresh-repair round, carries the run's verified Proof of Done forward to the new head when a deterministic, conservative relevance rule classifies every incoming default-branch path as inert for the item and the rebased item diff has the same stable patch identity as the verified one; it re-proves through proof_capture, review and proof_verify whenever the rule finds a relevant path, a differing diff, or an input it cannot read. Every changed-head pr_refresh posts one decision record on the pull request (carried_forward or reproof_required) naming the verified head, the new head, the incoming range and the deciding inputs, and pr accepts a carried_forward record naming exactly the head it publishes. No language model takes part in the decision.

### Motivation

The maintainer ruled on 2026-10-14: "If the changes were not likely to be relevant or cause a difference in the definition of done, no need to re-run proof", and called it a high-priority factory-throughput fix (plan pr-refresh-reproof-relevance, epic bd-ib-ku7phe, research note 001; spec-change child bd-ib-3k7c2z carries this filing). Today the paragraph 'Scripted publication and proof-head integrity' sends EVERY changed head back to proof_capture, and the pr paragraph forbids reusing a verified record across a head change; the workflow's pr_refresh_head node implements that without looking at what the rebase brought in. On hp, run 01M4VSTCF4GWH9JWC53AEE0BP1 (bd-ib-t4dtx4, a one-bullet AGENTS.md change) was verified by 00:47Z and then spent two re-proof laps, 25.2 minutes, after refreshes that brought in only plan/ research notes, before a third refresh failed its gate; across 2026-10-11 to 2026-10-14, 4 of the 5 runs that reached pr_refresh hit HEAD_CHANGED, spending 5 laps and 64.1 minutes of capture, review and verify. With master merging up to six pull requests an hour, each 25-minute lap gives master time to move again, raising the chance of the next refresh and of exhausting the three-refresh bound. pr_refresh already re-runs the repository-declared gate on the rebased head, so gate correctness is re-established either way; the only open question is whether the verified observations could differ on the new head. Design decisions resolved in this proposal: (a) the rule is an ALLOWLIST of inert path classes, not a denylist of relevant paths, because an incoming change to code the item merely imports can change behaviour an assertion observes without touching any path the item names; carry-forward therefore requires every incoming path to be inert, and everything else re-proves. (b) The built-in inert classes are the plan store (plan/) and every spec tree's frozen history snapshots (<spec-root>/history/); both are prose records no runtime path executes. Live spec files and proposed_changes/ are deliberately NOT inert, because operations such as next, doctor and the Spec Reader read them at runtime; widening the set is a later revise, and no configuration key widens it, so the rule cannot be loosened per repository without ratification. (c) A class becomes relevant for an item whose own diff, Definition of Done section, References line or verified reproduction steps names that class root or any path beneath it, so an item that is ABOUT plan notes or history snapshots always re-proves. (d) Diff equality uses the stable patch identity of the item's whole diff against its base, compared with the diff the verified record was taken on, so a chain of carry-forwards is always measured against the originally verified diff, never against the previous carry. (e) A conflicted or gate-rejected refresh keeps v134's refresh-repair route, whose repaired head always re-proves; carry-forward applies only to a clean refresh. Alternatives rejected: an LLM relevance judgement (non-deterministic and unauditable, excluded by the maintainer); re-proving only when an incoming path is named by the Definition of Done (unsafe for imported code); skipping only review while still re-running capture and verify (saves under a third of the lap). Coordination: plan publish-draft-green-work-loss (epic bd-ib-acrr56) landed v134's 'Refresh repair' and 'Refresh-repair accounting' paragraphs in the same sub-section; this proposal is written against the v134 text on master (db4ec6aa) and leaves both paragraphs unchanged. The scenario number 178 is the next free number after Scenario 177.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Self-contained plugin dispatch", sub-section "Definition-of-Done and Proof-of-Done stages":

(1) In the paragraph beginning "**The stages.**", replace "`proof_capture`, entered from `publish_draft` or a changed-head `pr_refresh` and exiting only to `review`;" with: "`proof_capture`, entered from `publish_draft` or from a changed-head `pr_refresh` whose decision is `reproof_required` (\"Proof carry-forward across a refresh\" below) and exiting only to `review`;".

(2) In the paragraph beginning "**Scripted publication and proof-head integrity.**", replace the sentence "A changed head MUST return to `proof_capture`, then `review` and `proof_verify`; only proof for the new head can reach final publication." with: "A changed head MUST take the decision of \"Proof carry-forward across a refresh\" below: on `reproof_required` the run MUST return to `proof_capture`, then `review` and `proof_verify`, and on `carried_forward` it MUST proceed to `pr`; in either case only a proof record naming the new head — a `verified` record taken on it, or a `carried_forward` record carrying an earlier `verified` record to it — can reach final publication."

(3) Insert a new paragraph immediately after the paragraph beginning "**Refresh-repair accounting.**" and before the paragraph beginning "`pr` MUST query the exact pull request":

"**Proof carry-forward across a refresh.** When `pr_refresh` has refreshed the run onto an advanced default branch cleanly — the rebase applied without conflict, the repository-declared gate passed, the leased push succeeded, and no refresh-repair round ran during this visit — and the head changed, the stage MUST decide, before routing, whether the run's verified proof still covers the new head. The decision MUST be computed by a deterministic rule from repository and record state alone; no language-model judgement MAY take part in it. Its inputs are: the *verified record*, the latest `verified` record on the pull request attributable to this run (including identifiers a resume links to it); the *verified head* and *verified base*, the head that record names and that head's merge base with the default branch; the *previous base* and *new base*, the default-branch commits the run was based on before and after this refresh; the *new head*; the *incoming paths*, every path added, modified, deleted or renamed (both names) between the previous base and the new base; the *item's named paths*, every path changed by the item's diff from the verified base to the verified head, together with every repository path or directory named in the item's Definition of Done section, its `References:` line, and the numbered reproduction steps of the verified record; and the *inert classes*, which are exactly the plan store `plan/` and the frozen history directory `<spec-root>/history/` of every spec tree the repository governs. An inert class is *named by the item* when any item's named path equals its root or lies beneath it. The decision MUST be `carried_forward` only when all of the following hold: every incoming path lies beneath an inert class that is not named by the item; and the stable patch identity of the item's diff from the new base to the new head equals the stable patch identity of the item's diff from the verified base to the verified head. Otherwise the decision MUST be `reproof_required`, and it MUST be `reproof_required` naming the input when any input cannot be read or computed — the verified record absent or unparseable, a base or head unresolvable, a path list or patch identity that cannot be computed. A refresh that took a refresh-repair round never reaches this decision: its repaired head re-enters `janitor`, `publish_draft` and `proof_capture` as \"Refresh repair\" requires. Before routing, the stage MUST post exactly one decision record on the pull request through the posting primitive of §\"Proof of Done record\": a `carried_forward` or `reproof_required` record naming the decision, the verified record's comment link, the verified head, the previous published head, the new head, the incoming range `<previous base>..<new base>` with its incoming paths, both patch identities, and, for `reproof_required`, each input that decided it — each relevant incoming path with the reason it is relevant, the differing patch identities, or the input that could not be read. A `carried_forward` decision whose record cannot be posted MUST be treated as `reproof_required`, and the stage output MUST name the failed post; a `reproof_required` decision still routes to `proof_capture` when its record cannot be posted, and the stage output MUST name the failed post. The verified head of a later carry-forward in the same run is still the head of the verified record, so a chain of carry-forwards is always measured against the diff that was actually verified. A carry-forward consumes no review-fix round and leaves the three-refresh non-convergence bound unchanged. Scenario 178 in `scenarios.md` exercises this paragraph."

(4) In the paragraph beginning "`pr` MUST query the exact pull request", replace "verify its current head against the head whose proof was verified," with "verify its current head against the head named by the latest record of this run that is either `verified` or `carried_forward`, and MUST refuse to mark the draft ready for a head that no such record names,"; and replace the sentence "A later head change requires fresh proof; publication MUST NOT reuse a verified record from before that change." with: "A later head change requires fresh proof or a `carried_forward` record for that head; publication MUST NOT reuse a verified record from before that change except through a `carried_forward` record that names the head being published."

In SPECIFICATION/contracts.md, section "Self-contained plugin dispatch", sub-section "Proof of Done record":

(5) In the paragraph beginning "**The record.**", add `carried_forward` and `reproof_required` to the first-line verdict enumeration, so it reads `<captured|not_captured|verified|not_reproduced|carried_forward|reproof_required|host_recorded|host_verified|host_not_reproduced|human_attested>`; add `carried_forward` and `reproof_required` to the parenthesised list of factory records that MUST name the full commit sha of the publish-branch head, where for both the named head is the new head; and insert after the sentence that defines `not_captured`: "`carried_forward` and `reproof_required` are the decision records of a changed-head `pr_refresh` (§\"Definition-of-Done and Proof-of-Done stages\" → \"Proof carry-forward across a refresh\"); their body carries the decision inputs that paragraph names in place of per-assertion reproduction steps, and a `carried_forward` record MUST link the `verified` record it carries. A `carried_forward` record anchors a resume exactly as the `verified` record it carries would, at the new head it names. A `reproof_required` record is not proof: it MUST NOT anchor a resume, and the acceptance pass and every reader of the latest proof record MUST skip it."

(6) In the paragraph beginning "**The pointer.**", after "its run id and timestamp, its verdict," insert "— when the merged head was reached through a carry-forward — the comment link of the `carried_forward` record naming that head,"; and add `carried_forward` to the parenthesised list of record kinds for which a stale pointer is judged against the latest record OF THE SAME KIND.

In SPECIFICATION/contracts.md, section "Dispatcher loop invocation surface", sub-section "Resume from a published pull request":

(7) Replace "a changed-head `pr_refresh` MUST run fresh capture, review and replay even if those nodes completed on the earlier head." with: "a changed-head `pr_refresh` MUST take the decision of §\"Definition-of-Done and Proof-of-Done stages\" → \"Proof carry-forward across a refresh\", and on `reproof_required` MUST run fresh capture, review and replay even if those nodes completed on the earlier head."

In SPECIFICATION/scenarios.md:

(8) In Scenario 132, sub-scenario "Slow hooks after a post-draft rebase are command work", insert after the line "And the default branch advanced after publish_draft" the line "And an incoming commit changes a path outside every inert class"; the remaining lines MUST stay unchanged.

(9) In Scenario 142, sub-scenario "A resumed publication refreshes proof after a changed head", insert after the line "And origin still names that head but the default branch has advanced" the line "And an incoming commit changes a path outside every inert class"; the remaining lines MUST stay unchanged.

(10) Append a new scenario after Scenario 177:

## Scenario 178 — A refresh that brings in only inert paths carries the verified proof forward, and anything else re-proves

```gherkin
Feature: A pr_refresh re-proves only when the incoming commits could change what the proof observed
  As the maintainer of a repository dispatched to the factory
  I want a verified proof carried across a refresh whose incoming commits cannot affect it
  So that a run is not sent round capture, review and replay for changes it cannot observe

  Scenario: A refresh that brings in only plan notes carries the proof forward
    Given a run whose proof was verified on its published head V, for an item whose diff and Definition of Done name only AGENTS.md
    And the default branch advanced with commits that change only paths beneath plan/
    When pr_refresh rebases the branch cleanly, the gate passes and the leased push yields head N
    Then the pull request carries one carried_forward record naming V, N, the incoming range, its paths and both patch identities
    And the run proceeds from pr_refresh to pr without visiting proof_capture, review or proof_verify
    And pr marks the draft ready for head N

  Scenario: An incoming change outside the inert classes re-proves
    Given a run whose proof was verified on its published head V
    And the default branch advanced with a commit that changes a Python module the item does not touch
    When pr_refresh rebases the branch cleanly and pushes head N
    Then the pull request carries one reproof_required record naming that module as a relevant incoming path
    And the run enters proof_capture for head N, then review and proof_verify, before pr

  Scenario: An inert class the item names is relevant
    Given a run whose item's Definition of Done names a file beneath plan/
    And the default branch advanced with commits that change only paths beneath plan/
    When pr_refresh rebases the branch cleanly and pushes head N
    Then the reproof_required record names plan/ as an inert class named by the item
    And the run enters proof_capture for head N

  Scenario: A rebased diff that differs from the verified diff re-proves
    Given a run whose proof was verified on head V
    And the default branch advanced with commits that change only paths beneath plan/
    When the rebased item diff's stable patch identity differs from the verified diff's
    Then the reproof_required record names both patch identities
    And the run enters proof_capture for the new head

  Scenario: An unreadable input re-proves and names the input
    Given a changed-head pr_refresh whose verified record cannot be parsed
    When the stage decides whether the proof covers the new head
    Then the decision is reproof_required and the record names the unparseable verified record as the unreadable input
    And the run enters proof_capture

  Scenario: A repaired refresh is never carried forward
    Given a pr_refresh whose rebase conflicted and took a refresh-repair round
    When the repaired run is published again
    Then no carried_forward record is posted for the repaired head
    And the run passes proof_capture, review and proof_verify before pr_refresh runs again

  Scenario: A second carry-forward is measured against the verified diff
    Given a run that carried its proof from verified head V to head N1
    And the default branch advanced again with commits that change only paths beneath plan/
    When pr_refresh pushes head N2
    Then the carried_forward record for N2 names V as the verified head and compares N2's patch identity with V's
    And pr marks the draft ready for head N2

  Scenario: pr refuses a head no proof record names
    Given a run whose latest verified record names head V and whose pull request carries no carried_forward record for head N
    When pr runs with the pull request at head N
    Then pr does not mark the draft ready and fails closed naming head N
```

The revise pass MUST add a `tests/heading-coverage.json` entry for the new Scenario 178 heading (test "TODO" with a reason naming work-item bd-ib-v4exlm, which implements the rule and owns that binding) in the same change, and MUST carry the matching `tests/heading-coverage-debt.json` row if that register requires one for a new TODO entry.
