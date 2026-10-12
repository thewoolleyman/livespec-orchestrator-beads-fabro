# Downsides of moving ordered model fallback from the Fabro engine to the Dispatcher

Investigated 2026-10-12, read-only, in `/data/projects/livespec-orchestrator-beads-fabro` at `428b7e65`.
Paths are relative to the repo root. `C/` means `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/`.

Labels used below:
- **MEASURED** means I ran something or read the exact text.
- **INFERRED** means I reasoned from code or spec that I read, but did not run.

"Dispatcher-level" means the proposed design: pick the first non-held candidate when the item is dispatched, and when a node fails on quota or refusal, put the provider on a cooldown hold and re-dispatch the whole item. "Engine-side" means the v112 design: the engine fails over to the next candidate within the same node visit.

## What v112 actually commits to, quoted

These normative sentences are in `SPECIFICATION/contracts.md` §"Factory-configurable ACP fallback priority" (lines 6455–6808). All MEASURED.

**Cannot be met by a Dispatcher-level design:**
- 6690–6693: "Reactive fallback is one bounded node visit. The externally observable integration is one run id, one sandbox identity, one node deadline, no predecessor-node replay, ordered candidate attempts, and normal workflow continuation on success."
- 6699–6708: one shared deadline, and "After the first reactive transition the node visit is non-retryable … The attempted set, original deadline, and event ids MUST survive resume."
- 6710–6721: sandbox-local partial changes MAY pass to the successor candidate, controlled by a side-effect onset ledger.
- 6663–6668: a reached conditional node whose chain is empty "MUST terminate the run before starting an adapter … MUST NOT traverse a continuation/failure edge into janitor, non-convergence, or `needs_human`". This is an in-run engine behaviour. `reached_node_termination` has no caller today (MEASURED: grep finds no caller outside `C/_acp_reached_termination.py`).
- 6747–6758: each transition emits a versioned `agent.acp.failover` engine event.
- 6760–6777: the Dispatcher MUST project those events, and an unresolved projection-failure fact stops unattended picking.
- 6522–6523, 6531: "A new-grammar-enabled dispatch MUST also refuse before claim when the Dispatcher or pinned Fabro build does not advertise this capability". On Petri, which never advertises `acp.fallback_chain.v1`, this refuses every fallback configuration. It therefore has to be revised (`C/_acp_capability_gate.py:76`).
- Scenario 127 (`SPECIFICATION/scenarios.md:3547ff`) has sub-scenarios that are engine-shaped and would need rewriting, along with their `tests/heading-coverage.json` bindings:
  - "A domain-held primary is skipped …" (it emits `agent.acp.failover`)
  - "A sandbox-local partial write is handed to the next candidate"
  - "One deadline and post-transition state prevent replay"
  - "Projection is server-qualified …"

**Can be met by a Dispatcher-level design, or met differently:**
- Preflight filtering by holds, and refusing admission only when a success-critical chain is empty (6637–6670; §"Provider spend containment", 4926–4931). This is already Dispatcher-side, and it already exists (`C/_dispatcher_acp_preflight.py`, `C/_dispatcher_admission_eligibility.py:150`).
- Holds minted from "a typed terminal failure" (6650–6651). The spec allows this, but the code is not built (see D5).
- One journal record and one `hygiene:model-fallback` fact per executed non-primary candidate (6779–6791). This can be sourced from the Dispatcher's own selection.
- "Cost follows every attempt in a successful fallback run" (6793–6808). It cannot hold within one run. It can be approximated across runs, but see D7.
- The confirmed model and effort on `agent.acp.started`, and the in-protocol `config_options` (6723–6745). These are engine features that are independent of which layer does fallback, and Dispatcher-level does not remove the need for them (D12).

**Open child item `bd-ib-vuwrv5`** (MEASURED via `bd show` and `bd comments`):
- Its fourth criterion is "One controlled live dispatch on the hp factory records a refused primary and a fallback finishing the same node visit". A Dispatcher-level design cannot satisfy it, so the item must be regroomed or disposed through the spec revision.
- Its 2026-10-04 rider adds three things:
  - the journey evidence list (the failover event, "unchanged run and sandbox identity with no predecessor replay", and the confirmed model);
  - an engine-side mirror of the status literals;
  - a warning: "UNPRICED MODELS BECOME A HAZARD THE MOMENT A CHAIN IS EMITTED".
- The 2026-10-10 correction comment says the Petri cutover does not add the capability.

---

## (A) Downsides of Dispatcher-level fallback

### D1. The visit is lost: the whole item re-runs, including the nodes before the failure — SIGNIFICANT

- **Evidence:**
  - MEASURED from the dispatch journal (`tmp/fabro-dispatch-journal.jsonl` calibration records since 2026-09-15): green runs have a median of 112 min and a p90 of 222 min (n=66). Their recorded cost has a median of $40.84 and a p90 of $144.32.
  - `.livespec.jsonc` sets `node_timeouts.implement` to 14400 s and `review_fix` to 7200 s.
  - **Mid-run exhaustion is real, not hypothetical** (MEASURED with `fabro inspect --server hp` on run `01M4J5M63APH75NJ1JF7ZCN9DY`, 2026-10-10):
    - Run start was 05:48:30Z. `review` (on Codex) succeeded.
    - `disposition` (also on Codex) then failed at about 05:50:42Z with "You've hit your usage limit … try again at Oct 16th, 2026 9:38 PM". It was retried once (`node_retries.disposition = 1`) and then routed to `needs_human`.
    - Under engine-side fallback that disposition visit would have continued on the next candidate. Dispatcher-level throws away everything before it.
  - Every ACP node has an `outcome=failed -> needs_human` edge (`.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro:710–894`). So the failure always ends the run.
- **Is it avoidable?** Partly.
  - `resume --item` (contracts §3755; `C/_dispatcher_resume_anchor.py`) can re-enter after `publish_draft`/`proof_capture`, so review/disposition/proof_verify failures need not re-run implement. But resume is an operator command today. Automating it is new work (INFERRED).
  - Before publication (dod_gate, implement, fix, janitor) the only salvage is "seeding rework from the preserved ref" (the needs-human detail text in `C/_dispatcher_fabro_terminal.py`). That re-runs nodes, it does not continue the visit.
  - The loss is **inherent** for a quota that runs out inside `implement`.

### D2. Detecting the failure is broken today, and Petri makes it worse — SIGNIFICANT (avoidable, but a precondition)

- **Evidence, all MEASURED:**
  - (a) **The needs-human path drops the provider attribution.** `_needs_human_terminal_outcome` (`C/_dispatcher_fabro_terminal.py:123–185`) builds the `blocked` outcome with no `provider_usage_limit*` fields, even though `failure` was parsed at line 88. Since every ACP-node failure routes to `needs_human`, quota failures arrive at the Dispatcher unlabelled. The journal outcome for the 2026-10-10 run shows `status: blocked`, `provider_usage_limit_provider: null`.
  - (b) **Claude's 5-hour "session limit" is not recognized at all.** "You've hit your session limit · resets 3:40am (UTC)" with `data.errorKind: "rate_limit"` was classified `transient_infra` with provider null on 2026-08-23, 2026-09-09 (×2) and 2026-10-09 (bd-ib-4ipmub, run `01M4EZ7CGACP…`).
    - Neither the Dispatcher's hint list (`C/_fabro_port_permanent_failure.py:67–72`) nor the built-in signatures (`C/_acp_builtin_signatures.py`; for Anthropic only "monthly spend limit") match it.
    - Of the provider-limit failures in this journal for October, the existing detection labelled **zero**. The only `provider-exhaustion-observed` records ever written are three, on 2026-08-30.
  - (c) **Codex now sends a camelCase field.** The October payload carries `"codexErrorInfo": "usageLimitExceeded"`. The structured token the code looks for is snake_case (`_PROVIDER_USAGE_LIMIT_FIELD = '"codex_error_info": "usage_limit_exceeded"'`), so only the prose hint saves it.
  - (d) **On Petri, the structured payload is gone.** Petri keeps only `failure.detail.message`; the `data` payload is lost (`plan/fabro-currency/research/004-acp-spend-limit-evidence.json`). The Anthropic text there is "You've hit your limit · resets …", which no hint matches.
  - (e) **INFERRED: on Petri a needs-human route may replace the provider text entirely.** Research 007 probe p6 shows Petri's terminal `detail.message` carries the needs-human script's stderr. So a quota failure routed through `needs_human` may lose the provider sentence from `inspect`, and detection would have to read per-attempt `step.finished` events instead.
- **Is it avoidable?** Yes, with work: fix the needs-human outcome, add the measured literals, and read Petri events. The engine-side design shares the signature-table gaps, because the Dispatcher renders the signatures for the engine too (S4 record: "Fabro carries NO signature table"). But the engine sees the raw JSON-RPC error.

### D3. A quota failure parks the item at `blocked / needs-human`, waiting on a human — SIGNIFICANT

- **Evidence:**
  - MEASURED: the outcome detail says "the decision lives in the ledger … Answer with `resolve-blocked:<id>:ready`" (`C/_dispatcher_fabro_terminal.py:170–185`). The 2026-10-10 run took exactly this route.
  - INFERRED: automatic re-dispatch therefore needs one of two new things:
    - a graph change so that provider-class failures do not take the `outcome=failed -> needs_human` edge (I did not establish that edge conditions on either engine can tell the failure class apart); or
    - an automatic `blocked/needs-human -> ready` transition. That cuts across the "decision lives in the ledger" policy and the v093 rule that a factory run never awaits a human.
- **Is it avoidable?** Yes, but it is a lifecycle and spec decision on top of the v112 revision.

### D4. The spec revision is larger than "change one sentence" — SIGNIFICANT

- **Evidence:** MEASURED; see the quoted list above. The revision has to cover:
  - one visit, deadline, sandbox and replay;
  - the partial-write handoff;
  - the failover event and its projection, including the unattended stop-picking rule;
  - the capability-gate refusal on Petri;
  - the reached-node termination rule;
  - Scenario 127's sub-scenarios and their heading bindings;
  - `bd-ib-vuwrv5`'s criteria.
- **Also:** already-shipped S5/S6 Dispatcher code is keyed on engine events and would become dead, or have to be re-sourced from Dispatcher selection: `C/_acp_event_projection.py`, `C/_acp_fallback_events.py`, `C/_acp_fallback_warning_ledger.py`, and `C/_dispatcher_reconcile_acp_projection.py` (INFERRED).
- **Is it avoidable?** No. It is inherent, and it is the known cost, but its scope is broad.

### D5. Holds are only ever created from engine events, and they cannot track a multi-day outage cheaply — SIGNIFICANT

- **Evidence, MEASURED:**
  - Typed holds are created only from projected `agent.acp.failover` events: `hold_observation_record(` is called only at `C/_acp_event_projection.py:251`. There is no path from a terminal failure.
  - The legacy hold is `_HOLD_INTERVAL = timedelta(minutes=15)` (`C/_dispatcher_provider_exhaustion.py:45`).
  - The measured outages lasted for days: one reset at "Aug 27th" (observed Aug 23) and one at "Oct 16th" (observed Oct 10).
  - The spec forbids using the provider's reset time as the hold's expiry (contracts 4949–4952, 6653–6654).
  - So every expiry is followed by a real dispatch that re-discovers the outage by failing. Its cost is every node that runs before the first node on the held provider (D1).
  - Pre-dispatch detection exists only for Claude (`classify_claude_probe`, HTTP 402/429; `C/_dispatcher_credential_reprobe.py`). There is no Codex usage probe; the Codex gate checks token lifetime only (`C/_dispatcher_codex_credential_gate.py`). The spec allows a probe refusal to cause only an ephemeral skip, never a hold (6672–6679).
- **Is it avoidable?** Partly: a new terminal-failure hold-minting path, a longer committed bounded expiry, and a Codex usage probe. The engine-side design also re-probes after expiry, but that costs one refused turn inside a run that then continues.

### D6. The legacy exhaustion gate would block fallback dispatches — SIGNIFICANT (avoidable)

- **Evidence:**
  - MEASURED: `DISPATCH_PROVIDERS = ("anthropic", "codex")` is hard-coded (`C/_dispatcher_provider_exhaustion.py:36`).
  - MEASURED: `provider_exhaustion_refusal` runs first in every candidate's refusal ladder (`C/_dispatcher_admission_eligibility.py:150–158`) and refuses the item if either vendor holds a record, whatever the item's nodes would actually use.
  - INFERRED consequence: once D2 is fixed, a Codex hold would refuse an all-Claude fallback dispatch.
- **Is it avoidable?** Yes, by scoping the gate to the candidates actually selected. Note that it also bites the engine-side design if legacy records are minted.

### D7. The failed attempt's spend becomes invisible — MINOR to SIGNIFICANT

- **Evidence:**
  - MEASURED: contracts 3899–3905 say a run that did not succeed "yields no cost observation … even though such a run MAY have consumed spend". In the journal, `token_cost_micros` appears on exactly the 66 green runs and nowhere else.
  - v112's "every attempt" cost (6793–6808) therefore cannot be met within a run.
  - MEASURED: no rates exist for the Codex models this repo ran before PR 2766 (`gpt-5.6-sol`, `gpt-5.6-terra` are absent from `C/_acp_model_prices.py:54–60`).
- **Is it avoidable?** Partly: sum `total_usd_micros` across the item's runs (the field exists in `C/_fabro_port_records.py` `_run_summary`). It stays unobservable for unpriced models.

### D8. Holds are per repository, and in-flight runs race the hold — MINOR to SIGNIFICANT

- **Evidence:**
  - MEASURED: the journal is `repo/tmp/fabro-dispatch-journal.jsonl` (`C/_dispatcher_paths.py:129`). Each family repo learns about an outage by failing its own run.
  - MEASURED: the package forbids a sidecar store (`.claude-plugin/scripts/livespec_orchestrator_beads_fabro/CLAUDE.md:96`), so a host-wide hold is not allowed.
  - INFERRED: runs already in flight when the first one fails each fail independently, up to `wip_cap` 10.
- **Is it avoidable?** Partly, via a pre-dispatch probe. Engine-side holds are equally per repo, but each run there recovers on its own.

### D9. The engine retries the doomed node once before failing — MINOR

- **Evidence:**
  - MEASURED: every ACP node has `max_retries=1`, and the engine classifies the cap as `transient_infra`. The 2026-10-10 run shows `node_retries.disposition = 1`.
  - MEASURED: Petri also retries caps (research 004 table: "retry_requested on both").
  - Contracts 6919–6934 already accept "ONE wasted attempt".
  - The v112 engine design advances immediately on an eligible failure. The Dispatcher cannot prevent the retry.
- **Is it avoidable?** Only by an engine change or by `max_retries=0`.

### D10. Telling transient errors from outages — MINOR

- **Evidence:** MEASURED: Claude's multi-hour session limit and a true transient carry the same `errorKind: "rate_limit"` (journal 2026-10-09).
- **Risk:** INFERRED: a whole-run re-dispatch plus a provider cooldown is a heavy response to a 429 or a 5xx that the node retry would have absorbed. The classification has to separate the two. v112 also lists `rate_limit`, `provider_capacity` and `provider_server_unavailable` as eligible causes (6596–6598).

### D11. Re-dispatching resets the per-run review loop bound — MINOR, INFERRED

The `review<->review_fix` loop is bounded by per-run `max_visits=3` (`workflow.fabro:547–580`). A re-dispatched run starts with fresh rounds. No ledger counter of review rounds across runs was found.

### D12. Engine work is still needed for protocol-mechanism agents — MINOR

- **Evidence:**
  - MEASURED: opencode, grok-build and glm use `PROTOCOL_MECHANISM` (`C/_acp_agent_catalog.py:232–263`). These need the engine's `config_options` handling.
  - MEASURED: only `claude-acp` (env) and `codex-acp` (json-env) launch as a literal `acp.command` on both engines (research 007 a3; `C/_dispatcher_graph_adapters.py`).
- **Consequence:** Dispatcher-level fallback is effectively limited to Claude and Codex unless the engine work is also done. This is shared with the engine-side design.

### D13. Reviewer independence — MINOR; no real difference between the layers

- **Evidence, MEASURED:**
  - The `.livespec.jsonc` comments record that review was moved from Codex terra to Opus after three non-convergences (2026-08-28).
  - PR 2766 (merged 2026-10-11) already puts `implement` and `review` on the same `claude-opus-5`.
- **Comparison:** fallback in either layer can collapse the reviewer onto the implementer's model. The Dispatcher, which picks every node at once, could enforce a cross-node "differ from the implementer" rule; per-node engine fallback cannot (INFERRED). This is an advantage for the Dispatcher, not a downside.

### Context that is not a downside, so the comparison is fair

- **Picking a different adapter per node at dispatch time is mechanically cheap.** The Dispatcher already writes a literal per-node `acp.command` into the graph, and that works on both engines (MEASURED, `C/_dispatcher_graph_adapters.py`).
- **The preflight verdict and the hold ledger exist, but nothing uses them to pick a candidate.**
  - The resolved chains "have no consumer yet" (MEASURED, `C/_dispatcher_acp_nodes.py:166–170`).
  - Preflight only refuses when a chain is empty. I found no code that replaces the primary with the first eligible candidate (grep for selection or emission consumers). So dispatch-time selection is unbuilt.
  - No `acp_nodes` entry carries `fallbacks` today (MEASURED, `.livespec.jsonc`).

---

## (B) Downsides of the engine-side design (v112 as written)

### E1. It does not exist on the engine being moved to — BLOCKING for any near-term delivery

- **Evidence, MEASURED:**
  - Petri rejects `acp.fallback_chain`; `bd-ib-r5cnjd` was closed as deferred on 2026-10-08.
  - The `bd-ib-vuwrv5` correction of 2026-10-10 says the cutover does not add the capability.
  - Fabro-currency 008 §13 says Petri's ACP backend "selects one command".
  - Delivering it means a hand-built Petri fork carry plus an upstream PR, sequenced after the cutover (`bd-ib-iud52v`, pending approval). That runs against the maintainer's stay-current posture if upstream declines it (AGENTS.md "Host Fabro server").
  - The 0.254 implementation was one large commit, and its pre-merge clippy found thirteen errors (S4 record).

### E2. The shared deadline starves the successor candidate — SIGNIFICANT

- **Evidence:**
  - MEASURED: "Every candidate shares the node's original wall-clock deadline and receives only its remaining time" (contracts 6699–6701).
  - INFERRED: a quota that runs out two hours into a 4-hour `implement` leaves the fallback two hours. That is shorter than the recorded legitimate turns of about 120 minutes, which was the reason for the 14400 s override (`.livespec.jsonc`).

### E3. It fails closed after any external effect, which covers the late nodes — SIGNIFICANT, INFERRED

- **Evidence:** MEASURED spec text (6710–6721): missing or unknown onset evidence "terminates without fallback", and missing remote evidence counts as already past onset.
- **Consequence:** `proof_capture`, `proof_verify`, `disposition` and `review` run after `publish_draft` has pushed and opened the PR. I did not establish whether those nodes perform external effects themselves; if they do, they may never fall back. That is exactly where the 2026-10-10 exhaustion struck.

### E4. Every candidate's credentials are projected into every run — MINOR to SIGNIFICANT, INFERRED

- Contracts 6500–6502: "Container-level credentials remain shared". So a Codex fallback forces the Codex credential into every run.
- The Codex freshness gate sits on the dispatch path with no node condition (`C/_dispatcher_pre_dispatch_wall.py:204`). A stale Codex token can therefore refuse a dispatch whose primary is Claude.

### E5. Unpriced models flip runs to cost-unobservable — MINOR to SIGNIFICANT

- MEASURED: rider 3 on `bd-ib-vuwrv5`.
- MEASURED: `gpt-5.6-*` is absent from `C/_acp_model_prices.py`.

### E6. Same signature gaps as D2(b)–(d) — SIGNIFICANT

The Dispatcher renders the signature table for the engine too, so the engine inherits the missing session-limit literal and the Anthropic "You've hit your limit" form.

### E7. Per-node fallback is uncoordinated — MINOR

It can place `review` and `implement` on the same model, and nothing can see across nodes to prevent it.

### E8. Re-porting cost — SIGNIFICANT, INFERRED

The event-projection code (S5/S6) is keyed on 0.254's `agent.acp.failover`. Petri's event shapes differ (research 004 `step.finished`), so the engine fork and the projection both need re-porting.

---

## (C) Facts I could not establish

- **Whether Petri can resume a run from a checkpoint with a changed adapter.** No measurement found; fabro-currency 008 discusses retained-workspace recovery only for the Kubernetes backend.
- **Whether edge conditions on 0.254 or Petri can branch on failure class**, so that provider-class failures avoid `needs_human`. I saw only `outcome=` and `preferred_label=` conditions; research 007 p3c says outcome conditions work on Petri.
- **What Petri's `inspect` shows for a real (not fake) adapter quota failure routed through `needs_human`.** D2(e) is inferred from p6.
- **Per-node `implement` durations.** The journal's inspect detail is truncated at 2000 chars, and calibration records carry only run wall time.
- **Behaviour in other repos' journals during the 2026-10-11 outage.** Only this repo's journal was read. In it, the latest Codex usage-limit run was 2026-10-10.
- **Whether every `drive` and `dispatch` invocation from a worktree writes the primary's journal.** I saw `journal_path` = `repo/tmp`, but did not trace each entry point's `--repo`.
- **Whether a Codex refusal always arrives at the first `session/prompt`.** The 2026-10-10 case refused at a node's first prompt about 2 minutes into the run. I did not measure the latency of a fresh-session refusal.
- **Whether `review`, `disposition`, `proof_capture` or `proof_verify` perform external effects themselves.** E3 depends on it, and I did not trace those prompts.

**Searched:**
- spec v112 sections and Scenario 127;
- `C/` modules for ACP, fallback, holds, exhaustion, failure parsing, resume, credential gates and admission;
- the workflow graph;
- `.livespec.jsonc`;
- `tmp/fabro-dispatch-journal.jsonl` (73,363 lines; Oct 9–11 outcomes; all "usage limit", "session limit" and `usage_limit_exceeded` records);
- one read-only `fabro inspect` against hp;
- fabro-currency research 004, 007 and 008;
- the fallback plan's S4 record;
- ledger items `bd-ib-vuwrv5`, `bd-ib-r5cnjd`, `bd-ib-jxvgq5` (latest comments), `bd-ib-iud52v` and `bd-ib-egms32`;
- PR 2766.
