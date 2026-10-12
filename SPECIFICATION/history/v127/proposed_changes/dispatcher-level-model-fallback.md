---
topic: dispatcher-level-model-fallback
author: claude-opus-5-5-spec-dispatcher-fallback
created_at: 2026-10-12T07:49:04Z
---

## Proposal: Fallback chain is consumed by the Dispatcher, and the engine capability gate is retired

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Restate the opening of the fallback section so the ordered candidate chain is consumed by the Dispatcher at every dispatch and re-dispatch (one literal adapter rendered per node, the first unheld candidate), and retire the requirement that the resolved Fabro server advertise a fallback-chain capability, which on Petri would refuse every fallback configuration.

### Motivation

Maintainer decision of 2026-10-12: ordered model fallback moves from the Fabro ENGINE (cross-candidate fallback inside one node visit, rendered as the `acp.fallback_chain` node attribute) to the DISPATCHER. Upstream Fabro re-platformed onto the Petri engine, which rejects `acp.fallback_chain` as `attractor.unknown_attribute` and has no equivalent (`plan/fabro-currency/research/001-currency-assessment-2026-09-30.md`; `plan/fabro-currency/research/002-fork-hygiene-and-carrier-inventory-2026-09-30.md`, row 23; `plan/fabro-currency/research/003-local-candidate-assessment-2026-10-01.md`); the 0.254 fork that implements the engine handler is retired at the Petri cutover (ledger bd-ib-iud52v), and bd-ib-r5cnjd (the Petri carry) was closed deferred on 2026-10-08. The maintainer's stated priority is to PREVENT STALLS and AVOID UNNECESSARY DELEGATION TO A HUMAN; lost work is acceptable when the system recovers on its own. The forcing incident: on 2026-10-11 the Codex subscription ran out of usage for hours and every node had to be rerouted by hand (PR 2766). A second measured instance: run 01M4J5M63APH75NJ1JF7ZCN9DY on 2026-10-10 failed `disposition` on Codex with "You've hit your usage limit", was retried once by the engine, and rested the item at blocked / needs-human waiting on a person. Evidence and the full downside comparison of the two layers is the 2026-10-12 investigation report committed at `plan/factory-configurable-model-fallback-priority/research/dispatcher-fallback-downsides-2026-10-12.md` (findings D1-D13 and E1-E8; every D-numbered or E-numbered finding cited in this proposal, and the measured counts it quotes, resolve to that file).

Today the capability sentence makes every new-grammar dispatch refuse on an engine that never advertises `acp.fallback_chain.v1` (code: `_acp_capability_gate.py`). The Dispatcher already writes a literal per-node `acp.command` into the graph and that works on both engines (`_dispatcher_graph_adapters.py`), so Dispatcher-level selection needs no engine capability.

### Proposed Changes

Heading: contracts.md §"Factory-configurable ACP fallback priority" (opening paragraphs).

Edit 1 — replace this current text:

> An ACP node MAY carry an ordered, provider-generic candidate chain so an
> observed allowance outage or exact model removal does not make one configured
> adapter a single point of failure.

with:

> An ACP node MAY carry an ordered, provider-generic candidate chain so an
> observed allowance outage or exact model removal does not make one configured
> adapter a single point of failure. The Dispatcher, not the Fabro engine,
> consumes the chain: at every dispatch and every re-dispatch it MUST render, for
> each ACP node, exactly ONE candidate as that node's literal adapter — the first
> candidate in configured order that no unexpired observed hold covers, selected
> as "Preflight consumes versioned observed holds" below specifies — and the
> engine runs that one adapter with no knowledge of the other candidates. Ordered
> fallback therefore happens BETWEEN runs, through "Provider-limit release and
> re-dispatch" below, never inside one node visit.

(The rest of that paragraph, from "This is an additive configuration feature:" through "the remote Git onset predicate does not apply to it.", stays, except that the final sentence's clause "so the remote Git onset predicate does not apply to it" is deleted together with the remote-onset rule it refers to — see the finding that removes the same-visit paragraphs.)

Edit 2 — replace this current text:

> A new-grammar-enabled
> dispatch MUST also refuse before claim when the Dispatcher or pinned Fabro build
> does not advertise this capability.

with:

> Because the Dispatcher renders exactly one literal adapter per node, a
> new-grammar-enabled dispatch requires NO Fabro engine capability for fallback.
> The Dispatcher MUST NOT refuse a dispatch because the resolved factory server
> does not advertise a fallback-chain capability; the only engine capability gate
> that remains is the `config_options` gate of "In-protocol model and effort
> selection" below.

Edit 3 — in the paragraph beginning '"New-grammar-enabled" means', replace this current text:

> The
> enabling repository MUST commit `dispatcher.minimum_release` at or above the
> first fallback-capable plugin release;

with "The enabling repository MUST commit `dispatcher.minimum_release` at or above the first plugin release that implements Dispatcher-level fallback;", and replace this current text:

> Fabro capability is
> read from the dispatch's resolved factory server, never a local binary.

with "Any remaining engine capability (the `config_options` gate) is read from the dispatch's resolved factory server, never a local binary."


## Proposal: Signature matching reads the Dispatcher-visible failure, and built-in provider-limit mappings cover every measured form

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Move availability-signature matching to the failure the Dispatcher can read from the run record on the resolved factory (structured payload where the engine keeps it, the message text where only it survives, the failing node's own record when the needs_human terminal replaced the terminal message), and require the built-in Claude and Codex candidates, and the model catalog, to carry measured mappings for every provider-limit form observed: Claude session limit, generic limit, usage limit and org spend limit; Codex camelCase `codexErrorInfo` and snake_case `codex_error_info` usage-limit fields and their message forms.

### Motivation

Maintainer decision of 2026-10-12: ordered model fallback moves from the Fabro ENGINE (cross-candidate fallback inside one node visit, rendered as the `acp.fallback_chain` node attribute) to the DISPATCHER. Upstream Fabro re-platformed onto the Petri engine, which rejects `acp.fallback_chain` as `attractor.unknown_attribute` and has no equivalent (`plan/fabro-currency/research/001-currency-assessment-2026-09-30.md`; `plan/fabro-currency/research/002-fork-hygiene-and-carrier-inventory-2026-09-30.md`, row 23; `plan/fabro-currency/research/003-local-candidate-assessment-2026-10-01.md`); the 0.254 fork that implements the engine handler is retired at the Petri cutover (ledger bd-ib-iud52v), and bd-ib-r5cnjd (the Petri carry) was closed deferred on 2026-10-08. The maintainer's stated priority is to PREVENT STALLS and AVOID UNNECESSARY DELEGATION TO A HUMAN; lost work is acceptable when the system recovers on its own. The forcing incident: on 2026-10-11 the Codex subscription ran out of usage for hours and every node had to be rerouted by hand (PR 2766). A second measured instance: run 01M4J5M63APH75NJ1JF7ZCN9DY on 2026-10-10 failed `disposition` on Codex with "You've hit your usage limit", was retried once by the engine, and rested the item at blocked / needs-human waiting on a person. Evidence and the full downside comparison of the two layers is the 2026-10-12 investigation report committed at `plan/factory-configurable-model-fallback-priority/research/dispatcher-fallback-downsides-2026-10-12.md` (findings D1-D13 and E1-E8; every D-numbered or E-numbered finding cited in this proposal, and the measured counts it quotes, resolve to that file).

Measured detection gaps (investigation D2): Claude's 5-hour "You've hit your session limit · resets 3:40am (UTC)" with errorKind rate_limit was classified transient_infra with provider null on 2026-08-23, 2026-09-09 (twice) and 2026-10-09; neither `_fabro_port_permanent_failure.py`'s hint list nor `_acp_builtin_signatures.py` (Anthropic: only "monthly spend limit") matches it. The October Codex payload carries `"codexErrorInfo": "usageLimitExceeded"` while the code looks only for snake_case `codex_error_info: usage_limit_exceeded`. On Petri the structured `data` payload is gone and only `failure.detail.message` survives (plan/fabro-currency/research/004-acp-spend-limit-evidence.json), where the Anthropic text is "You've hit your limit · resets ...", which no hint matches. Of October's provider-limit failures in this repository's journal, the existing detection labelled zero.

### Proposed Changes

Heading: contracts.md §"Factory-configurable ACP fallback priority".

Edit 1 — replace this current text:

> Text matching is a conjunction after Unicode case-folding and whitespace
> normalization, never a regular expression. It reads only the named ACP protocol
> field or separately captured terminal adapter startup/termination diagnostic,
> never an arbitrary exec-output tail, agent response, prompt, tool/test/review
> output, or run log. Structured machine codes take precedence. Authentication,
> command-not-found, cancellation, node deadline or stall expiry, generic HTTP
> 400/404, remote-compaction 404, malformed command/configuration, signal exit,
> unattributed sandbox/DNS/transport failure, code/test/review/tool failure, and
> non-convergence are non-eligible before configured matching and MUST terminate
> with their original identity. A mere pre-turn failure is not provider evidence.

with:

> Text matching is a conjunction after Unicode case-folding and whitespace
> normalization, never a regular expression. The Dispatcher applies signatures to
> the failing node's recorded failure as read from the run's resolved factory:
> a `protocol.machine_code` signature matches only where the engine preserved the
> provider's structured payload; a `protocol.message` signature matches the
> provider's message text, including the engine form that preserves ONLY the
> failure message text and no structured payload; a `process.terminal_diagnostic`
> signature matches the separately captured adapter startup/termination
> diagnostic. When the run ended at the workflow's `needs_human` terminal and the
> terminal message no longer carries the provider's sentence, the Dispatcher MUST
> read the failing node's own recorded attempt outcome before classifying, and
> MUST NOT classify from the needs-human script's own output. Matching never reads
> an arbitrary exec-output tail, agent response, prompt, tool/test/review output,
> or run log. Structured machine codes take precedence. Authentication,
> command-not-found, cancellation, node deadline or stall expiry, generic HTTP
> 400/404, remote-compaction 404, malformed command/configuration, signal exit,
> unattributed sandbox/DNS/transport failure, code/test/review/tool failure, and
> non-convergence are non-eligible before configured matching: they mint no hold,
> are not released for re-dispatch, and keep their original identity and their
> existing route. A mere pre-turn failure is not provider evidence.

Edit 2 — replace this current text:

> Built-in Claude and Codex candidates MUST carry exact, measured mappings for
> stable diagnostics exposed by the pinned adapters, including the recorded
> ChatGPT-account diagnostic that names the requested model as unsupported. The
> generic HTTP 400 remains non-eligible; the exact model-naming discriminator is
> candidate-scoped.

with:

> Built-in Claude and Codex candidates MUST carry exact, measured mappings for
> stable diagnostics exposed by the pinned adapters, including the recorded
> ChatGPT-account diagnostic that names the requested model as unsupported. The
> generic HTTP 400 remains non-eligible; the exact model-naming discriminator is
> candidate-scoped. Every provider-limit mapping MUST exist as a
> `protocol.message` signature, and additionally as a `protocol.machine_code`
> signature where the adapter emits a structured token, so that detection survives
> an engine that keeps only message text. The measured minimum set at this
> ratification, each `cause: quota` and `scope: availability-domain`, is: for
> `claude-acp`, the session-limit form (literals `hit your session limit`), the
> generic limit form (literals `hit your limit` and `resets`), the usage-limit form
> (literals `hit your usage limit`), and the organisation spend-limit form
> (literals `org` and `spend limit`); for `codex-acp`, the structured usage-limit
> field in BOTH its camelCase spelling (`codexErrorInfo` carrying
> `usageLimitExceeded`) and its snake_case spelling (`codex_error_info` carrying
> `usage_limit_exceeded`), and the message forms (literals `hit your usage limit`;
> literals `usage limit exceeded`). A Claude structured `errorKind` of
> `rate_limit` is NOT by itself evidence of a multi-hour ceiling; the session-limit
> literal decides it. A newly measured provider-limit form is added to this set by
> a committed change to the built-in signatures or the model catalog, never by
> loosening a literal into a broader match.

(The remainder of that paragraph, from "Every Codex primary or fallback continues to obey the v107" onward, is replaced by: "Every Codex primary or fallback continues to obey the v107 pin, posture, baked-path, and empty-model opt-out rules. Consequently the v107 reachability statement is narrowed: an unreachable pin is a failure of that candidate; when its exact typed cause is eligible it mints a candidate hold and the item is released for re-dispatch to the next unheld candidate, and otherwise it keeps its existing route. Verification-run guidance applies to every new or changed candidate.")

Heading: contracts.md §"Agent and model catalogs" — replace this current text:

> **The model catalog.** Entries are keyed by `provider/model` and carry the
> canonical model id, aliases, the four USD-per-million prices in the `pricing`
> shape of §"Factory-configurable ACP fallback priority", and measured
> availability signatures in that section's signature grammar. It MUST be seeded
> from upstream Fabro's model catalog where that catalog carries the model and
> extended for models it does not, including the ratified Codex ChatGPT-account
> diagnostic.

with:

> **The model catalog.** Entries are keyed by `provider/model` and carry the
> canonical model id, aliases, the four USD-per-million prices in the `pricing`
> shape of §"Factory-configurable ACP fallback priority", and measured
> availability signatures in that section's signature grammar, including a
> `protocol.message` form for every provider-limit diagnostic it carries. It MUST
> be seeded from upstream Fabro's model catalog where that catalog carries the
> model and extended for models it does not, including the ratified Codex
> ChatGPT-account diagnostic.

(The pricing-override sentence that follows in that paragraph is the subject of the pending proposal `acp-pricing-precedence`; this proposal aligns with it and does not change that sentence.)

Heading: contracts.md §"Built-in ACP node defaults" — replace this current text:

> A pin naming an unreachable model terminates that candidate; only
> an exact eligible diagnostic may advance an explicitly configured chain under
> §"Factory-configurable ACP fallback priority". Without such a chain it still
> fails every dispatch that uses it.

with:

> A pin naming an unreachable model fails that candidate. When the failure
> carries an exact eligible diagnostic, the Dispatcher mints a candidate-scoped
> hold and re-dispatches the item to the next unheld candidate of an explicitly
> configured chain under §"Factory-configurable ACP fallback priority"; without a
> further candidate the item waits under that section rather than failing every
> dispatch, and without an eligible diagnostic the failure keeps its existing
> route.


## Proposal: Holds: sources, per-provider scoping, host-wide visibility from the dispatch journals, and per-node selection

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Restate where a hold may come from (a classified failed node of a terminal run of any terminal, or a refused availability probe turn — no longer a projected engine failover event), require that holds are stored only in the dispatch journal and made visible host-wide by reading peer repositories' journals named in a committed key, forbid a hold on one provider from refusing a dispatch whose candidates are wholly on another, and replace the reached-node termination rule with Dispatcher-side per-node selection.

### Motivation

Maintainer decision of 2026-10-12: ordered model fallback moves from the Fabro ENGINE (cross-candidate fallback inside one node visit, rendered as the `acp.fallback_chain` node attribute) to the DISPATCHER. Upstream Fabro re-platformed onto the Petri engine, which rejects `acp.fallback_chain` as `attractor.unknown_attribute` and has no equivalent (`plan/fabro-currency/research/001-currency-assessment-2026-09-30.md`; `plan/fabro-currency/research/002-fork-hygiene-and-carrier-inventory-2026-09-30.md`, row 23; `plan/fabro-currency/research/003-local-candidate-assessment-2026-10-01.md`); the 0.254 fork that implements the engine handler is retired at the Petri cutover (ledger bd-ib-iud52v), and bd-ib-r5cnjd (the Petri carry) was closed deferred on 2026-10-08. The maintainer's stated priority is to PREVENT STALLS and AVOID UNNECESSARY DELEGATION TO A HUMAN; lost work is acceptable when the system recovers on its own. The forcing incident: on 2026-10-11 the Codex subscription ran out of usage for hours and every node had to be rerouted by hand (PR 2766). A second measured instance: run 01M4J5M63APH75NJ1JF7ZCN9DY on 2026-10-10 failed `disposition` on Codex with "You've hit your usage limit", was retried once by the engine, and rested the item at blocked / needs-human waiting on a person. Evidence and the full downside comparison of the two layers is the 2026-10-12 investigation report committed at `plan/factory-configurable-model-fallback-priority/research/dispatcher-fallback-downsides-2026-10-12.md` (findings D1-D13 and E1-E8; every D-numbered or E-numbered finding cited in this proposal, and the measured counts it quotes, resolve to that file).

Typed holds are created today only from projected `agent.acp.failover` events (`hold_observation_record(` is called only at `_acp_event_projection.py`), which do not exist on Petri, so the terminal-failure route must be the primary source. The dispatch journal is per repository (`repo/tmp/fabro-dispatch-journal.jsonl`), so each family repository today learns of an outage by failing its own run (D8); the package forbids a sidecar store (`.claude-plugin/scripts/livespec_orchestrator_beads_fabro/CLAUDE.md`), hence peer-journal reads. The existing gate that refuses EVERY dispatch while either anthropic or codex holds a legacy record is `provider_exhaustion_refusal` in `_dispatcher_admission_eligibility.py`, iterating the hard-coded `DISPATCH_PROVIDERS = ("anthropic", "codex")` of `_dispatcher_provider_exhaustion.py`; it runs first in every candidate's refusal ladder whatever the item's nodes would use (D6). The ratified legacy-record coverage text already limits a legacy record to candidates whose compatibility alias names that provider; this proposal makes the cross-provider prohibition explicit so the gate is unambiguously non-conforming. The reached-node termination rule (`reached_node_termination`) has no caller and is an in-run engine behaviour that the Dispatcher cannot perform.

### Proposed Changes

Heading: contracts.md §"Factory-configurable ACP fallback priority" → paragraph "**Preflight consumes versioned observed holds.**".

Edit 1 — replace this current text:

> A hold MUST come from an actual candidate attempt: a typed terminal failure or
> an idempotently projected `agent.acp.failover` event from a run of any eventual
> outcome. Expiry is computed from occurrence time and never from ingestion. No
> hold may come from credentials, catalogs, host probes, predicted health, price,
> model strength, or provider reset claims. The Dispatcher MUST retain configured
> order after filtering.

with:

> A hold MUST come from an actual candidate attempt: a typed eligible failure
> classified from a failed node of a terminal run, whichever terminal the run
> reached, or a refused availability probe turn (see "Availability is
> re-confirmed after expiry" below), which runs the candidate's own adapter and
> is therefore an actual attempt. Expiry is computed from occurrence time and
> never from ingestion. No hold may come from credentials, catalogs, the
> admission-time credential-usability probe, predicted health, price, model
> strength, or provider reset claims. The Dispatcher MUST retain configured order
> after filtering.
>
> **Holds are per provider domain, stored only in the substrate, and visible
> host-wide.** A domain hold keyed on a provider allowance's `availability_key`
> is the per-provider hold; a candidate hold keys on the exact identity pair.
> Every hold record MUST be appended to the dispatch journal of the repository
> whose run or probe observed it; no sidecar file, cache, or separate store MAY
> hold or mirror it. Each Dispatcher's preflight MUST read current hold records
> from its own dispatch journal AND from the dispatch journal of every repository
> listed in the committed-configuration-only key
> `dispatcher.hold_peer_repositories` (an array of absolute primary-checkout paths
> on the same host; default empty), so one repository's observation spares every
> listed repository the same failed attempt. Reading a peer journal for hold
> records is not counted-claim bookkeeping and is not governed by the
> tenant-scope clause of §"Host concurrency belongs to the Fabro scheduler". A
> peer journal that cannot be read MUST be surfaced as one
> `hygiene:hold-peer-unreadable:<repo>:<peer>` fact on the existing `hygiene`
> kind at `high` urgency, carrying the peer path and the read error, and MUST NOT
> refuse or delay a dispatch: the cost of that blind spot is at most one
> provider-limit attempt, which itself mints a local hold. A hold, current or
> legacy, MUST NOT refuse, delay, or re-route a dispatch whose resolved
> candidates are all outside its coverage; in particular no gate MAY refuse every
> dispatch because some provider holds a record.

Edit 2 — replace this current text:

> A conditional repair
> or adjudication node may have an empty filtered chain at preflight, but if
> reached it MUST terminate the run before starting an adapter with the typed
> availability cause surfaced. It MUST NOT traverse a continuation/failure edge
> into janitor, non-convergence, or `needs_human`, and the Dispatcher MUST NOT
> reclassify it as deterministic work failure.

with:

> A conditional repair or adjudication node may have an empty filtered chain at
> preflight; the Dispatcher then renders for it the candidate whose covering hold
> expires earliest, configured order breaking ties, and if that node is reached
> and the provider still refuses, the failure takes "Provider-limit release and
> re-dispatch" like any other. When a success-critical chain is empty the item
> WAITS: it is not claimed, it stays `ready`, it is not marked `blocked`, and the
> Dispatcher schedules its next admission evaluation at the earliest expiry among
> the holds that empty the chain (that evaluation is then subject to "Availability
> is re-confirmed after expiry"). No human valve is the remedy for that wait.
> Per-node selection is made once per dispatch from one consistent read of the
> holds and is journaled per node with the selected candidate index and identity,
> the full-chain digest, the primary-generation fingerprint, and the holds that
> skipped earlier candidates; that record contains no command, env value,
> credential, prompt, raw error, or unredacted diagnostic.

(The sentences that follow — "An unsupported or ambiguous workflow graph MUST refuse fallback-enabled dispatch instead of guessing. Idle-factory and wait attention consume this identical verdict." — stay.)

Edit 3 — in the paragraph beginning "Bounded expiry, later matching execution, and operator clearance", replace this current text:

> A successful fallback MUST NOT clear its skipped or failed primary, even
> when the whole run succeeds.

with "A re-dispatched run that succeeds on a fallback candidate MUST NOT clear the held primary, even when the whole run succeeds."


## Proposal: Replace same-visit reactive fallback with provider-limit release, re-dispatch from the preserved tree, and post-expiry probing

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Delete the three engine-side paragraphs (one bounded node visit; shared deadline and non-retryable post-transition state; sandbox-local partial-write hand-off with the side-effect onset ledger) and replace them with: provider-limit release (record the hold, release the item to ready, re-dispatch to the first unheld candidate per node; wait with a scheduled retry when a required chain is empty; only unclassifiable failures keep the human route), re-dispatch from the failed run's preserved tree, and a cheap availability probe turn after a hold expires.

### Motivation

Maintainer decision of 2026-10-12: ordered model fallback moves from the Fabro ENGINE (cross-candidate fallback inside one node visit, rendered as the `acp.fallback_chain` node attribute) to the DISPATCHER. Upstream Fabro re-platformed onto the Petri engine, which rejects `acp.fallback_chain` as `attractor.unknown_attribute` and has no equivalent (`plan/fabro-currency/research/001-currency-assessment-2026-09-30.md`; `plan/fabro-currency/research/002-fork-hygiene-and-carrier-inventory-2026-09-30.md`, row 23; `plan/fabro-currency/research/003-local-candidate-assessment-2026-10-01.md`); the 0.254 fork that implements the engine handler is retired at the Petri cutover (ledger bd-ib-iud52v), and bd-ib-r5cnjd (the Petri carry) was closed deferred on 2026-10-08. The maintainer's stated priority is to PREVENT STALLS and AVOID UNNECESSARY DELEGATION TO A HUMAN; lost work is acceptable when the system recovers on its own. The forcing incident: on 2026-10-11 the Codex subscription ran out of usage for hours and every node had to be rerouted by hand (PR 2766). A second measured instance: run 01M4J5M63APH75NJ1JF7ZCN9DY on 2026-10-10 failed `disposition` on Codex with "You've hit your usage limit", was retried once by the engine, and rested the item at blocked / needs-human waiting on a person. Evidence and the full downside comparison of the two layers is the 2026-10-12 investigation report committed at `plan/factory-configurable-model-fallback-priority/research/dispatcher-fallback-downsides-2026-10-12.md` (findings D1-D13 and E1-E8; every D-numbered or E-numbered finding cited in this proposal, and the measured counts it quotes, resolve to that file).

Every ACP node has an `outcome=failed -> needs_human` edge (`.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro`), and `_needs_human_terminal_outcome` in `_dispatcher_fabro_terminal.py` maps that terminal to the `blocked` outcome with no provider attribution and the remedy `resolve-blocked:<id>:ready` — so every provider-limit failure today waits on a human (D2a, D3). The legacy hold interval is 15 minutes (`_HOLD_INTERVAL` in `_dispatcher_provider_exhaustion.py`) while measured outages lasted days, and the spec forbids adopting the provider's reset time, so without a probe every expiry is followed by a real dispatch that re-discovers the outage by failing (D5). A plain re-dispatch starts at implement and throws the failed run's tree away (D1); the resume path and preserved references already exist (§"Resume from a published pull request", the needs-human ref, the publish-branch reclaim's run-scoped ref). The engine-side paragraphs cannot be met on Petri (E1) and carried their own costs (shared deadline starving the successor, E2; fail-closed after any external effect, which covers the late nodes where the 2026-10-10 exhaustion struck, E3).

### Proposed Changes

Heading: contracts.md §"Factory-configurable ACP fallback priority".

Edit 1 — delete this current text in full (three paragraphs):

> **Reactive fallback is one bounded node visit.** The externally observable
> integration is one run id, one sandbox identity, one node deadline, no
> predecessor-node replay, ordered candidate attempts, and normal workflow
> continuation on success. The Fabro repository owns the internal handler and this
> repository consumes a capability-bearing pinned release. The scope boundary in
> §"Provider-limit permanence and root-cause surfacing" is narrowed only for this explicit integration:
> that section still does not govern Fabro generally, but the fallback-enabled
> node MUST exhibit these observables.
>
> Every candidate shares the node's original wall-clock deadline and receives
> only its remaining time; timeout derivation MUST remain one node timeout, never
> candidate count multiplied by timeout. Within one engine handler attempt each
> candidate is tried at most once in order. `engine_attempt` and
> `candidate_index` are distinct. Before any failover, an existing outer retry for
> a non-eligible transient failure MAY retry the preflight-selected candidate.
> After the first reactive transition the node visit is non-retryable: neither an
> outer retry nor checkpoint/resume may replay any attempted or skipped candidate.
> The attempted set, original deadline, and event ids MUST survive resume.
> Exhaustion is a typed, non-retryable node outcome preserving the final cause.
>
> Sandbox-local partial changes MAY pass to the successor with the original task
> and a delimited recovery preamble that names the interrupted attempt and
> requires inspection of current state. This is permitted only with durable proof
> that every completed tool operation was sandbox-local and no external effect
> began. A side-effect ledger MUST write onset before issuing an external mutation;
> missing, incomplete, or unknown evidence is fail-closed and terminates without
> fallback. Transition after onset additionally requires declared durable
> idempotent/resumable semantics plus the idempotency key, resume identity, and
> observed remote state. The scripted publication stages have no adapter fallback. For any ACP node
> performing external effects, missing or unreadable remote evidence MUST be
> treated as already past onset; converting publication to commands does not
> relax this rule for agent stages.

and insert in its place:

> **Provider-limit release and re-dispatch.** When a run terminates — through
> any terminal, the workflow's `needs_human` terminal included — and the failing
> node's recorded failure classifies under this section's signatures as an
> eligible cause, the Dispatcher MUST, in this order and without a human:
> (1) append the hold that failure observed, scoped and keyed as the matching
> signature declares; (2) journal one `provider-limit-release` record naming the
> work-item, run id, factory, failing node, matched cause, scope and hold key,
> the candidate identity that failed, and the preserved tree reference below;
> (3) release the item's dispatch claim and return it to `ready`, NOT to
> `blocked` and with no `blocked_reason`; and (4) leave the item to the ordinary
> admission valve, which re-dispatches it with every node selected afresh as
> "Preflight consumes versioned observed holds" specifies. When every
> success-critical chain still retains a candidate the re-dispatch is admitted on
> the next pass; when any is empty the item waits with its next evaluation
> scheduled at the earliest covering expiry. A provider-limit release MUST NOT
> consume any budget of §"The three rework caps", MUST NOT count as an
> item-attributable terminal under §"Across-dispatch required-result progress",
> and MUST NOT be surfaced as a needs-human decision. Only a failure the
> Dispatcher cannot classify as eligible keeps its existing route, including the
> `blocked / needs-human` rest of §"A factory run never awaits a human".
>
> **A re-dispatch starts from the failed run's preserved tree.** When the failed
> run published a pull request whose latest proof record anchors §"Resume from a
> published pull request (`resume --item`)", the re-dispatch MUST take that
> resume path, with its resumed-at stage derivation, instead of a plain dispatch;
> the Dispatcher invokes it itself and journals it under its own invoker
> identity. Otherwise, when the failed run preserved its work by reference — its
> `refs/heads/needs-human/<run>` ref, its pushed publish branch, or the run-scoped
> ref that §"Stale publish-branch reclaim before a re-dispatch" preserves — the
> re-dispatch MUST seed its working tree from that reference's head rather than
> from the default-branch tip, and the goal brief MUST name that reference as an
> interrupted prior attempt whose current state the agent inspects before
> continuing. The publish-branch reclaim MUST preserve the seeding reference
> before it deletes any branch. When no preserved reference exists the
> re-dispatch is a plain dispatch and the failed run's work is accepted as lost.
>
> **Availability is re-confirmed after expiry.** When a domain or candidate hold
> reaches its bounded expiry, the Dispatcher MUST NOT route a real dispatch to a
> candidate that hold covered until an availability probe turn has completed for
> that candidate. The probe turn runs the candidate's exact rendered adapter
> bytes under the same projected worker credential a sandbox receives — on the
> host or in a minimal factory run; either is conforming when the bytes and the
> credential are identical — sends one fixed minimal prompt, and is bounded by
> the committed-configuration-only `dispatcher.availability_probe_timeout_seconds`
> (positive integer, default **120**). A probe that completes its turn makes the
> candidate eligible; a probe whose failure classifies as an eligible cause mints
> a fresh hold whose bounded expiry runs from the probe's occurrence time; any
> other probe failure leaves the candidate ineligible for that evaluation, mints
> no hold, and is surfaced as a `hygiene` fact naming the candidate and the
> failure. Every probe turn is journaled with the candidate identity, outcome,
> occurrence time and, where observable, its cost. A provider's own advertised
> reset instant MUST NOT schedule, shorten, or replace the probe; it MAY be
> recorded only as unverified provenance. The probe turn is not the
> admission-time credential-usability probe of §"Provider spend containment" and
> changes none of that probe's rules.
>
> No engine-side same-visit fallback is required. Should a pinned Fabro engine
> later expose a supported extension point for trying a further candidate within
> one node visit, using it is an optional optimisation that requires its own
> ratified change; this section neither requires nor forbids it.


## Proposal: Decouple in-protocol model and effort selection from the fallback-chain capability

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Keep the `config_options` requirement for protocol-mechanism agents but attach it to the single rendered node adapter rather than to a rendered chain candidate, gate it only on its own `acp.candidate_config_options.v1` capability, and replace "never triggering reactive fallback" with the Dispatcher-level equivalent.

### Motivation

Maintainer decision of 2026-10-12: ordered model fallback moves from the Fabro ENGINE (cross-candidate fallback inside one node visit, rendered as the `acp.fallback_chain` node attribute) to the DISPATCHER. Upstream Fabro re-platformed onto the Petri engine, which rejects `acp.fallback_chain` as `attractor.unknown_attribute` and has no equivalent (`plan/fabro-currency/research/001-currency-assessment-2026-09-30.md`; `plan/fabro-currency/research/002-fork-hygiene-and-carrier-inventory-2026-09-30.md`, row 23; `plan/fabro-currency/research/003-local-candidate-assessment-2026-10-01.md`); the 0.254 fork that implements the engine handler is retired at the Petri cutover (ledger bd-ib-iud52v), and bd-ib-r5cnjd (the Petri carry) was closed deferred on 2026-10-08. The maintainer's stated priority is to PREVENT STALLS and AVOID UNNECESSARY DELEGATION TO A HUMAN; lost work is acceptable when the system recovers on its own. The forcing incident: on 2026-10-11 the Codex subscription ran out of usage for hours and every node had to be rerouted by hand (PR 2766). A second measured instance: run 01M4J5M63APH75NJ1JF7ZCN9DY on 2026-10-10 failed `disposition` on Codex with "You've hit your usage limit", was retried once by the engine, and rested the item at blocked / needs-human waiting on a person. Evidence and the full downside comparison of the two layers is the 2026-10-12 investigation report committed at `plan/factory-configurable-model-fallback-priority/research/dispatcher-fallback-downsides-2026-10-12.md` (findings D1-D13 and E1-E8; every D-numbered or E-numbered finding cited in this proposal, and the measured counts it quotes, resolve to that file).

In-protocol model selection is needed by opencode, grok-build and glm (PROTOCOL_MECHANISM in `_acp_agent_catalog.py`) whichever layer performs fallback (investigation D12); only its coupling to `acp.fallback_chain.v1` and to reactive fallback is obsolete.

### Proposed Changes

Heading: contracts.md §"Factory-configurable ACP fallback priority" → paragraph "**In-protocol model and effort selection.**".

Replace this current text:

> **In-protocol model and effort selection.** For a candidate whose agent catalog
> entry declares the `protocol` mechanism, the rendered chain candidate MUST carry

with "**In-protocol model and effort selection.** For a candidate whose agent catalog entry declares the `protocol` mechanism, the node adapter the Dispatcher renders for that candidate MUST carry";

replace this current text:

> recorded with its own identity, minting no hold, and never
> triggering reactive fallback.

with "recorded with its own identity, minting no hold, and never released for re-dispatch as a provider-limit failure; it keeps its existing route.";

and replace this current text:

> The Fabro server MUST advertise the additive capability
> `acp.candidate_config_options.v1` alongside `acp.fallback_chain.v1`, and the
> Dispatcher MUST refuse before claim a chain carrying `config_options` when the
> resolved factory server does not advertise it, exactly as the existing
> capability gate does.

with:

> The Fabro server MUST advertise the additive capability
> `acp.candidate_config_options.v1`, and the Dispatcher MUST refuse before claim a
> dispatch that renders `config_options` for any node when the resolved factory
> server does not advertise it.


## Proposal: Retire engine failover events and their projection; source the model-fallback warning from Dispatcher selection

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Delete the `agent.acp.failover` event contract, its server-qualified projection, the `hygiene:model-fallback-projection` fact and the rule that an unresolved projection fact stops unattended picking; keep the `hygiene:model-fallback:<repo>:<node>` warning but derive it from the Dispatcher's own per-node selection plus the run's node outcomes.

### Motivation

Maintainer decision of 2026-10-12: ordered model fallback moves from the Fabro ENGINE (cross-candidate fallback inside one node visit, rendered as the `acp.fallback_chain` node attribute) to the DISPATCHER. Upstream Fabro re-platformed onto the Petri engine, which rejects `acp.fallback_chain` as `attractor.unknown_attribute` and has no equivalent (`plan/fabro-currency/research/001-currency-assessment-2026-09-30.md`; `plan/fabro-currency/research/002-fork-hygiene-and-carrier-inventory-2026-09-30.md`, row 23; `plan/fabro-currency/research/003-local-candidate-assessment-2026-10-01.md`); the 0.254 fork that implements the engine handler is retired at the Petri cutover (ledger bd-ib-iud52v), and bd-ib-r5cnjd (the Petri carry) was closed deferred on 2026-10-08. The maintainer's stated priority is to PREVENT STALLS and AVOID UNNECESSARY DELEGATION TO A HUMAN; lost work is acceptable when the system recovers on its own. The forcing incident: on 2026-10-11 the Codex subscription ran out of usage for hours and every node had to be rerouted by hand (PR 2766). A second measured instance: run 01M4J5M63APH75NJ1JF7ZCN9DY on 2026-10-10 failed `disposition` on Codex with "You've hit your usage limit", was retried once by the engine, and rested the item at blocked / needs-human waiting on a person. Evidence and the full downside comparison of the two layers is the 2026-10-12 investigation report committed at `plan/factory-configurable-model-fallback-priority/research/dispatcher-fallback-downsides-2026-10-12.md` (findings D1-D13 and E1-E8; every D-numbered or E-numbered finding cited in this proposal, and the measured counts it quotes, resolve to that file).

The S5/S6 projection code (`_acp_event_projection.py`, `_acp_fallback_events.py`, `_acp_fallback_warning_ledger.py`, `_dispatcher_reconcile_acp_projection.py`) is keyed on 0.254's `agent.acp.failover`, which Petri does not emit (D4, E8). Keeping the stop-picking rule would let an event stream that can never exist halt unattended work, which is the stall the maintainer's priority forbids.

### Proposed Changes

Heading: contracts.md §"Factory-configurable ACP fallback priority".

Edit 1 — delete this current text in full (three paragraphs):

> **Events and projection are compatible, idempotent, and leak-free.** The feature
> MUST NOT reuse Fabro's existing incompatible native-API `agent.failover` event.
> Each reactive or actually executed preflight transition emits a versioned
> `agent.acp.failover` event with `schema_version: 1`, stable event id, occurrence time, node visit,
> engine attempt, candidate indexes and durations, from/to display and machine
> identities, selected hold key, typed cause/scope, primary-generation
> fingerprint, and separate full-chain digest. It MUST contain no command, env
> value, credential, prompt, raw error, or unredacted diagnostic. Existing
> `agent.failover` events and stored-run consumers remain unchanged and require
> historical/native round-trip controls.
> Unknown versions MUST be round-tripped byte-for-byte and surfaced as
> unobservable; they MUST NOT mint a hold or silently disappear.
>
> The Dispatcher MUST fetch events from the run's resolved factory target,
> project by stable event id, calculate holds from occurrence time, and replay
> projection during reconciliation. Read failure is not absence. It emits exactly
> one flat fact per run/node with id
> `hygiene:model-fallback-projection:<repo>:<run>:<node>`, existing `hygiene`
> kind, `high` urgency, source reference to repository and dispatch journal, a
> deterministic run/node/factory/error summary, and a `shell` handoff containing
> the same executable server-qualified inspection command reconciliation uses.
> Repeated failures aggregate into that id; it clears only after successful
> idempotent projection for the run/node or an attributed, reason-required,
> append-only operator clearance naming that exact fact id. Clearance retires the
> fact only and MUST NOT mint, retire, or reinterpret a hold; run absence alone is
> never resolution.
>
> While any projection-failure fact remains unresolved, an unattended loop MUST
> stop further picking for that repository. A human-attended `--item` dispatch MAY
> proceed only after the high-urgency warning is surfaced before claim and does
> not clear the fact.

and insert in its place:

> **Fallback selection is observed from the Dispatcher's own decisions.** The
> Dispatcher MUST NOT depend on any engine fallback or failover event; the
> per-node selection record of "Preflight consumes versioned observed holds" and
> the `provider-limit-release` record are the authoritative fallback history.
> Fabro's existing native-API `agent.failover` events and their stored-run
> consumers are unaffected by this section.

Edit 2 — replace this current text:

> Every actually executed non-primary candidate appends one idempotent journal
> record and yields one aggregate attention fact per repository/node with id
> `hygiene:model-fallback:<repo>:<node>`, existing `hygiene` kind, valid urgency,
> source reference, and executable inspection handoff. The newest unresolved
> observation supplies the deterministic summary. Later run failure does not
> erase it, and it never refuses or disposes work. A primary node attempt clears
> only a warning from the same primary-generation fingerprint when its attempt
> began after the warning and completed successfully, regardless of the overall
> run's later outcome. Older concurrent success, unrelated success, probes, and
> unexecuted preflight selection cannot clear it. Primary replacement retires the
> prior warning as append-only `superseded`; non-primary chain changes alter only
> the full-chain digest, not the primary generation, so they do not strand the
> warning.

with:

> Every dispatch whose per-node selection rendered a non-primary candidate for a
> node the run then actually executed — as read from the run's node outcomes on
> its resolved factory — appends one idempotent journal record and yields one
> aggregate attention fact per repository/node with id
> `hygiene:model-fallback:<repo>:<node>`, existing `hygiene` kind, valid urgency,
> source reference, and executable inspection handoff. The newest unresolved
> observation supplies the deterministic summary. Later run failure does not
> erase it, and it never refuses or disposes work. The warning clears only when a
> later dispatch renders the same primary generation for that node and that node
> attempt, begun after the warning, completes successfully, regardless of the
> overall run's later outcome. Older concurrent success, unrelated success,
> probes, and a selection for a node the run never reached cannot clear it.
> Primary replacement retires the prior warning as append-only `superseded`;
> non-primary chain changes alter only the full-chain digest, not the primary
> generation, so they do not strand the warning.


## Proposal: A failed provider-limit attempt's cost is recorded

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Replace "Cost follows every attempt in a successful fallback run" (unmeetable once fallback spans runs) with a requirement that every run released for a provider-limit failure gets an attempt-cost record, and that an item's cost across a release-and-re-dispatch sequence is the sum; keep the pricing rules; amend the fail-closed cost gate's coverage bullet so these records are observations, not gate verdicts.

### Motivation

Maintainer decision of 2026-10-12: ordered model fallback moves from the Fabro ENGINE (cross-candidate fallback inside one node visit, rendered as the `acp.fallback_chain` node attribute) to the DISPATCHER. Upstream Fabro re-platformed onto the Petri engine, which rejects `acp.fallback_chain` as `attractor.unknown_attribute` and has no equivalent (`plan/fabro-currency/research/001-currency-assessment-2026-09-30.md`; `plan/fabro-currency/research/002-fork-hygiene-and-carrier-inventory-2026-09-30.md`, row 23; `plan/fabro-currency/research/003-local-candidate-assessment-2026-10-01.md`); the 0.254 fork that implements the engine handler is retired at the Petri cutover (ledger bd-ib-iud52v), and bd-ib-r5cnjd (the Petri carry) was closed deferred on 2026-10-08. The maintainer's stated priority is to PREVENT STALLS and AVOID UNNECESSARY DELEGATION TO A HUMAN; lost work is acceptable when the system recovers on its own. The forcing incident: on 2026-10-11 the Codex subscription ran out of usage for hours and every node had to be rerouted by hand (PR 2766). A second measured instance: run 01M4J5M63APH75NJ1JF7ZCN9DY on 2026-10-10 failed `disposition` on Codex with "You've hit your usage limit", was retried once by the engine, and rested the item at blocked / needs-human waiting on a person. Evidence and the full downside comparison of the two layers is the 2026-10-12 investigation report committed at `plan/factory-configurable-model-fallback-priority/research/dispatcher-fallback-downsides-2026-10-12.md` (findings D1-D13 and E1-E8; every D-numbered or E-numbered finding cited in this proposal, and the measured counts it quotes, resolve to that file).

Today `token_cost_micros` appears on exactly the 66 green runs in this repository's journal and on no failed run, although failed runs consume spend (D7); the per-run `total_usd_micros` field already exists in `_fabro_port_records.py` `_run_summary`.

### Proposed Changes

Heading: contracts.md §"Factory-configurable ACP fallback priority" → paragraph "**Cost follows every attempt in a successful fallback run.**".

Replace this current text:

> **Cost follows every attempt in a successful fallback run.** Token use and
> elapsed time MUST be attributed and summed per candidate attempt, including
> failed attempts before the successful fallback.

with:

> **Cost follows every attempt.** For every run released under "Provider-limit
> release and re-dispatch", and for every availability probe turn, the Dispatcher
> MUST journal one attempt-cost record carrying the attempt's token use and
> elapsed time per node attempt wherever the run record exposes them, priced
> under the rules below, or marked cost-unobservable. An item's cost across a
> release-and-re-dispatch sequence is the sum of those records and the final
> run's cost.

and replace this current text:

> Terminally unsuccessful
> runs retain the existing no-cost-observation/no-gate posture.

with "Attempt-cost records are observations only and never yield a gate verdict; terminally unsuccessful runs otherwise retain the existing no-gate posture."

Heading: contracts.md §"Fail-closed cost gate (keyed on `--item` presence)" → "Gate coverage" bullet. Replace this current text:

>   - A run that did NOT reach a successful terminal outcome yields no cost
>     observation and no gate verdict — even though such a run MAY have
>     consumed spend.

with:

> - A run that did NOT reach a successful terminal outcome yields no gate
>   verdict — even though such a run MAY have consumed spend. A run released
>   for a provider-limit failure additionally yields the attempt-cost record of
>   §"Factory-configurable ACP fallback priority" → "Cost follows every
>   attempt", which is an observation and never a gate verdict.


## Proposal: Provider-limit permanence: typed state survives the needs_human terminal and routes to release, with no engine carve-out

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Require that a provider-limit failure is classified permanent (never transient_infra) in every measured form, that the typed state, provider attribution and surfaced sentence survive a run that ended at the workflow's needs_human terminal, and that a set typed state routes the item to provider-limit release instead of the needs-human rest; drop the scope-boundary carve-out that placed the same-node engine integration under this specification.

### Motivation

Maintainer decision of 2026-10-12: ordered model fallback moves from the Fabro ENGINE (cross-candidate fallback inside one node visit, rendered as the `acp.fallback_chain` node attribute) to the DISPATCHER. Upstream Fabro re-platformed onto the Petri engine, which rejects `acp.fallback_chain` as `attractor.unknown_attribute` and has no equivalent (`plan/fabro-currency/research/001-currency-assessment-2026-09-30.md`; `plan/fabro-currency/research/002-fork-hygiene-and-carrier-inventory-2026-09-30.md`, row 23; `plan/fabro-currency/research/003-local-candidate-assessment-2026-10-01.md`); the 0.254 fork that implements the engine handler is retired at the Petri cutover (ledger bd-ib-iud52v), and bd-ib-r5cnjd (the Petri carry) was closed deferred on 2026-10-08. The maintainer's stated priority is to PREVENT STALLS and AVOID UNNECESSARY DELEGATION TO A HUMAN; lost work is acceptable when the system recovers on its own. The forcing incident: on 2026-10-11 the Codex subscription ran out of usage for hours and every node had to be rerouted by hand (PR 2766). A second measured instance: run 01M4J5M63APH75NJ1JF7ZCN9DY on 2026-10-10 failed `disposition` on Codex with "You've hit your usage limit", was retried once by the engine, and rested the item at blocked / needs-human waiting on a person. Evidence and the full downside comparison of the two layers is the 2026-10-12 investigation report committed at `plan/factory-configurable-model-fallback-priority/research/dispatcher-fallback-downsides-2026-10-12.md` (findings D1-D13 and E1-E8; every D-numbered or E-numbered finding cited in this proposal, and the measured counts it quotes, resolve to that file).

`_needs_human_terminal_outcome` (`_dispatcher_fabro_terminal.py`) builds the blocked outcome with no `provider_usage_limit*` fields even though the failure was parsed; the 2026-10-10 journal outcome shows `status: blocked`, `provider_usage_limit_provider: null` (D2a). On Petri the terminal detail message for a needs-human route may carry the needs-human script's stderr instead of the provider sentence (`plan/fabro-currency/research/007-petri-semantic-probes-2026-10-08.md`, probe p6; D2e).

### Proposed Changes

Heading: contracts.md §"Provider-limit permanence and root-cause surfacing".

Edit 1 — after this current paragraph (unchanged):

> **The condition is typed, not re-matched.** The Dispatcher MUST carry the
> provider-limit condition as typed state on the failure detail. A consumer —
> notably the admission gate of §"Provider spend containment" — MUST be able to
> read that state directly, and MUST NOT be required to re-match the cause text for
> itself. Detection MUST prefer the provider's own STRUCTURED machine token over
> prose matching, and MAY fall back to prose hints when that token is absent: prose
> hints are locale- and wording-fragile, and a near-miss variant has already been
> observed to defeat a substring match that omitted one word.

insert:

> **Detection covers every measured form, and the verdict is never transient.**
> A provider usage, session, or spend ceiling MUST be classified permanent and
> MUST NOT be classified `transient_infra`, whichever measured form carries it:
> the provider's structured token in any spelling the pinned adapters emit (for
> Codex both `codexErrorInfo` / `usageLimitExceeded` and `codex_error_info` /
> `usage_limit_exceeded`), or, where the engine preserves only the failure
> message text, the provider's sentence (for Claude the session-limit, generic
> limit, usage-limit, and organisation spend-limit sentences; for Codex the
> usage-limit sentences), using the measured set of §"Factory-configurable ACP
> fallback priority". A Claude refusal whose structured kind is `rate_limit` is
> classified by its sentence, not by that kind alone.
>
> **The typed state survives the needs_human terminal.** A run that ended at the
> workflow's `needs_human` terminal after an ACP node failed MUST be classified
> from that node's own recorded failure. The typed provider-limit state, the
> attributed provider, and the surfaced provider sentence MUST be carried on the
> outcome the Dispatcher derives, exactly as for any other terminal; when the
> typed state is set the item takes §"Factory-configurable ACP fallback
> priority" → "Provider-limit release and re-dispatch" and does NOT rest at
> `blocked / needs-human`. A dead-implementer truncation (§"Provider spend
> containment") whose surfaced implementer failure carries the typed state takes
> the same route.

Edit 2 — replace this current text:

> The explicit same-node integration in
> §"Factory-configurable ACP fallback priority" is the sole carve-out: it binds
> that fallback-enabled node's observable transition semantics without otherwise
> placing Fabro's classifier under this specification.

with:

> Ordered fallback is a Dispatcher behaviour (§"Factory-configurable ACP fallback
> priority"), so no carve-out places any Fabro behaviour under this
> specification. The one wasted engine retry remains expected; the
> provider-limit release route, not any engine behaviour, is what moves the item
> to an unheld candidate.


## Proposal: Provider spend containment, the admission valve, and progress accounting follow the Dispatcher-level model

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Update every dependent clause outside the fallback section: the containment rule's wait and cross-provider prohibition, the hold-source sentence, legacy-record coverage, the no-silent-containment field list (a third disposition), the human-gate relationship, the admission-valve bullet, the host-concurrency tenant clause (peer hold reads are not counted-claim bookkeeping), the across-dispatch progress rule, the control-surface journal sentence, the factory-run-never-awaits-a-human rule, the Definition-of-Done structured needs-human ending, and the needs-attention wait enumeration.

### Motivation

Maintainer decision of 2026-10-12: ordered model fallback moves from the Fabro ENGINE (cross-candidate fallback inside one node visit, rendered as the `acp.fallback_chain` node attribute) to the DISPATCHER. Upstream Fabro re-platformed onto the Petri engine, which rejects `acp.fallback_chain` as `attractor.unknown_attribute` and has no equivalent (`plan/fabro-currency/research/001-currency-assessment-2026-09-30.md`; `plan/fabro-currency/research/002-fork-hygiene-and-carrier-inventory-2026-09-30.md`, row 23; `plan/fabro-currency/research/003-local-candidate-assessment-2026-10-01.md`); the 0.254 fork that implements the engine handler is retired at the Petri cutover (ledger bd-ib-iud52v), and bd-ib-r5cnjd (the Petri carry) was closed deferred on 2026-10-08. The maintainer's stated priority is to PREVENT STALLS and AVOID UNNECESSARY DELEGATION TO A HUMAN; lost work is acceptable when the system recovers on its own. The forcing incident: on 2026-10-11 the Codex subscription ran out of usage for hours and every node had to be rerouted by hand (PR 2766). A second measured instance: run 01M4J5M63APH75NJ1JF7ZCN9DY on 2026-10-10 failed `disposition` on Codex with "You've hit your usage limit", was retried once by the engine, and rested the item at blocked / needs-human waiting on a person. Evidence and the full downside comparison of the two layers is the 2026-10-12 investigation report committed at `plan/factory-configurable-model-fallback-priority/research/dispatcher-fallback-downsides-2026-10-12.md` (findings D1-D13 and E1-E8; every D-numbered or E-numbered finding cited in this proposal, and the measured counts it quotes, resolve to that file).

A missed dependent clause would leave the ratified text contradicting the new section — for example "Observed, not predicted" still names projected `agent.acp.failover` events as a hold source, and "A factory run never awaits a human" says the blocked/needs-human rest is the only place a decision waits without excluding a classified provider-limit failure.

### Proposed Changes

Heading: contracts.md §"Provider spend containment" (under §"Dispatcher admission, WIP cap, and post-merge acceptance").

Edit 1 — replace this current text:

> **No dispatch into a known-exhausted candidate chain.** Before claim, the
> Dispatcher MUST filter every success-critical node's ordered candidates by the
> versioned observed availability holds of §"Factory-configurable ACP fallback
> priority". It MUST refuse only when at least one such chain is empty. A known
> dead primary with an eligible fallback therefore does not refuse the run; a
> known-exhausted complete chain does.

with:

> **No dispatch into a known-exhausted candidate chain.** Before claim, the
> Dispatcher MUST filter every success-critical node's ordered candidates by the
> versioned observed availability holds of §"Factory-configurable ACP fallback
> priority", read from its own and its peer repositories' dispatch journals as
> that section requires. It MUST refuse only when at least one such chain is
> empty, and that refusal is a wait whose next evaluation is scheduled at the
> earliest covering expiry. A known dead primary with an eligible fallback
> therefore does not refuse the run; a known-exhausted complete chain does; and a
> hold on one provider never refuses an item whose resolved candidates are all on
> other providers.

Edit 2 — replace this current text:

> **Observed, not predicted.** A hold MUST derive from a real candidate attempt:
> either the typed condition on a terminal failed run or an idempotently projected
> `agent.acp.failover` event from a run of any eventual outcome. The latter is
> load-bearing: a primary may report an eligible failure before its fallback
> succeeds, and the successful run still records that observation. A hold MUST NOT
> derive from credential material, catalogs, a host-side probe, or provider reset
> claims.

with:

> **Observed, not predicted.** A hold MUST derive from a real candidate attempt:
> either the typed condition classified from a failed node of a terminal run,
> whichever terminal the run reached, or a refused availability probe turn of
> §"Factory-configurable ACP fallback priority", which runs the candidate's own
> adapter. A hold MUST NOT derive from credential material, catalogs, the
> admission-time credential-usability probe, or provider reset claims.

Edit 3 — in "**Every observed availability record is scoped, versioned, and expires.**", after the current sentence

> Typed candidate evidence wins over legacy cause-text attribution when
> a chain executed.

append: "No record, current or legacy, MAY refuse a dispatch whose resolved candidates all lie outside its coverage."

Edit 4 — in "**No silent containment.**", replace this current text:

> **No silent containment.** A refusal to admit on containment grounds, and a
> truncation of a run under the dead-implementer rule, are each auto-dispositions
> and MUST be journaled under §"Control surface and audit". Neither MAY be silent.
> The two carry DIFFERENT fields, because they are not governed by the same
> observation:

with "**No silent containment.** A refusal to admit on containment grounds, a truncation of a run under the dead-implementer rule, and a provider-limit release are each auto-dispositions and MUST be journaled under §"Control surface and audit". None MAY be silent. The three carry DIFFERENT fields, because they are not governed by the same observation:" and append this bullet to that list:

> - A provider-limit release MUST carry at minimum the fields
>   §"Factory-configurable ACP fallback priority" → "Provider-limit release and
>   re-dispatch" names: the work-item id, run id, factory, failing node, matched
>   cause, scope and hold key, the failed candidate identity, and the preserved
>   tree reference or its absence.

Edit 5 — in "**Relationship to the human-gate floor.**", after the current text

> No containment refusal MAY
> dispose of a `blocked_reason: needs-human` item.

append: "A provider-limit release is not an auto-resolution of a needs-human decision: a classified provider-limit failure never enters `blocked / needs-human`, because it is not a decision a human holds."

Heading: contracts.md §"Admission valve (`ready → active`)". Replace this current text:

> - **Required ACP chains not observed exhausted:** resolve each node's ordered
>   candidates against versioned observed availability holds as §"Factory-configurable
>   ACP fallback priority" requires. An item is not admitted only when at least
>   one success-critical node has no remaining candidate. A hold covering one
>   primary MUST NOT refuse admission while its chain has an eligible fallback.
>   The item is NOT marked `blocked` on these grounds and MUST NOT be
>   auto-disposed; it remains `ready` for a subsequent pass.

with:

> - **Required ACP chains not observed exhausted:** resolve each node's ordered
>   candidates against versioned observed availability holds, read from this
>   repository's and its peer repositories' dispatch journals, as
>   §"Factory-configurable ACP fallback priority" requires. An item is not
>   admitted only when at least one success-critical node has no remaining
>   candidate. A hold covering one primary MUST NOT refuse admission while its
>   chain has an eligible fallback, and a hold on one provider MUST NOT refuse an
>   item whose resolved candidates are all on other providers. The item is NOT
>   marked `blocked` on these grounds and MUST NOT be auto-disposed; it remains
>   `ready`, and its next evaluation is scheduled at the earliest covering expiry.

Heading: contracts.md §"Host concurrency belongs to the Fabro scheduler". After this current text:

> The counted-claim bound (§"Per-repo WIP cap") is TENANT-scoped and MUST be
> computed from this repository's own state ONLY — its ledger rows, its
> dispatch locks, and its dispatch journal, across every checkout of the
> tenant. It MUST NOT be read as licensing any observation of the Fabro host
> or of any OTHER repository's state. Tenant-scoped bookkeeping across this
> repository's own checkouts is NOT host observation and is NOT barred by this
> section;

insert the sentence: "Reading the hold records of the peer repositories listed in `dispatcher.hold_peer_repositories` (§"Factory-configurable ACP fallback priority") is availability evidence, not counted-claim bookkeeping, and this tenant-scope clause does not govern it."

Heading: contracts.md §"Across-dispatch required-result progress". Replace this current text:

> Known host-attributable failures neither increment nor reset the item count;

with "Known host-attributable failures, and runs released under §"Factory-configurable ACP fallback priority" → "Provider-limit release and re-dispatch", neither increment nor reset the item count;"

Heading: contracts.md §"Control surface and audit". Replace this current text:

> The two spend-containment dispositions of §"Provider spend containment" — a
> provider-exhaustion admission refusal and a dead-implementer run truncation —

with "The three spend-containment dispositions of §"Provider spend containment" — a provider-exhaustion admission refusal, a dead-implementer run truncation, and a provider-limit release —".

Heading: contracts.md §"A factory run never awaits a human" (under §"Dispatcher policy settings"). In the first bullet, after this current text:

>   The human's answer — retry, re-implement, or abandon — is expressed
>   through ledger valves (`resolve-blocked`, the rework path, or leaving
>   the item blocked), never by attaching to a run.

append: "A failure the Dispatcher classifies as provider-limit is NOT a needs-human outcome even when the workflow routed it through the `needs_human` terminal: the item takes §"Factory-configurable ACP fallback priority" → "Provider-limit release and re-dispatch" and does not rest at `blocked / needs-human`."

Heading: contracts.md §"Definition-of-Done and Proof-of-Done stages". Replace this current text:

> A *structured needs-human ending* is the existing failed outcome
> of an ACP node that the reserved workflow routes to its `needs_human`
> terminal (§"A factory run never awaits a human"), carrying a failure reason
> the Dispatcher records as the needs-human question.

with "A *structured needs-human ending* is the existing failed outcome of an ACP node that the reserved workflow routes to its `needs_human` terminal (§"A factory run never awaits a human"), carrying a failure reason the Dispatcher records as the needs-human question; a failed outcome the Dispatcher classifies as provider-limit is not a structured needs-human ending."

Heading: contracts.md §"Orchestrator-owned attention facts" → "Wait completeness". Replace this current text:

> and an item for which unexpired observed availability holds
> exhaust at least one success-critical ACP fallback chain, which likewise stays
> `ready` (§"Provider spend containment" and §"Factory-configurable ACP fallback
> priority").

with:

> and an item for which unexpired observed availability holds
> exhaust at least one success-critical ACP fallback chain, which likewise stays
> `ready` and whose wait item names the earliest covering expiry as its scheduled
> retry instant (§"Provider spend containment" and §"Factory-configurable ACP
> fallback priority"); that wait's handoff is the exact scope/key clearance
> valve, never `resolve-blocked`.


## Proposal: Rewrite Scenario 127 to the Dispatcher-level model

### Target specification files

- SPECIFICATION/scenarios.md

### Summary

Replace Scenario 127 as a whole. Its heading drops "one node visit"; the engine-shaped sub-scenarios (failover event emission, sandbox-local partial-write hand-off, external-effect fail-closed, one shared deadline, server-qualified event projection, reached-node typed termination) are removed; new sub-scenarios bind provider-limit release and re-dispatch, the human route for unclassifiable failures, re-dispatch from the preserved tree, the post-expiry probe turn, and failed-attempt cost. Configuration sub-scenarios are kept.

### Motivation

Maintainer decision of 2026-10-12: ordered model fallback moves from the Fabro ENGINE (cross-candidate fallback inside one node visit, rendered as the `acp.fallback_chain` node attribute) to the DISPATCHER. Upstream Fabro re-platformed onto the Petri engine, which rejects `acp.fallback_chain` as `attractor.unknown_attribute` and has no equivalent (`plan/fabro-currency/research/001-currency-assessment-2026-09-30.md`; `plan/fabro-currency/research/002-fork-hygiene-and-carrier-inventory-2026-09-30.md`, row 23; `plan/fabro-currency/research/003-local-candidate-assessment-2026-10-01.md`); the 0.254 fork that implements the engine handler is retired at the Petri cutover (ledger bd-ib-iud52v), and bd-ib-r5cnjd (the Petri carry) was closed deferred on 2026-10-08. The maintainer's stated priority is to PREVENT STALLS and AVOID UNNECESSARY DELEGATION TO A HUMAN; lost work is acceptable when the system recovers on its own. The forcing incident: on 2026-10-11 the Codex subscription ran out of usage for hours and every node had to be rerouted by hand (PR 2766). A second measured instance: run 01M4J5M63APH75NJ1JF7ZCN9DY on 2026-10-10 failed `disposition` on Codex with "You've hit your usage limit", was retried once by the engine, and rested the item at blocked / needs-human waiting on a person. Evidence and the full downside comparison of the two layers is the 2026-10-12 investigation report committed at `plan/factory-configurable-model-fallback-priority/research/dispatcher-fallback-downsides-2026-10-12.md` (findings D1-D13 and E1-E8; every D-numbered or E-numbered finding cited in this proposal, and the measured counts it quotes, resolve to that file).

Behaviour introduced by the contracts findings of this proposal must be bound by scenarios (propose-change authoring split (i)). Because the Scenario 127 heading text changes, the revise pass that accepts this proposal MUST update the corresponding `tests/heading-coverage.json` entry in the same change (and re-point the sub-scenario test bindings, which the open item bd-ib-vuwrv5 also needs regroomed: its live-dispatch criterion "a fallback finishing the same node visit" cannot be met). This proposal does not edit that file.

### Proposed Changes

Heading: scenarios.md "## Scenario 127 — Ordered ACP fallback preserves primary resolution, failure honesty, and one node visit".

Replace this current text in full:

> ## Scenario 127 — Ordered ACP fallback preserves primary resolution, failure honesty, and one node visit
>
> ```gherkin
> Feature: Factory-configurable ACP fallback priority
>   As a factory operator
>   I want each ACP node to use an observed-health-filtered ordered candidate chain
>   So that a removed model or exhausted allowance does not replay a long workflow or silently change its failure
>
>   Scenario: v107 primary bytes survive absent and fallback-only configuration
>     Given the review_fix node has no acp_nodes entry and no new-grammar metadata
>     When the Dispatcher resolves its adapter
>     Then candidate zero is byte-identically the Claude Opus 5 workflow default rendered from the structured built-in default
>     And `fallbacks: []` alone produces the same bytes
>     And when the review_fix node carries an explicit structured entry, identity-only or fallback-only fields attach after that primary renders
>
>   Scenario: New grammar is version-gated against the resolved factory
>     Given a node carries identity, signature, pricing, or a non-empty fallback field
>     When dispatcher.minimum_release is below the first supporting release or the resolved factory server lacks the pinned Fabro capability
>     Then dispatch refuses before claim or run creation
>     And a local Fabro binary is not evidence of the remote capability
>
>   Scenario: A domain-held primary is skipped and an eligible fallback executes
>     Given a success-critical node whose candidate zero is covered by an unexpired domain hold
>     And candidate one is not covered
>     When the node is dispatched and reached
>     Then candidate one is selected in configured order
>     And its actual execution emits one version-1 agent.acp.failover event and one idempotent journal record
>     And an unexecuted preflight selection for a node never reached emits no fallback warning
>
>   Scenario: Shared and distinct identities scope holds across nodes
>     Given two nodes repeat the same availability_key and candidate_key pair
>     And a third candidate has either key different
>     When a candidate-scoped hold is observed
>     Then it skips the repeated identity in both nodes
>     And it does not skip the third candidate
>     And a domain hold covers a candidate when its key equals the candidate availability_key or one of its declared domain-signature hold_keys
>
>   Scenario: Legacy and unidentified adapters retain the conservative v107 posture
>     Given an unexpired legacy provider record
>     When a built-in candidate carries that provider alias
>     Then the legacy record covers that candidate until retirement
>     And an identity-less arbitrary legacy adapter is covered by every live legacy record and continues to mint legacy records
>
>   Scenario: Only an exhausted success-critical chain refuses admission
>     Given implement, review, and proof_verify each retain an unheld candidate
>     And a conditional fix node retains none
>     When the Dispatcher evaluates admission
>     Then it admits the item
>     And if fix is later reached it terminates typed before any adapter without traversing janitor, non-convergence, or needs_human
>     And when instead implement, review, or proof_verify retains none, admission refuses before claim
>
>   Scenario: The recorded removed-model diagnostic falls back but a generic 400 does not
>     Given the pinned Codex adapter returns the measured ChatGPT-account HTTP 400 diagnostic naming the exact requested model as unsupported
>     When the built-in classifier reads its terminal protocol diagnostic
>     Then it emits candidate-scoped model_unsupported and advances once
>     But a generic HTTP 400 or 404 with no exact eligible discriminator terminates with its original identity
>
>   Scenario: Non-eligible failures outrank configured text overlap
>     Given a candidate signature whose literals also appear in an authentication failure, exit 127, signal termination, node timeout, sandbox transport fault, compaction 404, or code or test failure
>     When classification runs
>     Then the non-eligible class terminates the chain without a hold
>     And a runtime multi-match with different dispositions is surfaced as ambiguous, non-eligible, and never first-match selected
>
>   Scenario: A sandbox-local partial write is handed to the next candidate
>     Given a primary makes a sandbox-local partial write and its durable side-effect ledger proves no external-effect onset
>     And it then reports an eligible failure
>     When the next candidate starts
>     Then it runs in the same node visit and sandbox with the original task plus a delimited recovery preamble
>     And predecessor nodes do not replay and the partial write remains
>
>   Scenario: Unknown or observed external effects fail closed
>     Given an attempt may have issued an external mutation and absence of onset cannot be proved durably
>     When it reports an otherwise eligible failure
>     Then reactive fallback does not occur
>     And for any externally mutating ACP node unreadable remote effect evidence is treated as past onset
>
>   Scenario: One deadline and post-transition state prevent replay
>     Given a node with several candidates and one configured timeout
>     When the primary consumes time and reactive fallback begins
>     Then every successor receives only the original deadline's remaining time
>     And the node timeout is not multiplied by candidate count
>     And outer retry, fallback exhaustion, checkpoint, or resume never cycles to an attempted or preflight-skipped candidate
>
>   Scenario: A successful fallback still records the failed primary hold and warning
>     Given a primary emits an eligible domain or candidate failure and candidate one succeeds
>     When the run later succeeds or fails in another node
>     Then the occurrence-time-scoped hold, failover journal record, and hygiene:model-fallback repository-node fact remain observable
>     And overall run success does not clear the primary
>
>   Scenario: Warning clearance is ordered and generation-safe
>     Given a model-fallback warning for a primary generation
>     When the same primary's node attempt starts later and completes successfully
>     Then that warning clears even if the overall run later fails
>     But an older concurrent attempt, unrelated candidate success, probe, or unexecuted selection does not clear it
>     And a committed primary replacement appends superseded while a fallback-only edit changes only the full-chain digest
>
>   Scenario: Projection is server-qualified, idempotent, and fail-closed for unattended picking
>     Given an agent.acp.failover event on the run's resolved remote factory
>     When reconciliation projects the same event more than once
>     Then its stable event id yields one hold and one journal record
>     And an unknown event version is preserved and surfaced without minting a hold
>     But when the event stream cannot be read, one high-urgency per-run-node projection fact appears with an executable server-qualified inspection handoff
>     And unattended picking stops until replay succeeds while an attended item dispatch may proceed only after surfacing the warning
>     And run absence does not clear the fact while an attributed reason-required clearance may retire that fact without changing a hold
>
>   Scenario: Successful fallback cost includes every attempt or is wholly unobservable
>     Given a successful fallback run whose failed primary and successful candidate both emit nonzero usage
>     When cost is derived
>     Then usage from both attempts is included
>     And only one trailing -YYYYMMDD date suffix is stripped from emitted model identity
>     And pricing resolves through the model catalog entry the candidate's identity names first and a per-candidate explicit table second
>     And if any nonzero component is unpriceable the whole run cost is unobservable rather than a partial subtotal or unrelated default
>     And a terminally unsuccessful run retains the existing no-cost-observation posture
>
>   Scenario: Model and effort are set over the protocol and an unadvertised model refuses before the prompt
>     Given a structured candidate whose agent catalog entry declares the protocol mechanism
>     When the Fabro handler opens the session
>     Then it sets model and effort through session/set_config_option before the first prompt
>     And the agent.acp.started event carries the confirmed model and effort
>     But when the agent does not advertise the requested model the candidate terminates typed before any prompt, mints no hold, and does not trigger reactive fallback
> ```

with:

> ## Scenario 127 — Ordered ACP fallback preserves primary resolution and failure honesty, and re-dispatches past a held provider
>
> ```gherkin
> Feature: Factory-configurable ACP fallback priority
>   As a factory operator
>   I want each ACP node dispatched to the first candidate no observed hold covers, and a provider-limit failure re-dispatched rather than escalated
>   So that an exhausted allowance neither stalls the item nor waits on a human
>
>   Scenario: v107 primary bytes survive absent and fallback-only configuration
>     Given the review_fix node has no acp_nodes entry and no new-grammar metadata
>     When the Dispatcher resolves its adapter
>     Then candidate zero is byte-identically the Claude Opus 5 workflow default rendered from the structured built-in default
>     And `fallbacks: []` alone produces the same bytes
>     And when the review_fix node carries an explicit structured entry, identity-only or fallback-only fields attach after that primary renders
>
>   Scenario: New grammar is version-gated by the release floor, not by an engine fallback capability
>     Given a node carries identity, signature, pricing, or a non-empty fallback field
>     When dispatcher.minimum_release is below the first release implementing Dispatcher-level fallback
>     Then dispatch refuses before claim or run creation
>     But a resolved factory server that advertises no fallback-chain capability does not refuse the dispatch
>
>   Scenario: A domain-held primary is skipped and the first unheld candidate is the node's only adapter
>     Given a success-critical node whose candidate zero is covered by an unexpired domain hold
>     And candidate one is not covered
>     When the Dispatcher dispatches the item
>     Then candidate one's adapter is the only adapter rendered for that node
>     And the per-node selection record names candidate one, the full-chain digest, and the hold that skipped candidate zero
>     And a selection for a node the run never reaches emits no fallback warning
>
>   Scenario: Shared and distinct identities scope holds across nodes
>     Given two nodes repeat the same availability_key and candidate_key pair
>     And a third candidate has either key different
>     When a candidate-scoped hold is observed
>     Then it skips the repeated identity in both nodes
>     And it does not skip the third candidate
>     And a domain hold covers a candidate when its key equals the candidate availability_key or one of its declared domain-signature hold_keys
>
>   Scenario: Legacy and unidentified adapters retain the conservative v107 posture
>     Given an unexpired legacy provider record
>     When a built-in candidate carries that provider alias
>     Then the legacy record covers that candidate until retirement
>     And an identity-less arbitrary legacy adapter is covered by every live legacy record and continues to mint legacy records
>
>   Scenario: Only an exhausted success-critical chain makes the item wait
>     Given implement, review, and proof_verify each retain an unheld candidate
>     And a conditional fix node retains none
>     When the Dispatcher evaluates admission
>     Then it admits the item
>     And fix is rendered with the candidate whose covering hold expires earliest
>     And when instead implement, review, or proof_verify retains none, the item is not claimed, stays ready, and is not marked blocked
>     And its next admission evaluation is scheduled at the earliest covering expiry
>     And no human valve is offered as the remedy
>
>   Scenario: A provider-limit failure releases the item and re-dispatches it to the next unheld candidate
>     Given a dispatched item whose disposition node ran on a codex-acp candidate
>     And the run ended at the needs_human terminal after that node failed with "You've hit your usage limit"
>     When the Dispatcher derives the run's outcome
>     Then it appends a domain hold on that candidate's availability key
>     And it journals one provider-limit-release record naming the item, run, factory, node, cause, scope, hold key, failed candidate, and preserved tree reference
>     And the item returns to ready with no blocked_reason
>     And the next dispatch renders disposition with the first unheld candidate in configured order
>     And no rework cap budget and no across-dispatch no-progress count is consumed
>
>   Scenario: A failure the Dispatcher cannot classify keeps the human route
>     Given a run whose failing node's recorded failure matches no eligible signature
>     When the Dispatcher derives the run's outcome
>     Then no hold is appended and no provider-limit-release record is written
>     And the item rests at blocked with blocked_reason needs-human as before
>
>   Scenario: The recorded removed-model diagnostic re-dispatches but a generic 400 does not
>     Given the pinned Codex adapter returns the measured ChatGPT-account HTTP 400 diagnostic naming the exact requested model as unsupported
>     When the Dispatcher classifies the failing node's recorded failure
>     Then it records a candidate-scoped model_unsupported hold and releases the item for re-dispatch
>     But a generic HTTP 400 or 404 with no exact eligible discriminator keeps its original identity and its existing route
>
>   Scenario: Non-eligible failures outrank configured text overlap
>     Given a candidate signature whose literals also appear in an authentication failure, exit 127, signal termination, node timeout, sandbox transport fault, compaction 404, or code or test failure
>     When classification runs
>     Then the non-eligible class mints no hold and is not released for re-dispatch
>     And a runtime multi-match with different dispositions is surfaced as ambiguous, non-eligible, and never first-match selected
>
>   Scenario: A re-dispatch starts from the failed run's preserved tree
>     Given a run released for a provider-limit failure
>     When the failed run published a pull request whose latest proof record anchors a resume
>     Then the re-dispatch takes the resume path with its resumed-at stage derivation
>     And when instead the failed run left only a needs-human ref or a pushed publish branch, the re-dispatch seeds its working tree from that reference's head and the goal brief names it as an interrupted prior attempt
>     And when no preserved reference exists the re-dispatch is a plain dispatch
>
>   Scenario: An expired hold is re-confirmed by a probe turn before a real dispatch uses the candidate
>     Given a domain hold whose bounded expiry has passed
>     When the Dispatcher next evaluates an item whose first candidate that hold covered
>     Then it runs one availability probe turn through that candidate's exact rendered adapter under the projected worker credential
>     And a probe that completes its turn makes the candidate eligible for the dispatch
>     And a probe refused with an eligible provider-limit cause mints a fresh hold whose expiry runs from the probe's occurrence time
>     And the provider's advertised reset instant neither schedules nor replaces the probe
>
>   Scenario: A successful fallback still records the failed primary hold and warning
>     Given a primary's provider-limit failure minted a hold and released the item
>     And the re-dispatched run executed that node on candidate one
>     When the re-dispatched run later succeeds or fails in another node
>     Then the occurrence-time-scoped hold, the provider-limit-release record, and the hygiene:model-fallback repository-node fact remain observable
>     And overall run success does not clear the primary
>
>   Scenario: Warning clearance is ordered and generation-safe
>     Given a model-fallback warning for a primary generation
>     When a later dispatch renders the same primary for that node and that node attempt completes successfully
>     Then that warning clears even if the overall run later fails
>     But an older concurrent attempt, unrelated candidate success, probe, or selection for an unreached node does not clear it
>     And a committed primary replacement appends superseded while a fallback-only edit changes only the full-chain digest
>
>   Scenario: Every failed attempt's cost is recorded
>     Given an item released twice for provider-limit failures whose failed runs both emitted nonzero usage, then completed by a third run
>     When cost is derived
>     Then each released run has one attempt-cost record, priced or marked cost-unobservable
>     And the item's cost across the sequence is the sum of those records and the final run's cost
>     And only one trailing -YYYYMMDD date suffix is stripped from emitted model identity
>     And pricing resolves through the model catalog entry the candidate's identity names first and a per-candidate explicit table second
>     And no attempt-cost record yields a gate verdict
>
>   Scenario: Model and effort are set over the protocol and an unadvertised model refuses before the prompt
>     Given a structured candidate whose agent catalog entry declares the protocol mechanism
>     When the Fabro handler opens the session
>     Then it sets model and effort through session/set_config_option before the first prompt
>     And the agent.acp.started event carries the confirmed model and effort
>     But when the agent does not advertise the requested model the candidate terminates typed before any prompt, mints no hold, and is not released for re-dispatch as a provider-limit failure
> ```


## Proposal: Extend Scenarios 60, 65 and 94 for cross-provider scoping, host-wide holds, scheduled waits, and detection

### Target specification files

- SPECIFICATION/scenarios.md

### Summary

Amend Scenario 60's expiry sub-scenario to require the post-expiry probe turn and add three sub-scenarios (a hold on one provider never refuses an item wholly on another; peer-repository holds are visible host-wide and an unreadable peer never refuses; an exhausted chain waits with a scheduled retry, not a human valve). Add to Scenario 65 an outline covering every measured provider-limit form and a sub-scenario for the needs_human terminal. Re-word Scenario 94's last sub-scenario's fallback clause.

### Motivation

Maintainer decision of 2026-10-12: ordered model fallback moves from the Fabro ENGINE (cross-candidate fallback inside one node visit, rendered as the `acp.fallback_chain` node attribute) to the DISPATCHER. Upstream Fabro re-platformed onto the Petri engine, which rejects `acp.fallback_chain` as `attractor.unknown_attribute` and has no equivalent (`plan/fabro-currency/research/001-currency-assessment-2026-09-30.md`; `plan/fabro-currency/research/002-fork-hygiene-and-carrier-inventory-2026-09-30.md`, row 23; `plan/fabro-currency/research/003-local-candidate-assessment-2026-10-01.md`); the 0.254 fork that implements the engine handler is retired at the Petri cutover (ledger bd-ib-iud52v), and bd-ib-r5cnjd (the Petri carry) was closed deferred on 2026-10-08. The maintainer's stated priority is to PREVENT STALLS and AVOID UNNECESSARY DELEGATION TO A HUMAN; lost work is acceptable when the system recovers on its own. The forcing incident: on 2026-10-11 the Codex subscription ran out of usage for hours and every node had to be rerouted by hand (PR 2766). A second measured instance: run 01M4J5M63APH75NJ1JF7ZCN9DY on 2026-10-10 failed `disposition` on Codex with "You've hit your usage limit", was retried once by the engine, and rested the item at blocked / needs-human waiting on a person. Evidence and the full downside comparison of the two layers is the 2026-10-12 investigation report committed at `plan/factory-configurable-model-fallback-priority/research/dispatcher-fallback-downsides-2026-10-12.md` (findings D1-D13 and E1-E8; every D-numbered or E-numbered finding cited in this proposal, and the measured counts it quotes, resolve to that file).

These are the scenario bindings for the detection (R2), scoping and visibility (R3), waiting (R4) and probing (R5) clauses of the contracts findings. Scenario headings 60, 65 and 94 are unchanged, so `tests/heading-coverage.json` needs no heading edit for them; the revise pass re-points any test binding the new sub-scenarios need.

### Proposed Changes

Heading: scenarios.md "## Scenario 60 — An observed provider exhaustion refuses admission, and expires".

Edit 1 — replace this current text:

>   Scenario: A scoped record expires and admission resumes
>     Given an observed availability record whose bounded expiry has passed
>     And the covered candidate makes a success-critical chain viable
>     When the Dispatcher evaluates the admission valve on a subsequent pass
>     Then the expired record does not skip the candidate
>     And the item is admitted normally

with:

>   Scenario: A scoped record expires, a probe turn confirms the candidate, and admission resumes
>     Given an observed availability record whose bounded expiry has passed
>     And the covered candidate makes a success-critical chain viable
>     And an availability probe turn through that candidate completes its turn
>     When the Dispatcher evaluates the admission valve on a subsequent pass
>     Then the expired record does not skip the candidate
>     And the item is admitted normally

Edit 2 — after the current sub-scenario ending

>   Scenario: A containment refusal never disposes a needs-human item
>     Given a work-item carrying blocked_reason "needs-human"
>     And observed holds exhaust a success-critical chain
>     When the Dispatcher evaluates that item
>     Then the item is not auto-resolved
>     And the item stays surfaced through the needs-attention awareness surface

append, inside the same gherkin block:

>
>   Scenario: A hold on one provider does not refuse an item wholly on another
>     Given an unexpired domain hold, current or legacy, on the codex availability domain
>     And a ready work-item whose every ACP node resolves to candidates outside that domain
>     When the Dispatcher evaluates the admission valve
>     Then the item is admitted
>     And no refusal record names the codex hold
>
>   Scenario: A peer repository's hold is visible host-wide, and an unreadable peer never refuses
>     Given dispatcher.hold_peer_repositories lists a peer repository on the same host
>     And the peer's dispatch journal records an unexpired domain hold on the codex availability domain
>     When this repository's Dispatcher evaluates a ready item whose first implement candidate is in that domain
>     Then that candidate is skipped exactly as a local hold would skip it
>     But when the peer's journal cannot be read, one high-urgency hygiene:hold-peer-unreadable fact appears and the dispatch is not refused
>
>   Scenario: An exhausted chain waits with a scheduled retry instead of a human valve
>     Given a ready work-item with no unheld candidate for one success-critical ACP node
>     When the Dispatcher evaluates the admission valve
>     Then the item's next admission evaluation is scheduled at the earliest expiry among the covering holds
>     And the wait is surfaced with that instant and the clearance valve, never resolve-blocked

Heading: scenarios.md "## Scenario 65 — A provider ceiling is permanent and surfaces the provider's own sentence". After the current final sub-scenario

> Scenario: An ordinary transient failure keeps its classification
>   Given a failed run whose cause chain carries no permanent cause of either recognised class
>   When the Dispatcher derives the failure detail
>   Then the failure category is the one the run reported
>   And the failure signature is unchanged
>   And the typed provider-limit flag is not set
> ```

insert, before the closing fence:

>
> Scenario Outline: Every measured provider-limit form is detected and is never transient
>   Given a failed run whose failing node's recorded failure carries <form>
>   When the Dispatcher derives the failure detail for that run
>   Then the failure category is permanent and not transient_infra
>   And the failure detail carries the typed provider-limit flag
>   And the provider is attributed as <provider>
>
>   Examples:
>     | form                                                                              | provider  |
>     | the Claude sentence "You've hit your session limit" with structured kind rate_limit | anthropic |
>     | only the message text "You've hit your limit · resets" and no structured payload   | anthropic |
>     | the Claude organisation spend-limit sentence                                       | anthropic |
>     | the structured field codexErrorInfo carrying usageLimitExceeded                    | codex     |
>     | the structured field codex_error_info carrying usage_limit_exceeded                | codex     |
>     | only the message text "You've hit your usage limit" and no structured payload      | codex     |
>
> Scenario: A provider-limit failure routed through the needs_human terminal keeps its typed state
>   Given a run that ended at the workflow's needs_human terminal after an ACP node failed on a provider usage ceiling
>   And the terminal message carries the needs-human script's output rather than the provider's sentence
>   When the Dispatcher derives the outcome
>   Then it classifies from the failing node's own recorded failure
>   And the outcome carries the typed provider-limit flag, the attributed provider, and the provider's sentence
>   And the item does not rest at blocked with blocked_reason needs-human

Heading: scenarios.md "## Scenario 94 — A provider's availability claim does not extend an exhaustion record's expiry". Replace this current text:

>   And overall fallback-run success does not clear a skipped or failed primary

with "  And a re-dispatched run's success on a fallback candidate does not clear the held primary".

