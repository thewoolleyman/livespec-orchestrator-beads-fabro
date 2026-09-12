# S5 and S6 draft work-item records for maintainer consent

Written 2026-09-12 by the session resuming plan epic `bd-ib-jxvgq5` after S4
merged. Nothing here is filed. The plan's standing record says S5, S6 and S7
each need maintainer approval before filing; the point of this note is to
make that approval a yes or a no on an exact record, the way S4 was approved
from an exact record on 2026-09-12, instead of a design conversation. Each
record below is complete enough to file verbatim through `capture-work-item`
as a child of `bd-ib-jxvgq5`; the acceptance criteria were checked through
`criteria_lines` and parse as one gradeable assertion per bullet.

Both slices are ordinary in-repository Python and are factory-dispatchable
here. S5 consumes the S4 event schema as merged in the Fabro fork (PR 9,
`20bf91e06`); it does not need that build deployed, because it reads events
through the existing server-qualified `fabro events <run> --json --server`
port and its tests use fixture events. S6 depends on S1's parsed pricing
tables and on the same S4 per-candidate event fields for attribution when a
chain executed; a run with one candidate attributes trivially.

## Why these two are ready and S7 is not

- S2 built the versioned hold ledger writer (`ingest_hold_observation`,
  `hold_observation_record`) but, measured 2026-09-12, nothing in
  `commands/` calls it: no module fetches run events, none mentions
  `agent.acp.failover` outside the ledger modules themselves. S5 is that
  missing wiring plus the two attention facts the contract names.
- The cost path today prices from host OTLP `claude_code.llm_request` spans
  with prefix normalization ("longest match first") and prices an unknown or
  absent model at `DEFAULT_DISPATCH_COST_MODEL` (`claude-opus-4-8`), which
  the ratified clause forbids for a fallback run. S1 already parses the
  per-candidate explicit table (`_acp_candidate_pricing.py`) and states in
  its own docstring that applying it belongs to the cost slice. S6 is that
  application.
- S7 pins a build no host runs yet and needs S5's projection to prove the
  end-to-end journey, so it stays last.

## Plain-language summary for the consent question

S5: when the factory switched a step from its main model to a backup, the
Dispatcher must notice that from the run's own event stream, remember it as
an availability hold so later dispatches skip the bad candidate, and warn a
human that the backup ran. If the events cannot be read at all, that is a
loud, separate warning, and an unattended loop stops picking work in that
repository until someone resolves it.

S6: when a step used more than one model before succeeding, the run's cost
must add up every attempt at each model's real price. If any part cannot be
priced honestly, the whole run's cost is reported as unknown rather than
guessed from a default model.

## Draft record: S5

**Title:** Project ACP fallback events into typed holds, the model-fallback
warning lifecycle, and the projection-failure fact

**Description:**

Implement S5 from plan `bd-ib-jxvgq5` and the ratified "Factory-configurable
ACP fallback priority" contract (v109), the paragraphs "Events and projection
are compatible, idempotent, and leak-free" (Dispatcher half) and "Every
actually executed non-primary candidate appends one idempotent journal
record". Build on S2's ledger writer (`_acp_hold_ledger.ingest_hold_observation`,
`_acp_hold_records.hold_observation_record`, which take occurrence time and
never a clock) and S3's shared preflight verdict. Consume the S4 event schema
as merged in the Fabro fork: `agent.acp.failover` (schema_version 1, stable
`event_id`, occurrence time, node visit, engine attempt, from/to candidate
indexes and identities, `hold_key`, typed `cause` and `scope`,
`primary_generation`, `full_chain`, attempted and skipped sets) and
`agent.acp.exhausted` (the typed terminal outcome). `agent.acp.side_effect` is
engine-internal evidence and is not a hold source.

Scope:

1. Event fetch and projection. After a run reaches any terminal outcome, and
   again during `reconcile-runs`, read the run's events through the existing
   `_fabro_port.events` seam against the dispatch's resolved factory target,
   never the local server. Project each `agent.acp.failover` and
   `agent.acp.exhausted` event into one versioned hold observation keyed by
   the event's stable id, so re-projection is idempotent (first write wins).
   Expiry derives from the event's occurrence time. An event whose
   `schema_version` is not 1 is preserved as unobservable and mints nothing.
2. Projection-failure fact. When the fetch fails, times out, returns
   unparseable output, or the run cannot be found on the resolved target,
   emit exactly one flat attention fact per run and node with id
   `hygiene:model-fallback-projection:<repo>:<run>:<node>`, kind `hygiene`,
   urgency `high`, a source reference to the repository and dispatch journal,
   a deterministic run/node/factory/error summary, and a `shell` handoff
   carrying the same server-qualified inspection command reconciliation uses.
   Repeated failures aggregate into that id. It clears only after a
   successful idempotent projection for the run and node, or through an
   attributed, reason-required, append-only operator clearance naming that
   exact fact id; clearance retires the fact only and touches no hold; run
   absence alone never resolves it.
3. Loop posture under an unresolved projection-failure fact. The unattended
   drain stops picking further work for that repository while any such fact
   is unresolved. A human-attended `--item` dispatch proceeds only after the
   high-urgency warning is surfaced before claim, and it does not clear the
   fact.
4. Model-fallback warning lifecycle. Every actually executed non-primary
   candidate appends one idempotent journal record and yields one aggregate
   attention fact per repository and node with id
   `hygiene:model-fallback:<repo>:<node>`, kind `hygiene`, a valid urgency,
   source reference, and executable inspection handoff; the newest unresolved
   observation supplies the summary. Later run failure does not erase it and
   it never refuses or disposes work. A primary node attempt clears it only
   when that attempt carries the same `primary_generation` fingerprint, began
   after the warning, and completed successfully, regardless of the run's
   later outcome; older concurrent success, unrelated success, credential
   probes, and unexecuted preflight selection cannot clear it. A primary
   replacement retires the prior warning as an append-only `superseded`
   record; a non-primary chain change alters only `full_chain` and leaves the
   warning standing.
5. Leak-free records. Journal records and attention facts carry candidate
   display names, machine keys, hold keys, typed cause and scope, digests and
   ids only: no command text, env value, credential, prompt, raw error, or
   unredacted diagnostic.

Out of scope: per-attempt cost (S6); pinning the capability-bearing build,
the release floor, the remote capability probe, and the end-to-end factory
proof (S7); any change to the fork.

Mechanical ownership: `gap-axaemm5l` is the owning gap id; `gap-sfj37mav`
and `gap-ybtz4fhr` are carried by the same implementation and acceptance
contract. `gap-nclfmyzp`, `gap-5rfmdaz4` and `gap-d7aiquri` were already
disposed into S4 (`bd-ib-mujvyn`) as the event half; this item cites them
for traceability and does not re-own them.

**Acceptance criteria:**

```text
- Terminal-run completion and reconcile-runs both read the run's events through the server-qualified fabro events port against the dispatch's resolved factory target.
- Each agent.acp.failover and agent.acp.exhausted event projects into one versioned hold observation keyed by the event's stable event_id, and re-projecting the same events writes nothing new.
- Hold expiry is computed from the event's occurrence time, and a replayed projection during reconciliation does not move an existing hold's expiry.
- An event whose schema_version is not 1 is preserved, surfaced as unobservable, and mints no hold.
- A fetch failure, timeout, unparseable payload, or missing run on the resolved target emits one attention fact with id hygiene:model-fallback-projection:<repo>:<run>:<node>, kind hygiene, urgency high, a source reference, a deterministic run/node/factory/error summary, and a shell handoff carrying the server-qualified inspection command.
- Repeated projection failures for the same run and node aggregate into the same fact id.
- The projection-failure fact clears only after a successful idempotent projection for that run and node or an attributed, reason-required, append-only clearance naming that exact fact id, and clearance retires no hold.
- Run absence on the resolved target does not clear a projection-failure fact.
- The unattended drain stops picking work for a repository while any projection-failure fact for it is unresolved, and an attended --item dispatch surfaces the high-urgency warning before claim and proceeds without clearing the fact.
- Every actually executed non-primary candidate appends one idempotent journal record and yields one aggregate attention fact with id hygiene:model-fallback:<repo>:<node>, kind hygiene, a valid urgency, a source reference, and an executable inspection handoff whose summary comes from the newest unresolved observation.
- A later run failure leaves the model-fallback warning standing, and the warning never refuses or disposes work.
- A primary attempt clears the model-fallback warning only when it carries the same primary_generation, began after the warning, and completed successfully, regardless of the run's later outcome.
- Older concurrent success, unrelated success, a credential probe, and an unexecuted preflight selection do not clear the model-fallback warning.
- A primary replacement retires the prior warning as an append-only superseded record, and a non-primary chain change alters only full_chain and does not strand the warning.
- Projection journal records and both attention facts contain no command text, env value, credential, prompt, raw error, or unredacted diagnostic.
```

## Draft record: S6

**Title:** Price every candidate attempt of a successful fallback run by
exact emitted identity with no default model

**Description:**

Implement S6 from plan `bd-ib-jxvgq5` and the ratified "Factory-configurable
ACP fallback priority" contract (v109), the paragraph "Cost follows every
attempt in a successful fallback run". Build on the existing host OTLP cost
path (`_dispatcher_cost_sink`, `_dispatcher_cost_pricing`,
`_dispatcher_cost_report`, `_dispatcher_cost_gate`) and on S1's parsed
per-candidate pricing table (`_acp_candidate_pricing.AcpCandidatePricing`,
whose docstring assigns application to this slice). Read per-attempt
boundaries from the S4 events as merged in the fork: `agent.acp.started` now
carries `candidate_index` and `chain_deadline_epoch_ms`, and
`agent.acp.failover` carries per-candidate `attempted_durations_ms`.

Scope:

1. Per-attempt attribution. For a run whose node executed a candidate chain,
   attribute observed token usage and elapsed time to each candidate attempt
   by its attempt window, including failed attempts before the successful
   fallback, and sum every attempt into the run's cost. A run with a single
   candidate attributes exactly as today.
2. Exact identity. Replace prefix normalization with exact model identity
   normalized only by stripping one trailing `-YYYYMMDD` date suffix; any
   broader prefix match is not identity. A built-in price applies only when
   the emitted identity matches a built-in candidate's model and endpoint.
3. Explicit table precedence. When the candidate that ran carries a complete
   explicit pricing table and the emitted identity matches its `model`, that
   table prices the attempt ahead of any built-in entry.
4. No default, no free. Remove the `DEFAULT_DISPATCH_COST_MODEL` fallback for
   fallback-enabled runs: an emitted identity with no matching explicit or
   built-in price makes the whole run cost unobservable, never a partial
   subtotal, never a default-priced estimate, and never zero. Add
   `claude-opus-5` to the built-in price table (a retained review hazard from
   the v109 revise).
5. Posture preserved. The existing fail-closed cost gate keyed on `--item`
   presence remains authoritative for an unobservable cost, and terminally
   unsuccessful runs keep the current no-cost-observation, no-gate posture.
   The cost report's `model_basis` names every priced identity and reports
   `model_resolved` false when any attempt was unpriceable.

Out of scope: the hold projection and warning lifecycle (S5); pinning,
release floor, and the end-to-end proof (S7); any change to the fork.

Mechanical ownership: `gap-dhqwnajn` is the owning gap id; `gap-g7d44dqj`
and `gap-gmvy22uc` are carried by the same implementation and acceptance
contract.

**Acceptance criteria:**

```text
- Token usage and elapsed time are attributed to each candidate attempt of a node by its attempt window from the run's agent.acp.started candidate_index and agent.acp.failover attempted_durations_ms fields.
- A successful fallback run's cost sums every attempt, including failed attempts before the successful fallback.
- A run whose node executed a single candidate is priced exactly as before this change.
- Model identity is normalized only by stripping one trailing -YYYYMMDD date suffix, and a broader prefix match does not select a price.
- A built-in price applies only when the normalized emitted identity matches a built-in candidate's model and endpoint exactly.
- A candidate's complete explicit pricing table prices its attempt ahead of any built-in entry when the emitted identity matches the table's model.
- An emitted identity with no matching explicit or built-in price makes the whole run cost unobservable rather than a partial subtotal, a default-priced estimate, or zero.
- The built-in price table contains claude-opus-5.
- An unobservable cost still routes through the existing fail-closed cost gate keyed on --item presence.
- A terminally unsuccessful run keeps the existing no-cost-observation and no-gate posture.
- The cost report names every priced identity in model_basis and reports model_resolved false when any attempt was unpriceable.
```

## What filing would do, if approved

File S5 first, then S6, each through `capture-work-item` as a child of
`bd-ib-jxvgq5` with `origin: gap` and the owning gap id above, run the
intake checklist so each lands at `ready`, and record one scope event per
item naming the carried gap ids and the S7 deferral. Both are factory work:
dispatch through `drive --action impl:<id>`; S6 may run in parallel with S5
because they share no module.
