# ACP provider-cap retry reproduction, 2026-10-02

The exact `v0.371.0-nightly.0` candidate **retries both recorded provider-cap
errors**. With `max_retries=1`, each fake ACP agent receives two prompt
requests, and both attempts report failure class `retry_requested`. This
confirms the runtime defect suspected in assessment 003; it is not a fix or
a qualification pass. Do not deploy this candidate on the strength of its
final `deterministic` failure category.

## Recovery reconciliation and scope

Recovery resumed the ledger handoff on epic `bd-ib-6tcjfx` dated
2026-10-01T19:27:44.362841+00:00. Before starting new work, the session
confirmed that evidence PR #2534 was merged, P0 `bd-ib-kqbuju` was closed,
the orchestrator primary checkout was clean, and the safety branch still
held `61e6a4dfed458a4cb5b8c61b8734973d78f3982c`. No child agents or existing
factory runs belonged to this session. The hp factory initially reported
no live runs. The retired vps endpoint returned 502; its retirement was
already documented, so it was not treated as an outage to repair.

The separate Fabro session owns its status/review work. This session did
not upgrade a shared factory, touch the Codex daemon or tmux sessions,
rewrite a carrier, or mutate an upstream repository or existing upstream
PR head. All executable experiments used the previously downloaded exact
candidate in fresh local storage. Existing unpublished work was preserved.

## Reproduction and controls

Run the adjacent script with Python 3 and the exact Linux x86-64 binary:

```sh
python3 plan/fabro-currency/research/004-acp-spend-limit-repro.py \
  /home/ubuntu/.local/state/fabro-currency/v0.371.0-nightly.0/fabro-x86_64-unknown-linux-gnu/fabro
```

The script refuses a binary whose SHA-256 differs from
`bd6366c6b1ce687c92944c48c005f042fc7cdd3e298d51ce5d849788fe478447`.
It creates a fresh temporary directory, starts a private Unix-socket
server with explicit configuration and storage, and sets a separate
`FABRO_HOME`. Its child environment excludes inherited credentials and
factory targets. Clone and run-branch push are disabled. Each case targets
an empty directory, not a checkout. The only ACP process is the adjacent
`004-fake-acp-agent.py`; it never invokes a model or provider API.

This candidate refuses even the ACP-only graph without a ready provider.
The fixture therefore stores the deliberately invalid value
`local-fixture-invalid-key` under `OPENAI_API_KEY` in its own private
server vault. Merely setting that variable in the server environment did
not satisfy admission. No real provider credential was read, copied, or
used. Private-server authentication uses newly generated fixture values.

Every graph has one ACP node with `max_retries=1` and `goal_gate=true`.
The fixture records each actual `session/prompt` request, independently of
the server event stream. The script checks both observations, final run
status, and CLI exit status. It saves raw events and `inspect --json`
output before terminating only its own server in a `finally` block.
Evidence remains on disk; it does not reap shared runs or delete storage.

| Fixture response | Actual prompt attempts | Attempt result | Terminal run / CLI exit |
| --- | ---: | --- | --- |
| Successful answer | 1 | Success | Success / 0 |
| Process exits on first prompt, then answers | 2 | `retry_requested`, then success | Success / 0 |
| Monthly organization spend-cap error | 2 | `retry_requested` on both | Failed / 1 |
| Usage-limit/reset-time error | 2 | `retry_requested` on both | Failed / 1 |

The two cap responses use JSON-RPC error code `-32603`, the previously
recorded provider messages, and `data.errorKind = "rate_limit"`. They
model the ACP error-response path, not a live provider account or every
possible adapter envelope. The process-exit control establishes that
ordinary retry behavior remains observable through the same instrument.

The final detached receipt is `20261002T214501Z-4128768`, which completed
2026-10-02T21:45:29Z with exit 0. **That exit means reproduction succeeded;
the candidate failed the desired no-retry behavior.** The four run IDs,
selected unmodified event fields, final inspection fields, binary hash,
and tested runner and fake-agent hashes are committed in
`004-acp-spend-limit-evidence.json`. Full experiment output is retained
locally at `/tmp/fabro-currency-acp-uknj04zn`; the committed summary and
reproducer do not require that temporary directory to survive.

Earlier exploratory runs established protocol viability. One packaged
attempt (`20261002T212826Z-3968645`) failed before any run because its
synthetic session secret was too short; that fixture error was corrected.
The subsequent receipts `20261002T212907Z-3973713` and
`20261002T213231Z-4005759` reproduced the same retry behavior. Receipt
`20261002T213322Z-4014836` added saved final inspection output and complete
exit/status assertions. The final receipt repeats them after splitting the
fake agent into its own file and conforming to repository Python conventions.

The first aggregate check (`20261002T213611Z-4038986`) found one failure in
the new fixture's mechanical Python-convention test: keyword-only arguments,
module exports, stdout ownership, and the logical-line soft ceiling. The
fixture was corrected, not the gate weakened; the focused three-test module
then passed. The two explicit `pyproject.toml` supervisor entries declare
their command-line stdout contracts (evidence JSON and ACP JSON-RPC), not a
tree-wide exclusion. When this plan is eventually archived, those two paths
must move with it; the normal outside-plan reference sweep will enforce that.

## Two observation traps

First, without `goal_gate=true`, a simple unconditional edge to the exit
node allows the failed probe to be followed by a successful terminal run.
The initial scratch experiment observed CLI exit 0 despite two failed cap
attempts. The goal-gated final fixture avoids treating graph completion
as proof that the agent succeeded.

Second, final `inspect` output reports category `deterministic` for both
cap failures, while the attempt events report `retry_requested`.
It also reports `conclusion.total_retries = 0` for the cap cases **and
the successful process-exit retry control**, although their prompt logs
and events independently show attempts 1 and 2. Do not use either summary
field as a proxy for an attempt-level no-retry assertion. This is a
measured projection discrepancy, not a claim about every retry path.

## Ownership and disposition

The source chain in assessment 003 remains the relevant seam: the locked
Petri revision `98144f107fcdd290a44699a8e76abf6e6f63fe2a` converts generic
ACP errors to `retry_requested` in
`crates/attractor/steps/src/agent/backend.rs`. Fabro's
`lib/components/fabro-petri/src/projection/coordinator.rs::conclude`
maps ordinary failed runs to `FailureCategory::Deterministic`. The live
measurements now establish why correcting only that projection would not
prevent the extra provider attempt.

This completes the outstanding local reproduction portion of
`bd-ib-m637al`, not its implementation or upstream-disposition criteria.
A successor must classify permanent provider-cap refusals before the
retry decision, prove one prompt attempt for each cap, preserve retry for
the transient/process-exit control, and check the consumer-facing failure
and retry fields. Keep successor work on a new user-owned fork branch;
do not push the existing upstream PR #688 head. No upstream action is
authorized by this receipt, and no item or plan is closed by it.

The broader no-go from assessment 003 remains: production graph syntax
and ACP fallback behavior also need migration. The full isolated
qualification matrix, replacement timeout coverage, and spec-gap
disposition are still separate work. A candidate upgrade is not the next
safe action merely because this private server started successfully.
