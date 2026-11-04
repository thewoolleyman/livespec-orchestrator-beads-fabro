---
topic: dod-judgement-shared-rubric
author: claude-opus-5-5
created_at: 2026-10-22T08:30:11Z
---

## Proposal: Every taking of the Definition-of-Done judgement grades one subject by one rubric

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

The Definition-of-Done judgement is taken up to four times before implementation spend: by a repository's host-side preflight, before admission, before dispatch, and in the `dod_gate` node. The ratified text already calls the earlier takings "the same Definition-of-Done judgement the `dod_gate` node applies". It does not pin what each taking grades, which capability set it grades against, or what a taking may add to the node's prompt, and the takings have drifted apart in practice. This proposal makes the node's prompt file the one RUBRIC. Every taking loads it from the build that will execute the dispatch and may append only an ending contract. Every taking also grades one SUBJECT, defined component by component: the rendered goal without the Dispatcher's own judgement receipts, the referenced heading bodies, a content identity of the ratified spec tree at one resolved commit, and the grading capability set. The committed `dispatcher.sandbox_capabilities` mirror becomes the one grading set, because it is the only source every taking can read. The published image file stays the authority for what the image provides, and a difference between the two is a journaled configuration mismatch. Verdict reuse and drain exclusion are re-keyed on the subject and rubric digests, so they no longer key on the narrower "criteria and referenced headings" inputs. The pre-dispatch judgement and the sandbox seed must use the same resolved commit. The References-coverage rule the node enforces is written into the contract as a semantic judgement and is not added to the deterministic host wall. The node keeps running on every run. A node refusal of a subject and rubric that a pre-dispatch verdict admitted is journaled as a disagreement, which makes the residual rate measurable.

### Motivation

Filed under bd-ib-gob6gl (P1, coordinator rulings R588 and R589). Four measured instances on 2026-10-22 show a host-side PASS followed by an in-run refusal on byte-identical Definition-of-Done text, each costing a factory slot. (1) livespec-dev-tooling-u5j5f6: the host preflight passed on both legs; the in-run dod_gate of run 01M5GMPAYBDT refused after 73 s because the References line named only a non-scenario H2 while a scenario governed the behaviour. (2) livespec-dev-tooling-7kvh2d: the same Codex leg gave PASS and then FAIL ten minutes apart on unchanged text. (3) livespec-dev-tooling-7oec4d: the launch-time preflight passed at 07:52:30Z, and run 01M5H9TYCAVD refused at 55 s for three missing governing headings. (4) livespec-dev-tooling-4cipbr: the preflight passed at 08:01:58Z, and run 01M5HACC4AZZ refused at 2m27s for a missing contract section (`## Delegated pre-push gate`) whose clause governed two assertions.

Reading the takings shows they do not grade the same thing. The node grades the full rendered goal: title, description, criteria, notes, lessons and every ledger comment. It takes its capability set from the published image file. The Dispatcher's host judgement (`_dispatcher_dod_judgement_run.py`) grades the effective criteria plus the referenced heading bodies, with no ledger comments, and takes its capability set from the committed mirror. The stopgap `dev-tooling/dod-preflight.sh` grades title, description and comments, and it appends a check-5 grading instruction of its own that the node never receives. The References rule the node enforced in instances 1, 3 and 4 (every governing scenario plus the governing contract section) is stricter than the rubric's written check 6, which makes a non-scenario H2 alone a finding only when a scenario states the behaviour. A reader of the contract therefore cannot predict which judge is right.

R589 sets the direction: same inputs and same rubric; the in-run node stays, because contracts.md requires the semantic half to run in the node on every run; and a deterministic host References check is rejected.

An independent gpt-6-astra review of the first draft raised three blockers, each resolved here:
- The capability source contradicted "Sandbox capabilities", so that paragraph and Scenario 139 are amended to a single grading set.
- The new invalidation conflicted with the retained reuse and drain-exclusion rules of "Judged again before dispatch", and a verdict's own ledger comment would have changed its subject. The reuse and exclusion rules and Scenario 174 are therefore re-keyed on the two digests, and judgement receipts are excluded from the subject.
- The digest and spec snapshot were underspecified, so both are now defined component by component, with a canonical serialization, and the judgement and the sandbox seed share one resolved commit.

A second review round raised two further blockers, also resolved here:
- The capability remedy "add the capability to the image" no longer cleared a finding graded against the array, so the remedy now adds the capability to the array as well.
- The shared spec-stated component kept its own reuse rule, which could reuse a governing-heading verdict after a rider changed the assertion's meaning. That rule is now keyed on the verdict's input, which includes the riders, and on the spec identity.

The consequence of the mirror-as-grading-set choice is stated deliberately. A repository that commits no mirror now has an UNKNOWN capability set at every taking, the node included, so no taking raises a missing-capability finding there. The stopgap preflight already refuses to run without a mirror. An assertion graded feasible on a mirrored name the image does not publish still meets the ratified missing-capability ending of `proof_capture`, and the mismatch is journaled at the gate, so the error is bounded and visible rather than silent.

The original gob6gl parser defect (a non-bullet line inside the section projected as a factory_captured assertion) needs no spec change, because Scenario 131 already requires the host-side wall to refuse a malformed section; it stays in the implementing item's scope. Instance 2 shows nondeterminism within one judge, which a shared rubric and subject cannot remove. The disagreement record is what measures that residual once this lands.

### Proposed Changes

**1. `SPECIFICATION/contracts.md`, the `dod_gate` paragraph.** Replace the clause

> and every reference line that names only a non-scenario H2 while a scenario heading states the behaviour the assertion names (§"Effective acceptance criteria" → "Behavioural assertions" and "The Definition of Done section"), naming the remedy in each case.

with

> and every reference line that omits, for any assertion, a heading that governs it — each `## Scenario NN — <title>` heading of `scenarios.md` that states behaviour the assertion names, and each non-scenario H2 whose clauses govern that behaviour — naming each omitted heading verbatim and the remedy of adding it to the reference line (§"Effective acceptance criteria" → "Behavioural assertions" and "The Definition of Done section"). This reference-coverage finding is a semantic judgement: it MUST NOT be added to the mechanical half the host-side wall runs, and a reference line the wall accepts MAY still carry it.

In the same paragraph, after its final sentence "neither earlier judgement removes or replaces the node.", append:

> Every taking of this judgement grades the rubric and subject defined in §"Effective acceptance criteria" → "One rubric, one subject".

In the same paragraph, replace the first remedy "add the capability to the sandbox image;" with "add the capability to the sandbox image and list it in the committed `dispatcher.sandbox_capabilities` array;", because the array is the grading set (change 2) and a capability the image gains but the array omits still fails the assertion. The rubric MUST prescribe that same remedy wherever it names this one.

**2. `SPECIFICATION/contracts.md`, the "Sandbox capabilities" paragraph.** Replace the text from "The published file is the authority:" through "and MUST NOT infer capability from the item's own prose." with:

> The committed `dispatcher.sandbox_capabilities` array is the GRADING SET. Every taking of the Definition-of-Done judgement (§"Effective acceptance criteria" → "One rubric, one subject"), the `dod_gate` node included, MUST grade proof-mode feasibility against that array and against nothing else, because it is the one source every taking can read. The published file is the authority for what the image provides. Where the file exists, the `dod_gate` node MUST compare it with the grading set and MUST report in its own output, as a configuration mismatch, each name the array lists that the image does not publish and each name the image publishes that the array omits. The Dispatcher MUST journal every mismatch. A configuration mismatch is not a finding against the item and MUST NOT fail the gate. An assertion graded feasible on a listed name the image does not publish meets the missing-capability ending of `proof_capture`, which names that capability. Where the repository commits no array, the capability set is UNKNOWN for every taking, whether or not the image publishes a file: no taking may raise a missing-capability finding, and each MUST report `sandbox-capabilities: unpublished` in its output. Every taking MUST take the grading set from the committed array alone and MUST NOT infer capability from the item's own prose.

In the same paragraph, replace "The fleet sandbox image MUST publish the file before the gate's missing-capability duty takes effect for a repository; that image change is sequenced ahead of the gate change." with "The fleet sandbox image MUST publish the file, because it is the authority the node compares the grading set against. A repository MUST NOT list a name in its array that the image it dispatches to does not publish, and the journaled mismatch is how a violation is found."

**3. `SPECIFICATION/contracts.md`, §"Effective acceptance criteria".** Insert a new paragraph immediately BEFORE the paragraph **Judged before admission.**:

> **One rubric, one subject.** The Definition-of-Done judgement is taken by the `dod_gate` node, before admission, before dispatch, and by any host-side preflight a repository runs before launching a dispatch. Every taking MUST grade by ONE rubric: the `dod_gate` node's prompt file, read from the plugin build that will execute the dispatch. A taking MUST NOT add, remove or restate a check. A taking other than the node MAY append only an ending contract stating the verdict form it must return. Any other guidance about how to grade a check, including any statement about where the capability set comes from, MUST be written into the rubric itself, so that the node grades by it too.
>
> Every taking MUST grade one SUBJECT, made of four components.
> - The GOAL: the item's rendered goal exactly as the Dispatcher renders it for the node — title, description, effective criteria, notes, lessons and every ledger comment except the Dispatcher's own Definition-of-Done judgement records (verdict, did-not-run and disagreement comments). Those records are receipts, not brief, so the Dispatcher MUST omit them from the node's rendered goal as well.
> - The HEADINGS: the verbatim body of each heading the reference line names.
> - The SPEC IDENTITY: a digest of the bytes of every file under the governed spec root at the resolved commit, excluding `proposed_changes/` and `history/`, so that a ratified revision or any change to a governing scenario, referenced or not, changes it.
> - The GRADING SET: the committed `dispatcher.sandbox_capabilities` array at that commit, as sorted names, or the literal `unpublished`.
>
> The RESOLVED COMMIT is the default-branch commit the dispatch seeds the sandbox from. The Dispatcher MUST resolve it once per dispatch, MUST take the pre-dispatch judgement against it, and MUST seed the sandbox from that same commit. A host taking before dispatch resolves the default branch's current tip. Every recorded verdict MUST carry the SUBJECT DIGEST and the RUBRIC DIGEST. The rubric digest is a SHA-256 over the rubric file's bytes. The subject digest is a SHA-256 over the four components in the order above, each encoded as UTF-8 and preceded by its byte length in ASCII decimal and one newline. Within the components: the HEADINGS are the bodies in reference-line order, each preceded by its heading line; the SPEC IDENTITY is itself a SHA-256 over the included files sorted by their path relative to the spec root, each contributing its path, a NUL byte, its byte length in ASCII decimal, a NUL byte and its bytes; the GRADING SET is the sorted names joined by newlines.
>
> When a run's `dod_gate` node refuses an item whose most recent pre-dispatch verdict admitted the same subject digest under the same rubric digest, the Dispatcher MUST append one `dod-judgement-disagreement` row to the dispatch journal and one judgement-record comment on the item. Each MUST name the run, both digests, the admitting verdict's timestamp and the node's findings. The item MUST rest exactly as any `dod_gate` refusal rests it. Scenario 239 in `scenarios.md` exercises this paragraph.

**3a. `SPECIFICATION/contracts.md`, the paragraph "The spec-stated judgement is one shared component".** Replace "A verdict MUST be reused while the item's effective criteria and referenced headings are byte-unchanged and no specification revision has been ratified since it was taken;" with:

> A verdict MUST be reused only while its input and the spec identity it was taken against (§"Effective acceptance criteria" → "One rubric, one subject") are both unchanged since it was taken. For a governing-heading verdict taken for an assertion, the input is the assertion's text together with every ledger comment the subject's goal carries, so a rider appended to the item invalidates the governing-heading verdicts of all its assertions. For a work-item classification, the input is the subject's goal.

The rest of that paragraph is unchanged.

**4. `SPECIFICATION/contracts.md`, the "Judged again before dispatch" paragraph.** Replace "while the item's effective criteria and referenced headings are byte-unchanged since that verdict was taken and no specification revision has been ratified since," with "while that verdict's subject digest and rubric digest both equal the digests of the subject and rubric this dispatch would grade (\"One rubric, one subject\"),". Replace "until its effective criteria or referenced headings change or a specification revision is ratified," with "until the subject digest or the rubric digest it would now be graded by differs from the refusing verdict's,". The "Judged before admission" paragraph is otherwise unchanged; its verdict carries both digests under "One rubric, one subject".

**5. `SPECIFICATION/scenarios.md`, Scenario 174.** In the scenario "A refused item is not judged or commented again while it is unchanged", replace its two Given lines with:

```gherkin
    Given an item whose pre-dispatch judgement refused it
    And the subject digest and rubric digest it would now be graded by equal the refusing verdict's
```

Rename the scenario "A refused item re-enters enumeration and is judged once after its criteria change or a revision is ratified" to "A refused item re-enters enumeration and is judged once after its subject or rubric changes", and replace its line "And its effective criteria or referenced headings have changed, or a specification revision has been ratified, since that verdict was taken" with:

```gherkin
    And the subject digest or the rubric digest it would now be graded by differs from the refusing verdict's
```

**6. `SPECIFICATION/scenarios.md`, Scenario 139.** Replace the scenarios of its gherkin block with:

```gherkin
Feature: Proof modes are graded against the committed capability set, and the published file is compared with it
  Scenario: A factory-captured assertion needing an unlisted capability is a gate finding
    Given a repository whose committed dispatcher.sandbox_capabilities lists terminal, tmux and headless_browser
    And a sandbox image publishing the same three names
    And an item whose factory-captured assertion is about behaviour inside herdr
    When the dod_gate node evaluates the rendered goal
    Then the run ends through the structured needs-human ending naming the assertion and the capability herdr
    And the finding lists the remedies in order: add the capability to the image and list it in the committed array, declare host_captured with a Reason, declare human_attested only when no agent session can exercise it
  Scenario: Publishing the capability without listing it leaves the finding
    Given the same item, a sandbox image that now publishes herdr, and a committed array that still omits it
    When the dod_gate node evaluates the rendered goal
    Then the run still ends through the structured needs-human ending naming herdr
    And the gate's output reports herdr as a configuration mismatch
  Scenario: Listing and publishing the capability clears the finding
    Given the same item, a committed array that now lists herdr, and a sandbox image that publishes herdr
    When the dod_gate node evaluates the rendered goal
    Then the run proceeds to the implement node
  Scenario: An image without the capability file is graded by the committed array
    Given a sandbox image that publishes no capability file
    And a repository whose committed dispatcher.sandbox_capabilities lists terminal and tmux
    When the dod_gate node evaluates a factory-captured assertion needing a browser
    Then the finding names headless_browser as missing
  Scenario: With no committed array the capability set is unknown even when the image publishes one
    Given a repository with no committed dispatcher.sandbox_capabilities
    And a sandbox image publishing terminal
    When the dod_gate node evaluates a factory-captured assertion needing a browser
    Then no missing-capability finding is raised
    And the gate's output reports sandbox-capabilities unpublished
  Scenario: A difference between the array and the published file is reported without failing the gate
    Given a committed array listing terminal and herdr
    And a sandbox image publishing terminal and headless_browser
    And an item whose assertions need only the terminal
    When the dod_gate node evaluates the rendered goal
    Then the gate's output reports herdr and headless_browser as configuration mismatches
    And the Dispatcher journals the mismatches
    And the run proceeds to the implement node
  Scenario: The capability set is read, never inferred from the item
    Given a committed array and a sandbox image both listing only terminal
    And an item whose description states that the sandbox carries herdr
    When the dod_gate node evaluates its factory-captured assertion about behaviour inside herdr
    Then the finding names herdr as missing
  Scenario: A host-captured declaration is refused where a listed capability can exercise the assertion
    Given a committed array and a sandbox image both listing headless_browser
    And an item declaring a web-interface behaviour of its own application under a Host-captured sub-heading
    When the dod_gate node evaluates the rendered goal
    Then the run ends through the structured needs-human ending naming the assertion and the capability headless_browser
```

Rename its H2 from "## Scenario 139 — The gate checks each proof mode against the capabilities the sandbox image publishes" to "## Scenario 139 — The gate checks each proof mode against the committed capability set and reports where the image differs", and rename that heading's entry in `tests/heading-coverage.json` to the same text, keeping its other fields.

**7. `SPECIFICATION/scenarios.md`.** Add after the last scenario:

```gherkin
## Scenario 239 — Every taking of the Definition-of-Done judgement grades one subject by one rubric

Feature: A Definition of Done passed before dispatch is graded in-run by the same rubric on the same subject
  As the operator of a factory
  I want every Definition-of-Done judgement to grade the same text by the same rules
  So that a pre-dispatch pass is not refused in-run on unchanged bytes

  Scenario Outline: A host taking grades by the node's rubric and appends only its ending contract
    Given the plugin build that will execute a dispatch carries the dod_gate node's prompt file
    When the <taking> judgement is taken on the host
    Then the judge's prompt carries that prompt file's bytes unchanged
    And after it only the ending contract and the subject

    Examples:
      | taking                   |
      | repository preflight     |
      | pre-admission            |
      | pre-dispatch             |

  Scenario: The subject carries rider comments and omits judgement receipts
    Given a ready item whose ledger comments include a rider appended after filing and an earlier pre-admission verdict comment
    When the pre-dispatch judgement is taken
    Then the subject carries the rider's text and omits the verdict comment
    And the node's rendered goal for a dispatch of that item carries the rider and omits the verdict comment
    And appending the new verdict comment leaves the item's subject digest unchanged

  Scenario Outline: A reference line missing one of several governing headings is refused by every host taking
    Given an item whose reference line names one of the two scenario headings that state its first assertion's behaviour
    And a non-scenario H2 of contracts.md whose clauses govern its second assertion is not on its reference line
    When the <taking> judgement is taken
    Then it refuses the item naming the omitted scenario heading and that H2 verbatim, each with the remedy of adding it
    And no factory run is created

    Examples:
      | taking               |
      | repository preflight |
      | pre-admission        |
      | pre-dispatch         |

  Scenario: A rider that changes the governing heading invalidates the reused governing-heading verdict
    Given an item admitted with a governing-heading verdict naming one scenario heading for its assertion
    And a rider is appended that narrows the assertion's behaviour to one another scenario heading states
    And the item's effective criteria and referenced heading bodies are unchanged
    When the pre-dispatch judgement is taken
    Then the governing-heading verdict is taken again rather than reused
    And a reference line that omits the newly governing heading is refused naming it

  Scenario: A change to an unreferenced governing scenario invalidates an admission verdict
    Given an item admitted by its pre-admission verdict
    And a scenario heading the item does not reference is added to the ratified spec tree before dispatch
    When the Dispatcher selects the item for a dispatch
    Then the subject digest differs from the admission verdict's
    And the judgement is taken again against the resolved commit before any claim is taken

  Scenario: The judgement and the sandbox seed share one resolved commit
    Given the default branch advances while a dispatch is being prepared
    When the Dispatcher takes the pre-dispatch judgement and creates the run
    Then the sandbox is seeded from the commit the judgement's spec identity was computed at

  Scenario: A changed rubric invalidates a stored verdict
    Given an item whose pre-dispatch verdict admitted it under one rubric digest
    And the plugin build that will execute the dispatch carries a dod_gate prompt file with different bytes
    When the Dispatcher selects the item for a dispatch
    Then the stored verdict is not reused
    And the judgement is taken again by the new rubric

  Scenario: The host taking and the node grade the same capability set
    Given a committed array listing terminal and herdr and a sandbox image publishing only terminal
    And an item whose factory-captured assertion is about behaviour inside herdr
    When the pre-dispatch judgement is taken and the run's dod_gate node grades the item
    Then neither raises a missing-capability finding for herdr
    And the node reports herdr as a configuration mismatch that the Dispatcher journals

  Scenario: An in-run refusal of an admitted subject is recorded as a disagreement
    Given an item whose pre-dispatch verdict admitted a subject digest under a rubric digest
    When the run's dod_gate node refuses that same subject under that same rubric
    Then the dispatch journal carries one dod-judgement-disagreement row naming the run, both digests, the admitting verdict's timestamp and the node's findings
    And the item carries one judgement-record comment with the same facts
    And the item rests at blocked with blocked_reason needs-human exactly as any dod_gate refusal rests it
```

**8. `tests/heading-coverage.json`.** Add the entry:

```json
{
  "heading": "## Scenario 239 — Every taking of the Definition-of-Done judgement grades one subject by one rubric",
  "spec_root": "SPECIFICATION",
  "spec_file": "scenarios.md",
  "test": "TODO",
  "reason": "An integration-tier test is owed for this heading: ratified with proposal dod-judgement-shared-rubric, and the owning work-item bd-ib-gob6gl makes every taking of the Definition-of-Done judgement grade one subject by one rubric, together with the test that binds this entry.",
  "work_item": "bd-ib-gob6gl"
}
```
