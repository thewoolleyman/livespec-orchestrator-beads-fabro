# Measurement: spec-stated judge over bug / chore / non_functional items (plan spec-implementation-lockstep, bd-ib-x366dh)

Read-only. No ledger write, no commit, no PR.

## Sample

- **Rule:** the 50 most recently created (by `captured_at`) non-epic items with the `bd-ib-` prefix in this tenant whose NEWEST `livespec-spec-change-tier` record (parsed with `recorded_spec_change_tier` over `item_comment_bodies`) has classification `bug`, `chore` or `non_functional`. Any status. Plus bd-ib-yqjaut, the known instance.
- **Size: 50.** 79 non-epic items, newest first, were scanned to find 50 that qualify. Every sampled record reads `tier: none`, verdict `(not taken)`. bd-ib-yqjaut (classification `non_functional`) qualified under the rule itself, at rank 3, so adding it made no 51st item.
- Classifications: 45 bug, 4 chore, 1 non_functional. Items were created between 2026-11-05T17:51Z and 2026-11-08T00:35Z.

## Method

1. Labels were written to `labels.json` before any judge call. I labelled each item from its title, description and Definition of Done, against `SPECIFICATION/` in the primary checkout. That was history v315 when labelling began.
2. The judge call matches `classify_spec_change_tier`'s feature arm: `judge_within_ceiling(spec_tree=snapshot.files, statement=asked_for_behaviour(item), run_model=drift_judge(project_root=repo, runner=ShellCommandRunner(), caller="measure_x366dh"), rubric=CONFIGURATION_RUBRIC)`. The runner is a subclass of `ShellCommandRunner` that only counts calls and reads `total_cost_usd` from each Claude `result` event. Neither `judge_within_ceiling` nor `drift_judge` appends a ledger record. They write a local spend journal under `~/.claude/spend-journal/`. The candidate on every call was claude-acp / claude-sonnet-5-5.
3. **Spec moved during the run.** v316 landed at 2026-11-08T00:45Z, between labelling and judging, so the judge read **v316**. Diffing v315 against v316 shows that v316 adds only the s754le paragraph "A tree a factory run resumes or seeds can pass under the harness judging it" and Scenario 326. The bd-ib-s754le label (does-not-break) is unchanged, and no other label is affected.

## Cost

- **51 model calls, $6.04**, all of it taken from the cost each call reported (no estimates).
- 50 items needed one call each. bd-ib-grzfpt needed two: its first reply was unparseable ("response is not JSON", $0.12), and one retry returned `partial`. The first attempt is kept in `verdicts.json` and `grzfpt_first_attempt.json`.

## Counts (rule B: hold when the verdict is `partial` or `unstated`)

| group | n | partial | unstated | stated |
|---|---|---|---|---|
| true holds (breaks, held) | 1 | 1 | 0 | — |
| false holds (does-not-break, held) | 39 | 27 | 12 | — |
| misses (breaks, stated) | 0 | — | — | 0 |
| correct passes (does-not-break, stated) | 7 | — | — | 7 |
| unsure (reported separately) | 3 | 2 | 1 | 0 |

Labels: 1 breaks, 46 does-not-break, 3 unsure. Verdicts over all 50 items: 30 partial, 13 unstated, 7 stated. A stricter rule that holds only on `unstated` would hold 0 of the 1 breaks item and 12 of the 46 does-not-break items.

## Every item

| id | classification | label | verdict | generalization target | group | label reason |
|---|---|---|---|---|---|---|
| bd-ib-csrvhs | bug | does-not-break | partial | ## Forbidden patterns | false hold | Test-harness wait fix; restores a load-independent verdict, no product behaviour a clause governs changes. |
| bd-ib-ax6bxj | bug | does-not-break | partial | ## Dispatcher admission, WIP cap, and post-merge acceptance | false hold | Reusing an unchanged non-feature tier record is what the reuse clause already requires ('Classifying ... again on every dispatch path is satisfied by that reuse'). |
| bd-ib-yqjaut | non_functional | breaks | partial | ## Self-contained plugin dispatch | true hold | Removing the merge commit's hook suite run (or reordering grade-before-merge) changes the refresh-then-aggregate order and the 'no check, target or gate is removed or weakened' sentence; owner says the paragraph must be amended. |
| bd-ib-ajfmkw | bug | does-not-break | partial | ## Dispatcher policy settings | false hold | Keeps naming the move valve as required; only adds a precondition. |
| bd-ib-qcshv6 | bug | does-not-break | partial | ## Dispatcher policy settings | false hold | Makes the cause quote the stage the run ended on; restores accuracy, no clause requires quoting a recovered stage. |
| bd-ib-xs2gmn | bug | does-not-break | unstated | ## Fabro runtime constraints | false hold | Fabro fork client/server refusal of resuming a finished run; no clause of this repo states the contrary. |
| bd-ib-bomy33 | bug | does-not-break | partial | ## Grooming and slice-size calibration | false hold | Conformance: the clause says a held item 'MUST be held out of ready' and the hold 'MUST fail closed'. |
| bd-ib-dpsiwz | chore | unsure | unstated | ## Fabro runtime constraints | unsure | Moves every prepare step into command nodes; clauses are written in terms of 'prepare steps the Dispatcher renders' and a scenario admits run.prepare token positions, so whether a functional move contradicts them depends on reading 'prepare step' as mechanism or as role (item itself says a propose-change is needed for the scenario). |
| bd-ib-qshcwc | bug | unsure | partial | ## Factory-configurable ACP fallback priority | unsure | Clause says 'prefer the one named under one of the item's run identifiers, otherwise newest by committer time' and orders runs by journal order; item ranks across run-id and dispatch-id names by committer time 'whichever identifier names it'. Breaks only if 'run identifiers' means run ids alone. |
| bd-ib-s754le | bug | does-not-break | stated | — | correct pass | Guard still refuses agent-turn publication (bullet 3); only a tree's own test suite stops tripping it. |
| bd-ib-oxx6eo | chore | does-not-break | partial | ## Expedited incident lifecycle | false hold | Adds an integration test only. |
| bd-ib-7i2bta | bug | does-not-break | partial | ## Expedited incident lifecycle | false hold | Adds the missing writer of master-observation the phase table already pairs with a merged carrier. |
| bd-ib-yvmtrm | bug | does-not-break | unstated | ## Self-contained plugin dispatch | false hold | Adds a sanity rule on Proof of Done timestamps; no clause permits future-dated records. |
| bd-ib-ot4av7 | bug | does-not-break | partial | ## Scenario 240 — A recorded Definition-of-Done verdict binds every host taking on identical digests, and opposite verdicts are journaled | false hold | Reusing a current recorded governing-heading verdict is what the reuse rule prescribes. |
| bd-ib-z5yzyq | bug | does-not-break | partial | ## Scenario 199 — A fix turn runs the check suite once per tree and counts a commit hook's full green run | false hold | Prompt change; keeps every case Scenario 199 requires (bullet 5) and adds a case the scenario does not state. |
| bd-ib-grzfpt | bug | does-not-break | partial | ## Self-contained plugin dispatch | false hold | Spec requires the fix turn to integrate the default branch; merge vs rebase is the prompt's choice, no clause mandates rebase. |
| bd-ib-wd2zcq | bug | does-not-break | partial | ## Dispatcher admission, WIP cap, and post-merge acceptance | false hold | Makes the valve do what the contract already says it does. |
| bd-ib-qnucbe | bug | does-not-break | unstated | ## Scenario 21 — Codex plugin discovery and full-access posture | false hold | Recipe registration arguments; no spec clause names sparse registration. |
| bd-ib-rjnif7 | chore | does-not-break | partial | ## Bounded session waits and observable inventory | false hold | Test made load-independent; behaviour under test unchanged. |
| bd-ib-st2sby | bug | does-not-break | unstated | ## Bounded session waits and observable inventory | false hold | Spend journal also records the final result event; no clause states the journal's line set. |
| bd-ib-e3vbbo | bug | does-not-break | partial | ## Self-contained plugin dispatch | false hold | Makes filing display agree with the pre-dispatch screen; consistency fix. |
| bd-ib-2eyiwy | bug | does-not-break | stated | — | correct pass | Scenario 325 already ratifies 'a workflow-declared node timeout stands unless configuration names the node'. |
| bd-ib-tcfwol | bug | does-not-break | unstated | ## Forbidden patterns | false hold | Shell pipefail reader fixes; item notes no spec clause on pipeline verdicts. |
| bd-ib-xwtohc | bug | does-not-break | unstated | ## Fabro factory host provisioning constraints | false hold | Ansible inventory pin parity in livespec-dev-tooling; no clause of this repo governs it. |
| bd-ib-diiztk | bug | does-not-break | unstated | ## Self-contained plugin dispatch | false hold | Same as grzfpt: merge instead of rebase is within 'integrates the default branch into the run's work'. |
| bd-ib-oknwxm | bug | does-not-break | partial | ## Scenario 185 — A released item's recovery route is decided before admission and executed per item, and a deferred item keeps its branch | false hold | Conformance: 'fresh only when preserved work is confirmed absent', 'held when a measurement cannot be taken'. |
| bd-ib-mpfv5q | bug | does-not-break | unstated | ## Provisional fleet launch scripts | false hold | Launcher matches its own dispatch id; no clause states first-row matching. |
| bd-ib-so6fef | bug | does-not-break | stated | — | correct pass | Conformance to the ratified run-age bound. |
| bd-ib-bx5rf2 | bug | does-not-break | partial | ## Dispatcher admission, WIP cap, and post-merge acceptance | false hold | Changes the fleet-default sandbox check-suite composition; no clause fixes the default as bare 'just check'. |
| bd-ib-azhnw5 | bug | does-not-break | partial | ## Factory-configurable ACP fallback priority | false hold | Adds lineage refusals for a seeded route; consistent with 'a seeded dispatch restores the captured code'. |
| bd-ib-xukb7w | bug | unsure | partial | ## Self-contained plugin dispatch | unsure | publish_draft drops an empty checkpoint commit before pushing; contradicts 'MUST push exactly the head that janitor passed' only if that checkpoint lies on the janitor-passed head rather than after it. |
| bd-ib-oixyzp | bug | does-not-break | partial | ## Self-contained plugin dispatch | false hold | Gives the third incomplete implement visit its needs_human ending; restores the scenario. |
| bd-ib-lpdlsq | bug | does-not-break | stated | — | correct pass | Exhausted janitor refresh repair reaches needs_human; restores the scenario's intent. |
| bd-ib-zedjgq | bug | does-not-break | partial | ## Dispatcher admission, WIP cap, and post-merge acceptance | false hold | Source-branch launch no longer blocks on the aggregate while every push still runs the full gate; no clause requires the synchronous wait. |
| bd-ib-2flry2 | bug | does-not-break | partial | ## Self-contained plugin dispatch | false hold | Display label made to match the ratified hold/advisory split. |
| bd-ib-ekrfg5 | bug | does-not-break | partial | ## Provisional fleet launch scripts | false hold | Launcher honours SIGTERM; restores intended stop behaviour. |
| bd-ib-kseatc | bug | does-not-break | partial | ## Dispatcher policy settings | false hold | Current ratified step 5 already follows the chain hop by hop and names S2 on stand-down (spec was amended). |
| bd-ib-w5yzzt | bug | does-not-break | stated | — | correct pass | Green amend on workflow.fabro runs tests; stricter gate, no clause requires the doc-only path. |
| bd-ib-a4dtst | bug | does-not-break | partial | ## Self-contained plugin dispatch | false hold | Prompt evidence requirements for 'inherited' failures; supports the scenario. |
| bd-ib-eb5zl5 | bug | does-not-break | partial | ## Provisional fleet launch scripts | false hold | Harness polls completed state; test-only. |
| bd-ib-tlgq3y | bug | does-not-break | partial | ## Dispatcher policy settings | false hold | Conformance to 'every non-closed work-item MUST name exactly one token' and the outside-protocol write rule. |
| bd-ib-gowxxg | bug | does-not-break | partial | ## Scenario 103 — A needs-human outcome terminates the run and routes the decision to the ledger | false hold | Retry and read-back of the needs-human push; restores preservation reporting. |
| bd-ib-m7o3wf | bug | does-not-break | partial | ## Provisional fleet launch scripts | false hold | Release the mutex before logging the yield; ordering fix. |
| bd-ib-keg67m | bug | does-not-break | stated | — | correct pass | Better first-error-line selection; no clause requires the context line. |
| bd-ib-utwjkf | chore | does-not-break | stated | — | correct pass | Test of the ratified 'Token records MUST be excluded from list-work-items ...'. |
| bd-ib-veyxvz | bug | does-not-break | partial | ## Grooming and slice-size calibration | false hold | Uses the existing non-converged exit for an unchanged-head loop. |
| bd-ib-mlxa6s | bug | does-not-break | unstated | ## Inherited from livespec | false hold | Hermetic test fixture only. |
| bd-ib-digmk2 | bug | does-not-break | unstated | ## Fabro runtime constraints | false hold | Sandbox driver umask fix and re-pin, outside this repo's clauses. |
| bd-ib-2fpn5m | bug | does-not-break | unstated | ## Scenario 1 — Gap-tied fix cycle | false hold | Umask-independent test assertion. |
| bd-ib-nsw25x | bug | does-not-break | unstated | ## Dispatch-time baseline conformance gate | false hold | Re-installs hooks after a refresh; its publish_draft-refresh premise is now moot under Scenario 305 (publish_draft MUST NOT refresh), but the requested behaviour contradicts no MUST. |

## Observations

1. **The judge answers "does the spec state this?", not "would this break the spec?", and most bug fixes ask for behaviour more specific than any clause.** 39 of the 46 does-not-break items were held. In most of them the rationale says the spec states the general rule and the fix only adds unstated detail. bd-ib-ajfmkw (partial): "requires the `attribution-pending` held entry to name the operator `move` valve as the remedy ... It does not require a p[recondition]". bd-ib-m7o3wf (partial): the text "requires a launcher ... to release the mutex and in-flight marker ... It never orders" the log line against the release. Test-only and infrastructure items are held as `unstated` because no clause speaks to them at all. bd-ib-mlxa6s: "does not state that a test fixture's PATH must be hermetic". bd-ib-digmk2: "never says that commands run through the sandbox driver's exec inherit the sandbox's own umask".
2. **Conformance fixes are held even when the rationale itself quotes the clause they restore.** bd-ib-kseatc (partial): "Step 5 of the Claim tokens bullet and Scenario 263 already state the first two behaviours", yet the item is held on its third bullet (a needs-attention surface). bd-ib-bomy33 (partial) quotes "a spec-change-tier item MUST be held out of `ready`" and then holds on the move-to-backlog mechanics. The 7 correct passes are the items whose every bullet a single paragraph already spells out: bd-ib-utwjkf ("Token records MUST be excluded from ..."), bd-ib-2eyiwy (Scenario 325), bd-ib-s754le (the v316 paragraph written for it), and bd-ib-so6fef (the v313 run-age bound).
3. **The one breaks item was held, but for "unstated detail" rather than for a contradiction. Nothing in the sample was a miss.** bd-ib-yqjaut (partial, target `## Self-contained plugin dispatch`): "The ratified text states that the janitor refreshes before the aggregate, that the aggregate runs once on the pushed tree ... It says nothing about the [merge commit's hooks]". Its hold rests on the same ground as the false holds, and the verdict does not name the conflict with "no check, target or gate is removed or weakened". The three unsure items were all held too. bd-ib-xukb7w's rationale points at the clause that makes it unsure ("publish_draft push[es] the janitor-passed head without refreshing ... never says that when publish_draft drops empty checkpoint commits"), but it gives the same `partial` it gives the false holds. With one breaks item, the sample cannot show a miss rate.

## Files

- `sample.json`: the sample rule, the scan and each item's newest tier record
- `labels.json`: the blind labels
- `verdicts.json`: each verdict's kind, stated_by, generalization target, named clauses, selected clauses, rationale, and per-call model, cost and usage
- `items/`: the `asked_for_behaviour` statement sent to the judge for each item
