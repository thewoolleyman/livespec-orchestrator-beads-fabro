---
topic: a-fresh-ruling-routes-a-released-item-fresh
author: claude-opus-5-5
created_at: 2026-11-07T23:10:45Z
---

## Proposal: An operator fresh ruling routes a recovery-released item's next dispatch fresh

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a fresh ruling beside the ratified seed ruling. An operator or delegated coordinator records it with dispatcher.py fresh-ruling as a livespec-fresh-ruling ledger comment, and while it is current recovery routing MUST route the released item fresh past every preserved tree it holds, still grading the pre-claim refusal first and keeping a non-fallback refusal's precedence. The route records the ruling and every passed-over needs-human ref, deletes nothing, and is consumed exactly once like a seed ruling. The newer of a seed ruling and a fresh ruling governs. This closes the gap that leaves a recovery-released item with stale or wrong preserved trees no route except seeding from one of them.

### Motivation

A recovery-released item cannot be dispatched fresh today, even when every preserved tree it holds is stale or wrong. The clause routes a released item `fresh` only when preserved work is confirmed absent, and the ruled-seed paragraph lets an operator choose a tree but not choose no tree; it explicitly forbids a seed ruling from falling through to `fresh`. The released Dispatcher (v0.302.0, 632fe9815) matches that text: legacy-dispatcher-agent read `route_recovery` on 2026-11-07 and found no operator-forced fresh route.

Measured instances on 2026-11-07:
- bd-ib-72hvx5 (the in-turn gate-time fix under plan sandbox-commit-gate-ceiling): both of its preserved trees are about 950 commits behind master, so every recovery dispatch would seed from a tree that stale. It is now blocked on the work item that carries this change.
- bd-ib-ltlg4i: the operator wanted current master plus its finished files. The route could only seed from its older ruled tree 417c6f847, so the work had to be carried by a path-limited rider instead.

Work item: bd-ib-xz35zu (plan publish-draft-green-work-loss, epic bd-ib-acrr56), filed on legacy-coordinator-agent's ruling (session 8e04c5e0, R301), which also holds the revise decision for this proposal as an operator-override extension mirroring the ratified ruled-seed design. The design deliberately mirrors the ruled seed's command, marker, currency, consumption, reconciliation and refusal-precedence rules, so that one ruling form covers both choices.

In-flight alignment: aligns with proposed_changes/a-plain-re-dispatch-of.md (it widens the release condition, while this proposal adds a route choice for an already-released item), with PR #4622's a-launcher-stops-a-drive-a-hold-precedes-admission, and with the v313 run-age preference. Tree-preference order among needs-human refs stays with bd-ib-qshcwc, and trailer attribution stays with bd-ib-7gssim.

### Proposed Changes

In `contracts.md` §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work", make three edits.

1. In the route list, the `fresh` entry MUST read:

```diff
-- `fresh`, when every applicable resume refusal is fallback-permitting and
-  preserved work is confirmed absent;
+- `fresh`, when every applicable resume refusal is fallback-permitting and
+  preserved work is confirmed absent, or when a current fresh ruling governs
+  the item and no non-fallback refusal applies;
```

2. In the paragraph "**A ruled seed names the tree a released item's next dispatch starts from.**", the sentence "A ruling is CURRENT from the instant its comment is written until the item carries a `livespec-seed-ruling-consumed` comment naming it, or until a later ruling for the same item replaces it; the latest ruling governs." MUST become "A ruling is CURRENT from the instant its comment is written until the item carries a `livespec-seed-ruling-consumed` comment naming it, or until a later seed ruling or fresh ruling for the same item replaces it; the latest ruling of either kind governs." Every other sentence of that paragraph is unchanged, including "Routing MUST NOT then fall through to another preserved tree, to the observed published head, or to `fresh`", which keeps governing a seed ruling.

3. Directly after that paragraph, a new paragraph MUST be added:

**A fresh ruling routes a released item's next dispatch fresh.** An operator or a delegated coordinator MAY rule that an item's next dispatch start fresh from the default branch, past every preserved tree the item holds, by running `dispatcher.py fresh-ruling --repo <path> --item <id> --reason <text>`. The command MUST write one ledger comment on the item that opens with the marker line `livespec-fresh-ruling` and names the invoker, the reason and the UTC instant, and MUST journal one `fresh-ruling` record carrying the same fields. The comment MUST pass the shared template-opener detector before it is written; when it does not, the command MUST refuse (exit `3`) and MUST write nothing. A fresh ruling is CURRENT on the same terms as a seed ruling: from the instant its comment is written until the item carries a `livespec-fresh-ruling-consumed` comment naming it, or until a later seed ruling or fresh ruling for the same item replaces it, and recovery routing MUST read it from the item's ledger comments and never from a host's journal alone. While an item carries a current fresh ruling, recovery routing MUST treat the item as released for recovery, and the pre-claim refusal of §"Across-dispatch required-result progress" MUST still be graded first. A non-fallback refusal keeps its precedence over a fresh ruling: the route MUST then be `held`, naming that refusal, and the ruling MUST stay current. Otherwise the route MUST be `fresh` ahead of a `resume` and ahead of the preference order this clause states, without seeding from any preserved tree. Recovery routing MUST still list the item's needs-human refs, and the `recovery-route` record MUST name the ruling's instant and MUST carry the `passed_over_needs_human` field this clause requires, listing every needs-human ref that carries one of the item's earlier runs, because the route took none of them. A needs-human listing that cannot be taken is the existing unobservable-measurement hold. A fresh ruling MUST NOT delete or move any needs-human or preservation ref, and the stale publish-branch reclaim of §"Stale publish-branch reclaim before a re-dispatch" MUST run for the item as for every other `fresh` item, preserving the branch's head before it deletes the branch. Once the run of a dispatch routed fresh by a ruling exists, that dispatch MUST add one ledger comment on the item that opens with the marker line `livespec-fresh-ruling-consumed` and names the ruling's instant, the dispatch id and the run id, and MUST journal one `fresh-ruling-consumed` record carrying the same fields. A reconciliation pass that finds a run launched from a fresh ruling whose item carries no such comment MUST add it. A consumed fresh ruling MUST NOT govern any later dispatch.

Fleet scope, stated for the reviser: `route_recovery` is the shared Dispatcher's, so this amendment governs every repository dispatched through this plugin's Dispatcher. That includes livespec-orchestrator-git-jsonl, whose `.livespec.jsonc` names `livespec-orchestrator-beads-fabro` as its implementation plugin and which carries no dispatcher or recovery routing of its own (read from its origin default branch, 2026-11-08).

In `scenarios.md`, a new scenario MUST be added, numbered as the next free scenario number at revise time, with the heading `## Scenario <N> — A fresh ruling routes a released item fresh past its preserved trees` and this body:

Governing clause: `contracts.md` §"Factory-configurable ACP fallback priority" → "Recovery from the failed run's preserved work".

```gherkin
Feature: Operator fresh ruling for a recovery-released item
  As the operator of a repository dispatched through the factory
  I want to rule that a released item's next dispatch starts fresh
  So that a stale or wrong preserved tree never seeds a dispatch I have judged it must not seed

  Scenario: a fresh ruling routes a released item fresh past a verified needs-human ref
    Given an item released for recovery that holds verified needs-human ref N
    And the item carries a current fresh ruling
    When recovery routing grades the item
    Then the route is fresh
    And the recovery-route record names the ruling's instant
    And its passed_over_needs_human field lists N with its commit

  Scenario: the newer of a seed ruling and a fresh ruling governs
    Given an item released for recovery that carries a seed ruling naming ref R at commit C
    And a later fresh ruling for the same item
    When recovery routing grades the item
    Then the route is fresh
    And the seed ruling is not current

  Scenario: a non-fallback refusal keeps its precedence over a fresh ruling
    Given an item released for recovery that carries a current fresh ruling
    And a non-fallback refusal applies to the item
    When recovery routing grades the item
    Then the route is held naming that refusal
    And the fresh ruling stays current

  Scenario: a consumed fresh ruling does not govern a later dispatch
    Given an item whose dispatch routed fresh by a ruling has a run
    When that dispatch records the run
    Then the item carries a livespec-fresh-ruling-consumed comment naming the ruling's instant, the dispatch id and the run id
    And the next recovery routing of the item does not route it fresh by that ruling
```

In the same revise, `tests/heading-coverage.json` MUST gain an entry for that heading (spec_root `SPECIFICATION`, spec_file `scenarios.md`, test `TODO`) whose reason names the owning work item bd-ib-xz35zu, per the revise co-edit discipline.
