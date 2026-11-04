---
topic: host-judgement-credential
author: claude:fabro-currency (session 5c3e43cb)
created_at: 2026-10-20T16:05:35Z
---

## Proposal: A host-side Definition-of-Done judgement authenticates as a dispatch would

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

State which Claude subscription credential the Dispatcher's host-side Definition-of-Done judgements authenticate with: the credential the Dispatcher selects for a dispatch it would launch at that moment, never merely the unnumbered credential the environment happens to carry. Add one Gherkin case to Scenario 174 that exercises it. No heading is added, changed or removed.

### Motivation

Work-item bd-ib-y4pyji (coordinator rulings R324 and R201, 2026-10-20). The pre-admission judgement of "Judged before admission" starts its host judge with the inherited environment. Under the credential wrapper, that environment's unnumbered CLAUDE_CODE_OAUTH_TOKEN was the account at its weekly limit. Meanwhile the account-selection process had selected another account, which `dispatcher.py claude-cred-status` reported as usable with HTTP 200 through CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_5. Every filing that afternoon recorded that the pre-admission judgement did not run (judge-command-failed), for a factory that could dispatch. The stopgap host preflight had the same defect and was fixed in PR 3394. The ratified text says nothing about the judge's credential, so bd-ib-y4pyji's Definition of Done had no governing clause, and both dod_gate candidates refused it on exactly that ground.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Dispatcher admission, WIP cap, and post-merge acceptance", in the paragraph that begins "**Judged before admission.**", insert after its first sentence: "When that judgement runs a Claude model on the host, it MUST authenticate with the Claude subscription credential the Dispatcher selects for a dispatch it would launch at that moment, which is the account-selection process's selected account when one is published and its credential is present, and otherwise the unnumbered credential. It MUST NOT authenticate solely with the unnumbered credential the environment carries while a selected account's credential is present. When it falls back to the unnumbered credential, it MUST say so on stderr, naming the reason. The same rule governs the pre-dispatch judgement of the paragraph that follows."

In SPECIFICATION/scenarios.md, inside the gherkin block of "## Scenario 174 — The Definition-of-Done judgement runs before admission and holds an item it would rest at needs-human", append these two cases after the last existing case. The heading MUST NOT change, so tests/heading-coverage.json needs no edit:

```gherkin
  Scenario: The judgement authenticates with the account a dispatch would use
    Given the account-selection process has published a selected account whose credential is present in the environment
    And the environment's unnumbered Claude credential names a different account
    When the pre-admission judgement runs its Claude model on the host
    Then the judge is started with the selected account's credential
  Scenario: The judgement falls back to the unnumbered credential and says so
    Given no account selection is published
    When the pre-admission judgement runs its Claude model on the host
    Then the judge is started with the unnumbered Claude credential
    And one stderr line names that fallback and its reason
```
