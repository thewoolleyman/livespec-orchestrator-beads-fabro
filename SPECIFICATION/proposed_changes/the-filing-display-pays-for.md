---
topic: the-filing-display-pays-for
author: claude-opus-5-5
created_at: 2026-11-13T16:58:12Z
---

## Proposal: The filing display reuses a recorded governing-heading verdict and records the one it takes

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The shared spec-stated judgement component already names the filing-time reference advisory as a consumer, and it reuses a governing-heading verdict only while that verdict's input and clause provenance are unchanged. But nothing requires `filing_display` to consult a recorded verdict, to record the one it takes, or to record nothing when no verdict was taken, and the pre-admission and pre-dispatch judgements have no recorded display verdict to reuse. This proposal makes the filing display a taking of the governing-heading verdict on the same terms as the two host judgements, and adds Scenario 368 to exercise it.

### Motivation

Work item bd-ib-3h7dsf (plan anthropic-burn-mitigation, epic bd-ib-b2jzxw, plan assertion 5: a statement and governing heading whose texts are unchanged since their last judgement are not sent to a model again) was held at spec-change tier at 2026-11-13T16:51:51Z on spec v369. The spec-stated verdict on its asked-for behaviour was partial, with generalization target ## Dispatcher admission, WIP cap, and post-merge acceptance. The verdict's rationale names exactly the gap filled here: the paragraph names the advisory as a consumer and states the reuse rule, but does not require filing_display to reuse or append a recorded verdict, does not state the no-record-on-no-verdict rule, and does not state cross-surface reuse by the pre-dispatch judgement. Spend evidence, reported by legacy-coordinator-agent for the 48 hours to about 2026-11-07T17:26Z: about $50 of $132 of headless judgement spend was repeats of an already-judged statement (452 calls), because every filing display takes a fresh judgement. The no-record-on-no-verdict rule protects against the false-clean class of bd-ib-dltgs5: a verdict that was not taken must never read as one that found nothing. The implementation is on preserved tree refs/heads/needs-human/31c7429f4b41417daf1b4a6153bf35aa (PR #5161), with full checks passed and the proof captured. In-flight survey, 2026-11-13: no live spec branch or open spec PR touches this paragraph; the only lexical hits are on branches 1,100 or more commits behind master. Relationship: align.

### Proposed Changes

In `contracts.md` §"Dispatcher admission, WIP cap, and post-merge acceptance", in the paragraph "**The spec-stated judgement is one shared component.**", insert the following immediately after the sentence that ends "... because this component answers only the two questions above.":

> The filing display (`filing_display`, the filing-time reference advisory that every filing front-end runs after an item is filed) MUST be a taking of the governing-heading verdict on the same terms as the pre-admission and pre-dispatch judgements. Before it takes a governing-heading verdict for an assertion, the display MUST look for a recorded governing-heading verdict on the item that this paragraph's reuse rule allows, whether an earlier display, the pre-admission judgement or the pre-dispatch judgement recorded it. When it finds one, it MUST use that verdict and MUST NOT start a judge candidate for it. When the display takes a verdict and the taking yields a usable verdict, it MUST append to the item exactly one governing-heading verdict record. That record MUST carry the governing-heading subject digest and the clause provenance this paragraph defines, so that a later display, the pre-admission judgement and the pre-dispatch judgement MAY reuse it under the same rule. A taking that yields no usable verdict MUST NOT append a record, so the next display of the unchanged item takes a verdict again. That covers a taking discarded by its evidence check, ended by the input bound, or failed. A verdict that was not taken MUST NOT be recorded or displayed as one that found nothing. The display's record MUST be a governing-heading record only. No taking's reuse of a recorded Definition-of-Done outcome MAY read it as the enclosing judgement's outcome, and the opposite-verdict journal of Scenario 240 MUST NOT count it as a taking. Like every record whose first line begins with `livespec-dod-judgement`, it MUST be omitted from every subject digest, so appending it MUST NOT invalidate the verdict it records. The display MUST still never refuse. When it cannot read the item's comments, it MUST take a verdict as though none were recorded. When it cannot append its record, it MUST still print every display line from the verdict it took. A caller that supplies its own governing-heading reader MUST keep exactly that reader. A standing `release-spec-tier` attestation MUST outrank a recorded verdict at the display exactly as it does at the pre-dispatch judgement. Scenario 368 in `scenarios.md` exercises this rule.

In `scenarios.md`, add after the last scenario:

~~~markdown
## Scenario 368 — The filing display reuses a recorded governing-heading verdict and records the one it takes

```gherkin
Feature: Filing display governing-heading verdict reuse

  Scenario: A second display of an unchanged item takes no judgement
    Given a filed item whose first filing display took a usable governing-heading verdict and appended its record
    And the item's statement, Definition of Done, rider comments and selected clauses are unchanged since then
    When the filing display runs on the item again
    Then it starts no judge candidate
    And it prints the same finding lines as the first display

  Scenario: The display and the host judgements reuse each other's recorded verdicts
    Given an item carrying a governing-heading verdict recorded by the pre-dispatch judgement, with its subject digest and clauses still current
    When the filing display runs on the item
    Then it starts no judge candidate
    Given an item carrying a governing-heading verdict recorded by the filing display, with its subject digest and clauses still current
    When the pre-dispatch Definition-of-Done judgement runs on the item
    Then it reads that verdict from the record and starts no governing-heading judge candidate

  Scenario Outline: A changed input takes the verdict again
    Given an item carrying a governing-heading verdict recorded by the filing display
    And <change> since that verdict was recorded
    When the filing display runs on the item
    Then it starts exactly one judge candidate

    Examples:
      | change                                                    |
      | the item's statement was edited                           |
      | the item gained a rider comment                           |
      | a clause the verdict was judged against changed its body  |

  Scenario: A display that took no usable verdict records nothing
    Given a filing display whose governing-heading taking was discarded by its evidence check
    When the display ends
    Then it appended no record to the item
    And the next display of the unchanged item starts one judge candidate

  Scenario: A ledger fault does not stop the display
    Given a filing display that cannot read the item's comments and cannot append its record
    When the display runs on the item
    Then it takes a verdict and prints every display line from that verdict
```
~~~

The revise that ratifies this proposal MUST add a `tests/heading-coverage.json` entry for the new `## Scenario 368 — ...` heading in the same change, per the repository's revise co-edit discipline. If another revision has taken the number 368 by then, the revise MUST renumber this scenario to the next free number and update the paragraph's reference to match.

## Proposal: A host Claude judgement's spend-journal header names its work item and the full prompt's digest

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The host spend journal's header carries only the first 2,000 characters of the prompt, so a spend reader cannot tell which work item a judgement was taken for, and cannot tell two prompts that share their first 2,000 characters apart. Repeat judgements of one statement therefore can only be counted by proxy. This proposal adds a `work_item_id` field, written when the judgement is taken for a work item, and a `first_prompt_sha256` field over the full prompt. It also adds one scenario to Scenario 332.

### Motivation

Same work item bd-ib-3h7dsf (DoD bullet 9). The 2026-11-07 spend count behind it estimated 452 repeat calls (about $50) only by proxy, because the journal held no item id and its 2,000-character first_prompt cannot tell two prompts apart. The implementation on preserved tree needs-human/31c7429f writes exactly these two keys: work_item_id when the judgement is taken for a work item, and first_prompt_sha256 as the lowercase hex SHA-256 of the full prompt's UTF-8 bytes. Its captured proof showed the digest equal to sha256sum of a 3,000-character prompt while first_prompt held 2,000 characters.

### Proposed Changes

In `contracts.md` §"Bounded session waits and observable inventory", in the paragraph "**A host Claude judgement journals its spend, ending with its final usage.**", after the sentence "`name` MUST be `purpose:<caller>@<working directory name>`, ...", insert:

> The header MUST also carry `first_prompt_sha256`: the lowercase hexadecimal SHA-256 digest of the UTF-8 bytes of the WHOLE prompt, not of the truncated `first_prompt`. When the judgement is taken for a work item, the header MUST also carry that item's id as `work_item_id`. When it is not, the header MUST NOT carry `work_item_id`. A spend reader MAY group journals by `work_item_id` and `first_prompt_sha256` to count repeated judgements of one unchanged prompt exactly.

In `scenarios.md`, in `## Scenario 332 — A host Claude judgement's spend journal ends with the closing result event's final usage`, append this scenario inside the existing gherkin block:

```gherkin
  Scenario: A judgement taken for a work item names the item and the full prompt's digest
    Given a host model judgement whose resolved candidate is the Claude agent, taken for work item bd-ib-example with a prompt of 3000 characters
    When the judgement starts
    Then its journal's header carries "work_item_id": "bd-ib-example"
    And its first_prompt_sha256 equals the SHA-256 digest of all 3000 characters of the prompt
    And its first_prompt carries only the prompt's first 2000 characters
```

This adds no new H2 heading, so `tests/heading-coverage.json` needs no new entry for it.
