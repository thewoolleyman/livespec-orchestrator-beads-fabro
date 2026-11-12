---
topic: a-drift-pass-reuses-one
author: claude-opus-5-5
created_at: 2026-11-12T14:07:00Z
---

## Proposal: A drift run's judge prompts share one byte-identical spec-tree prefix that a Claude judge reads from its prompt cache

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The drift-job clause already requires one rendering of the ratified spec tree per run. It does not require that rendering to be the same bytes in every prompt, and it does not say how a Claude judge receives it, so every judge call pays full fresh input for about 57K tokens of spec tree. This proposal requires a pass-stable, statement-independent spec-tree prefix in every judge prompt of a drift run, delivered to a Claude judge as a system prompt FILE with prompt caching on. The Definition-of-Done judgement and the governing-heading judgement, whose prompts differ per statement, keep caching off.

### Motivation

Work item bd-ib-kojs3t (plan bd-ib-ax3rds). It has been HELD at spec-change tier since 2026-11-12 02:48Z: linked topic a-drift-pass-reuses-one, verdict unstated, generalization target Scenario 207. No deposit had been filed, so the plan's pointer has been waiting on an item that could not move. This is that deposit. It is precondition (1) of the coordinator ruling of 2026-11-01 on livespec-dev-tooling-dfixhe: the bd-ib-76ztny drift backfill and the live per-merge lane stay OFF until it lands. Measured with caching on but no stable prefix (drift gate 20261101T000057Z-2498587, 10 commits, sonnet-5-5): $0.231 per commit and about 57.3K input tokens per call, of which about 56.7K was a fresh one-hour cache write the next call never read (cache reads 649). bd-ib-2r7c3p (v0.286.0) then set DISABLE_PROMPT_CACHING=1 for every Claude candidate. That was right for the two per-statement judgements, but the drift pass reaches the same launcher through run_candidate_chain, so drift now pays about $0.119 per call uncached, against a bar of at most $0.06 per commit. A probe of 2026-11-07 (four real `claude -p` calls, the judge's isolation flags, caching on, an 8K shared text) found the delivery decisive. The shared text first on standard input gave a second call 2,254 reads and 6,424 writes ($0.0260). The same text through --append-system-prompt gave 8,085 reads and 602 writes ($0.0033). A ~57K-token prefix is about 230 KB, above Linux's 128 KB single-argument limit, hence a FILE. Today `_spec_tree_condensation.condensed_spec_tree` selects clause bodies per statement, so the prefix differs per commit; the prefix must be statement-independent, with per-statement selection after it. In-flight alignment: #5031 (inherited specification files in the judgement's text) `align`, since inherited files join the same statement-independent prefix; #5036, #5037 and #5042 `align`.

### Proposed Changes

**1. One cached spec-tree prefix per drift run (`contracts.md` §"The skill surface", the drift-job paragraph).** After the sentence "Batching MUST NOT change what is filed: the run MUST still file one proposed change per `partial` or `unstated` behaviour per merge, under the same finding identity.", add:

> Every judge prompt of one drift-job run MUST open with the same SPEC-TREE PREFIX, byte for byte. The prefix is a rendering of the ratified spec tree that does not depend on any merge or statement the run judges, and it MUST name every H2 heading of the governed spec tree verbatim. Each merge's own content, and any clause selection that depends on it, MUST follow the prefix. A Claude judge of a drift-job run MUST be launched with prompt caching on, and MUST receive the prefix as its system prompt, supplied from a file (for example `--append-system-prompt-file`), never on standard input and never as a single command-line argument. The Definition-of-Done judgement and the spec-stated governing-heading judgement, whose prompts differ per statement, MUST launch every Claude candidate with prompt caching off. Because both judgements and the drift run reach a shared judge entry, the choice of caching and of the system-prompt file MUST be made by the drift run as the caller, and MUST NOT be keyed off the shared entry.

**2. Scenario (`scenarios.md`).** Append:

## Scenario 356 — A drift run's judge prompts share one byte-identical spec-tree prefix that a Claude judge reads from its prompt cache

```gherkin
Feature: a drift pass pays for its spec tree once per cache lifetime
  Scenario: every prompt of a drift run opens with the same prefix
    Given a drift-job run over at least two default-branch merges with a Claude judge
    When the run builds its judge prompts
    Then every judge prompt opens with a spec-tree prefix naming every H2 heading of the governed spec tree verbatim
    And that prefix is byte-identical across every prompt of the run
  Scenario: the Claude judge receives the prefix as a cached system prompt file
    Given a drift-job run with a Claude judge
    When the run launches each judge call
    Then the call is launched with prompt caching on
    And the spec-tree prefix is supplied from a system prompt file, not on standard input
    And every call after the first reports cache-read input tokens at least as large as the shared prefix
  Scenario: the per-statement judgements keep caching off
    When the Definition-of-Done judgement or the governing-heading judgement launches a Claude candidate
    Then the candidate is launched with prompt caching off
```

**3. **Revise co-edit.** The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new scenario heading, carried through `resulting_files[]` with the path spelled `../tests/heading-coverage.json` or edited directly in that commit, with `test: "TODO"`, `work_item: "bd-ib-kojs3t"` and a non-empty `reason` naming the tier the owed test runs at, integration or above; and one matching `tests/heading-coverage-debt.json` entry carrying the key three, `work_item: "bd-ib-kojs3t"` and `first_seen` set to the revise date. If the revise renumbers Scenario 356, the row and entry MUST carry the renumbered heading text.
