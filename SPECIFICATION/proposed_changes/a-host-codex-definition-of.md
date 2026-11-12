---
topic: a-host-codex-definition-of
author: claude-opus-5-5
created_at: 2026-11-12T18:25:42Z
---

## Proposal: A host Definition-of-Done judgement is tool-less and grades the subject it is given

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A host taking of the Definition-of-Done judgement MUST grant its candidate no tools, and its ending contract MUST say so. A candidate that cannot launch with an empty tool allowance counts as one the host cannot launch: the pre-admission and pre-dispatch takings pass to the next candidate, and a repository preflight did not run. The rubric becomes the rubric FILE, `prompts/dod-gate.md`, and the `dod_gate` node gets its own NODE PROMPT file outside the rubric digest. That file directs the node to read the rubric and the subject file the Dispatcher MUST write before the node runs, and to make the published-capability comparison §"Sandbox capabilities" assigns it. The rubric names the subject's GRADING SET as the only capability source and MUST NOT instruct the judge to read, list, search or execute anything. A host taking places the whole subject, GRADING SET included, in its prompt. The reference-line rule's "wherever it reads `scenarios.md` itself" becomes a direction to quote the step line from the subject's HEADINGS. Today the rubric file is also the node's prompt, so its read instructions (the subject file, the spec tree, the capability file) reach every tool-less host judge.

### Motivation

Work item bd-ib-ff5ohb (plan anthropic-burn-mitigation, epic bd-ib-b2jzxw) was refused at the pre-dispatch wall on 2026-11-12T17:11Z as spec-change tier. The verdict was partial, the generalization target was "## Dispatcher admission, WIP cap, and post-merge acceptance", and the linked topic was this one. The judgement's rationale: "no clause says the judgement prompt must inline the capability set, tell the candidate it has no tools, or omit read/list/search instructions. The text only requires the prompt file's bytes plus the ending contract and subject, and implies a tool allowance the judgement may grant." Measured 2026-10-31 on PR #4026's head 648a28ed7: with the Claude host candidate made tool-less (bd-ib-55vxu5), both Claude transcripts opened by writing tool calls as plain text (`cat /etc/livespec/sandbox-capabilities`, a listing of `SPECIFICATION`), said every probe returned no output, and graded on that assumption. Write-up: https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/pull/4026#issuecomment-6540165509. The rubric file is today ALSO the node's prompt (`prompt="@prompts/dod-gate.md"` in workflow.fabro). It tells the node to read the Dispatcher-written subject file, to grade from "the goal and the spec tree" when that file is absent, and §"Sandbox capabilities" has the node compare the image's published capability file. Every one of those instructions reaches a host judge that has no tools. Separating a node prompt file from the rubric file keeps the node's reads where the node can perform them, and keeps them out of every host prompt and out of the rubric digest. legacy-coordinator-agent's grade of this proposal's first draft (2026-11-12 about 17:5xZ) asked for the location of the node-only text, the subject-file read, the scenarios.md direction at the reference-line rule and the cannot-launch branch; this revision answers all four. The coordinator also offered a deterministic command node for the capability comparison. It is not taken: the node prompt file is needed anyway to carry the subject-file read, so the comparison rides in it at no extra cost, and the mismatch steps of Scenarios 139 and 239 stay true unchanged. A command node would amend §"Sandbox capabilities" and those scenarios for no gain. A tool-less host taking costs one request; a grading that reads files re-sends its whole context on every tool round trip (measured 2026-10-26: about 128,000 tokens per request over three requests). That per-grading input is what plan anthropic-burn-mitigation assertion 4 bounds below 100,000 tokens.

### Proposed Changes

Four edits to `SPECIFICATION/contracts.md` (Edits 1, 2, 3 and 3a) and two to `SPECIFICATION/scenarios.md` (Edits 4 and 5). No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit. §"Sandbox capabilities" is unchanged.

**Edit 1 — `contracts.md`, §"Dispatcher admission, WIP cap, and post-merge acceptance", the paragraph that begins **A host judgement launches outside the interactive agent configuration.**** Replace its sentence "The judgement's subject, rubric and governing text reach the agent only through the judgement's own prompt and the tool allowance the judgement grants." with:

> The judgement's subject, rubric and governing text reach the agent only through the judgement's own prompt. A host taking of the Definition-of-Done judgement MUST grant its candidate no tools: the candidate's tool allowance MUST be empty, whichever agent the resolved candidate runs, and no file, directory, command or network resource is reachable from its session. Its ending contract MUST state that the candidate has no tools and that every input it grades is in the prompt. A candidate whose agent cannot be launched with an empty tool allowance is a candidate the host cannot launch, with the cause `no-tool-less-launch`. In the pre-admission and pre-dispatch takings it passes the judgement to the next candidate, as the preceding paragraph provides, and the taking's record names it with that cause. In a repository preflight, which grades every candidate of its chain independently, it is a candidate that cannot return a verdict: the preflight did not run, exits with its cannot-run code `2`, and its did-not-run record names that candidate with the cause `no-tool-less-launch`. A host judgement other than the Definition-of-Done judgement MAY grant a tool allowance only when it names that allowance on its own invocation.

Every other sentence of that paragraph is unchanged.

**Edit 2 — `contracts.md`, the paragraph that begins **One rubric, one subject.**** (a) In its second sentence, replace "Every taking MUST grade by ONE rubric: the `dod_gate` node's prompt file, read from the plugin build that will execute the dispatch." with "Every taking MUST grade by ONE rubric: the RUBRIC FILE, `prompts/dod-gate.md` of the `implement-work-item` workflow, read from the plugin build that will execute the dispatch." (b) Replace its sentences "A taking other than the node MAY append only an ending contract stating the verdict form it must return. Any other guidance about how to grade a check, including any statement about where the capability set comes from, MUST be written into the rubric itself, so that the node grades by it too." with:

> A taking other than the node MAY append only an ending contract. That contract states the verdict form the taking must return and the tool-less statement the paragraph "A host judgement launches outside the interactive agent configuration" requires. Any other guidance about how to grade a check MUST be written into the rubric itself, so that the node grades by it too. The rubric MUST name the subject's GRADING SET as the only source of the sandbox capability set it grades proof-mode feasibility against. It MUST NOT instruct the judge to read, list, search or execute anything: not a file, a directory, a command's output or the network, including `/etc/livespec`, the governed `SPECIFICATION` tree and any subject file. A host taking MUST place the whole subject, its GRADING SET included, in the judge's prompt after the rubric and its ending contract. The `dod_gate` node's own prompt MUST be a NODE PROMPT FILE separate from the rubric file, and its bytes MUST NOT enter the rubric digest. The node prompt file MUST direct the node to read the rubric file and the subject file the Dispatcher writes for the run (the same subject, byte for byte, that a host taking places in its prompt), to grade that subject by the rubric, and to make the comparison of the image's published capability file with the GRADING SET that §"Sandbox capabilities" assigns the node. It MUST NOT add, remove or restate a check. No host taking's prompt carries the node prompt file's text. Before the run's `dod_gate` node runs, the Dispatcher MUST write the run's SUBJECT FILE: the four subject components, in the order above, byte for byte as the components it computed the subject digest it supplies to the run from.

Every other sentence of that paragraph is unchanged. The GRADING SET's definition, the subject's components and the subject digest are unchanged, so no recorded verdict's subject digest changes. The rubric digest changes when the rubric file's bytes change, as it does today.

**Edit 3 — `contracts.md`, the paragraph that states the reference-line rule (the sentence beginning "Per that paragraph's rule that grading guidance MUST be written into the rubric itself").** Replace "the `dod_gate` node's prompt file MUST state this reference-line rule once, MUST name the governing scenario's step lines as its decision input, and MUST direct the judge, wherever it reads `scenarios.md` itself rather than taking a returned governing-heading verdict, to quote the step line that states the behaviour when it names a scenario heading as governing an assertion." with "the rubric file MUST state this reference-line rule once, MUST name the governing scenario's step lines as its decision input, and MUST direct the judge, wherever it grades a reference from a scenario heading's body in the subject's HEADINGS rather than from a returned governing-heading verdict, to quote from that body the step line that states the behaviour when it names a scenario heading as governing an assertion." Every other sentence of that paragraph is unchanged.

**Edit 3a — `contracts.md`, the paragraph that begins **Judged before admission.**** Replace "the same Definition-of-Done judgement the `dod_gate` node applies (its prompt," with "the same Definition-of-Done judgement the `dod_gate` node applies (its rubric file,". Every other word of that paragraph is unchanged.

**Edit 4 — `scenarios.md`, §"Scenario 239 — Every taking of the Definition-of-Done judgement grades one subject by one rubric", the Scenario Outline "A host taking grades by the node's rubric and appends only its ending contract".** Replace its step "Given the plugin build that will execute a dispatch carries the dod_gate node's prompt file" with "Given the plugin build that will execute a dispatch carries the Definition-of-Done rubric file", and its step "Then the judge's prompt carries that prompt file's bytes unchanged" with "Then the judge's prompt carries that rubric file's bytes unchanged". Every other line of that outline is unchanged. In the same Scenario 239, in the scenario "A changed rubric invalidates a stored verdict", replace the step "And the plugin build that will execute the dispatch carries a dod_gate prompt file with different bytes" with "And the plugin build that will execute the dispatch carries a rubric file with different bytes".

**Edit 5 — `scenarios.md`, the same Scenario 239.** Append these scenarios to the end of its Gherkin block, inside the same fenced block, after "Then needs-attention no longer lists the item as unpreflightable". The scenario's heading is unchanged:

```gherkin
  Scenario: A host taking grants its candidate no tools and says so
    Given a repository whose resolved dod_gate chain names codex-acp first and claude-acp second
    When the pre-dispatch taking of the Definition-of-Done judgement runs either candidate on the host
    Then that candidate's session is launched with an empty tool allowance
    And the ending contract appended to the rubric states that the candidate has no tools and that every input it grades is in the prompt

  Scenario: A candidate that cannot launch tool-less passes a pre-dispatch judgement on
    Given a resolved dod_gate chain whose first candidate's agent cannot be launched with an empty tool allowance
    When the pre-dispatch taking of the Definition-of-Done judgement is taken
    Then the first candidate is not run
    And the second candidate grades the subject
    And the taking's record names the first candidate with the cause no-tool-less-launch

  Scenario: A preflight with a candidate that cannot launch tool-less did not run
    Given a repository preflight chain one of whose candidates' agents cannot be launched with an empty tool allowance
    When the repository preflight is run for an item
    Then the preflight exits with its cannot-run code 2 and refuses nothing
    And its did-not-run record names that candidate with the cause no-tool-less-launch

  Scenario: A host prompt carries the subject and grading set and no instruction to read
    Given a repository whose committed dispatcher.sandbox_capabilities array names two capabilities
    When the pre-admission and the pre-dispatch takings each build the prompt they give the judge
    Then each prompt carries the rubric file's bytes, then the ending contract, then the whole subject with the two capability names sorted as its grading set
    And neither prompt instructs the judge to read, list, search or execute anything
    And neither prompt names /etc/livespec, the SPECIFICATION tree or a subject file

  Scenario: The node reads the rubric and subject its node prompt file names
    Given a dispatch of an item whose subject the Dispatcher writes to the run's subject file
    When the run's dod_gate node grades the item
    Then the node's prompt is the node prompt file, not the rubric file
    And the node grades the subject file's bytes by the rubric file
    And the node's subject digest and rubric digest equal those of the pre-dispatch taking for the same item

  Scenario: An unpublished capability set reaches the judge as the literal unpublished
    Given a repository that commits no dispatcher.sandbox_capabilities array
    When a host taking builds the prompt it gives the judge
    Then the subject in that prompt carries the grading set as the literal unpublished
```
