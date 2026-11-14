---
topic: make-the-definition-of-done
author: claude-opus-5-5
created_at: 2026-11-14T07:28:48Z
---

## Proposal: A host taking's candidate returns a verdict only by an agreement rule over its own replies, and an unparseable reply is no verdict

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The same Definition-of-Done subject passes in one host taking and fails in the next on unchanged bytes, because each candidate's verdict is one sampled reply. This proposal defines when a candidate in a HOST taking (pre-admission, pre-dispatch, repository preflight) has returned a verdict. Its replies are resamples of that one candidate. Two parseable replies that agree decide it. When they disagree, exactly one further reply, the re-judge, decides by majority. An unparseable reply is no verdict and is replaced by a further resample, within a bound of five replies per candidate. A candidate whose rule does not decide within that bound has returned no verdict. Both chain rules stay as ratified: the pre-admission and pre-dispatch takings fall back to the next candidate, and the repository preflight's independently graded chain passes only when every candidate passes. The text that today treats one reply as the candidate's verdict is amended explicitly. The `dod_gate` node is out of scope and keeps its single reply.

### Motivation

Work item bd-ib-sq5oes (plan bd-ib-ax3rds, spec-implementation-lockstep), approved P1 by legacy-coordinator-agent. Its dispatch at 2026-11-14T07:26:41Z was held for this topic: spec-change, partial, generalize ## Scenario 239, spec 373. legacy-coordinator-agent ruled no clause release and directed a single-topic proposal. This re-cut answers that seat's FAIL grade of the first draft (session a7764b59).

Measured flips on unchanged bytes:
- li-cyucz7 (2026-10-31): a hand screen passed, then the launch preflight failed, with the same candidate and rubric.
- livespec-dev-tooling-6cgj2e (2026-11-14): the launch dod-preflight refused at 03:57:18Z, and the same bytes passed at ~07:10Z.
- Unparseable replies: approve:livespec-dev-tooling-i3w3gt (~07:2xZ), and three on bd-ib-sq5oes itself (the filing display and two classify-tier runs), before an approve on the same bytes got a verdict.

The 6cgj2e re-roll is ALREADY forbidden by the ratified verdict-reuse rule (a host taking returns the earliest cache-eligible record on identical subject and rubric digests; Scenario 240). That rule is unimplemented while bd-ib-hofndb and bd-ib-v7aftf are blocked, which is conformance work and needs no spec change. This proposal covers what reuse cannot: the FIRST taking on a subject, which reuse never answers, and the unparseable reply.

Design choices, stated for the grade:
1. **Resamples of one candidate, not the next candidates.** The chain keeps its ratified meanings: fallback for pre-admission and pre-dispatch, independent grading for a repository preflight. The agreement rule only defines when ONE candidate has returned a verdict, so neither chain rule changes, and a fallback still happens only when a candidate returns no verdict.
2. **A reply-count bound of five per candidate.** At most three parseable replies count (two, plus one re-judge). Up to two unparseable replies may be replaced. The input bound applies to each reply separately, so a candidate's resamples are not ended by their combined input.
3. **The node is excluded.** Node records are never reused, so applying the rule there would at least double every run's node cost. A node refusal after a host pass is already journaled as a disagreement and rests the item. The node keeps one reply.
4. **No disagreement record inside one candidate.** The ratified disagreement record compares takings, or a chain's candidates. A re-judge inside one candidate is the rule working, not a disagreement, so it writes none. Disagreement between candidates and between takings is recorded exactly as before.
5. **Older records stay reusable.** A cache-eligible record written before this rule names no `decided-by` and remains cache-eligible.
6. **Cost.** A host taking's candidate now costs two replies when they agree, and three on a re-judge. The node is unchanged, and verdict reuse answers later host takings on identical digests.

The first draft's coherence-check edit is DROPPED from this topic, on the grade. It is a behaviour change, not a determinism fix, and if wanted it will be proposed separately.

In-flight alignment: a-host-codex-definition-of (pending on master) gives a host candidate no tools and separates the node prompt from the rubric file. This proposal does not touch the rubric or the tool allowance, so align: a candidate that cannot launch with an empty tool allowance still counts as one the host cannot launch, before any reply is taken. node-record-names-model-and-tools adds fields to judgement records; this adds `decided-by` and the counted reply outcomes beside them, so align.

Fleet scope: every tenant whose host Definition-of-Done takings run this plugin.

### Proposed Changes

**1. `SPECIFICATION/contracts.md`, the paragraph beginning "**Host judgements take the resolved `dod_gate` chain.**"**
- Replace "the first candidate that returns a verdict decides the judgement, and the remaining candidates are not run" with "the first candidate that returns a verdict decides the judgement, and the remaining candidates are not run; in a host taking of the Definition-of-Done judgement, a candidate returns a verdict only as the agreement rule below decides".
- Replace "or one that returns no verdict (a timeout or an unparseable reply), passes the judgement to the next candidate" with "or one that returns no verdict (a timeout, or, in a host taking of the Definition-of-Done judgement, an agreement rule that does not decide within its reply bound), passes the judgement to the next candidate".
- Directly after the sentence "When no candidate returns a verdict, the judgement did not run, and the taking follows its ratified did-not-run route.", insert:

> **A host candidate's verdict: the agreement rule.** In every HOST taking of the Definition-of-Done judgement (pre-admission, pre-dispatch and repository preflight), a candidate's REPLIES are resamples of that one candidate: further turns on the same subject and rubric, each a new session. A reply that does not parse as the taking's verdict form is NO VERDICT and MUST NOT be counted as a pass or as a refusal. The candidate returns a verdict only by this AGREEMENT RULE. Its first two parseable replies decide it when they return the same outcome, `decided-by: agreement`. When they return opposite outcomes, exactly one further parseable reply, the RE-JUDGE, decides it as the outcome at least two of the three return, `decided-by: re-judge`. An unparseable reply, the re-judge's included, is replaced by a further resample. A candidate MUST take at most FIVE replies. When its rule has not decided by then, the candidate has returned no verdict, with the cause `agreement-bound`. The input bound applies to each reply separately, and a reply the input bound ends is no verdict. A candidate MUST NOT take a reply beyond what this rule requires, and its verdict MUST NOT be the outcome of whichever reply returned last. A candidate's findings for a refusal are those of its counted replies that refused. Every host taking's verdict record MUST name, for each candidate it ran, the rule that decided it and the outcome of each reply it counted. A cache-eligible record written before this rule, which names no `decided-by`, remains cache-eligible. The `dod_gate` node is not a host taking, and it takes one reply as before.

**2. `SPECIFICATION/contracts.md`, the paragraph beginning "A TAKING is one invocation of the judgement".**
- Replace "When any candidate cannot return a verdict (no eligible model, a timeout, an unparseable reply, or the input bound ending it)" with "When any candidate cannot return a verdict (no eligible model, a timeout, or its agreement rule not deciding within its reply bound, as the "Host judgements take the resolved `dod_gate` chain" paragraph states)".
- After "or one record's candidates returned opposite outcomes", insert ", where a candidate's outcome is its agreement-rule verdict; replies of one candidate that the re-judge settles are not a disagreement and MUST NOT cause a disagreement record".

**3. `SPECIFICATION/scenarios.md`, `## Scenario 239 — Every taking of the Definition-of-Done judgement grades one subject by one rubric`.**
- In the scenario `A host judgement falls back along the resolved dod_gate chain`, replace "When the pre-dispatch Definition-of-Done judgement is taken and the primary returns a verdict" with "When the pre-dispatch Definition-of-Done judgement is taken and the primary's agreement rule decides a verdict".
- Inside that scenario's Gherkin block, after the scenario `The unpreflightable fact clears when a later taking runs a judge` and before the closing fence, add:

```gherkin
  Scenario: An unparseable reply is no verdict and is replaced
    Given a host taking whose candidate's first reply does not parse as the verdict form
    When the candidate's agreement rule decides
    Then that reply is counted neither as a pass nor as a refusal
    And a further resample of the same candidate is taken in its place

  Scenario: Two agreeing replies decide the candidate
    Given a host taking whose candidate's first two parseable replies both pass the subject
    When the candidate's agreement rule decides
    Then the candidate's verdict is a pass with decided-by agreement
    And no third reply is taken
    And the verdict record names both counted reply outcomes

  Scenario: A disagreement inside one candidate is settled by exactly one re-judge
    Given a fixture judge whose replies alternate between pass and refuse, starting afresh with each taking
    When two separate host takings of one unchanged subject each run that candidate
    Then each candidate takes exactly one re-judge after its first two replies disagree
    And both takings record the same outcome with decided-by re-judge
    And no dod-judgement-disagreement record is written for those replies

  Scenario: A candidate whose rule does not decide within five replies returned no verdict
    Given a host candidate whose replies are unparseable except for one pass
    When it has taken five replies
    Then the candidate has returned no verdict with the cause agreement-bound
    And a pre-dispatch taking passes the judgement to the next candidate
    And a repository preflight did not run and exits with its cannot-run code 2

  Scenario: The dod_gate node takes one reply
    Given a run whose dod_gate node grades an item
    When the node returns its verdict
    Then the node took one reply and no agreement rule applied
```

No heading is added, removed or renamed, so `tests/heading-coverage.json` needs no edit.
