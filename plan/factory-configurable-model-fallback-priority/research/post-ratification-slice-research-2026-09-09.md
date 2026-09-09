# factory-configurable-model-fallback-priority — post-ratification slice research

_Recorded 2026-09-09 after v109 landed on `master`. Plan epic:
`bd-ib-jxvgq5`. This note supersedes the opening note wherever the v109
contract made a different decision._

## Outcome

The work is not one Dispatcher retry loop. It is a seven-slice delivery with a
hard cross-repository dependency: the Dispatcher owns configuration,
preflight, observed holds, projection, warning facts, and cost; Fabro owns the
bounded in-node ACP transition and its versioned event. The enabling adoption
slice must remain last and must prove the capability against the resolved
remote factory, not a local binary.

The permanent detection-coverage anchor for this repository is now ledger
record `bd-ib-j5fzyo`. It is intentionally an unparented, non-dispatchable
`backlog` chore. `.livespec.jsonc` points at it; only
`record_detection_run(...)` may append its coverage comments. Parenting the
anchor to this plan would make plan archival impossible because the anchor must
never close.

## Corrections to the opening research

The ratified contract rejects three early assumptions:

- Reactive fallback is not a Dispatcher-side whole-run re-dispatch. It is one
  Fabro ACP handler visit with one run id, sandbox, and original node deadline.
- Authentication failures, command-not-found/exit 127, generic HTTP 400/404,
  cancellation, deadlines, signals, sandbox/DNS/transport failures, and
  code/test/review/tool failures are explicitly non-eligible. The recorded
  exact Codex diagnostic naming the requested model as unsupported is eligible;
  the surrounding generic HTTP status is not.
- S6 is not an optional catalog probe. The final slice is mandatory adoption:
  capability-bearing Fabro pin, plugin minimum-release floor, server-qualified
  integration proof, and Scenario 127 coverage ownership.

## Mechanical detection result and its interpretation

`detect-impl-gaps --since-version v108` emits 752 candidate ids because
`--since-version` is file-scoped: v109 changed `contracts.md`, so the detector
enumerates every live normative clause in that file, not only lines introduced
by v109. Treating 752 as 752 new implementation defects would be a false
positive.

The new `Factory-configurable ACP fallback priority` heading contains 44
mechanical rule candidates. Scenario 127 contains no BCP-14 keyword and
therefore has no gap id; it needs the heading-coverage binding in the adoption
slice. A detector id means “not yet tracked,” not “implementation proven
absent.” The code audit below establishes the actual absence. Per the
`capture-impl-gaps` contract, none of these ids may be filed without explicit
per-gap human consent.

## Current Dispatcher implementation

The present implementation is deliberately single-candidate:

- `_acp_node_adapters.AcpAdapter` holds one `(command, env, args)` triple.
- `_acp_node_layers.ResolvedAcpNode` holds one adapter and its supplying
  layers; `run_inputs` renders one `<node>_adapter=...` value.
- `_acp_node_repository.repository_acp_overlays` accepts only the legacy
  string/table overlay and the `codex_models` shorthand. Its table parser does
  not reject unknown keys.
- `_dispatcher_acp_nodes.prepare_acp_nodes` journals and launches only that one
  rendered adapter.
- `_dispatcher_provider_exhaustion` is a provider-wide, 15-minute legacy
  record over the fixed provider set `("anthropic", "codex")`; it has no
  schema version, candidate/domain identity, observation id, occurrence-time
  projection, or exact clearance.
- `_dispatcher_cost_pricing.normalize_model_id` accepts arbitrary known-model
  prefixes, and `derive_usd_micros` prices every unknown model as
  `claude-opus-4-8`. Both behaviours directly contradict v109, which permits
  only one trailing date suffix and makes any nonzero unpriceable component
  render the whole successful-run cost unobservable. The table also lacks the
  current `claude-opus-5` workflow default.
- Existing `FabroPort.events(...)` is already server-qualified and is the
  correct transport seam to extend. Projection must not grow a local `fabro
  events` side path.

The prior-art ledger scan found one live overlap: backlog bug `bd-ib-5j4b`
records that a legacy cross-provider `acp_nodes` command replacement can retain
the workflow default's provider-specific env and therefore render two model
identities. v109 does not silently decide that older issue: candidate zero
still resolves through the existing layer order, and no-fallback legacy bytes
remain compatible, while a fallback entry is expressly forbidden from
inheriting another candidate's env. S1 must test both sides. It may reference
`bd-ib-5j4b`, but must not close or supersede it unless the maintainer separately
chooses a disposition for the legacy merge rule.

## Fabro audit: adjacent feature is not this capability

Fabro upstream merged PR 684, “portable model fallbacks,” as merge commit
`2efcc7212` (feature commits `e0f73f963`, `48fd09aaa`, `8a597ca26`). That work
handles the native API-agent backend, uses `[run.model].fallbacks`, and emits
the pre-existing `agent.failover` event. v109 expressly forbids reusing that
event. There is no `agent.acp.failover` event on upstream `main`.

The factory carrier `origin/factory-integration` is currently `977cb67ac` and
does have the ACP backend, steering, per-tool events, and Wave A-C factory
hardening, but it does not contain upstream's portable native-API fallback.
That absence is not itself a blocker: importing the native feature wholesale
would be wrong. Its resolver and error-flow shape are prior art only.

The factory ACP handler currently resolves one `acp.command`, calls
`run_acp_turn` once, and returns every ACP error. Its per-tool events provide
activity evidence but are not the durable side-effect-onset ledger v109
requires. Its checkpoint has no attempted-candidate set, original fallback
deadline, or stable fallback event ids. `SystemInfoResponse` reports version
and build data but no capability list; an integration test even asserts that
`features` is absent. A fallback implementation must deliberately replace that
negative assertion with an additive, typed capability contract while keeping
older clients tolerant of the new field.

Fabro's adjacent `classify_failure_reason` is also unsuitable as fallback
eligibility. It is a broad ordered substring classifier whose first match wins;
the current `fix/classify-provider-spend-limit-not-transient` branch needs 500+
lines of guards and regression cases merely to stop a Cargo source path from
misclassifying one measured provider limit. That classifier may continue to
categorize terminal failures, but S4 must implement the closed candidate
signature grammar, non-eligible pre-checks, and multi-match ambiguity rule as a
separate decision surface. Reusing the heuristic would recreate exactly the
false fallback v109 forbids.

This also fixes the release-order dependency: the Dispatcher cannot safely
enable new grammar merely because its own plugin is new. It must query
`fabro system info --json --server <resolved-target>` (or an equivalently
server-qualified typed client seam) and observe the explicit ACP-fallback
capability on the server that will execute the run.

## Dependency-layered implementation slices

The ids below are provisional filing groups, not consent and not filed work.
Some rules span two slices; the eventual gap item should choose one owning id
and cite the other rules in acceptance criteria rather than create duplicate
owners.

### S1 — closed candidate schema and primary-preserving resolution

Extend the pure adapter/config domain with explicit candidate identity,
fallback entries, closed signature/pricing objects, structural redaction, and
two digests. Resolve the legacy primary completely before attaching metadata or
fallbacks. Preserve byte identity when metadata is absent or only
`fallbacks: []`; preserve the explicit `codex_models.pr` primary. Refuse all
unknown/wrong/duplicate/conflicting new grammar before claim. A legacy
`--acp-node` override remains valid only for a legacy node.

High-risk controls:

- fallback-only or identity-only configuration must not replace the primary;
- no field may inherit from a neighbouring candidate;
- arbitrary primaries must not retain built-in identity;
- the candidate chain must never appear unredacted in journals, traces,
  diagnostics, or refusals;
- credential values and secret references must not enter committed candidate
  data or rendered/run-record surfaces.

Primary candidate ids: `gap-l4psyed6`, `gap-s445a6la`, `gap-4skovge4`,
`gap-3gcxoobc`, `gap-geg5ne3u`, `gap-eotln3fu`, `gap-qspq7y5k`,
`gap-ettinkup`, `gap-im3yns7h`, `gap-zu7qhh5o`, `gap-o3vebjra`.

### S2 — typed classifier, versioned holds, legacy compatibility, and valves

Introduce the closed source/cause/scope classifier, ambiguity refusal, exact
machine-code precedence, normalized conjunctive literal matching, and the
non-eligible-before-matching guard. Replace new observations with schema-v1
domain/candidate records keyed by stable observation id and occurrence time.
Preserve unknown versions as unobservable. Keep legacy provider records
readable and clearable without broadening explicitly identified candidates.
Implement bounded expiry, later matching success retirement, and exact
reason-required attributed clearance.

High-risk controls:

- a pre-turn failure is not provider evidence;
- generic 400/404 and any auth/exit-127/timeout/signal/tool overlap must not
  match a configured text signature;
- runtime multi-match with distinct disposition must be ambiguous and mint no
  hold;
- a successful fallback never clears its failed/skipped primary;
- ingestion time must not refresh expiry.

Primary candidate ids: `gap-ma4amhe3`, `gap-zgaecrho`, `gap-o3vebjra`,
`gap-2crp72ke`, `gap-nskn5h64`, `gap-xywcwo3t`, `gap-22fkst2o`,
`gap-xjibuknd`, `gap-d5hep7le`.

### S3 — success-critical preflight, admission, probe, and idle-factory verdict

Filter candidates in configured order through typed holds and one-evaluation
credential-probe skips. Compute success-critical ACP nodes from the workflow's
green-terminal dominators; currently the result is `implement`, `review`, and
`pr`. Refuse an unsupported/ambiguous graph rather than hard-code a guess.
Admission and rework admission refuse only on an exhausted success-critical
chain. A reached conditional node with no candidate terminates typed before an
adapter and cannot traverse the normal failure/non-convergence edges. Export
one pure verdict shared by admission, wait attention, and idle-factory.

High-risk controls:

- credential probe results create no durable hold;
- a primary-local probe refusal cannot hold a viable fallback loop;
- a conditional empty chain cannot become a `needs_human` or deterministic
  work failure;
- idle-factory must consume the same pure verdict and perform no extra live
  probe.

Primary candidate ids: `gap-ioncmxa3`, `gap-rdw5ltg5`, `gap-7jqdhlgy`,
`gap-thjlihf4`, `gap-unlkyoek`, `gap-qsksxxuq`, plus the amended
idle-factory candidate `gap-pd6xq3tr`.

### S4 — Fabro-owned bounded ACP transition and capability advertisement

In the Fabro repository, add the ACP-specific chain transport, one-visit
handler, stable schema-v1 `agent.acp.failover` event, shared deadline,
attempted/skipped-set checkpoint state, non-retryable post-transition outcome,
and durable external-side-effect onset gate. Preserve the same run id, sandbox,
and predecessor results. Add an explicit server capability advertised through
the remote system-info surface. Keep native `agent.failover` byte-compatible
and unchanged.

The side-effect gate needs its own adversarial proof. An ACP tool-start event is
not enough: onset must be written before an external mutation, unknown evidence
must fail closed, and `pr` must inspect the remote publish branch/PR with
unreadable remote treated as already past onset. Recovery preambles are allowed
only for proven sandbox-local partial state. Resume must not replay an attempted
or preflight-skipped candidate.

Primary candidate ids: `gap-q444mzcy`, `gap-okyvjwew`, `gap-gl463rdv`,
`gap-gtpbrtek`, `gap-aompbvpa`, `gap-4b77bkdn`, `gap-nclfmyzp`,
`gap-5rfmdaz4`, `gap-d7aiquri`.

This slice lives in another repository. A current-tenant blocker edge cannot
represent it honestly. Record the Fabro issue/PR/release as an external
dependency in the adopting orchestrator item, then block adoption on the
capability probe rather than inventing a same-ledger id.

### S5 — idempotent event projection, holds, and fallback warning lifecycle

Fetch from the dispatch's resolved factory target, parse/preserve event
versions, project by stable event id, and replay projection during
reconciliation. On read/parse failure emit one high-urgency per-run-node fact
with the executable server-qualified inspection command and stop unattended
picking. Human-attended explicit dispatch may proceed only after surfacing the
warning. Separately append one idempotent record and one repo/node warning for
every actually executed non-primary candidate, retaining it across later run
failure and clearing it only by a later successful primary attempt of the same
primary generation. Full-chain-only edits must not strand that warning.

High-risk controls:

- read failure is not an empty event stream;
- run absence cannot clear a projection-failure fact;
- projection-fact clearance changes no hold;
- preflight selection for an unreached node emits no warning;
- concurrent older success cannot clear a newer warning.

Primary candidate ids: `gap-axaemm5l`, `gap-sfj37mav`, `gap-ybtz4fhr`,
`gap-nclfmyzp`, `gap-5rfmdaz4`, `gap-d7aiquri`.

### S6 — exact per-attempt successful-run cost

Attribute usage and elapsed time to each attempted candidate and sum all
attempts on successful fallback runs. Replace prefix normalization with exact
identity plus at most one trailing `-YYYYMMDD`; apply a complete explicit
candidate table before a matching built-in endpoint table. Any nonzero
unpriceable component makes the whole run cost unobservable. Remove the current
unrelated-default fallback and add the exact current built-in model table,
including `claude-opus-5`. Preserve the existing no-cost-observation posture
for terminally unsuccessful runs.

Primary candidate ids: `gap-dhqwnajn`, `gap-g7d44dqj`, `gap-gmvy22uc`.

### S7 — release adoption, remote proof, and Scenario 127 coverage

After S1-S6, publish and pin the capability-bearing Fabro build, publish the
first fallback-capable orchestrator release, set `dispatcher.minimum_release`
to that release, and reject new grammar when either the local plugin floor or
resolved remote capability is absent. Run a controlled factory journey where
the primary produces the measured exact unavailable-model diagnostic and the
fallback succeeds in the same node visit. Assert remote events, holds, warning,
cost, unchanged run/sandbox identity, and no predecessor replay. Bind Scenario
127 in `tests/heading-coverage.json` to that consumer-tier test and replace its
temporary TODO.

Primary candidate ids: `gap-j6kfvdht`, `gap-wdianxsa`; Scenario 127 itself has
no mechanical gap id.

## Dependency graph

```text
S1 schema/resolution ─┬─> S3 preflight/admission ─┐
                      ├─> S4 Fabro ACP runtime ───┼─> S5 projection/warnings ─┐
S2 classifier/holds ──┘                           │                           ├─> S7 adoption
S1 schema/resolution ─────────────────────────────┴─> S6 exact cost ─────────┘
```

S1 and S2 can proceed in parallel after their shared wire identities are
agreed. S4 is cross-repository and can proceed in parallel with S2/S3, but S5
must consume its final event schema rather than a guessed duplicate. S7 is the
only slice allowed to enable real fallback configuration.

## Next ledger action

Present the exact S1-S7 draft records and their proposed gap-id ownership for
human consent. On consent, file one item at a time through
`capture-impl-gaps`; do not bulk-create from this note. Whether consent is
given or withheld, finish that capture invocation by recording the complete
detection run against anchor `bd-ib-j5fzyo`, with all surfaced ids and only the
explicitly disposed subset. Until then the correct coverage record is a partial
ATTEMPT, not a false COMPLETED pass.
