# Fork config-options implementation record — in-protocol model and effort selection

Written 2026-09-30 by the session driving plan epic `bd-ib-jxvgq5` after the
hand-build of `bd-ib-afcn3d`. It records where the slice landed, what
verified it, and the consumer facts the remaining slices (the Dispatcher's
structured candidate form `bd-ib-kc7vzk`, the pricing item `bd-ib-tmgt7v`,
and the deploy slice S7) must consume. The design itself lives in the Fabro
fork (`docs/plans/2026-09-30-acp-candidate-config-options.md` on
`factory-integration`); this note is the orchestrator-side pointer.

## Where it landed

- Ledger item: `bd-ib-afcn3d`, host-routed (`factory_safety:
  mutates-host-machinery`) per `.ai/fabro-fork-hand-build.md`, opened through
  the driver door and closed `resolution:completed` with the fork PR URL and
  merge SHA as the reason.
- Fork pull request: <https://github.com/thewoolleyman/fabro/pull/10>, branch
  `acp-config-options`, four commits on `origin/factory-integration`
  `20bf91e06` (S4's tip).
- Merge: rebase-merged into `factory-integration` on 2026-09-30; merge SHA
  `8869e88b2f7e383ec6fceb8d3f6f928dd0339b34`. Under rebase-merge the branch
  SHAs did not survive: the landed series is `908116cc2` (feat), `933c0e329`,
  `2d23fa966`, `8869e88b2` (review and gate fixes), verified by a content
  check on `origin/factory-integration` (the capability string, the
  `CandidateConfigOptions` grammar, the `SetRefused` reason and the design
  note are all present), not by branch containment.
- Deployment: NOT done. hp and vps still run the builds recorded in
  `AGENTS.md` (`4b8cc85` and `977cb67`), which carry neither S4 nor this
  slice. Pinning both hosts is S7.

## Verification record

Local merge gate (the fork's CI runs only on `main`), detached run
`20260930T090139Z-3994773` against fork commit `b680e5386`, with the build
cache at `/data/projects/fabro/target` (the S4-era shared cache directory no
longer exists):

- `cargo +nightly-2026-04-14 fmt --check --all`: clean on every touched file.
  The two files fork PR 8 left unformatted (`fabro-manifest/src/lib.rs`,
  `fabro-workflow/src/git.rs`) are still unformatted and still belong to that
  thread; the gate excluded exactly those two by name.
- `cargo +nightly-2026-04-14 clippy --workspace --all-targets -- -D warnings`:
  exit 0, after one `let...else` lint in the first gate run.
- `cargo nextest run` for `fabro-types`, `fabro-acp`, `fabro-workflow`,
  `fabro-store`, `fabro-server`: 2,503 passed, 31 skipped, 0 failed, with
  `CARGO_BIN_EXE_fabro` exported for the server's render-subprocess tests as
  the S4 record prescribes. `fabro-cli` `system_info` and `acp` targets: 6
  passed.
- Two earlier gate runs were red on the pre-fix tree: the clippy lint above,
  and one test that had shadowed its own fixture with the JSON `null`
  literal inside `json!` (it was testing a null candidate, not a null option
  value). Both fixed in `b680e5386`.

Independent review before merge, two legs, both DO-NOT-MERGE on the first
commit, both findings fixed and tested before the merge:

- Opus leg: a JSON-RPC error answer to `session/set_config_option` bypassed
  the typed refusal and reached the classifier as a provider-evidenced
  protocol error, so an availability signature matching the agent's text
  would have produced a failover, a later candidate and a minted hold. Now
  `set_refused`, proven by a chain test carrying a matching signature that
  asserts no failover, no exhaustion, no prompt to the fallback candidate. It
  also asked that confirmation read the agent's FINAL advertisement (an
  agent that resets the model when the effort changes must not be prompted;
  added, with a fake-agent test), that the refusal slot be read before
  transport cleanup, and that `docs/internal/events.md` gain the started
  event's new rows.
- Codex leg (gpt-5.6-sol): confirmed wire order, refusal identity and that
  moving `agent.acp.started` breaks no consumer (the store and the server
  read `AgentSessionActivated` independently); found that an explicit JSON
  `null` for `model` or `effort` deserialised as absence past the
  non-empty-text rule. Now refused at chain validation through a
  present-key deserializer.

## Consumer contract as built (read before working kc7vzk, tmgt7v or S7)

- **Capability string:** `acp.candidate_config_options.v1`, advertised on
  `GET /system/info` beside `acp.fallback_chain.v1`. The Dispatcher MUST
  refuse before claim a chain carrying `config_options` against a server
  that does not advertise it, exactly as the existing capability gate does;
  an older engine omits the string and must read as "capability absent".
- **Grammar:** each candidate object MAY carry
  `"config_options": {"model": "<value id>", "effort": "<value id>"}`; both
  keys optional, at least one required, values non-empty text, no other key,
  no explicit `null`. The value is the agent's ACP `configOptions` VALUE ID
  (for Codex, the model slug as the agent advertises it), not a display
  name. `acp.command` must still equal `candidates[0].command`.
- **Order and confirmation:** model is set before effort; every option is
  checked current in the agent's final `configOptions` before the prompt.
- **Refusal identity, for S5's projection:** a pre-turn refusal emits NO
  `agent.acp.failover` and NO `agent.acp.exhausted` and NO
  `agent.acp.started`; it surfaces as the node's failure with a message of
  the form `ACP candidate refused before any prompt: typed cause
  model_unsupported (candidate) — session config option model=<v>
  <reason>; the agent advertised [...]` (or `malformed_configuration` for a
  non-model option), category deterministic, non-retryable. The projection
  therefore mints nothing from it; the S3 preflight is what should have
  excluded the candidate.
- **Started event:** `agent.acp.started` now carries `model` and `effort`
  (absent when none were requested) and is emitted AFTER
  `AgentSessionActivated`, once configured and flushed before the first
  prompt. A legacy node whose process fails before `session/new` emits no
  started event at all. Readers keyed on the old pre-spawn timing must be
  updated; none in this repository were found to depend on it.
- **Option ids are the spec's:** `model` and `effort`. An agent advertising
  effort under another id refuses as `malformed_configuration`; whether the
  live Codex and Claude adapters advertise these ids is not yet measured on
  a real run and is part of S7's proof.

## Runbook facts corrected in the same change

- `AGENTS.md` and `orchestrator-image/README.md` now say that neither host
  carries this slice either, and the README's carried-fix table gained its
  row, marked merged-not-deployed.
