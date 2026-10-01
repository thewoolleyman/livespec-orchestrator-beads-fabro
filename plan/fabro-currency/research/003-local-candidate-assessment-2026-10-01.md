# Local candidate assessment, 2026-10-01

The candidate is **not safe to re-pin** with the current orchestration
workflow. The released binary rejects three production-graph conditions and
the carried ACP fallback attribute. These measurements are a local screening
result, not completion of the isolated-server qualification matrix in
`bd-ib-4jzql3`.

## Scope and authority

The maintainer authorized local cleanup, research, and testing, with routine
human gates pre-approved, and explicitly prohibited public changes to Fabro
or any other repository they do not own. Consequently, this session read
upstream PRs #576 and #688 and issue #553 but did not comment, edit, close,
push to their head branches, or create upstream replacements. Pushing an
existing upstream PR's fork head would also change that public PR and is
outside this session's scope. The P1 upstream-disposition criteria remain
unmet; local evidence must not be reported as their completion.

## Reproducible candidate identity

Observed through [GitHub Releases](https://github.com/fabro-sh/fabro/releases/tag/v0.371.0-nightly.0)
on 2026-10-01 at approximately 19:06 UTC:
the newest published release is `v0.371.0-nightly.0`, published
2026-09-29T21:34:58Z. Its source commit is
`5879ebf099596a107464f6d1ce97b1c91759d533`.

The downloaded `fabro-x86_64-unknown-linux-gnu.tar.gz` matches both its
published checksum file and GitHub's asset digest:
`718ae0821d9e27cf8f8659df85641f1bfda0105756d3840816f898bdeecfec37`.
The extracted binary has SHA-256
`bd6366c6b1ce687c92944c48c005f042fc7cdd3e298d51ce5d849788fe478447`
and reports `fabro 0.371.0-nightly.0 (5879ebf 2026-09-29)`.
It is retained under
`/home/ubuntu/.local/state/fabro-currency/v0.371.0-nightly.0/`.
Validation used a separate `FABRO_HOME` at
`/home/ubuntu/.local/state/fabro-currency/isolated-home`, telemetry disabled,
and upgrade checks disabled. No server or production binary was changed.

The local baseline client reports `fabro 0.254.0 (977cb67 2026-09-09)`
and has binary SHA-256
`a1f558c2e625303ed603ace14fd8d80dd7ceedfe13064449b85c57a7acd608ac`.
This is a local-client observation, not a fresh report from either serving
factory host.

The exact source lockfile pins Petri to
`98144f107fcdd290a44699a8e76abf6e6f63fe2a`, Pebble to
`72a51ea2652be619f214e331f1fde87e9acb2267`, and sandbox-driver to
`7d1932b5fd758dbc67ae5a34aaed08d8733ddaba`. Their `branch = main`
manifest declarations do not replace these lockfile identities.

## Executed validation

Use the extracted binary with `validate --json <file>`. The adjacent
`003-validation-control.fabro` and `003-validation-fallback.fabro` fixtures
make the positive and negative observations independently repeatable.

| Input | Exit | Measured result | Migration owner |
| --- | ---: | --- | --- |
| Minimal command control | 0 | `valid: true`, zero diagnostics | Control only |
| Current production graph on the local 0.254 baseline | 0 | `valid: true`, 18 nodes, 36 edges, zero diagnostics | Baseline control |
| Current `implement-work-item/workflow.fabro` | 1 | Three `attractor.condition.syntax` errors at lines 704, 706, 707: the review-cap inputs remain interpolation tokens inside conditions | `bd-ib-hti4zf` |
| Minimal ACP fallback graph | 1 | `attractor.unknown_attribute`: `acp.fallback_chain` is not a Fabro attribute | `bd-ib-r5cnjd` |

The current graph validation also warns that checkpoint, integrations,
meta-branch, pull-request, and run-branch settings are ignored by the
standalone runner; embedding-host behavior still needs separate measurement.
It explicitly warns that Docker/host resource limits are ignored. These are
validation observations, not proof of server or container behavior.
The loop warning says an uncapped loop lowers to 500 firings; that is not
evidence that the fleet's intended three-visit cap works.

## P1 source and forge findings

### OTLP PR #576 (`bd-ib-lic3n3`)

[PR #576](https://github.com/fabro-sh/fabro/pull/576) remains open at head
`da277a4e5945e98827866fb407b7aa1d28a1d4d8`.
Its claim to add transport, rather than instrumentation, still identifies a
Fabro-owned seam. At the candidate tag,
`lib/apps/fabro-cli/src/logging.rs` owns the subscriber registry in
`init_subscriber`, `init_stdout_subscriber`, `init_worker_subscriber`, and
`init_worker_stdout_subscriber`. The registries still put the log filter
outside the formatting layers. Searching candidate `Cargo.toml` and all
Rust/TOML files under `lib/` finds no `opentelemetry`, `OTEL_EXPORTER`, or
`otel_layer` implementation. `lib/apps/fabro-server/src/spawn_env.rs`
still clears worker environment and copies an allowlist without OTLP names.

Local disposition recommendation: port transport to the current Fabro CLI
and worker environment seam on a new fork-only branch. Keep the OTLP layer's
filter independent of `FABRO_LOG`, as the carried fix requires. Petri owns
engine instrumentation and propagation; the Dispatcher owns its own spans,
not export of spans inside another process. A current mock-collector test
must prove disabled behavior, span export, worker forwarding, correlation,
and shutdown before accepting a successor. Production observability remains
owned by `bd-ib-wo4m6o`; the old PR's tests do not prove this port.

### Spend-limit PR #688 (`bd-ib-m637al`)

[PR #688](https://github.com/fabro-sh/fabro/pull/688) remains open at head
`3b37818887c8daf80bbb28fb6e30056a32b22db1`.
Its legacy classifier no longer exists in the candidate's
`lib/components/fabro-workflow/src/error.rs`. Retained public
`FailureCategory` types are not evidence that the old classifier still runs.
`lib/components/fabro-petri/src/projection/coordinator.rs::conclude`
maps an ordinary failed run to `FailureCategory::Deterministic`.

At the exact locked Petri revision,
`crates/attractor/steps/src/agent/backend.rs`, `From<AcpError>` maps every
non-cancel ACP error to `retry_requested`; its documentation explicitly
includes rejected requests. `crates/attractor/steps/src/acp/mod.rs` turns a
`session/prompt` error response into a rejected error. This is source
evidence that provider-cap retry policy belongs in Petri's ACP conversion,
with Fabro's projection considered separately. It is not a live spend-limit
reproduction. Existing Petri coverage
`an_agent_that_exits_before_answering_is_retried_while_attempts_remain`
proves process-exit retry, not permanent billing refusal.

Local disposition recommendation: do not blindly rebase the 527-line legacy
classifier patch. First use a fake ACP agent returning the two recorded
provider-limit messages and count actual prompt attempts; assert the typed
failure and no retry while retaining a transient/process-exit control.
That measurement and successor coverage remain outstanding. No Petri
repository was edited or published to.

### ACP timeout issue #553 (`bd-ib-g7qlmo`)

[Issue #553](https://github.com/fabro-sh/fabro/issues/553) remains open.
Its upstream maintainer comment from 2026-07-23
reports a local non-reproduction and requests confirmation. The three
original test names are absent from the candidate's executable test tree.
The positive provenance check is commit
`af38d68942e329a6b6b8d54c15a245d8df0330cc`, which deletes the entire
325-line `lib/apps/fabro-cli/tests/it/workflow/acp.rs` during the Petri
migration. A whole-tree search still finds historical documentation mentions
of `acp_backend_workflow`; those are not runnable tests.

The literal issue command was submitted against the exact candidate source:

```sh
CARGO_BUILD_JOBS=4 \
CARGO_TARGET_DIR=/home/ubuntu/.worktrees/fabro/factory-wave-c/target \
nice -n 10 cargo nextest run --locked -p fabro-cli --profile ci \
  --no-fail-fast workflow::acp::acp
```

The detached gate receipt is `20261001T190429Z-3328887`. It started at
19:04:29 UTC and was deliberately terminated after approximately 14 minutes
while compiling dependencies, after the source/provenance check established
that the exact test module was deleted. No tests executed and no pass is
claimed; this is an interrupted build, not a reproduced timeout or a passing
current-engine test. A completed zero-test selection would likewise mean
the reproducer was retired, not that three formerly failing tests passed.
The next meaningful instrument is a replacement ACP behavior test on the
current engine, not the removed test-name filter. The temporary candidate
source worktree was removed after its processes stopped; the release binary
and the gate log remain available for follow-up.

## Safe stopping boundary

The cleanup can be accepted independently. The candidate has an explicit
no-go for a production re-pin; no host cutover, storage migration, image
rebuild, or carrier source rewrite was attempted. The next local work is
current-engine behavioral qualification and fork-only successors for the
surviving capabilities. P1's public-upstream acceptance actions remain
outside the latest authorization. The full plan stays live, including its
unfinished spec-gap capture; this note does not claim archive readiness.
