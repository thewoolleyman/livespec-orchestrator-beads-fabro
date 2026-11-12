---
topic: the-spec-change-tier-judgement
author: claude-opus-5-5:publish-draft-green-work-loss
created_at: 2026-11-12T09:50:37Z
---

## Proposal: The spec-stated judgement's clause selection reaches the stating paragraph and the inherited specification files

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The paragraph "The spec-stated judgement is one shared component" defines the judgement's clause provenance as the set of clauses it placed before its model in full, and requires that selection to be a deterministic function of the subject and the specification text. It says nothing about WHICH clauses the selection must reach, so a selection that withholds the very paragraph stating an item's behaviour, or that never reads a specification file the repository inherits, conforms to it. This proposal adds one paragraph under the same H2 that states what the selection covers. The specification text the judgement reads MUST include each specification file the governed repository's constraints declare as applying to it without restatement, under either layout the fleet uses. A declared inherited file that is absent from the checkout MUST be omitted and named in the clause provenance, and MUST NOT make the read fail. The selection MUST place in full the paragraphs most relevant to the asked-for behaviour wherever they sit, under any heading and at any depth, before it fills the remaining budget with heading-level clauses. The rendered prompt MUST stay under the judgement's prompt character ceiling. One sentence of the existing paragraph is amended to point at the new one, and Scenario 353 exercises it.

### Motivation

Measured 2026-11-11 by the publish-draft-green-work-loss plan seat (session 20481992). gmktec-factory-placement's dry run of 0.320.0's classify_spec_change_tier held 22 of 25 non-feature items. Independent per-repository readers found 7 of the 22 already stated by the ratified specification. Running the real condensed spec tree (_spec_tree_condensation, 200 000-character ceiling against a 2 068 305-character specification) on each item's asked-for behaviour showed two mechanisms that only the clause selection can fix. In M1 the condensation withheld the stating clause: bd-ib-b3nosr and bd-ib-hi7lzn had no stating sentence in the tree the judge saw, and overseer-umcueg had one stating clause withheld. In M3 an inherited file was absent: the judgement never read livespec/SPECIFICATION/non-functional-requirements.md, which this repository's constraints declare as applying without restatement (overseer-o9fn, livespec-orchestrator-git-jsonl-xajzy6). legacy-coordinator-agent admitted bd-ib-lrjdlo on 2026-11-11 as conformance to "The spec-stated judgement is one shared component". On 2026-11-12 at 09:45:15Z the v348 judgement itself held bd-ib-lrjdlo as spec-change tier (partial, spec v360, generalization target "## Dispatcher admission, WIP cap, and post-merge acceptance", linked topic the-spec-change-tier-judgement). Its rationale: "The visible text does not state that the tree must include inherited specification files, that the full-text selection must include the paragraph stating the behaviour, or the prompt-ceiling bound the bullets assert." The coordinator (session cb187a57) and the plan owner both agreed, and ruled this proposal rather than a release-spec-tier attestation. bd-ib-lrjdlo's implementation is complete on PR #5008, but that PR's CI failed because the reference reader raised FileNotFoundError on livespec/SPECIFICATION/non-functional-requirements.md in a checkout with no sibling livespec clone. That is why this proposal states the absent-file rule. Fleet scope: the judgement runs for every tenant the Dispatcher admits. The inheritance layouts in use today are two. Layout one is a constraints sentence naming a file that "applies to this plugin" or "applies to this library" "without restatement": livespec-orchestrator-beads-fabro, livespec-orchestrator-git-jsonl and livespec-runtime, each naming livespec/SPECIFICATION/non-functional-requirements.md. Layout two is a constraints sentence stating that every constraint in a named file "that applies to a Driver binding applies here unmodified" and that the tree does not restate them: livespec-driver-claude, livespec-driver-codex and livespec-driver-pi, each naming livespec/SPECIFICATION/constraints.md. livespec-dev-tooling, livespec-overseer and livespec core declare no inherited specification file; they only cite one. Owning work item: bd-ib-lrjdlo, plan publish-draft-green-work-loss (epic bd-ib-acrr56). Co-edit owed at revise, outside this spec target: tests/heading-coverage.json gains one row for the new "## Scenario 353" heading (test TODO, reason naming bd-ib-lrjdlo), per the repository's heading-coverage co-edit rule. The revise MUST confirm that Scenario 353 is still free when it cuts, because 350 to 352 are claimed by open proposals, and renumber if it is not.

### Proposed Changes

1. contracts.md: insert this new paragraph IMMEDIATELY AFTER the paragraph that begins "**The spec-stated judgement is one shared component.**" and ends "... on the terms that touchpoint states.", and BEFORE the paragraph that begins "**Host judgements take the resolved `dod_gate` chain.**":

**The judgement's clause selection reaches the stating paragraph and the inherited specification files.** This paragraph states what the specification text and the clause selection of the shared component above MUST cover, for every governing-heading verdict and every spec-change tier decision.

- The specification text the judgement selects from MUST be the governed repository's ratified specification tree TOGETHER WITH each inherited specification file. An inherited specification file is a specification file of another repository that the governed repository's `constraints.md` declares as applying to it without restatement. The declaration forms are a CLOSED list of exactly two, quoted here verbatim, where `<path>` is the inherited file's path and `<scope>` is `plugin` or `library`: the sentence "Every constraint in `<path>` applies to this <scope> without restatement."; and the sentence "Every constraint in `<path>` that applies to a Driver binding applies here unmodified; this tree does not relax or restate them.". A `constraints.md` declares an inherited specification file ONLY by one of those two forms. Any other mention of another repository's specification file, including a citation, a cross-reference or a quotation, MUST NOT be read as a declaration and adds nothing to the specification text. The Dispatcher MUST resolve each such file at the declared path, relative to the directory that holds the governed repository's sibling clones. That directory is the parent of the governed repository's root unless the operator configures another, and MUST NOT be the process's working directory.
- A declared inherited specification file that is absent at that path MUST be omitted from the specification text. Its absence MUST NOT make the read, the selection or the judgement fail, and MUST NOT be read as an empty file. The clause provenance of a verdict taken while an inherited file was omitted MUST name that file as omitted, so a later taking that can read the file does not reuse the verdict.
- A verdict MAY name a heading of an inherited specification file as governing. It MUST then name that heading verbatim together with the file's declared path.
- The selection MUST rank the paragraphs of that specification text by their relevance to the subject, and MUST place the most relevant paragraphs before the model IN FULL, wherever they sit: under a heading the subject does not name, at any heading depth, and including the first paragraph of a heading's body. It MUST reserve part of the prompt budget for those paragraphs before it fills the remaining budget with heading-level clauses, so a large tree MUST NOT crowd out a stating paragraph merely because its heading sorts or ranks later.
- The rendered prompt MUST stay under the judgement's prompt character ceiling. Every selection rule above applies within that ceiling, and the selection MUST remain a deterministic function of the subject and the specification text, as the paragraph above requires.

Scenario 353 in `scenarios.md` exercises this paragraph.

1b. contracts.md, in the paragraph "**The spec-stated judgement is one shared component.**", the sentence "The selection of those clauses MUST be a deterministic function of the item's subject and the specification text, and before reusing a verdict after a new revision the Dispatcher MUST repeat that selection against the new revision." MUST become: "The selection of those clauses MUST be a deterministic function of the item's subject and the specification text, which the paragraph \"The judgement's clause selection reaches the stating paragraph and the inherited specification files\" defines and whose coverage it states, and before reusing a verdict after a new revision the Dispatcher MUST repeat that selection against the new revision." No other sentence of that paragraph changes.

2. scenarios.md: append this new H2 section after the last ratified scenario:

## Scenario 353 — The spec-stated judgement places the stating paragraph in full, reads inherited specification files, and omits an absent one without failing

```gherkin
Feature: The judgement sees the clause that states the behaviour
  Scenario: A paragraph stating the behaviour under a heading the item does not name is placed before the model in full
    Given a ratified specification whose stating paragraph sits deep under a heading the item does not name
    And the whole specification exceeds the judgement's prompt character ceiling
    When the spec-stated judgement is taken for the item's asked-for behaviour
    Then the clauses placed before the model in full include that stating paragraph
    And the rendered prompt is under the prompt character ceiling
  Scenario: An inherited specification file is part of the specification text
    Given a repository whose constraints declare livespec/SPECIFICATION/non-functional-requirements.md as applying to it without restatement
    And that file is present under the sibling-clones directory
    When the spec-stated judgement is taken
    Then the specification text includes that file
    And a verdict may name one of its headings verbatim together with the file's declared path
  Scenario: A driver repository's inherited constraints file is read too
    Given a repository whose constraints state that every constraint in livespec/SPECIFICATION/constraints.md that applies to a Driver binding applies here unmodified
    And that file is present under the sibling-clones directory
    When the spec-stated judgement is taken
    Then the specification text includes that file
  Scenario: An absent inherited specification file is omitted and named, not raised on
    Given a repository whose constraints declare an inherited specification file
    And no sibling clone carries that file
    When the spec-stated judgement is taken
    Then the judgement completes with a verdict
    And the specification text omits that file
    And the verdict's clause provenance names that file as omitted
  Scenario: Another mention of a sibling specification file adds nothing
    Given a repository whose constraints mention a sibling repository's specification file in a form other than the two declaration forms
    And that file is present under the sibling-clones directory
    When the spec-stated judgement is taken
    Then the specification text does not include that file
  Scenario: The selection is deterministic
    Given an unchanged subject and an unchanged specification text
    When the selection is taken twice
    Then both takings place the same clauses before the model in full
```

No existing H2 heading is renamed or removed. The revise that accepts this proposal MUST add one `tests/heading-coverage.json` row for the new `## Scenario 353` heading in the same change.
