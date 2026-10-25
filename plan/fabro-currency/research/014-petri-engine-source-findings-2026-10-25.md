# Petri engine source findings, 2026-10-25

Session: claude:fabro-currency (Claude Code session fabro-currency [84b3fb]), working the
coordinator's stability tier (gitops-fleet-capacity-monitoring, epic
`livespec-dev-tooling-dfixhe`).

All three findings were read against the Petri commit gmktec serves. The serving Fabro
carrier is `carrier-candidate-registered-20261023` at `9f6c38fab`. It patches every Petri
crate to `thewoolleyman/petri` branch `fabro-integration-registered-20261023`, and its
`Cargo.lock` pins `e92b191`. The two engine items below are therefore Petri work, not
Fabro-fork work. `.ai/fabro-fork-hand-build.md` describes the Fabro fork's
`factory-integration` route, so it does not apply to them as written.

## 1. The review-label misroute (`bd-ib-7smzwo`): cause and fix

The label is read in `crates/attractor/steps/src/directive.rs`. `parse()` takes the last
JSON object with a routing field from `json_objects(text)`. That function was one depth
counter over the whole response, and it emitted an object only when the depth returned to
zero.

An unbalanced opening brace in prose left the depth at 1 or more. The misrouted review
quoted two lone opening braces and no closing one. The trailing label object's own
braces then moved the depth from 1 to 2 and back to 1, so the object was never emitted.
Once the depth was raised, prose quote marks also toggled string mode.

`parse()` then returned `Missing`, so `preferred_label` was never set and the review fell
through edge 45 to `needs_human`. That matches the same-engine control: run `01M5KCE576P6`
had no braces before its label object, and it recorded the label.

The fix resumes the scan one byte past an object still open at the end of the response.
It is thewoolleyman/petri#2, merged as `565ac47` on `fabro-integration-registered-20261023`.
A response with no routing object still reports `Missing`.

Local gate against `9b8cd29`:

- `cargo +nightly-2026-04-14 fmt --check --all` passed.
- `cargo nextest run -p petri-attractor-steps --all-features` passed 206 of 206, with
  `PETRI_SANDBOX_DOCKER_PLUGIN` and `PETRI_SANDBOX_HOST_PLUGIN` set.
- `cargo +1.97.1 clippy ... -D warnings` passed.

Two instrument traps came up on this host, and each cost a run:

- Without the sandbox plugins, three directive command-node tests fail. They failed
  identically on the unmodified base, which was the control.
- The rustup default nightly hits an internal compiler error on the core crate
  `petri-steps`. The pinned 1.97.1 toolchain is the one that counts, and the host's mise
  (2026.2.7) cannot run Petri's `mise.toml`, which requires 2026.6.11.

The fix is not deployed. The item's host-captured assertions need a gmktec redeploy, which
the maintainer's 2026-10-24 hold on further upgrades governs.

## 2. Stop-reason recording (`bd-ib-odi6dr`) is two mechanisms

**Assertions 1 and 2, the stop reason in the run events and the stage outcome, are Petri
engine work.** `AcpClient::prompt` in `crates/attractor/steps/src/acp/mod.rs` matches the
`session/prompt` response's `stopReason` and then drops it:

- `end_turn` and `refusal` pass.
- `cancelled` is handled.
- Anything else becomes `AcpError::StopReason`.

`struct Turn` carries only `text`, and `agent/backend.rs` returns `turn.text`. So a
`refusal` is booked exactly like an `end_turn`, and nothing downstream can record either
reason.

**Assertion 3, an implement turn with no completion field booked as a failed step, needs
no engine change.** Petri's agent step already enforces a node output contract:

1. `agent.rs` validates the final reply against the node's `output_schema`.
2. It runs `output_retries` repair turns (default 2).
3. It then fails the step with class `bad_output`. The message names each schema
   violation, including a missing required property.

The frontend lowers `output_schema` for ACP agent nodes (`lower/nodes.rs`, and `lints.rs`
under `Kind::Agent`). So declaring an `output_schema` on this repository's `implement`
node, requiring `definition_of_done_complete`, makes the engine book the missing field as
a failed implement step. Only the `petri` factory is configured, so no pre-Petri engine
reads the graph.

The workflow comment above `implement_completion` says the engine decides an outcome only
from the structured ending. That was true before Petri and is stale now.

Proposed to the coordinator, with no ruling yet: file a factory-dispatchable workflow item
for assertion 3, and narrow `bd-ib-odi6dr` to assertions 1 and 2.

## 3. A long implement attempt is not a stuck one

Re-dispatched run `01M5SA824TQE` (`bd-ib-j5cwkj`) showed `implement` running for about four
hours, against the node's 1800 s timeout. Its event tail showed attempt 2 inside a tool
call that was still streaming test-progress dots, one event about every 55 ms. A run whose
events are still advancing has not stalled. Read the tail with
`fabro events <run> --server <factory> --json --tail 40`, because a bare `fabro events`
follows the stream and never returns. Use the 0.393 client: the PATH 0.254 client fails
against the petri server.
