---
topic: preserve-runs-sh-keeps-every
author: claude:factory-run-work-preservation plan seat session 8a6b35
created_at: 2026-11-13T02:52:32Z
---

## Proposal: An operator preserve tool removes a run's local copy only once origin holds the commit it pushed, keeps every other copy with no time bound, and reports what it keeps

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json
- tests/heading-coverage-debt.json

### Summary

Add a paragraph to contracts.md §"Dispatcher admission, WIP cap, and post-merge acceptance", directly after the paragraph whose opening sentence is "When the events cannot be read, the Dispatcher MUST still apply the disposition above.". It states the local-copy retention rule for an operator preserve tool such as `dev-tooling/preserve/preserve_runs.sh`. It defines when a candidate commit carries no work (its tree is identical to the tree of its merge base with origin's default branch), and keeps a copy none of whose candidates carries work. Otherwise the tool removes a run's local copy and its side files only once `git ls-remote` reads the ref its push wrote at exactly the commit that copy pushed, and keeps the copy, recording its repository, ref and commit, when the push failed or the ref reads another commit or is absent. It retries every kept copy before it reads any sandbox. A copy from before the rule is judged by re-running the tool's own candidate selection, and its repository is taken from the fleet repository whose origin carries the preserve ref, or named unknown and kept. A copy whose objects `git fsck` reports missing is kept. Kept copies have no time bound, and every run reports their count, total bytes, and each one's run id, bytes and reason. Add one numberless scenario, its heading-coverage entry, and the regenerated debt-register row.

### Motivation

bd-ib-yw7yot (plan factory-run-work-preservation, epic bd-ib-nckst7) is READY but held at spec-change tier. Its filing-time tier record names the linked topic preserve-runs-sh-keeps-every, which no history, pending proposal or spec branch carried. legacy-coordinator-agent (session 56ce1bcd, about 01:2xZ on 2026-11-13) routed it to this seat as a spec-tier orphan. This proposal is filed under exactly that slug.

THIS IS A REGENERATION. The first filing (pull request #5115, head 72faa1693) FAILED the coordinator's grade (legacy-coordinator-agent successor session, about 02:4xZ on 2026-11-13). It is regenerated under the same slug with the six required fixes: (1) define "carries no work" and keep a copy none of whose candidates carries work; (2) make the removal sentence name its exceptions; (3) judge a pre-rule copy by re-running the tool's candidate selection, name the ref pattern, and say where a pre-rule copy's repository comes from; (4) state that kept copies have no time bound and require a per-run report of them; (5) give every scenario a When, and add the case where the ref reads another commit or is absent; (6) move the insertion point. Change 4 now regenerates the debt register rather than hand-authoring a row.

THE DEFECT, measured. `dev-tooling/preserve/preserve_runs.sh` keeps a local bare copy plus side files per run in `${PRESERVE_WORK:-${XDG_STATE_HOME:-~/.local/state}/livespec-preserve}` on the control node, and nothing removes them. At filing on 2026-11-12 (a dev-host-disk-retention measurement routed by legacy-coordinator-agent session 0f6da4ba) that was 77 copies and 3.4 GB, about 0.6 GB a day, and 69 of the 77 were already on origin at exactly their local fabro/run tip. Re-measured by this seat at 2026-11-13 about 01:45Z: 6.0 GB and 133 copies, with the script still writing at 01:42Z. The rule the coordinator set when routing it: a copy is removed only once `git ls-remote` shows the origin ref at that copy's commit; a copy whose push failed is never removed and is retried instead; an empty diff against the merge base still counts as not preserved.

THE PRE-RULE COPIES RECORD NO REPOSITORY, measured by this seat on 2026-11-13. A bare copy's config carries no remote URL. Its side files are `.git.sizes`, `.git.list`, `.git.args`, `.push.err`, `.nh.err` and `.alias.err`; `.git.args` holds only object paths, and 0 of 948 side files mention github.com. The tool takes a run's repository from the sandbox's remote URL (preserve_runs.sh line 117) and writes it nowhere beside the copy. So a pre-rule copy's repository can only be found by asking which fleet repository's origin carries its preserve ref, and new copies must record it.

WHAT "CARRIES NO WORK" MEANS HERE. The definition is the read-side one of contracts §"Factory-configurable ACP fallback priority" → "A needs-human tree is recognised by the run it carries, not only by its ref name": a tip whose tree is identical to the tree of its merge base with the default branch carries no work. preserve_runs.sh already decides exactly this with `git diff --quiet $mb $c` over the whole tree, the top-level `.fabro` directory included (lines 150-179). Two nearby rules are deliberately NOT reused. The run-time tree guard of "Each committing step of a run preserves the run branch's tip to an ordered work-in-progress ref" compares a tip with the run's base commit and the default branch's head, but the tool knows no base commit for a run. The `.fabro` exclusion of "A run's ending names its latest preserved capture on the item" is a reporting measure for a ledger comment, not a test of whether work exists.

WHY IT NEEDS SPEC TEXT: the ratified spec does not mention the operator preserve tool at all. On origin/master, zero hits for preserve_runs, "operator preserve" or "preserve work" across contracts.md, scenarios.md, constraints.md and spec.md, each searched separately. Its only mention is in the pending proposal an-operator-preserve-writes-a, which governs the needs-human ref the tool WRITES, not its local copies.

PLACEMENT: this repository's spec has no non-functional-requirements.md. The nearest governing text is the ref-retention paragraph "Preservation refs are deleted when the Dispatcher closes or collects an item's runs." (Scenario 320), which yw7yot's Definition of Done already references and which carries plan assertion 4 ("Preserved run refs on origin are removed by a stated retention rule"). The paragraph that directly follows it on master, "When the events cannot be read, the Dispatcher MUST still apply the disposition above.", must stay adjacent to the text it points back to, so the new paragraph goes after THAT paragraph, not between the two.

IN-FLIGHT ALIGNMENT: no pending proposal on origin/master edits or anchors on the paragraph that opens "When the events cannot be read" (each file under SPECIFICATION/proposed_changes/ searched). a-commit-settle-abort-preserves-the-in-progress-resolution edits the text of "Preservation refs are deleted..." but inserts nothing after either paragraph, so the two compose in either order. an-operator-preserve-writes-a governs which needs-human ref the operator tool writes; this proposal governs only when its local copy may be removed. Relationship to both: align. bd-ib-yw7yot is sequenced never beside bd-ib-4jxlnn, because both change preserve_runs.sh.

### Proposed Changes

### 1. `SPECIFICATION/contracts.md` §"Dispatcher admission, WIP cap, and post-merge acceptance": add one paragraph

Insert this paragraph directly AFTER the paragraph whose opening sentence is **When the events cannot be read, the Dispatcher MUST still apply the disposition above.** (on origin/master at the time of filing, the paragraph directly after **Preservation refs are deleted when the Dispatcher closes or collects an item's runs.**), separated from it and from the next paragraph by one blank line. It MUST NOT be inserted between those two paragraphs, which would separate "the disposition above" from the text it names. No existing paragraph changes:

```markdown
**An operator preserve tool removes a run's local copy only once origin holds it.** This paragraph governs an operator preserve tool, such as `dev-tooling/preserve/preserve_runs.sh`, that copies a run's committed tree out of its sandbox into a local work directory and pushes a commit of that run to a ref on the run's repository. The tool's *candidates* for a copy are, in order: the tip of the copy's `fabro/run/<run-id>` branch, or its `HEAD` when the copy has no such branch; then that branch's reflog, newest entry first; then the copy's `HEAD` reflog, newest entry first. A candidate *carries no work* when its tree is identical to the tree of its merge base with the default branch of the run's repository on origin, compared over the whole tree. This is the definition of "A needs-human tree is recognised by the run it carries, not only by its ref name" in §"Factory-configurable ACP fallback priority". It is not the run-time tree guard of "Each committing step of a run preserves the run branch's tip to an ordered work-in-progress ref", which needs the run's base commit that the tool does not know, and it does not exclude the `.fabro` directory, which "A run's ending names its latest preserved capture on the item" excludes only for reporting. The tool MUST push the first candidate that carries work, and MUST push no commit when none does. It MUST push to `refs/heads/preserve/run-<run-id>`, or, when that ref already exists on origin at a commit that is not an ancestor of the commit being pushed, to `refs/heads/preserve/run-<run-id>-<the first 12 hexadecimal digits of the commit>`. Beside each copy it writes, the tool MUST record the run's repository, the ref and the commit it pushed or tried to push. After a push, the tool MUST read that ref with `git ls-remote`. When the ref reads exactly the commit the copy pushed, the tool MUST remove that run's local copy and every file it keeps beside the copy, except a copy this paragraph keeps below. When the push failed, or the ref reads another commit or is absent, the tool MUST keep the copy. On each later start, before it reads any sandbox, the tool MUST push every kept copy's recorded commit to its recorded repository and ref again, and MUST remove that copy only once `git ls-remote` reads that ref at that commit. A copy written before this rule records no repository, ref or commit. The tool MUST judge it by re-running the candidate selection above on the copy, and MUST remove it only once `git ls-remote` reads `refs/heads/preserve/run-<run-id>`, or the sibling ref named for that commit, at exactly the selected commit on the origin of one of the repositories the tool preserves runs for. That repository is the copy's repository. When no such origin carries such a ref, the tool MUST keep the copy and name its repository as unknown. The tool MUST keep a copy none of whose candidates carries work, and a copy whose objects `git fsck` reports missing. Kept copies have no time bound: the tool MUST NOT remove a copy on any condition other than the verified read above, so the only copy of a run's work is never deleted before origin holds it. Every run of the tool MUST report the count and total bytes of the copies it keeps, and each kept copy's run id, bytes and the reason it was kept: push failed, ref reads another commit, ref absent, no candidate carries work, objects missing, or repository unknown.
```

### 2. `SPECIFICATION/scenarios.md`: add one scenario, numbered at revise

The heading is numberless here. The revise pass MUST assign the next free scenario number and update the heading text in changes 3 and 4 to match.

~~~markdown
## Scenario: an operator preserve tool removes a run's local copy only once origin holds the commit it pushed

```gherkin
Feature: Operator preserve copies do not accumulate, and the only copy of a run's work is never lost
  As the operator of the control node that preserves factory runs
  I want each run's local preserve copy removed once origin verifiably holds it, and kept, retried and reported otherwise
  So that the work directory stops growing without bound while no unpushed work is deleted

  Scenario: A verified push removes the local copy
    Given the operator preserve tool holds a copy of run R whose first candidate carrying work is commit P
    When the tool pushes P to refs/heads/preserve/run-R on R's repository
    And git ls-remote reads that ref at exactly P
    Then the tool removes R's local copy and every file beside it from the work directory

  Scenario: A failed push keeps the copy and records what it tried to push
    Given the operator preserve tool holds a copy of run R whose first candidate carrying work is commit P
    When the tool's push of P to R's repository fails
    Then the tool keeps R's local copy
    And it records beside the copy R's repository, the ref and commit P
    And its report names the kept copy with its run id, its bytes and the reason push failed

  Scenario: A ref that reads another commit or is absent keeps the copy
    Given the operator preserve tool pushed commit P of run R to a ref on R's repository
    When git ls-remote reads that ref at a commit other than P, or does not list the ref
    Then the tool keeps R's local copy
    And its report names the kept copy with the reason ref reads another commit, or ref absent

  Scenario: A kept copy is retried on the next start and removed once origin holds it
    Given a kept copy of run R recording repository U, ref F and commit P
    When the operator preserve tool starts
    Then before it reads any sandbox it pushes P to F on U again
    And it removes the copy only once git ls-remote reads F at P

  Scenario: A copy from before the rule is judged by re-running candidate selection
    Given a copy of run R that records no repository, ref or commit
    And re-running the candidate selection on it selects commit C
    When the operator preserve tool starts
    Then it removes the copy only once git ls-remote reads refs/heads/preserve/run-R, or the sibling ref named for C, at exactly C on the origin of one of the repositories it preserves runs for
    And when no such origin carries such a ref, it keeps the copy and its report names the repository as unknown

  Scenario: A work-free or damaged copy is kept and reported
    Given a copy of run R none of whose candidates carries work, or whose objects git fsck reports missing
    When the operator preserve tool runs
    Then it pushes no commit for that copy and keeps it
    And its report states the count and total bytes of kept copies, and names this copy with its run id, its bytes and the reason no candidate carries work, or objects missing
```
~~~

### 3. `tests/heading-coverage.json`: add the new heading in the same revise

The revise that ratifies this MUST add one entry, using the heading as numbered at revise:

```json
{"heading": "## Scenario: an operator preserve tool removes a run's local copy only once origin holds the commit it pushed", "spec_root": "SPECIFICATION", "spec_file": "scenarios.md", "test": "TODO", "work_item": "bd-ib-yw7yot", "reason": "A test at the integration tier or above is owed: the operator preserve tool's own suite, delivered by bd-ib-yw7yot, driving preserve_runs.sh against a local bare origin."}
```

### 4. `tests/heading-coverage-debt.json`: regenerate it in the same revise

The register is generated, never authored by hand. The revise MUST regenerate it with `uv run python -m livespec_dev_tooling.heading_coverage_debt` and stage the result. The generated row is expected to read:

```json
{"spec_root": "SPECIFICATION", "spec_file": "scenarios.md", "heading": "## Scenario: an operator preserve tool removes a run's local copy only once origin holds the commit it pushed", "work_item": "bd-ib-yw7yot", "first_seen": "<revise date>"}
```

No existing heading changes, per AGENTS.md §"Revise co-edit discipline".

### 5. Follow-through outside the spec (not part of this revise)

On ratification, bd-ib-yw7yot's Definition of Done `References:` line SHOULD name the new scenario heading, as numbered at revise, beside `## Scenario 320 — Preservation refs are deleted when the Dispatcher closes or collects an item's runs`. Its spec-change tier is then re-classified.
