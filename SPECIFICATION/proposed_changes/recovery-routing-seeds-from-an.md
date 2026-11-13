---
topic: recovery-routing-seeds-from-an
author: claude-opus-5-5
created_at: 2026-11-13T16:23:50Z
---

## Proposal: A released item seeds from its newest needs-human tree across its earlier runs, whatever run its pull request record names

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The ratified text orders needs-human refs by committer time only among refs that carry ONE run. For the choice ACROSS an item's earlier runs, it says only "prefer the failed run's successfully preserved terminal tree" and orders runs by journal order. The shipped router takes the first identifier with a ref, so a pull request record's run, or an older journaled run, outranks a newer needs-human tree. This proposal adds one paragraph to contracts.md §"Factory-configurable ACP fallback priority", after "A needs-human tree is recognised by the run it carries". Each earlier run is first reduced to its own terminal tree by the existing within-run rule. Among those trees, the one with the newest tip commit by committer time is the seed, with a byte-order tie-break. The identifier collection order, including the pull request record's run, never ranks one run above another. The run-age bound, the published-head and capture comparisons, and ruled seeds are unchanged. Every ref the route did not take is listed in passed_over_needs_human, and a resume still journals the pull request record's run first. One scenario exercises it.

### Motivation

Filed as bd-ib-qshcwc on legacy-coordinator-agent's R301 ruling (session e61db277, 2026-11-07), under plan publish-draft-green-work-loss (epic bd-ib-acrr56). Its FRESH dispatch on 2026-11-13 was refused before listing at 16:19:45Z as spec-change tier, verdict PARTIAL, generalization target "## Factory-configurable ACP fallback priority", linked topic recovery-routing-seeds-from-an, spec v369. The judgement's rationale: the spec states passed_over_needs_human, the no-change pass-over, and the descendant-then-newest-committer-time choice among refs carrying one run, "It does not state newest-by-committer-time across needs-human refs of different earlier runs, or that the run named by the pull request record cannot outrank a newer ref. It orders runs by journal order and speaks of the failed run's terminal tree". Read against v369's contracts.md, the judgement is right: "A needs-human tree is recognised by the run it carries" ranks by committer time only among refs carrying the same run, and the seed-record paragraph prefers "the failed run's successfully preserved terminal tree". Defect, measured on v0.301.0: _needs_human_seed in _dispatcher_recovery_preserved.py takes the FIRST identifier with a ref. _earlier_run_ids in _dispatcher_resume_observation.py builds them as the pull request record's run id, then journaled run ids, then dispatch ids, the last two oldest first. Design choices, settled here: (a) Reduce within a run first, then rank across runs, so the within-run descendant rule is untouched. (b) Committer time, not journal order, because journals are per checkout and dispatchers are multi-host. (c) Sort at the point of selection and leave the collection order alone, because it serves the operator's third-resume refusal text and the resume journal. (d) Explicitly unchanged: the run-age bound and published-head comparison (so6fef, ex4omz) and ruled seeds (bd-ib-ltlg4i, a-ruled-seed-s-recovery #5067). Trailer-carried attribution stays with bd-ib-7gssim. Placement: recovery routing is this orchestrator's Dispatcher realization, so the paragraph belongs in this repository's contracts.md. Fleet scope: the shared Dispatcher, so every factory-target repository. In-flight survey: #5067 (a-ruled-seed-s-recovery), #5083 (recovery-routing-reads-a-rework), #5165 (a-resume-refuses-the-resumed) and the pending a-stale-preserved-seed-is touch the same section. None orders needs-human refs across runs, and all align.

### Proposed Changes

Two edits, both in this repository's spec target.

1. `SPECIFICATION/contracts.md` §"Factory-configurable ACP fallback priority": insert the following paragraph immediately after the paragraph that begins "**A needs-human tree is recognised by the run it carries, not only by its ref name.**".

**The newest needs-human tree across an item's earlier runs is the seed.** When recovery routing looks for a released item's needs-human seed and the item's needs-human refs carry two or more different earlier runs, it MUST first reduce each run to its own terminal tree by the preceding paragraph. Then, among those per-run terminal trees, it MUST take the one whose tip commit is newest by committer time. On an equal committer time it MUST take the one whose full ref name sorts first in byte order. For this comparison, a ref named `needs-human/<identifier>` whose tip carries no run trailer is attributed to the earlier run that `<identifier>` names, whether that is a run id or a dispatch id. A ref that carries no work is never a candidate, as the preceding paragraph states. The order in which the item's earlier-run identifiers are collected MUST NOT rank one run's ref above another's. That order is the run id the pull request's records name, then journaled run ids, then dispatch ids. In particular, the run that the item's pull request records name takes its ref only when that ref's tip commit is the newest by this rule, and it MUST NOT outrank a needs-human ref of the item whose tip commit is newer. Where this clause says the Dispatcher prefers the failed run's successfully preserved terminal tree, that tree is the one this paragraph selects. This paragraph orders needs-human refs only. It does not change the run-age bound, the comparison of the selected ref against the observed published head or a preserved capture, or the precedence of a current seed ruling or fresh ruling, and each of those applies to the ref it selects exactly as before. Every needs-human ref carrying, or named under, one of the item's earlier-run identifiers that the route did not take MUST be listed in the `recovery-route` record's `passed_over_needs_human` field with its commit, and the field MUST be an empty list when there is none. The collection order is unchanged for every other use, so the earlier-run identifiers a resume journals still lead with the run id the pull request's records name, and a third-resume refusal names that run id first. Committer time ranks the runs, not journal order, because a dispatch journal is kept per checkout while dispatchers run on several hosts, so no journal can rank a run it never saw. Committer time is host-independent, and it is already this clause's tie-break between refs of one run. Measured on build 1895a0ddbe37 (v0.301.0): bd-ib-akxkza run 01M6VR76ZQN2 was seeded from f58de533, the run PR #4555's record names, over the newer 45cbcb83. overseer-mldt32 was seeded three times from 7da576a5 while 649bd2bb survived. A scan of three fleet journals found 24 of 90 seeded routes took a ref older than the newest surviving dispatch-named ref. Scenario <number assigned at revise> in `scenarios.md` exercises this paragraph.

2. `SPECIFICATION/scenarios.md`: append the following scenario after the last numbered scenario. The revise assigns its number and writes that number into both the heading and the closing sentence of the paragraph above.

## Scenario <number assigned at revise> — A released item seeds from its newest needs-human tree across its earlier runs, whatever run its pull request record names

```gherkin
Feature: Recovery routing ranks an item's earlier runs' needs-human trees by recency, not by identifier order
  Scenario: The newer of two earlier runs' needs-human refs is the seed
    Given an item released for recovery whose needs-human refs carry two different earlier runs
    And the ref of the run journaled first has the newer tip commit by committer time
    When recovery routing routes the item
    Then the route is seeded from the ref with the newer tip commit
    And the recovery-route record lists the other ref with its commit under passed_over_needs_human

  Scenario: The run the pull request record names does not outrank a newer ref
    Given an item released for recovery whose pull request record names run R
    And R's needs-human ref has a tip commit older than another needs-human ref of the item
    When recovery routing routes the item
    Then the route is seeded from the newer ref
    And R's ref is listed with its commit under passed_over_needs_human

  Scenario: The pull request record's run is taken when its ref is the newest
    Given an item released for recovery whose pull request record names run R
    And R's needs-human ref has the item's newest tip commit
    When recovery routing routes the item
    Then the route is seeded from R's ref
    And passed_over_needs_human lists every other needs-human ref of the item, or is an empty list when there is none

  Scenario: A ref that carries no work never wins on recency
    Given an item released for recovery holding a needs-human ref with the newest tip commit whose tree equals its merge base's tree
    And another needs-human ref of the item that carries work
    When recovery routing routes the item
    Then the route is seeded from the ref that carries work
    And the empty ref is listed with its commit and the reason no-change under passed_over_needs_human

  Scenario: A resume still journals the pull request record's run first
    Given an item whose pull request record names run R and whose journal names older runs
    When a resume of the item journals its earlier-run identifiers
    Then R's run id is the first identifier journaled
```

No existing H2 heading is renamed or removed. The revise that accepts this proposal MUST add, in the same change, one `tests/heading-coverage.json` row for the new scenario heading with `"test": "TODO"`, `"work_item": "bd-ib-qshcwc"` and a `reason` that names the owed test's tier as "integration tier or above". It MUST then REGENERATE the debt register with `uv run python -m livespec_dev_tooling.heading_coverage_debt`, and never author its entry by hand.
