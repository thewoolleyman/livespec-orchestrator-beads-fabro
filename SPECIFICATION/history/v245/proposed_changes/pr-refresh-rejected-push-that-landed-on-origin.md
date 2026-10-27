---
topic: pr-refresh-rejected-push-that-landed-on-origin
author: claude-opus-5-5
created_at: 2026-10-24T01:34:49Z
---

## Proposal: pr-refresh-rejected-push-landed-on-origin

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

When the forge rejects pr_refresh's leased push, pr_refresh MUST read origin's publish branch once more before naming a cause. If origin points at the exact pushed head, the write landed and the stage fails closed with a landed-but-errored cause naming the forge's error text, the pushed head and the pull request ref's head, and does not report LIVESPEC_PR_REFRESH_LEASE_FAILED. If origin points at neither the leased head nor the pushed head, the stage reports LIVESPEC_PR_REFRESH_LEASE_FAILED and routes to needs_human as today. If origin cannot be read, the stage reports an unobservable write outcome instead of a lease failure. The clause lands in the "Scripted publication and proof-head integrity" paragraph of §"Self-contained plugin dispatch" in contracts.md, and three new scenarios go inside the existing Scenario 184 of scenarios.md.

### Motivation

The generalization target is §"Self-contained plugin dispatch" in SPECIFICATION/contracts.md, specifically its "Scripted publication and proof-head integrity" paragraph. That paragraph requires pr_refresh to fail closed with a named cause on a missing or unobservable remote or on a foreign or unexpectedly changed publish head, and it lets a completed refresh be recognized from matching remote state. No clause says what pr_refresh must report when its leased push is rejected, so the stage reports every rejection as LIVESPEC_PR_REFRESH_LEASE_FAILED, whose text says the remote moved after it was observed or origin refused the write. Work item bd-ib-bu553k measured the cost on 2026-10-23 on bd-ib-57ss2n, run 01M5MKDXDNTNVYPT2FV8M0EJ9D: pr_refresh rebased the run's 11-commit series onto master as 4da85970 and pushed it with a lease against ca0fbf38. GitHub answered "remote: fatal error in commit_refs" and reported the ref as remote rejected. The stage emitted LIVESPEC_PR_REFRESH_LEASE_FAILED and the run ended needs_human after 123 minutes of otherwise green work, with a VERIFIED Proof of Done on PR 3552. The remote had not moved and nothing else had pushed: git ls-remote showed the publish branch at 4da85970, the run's own pushed head, while refs/pull/3552/head stayed at ca0fbf38 and 4da85970 had no check-runs, so GitHub wrote the ref but never processed the push event. The misreport sends triage after a phantom second pusher, and it hides that the publish branch and the pull request disagree, which also blocks `dispatcher resume --item` until a human repairs the branch. A lease miss and a forge-internal failure on a write that landed have different remedies, so the stage must measure where the ref points before it names the cause. The three cases of the proposed clause are the work item's three Definition-of-Done bullets, and the work item's References line names Scenario 184, whose scenarios already govern pr_refresh's behaviour, as the scenario home.

### Proposed Changes

Two coordinated edits. Both MUST land together in a single revision.

**1. `SPECIFICATION/contracts.md` §"Self-contained plugin dispatch", the "Scripted publication and proof-head integrity" paragraph.** The paragraph currently reads, in part:

> A rewrite MUST use an explicit lease against the recorded remote head of this run's own publish branch. Hooks MUST run normally. It MUST NOT use bare force, `--no-verify`, or rewrite another ref.

Immediately after the sentence "It MUST NOT use bare force, `--no-verify`, or rewrite another ref." and before the sentence beginning "A changed head MUST take the decision of", insert:

```
When the forge rejects that leased push, `pr_refresh` MUST read origin's
publish branch once more before it names a cause, because a rejection is the
forge's report about the write and not a measurement of where the ref now
points. Here the leased head is the recorded remote head the lease was taken
against, and the pushed head is the refreshed head the push carried. When
origin's publish branch then points at the exact pushed head, the write
landed although the forge reported an error, and `pr_refresh` MUST fail
closed with the named cause `LIVESPEC_PR_REFRESH_PUSH_LANDED_ERRORED`, whose
detail MUST name the forge's error text, the pushed head, and the head of the
run's pull request ref (`refs/pull/<number>/head`) as origin reports it, and
MUST state that the publish branch and the pull request may disagree. In that
case `pr_refresh` MUST NOT report `LIVESPEC_PR_REFRESH_LEASE_FAILED` and MUST
NOT state that the remote moved or that another writer pushed. When origin's
publish branch then points at neither the leased head nor the pushed head,
`pr_refresh` MUST report `LIVESPEC_PR_REFRESH_LEASE_FAILED` and route to
`needs_human` exactly as it does for a lease failure today. When origin's
publish branch points at the leased head, the write did not land, and
`pr_refresh` MUST keep its existing lease-failure cause and routing; this
paragraph does not change that case. When origin's publish branch cannot be
read after the rejection, `pr_refresh` MUST fail closed with the named cause
`LIVESPEC_PR_REFRESH_PUSH_OUTCOME_UNOBSERVABLE`, stating that whether the
write landed cannot be established, and MUST NOT report
`LIVESPEC_PR_REFRESH_LEASE_FAILED`. A head of the pull request ref that
cannot be read MUST be named as unobservable in the landed-but-errored detail
and MUST NOT change which of these causes is reported. Each of these causes
MUST carry the recovery artifact pointer this paragraph already requires.
Scenario 184 in `scenarios.md` exercises these sentences.
```

**2. `SPECIFICATION/scenarios.md` §"Scenario 184 — The default branch advancing between pr_refresh and the arming re-enters pr_refresh, and an armed pull request it overtakes rests at needs-human with a named cause".** Inside that scenario's single `gherkin` fenced block, immediately after the last scenario, "A merge-hold release cannot arm a head that no proof record names" (whose last step is "Then the release refuses, naming the head comparison that failed, and the pull request stays unarmed"), and before the block's closing fence, insert:

```gherkin
  Scenario: A rejected refresh push that landed on origin is reported as a landed-but-errored write
    Given a run whose pr_refresh rebased its series onto the default branch as pushed head P and pushed it with a lease against leased head L
    And the forge rejects the push with the error text "fatal error in commit_refs"
    And origin's publish branch afterwards points at P while the pull request ref's head is still L
    When pr_refresh names the cause of the rejected push
    Then it fails closed with LIVESPEC_PR_REFRESH_PUSH_LANDED_ERRORED, and its detail names the forge's error text, the pushed head P and the pull request ref's head L
    And it does not report LIVESPEC_PR_REFRESH_LEASE_FAILED and does not state that the remote moved

  Scenario: A rejected refresh push with origin at neither head is still a lease failure
    Given a run whose pr_refresh pushed head P with a lease against leased head L
    And the forge rejects the push
    And origin's publish branch afterwards points at a head that is neither L nor P
    When pr_refresh names the cause of the rejected push
    Then it reports LIVESPEC_PR_REFRESH_LEASE_FAILED and the run routes to needs_human as it does today

  Scenario: A rejected refresh push whose outcome cannot be read is reported as unobservable
    Given a run whose pr_refresh pushed head P with a lease against leased head L
    And the forge rejects the push
    And origin's publish branch cannot be read afterwards
    When pr_refresh names the cause of the rejected push
    Then it fails closed with LIVESPEC_PR_REFRESH_PUSH_OUTCOME_UNOBSERVABLE, stating that whether the write landed cannot be established
    And it does not report LIVESPEC_PR_REFRESH_LEASE_FAILED
```

No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.
