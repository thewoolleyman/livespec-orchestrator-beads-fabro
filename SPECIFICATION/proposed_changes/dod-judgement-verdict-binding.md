---
topic: dod-judgement-verdict-binding
author: claude-opus-5-5
created_at: 2026-10-22T09:59:59Z
---

## Proposal: Every host taking of the Definition-of-Done judgement records its verdict and reuses a recorded verdict on identical digests, and any two opposite verdicts on identical digests are journaled

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

v201 ("One rubric, one subject") makes every taking of the Definition-of-Done judgement grade one rubric over one subject, and keys pre-dispatch reuse on the subject and rubric digests. A shared rubric and subject cannot stop one judge from returning opposite verdicts on identical inputs, and two measured instances on 2026-10-22 show exactly that. This proposal defines a TAKING as one invocation of the judgement: a repository preflight run over its whole candidate chain, one pre-admission judgement, one pre-dispatch judgement, or one run's dod_gate node. Every taking records one judgement record carrying both digests, its outcome, and each candidate's outcome where it ran a chain. Every judgement record is excluded from the subject, so recording a verdict never changes the digest it was taken on. The earliest completed host verdict (a pass or a refusal, never a did-not-run record) whose two digests match the current ones binds every later host taking, which returns it without running any judge. The node still runs on every run, and its records never answer a host lookup. The Dispatcher journals dod-judgement-disagreement whenever any two takings, or two candidates within one taking, return opposite outcomes on identical digests.

### Motivation

Coordinator ruling R595b, recorded on bd-ib-gob6gl. The two instances show one judge flipping on unchanged input, which v201 does not address because v201 only makes the takings grade the same thing. Evidence 5: livespec-dev-tooling-ggoyiq, unchanged Definition-of-Done text. The host preflight said at 06:00Z "do NOT move A1/A2; the GateCommandRunner seam proves them" and REFUSED at 09:02Z with "move A1/A2 to Host-captured". Evidence 6: bd-ib-gob6gl on 2026-10-22, recorded on that item. The codex-acp leg of the preflight demanded at 09:25Z that all twelve assertions be host_captured. At 09:40Z it PASSED the eleven factory_captured bullets, byte-identical to the earlier draft. Each flip cost a relaunch or a re-authoring round. Under v201 alone, the repository preflight records nothing and reuses nothing, so every relaunch re-rolls the judge. A refusal can follow a pass, or a pass can follow a refusal that a human already acted on. Binding the first recorded verdict per digest pair turns a nondeterministic judge into a deterministic gate for the life of that text. A wrong first verdict is answered the way every Definition-of-Done refusal already is: the human edits the section, which changes the subject digest and takes a fresh judgement. The node keeps its every-run duty (contracts.md, the dod_gate paragraph: "neither earlier judgement removes or replaces the node"), so a cached host PASS can still be refused in-run. The widened disagreement record makes each such case, and each host-versus-host flip that a race lets through, measurable rather than anecdotal.

### Proposed Changes

**1. `SPECIFICATION/contracts.md`, the paragraph "One rubric, one subject".** In the GOAL bullet, replace "every ledger comment except the Dispatcher's own Definition-of-Done judgement records (verdict, did-not-run and disagreement comments). Those records are receipts, not brief, so the Dispatcher MUST omit them from the node's rendered goal as well." with:

> every ledger comment except the Definition-of-Done JUDGEMENT RECORDS: each comment whose first line begins with `livespec-dod-judgement`, whichever taking or surface wrote it (verdict, did-not-run and disagreement records alike). Those records are receipts, not brief, so the Dispatcher MUST omit them from the node's rendered goal as well, and recording one MUST NOT change any subject digest.

Then replace the sentence beginning "When a run's `dod_gate` node refuses an item whose most recent pre-dispatch verdict admitted the same subject digest under the same rubric digest," through "The item MUST rest exactly as any `dod_gate` refusal rests it." with:

> A TAKING is one invocation of the judgement: one repository preflight run, one pre-admission judgement, one pre-dispatch judgement, or one run's `dod_gate` node. The first three are HOST TAKINGS. A repository preflight that runs a chain of candidate judges is ONE taking. When every candidate returns a verdict, its outcome is a pass only when every candidate passes, and otherwise a refusal carrying the refusing candidates' findings. When any candidate cannot return a verdict (no eligible model, a timeout or an unparseable reply), the taking did NOT run: it returns no verdict, the preflight exits with its cannot-run code `2`, and the record it appends is a did-not-run record naming that candidate and the cause. A did-not-run outcome is never a refusal. The pre-admission and pre-dispatch takings keep their ratified did-not-run routes unchanged. Every taking that runs a judge MUST cause one judgement record to be appended to the item. For a host taking, the taking appends it. For the node, the Dispatcher appends it when it reads the run's `dod_gate` outcome, whether that is a pass or a refusal. Each record names the taking (and the run, for the node), the subject digest, the rubric digest, the outcome with any findings, and, for a chain, each candidate with its outcome. Records are ordered by their ledger creation time, ties broken by comment id. A CACHE-ELIGIBLE record is a host taking's completed verdict record, a pass or a refusal. Did-not-run records, node records and disagreement records are never cache-eligible. Before running any judge, a host taking MUST look for the earliest cache-eligible record whose subject digest and rubric digest both equal its own. When one exists, the taking MUST return that record's outcome as its verdict, MUST name the record as reused, MUST NOT run any judge or candidate, and MUST NOT append a record. Node records MUST NOT answer a host lookup, and no record ever answers the node, which runs on every run. Whenever two records on an item carry identical subject and rubric digests and opposite outcomes, whichever takings wrote them, or one record's candidates returned opposite outcomes, the Dispatcher MUST append one `dod-judgement-disagreement` row to the dispatch journal and one judgement record of that kind on the item. Each MUST name both digests, the two takings or candidates, each outcome's timestamp, the run where the node is one of them, and each refusal's findings. The Dispatcher MUST record each distinct disagreement exactly once. An item refused by the node MUST rest exactly as any `dod_gate` refusal rests it.

**2. `SPECIFICATION/contracts.md`, the "Judged again before dispatch" paragraph.** Replace "The Dispatcher MUST reuse the most recent verdict recorded for the item, the pre-admission verdict or an earlier pre-dispatch verdict, while that verdict's subject digest and rubric digest both equal the digests of the subject and rubric this dispatch would grade (\"One rubric, one subject\")," with "The Dispatcher MUST reuse the earliest cache-eligible record among those whose subject digest and rubric digest both equal the digests of the subject and rubric this dispatch would grade (\"One rubric, one subject\"),".

**3. `SPECIFICATION/contracts.md`, the "Judged before admission" paragraph.** After the sentence "When that judgement admits the item, intake MUST route it exactly as it would without the judgement.", insert: "A cache-eligible record on identical digests answers this judgement without running any judge, as \"One rubric, one subject\" requires of every host taking, and the verdict comment this paragraph requires is then not appended again."

**4. `SPECIFICATION/scenarios.md`.** Add after the last scenario:

```gherkin
## Scenario 240 — A recorded Definition-of-Done verdict binds every host taking on identical digests, and opposite verdicts are journaled

Feature: A judge that flips on unchanged input cannot flip a recorded verdict
  As the operator of a factory
  I want the first verdict on a Definition of Done to stand until its text or rubric changes
  So that relaunching an item never re-rolls the judgement of unchanged bytes

  Scenario Outline: A host taking reuses a recorded host verdict without running any judge
    Given an item carrying a host record written by the <earlier> taking for its current subject digest and rubric digest
    When the <later> taking judges the item
    Then it returns that record's outcome and names the record as reused
    And no judge or candidate is started
    And no record is appended

    Examples:
      | earlier              | later                |
      | repository preflight | pre-dispatch         |
      | pre-admission        | repository preflight |
      | pre-dispatch         | pre-dispatch         |

  Scenario: Recording a verdict does not change the subject it was taken on
    Given an item with no record for its current digests
    When the repository preflight judges the item and appends its record
    Then the subject digest the pre-dispatch judgement computes next equals the digest the preflight record carries
    And the goal the Dispatcher renders for the node omits the preflight record

  Scenario: Reuse selects the earliest record among those matching the current digests
    Given an item whose cache-eligible records, all under one rubric digest, carry subject digest A, then subject digest B, then subject digest A again
    When the pre-dispatch judgement judges the item while its current subject digest is B
    Then it reuses the record carrying digest B
    When the item's subject is restored so its current subject digest is A and the pre-dispatch judgement judges it again
    Then it reuses the first record carrying digest A, not the later one

  Scenario: A candidate that cannot run leaves no binding verdict
    Given an item with no cache-eligible record for its current digests
    When the repository preflight runs two candidates and the second times out
    Then the preflight exits with code 2 and returns no verdict
    And the item carries one did-not-run record naming the second candidate and the timeout
    When the repository preflight runs again on the same digests and both candidates return verdicts
    Then the candidates are started rather than the did-not-run record being reused
    And the record this run appends answers every later host taking on those digests

  Scenario: A preflight chain is one taking whose mixed candidate outcomes are recorded and journaled
    Given an item with no record for its current digests
    When the repository preflight runs two candidates and the first passes while the second refuses
    Then the item carries one record naming the preflight as refusing, with both candidates and their outcomes
    And the dispatch journal carries one dod-judgement-disagreement row naming the two candidates
    And a later host taking on the same digests returns the refusal without running any candidate

  Scenario: A changed subject takes a fresh judgement
    Given an item whose host record refused it
    And the item's Definition of Done section has since been edited
    When the pre-dispatch judgement judges the item
    Then a judge is started against the new subject
    And one new record carries the new subject digest

  Scenario Outline: Opposite outcomes on identical digests are journaled once, whichever takings produced them
    Given an item whose records include a <first> and a <second> on identical subject and rubric digests
    When the Dispatcher next reads the item's records
    Then the dispatch journal carries one dod-judgement-disagreement row naming both takings, both digests and each outcome's timestamp
    And the item carries one disagreement record with the same facts
    And a later read of the same two records appends nothing further

    Examples:
      | first                              | second                                  |
      | pass recorded by the preflight     | refusal recorded by pre-admission       |
      | node pass recorded for one run     | node refusal recorded for a later run   |
      | node pass recorded for one run     | refusal recorded by the pre-dispatch    |

  Scenario: The node still runs, records its outcome, and is never answered from a record
    Given an item whose only record is a pass written by the repository preflight on the current digests
    When a run of the item reaches the dod_gate node and the node refuses it
    Then the node ran rather than being answered from the record
    And the item carries one node record naming the run and the refusal
    And the dispatch journal carries one dod-judgement-disagreement row naming the run and the repository preflight
    And the item rests at blocked with blocked_reason needs-human exactly as any dod_gate refusal rests it
```

**5. `tests/heading-coverage.json` and `tests/heading-coverage-debt.json`.** The revise that ratifies this proposal files its implementing work-item (blocked by bd-ib-gob6gl, which introduces the digests) and adds a `test: "TODO"` coverage row for the Scenario 240 heading owned by that work-item, with the matching debt-register entry, in the same change.
