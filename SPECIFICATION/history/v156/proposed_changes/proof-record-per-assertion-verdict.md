---
topic: proof-record-per-assertion-verdict
author: claude:definition-and-proof-of-done
created_at: 2026-10-16T22:17:34Z
---

## Proposal: Each factory-captured assertion carries its own reproduction verdict, and a proof_grade node grades the verified record before the run advances

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The Proof of Done record clause gains one requirement: in a proof_verify record, the section of each factory_captured assertion MUST carry its own prose Reproduced: yes or Reproduced: no line, and a verdict line outside an assertion's section is not evidence for it. The proof_verify routing gains a command node, proof_grade, between the verified outcome and pr_refresh. It grades the newest verified record naming the run with the same record reader the acceptance pass uses, routes to pr_refresh when every factory_captured assertion reads as reproduced, and otherwise re-enters proof_verify naming the ungraded assertions, inside proof_verify's existing visit cap. A new scenario exercises both.

### Motivation

Work item bd-ib-rszkjc merged as pull request 3130 with captured and verified records for its run, and the acceptance pass parked it NEEDS_ATTENTION with all three assertions pending a Proof of Done record. Replaying the shipped reader against the published comments showed the record was found and correctly attributed; it carried no Reproduced: line inside any assertion section, only one record-wide line under a trailing comparison heading. The proof_verify prompt already asks for the line per assertion, but no ratified clause requires it, and nothing grades the record before merge, so an agent's formatting deviation strands correct, merged work in acceptance where no re-run can move it. Widening the reader to accept a trailing summary is the fail-open direction the reader exists to refuse, so the check belongs before the merge, where a new record can still be posted. Filed as bd-ib-kcq6pu under plan definition-and-proof-of-done at the stability-freeze driver's request (rulings R85 and R86).

### Proposed Changes

1. contracts.md, §"Proof of Done record", paragraph "The record." — after the sentence ending "and a fenced code block for each text capture.", insert:

"In a `verified` or `not_reproduced` record, the section of each `factory_captured` assertion MUST carry its own prose line `Reproduced: yes` or `Reproduced: no`, outside any fenced block; a verdict line in another section, including a record-wide summary, MUST NOT be read as that assertion's verdict."

2. contracts.md, §"Definition-of-Done and Proof-of-Done stages", paragraph "The stages." — replace "and `proof_verify`, entered from `review` and exiting to `pr_refresh` on success." with "and `proof_verify`, entered from `review` and, on success, exiting to the command node `proof_grade`." After the `publish_draft` sentence, insert: "It MUST also carry the command node `proof_grade`, entered only from a `verified` outcome of `proof_verify`. `proof_grade` MUST read the newest `verified` record on the pull request whose run identifier the Dispatcher attributes to this dispatch, using the same record reader the acceptance pass grades with, and MUST exit zero, routing to `pr_refresh`, exactly when every `factory_captured` assertion of the effective criteria reads as reproduced from that record. Otherwise it MUST exit non-zero naming each assertion that did not read as reproduced, and the record it could not read when there was none; its failure edge MUST re-enter `proof_verify` while `proof_verify`'s own visit count is below three, and otherwise MUST lead to `non_converged`. A re-entered `proof_verify` MUST publish a new record rather than edit the earlier one."

3. contracts.md, the `proof_verify` paragraph — replace "`verified` routes to `pr_refresh`;" with "`verified` routes to `proof_grade`, which routes to `pr_refresh` as above;" and replace "No edge MAY route from `proof_verify` to `pr_refresh` or `pr` on any verdict but `verified`." with "No edge MAY route from `proof_verify` to `pr_refresh` or `pr`; a `verified` outcome reaches `pr_refresh` only through `proof_grade`."

4. scenarios.md — append a new scenario, numbered as the next free scenario at revise time, titled "A verified record is graded per assertion before the run advances, and a record-wide verdict line re-enters proof_verify", with this Gherkin:

Feature: The verified record is graded per assertion before publication
  Scenario: A verified record with a verdict line in every assertion section advances
    Given proof_verify posted a verified record whose every factory_captured assertion section carries a prose Reproduced: yes line
    When the proof_grade node runs
    Then it exits zero and the run proceeds to pr_refresh
  Scenario: A record-wide verdict line is not a per-assertion verdict
    Given proof_verify posted a verified record whose only Reproduced: line sits under a trailing summary heading
    When the proof_grade node runs
    Then it exits non-zero naming every factory_captured assertion
    And the run re-enters proof_verify, which posts a new record without editing the earlier one
  Scenario: Ungradeable records stay inside the proof_verify visit cap
    Given proof_verify has reached its third visit and its verified record is still ungradeable
    When the proof_grade node runs
    Then the run routes to non_converged

The revise MUST co-edit `tests/heading-coverage.json` with an entry for the new scenario heading, test `TODO` with a reason naming bd-ib-kcq6pu as the implementing item.
