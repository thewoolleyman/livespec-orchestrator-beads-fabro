---
topic: make-the-definition-of-done
author: claude-opus-5-5
created_at: 2026-11-14T07:28:48Z
---

## Proposal: A Definition-of-Done taking decides one verdict per subject by a fixed agreement rule, an unparseable reply is no verdict, and the coherence check admits one reading

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Scenario 239 promises that every taking grades one subject by one rubric, yet the same subject on unchanged bytes passes in one taking and fails in the next. This proposal (1) makes an unparseable candidate reply explicitly no verdict, never a pass or a refusal; (2) makes every taking that runs a candidate decide by one agreement rule: two parseable verdicts that agree, or exactly one re-judge deciding by majority when they disagree, otherwise did-not-run; each record names the deciding rule; and (3) settles the two readings the rubric's coherence check currently admits.

### Motivation

Work item bd-ib-sq5oes (plan bd-ib-ax3rds, spec-implementation-lockstep), approved P1 by legacy-coordinator-agent. Its dispatch at 2026-11-14T07:26:41Z was held for this topic: spec-change, partial, generalization target ## Scenario 239 at spec 373. legacy-coordinator-agent ruled no clause release and directed this single-topic proposal. Measured flips on unchanged bytes:
- li-cyucz7, 2026-10-31: a hand screen PASSED and the launch preflight FAILED check 4 minutes later, same candidate and rubric. Check 4's lead question licenses repository-only observability, while its incoherent list forbids it.
- livespec-dev-tooling-6cgj2e, 2026-11-14: the launch dod-preflight REFUSED at 03:57:18Z and the unchanged bytes PASSED at ~07:10Z.
- Unparseable replies: approve:livespec-dev-tooling-i3w3gt (~07:2xZ), and on bd-ib-sq5oes itself three replies (the filing display and two classify-tier runs) before the coordinator's approve got a verdict on the same bytes.
Design choices, stated for the grade:
(1) Agreement within a taking, not across takings. Reusing a recorded verdict on identical digests (bd-ib-hofndb, bd-ib-v7aftf, both blocked) makes later takings identical, but every first taking still faces one sampled reply. Two agreeing verdicts plus one tie-breaking re-judge is the smallest rule that never records a lone sample, and it is bounded: at most three parseable verdicts per taking.
(2) Never a bare retry loop. Further replies are taken only to replace a no-verdict reply or to break a tie, all within the existing input bound; a bound that ends first is did-not-run, which already has a ratified route.
(3) Unparseable is no verdict, stated once for this judgement. This matches the spec's existing intake and reflector rules, which already treat an unparseable reply as did-not-run.
(4) The coherence readings go into the spec because the spec already says grading guidance belongs in the one rubric. Stating which reading it carries keeps every taking on the same one.
(5) Cost: a taking whose first two verdicts agree costs two candidate replies. That doubles the single-reply cost on a first taking, but every later taking on identical digests reuses the record, and one wasted factory launch costs far more.
In-flight alignment, align: #5068 (a-spec-change-tier-record) and node-record-names-model-and-tools add fields to judgement records; this proposal adds `decided-by` and the counted outcomes beside them. Fleet scope: every tenant whose Definition-of-Done takings run this plugin.

### Proposed Changes

**1. `SPECIFICATION/contracts.md` §"Effective acceptance criteria".** Directly after the sentence "When no candidate returns a verdict, the judgement did not run, and the taking follows its ratified did-not-run route.", insert:

> **One verdict per subject: the agreement rule.** A candidate reply that does not parse as the taking's verdict form is NO VERDICT, exactly as a candidate the input bound ended is: it MUST NOT be recorded as a pass or as a refusal. Every taking of the Definition-of-Done judgement that runs a candidate MUST decide its outcome by this one agreement rule. The taking obtains two parseable verdicts from its candidate chain, taking a further candidate reply in place of each no-verdict reply while its input bound allows. When the two verdicts return the same outcome, that is the taking's outcome, decided by `agreement`. When they return opposite outcomes, the taking obtains exactly one further parseable verdict, the RE-JUDGE, and its outcome is the one at least two of the three verdicts return, decided by `re-judge`. The findings it records for a refusal are those of the counted verdicts that refused. When the bound ends the chain before the rule decides, either with fewer than two parseable verdicts or with a disagreement and no re-judge, the judgement did not run and the taking follows its did-not-run route. A taking MUST NOT take candidate replies beyond what this rule requires, and MUST NOT record the outcome of whichever reply returned last. Every verdict record MUST name the rule that decided it, as `decided-by: agreement` or `decided-by: re-judge`, and the outcome of each verdict it counted. A taking that reuses a recorded verdict runs no candidate and decides nothing, so the rule does not apply to it, and the disagreement records that the "Judged again before dispatch" paragraph defines continue to compare takings exactly as before.

**2. `SPECIFICATION/contracts.md`, the `dod_gate` node's description.** Directly after the sentence ending "a Definition of Done that a competent engineer could not recognise as satisfied or unsatisfied from the referenced scenario is incoherent.", insert:

> The rubric's coherence check MUST leave one reading of these two cases. An assertion whose subject the referenced heading's whole section neither states nor derives is incoherent, even when that subject is repository state an engineer could check without the specification. A governing-heading verdict of kind `unstated` is never licence to pass an assertion that its referenced heading does not govern.

**3. `SPECIFICATION/scenarios.md`, `## Scenario 239 — Every taking of the Definition-of-Done judgement grades one subject by one rubric`.** Inside that scenario's Gherkin block, after the scenario `The unpreflightable fact clears when a later taking runs a judge` and before the block's closing fence, add:

```gherkin
  Scenario: An unparseable candidate reply is no verdict
    Given a taking whose first candidate reply does not parse as its verdict form
    When the taking decides its outcome
    Then that reply is counted neither as a pass nor as a refusal
    And the taking takes a further candidate reply in its place while its input bound allows

  Scenario: Two agreeing verdicts decide the outcome
    Given a taking whose first two parseable verdicts both pass the subject
    When the taking decides its outcome
    Then it records a pass with decided-by agreement and both counted outcomes
    And it takes no further candidate reply

  Scenario: A disagreement is settled by exactly one re-judge
    Given a fixture judge whose single replies alternate between pass and refuse on one unchanged subject
    When two separate takings each decide their outcome
    Then each taking obtains exactly one re-judge after its first two verdicts disagree
    And both takings record the same outcome with decided-by re-judge
    And neither records the outcome of whichever reply returned last

  Scenario: A chain the input bound ends before the rule decides did not run
    Given a taking whose input bound ends its chain after one parseable verdict and one unparseable reply
    When the taking decides its outcome
    Then the judgement did not run and the taking follows its did-not-run route
    And no pass and no refusal is recorded

  Scenario: A repository-checkable assertion its section does not state is incoherent
    Given an assertion whose subject is repository state an engineer could check without the specification
    And the referenced heading's whole section neither states nor derives that subject
    And the governing-heading verdict for the assertion is of kind unstated
    When the coherence check grades the assertion
    Then the assertion is incoherent
```

No heading is added, removed or renamed, so `tests/heading-coverage.json` needs no edit.
