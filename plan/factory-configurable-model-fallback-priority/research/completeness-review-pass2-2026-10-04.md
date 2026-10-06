VERDICT: COMPLETE-UPON-ACCEPT

# Completeness review, pass 2 — plan `factory-configurable-model-fallback-priority` (epic `bd-ib-jxvgq5`)

Same independent reviewer as pass 1, read-only. Reviewed 2026-10-04 against `origin/master` at
`ba13f748` (release 0.164.0), the ledger re-dumped with `bd list --status all --limit 0 --json`
(1,149 items), and the forge.

**Attestation 1 — complete requirement coverage (every requirement delivered, or carried by a live
item whose text names it): YES**, with the one condition that `bd-ib-tmgt7v` leaves `acceptance`
through the accept valve.

**Attestation 2 — pressing `accept` on `bd-ib-tmgt7v` is warranted by what is on master: YES.** All
eight Definition of Done assertions are satisfied by merged content with a named test each (section 2).

No blocking findings remain. Two housekeeping actions and four notes for the carriers are listed in
sections 4 and 5; none is a requirement of this plan that lacks a carrier.

## 1. Disposition of the seven pass-1 findings

| Finding | Claimed disposition | What I verified | Result |
|---|---|---|---|
| Report and evidence (claim 1) | on master; evidence recorded, attests false | `plan/.../research/completeness-review-pass1-2026-10-04.md` on `origin/master`, first line `VERDICT: NOT-COMPLETE`; PR 2560 MERGED 2026-10-04T10:14:49Z; epic comment 2026-10-04T09:59:28Z carries `evidence-id: completeness-review-2026-10-04-pass1`, `attests-complete-requirement-coverage: false` | True |
| B1 chain emission | `bd-ib-vuwrv5` | Status `blocked` (live). No `parent` field and no parent-child edge; its only dependency row is `bd-ib-r5cnjd`, `dependency_type: blocks`, target `pending-approval`. Re-enumerating the epic's children still returns exactly the original ten. Text carries: render each node's resolved chain into the engine's run input with effective availability signatures, `config_options`, the preflight-skipped set and first candidate equal to the primary; the workflow graph passes it to every ACP node; a test asserts the rendered `fabro run` argv | Carried |
| B1 reached-node termination | `bd-ib-vuwrv5` | Criterion 3: "`reached_node_termination` is called on the dispatch path for a reached node whose chain is empty." | Carried |
| B2 live journey | `bd-ib-vuwrv5` | Criterion 4: one controlled live dispatch on hp, refused primary, fallback finishing the same node visit, run id and journal excerpt recorded | Carried (narrower than the research; see note C1) |
| B3 release floor | `bd-ib-vuwrv5` | Criterion 5: floor set to the first release that emits a chain, and the journey test reads the same value | Carried |
| "Dormant, not activated" deferral | scope event | Epic comment 2026-10-04T10:03:30Z, `plan-scope-event`: ordered fallback "is NOT active in production and will not be activated on the 0.254 fork… Reconsidered at bd-ib-r5cnjd, through bd-ib-vuwrv5." `bd-ib-r5cnjd` comment 2026-10-04T10:02:39Z carries the cross-reference and transfer request; its description and criteria are unchanged from what I read in pass 1 | Recorded, with a named place of reconsideration |
| B5 agent catalog | `bd-ib-5tk7bx` (`ready`, standalone, no dependencies) | Carries: the three entries take the registry's launch distribution and pinned version; the catalog records the registry snapshot digest and date; each non-built-in entry names a verification run or is removed. Leaves out the "rest of the registry's population" sentence — explicitly, and the scope event records that as a deferral routed through `propose-change` | Carried; the omitted sentence is an explicit deferral with a stated route |
| B6 classifier literals | `bd-ib-iyihsd` (`ready`, bug, standalone) | Carries both literals and a regression test on `signature_discriminates`. The fork mirror is NOT in this item; it is named in `bd-ib-vuwrv5`'s Context paragraph ("The engine-side mirror of the generic status literal set… belongs to the engine work here") and in the scope event | Carried (the mirror only in prose; see note C2) |
| B7 pricing precedence | `bd-ib-6lzk3o` (`ready`, standalone) | Carries FILING a proposal that states one precedence and names the sentences it replaces. It is not itself a filed proposal: `SPECIFICATION/proposed_changes/` on master still holds only the two unrelated proposals. Pass 1 accepted "a named live item that will file one", so this discharges it | Carried |
| B4 pricing slice | `bd-ib-tmgt7v` merged, at `acceptance` | Section 2 | Delivered by content; awaiting the valve |

## 2. `bd-ib-tmgt7v`: the verification an honest accept needs

Landing. PR 2562 MERGED 2026-10-04T11:24:17Z, 7 commits, 22 files. All seven subjects are on
`origin/master` (`10e5b1d0` … `274d007e`). `ci-green` is `success` on `274d007e` and on `ba13f748`.
I ran the PR's eight test files plus the Scenario 127 journey module on the primary checkout at
`8a945aa4` (which contains the PR): **134 passed**. Paths below are under
`.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/` and
`tests/livespec_orchestrator_beads_fabro/commands/`.

| # | Definition of Done assertion | Satisfied? | Code | Test |
|---|---|---|---|---|
| 1 | Usage and elapsed time attributed per attempt from `agent.acp.started` `candidate_index` and `agent.acp.failover` `attempted_durations_ms` | Yes | `_acp_attempt_windows.py` (`attempt_windows`), `_dispatcher_cost_attempts.py` | `test_acp_attempt_windows.py::test_a_failed_attempt_is_bounded_by_its_reported_duration`; `test_dispatcher_cost_attempts.py::test_each_attempt_is_reported_with_its_own_candidate_index_and_elapsed_time` |
| 2 | A successful fallback run sums every attempt; a single-candidate run is priced exactly as before | Yes | `_dispatcher_cost_attempts.chain_cost`; `_dispatcher_cost_chain.run_chain_cost` returns `None` when the events place no window, handing back to the sink | `test_dispatcher_cost_attempts.py::test_a_successful_fallback_run_sums_both_attempts`, `::test_a_single_candidate_chain_totals_exactly_what_the_shipped_sink_reports`; `test_dispatcher_cost_chain.py::test_the_legacy_derived_cost_map_is_unchanged_without_chains` |
| 3 | Catalog entry first, per-candidate table second; a manual candidate with no catalog match prices only by its table | Yes | `_acp_attempt_price.attempt_price` | `test_acp_attempt_price.py::test_the_catalog_entry_the_identity_names_wins_over_the_candidate_table`, `::test_the_candidate_table_applies_when_no_catalog_entry_names_the_identity` |
| 4 | Identity normalized only by one trailing `-YYYYMMDD`; no broader prefix | Yes | `_acp_model_identity.exact_model_identity`; `_dispatcher_cost_pricing.normalize_model_id` | `test_acp_model_identity.py::test_only_one_date_suffix_is_stripped`, `::test_a_broader_prefix_match_selects_no_price` |
| 5 | No matching price makes the whole run cost unobservable, not a subtotal, default estimate or zero | Yes | `_dispatcher_cost_attempts.py`, `_dispatcher_cost_report.py` | `test_dispatcher_cost_report_chain.py::test_the_darkened_total_is_not_the_priceable_attempt_s_subtotal`, `::test_the_darkened_total_is_not_a_default_priced_estimate`, `::test_the_darkened_total_is_not_zero` |
| 6 | The model catalog contains `claude-opus-5` with its four prices | Yes | `_acp_model_prices._BASE_RATES`; I loaded `builtin_model_catalog()` and read `anthropic/claude-opus-5` as priced | `test_acp_model_prices.py::test_the_catalog_prices_claude_opus_five_with_all_four_components` |
| 7 | Unobservable cost still routes through the existing `--item`-keyed gate; a terminally unsuccessful run keeps the no-observation posture | Yes | `_dispatcher_cost_gate.py:145,175-190` calls `chain_costs`; `_dispatcher_cost_chain.chain_costs` skips non-green outcomes | `test_dispatcher_cost_chain.py::test_a_darkened_chain_refuses_an_unattended_drain`, `::test_a_darkened_chain_only_warns_a_hand_picked_item_dispatch`, `::test_a_terminally_unsuccessful_run_is_never_read_for_cost` |
| 8 | Report names every priced identity in `model_basis`; `model_resolved` false when any attempt was unpriceable | Yes | `_dispatcher_cost_report.py` | `test_dispatcher_cost_report_chain.py::test_the_report_item_names_every_priced_identity_in_model_basis`, `::test_the_report_item_reports_model_resolved_false_when_an_attempt_was_unpriceable` |

### My six pass-1 closure proofs

1. **Merged, on master, janitor green, closed through its gate.** Merged and on master by content;
   CI green. "Post-merge janitor green" is the ledger's and the handoff's statement, which I did not
   re-run. NOT closed: status `acceptance`, assignee `fabro`. This is the one open step.
2. **`claude-opus-5` four prices.** Met.
3. **Every model the shipped defaults run still prices.** Met, and the missing post-merge cost record
   is **not blocking**. Reasoning from content:
   - The no-default rule lives only on the per-attempt chain path. That path activates only when the
     run's events place at least one window, which requires an `agent.acp.started` carrying
     `candidate_index` (`_acp_fallback_events._parse_start` returns `None` without it). The pinned
     engine sets `candidate_index` to `None` for a node with no chain (fork `acp.rs` line 850-857).
     Because nothing emits a chain (B1), every production run today yields no window and is priced
     by the legacy sink path.
   - The legacy path KEEPS its default: `derive_usd_micros` still falls back to
     `DEFAULT_DISPATCH_COST_MODEL` (`claude-opus-4-8`). So no production run can go dark from this change.
   - Models actually run: `workflow.toml` defaults name `claude-opus-5` (implement, fix, review_fix,
     proof_capture), `claude-haiku-4-5` (pr), `claude-opus-4-8[1m]` (review, dod_gate, proof_verify),
     and an unpinned Claude adapter (disposition). This repository's `.livespec.jsonc` sets no
     `dispatcher.acp_nodes`, `model_catalog` or `agent_catalog` (keys absent). `_BASE_RATES` prices
     opus-5, opus-4-8, sonnet-4-6, haiku-4-5, fable-5, gpt-5.5, gpt-5.4-mini.
   - One measured behaviour change on the legacy path: an identity with a non-date suffix no longer
     prefix-matches. `normalize_model_id("claude-opus-4-8[1m]")` now returns `None` and is priced at
     the default, which is the same Opus rate, so the number is unchanged; a `claude-sonnet-4-6[1m]`
     or Haiku identity with such a suffix would now be charged at the Opus default instead of its own
     rate. Whether Claude Code's spans ever carry the `[1m]` suffix I could not establish from the
     tree. This is an over-count in the conservative direction and belongs with note C3.
   A real cost record from the first post-merge dispatch is worth reading once it exists, but it is
   confirmation of the legacy path, not evidence the accept depends on.
4. **`AcpNodeStart` union.** Met: `_acp_fallback_event_types.py` lines 143-144 carry
   `chain_deadline_epoch_ms` and `confirmed_model` (and `confirmed_effort`) together.
5. **Precedence stated and B7 carried.** Met: `_acp_attempt_price.py` docstring records the tension and
   the order implemented; `bd-ib-6lzk3o` carries the proposal.
6. **Branch cleanup.** NOT done at review time: `git ls-remote origin` still lists
   `refs/heads/preserve/bd-ib-tmgt7v-01M3WTW7XW77` (`041f2a31`) and
   `refs/heads/needs-human/01M3T09DJ0ZF9T9XZTFF6W4STT` (`377b4984`). Housekeeping, not a requirement.

## 3. PR 2558's heading binding (question 6)

Still non-blocking. The bound test is real and exercises the heading's configuration half. I would
not re-bind it now: no test on master exercises chain emission, so there is nothing better to bind to
until `bd-ib-vuwrv5` lands. That item's criterion 2 creates the argv-asserting test; re-binding the
contract heading or Scenario 127 to it is a natural rider for that item and is not in its text today
(note C4).

## 4. Housekeeping still owed before the archive PR

- H1. Press `accept:bd-ib-tmgt7v`, then confirm `undisposed_plan_child_ids` is empty.
- H2. Confirm the two origin branches above are deleted. Two older needs-human branches from this
  plan's runs also remain on origin and whose work merged: `needs-human/01M25XBZVFRXHYJSQ725YYX3ZG`
  (S1, PR 2447) and `needs-human/01M2A3AEMBRC09VPMD2QAMG77S` (S3, PR 2479).

## 5. Notes for the carriers (non-blocking)

- C1. `bd-ib-vuwrv5`'s live-journey criterion asks for a run id and journal excerpt showing the refused
  primary and the finishing fallback. The research also asked the journey to show the projected hold,
  the `hygiene:model-fallback` fact, the cost attribution and the primary-restoration clearance. Those
  are not named in the criterion.
- C2. The fork-side mirror of the status literals appears only in `bd-ib-vuwrv5`'s Context prose, not in
  its Definition of Done bullets, so acceptance will not grade it.
- C3. A hazard for whoever activates chains: `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.4`,
  `gpt-5.3-codex-spark` and `zai/glm-5.2` are catalogued but unpriced, and `claude-opus-4-8[1m]` does not
  normalize to a priced identity. If `bd-ib-vuwrv5` passes a chain "to every ACP node", every node gains
  a `candidate_index`, the no-default path activates for ordinary runs, and any such identity darkens
  the whole run cost, which refuses an unattended drain under enforce mode. No carrier names this.
- C4. Re-binding the two heading-coverage rows to an emission-asserting test is not in `bd-ib-vuwrv5`'s text.
- C5. `bd-ib-vuwrv5` carries the label `blocked-reason:needs-human` in addition to its blocks edge.

## 6. Limits of my own probes

- "Standalone" was established from each carrier's `bd show --json` dependency rows (`id` +
  `dependency_type`) and from re-running the child enumeration over `bd list` rows (`depends_on_id` +
  `type`, plus `parent`). The dotted-id form cannot apply to these ids.
- I ran 134 tests from nine files; I did not run `just check`, the full suite, or the post-merge janitor.
- The claim that no production run reaches the chain cost path rests on reading the parser and the
  fork's emission site, not on a real run's event stream; I did not call `fabro events`.
- Whether Claude Code spans emit a `[1m]`-suffixed model id is unmeasured here.
- The vetting legs (Opus, Codex) are the coordinator's report; I saw only the ledger's account of them.
- I did not re-verify the hp engine or the closed children again in this pass; those stand on pass 1.
- The ledger search for a pending pricing proposal covered `SPECIFICATION/proposed_changes/` on master
  only, not unmerged `spec/*` branches.
