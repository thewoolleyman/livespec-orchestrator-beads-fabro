VERDICT: NOT-COMPLETE

# Completeness review, pass 1 — plan `factory-configurable-model-fallback-priority` (epic `bd-ib-jxvgq5`)

Reviewer: independent, read-only, no role in implementation. Reviewed 2026-10-04 against
`origin/master` at `fcf208dc`, the fork `thewoolleyman/fabro` `origin/factory-integration` at
`8869e88b2`, the ledger (`bd list --status all --limit 0 --json`, 1,144 items), and the hp factory
(`fabro ps` / `system info --server https://hp-xubuntu.perch-rudd.ts.net:32276`).

Sources read in full: all eight files under `plan/factory-configurable-model-fallback-priority/research/`
on master (there is NO `preserved/` directory on master; it exists only on the origin branch
`preserve/bd-ib-tmgt7v-01M3WTW7XW77`, from which I read the implement and review responses), all 48
comments on the epic (`bd comments --json`, key `text`), the records and comments of all ten children,
`SPECIFICATION/contracts.md` sections "Agent and model catalogs" and "Factory-configurable ACP fallback
priority" in full, and Scenarios 127 and 129 in full.

Child enumeration: selecting every ledger item with a `parent-child` edge whose `depends_on_id` is
`bd-ib-jxvgq5`, or `parent == bd-ib-jxvgq5`, or a dotted id under it, returns exactly the ten items the
brief listed (nine `closed`, `bd-ib-tmgt7v` `active`). No unlisted child.

## 1. The headline

The plan's stated goal (opening research section 2; scope event 2026-09-09) is that a node "fall back
automatically, in priority order". On `origin/master` that cannot happen. Every half exists — the
Dispatcher parses, validates, gates, preflights, projects and (soon) prices a chain; the Fabro engine
on hp executes a chain when a node carries the `acp.fallback_chain` attribute — but **nothing connects
the two**: the Dispatcher never emits the chain to Fabro, and the workflow graph never declares the
attribute. A repository that configures `fallbacks` today passes every gate, journals a chain, and is
then launched with its primary adapter alone. The one activity that would have exposed this, the live
journey on hp, was replaced by a recorded-stream test whose events are hand-written fixtures. This is
finding B1; B2 and B3 follow from it.

## 2. Requirement-to-carrier table

"Verified" means I checked it myself on the forge or the tree; "ledger" means I am relying on the
record. PR state for every row was read with `gh pr view <n> --json state,mergedAt,commits,files`.

| # | Requirement or deferral | Source | Carrier | Closure evidence I verified | Row verdict |
|---|---|---|---|---|---|
| 1 | S0 ratified contract and scenarios (v109) | scope event 2026-09-09 | PR 2402 (epic-level) | `SPECIFICATION/history/v109/proposed_changes/factory-configurable-model-fallback-priority*.md` on master; section and Scenario 127 present | Delivered |
| 2 | S1 closed candidate schema, primary-preserving resolution, redaction, digests | slice research S1 | `bd-ib-qu3htl` | PR 2447 MERGED 2026-09-10; `_acp_candidate_schema.py`, `_acp_node_chains.py`, `_acp_chain_resolution.py` on master and used by later slices | Delivered (spot-checked, not line-audited) |
| 3 | S2 typed classifier, versioned holds, clearance valves | slice research S2 | `bd-ib-5ltgny` | PR 2471 MERGED; `_acp_failure_matching.py`, `_acp_hold_ledger.py` on master; `ingest_hold_observation` now has a production caller (`_acp_event_projection.py:259`) | Delivered, with a KNOWN UNFIXED DEFECT (B6) |
| 4 | S3 preflight, success-critical admission, shared verdict | slice research S3 | `bd-ib-okf3om` | PR 2479 MERGED; `_acp_preflight_verdict.py` consumed by admission, re-probe, loop wave, needs-attention waits | Admission half delivered. "Candidate one is selected in configured order" and "a reached conditional empty chain terminates typed" are DECISIONS WITH NO CONSUMER (B1): `reached_node_termination` has zero callers on master |
| 5 | S4 Fabro in-node failover, events, side-effect gate, capability | slice research S4 | `bd-ib-mujvyn` | fork PR 9 MERGED into `factory-integration` at `20bf91e06`; content on `origin/factory-integration`: `acp_fallback/chain.rs`, `acp_chain_tests.rs`, `ACP_FALLBACK_CHAIN_CAPABILITY` in `fabro-types/src/capabilities.rs` | Delivered in the fork |
| 6 | Structured candidate form, catalogs, `codex_models` retirement | scope events 2026-09-30 | `bd-ib-kc7vzk` | PR 2546 MERGED (13 commits, 68 files); `_acp_agent_catalog.py`, `_acp_model_catalog.py`, `_acp_codex_models_retired.py` on master; workflow defaults are structured entries in `workflow.toml`; heading rows for "Agent and model catalogs" and Scenario 129 bound to `tests/integration/test_acp_structured_catalogs_scenario129.py` | Delivered, EXCEPT the agent catalog (B5) and "config_options on the chain candidate", which is a dataclass field never emitted anywhere (B1) |
| 7 | Fork in-protocol model and effort selection | scope event 2026-09-30 | `bd-ib-afcn3d` | fork PR 10 MERGED at `8869e88b2`; `ACP_CANDIDATE_CONFIG_OPTIONS_CAPABILITY` on `origin/factory-integration` | Delivered in the fork; never exercised by a real run (record itself says "not yet measured on a real run and is part of S7's proof") |
| 8 | S5 event projection, holds, warning lifecycle, projection-failure fact | S5 draft record | `bd-ib-xtgwpz` | PR 2495 MERGED; `project_run_events` called from `_acp_projection_terminal.py:97` and `_dispatcher_reconcile_acp_projection.py:96` | Delivered (wiring verified; behaviour not re-tested) |
| 9 | S6 re-cut: per-attempt, catalog-first pricing; `claude-opus-5` priced; no default model | scope event 2026-09-30 03:27 | `bd-ib-tmgt7v` | NONE. Item is `active`, assignee `fabro`, run `01M4350SNV0T` `running` on hp at review time. `_acp_model_catalog.py` on master carries NO prices (its digest docstring says pricing is "deliberately not" there) | NOT DELIVERED (B4) |
| 10 | S7a pin the capability-bearing build on both hosts | S7 draft record | `bd-ib-q32gs5` | PR 2548 MERGED; live `fabro system info --json --server hp` returned `git_sha 8869e88`, capabilities `["acp.fallback_chain.v1","acp.candidate_config_options.v1"]`; README lines 136-151 and AGENTS.md name the build and both `.bak` files; receipt comment 2026-10-01T22:56:07Z read back | Delivered for hp. vps deviation is recorded and justified (N1) |
| 11 | S7b capability gate on the resolved factory | S7 draft record | `bd-ib-jamtsf` | PR 2549 MERGED; `_acp_capability_gate.py` on master has both arms, fail-closed on unreadable; called from `_dispatcher_acp_nodes._resolve_chains` | Delivered |
| 12 | S7b `dispatcher.minimum_release` = first fallback-capable release | S7 draft record; contracts.md line 5827 | `bd-ib-jamtsf` | `.livespec.jsonc` line 257: `0.161.0`. `git show v0.161.0:…/_acp_capability_gate.py` has ONLY the `config_options` arm; `FALLBACK_CHAIN_CAPABILITY` first appears at `v0.162.0` (commit `71526bc4`) | DELIVERED ON PAPER (B3) |
| 13 | S7b one controlled live fallback journey on hp | slice research S7; S7 draft record ("run one controlled factory journey on hp") | none | Test module docstring: "A LIVE FACTORY JOURNEY IS A SEPARATE, OPERATIONAL ARTEFACT"; epic handoff 2026-10-04T06:19 says not performed and uncarried; ledger search (below) finds no live item | NOT DELIVERED, NO CARRIER (B2) |
| 14 | S7 "render the EFFECTIVE signatures into each candidate when it emits the chain input" | S4 implementation record, "Consumer contract as built" | none | No production code on master contains the string `fallback_chain` other than the capability constant; `_run_inputs` renders only `<input>=<primary adapter>`; `workflow.fabro` nodes carry only `acp.command` | NOT DELIVERED, NO CARRIER (B1) |
| 15 | S7b Scenario 127 and contract-heading coverage bindings | S7 draft record; handoff 2026-10-04 | `bd-ib-jamtsf`, PR 2558 | Rows present, no `TODO`; no row in either register names the epic, a child, or the slug (186 rows, 97 TODO, none owned by this plan) | Bound, but see N2: neither bound test exercises the path B1 shows is missing |
| 16 | Deferral: generic `transient_infra` whole-workflow redispatch | scope event 2026-09-09 | `bd-ib-cewr.6` (backlog, live) | ledger | Validly carried |
| 17 | Deferral: Fabro modernization beyond 0.254 | scope events 2026-09-09, 09-12, 09-30 | plan `fabro-currency`, `bd-ib-6tcjfx`; P5 `bd-ib-r5cnjd` (pending-approval) names this epic | ledger | Validly carried |
| 18 | Deferral: vps return to service | S7a pin record | `bd-ib-iud52v` (pending-approval) | ledger | Validly carried |
| 19 | Deferral: live catalog or host credential probing | scope event 2026-09-09 | none; stated reconsideration condition ("only when a provider-generic sandbox-local typed probe exists") | n/a | Valid deferral with a stated condition |
| 20 | Deferral: provider-reported reset times untrusted; hold expiry fixed fifteen minutes | scope events 2026-09-09 and 2026-09-30 03:53 | none needed | Recorded as a maintainer review-and-keep ("a capped upper-bound variant was described and not requested") | A recorded DECISION, not a dropped requirement (N3) |
| 21 | Deferral: upstream native fallback import; ACP crate bump; dispatch-time registry fetch | scope events 2026-09-12, 09-30 | none needed | Design decisions with reasons | Valid |
| 22 | Deferral: legacy overlap `bd-ib-5j4b` disposition | scope event 2026-09-10 | `bd-ib-5j4b` (backlog, live) | ledger | Validly carried |
| 23 | Rider: `GENERIC_STATUS_LITERALS` lacks `404 not found` | S4 implementation record; handoffs 2026-09-12 | none | `_acp_failure_matching.py` lines 61-74 on master: literal still absent; line 116 is a set-membership test | KNOWN DEFECT, NO CARRIER (B6) |
| 24 | Ratified-text tension: pricing precedence | preserved implement response for `bd-ib-tmgt7v` | none | contracts.md lines 5734-5737 ("override … wins over the catalog value") vs lines 5752-5753 and 6097-6099 ("catalog first … per-candidate … second") | SPEC CONTRADICTION, NO CARRIER (B7) |

## 3. BLOCKING findings

### B1. The Dispatcher never transports the candidate chain to Fabro; reactive and preflight fallback are inert end to end

What is missing. The Fabro handler runs a chain only for a node carrying the `acp.fallback_chain`
attribute (fork `acp_fallback/chain.rs`; S4 record: "one optional string node attribute
`acp.fallback_chain`… `acp.command` must still be present and must equal `candidates[0].command`").
The S4 record assigns the emission to S7: "S7 must render the EFFECTIVE signatures (configured plus
built-in) into each candidate's `availability_signatures` when it emits the chain input." No slice
did. Consequently none of these ratified observables can occur in production: ordered reactive
failover in one node visit; "candidate one is selected in configured order" when candidate zero is
held (Scenario 127); `config_options` reaching the handler (kc7vzk criterion 10); the
preflight-skipped set reaching the engine; typed termination of a reached conditional node with an
empty chain.

Evidence.
- `git grep -c 'fallback_chain' origin/master` over the whole tree: the only production hit is
  `_acp_capability_gate.py` (2, both the capability constant). No hit under `.claude-plugin/.fabro/`.
  Positive control: the same grep finds the capability constant and 5 test files, so it could hit.
- `.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro`: every ACP node carries exactly
  `acp.command="{{ inputs.<node>_adapter }}"` (lines 118-492) and no other `acp.` attribute.
- `_acp_node_layers._run_inputs` renders `f"{name}={distinct[0]}"` from `nodes[node].rendered`, the
  PRIMARY; `_dispatcher_engine.dispatch_fabro_run_inputs` passes only those plus integration and
  policy inputs.
- `_dispatcher_acp_nodes.prepare_acp_nodes` returns `resolution` and discards the chains except for
  the redacted journal; its own docstring: "The resolved chains themselves have no consumer yet --
  preflight, classification and the runtime transition are later slices".
- `reached_node_termination` (`_acp_reached_termination.py`) has zero callers (`git grep` over
  `.claude-plugin`); its docstring says "S4 owns the runtime transition that consumes it".
- Preflight output is consumed only as `verdict.viable` / `fallback_enabled` (admission, re-probe,
  wait attention). Nothing swaps the launched adapter, so a held primary with a viable fallback is
  ADMITTED and then launched on the held primary.

How it slipped. The S7b record's own acceptance criteria dropped the emission sentence; criterion 4
("a consumer-tier test dispatches a two-candidate structured chain to a pinned factory and asserts
one `agent.acp.failover` event…") was graded on a test that dispatches nothing: its failover and
started events are built by `_failover()` / `_started()` helpers in the test file and fed through a
fake `CommandRunner`.

Scope searched. All of `origin/master` for the attribute name; the three modules on the launch path
read directly; commits to those modules and to `workflow.fabro` since PR 2549 (one unrelated commit,
`41648403`). Ledger: regex for chain emission/transport over title, description, acceptance
criteria, notes, design and metadata of all 1,144 items returned 4 hits, all closed children of this
epic describing the Fabro side.

What discharges it. Either (a) implement and land it under this plan: a workflow input and
`acp.fallback_chain` attribute per ACP node, Dispatcher rendering of the chain document
(schema_version 1, `primary_generation`, `full_chain`, candidates with EFFECTIVE signatures and
`config_options`, preflight-skipped set, `candidates[0].command == acp.command`), and a test that
asserts the rendered `fabro run` argv; or (b) a NAMED standalone live item carrying exactly that,
with no parent-child edge to this epic. `bd-ib-r5cnjd` (fabro-currency P5) is the natural
neighbour — it already says "bd-ib-jxvgq5 and bd-ib-afcn3d each receive an explicit evidenced
disposition" and "Do not deploy the 0.254 S4 bridge by default" — but as written it does NOT name
Dispatcher-side chain emission, so it does not carry this today. If the maintainer's intent is that
emission waits for Petri, that must be stated in a live item and in a plan scope event; at present
the record everywhere says S7 is done.

### B2. The controlled live fallback journey on hp was never run, and no live item carries it

What is missing. Slice research S7 ("Run a controlled factory journey where the primary produces the
measured exact unavailable-model diagnostic and the fallback succeeds in the same node visit. Assert
remote events, holds, warning, cost, unchanged run/sandbox identity, and no predecessor replay"), the
first scope event's S6 carrier ("controlled unavailable-primary run, visible fallback warning,
preserved work, and primary-restoration clearing evidence"), and the fork record ("whether the live
Codex and Claude adapters advertise these ids is not yet measured on a real run and is part of S7's
proof").

Evidence. `tests/integration/test_acp_fallback_journey_scenario127.py` docstring: "A LIVE FACTORY
JOURNEY IS A SEPARATE, OPERATIONAL ARTEFACT… whose evidence is a run id and a journal excerpt rather
than a test." Its `_RUN_ID` `01M3WW420JH49ZWJYV15HF73XN` is the run that IMPLEMENTED `bd-ib-jamtsf`,
not a fallback run. The epic's own 2026-10-04T06:19 handoff states the journey was not performed and
is uncarried. Given B1 it could not have succeeded: no dispatch can deliver a chain to hp.

Scope searched. Ledger regex `live (fallback )?journey|controlled (factory |fallback )?journey|fallback journey`
over the same fields of all 1,144 items: 2 hits, the only live one is the epic itself.

What discharges it. Run it after B1 lands and record the run id, the `agent.acp.failover` event, the
projected hold, the `hygiene:model-fallback` fact, the cost attribution and the primary-restoration
clearance on the ledger; or a NAMED standalone live item (blocked on the B1 carrier) whose acceptance
is that recorded evidence.

### B3. `dispatcher.minimum_release` is one release below the gate it is supposed to guarantee

What is missing. contracts.md line 5827: the floor MUST be "at or above the first fallback-capable
plugin release"; line 5820: a new-grammar dispatch MUST refuse when "the Dispatcher or pinned Fabro
build does not advertise this capability".

Evidence. `.livespec.jsonc` line 257 is `0.161.0`. `git tag --contains ea0d6c69` shows the gate file
first shipped in `v0.161.0`, but that version has only `CONFIG_OPTIONS_CAPABILITY` and
`config_options_capability_refusal` (102 lines); `FALLBACK_CHAIN_CAPABILITY` and
`acp_capability_refusal` first exist at `v0.162.0` (162 lines, commit `71526bc4`). A 0.161.0 build
therefore sends a manual-form fallback chain past the floor with no `acp.fallback_chain.v1` check.
The config comment's justification ("the factory capability gate that keeps such a chain from running
green") is true only of the `config_options` arm. The handoff of 2026-10-02T00:43 noticed this and
called it "a follow-up question, not a reopen"; no item was filed. The journey test hard-codes
`"0.161.0"`, so the test pins the defect.

Scope searched. Tags `v0.161.0`, `v0.162.0`, `origin/master` for the module content (positive
control: `v0.162.0` shows the constant). Ledger regex for `minimum_release` near `0.161`/`0.162`: 0
hits.

What discharges it. Raise the floor to at least `0.162.0` (and update the test constant and the
config comment) in a merged change, or name it in the B1 carrier with the floor set to the first
release that actually EMITS a chain, which is the honest reading of "first fallback-capable".

### B4. `bd-ib-tmgt7v` (S6 re-cut, pricing) is not delivered

Evidence. Status `active`, run `01M4350SNV0T` running on hp at review time. On master the model
catalog has no prices and `claude-opus-5` is unpriced; the journey test supplies prices through a
fixture `dispatcher.model_catalog`.

What its closure must prove, by content on `origin/master`, not by the ledger:
1. A merged PR whose commits are on master (content grep, not SHA), post-merge janitor green, item
   closed through `reconcile-merged` or its gate.
2. `claude-opus-5` carries all four prices in the model catalog.
3. EVERY model the shipped workflow defaults and this repository's `acp_nodes` actually run
   (`claude-haiku-4-5`, the review/disposition models, any Codex slug in use) still prices after the
   default-model fallback is removed — the criterion "a single-candidate run is priced exactly as
   before" must be shown on a real post-merge dispatch's cost record, because an unpriced default
   model would silently turn every run's cost unobservable and trip the fail-closed gate.
4. `AcpNodeStart` keeps master's `confirmed_model`/`confirmed_effort` AND gains
   `chain_deadline_epoch_ms` (the union the continuation rider names).
5. The precedence it implements is stated, and B7 is carried.
6. Cleanup: origin branches `preserve/bd-ib-tmgt7v-01M3WTW7XW77` and
   `needs-human/01M3T09DJ0ZF9T9XZTFF6W4STT` (both still present per `git ls-remote`) deleted.

### B5. The agent catalog's non-built-in entries are guessed, not seeded from the registry, and nothing carries their verification

What is missing. contracts.md lines 5706-5719: each entry MUST carry "the launch distribution rendered
from the registry's `npx`, `uvx` or per-platform `binary` distribution at a pinned agent version",
the catalog MUST "record the registry snapshot digest", and the population is the named five "and the
rest of the registry's population". Scope event 2026-09-30: "a committed, pinned agent catalog seeded
from the ACP registry snapshot".

Evidence (`_acp_agent_catalog.py` on master). Five entries exist. `opencode`, `grok-build`,
`glm-acp-agent` have `version=REGISTRY_SNAPSHOT_DATE` (a date, not a version) and commands that the
module's own docstring says follow "the `@agentclientprotocol/<adapter>` npx convention" rather than
the registry: `npx -y @agentclientprotocol/grok-build-acp`, whereas this plan's own research
(config-ergonomics assessment) measured the registry distribution for `grok-build` as
`@xai-official/grok agent stdio`. The digest is computed over the module's own entries; no registry
snapshot digest is recorded. The remaining ~40 registry agents are absent. The docstring defers
verification to "the work-item that made the change" for a future first dispatch; the first-run
reviewer flag ("must name the full ratified registry population") was downgraded in the continuation
rider to "keep both as documented".

Scope searched. Ledger regex `agent.catalog|seeded|registry snapshot`: 11 hits, the one live hit
(`bd-ib-js1f`) is unrelated.

What discharges it. A NAMED standalone live item: re-seed the three entries from the actual registry
snapshot (real distribution, real pinned version, recorded registry digest), decide the "rest of the
registry" population or route the spec sentence through `propose-change`, and record one
verification run per non-measured agent. Until then a structured candidate naming `grok-build`
passes every refusal and fails at launch.

### B6. Known classifier defect in the plan's highest-risk clause is unfixed and unfiled

Evidence. S4 implementation record and two handoffs flag that `GENERIC_STATUS_LITERALS` lacks
`404 not found` while `_STATUS_MARKERS` uses it. On master the set (lines 61-74) still lacks it, and
`signature_discriminates` is a membership test (`normalized(literal) not in GENERIC_STATUS_LITERALS`,
line 116), so a text signature whose only literal is `404 not found` (likewise `400 bad request`)
counts as naming something beyond the generic status and can make a generic 404 fallback-eligible —
the permissive direction the opening research calls "the highest-risk clause". The record says "left
for the maintainer to file or fold into S5"; S5's criteria do not contain it and the fork mirror is
also unfixed.

Scope searched. Ledger regex `404 not found|GENERIC_STATUS_LITERALS`: 2 hits, the live one
(`bd-ib-ihp5`) is the unrelated Codex compaction-404 item.

What discharges it. A NAMED standalone live item (Dispatcher fix plus the fork mirror), or a merged
fix with a regression test.

### B7. The ratified text contradicts itself on pricing precedence and no proposal carries it

Evidence. contracts.md "Agent and model catalogs": "A per-candidate `pricing` … override on a
structured entry wins over the catalog value" (lines 5734-5737), versus the same section's "price a
structured candidate through the model catalog first and a per-candidate override second" (lines
5752-5753) and the cost clause (lines 6097-6099). The first `bd-ib-tmgt7v` run flagged it ("A tension
in the ratified text that I resolved rather than papered over… This wants a maintainer [ruling]") and
implemented catalog-first. Both readings were introduced by this plan's v112.

Scope searched. Ledger regex `pricing precedence|catalog first|override (wins|second)`: 1 unrelated
live hit; `SPECIFICATION/proposed_changes/` on master holds two pending proposals, neither about pricing.

What discharges it. A filed `propose-change` (or a named live item that will file one) settling the
order, referenced from `bd-ib-tmgt7v`'s closure.

## 4. NON-BLOCKING observations

N1. vps deviation (lead g) is properly recorded and justified. `bd-ib-3ysb6k` is real, closed by PR
2467, and its description says the vps service "must remain stopped" and "Do not query, start, or
restart either VPS Fabro backend"; `.livespec.jsonc` `factories` declares hp alone. The deviation is
recorded in the pin record, the receipt comment, the close reason and AGENTS.md. `bd-ib-q32gs5`'s
criterion 3 ("on each") was not amended and is literally unmet for vps; the receipt says so.

N2. PR 2558's binding (lead f) is honest in the narrow sense — the bound test is real, runs the real
config and catalog seams, and asserts the heading's configuration half — but it is a
configuration-resolution precondition test bound to a heading whose substance is runtime fallback.
Together with Scenario 127's recorded-stream binding, the two rows make the coverage registers read
green over the exact gap in B1. When B1 is carried, the carrier should own re-binding at least one of
them to a test that asserts the emitted chain.

N3. Hold expiry (lead h) is an explicit, attributed maintainer decision ("reviewed this on 2026-09-30
and kept it; a capped upper-bound variant was described and not requested"), not a silently dropped
requirement. No home is needed.

N4. `_codex_model_tiers.py` (lead c) still exists but is only the `CodexModelTier` value type; its
docstring says so, `_acp_codex_models_retired.py` refuses the key, and `_acp_node_repository.py`
checks the retired key before parsing. The retired expansion is not reachable. Stale cross-references
remain: `_acp_agent_catalog.py:107` and `_acp_model_catalog.py:17,81` still say the measurement
record lives in `_codex_model_tiers`, which now says it moved to the model catalog.

N5. Side observations from the handoffs that are NOT this plan's requirements, all unfiled (lead i):
the janitor-before-refresh ordering defect (cost this plan two whole runs, kc7vzk and tmgt7v;
ledger regex found no item); the livespec-overseer picker pin (another repository); the fork carrier
not fmt-clean in two PR 8 files and the README missing a PR 8 row (`bd-ib-bindom` thread); the
`_dispatcher_cost_gate.py` / `_dispatcher_cost_sink.py` LLOC headroom; the calibration emitter staying
on aggregate pricing. Recommend filing the first; none blocks the archive.

N6. Unfixed-by-choice advisories with no carrier: the S2 reviewer's same-disposition/different-source
ambiguity (conservative direction, maintainer chose to proceed) and the S1 note that the digests do
not track every matcher or price edit. Both fail in the safe direction.

N7. The detection-coverage anchor `bd-ib-j5fzyo` holds only ATTEMPT records for this plan's ranges;
no COMPLETED record was ever written ("the declared scope was covered only partially"). That is the
anchor's own bookkeeping, not a plan child.

N8. `bd-ib-jamtsf`'s close reason and the 2026-10-02 handoff say "prove one fallback journey" was
delivered. Any correction should reach the same audience: the epic handoff and the item, not only
this review.

## 5. Limits of my own probes

- Ledger carrier searches covered title, description, acceptance criteria, notes, design and metadata
  of all 1,144 items in THIS tenant. They did NOT cover comments on items other than the epic and its
  ten children, and did not cover other tenants (for example livespec-overseer). A carrier that
  exists only as a comment elsewhere, or in another repository's ledger, would be missed.
- The transport absence (B1) rests on a literal grep for `fallback_chain` plus a direct read of the
  three launch-path modules. A string assembled at runtime would evade the grep; the direct read of
  `_run_inputs` and `dispatch_fabro_run_inputs` is what rules that out. I did not execute a dispatch
  or inspect a real `fabro run` argv.
- I did not query hp for whether any `agent.acp.failover` event has ever been emitted; B2 rests on the
  plan's own admission plus B1 making it impossible.
- My first fork content probe (`gh api …/contents/…?ref=`) failed on shell globbing and returned
  nothing; I replaced it with the local clone `/data/projects/fabro` after `git fetch origin
  factory-integration`, whose `rev-parse` matched `8869e88b2`. The fetch's own output was not shown.
- PRs 2447, 2471, 2479 and 2495 were verified as MERGED with their modules present and consumed on
  master; I did not line-audit their acceptance criteria or run any test.
- For B7 I checked `SPECIFICATION/proposed_changes/` on `origin/master`: two pending proposals
  (`factory-size-justification-gate.md`, `live-exercise-acceptance-admission.md`), neither mentions
  pricing. Unmerged `spec/*` branches on origin were not searched.
- `bd-ib-3ysb6k` returned no comments; the "maintainer direction" is in its description, as quoted.
