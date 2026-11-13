---
topic: preserve-runs-sh-keeps-every
author: claude:factory-run-work-preservation plan seat session d3d4ab
created_at: 2026-11-13T01:42:56Z
---

## Proposal: An operator preserve tool removes a run's local copy only once origin holds the commit it pushed, and retries a copy whose push failed

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Add a paragraph to contracts.md §"Dispatcher admission, WIP cap, and post-merge acceptance", directly after the paragraph whose opening sentence is "Preservation refs are deleted when the Dispatcher closes or collects an item's runs.". It states the local-copy retention rule for an operator preserve tool such as `dev-tooling/preserve/preserve_runs.sh`. The tool removes a run's local copy and its side files only once `git ls-remote` reads the ref its push wrote at exactly the commit that copy pushed. It keeps the copy, recording the repository and commit, when the push failed or the ref reads otherwise, and retries every kept copy on its next start before it reads any sandbox. A copy from before the rule counts as recording its `fabro/run/<run-id>` tip. A copy whose verdict is that no candidate carried work, or whose objects `git fsck` reports missing, is kept, and the tool names each kept copy with its reason. Add one numberless scenario plus its heading-coverage and debt-register rows.

### Motivation

bd-ib-yw7yot (plan factory-run-work-preservation, epic bd-ib-nckst7) is READY but held at spec-change tier. Its filing-time tier record names the linked topic preserve-runs-sh-keeps-every, which no history, pending proposal or spec branch carried. legacy-coordinator-agent (session 56ce1bcd, about 01:2xZ on 2026-11-13) routed it to this seat as a spec-tier orphan. This proposal is filed under exactly that slug.

THE DEFECT, measured. `dev-tooling/preserve/preserve_runs.sh` keeps a local bare copy plus side files per run in `${XDG_STATE_HOME:-~/.local/state}/livespec-preserve` on the control node, and nothing removes them. At filing on 2026-11-12 (a dev-host-disk-retention measurement routed by legacy-coordinator-agent session 0f6da4ba) that was 77 copies and 3.4 GB, about 0.6 GB a day, and 69 of the 77 were already on origin at exactly their local fabro/run tip. Re-measured by this seat at 2026-11-13 about 01:45Z: 6.0 GB and 133 copies, with the script still writing at 01:42Z. The rule the coordinator set when routing it: a copy is removed only once `git ls-remote` shows the origin ref at that copy's commit; a copy whose push failed is never removed and is retried instead; an empty diff against the merge base still counts as not preserved.

WHY IT NEEDS SPEC TEXT: the ratified spec does not mention the operator preserve tool at all. On origin/master, zero hits for preserve_runs, "operator preserve" or "preserve work" across contracts.md, scenarios.md, constraints.md and spec.md, each searched separately. Its only mention is in the pending proposal an-operator-preserve-writes-a, which governs the needs-human ref the tool WRITES, not its local copies.

PLACEMENT: this repository's spec has no non-functional-requirements.md. The nearest governing text is the ref-retention paragraph "Preservation refs are deleted when the Dispatcher closes or collects an item's runs." (Scenario 320), which yw7yot's Definition of Done already references and which carries plan assertion 4 ("Preserved run refs on origin are removed by a stated retention rule"). This paragraph is that rule's local-copy counterpart, so it is placed directly after it.

IN-FLIGHT ALIGNMENT: a-commit-settle-abort-preserves-the-in-progress-resolution edits the TEXT of the anchor paragraph (it adds resolution refs to the deletion sentence) but inserts nothing after it; this proposal anchors on that paragraph's unchanged opening sentence, so the two compose in either order. an-operator-preserve-writes-a governs which needs-human ref the operator tool writes; this proposal governs only when its local copy may be removed. Relationship to both: align. bd-ib-yw7yot is sequenced never beside bd-ib-4jxlnn, because both change preserve_runs.sh.

### Proposed Changes

### 1. `SPECIFICATION/contracts.md` §"Dispatcher admission, WIP cap, and post-merge acceptance": add one paragraph

Insert this paragraph directly AFTER the paragraph whose opening sentence is **Preservation refs are deleted when the Dispatcher closes or collects an item's runs.**, separated from it and from the next paragraph by one blank line. No existing paragraph changes:

```markdown
**An operator preserve tool removes a run's local copy only once origin holds it.** This paragraph governs an operator preserve tool, such as `dev-tooling/preserve/preserve_runs.sh`, that copies a run's committed tree out of its sandbox into a local work directory and pushes it to a ref on the run's repository. After such a push, the tool MUST read that ref with `git ls-remote`. When the ref reads exactly the commit the copy pushed, the tool MUST remove that run's local copy and every file it keeps beside the copy. When the push failed, or the ref reads another commit or is absent, the tool MUST keep the copy and MUST record beside it the repository and the commit it tried to push. On each later start, before it reads any sandbox, the tool MUST push every kept copy's recorded commit again, and MUST remove that copy only once `git ls-remote` reads the ref at that commit. A copy written before this rule, which records no commit, MUST be treated as recording the tip of its `fabro/run/<run-id>` branch, and MUST be removed only once `git ls-remote` reads a ref named for that run at exactly that tip. The tool MUST keep a copy whose preservation verdict is that no candidate commit carried work, and a copy whose objects `git fsck` reports missing. Its output MUST name every kept copy with the reason it was kept. The tool MUST NOT remove a copy on any other condition, so the only copy of a run's work is never deleted before origin holds it.
```

### 2. `SPECIFICATION/scenarios.md`: add one scenario, numbered at revise

The heading is numberless here. The revise pass MUST assign the next free scenario number and update the heading text in changes 3 and 4 to match.

~~~markdown
## Scenario: an operator preserve tool removes a run's local copy only once origin holds the commit it pushed

```gherkin
Feature: Operator preserve copies do not accumulate, and the only copy of a run's work is never lost
  As the operator of the control node that preserves factory runs
  I want each run's local preserve copy removed once origin verifiably holds it, and kept and retried otherwise
  So that the work directory stops growing without bound while no unpushed work is deleted

  Scenario: A verified push removes the local copy
    Given the operator preserve tool pushed run R's copy at commit P to a ref on R's repository
    And git ls-remote reads that ref at exactly P
    Then the tool removes R's local copy and every file beside it from the work directory

  Scenario: A failed push keeps the copy and records what it tried to push
    Given the operator preserve tool's push of run R's copy at commit P failed
    Then the tool keeps R's local copy
    And it records beside the copy R's repository and commit P
    And its output names the kept copy with the reason it was kept

  Scenario: A kept copy is retried on the next start and removed once origin holds it
    Given a kept copy of run R recording repository U and commit P, whose ref no origin read holds at P
    When the operator preserve tool starts
    Then before it reads any sandbox it pushes P to U again
    And it removes the copy only once git ls-remote reads the ref at P

  Scenario: A copy from before the rule is judged by its run branch tip
    Given a copy of run R that records no commit, whose fabro/run/R branch tip is T
    When the operator preserve tool starts
    Then it removes the copy only once git ls-remote reads a ref named for R at exactly T

  Scenario: A work-free or damaged copy is kept and named
    Given a copy of run R whose preservation verdict is that no candidate commit carried work, or whose objects git fsck reports missing
    When the operator preserve tool runs
    Then it keeps that copy
    And its output names the copy with the reason it was kept
```
~~~

### 3. `tests/heading-coverage.json`: add the new heading in the same revise

The revise that ratifies this MUST add one entry, using the heading as numbered at revise:

```json
{"heading": "## Scenario: an operator preserve tool removes a run's local copy only once origin holds the commit it pushed", "spec_root": "SPECIFICATION", "spec_file": "scenarios.md", "test": "TODO", "work_item": "bd-ib-yw7yot", "reason": "A test at the integration tier or above is owed: the operator preserve tool's own suite, delivered by bd-ib-yw7yot, driving preserve_runs.sh against a local bare origin."}
```

### 4. `tests/heading-coverage-debt.json`: add the matching row in the same revise

The register has no generator, so the row is authored. `check-heading-coverage-debt-register` admits it under its spec-first admission, because this same change introduces the heading:

```json
{"spec_root": "SPECIFICATION", "spec_file": "scenarios.md", "heading": "## Scenario: an operator preserve tool removes a run's local copy only once origin holds the commit it pushed", "work_item": "bd-ib-yw7yot", "first_seen": "<revise date>"}
```

No existing heading changes, per AGENTS.md §"Revise co-edit discipline".

### 5. Follow-through outside the spec (not part of this revise)

On ratification, bd-ib-yw7yot's Definition of Done `References:` line SHOULD name the new scenario heading, as numbered at revise, beside `## Scenario 320 — Preservation refs are deleted when the Dispatcher closes or collects an item's runs`. Its spec-change tier is then re-classified.
