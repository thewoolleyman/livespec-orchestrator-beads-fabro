---
topic: unlabeled-verdict-turn-retries-once
author: claude-opus-5-5
created_at: 2026-10-27T00:54:30Z
---

## Proposal: A review or proof_verify turn that succeeds without its verdict label is retried once

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

In the stage contracts: a review or proof_verify turn that ends succeeded without any verdict label it routes on gets one retry of the same stage, on the same head, with an instruction to emit only its verdict. A second unlabeled turn routes to needs_human, naming the stage and the missing label. Labeled turns, failed turns and nodes that do not route on labels are unchanged.

### Motivation

Routed by petri-factory-on-gmktec under coordinator ruling R82, spec-first for work-item bd-ib-wg5zyt (held for dispatch until this lands). Today a review or proof_verify turn that succeeds without a verdict label falls through to needs_human (the workflow's "unmatched review outcome" and "unmatched proof_verify outcome" edges), so a run is lost to a turn that merely forgot to emit its verdict. Measured 2026-10-26 on livespec-driver-claude-5jr2xu run 01M5XA3WX7H0ZFHE4KDJ3ZVJHZ: after review approved, proof_verify succeeded with an implement-style report and no label. Prior art bd-ib-7smzwo (pending approval) fixes the engine dropping a label that IS present, and its second assertion keeps "no label object routes to needs_human"; this clause supersedes that assertion's routing with one bounded retry. proof_grade is a command node that routes on its outcome, not a verdict label, so it is out of scope.

### Proposed Changes

1. In `SPECIFICATION/contracts.md`, §"Self-contained plugin dispatch" → "### Definition-of-Done and Proof-of-Done stages", after the paragraph "**`proof_verify`.**", insert immediately after the text

```
`verified`. The engine
constraints these nodes MUST honour are in `constraints.md` §"Fabro
runtime constraints".
```

the following new paragraph (separated by one blank line):

```
**A verdict turn that ends without its verdict label is retried once.** The `review` and `proof_verify` nodes route on the verdict label their turn records (`preferred_label`). When such a turn ends succeeded but records none of the verdict labels its node routes on, the run MUST NOT route it to `needs_human` on that turn. It MUST instead run the same stage once more, on the same head and inputs, with a stage-scoped instruction added to that turn's prompt to end by emitting only its verdict. A retry turn that records a verdict label routes exactly as a first turn with that label does. A second consecutive turn of the same stage visit that ends succeeded without a verdict label MUST route to `needs_human`, with a cause that names the stage and states that its turn recorded no verdict label. The retry counts once per stage visit, and a stage that the run re-enters later gets its own single retry. A turn that records a verdict label, a failed turn, and a node that does not route on a verdict label, such as the command node `proof_grade`, route exactly as before. A record a `proof_verify` turn published before ending without a label stays on the pull request and is read by the existing record rules. Measured 2026-10-26 on livespec-driver-claude-5jr2xu run 01M5XA3WX7H0ZFHE4KDJ3ZVJHZ: after `review` approved, `proof_verify` ended succeeded with an implement-style report and no verdict label, and the run went to `needs_human` through the unmatched-outcome edge with no question asked. Scenario 258 in `scenarios.md` exercises this paragraph.
```

2. In `SPECIFICATION/scenarios.md`, append:

````
## Scenario 258 — A review or proof_verify turn that succeeds without a verdict label is retried once before it reaches needs_human

```gherkin
Feature: A verdict turn that forgets its verdict gets one more chance before a human is asked
  Scenario: proof_verify without a verdict label is retried and then routes on its verdict
    Given a proof_verify turn that ends succeeded and records no verdict label
    When the run routes that turn
    Then proof_verify runs once more on the same head with an instruction to emit only its verdict
    And when the retry records preferred_label approve, the run routes to proof_grade

  Scenario: review without a verdict label is retried once
    Given a review turn that ends succeeded and records no verdict label
    When the run routes that turn
    Then review runs once more with an instruction to emit only its verdict
    And the retry's verdict label routes it exactly as a first turn's would

  Scenario: A second unlabeled turn reaches needs_human with a named cause
    Given a proof_verify retry turn that also ends succeeded and records no verdict label
    When the run routes that turn
    Then the run routes to needs_human with a cause naming proof_verify and its missing verdict label

  Scenario: A labeled or failed turn routes as before
    Given a review turn that records preferred_label fix, and another that ends failed
    When the run routes each turn
    Then the first routes to disposition and the second to needs_human, with no retry
```
````

3. Add a TODO row for the new heading to `tests/heading-coverage.json` and a matching debt row to `tests/heading-coverage-debt.json`, both owned by the implementing work-item bd-ib-wg5zyt.
