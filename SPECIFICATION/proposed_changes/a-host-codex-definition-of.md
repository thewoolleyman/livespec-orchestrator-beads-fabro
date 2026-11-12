---
topic: a-host-codex-definition-of
author: claude-opus-5-5
created_at: 2026-11-12T17:19:10Z
---

## Proposal: A host Definition-of-Done judgement is tool-less and grades the capability set it is given

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A host taking of the Definition-of-Done judgement MUST grant its candidate no tools, and its ending contract MUST say that the candidate has no tools and that everything it grades is in the prompt. The shared rubric MUST name the subject's GRADING SET as the only source of the sandbox capability set, and MUST NOT instruct the judge to read, list or search any file or directory, including `/etc/livespec` and the governed `SPECIFICATION` tree. Every taking MUST place the GRADING SET in the prompt it gives the judge. Today the specification only bounds what loads into a host judgement and how much input it may consume. It implies a tool allowance the judgement may grant, and it says nothing about read instructions in the rubric. So a tool-less host candidate is still told to read files it cannot reach.

### Motivation

Work item bd-ib-ff5ohb (plan anthropic-burn-mitigation, epic bd-ib-b2jzxw) was refused at the pre-dispatch wall on 2026-11-12T17:11Z as spec-change tier. The verdict was partial, the generalization target was "## Dispatcher admission, WIP cap, and post-merge acceptance", and the linked topic was this one. The judgement's rationale: "The first two bullets are stated ... The third bullet is not stated: no clause says the judgement prompt must inline the capability set, tell the candidate it has no tools, or omit read/list/search instructions. The text only requires the prompt file's bytes plus the ending contract and subject, and implies a tool allowance the judgement may grant." Measured 2026-10-31 by the anthropic-burn-mitigation seat on PR #4026's head 648a28ed7: with the Claude host candidate made tool-less (bd-ib-55vxu5), both Claude transcripts opened by writing tool calls as plain text (`cat /etc/livespec/sandbox-capabilities`, a listing of `SPECIFICATION`). They then said every probe returned no output, and graded on that assumption, because the rubric told the judge to read those files. Full write-up: https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/pull/4026#issuecomment-6540165509. The capability set is already a SUBJECT component (the GRADING SET) of "One rubric, one subject", and that paragraph already requires any statement about where the capability set comes from to be written into the rubric. So the fix states that the rubric names the GRADING SET as that source and never sends the judge to a file. Because every taking shares the one rubric, this binds the in-run `dod_gate` node too. A tool-less host taking costs one request against a grading that reads files, which re-sends its whole context on every tool round trip (measured 2026-10-26: about 128,000 tokens per request over three requests). That per-grading input is what plan anthropic-burn-mitigation assertion 4 bounds below 100,000 tokens.

### Proposed Changes

Two edits to `SPECIFICATION/contracts.md` and one to `SPECIFICATION/scenarios.md`. No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.

**Edit 1 — `contracts.md`, §"Dispatcher admission, WIP cap, and post-merge acceptance", the paragraph that begins **A host judgement launches outside the interactive agent configuration.**** Replace its sentence "The judgement's subject, rubric and governing text reach the agent only through the judgement's own prompt and the tool allowance the judgement grants." with:

> The judgement's subject, rubric and governing text reach the agent only through the judgement's own prompt. A host taking of the Definition-of-Done judgement MUST grant its candidate no tools: the candidate's tool allowance MUST be empty, whichever agent the resolved candidate runs, and no file, directory, command or network resource is reachable from its session. Its ending contract MUST state that the candidate has no tools and that every input it grades is in the prompt. A host judgement other than the Definition-of-Done judgement MAY grant a tool allowance only when it names that allowance on its own invocation.

Every other sentence of that paragraph is unchanged.

**Edit 2 — `contracts.md`, the paragraph that begins **One rubric, one subject.**** Replace its sentences "A taking other than the node MAY append only an ending contract stating the verdict form it must return. Any other guidance about how to grade a check, including any statement about where the capability set comes from, MUST be written into the rubric itself, so that the node grades by it too." with:

> A taking other than the node MAY append only an ending contract. That contract states the verdict form the taking must return and, for a host taking, the statement the paragraph "A host judgement launches outside the interactive agent configuration" requires: the candidate has no tools and every input it grades is in the prompt. Any other guidance about how to grade a check MUST be written into the rubric itself, so that the node grades by it too. The rubric MUST name the subject's GRADING SET as the only source of the sandbox capability set it grades proof-mode feasibility against. It MUST NOT instruct the judge to read, list, search or execute anything to obtain an input it grades: not a file, a directory, a command's output or the network, including `/etc/livespec` and the governed `SPECIFICATION` tree. Every taking, the node included, MUST place the GRADING SET in the prompt it gives the judge, exactly as the subject digest encodes it: the sorted capability names, or the literal `unpublished`. The `dod_gate` node's comparison of the image's published capability file with the grading set (§"Sandbox capabilities") is not grading, and its instruction MUST NOT be written into the rubric. The node's prompt MUST carry it after the rubric, as the node's own duty, so that no host taking's prompt names the published file.

Every other sentence of that paragraph is unchanged, and §"Sandbox capabilities" is unchanged: the node still compares the published file with the grading set and reports each mismatch. The GRADING SET's definition, its position in the subject and the subject digest are unchanged, so no recorded verdict's subject digest changes. The rubric digest changes when the rubric file's bytes change, as it does today.

**Edit 3 — `scenarios.md`, §"Scenario 239 — Every taking of the Definition-of-Done judgement grades one subject by one rubric".** Append these scenarios to the end of that scenario's Gherkin block, inside the same fenced block, after "Then needs-attention no longer lists the item as unpreflightable". The scenario's heading is unchanged:

```gherkin
  Scenario: A host taking grants its candidate no tools and says so
    Given a repository whose resolved dod_gate chain names codex-acp first and claude-acp second
    When the pre-dispatch taking of the Definition-of-Done judgement runs either candidate on the host
    Then that candidate's session is launched with an empty tool allowance
    And the ending contract appended to the rubric states that the candidate has no tools and that every input it grades is in the prompt

  Scenario: Every taking is given the grading set and no instruction to read a file
    Given a repository whose committed dispatcher.sandbox_capabilities array names two capabilities
    When the pre-admission taking, the pre-dispatch taking and a run's dod_gate node each build the prompt they give the judge
    Then each prompt carries the two capability names, sorted, as the grading set
    And no prompt instructs the judge to read, list, search or execute anything to obtain an input it grades
    And no host taking's prompt names /etc/livespec or the SPECIFICATION tree as a place to look
    And the dod_gate node's prompt carries the published-file comparison after the rubric, not within it

  Scenario: An unpublished capability set reaches the judge as the literal unpublished
    Given a repository that commits no dispatcher.sandbox_capabilities array
    When a host taking builds the prompt it gives the judge
    Then the prompt carries the grading set as the literal unpublished
    And the subject digest encodes the same literal unpublished as its GRADING SET component
```
