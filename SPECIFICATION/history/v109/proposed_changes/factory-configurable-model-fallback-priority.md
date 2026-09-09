---
topic: factory-configurable-model-fallback-priority
author: codex-gpt-5
created_at: 2026-09-09T11:13:49Z
---

## Proposal: Per-node ACP fallback chains preserve failure honesty

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- ../tests/heading-coverage.json

### Summary

Add a backwards-compatible, per-node ordered ACP-adapter fallback chain that can cross providers, skips candidates covered by observed availability holds, reacts inside the failing Fabro node without replaying the workflow, and makes every non-primary use visible without converting deterministic work failures into availability failures.

### Motivation

A removed ChatGPT-account model caused the publish node to fail after roughly forty minutes of successful implementation and review work because each ACP node resolves exactly one adapter. Moving the default away from that model removed the immediate outage but left every configured model as a single point of failure. Plan factory-configurable-model-fallback-priority (epic bd-ib-jxvgq5) requires provider-generic ordered fallback while preserving the existing observed-not-predicted exhaustion and failure-honesty contracts.

### Proposed Changes

This change is additive at the configuration boundary but it is not isolated to
`ACP node adapter configuration`: the revision MUST co-edit the existing
provider-containment, admission/rework-admission, idle-factory, wait-fact,
operator-clearance, cost, Fabro-runtime-boundary, and Codex-pin clauses whose
single-provider assumptions fallback makes stale. It MUST also amend Scenarios
60, 85, 87, 94, 116, 120, and 121, preserve Scenario 88's no-fallback behavior,
and add the new scenario below. A second, contradictory hold or
warning system beside the existing one is forbidden.

#### Chain grammar and resolution

Extend `ACP node adapter configuration` with an additive fallback-chain grammar.
The Dispatcher MUST first resolve candidate zero through the existing layers in
their current order: workflow default, `codex_models` shorthand, explicit
repository `command`/`env`/`args`, then per-dispatch adapter override. Only after
that adapter is resolved may repository identity metadata and fallback entries
be attached. Therefore a table containing fallback metadata but no primary
`command`/`env`/`args` MUST NOT shadow an explicit `codex_models` primary or
restore the workflow default. With no fallback fields, or with
`fallbacks = []`, configuration and rendered adapter bytes MUST be identical to
v107: an unconfigured `pr` remains the Claude Haiku 4.5 default and an explicit
`codex_models.pr` remains the resolved candidate zero.

A fallback-enabled node's primary and every fallback entry MUST carry three
non-empty, non-secret identity fields: `display_name` for operators,
`candidate_key` for stable machine identity, and opaque `availability_key` for
the default allowance/account/endpoint domain. Display text MUST never be a hold
key. The pair `(availability_key, candidate_key)` identifies one candidate
entitlement and MAY intentionally be repeated across nodes so one exact-model
hold applies in both; different accounts or routers MUST use different keys.
Built-in workflow primaries receive stable built-in identity metadata only while
the finally resolved adapter still matches that built-in. A fallback-enabled
arbitrary primary produced by `acp_nodes` MUST carry explicit identity metadata;
it MUST NOT retain a replaced built-in's identity or run unidentified. Every fallback entry is a complete
adapter definition: `command` is required and omitted `args` or declared adapter
`env` mean empty values. A fallback MUST NOT inherit another candidate's
command, args, declared env map, model identity, signatures, identity, or
pricing. This non-inheritance does not promise per-process credential isolation:
container-level credentials remain shared under the existing Worker credential
projection contract.

An identity-less arbitrary single-adapter override with no fallback fields keeps
the v107 legacy provider-containment path and cannot mint or consume current
typed holds. That compatibility posture lasts until the operator opts the node
into explicit identity metadata; the implementation MUST NOT invent an identity
from command text. Such a candidate is conservatively covered by every
unexpired legacy provider record and continues to mint legacy records through
the v107 cause-text attribution path; declaring explicit identity is the only
route out of that blanket legacy posture.

The legacy string-valued `--acp-node NODE=ADAPTER` remains unchanged for a node
without new grammar metadata. On a new-grammar-enabled node it MUST refuse before
claim because it carries no safe candidate/domain identity; it MUST NOT retain
stale identity, become hold-exempt, or infer identity from command text. A
future structured chain override requires a separate ratified syntax. Unknown,
duplicate-key, incomplete, or conflicting new-grammar metadata
MUST be refused before claim or run creation. A new-grammar-enabled dispatch also
MUST refuse before claim when the installed Dispatcher or pinned Fabro runtime
does not advertise the ratified fallback capability; an older build silently
ignoring the new keys is never a successful dispatch.

"New-grammar-enabled" means any identity, signature, pricing, or non-empty
fallback field is present; `fallbacks: []` with no other new field remains the
explicit byte-identical no-op. New-grammar enablement additionally requires committed `dispatcher.minimum_release`
at or above the first fallback-capable plugin release, which is the existing
operator-controlled floor that makes an older Dispatcher refuse rather than
silently ignore the feature. From that release onward, an `acp_nodes` object
with any key outside the ratified grammar MUST refuse before claim. The Fabro
capability/version MUST be queried from the dispatch's resolved factory server,
never inferred from a local `fabro` binary. The existing `acp_nodes`-wins wording
MUST be narrowed: it wins over `codex_models` only for the primary
`command`/`env`/`args` fields it actually sets; identity-only and fallback-only
fields attach after the shorthand primary resolves.

Every Codex candidate, whether primary or fallback, continues to obey the v107
pin, posture, baked-path, and empty-model opt-out rules. Amend the stale v107
statement that an unreachable pin fails every dispatch: an unreachable
candidate may advance only when its exact typed failure is fallback-eligible;
otherwise it still terminates the node. Verification-run guidance applies per
new or changed primary/fallback candidate rather than assuming one adapter.

#### Failure classification and scope

Each candidate MAY declare committed, provider-generic
`availability_signatures` with this closed JSONC shape (all objects reject
unknown keys):

```jsonc
{
  "display_name": "operator text",
  "candidate_key": "stable-candidate",
  "availability_key": "default-domain",
  "command": "adapter",                 // required on a fallback
  "args": ["literal", "non-secret"],   // optional; defaults to []
  "env": {"NAME": "non-secret value"}, // optional; defaults to {}
  "pricing": {                           // optional; all-or-none
    "model": "exact-emitted-model",
    "input_usd_per_million": 0.0,
    "output_usd_per_million": 0.0,
    "cache_write_usd_per_million": 0.0,
    "cache_read_usd_per_million": 0.0
  },
  "availability_signatures": [
    {
      "source": "protocol.machine_code",
      "machine_code": "exact.nonempty.code",
      "cause": "model_unsupported",
      "scope": "candidate"
    },
    {
      "source": "protocol.message",
      "all_literals": ["usage limit", "requested model"],
      "exit_code": 1,
      "cause": "quota",
      "scope": "availability-domain",
      "hold_key": "optional-domain-override"
    }
  ]
}
```

`source` is exactly `protocol.machine_code`, `protocol.message`, or
`process.terminal_diagnostic`. `cause` is exactly `quota`, `rate_limit`,
`provider_capacity`, `provider_server_unavailable`, `model_unavailable`,
`model_not_found`, `model_unsupported`, or `model_not_entitled`. `scope` is
exactly `availability-domain` or `candidate`. The machine-code source requires
exactly one non-empty `machine_code` and forbids `all_literals`; the other
sources require a non-empty array of non-empty `all_literals` and forbid
`machine_code`. `exit_code`, when present, is an integer from 1 through 125 and
only refines the required discriminator. A domain signature MAY carry one
non-empty, non-secret `hold_key` and otherwise defaults it to
`availability_key`. A candidate signature forbids `hold_key` and is keyed
exactly on `(availability_key, candidate_key)`. Missing required fields,
wrong-typed fields, forbidden combinations, duplicate identities within one
node chain, and statically identical conflicting signatures refuse the complete
configuration before claim. Cross-node identity reuse remains intentional. A
candidate belongs to its `availability_key` domain plus every override
`hold_key` declared by its domain signatures, so preflight membership is
deterministic. If distinct configured signatures nevertheless match one runtime
diagnostic with different cause/scope/key dispositions, the failure is
non-eligible, surfaced as ambiguous, and creates no hold; runtime first-match
selection is forbidden.

The matching grammar is closed. Its source is one of
`protocol.machine_code`, `protocol.message`, or the adapter process's separately
captured terminal startup/termination diagnostic; arbitrary exec-output tails
are excluded. A structured machine code is preferred. Text matching uses a
declared conjunction of non-empty literal markers after Unicode case-folding
and whitespace normalization, never a regular expression. An exit status MAY
only refine a machine-code or literal match and is never sufficient by itself;
0, 126, 127, signal termination, and every status 128 or greater are forbidden.
Statically identical conflicting signatures refuse configuration; a runtime
multi-match with differing dispositions is non-eligible and surfaced. Neither
case may pick the first match.
The non-eligible exclusions take precedence over every
configured marker or exit code: authentication, command-not-found, cancellation,
ACP node deadline or stall expiry, generic HTTP 400/404, remote-compaction 404,
malformed command/configuration, sandbox or un-attributed DNS/transport failure,
code/test/review/tool failure, and non-convergence terminate with their original
identity. A provider-attributed structured transport diagnostic may be proposed
later; mere occurrence before the first turn is not availability evidence.

The built-in Claude and Codex candidates MUST ship exact, measured mappings for
stable diagnostics exposed by the pinned adapters, including the recorded
ChatGPT-account diagnostic that names the requested model as unsupported. A
generic 400 remains ineligible; the exact model-naming discriminator makes that
known diagnostic candidate-scoped. Implementations MUST match only the terminal
ACP protocol/process fields above, never agent response text, prompt content,
tool/test/review output, or arbitrary run logs. An unmatched or first
non-eligible failure terminates the chain honestly.

#### Versioned observed holds and preflight

Replace the existing provider-only exhaustion identity with a versioned observed
availability record containing at least `scope`, `hold_key`, optional
`candidate_key`, stable `observation_id`, occurrence time, bounded expiry, and
explicit `schema_version: 1`. Unknown versions MUST be preserved and surfaced as
unobservable rather than ignored, interpreted as v1, or rewritten.
Legacy provider records remain readable, clearable by their current valve, and
honored until retirement as availability-domain holds against candidates whose
built-in compatibility alias names that provider, plus the explicitly carved-out
identity-less legacy candidates above, which every live legacy record covers.
For explicitly identified candidates, legacy records MUST NOT be silently
ignored or broadened to unrelated identities. Typed per-candidate evidence takes
precedence over legacy cause-text attribution whenever a chain executed.

The three existing retirement routes remain, with scoped meanings. Expiry is
computed from failure occurrence, never ingestion. A node execution that began
after a domain observation and completes successfully on the same hold key
retires only that older domain hold; a later success by the exact
`(availability_key, candidate_key)` retires only that older candidate hold. A
fallback success never clears a skipped or failed primary merely because the
run later succeeds. Operator clearance gains an exact scope/key valve, remains
attributed, reason-required, append-only, and refuses nonexistent live holds;
the legacy provider valve continues to address legacy records only.

Before dispatch, the Dispatcher resolves every node chain against unexpired
holds in configured order. A domain hold skips candidates sharing that hold key;
a candidate hold skips only the exact identity pair. It MUST NOT reorder by
predicted health, price, or strength or derive a hold from credentials, catalogs,
host probes, or provider reset-time claims. A workflow MUST expose which ACP
nodes dominate every green terminal path; those success-critical nodes are
admission-required (the current workflow includes `implement`, `review`, and
`pr`). Admission refuses before claim only when one such node has no candidate.
A conditional repair/adjudication node may have no unheld candidate at preflight,
but if reached it fails typed before starting an adapter. That typed no-candidate
failure MUST terminate the run with the availability cause surfaced; it MUST NOT
traverse the node's continuation or failure edge into janitor, non-convergence,
or `needs_human`, and the Dispatcher MUST NOT reclassify it as deterministic
work failure or non-convergence. This avoids refusing
healthy runs for unused repair paths without recreating a forty-minute late
publish attempt. An unsupported/ambiguous workflow graph refuses fallback-enabled
dispatch rather than guessing. Admission, rework admission, idle-factory, wait
completeness, and Scenarios 60/94/116/121 MUST all consume this same per-node verdict,
so a viable fallback makes the item dispatchable and an exhausted required chain
does not.

The existing admission-time credential probe does not create observed evidence.
For a fallback-enabled chain, a provider-limit/rate-limit probe refusal is an
ephemeral candidate-local skip for that one admission evaluation only; the
Dispatcher continues to the next candidate and MUST NOT hold the whole loop
while any success-critical chain remains viable. If every candidate is locally
unusable, admission may refuse for the empty chain, but no durable hold is
minted. Scenario 121 MUST be amended so its re-probe wait applies to the legacy
single-candidate path and to a genuinely exhausted fallback chain, never to a
primary-only probe refusal with a viable fallback.

#### Same-node reactive execution and side effects

The observable integration contract is one Fabro run id, one sandbox identity,
one bounded node visit, no predecessor-node replay, ordered typed attempts, and
normal continuation after success. The Fabro repository owns its internal
classifier/handler change and this repository consumes a capability-bearing
pinned release; the current paragraph declaring the in-sandbox classifier out
of scope MUST be narrowed for this explicit integration seam rather than left in
contradiction.

All candidates in one node chain share the node's single wall-clock deadline;
each successor receives only the remaining time, and timeout derivation remains
one node timeout rather than candidate-count times timeout. Within one engine
handler attempt, candidates are attempted at most once and in order. The event
records `engine_attempt` separately from `candidate_index`. If no failover has
occurred, an existing outer retry for a non-eligible transient failure MAY retry
the preflight-selected candidate under current semantics. Once the first
reactive transition occurs, that node visit is non-retryable: no outer retry may
replay any part of the chain. Attempted/skipped identities, the original node
deadline, and occurrence ids survive checkpoint/resume. Exhaustion is a typed,
non-retryable node outcome that preserves the final underlying cause.

Sandbox-local partial changes MAY pass to a successor; they MUST NOT be
discarded. The successor receives the original task plus a delimited recovery
preamble naming the interrupted candidate and requiring inspection of current
local state. Reactive fallback requires durable proof that every completed tool
operation in the attempt was sandbox-local and that no external effect began.
The runtime's side-effect ledger MUST write an onset record before issuing an
external mutation; missing, incomplete, or unknown evidence is fail-closed and
terminates with the original failure instead of falling back. Reactive fallback
after an onset record is permitted only when the node declares durable
idempotent/resumable semantics and the successor receives the corresponding
idempotency key, resume identity, and observed remote state. In particular, the
current `pr` node MUST NOT fall back after push/publication/auto-merge arming has
begun until those operations carry such write-ahead records, durable idempotency
keys, and resume checks. The runtime MUST NOT infer absence from a missing event
or claim that preserving a sandbox rolls back remote effects. Onset is a
declared per-node observation; for the current `pr` node, a publish branch or its
pull request present on the remote at takeover time proves onset, and inability
to make that observation is treated as already past onset.

#### Events, projection, warnings, and secrets

Do not reuse Fabro's incompatible native-API `agent.failover` wire shape. Each
transition emits a versioned `agent.acp.failover` event with a stable event id,
explicit `schema_version: 1`, occurrence timestamp, node visit, engine attempt, candidate indexes and elapsed
durations, from/to display and machine identities, selected hold key, canonical
cause and scope, a primary-generation fingerprint, and a separate full-chain
digest. It contains no adapter
command, env value, credential, prompt, raw error, or unredacted diagnostic.
Historical `agent.failover` events and their consumers remain unchanged and gain
round-trip regression coverage. Unknown `agent.acp.failover` versions MUST be
round-tripped byte-for-byte and surfaced as unobservable; they MUST NOT mint a
hold or silently disappear.

The Dispatcher reads events from the run's resolved factory target, projects
them idempotently by event id, calculates holds from occurrence time, and can
replay projection during reconciliation after a crash. Failure to read the
correct event stream is not evidence that no failover occurred. It emits exactly
one flat fact per run/node with id
`hygiene:model-fallback-projection:<repo>:<run>:<node>`, existing `hygiene`
kind, `high` urgency, a source reference naming the repository and dispatch
journal, a deterministic summary naming run/node/factory target and the read
failure, and a `shell` handoff containing the same resolved, executable
server-qualified event-inspection command reconciliation uses. Repeated failures
aggregate into that same id; the fact clears only after an idempotent replay
successfully reads and projects that run/node, or after an attributed,
reason-required, append-only operator clearance naming that exact fact id. Such
a clearance retires only the projection-failure fact and MUST NOT mint, retire,
or reinterpret a hold; run absence alone is never resolution. An eligible transition mints its
correctly scoped hold even when fallback makes the run succeed. Every executed
non-primary candidate also
appends a journal record and surfaces exactly one aggregate attention fact per
repository/node with stable id `hygiene:model-fallback:<repo>:<node>`, existing
`hygiene` kind, valid urgency, source reference, and executable inspection
handoff. The newest unresolved observation deterministically supplies its
summary; later run failure does not erase it and it never refuses or disposes a
work item.

While any projection-failure fact remains unresolved, an unattended loop MUST
stop further picking for that repository so unread evidence cannot repeatedly
burn the same primary. A human-attended `--item` dispatch MAY proceed only with
the high-urgency warning surfaced before claim; it does not clear the fact.

A primary execution clears only a warning from the same primary generation when
that node attempt began after the warning and completed successfully, regardless
of the overall run's later outcome. Older concurrent success, unrelated
provider success, probes, and unexecuted preflight selection cannot clear it. A
committed primary replacement retires the old generation as `superseded` with
an append-only record, preventing an immortal warning for an intentionally
removed primary. Reordering or changing only non-primary entries changes the
full-chain digest but not the primary-generation fingerprint, so it cannot
strand an otherwise clearable primary-health warning.

For a fallback-enabled node, `command`, `args`, and declared `env` are public committed data and MUST
contain no literal credential, token, or secret reference. Candidate credentials
MUST arrive only through the existing Worker credential projection; adding a new
provider credential channel requires a separate ratified change. A legacy node
with no fallback fields retains v107's arbitrary-adapter env behavior and
Scenario 88 unchanged. A projected credential is supplied as a child-process
environment key through the uncommitted overlay and MUST be omitted from the
rendered adapter string, run input, run record, and trace; absence MUST NOT be
inferred from redaction. The existing
journal rule requiring the rendered
adapter string MUST be amended: execution still receives the exact rendered
bytes, but journals, diagnostics, traces, events, and refusal messages store a
redacted structural representation (command/args, env key names and supplying
layers) plus a deterministic digest, never raw env values or the full chain.
Existing Codex-pin assertions against `run_turn.command` MUST compare the clear
command/args plus that digest instead of requiring raw env values in the trace;
the digest remains the byte-identity proof.
`display_name`, `candidate_key`, `availability_key`, hold keys, the primary
generation, and the full-chain digest are explicitly non-secret because they
surface operationally.

#### Cost

For a run that reaches successful terminal outcome through fallback, token usage
and elapsed time are attributed and summed per candidate attempt, including its
preceding failed primaries, rather than only the successful fallback. A run that
terminates unsuccessfully retains the existing no-cost-observation/no-gate
posture; this change does not silently widen the gate to failed runs. Exact
emitted model identity, normalized only by stripping one trailing `-YYYYMMDD`
date suffix (ratified here; any broader prefix match is not exact identity),
selects built-in pricing only when the executing
candidate and endpoint also have the matching built-in identity. For an
arbitrary candidate, its exact-model matching explicit table takes precedence.
A candidate MAY carry an
explicit all-or-none price table naming the exact model it prices and finite,
non-negative USD-per-million input, output, cache-write, and cache-read prices;
that table applies only when the emitted model identity matches. If any nonzero
usage component from any attempt cannot be priced, the whole run cost is
unobservable—never a known partial subtotal—and the existing fail-closed
unobservable-cost posture remains authoritative. An unknown candidate is never
priced as an unrelated default model or treated as free.

#### Scenario and coverage

Add a numbered scenario covering two success-critical node chains. The first
skips a domain-held primary and executes its next candidate. The second primary
emits the exact built-in, candidate-scoped model-unsupported diagnostic after a
strictly sandbox-local partial write and before any external effect; the next
candidate continues the same node, sandbox, and remaining deadline with a
recovery preamble. Both transitions surface idempotent journal/warning evidence
and correctly scoped holds even though the run succeeds; a later primary node
success clears only its own same-generation newer warning/hold.

The scenario also proves: the v107 unconfigured Haiku `pr` bytes and explicit
Codex primary are unchanged; fallback-only metadata does not shadow that
primary; shared and distinct identity keys scope holds across nodes correctly;
legacy records remain effective; a conditional node with no candidate does not
refuse admission but fails typed if reached; a generic HTTP error,
authentication failure, exit 127, signal/timeout, sandbox transport fault, and
code/test failure do not fall back even when text overlaps; a model hold leaves
another model on the same domain eligible; external-side-effect onset forbids
unsafe takeover; one deadline bounds the chain; exhaustion and post-transition
checkpoint/resume never replay it; duplicate/replayed events do not duplicate
records; event-read failure is visible; older concurrency cannot clear newer
facts; superseded primaries retire warnings; every attempt contributes cost and
one unknown component makes the run unobservable; and an unexecuted preflight
selection emits no warning. Update `../tests/heading-coverage.json` atomically with
the new heading.
