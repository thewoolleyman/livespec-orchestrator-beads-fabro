# livespec dark-factory orchestrator image (Beads/Dolt + Fabro, Docker-in-Docker)

Step 1 of the W7 orchestrator-convergence epic (`livespec-impl-beads-8bc`). This
directory builds the **production orchestrator container**: a privileged image
running an *inner* Docker daemon (Docker-in-Docker) on which Fabro spawns its
sandboxes, fully decoupled from the host daemon. It carries the dispatcher's
host-level runtime (`fabro`, guarded `bd`, `dolt`, `gh`, `mise`, `uv`, `git`,
Python, and `libatomic1` for Pyright's Node runtime) and a
supervisor entrypoint that brings up dockerd + a headless fabro server, then
hands off to the dispatcher.

The recipe is derived from the step-0 DinD spike
(`../archive/research/w7-orchestrator-convergence/dind-spike.md`) — read it for the
constraint rationale. The image is **secret-free by construction**; every
credential is injected at `docker run` time.

## Contents

| File | Purpose |
|---|---|
| `Dockerfile` | `ubuntu:24.04` base (glibc 2.39 — the fabro v0.254.0 hard floor) + inner `docker.io` + content-pinned Beads v1.2.2 installed as `/usr/local/bin/bd-real` behind the tracked lifecycle guard at `/usr/local/bin/bd` / `dolt` v2.1.4 + `uv` + `gh` + `mise` + `libatomic1` + the COPYed pinned `fabro` binary; `VOLUME /var/lib/docker`; `EXPOSE 32276`. |
| `orchestrator-entrypoint.sh` | Supervisor: start dockerd → wait for socket → provision headless fabro (gh auth with a minted App token + hand-written settings with the native GitHub App integration + dev-token server credentials, listening on `0.0.0.0:32276`) → exec the dispatcher (or a passed command). |
| `build-and-verify.sh` | Stages the fabro binary, builds the image, runs the privileged container with an ext4-backed volume + injected secrets, and runs tier-1 verification. |
| `tier2-dispatch-proof.sh` | Runs the W7 Tier-2 proof: one explicit shadow dispatch from inside the container against a tiny ready item, with redacted logs and inner-daemon evidence. **Bind-mounts the host impl-beads checkout** — it is a proof runner, not the real-work substrate. |
| `real-work-dispatch.sh` | The W7 step-5 **real-work substrate**: dispatches one ready work-item with **no host checkout bind-mount**. It fresh-`git clone`s impl-beads (dispatcher code + the `.fabro/workflows` graph) *and* the dispatch target *inside* the container, `uv sync`s the dispatcher clone, regenerates the gitignored `.beads/metadata.json` (server-stable `project_id`), and points `dispatcher.py loop --repo` at the in-container target clone. The only host coupling is the `-e` secret set. |
| `fabro` | The pinned fabro binary, fetched at build time from `~/.fabro/bin/fabro`. **Gitignored — never committed** (111MB blob; the version is pinned in the Dockerfile's `FABRO_VERSION` for documentation). |

## Hard constraints (proven by the spike + this build)

- **Base must be `ubuntu:24.04` (glibc ≥ 2.39).** fabro v0.254.0 links
  `GLIBC_2.39`; `debian:12` (glibc 2.36) silently passes the dockerd checks then
  fails the moment fabro is invoked, and Alpine/musl won't run it at all.
- **`--privileged` is required.** The inner dockerd needs cgroup/device/mount
  capabilities to run nested. There is no unprivileged-DinD path in scope.
- **`/var/lib/docker` must be on a non-overlay (ext4) filesystem.** A privileged
  container's rootfs is itself an overlay mount; if the inner graph store lives
  there, the inner daemon silently degrades `overlay2` → `vfs` (slow, no
  hardlinks). Back `/var/lib/docker` with an ext4 docker volume or bind. The
  `VOLUME /var/lib/docker` declaration is load-bearing.
- **DinD, not DooD.** No host docker socket is mounted; the only socket in the
  container is the inner dockerd's, so Fabro targets the inner daemon by
  construction and never reaches the host daemon.

## Build + verify

Run on the host as `ubuntu` (Docker access) **under the 1Password env wrapper**
so the injected secrets are present:

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  ./orchestrator-image/build-and-verify.sh
```

This stages the fabro binary, builds `livespec-orchestrator:dev`, runs a
privileged container with an ext4-backed `/var/lib/docker` volume + the
host-loopback web-UI port, and asserts: inner storage driver is overlay-based
(not vfs), `fabro version`/`fabro doctor` run with the server reachable + GitHub
configured, the web UI answers on the published port, `LIVESPEC_BD_PATH` points
at the lifecycle guard, `/usr/local/bin/bd-real` has the pinned v1.2.2 binary
hash, both guarded and direct version probes report v1.2.2, and an ephemeral
in-container Dolt + `bd` round-trip succeeds. All probe output is redacted /
status-only; no secret is printed. The container + volume + staged build-context
payloads are cleaned up on exit.

## Tier-2 dispatch proof

After Tier 1 is green, `tier2-dispatch-proof.sh` runs the next W7 proof: one
explicit `dispatcher.py loop --mode shadow --item <id>` invocation from inside
the container. It uses the same entrypoint path as production, proves the inner
Docker daemon is the only daemon available to Fabro, captures a redacted
dispatcher journal tail, and leaves automatic item closure disabled with
`--no-close-on-merge`.

Preflight:

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  bash orchestrator-image/tier2-dispatch-proof.sh --preflight
```

Run against a deliberately tiny ready item:

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  bash orchestrator-image/tier2-dispatch-proof.sh --run --item <tiny-ready-item>
```

See `archive/research/w7-orchestrator-convergence/tier2-dispatch-proof.md` for the
evidence checklist and Codex/runtime classification.

When `TIER2_USE_HOST_NETWORK=1` (the default for that helper), the helper runs
Fabro on `32281` unless `FABRO_PORT` is explicitly set. This avoids colliding
with a maintainer's normal host Fabro server on `32276`.

## e2e-repo reaper (orphaned `livespec-e2e-*` cleanup)

`reap-e2e-repos.sh` is the W7 mechanical fail-safe that sweeps orphaned
throwaway GitHub repos (`livespec-e2e-*`) left behind by dark-factory
acceptance runs in the disposable `livespec-e2e` org. It is **org- and
name-scoped by construction**, **age-gated** so an in-progress run's repo is
never reaped, and its deletes **retry with backoff** for the GitHub
create-on-disk race (`HTTP 403 … done being created on disk`) and treat an
already-gone repo as success. It reads `LIVESPEC_E2E_GITHUB_TOKEN` by byte
count only and never prints a secret.

Preview (deletes nothing):

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  bash orchestrator-image/reap-e2e-repos.sh --dry-run
```

Real reap (default 120-minute age gate; `--force-all` deletes regardless of
age):

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  bash orchestrator-image/reap-e2e-repos.sh
```

**Run it only at boundaries — session-start, post-confirmed-merge, deliberate
teardown, or as a scheduled sweep — never mid-dispatch.** See
`archive/research/w7-orchestrator-convergence/e2e-repo-reaper.md` for the full safety
model and validation evidence.

## Host Fabro server (self-hosted; the maintainer's factory)

The host-direct Dispatcher path runs `dispatcher.py loop` **on the host** (not in
this image) and connects to a long-lived Fabro server the maintainer runs
directly from `~/.fabro/bin/fabro`, listening on **`127.0.0.1:32276`**. This is
the "maintainer's normal host Fabro server on `32276`" the Tier-2 proof helper
steps around. It is distinct from the containerized server the entrypoint
provisions (below); the image's `COPY fabro` stages this same host binary from
`$HOST_FABRO_BIN`, so the host install IS the image's staging source.

**Current binary (measured 2026-09-12; the hosts DIVERGE):** hp `fabro 0.254.0 (4b8cc85)`,
vps `fabro 0.254.0 (977cb67)` — both built from the
`factory-integration` branch (see below). Verify with `~/.fabro/bin/fabro
--version`; the parenthesized short SHA is the integration commit, and it MUST be
reachable from `factory-integration` — **reachability, not equality**. The branch
tip advances past the pinned build whenever a fix or a test lands, so a recorded
`origin/factory-integration` = `<sha>` snapshot goes stale without becoming
visibly wrong, which is how a true statement keeps reading as authoritative after
it stops being true. Check the property itself rather than a snapshot of it:
`git merge-base --is-ancestor 8de661118 origin/factory-integration`.

### `factory-integration` — the carrier branch for unreleased fixes

The factory does not run an official upstream fabro release: it depends on fixes
upstream has not shipped yet. Those fixes are carried on ONE standing branch in
our fork (`thewoolleyman/fabro`) named **`factory-integration`** — the only branch
name the factory ever pins for unreleased fixes. This is a spec-level rule, not a
convention: the branch name, the composition rule, the base-version ceiling, and the
rebuild/re-pin duty are fixed by `SPECIFICATION/constraints.md` §"Fabro runtime
constraints" (ratified in `v035`). That section is normative and requires this runbook to
be updated **in the same change** whenever the pinned build or the carried-fix set
changes — the spec fixes the rules, this section carries the commands and the current set.

`factory-integration` = the pinned base + EVERY pending upstream fix the factory
needs (never a subset, so the branch is always the whole truth about what runs):

| Carried fix | What it is | Why the factory needs it |
| --- | --- | --- |
| upstream PR **#568** (`push-credential-refresh-ahead`) | credential refresh ahead of expiry | dispatches longer than ~60 min otherwise die on an expired token |
| env-configurable daemon-readiness timeout | `FABRO_SERVER_START_READY_TIMEOUT_SECS` (default 60s) | the ~6s SlateDB store open exceeds stock 0.254's hard 5s cap, so stock 0.254 cannot start against this store |
| upstream PR **#552** | configurable per-node checkpoint git timeout (`[run.checkpoint] commit_timeout`) | the stock 30-second budget kills completed work when gate-running repository hooks take minutes; the factory workflow sets `commit_timeout = "10m"` |
| upstream PR **#576** | opt-in OTLP/HTTP span export | restores factory observability for the Codex era (the transport; lit up by the fork-local O1/O2 emitter wiring below) |
| fork-local **O1** — worker OTLP env re-injection (`bd-ib-98c.4`) | the server forwards its non-secret `OTEL_*` export config into the `__run-worker` subprocess (`apply_worker_otel_export_env`), deliberately stripping the credential-bearing `OTEL_EXPORTER_OTLP_HEADERS` | #576 alone is inert in the factory: the ACP work runs in a server-spawned worker whose env is `env_clear`ed by `apply_worker_env`, so without re-injection the worker exports nothing |
| fork-local **O2** — W3C `traceparent` join (`bd-ib-98c.5`) | the server serializes its `run`-span context to a per-run `TRACEPARENT` env at the worker-launch seam; the worker parents its `run` span on it | without it the server and worker each emit a SEPARATE root `run` span in a distinct trace, so one dispatch is unviewable as one trace |
| fork-local **P2** — decouple OTLP export from `FABRO_LOG` (`bd-ib-98c.12`) | `FABRO_LOG` was a GLOBAL registry filter gating the otel layer too; the fix filters per-layer (`FABRO_LOG` on the fmt layers, a fixed `INFO` floor on the otel layer) | otherwise raising the log level silently zeroes ALL telemetry at both ends (the server injects its level into the worker), with no error — an operator quieting logs could kill the Honeycomb dataset |
| fork-local **O4** — `run_turn` ACP turn span (`bd-ib-98c.7`) | a `tracing::info_span!("run_turn", …)` at the ACP seam (`fabro-workflow/src/handler/llm/acp.rs::run_turn`) carrying `node_id` / `command` / `config_name` (ALWAYS EMPTY here — see below) / `visit` plus a deferred `stop_reason`; it nests under the worker `run` span (fabro-workflow has no spans of its own, so the `Stage started/completed` telemetry — which are EVENTS, not spans — is not the parent) | without it the finest per-agent granularity is the `handler_type=agent` Stage telemetry, which never records WHICH command an agent turn ran or HOW it ended; O4 is what makes per-turn command/stop-reason queryable in Honeycomb |
| fork-local **Wave A / .2** — sandbox `init` (`bd-ib-bb41.2`) | `HostConfig.init = true` in `fabro-sandbox/src/docker.rs::host_config`, so Docker's bundled `docker-init` (tini) is PID 1 in the sandbox container; no image change, `sleep infinity` stays the command | the container command was PID 1 and reaped nothing, so every orphaned gate/agent subprocess stayed defunct (559 measured in one implement run) until the container died |
| fork-local **Wave A / .5** — no empty checkpoints (`bd-ib-bb41.5`) | the run-branch and parallel-branch checkpoint commits are guarded by `git diff --cached --quiet`; an empty tree is skipped and reported as an Info `run.notice` with code `checkpoint_empty` (branch failures as Warn `parallel_branch_checkpoint_failed`), `--allow-empty` removed from both, and no `git.commit` is emitted for a skipped checkpoint | `--allow-empty` let a run that produced nothing emit a chain of checkpoint commits, so every "the run made progress" signal built on them (commit count, checkpoint events) was vacuous — the fabro half of the closed orchestrator item `bd-ib-xmom` |
| fork-local **Wave A / jm4efv** — typed checkpoint budget (`bd-ib-jm4efv`) | a git command that hits its configured checkpoint commit budget is carried as `fabro_core::Error::CheckpointBudgetExceeded` and reaches the run as the deterministic `Error::Checkpoint`, never through the string classifier | the classifier read "timed out" in the rendered message and filed a Fabro operation-budget failure as `transient_infra`, so an exhausted budget was retried as if the network had blinked |
| fork-local **Wave A / .3** — `AgentAcpTimedOut` progress evidence (`bd-ib-bb41.3`) | the timed-out event carries the agent's message-text tail (or an explicit "output not captured" marker), `tool_call_count`, `update_count` and `last_activity_ms`; the failure message summarises the same counters; fields are `#[serde(default)]` so stored runs replay | the event reported `stdout: ""` unconditionally, so a working agent that ran out of time was indistinguishable from one that never started (the residue of `bd-ib-b5dg`); `update_count == 0` is now the zero-activity discriminator |
| fork-local **Wave A / .1 fork half** — script-node run identity (`bd-ib-bb41.1`) | script nodes receive `FABRO_RUN_ID`, `FABRO_WORKFLOW` and `FABRO_NODE_ID` in their env (the hook executor's trio) from `fabro-workflow/src/handler/command.rs`; workflow-declared values win | the workflow's needs-human preservation ref is run-scoped only if the script node can see the run id; without it every stranded run collided on one `refs/heads/needs-human/unknown-run` ref (the orchestrator half, PR #2198, now fails loudly with no id) |
| fork-local **Wave B / .4** — per-tool ACP run events (`bd-ib-bb41.4`) | the ACP session read loop keeps a tool-call ledger over `session/update` `ToolCall` / `ToolCallUpdate` and the handler emits the ordinary `agent.tool.started` / `agent.tool.completed` events for every call, with a payload bounded to `{kind}` / `{kind, status, elapsed_ms}` (no tool input or output) | `attach` and `dump` showed node-level events only for ACP agents, so a working agent and a hung one looked identical from outside the sandbox; per-tool events are what makes `watch` worth anything |
| fork-local **Wave B / js4t57** — refuse staging after a failed pre-run push (`bd-ib-js4t57`) | `pipeline/initialize.rs` refuses a remote sandbox at staging, as `Error::Precondition`, when the manifest's `push_outcome` is `Failed`, naming the branch, the source HEAD and the push error; `NotAttempted` / `Succeeded` / `Skipped*` and Local sandboxes are untouched | measured 2026-09-06: with the pre-run push refused, a docker sandbox cloned the origin branch BEHIND the operator's unpushed commit and the run succeeded silently on that base (run `01M1VQYHBAH9`); the only trace was the `push_outcome` field, which nothing read |
| fork-local **Wave B / .6** — ACP permission requests as interview questions (`bd-ib-bb41.6`) | `acp.permission_policy="ask"` (node attr; default `auto`) parks each adapter `session/request_permission` on the workflow's `AgentQuestionRuntime` as one multiple-choice question whose options are the adapter's, keyed by option id and presented **most-permissive first**; the answer resumes the node and is resolved **identity-first** on the option id, falling back to a label only when that label is unambiguous and cancelling rather than guessing otherwise; `acp.permission_timeout` bounds the wait and its expiry ends the turn as the deterministic `AcpError::PermissionTimedOut`, so the workflow's failed edge parks the node at `needs_human`; `auto` keeps the inline most-permissive answer, byte-identical to before | `select_permission_outcome` auto-answered every permission question, so a node never parked on a question and the console's needs-attention consumer had nothing to publish; under `ask` the question is data on `GET /runs/{id}/questions`. **Three review-found traps are why the row reads as it does:** matching the answer by display NAME let two options sharing a label collapse to the first, so a human choosing reject would have GRANTED the call; without an explicit ordering, `AutoApproveInterviewer` (installed for every `approval = auto` run) answers with `options.first()`, and ACP does not order an adapter's options, so a reject-first adapter would have denied everything silently under `ask` while `auto` allowed it; and the deadline did not exist at all — the question runtime carries no clock, so `PermissionTimedOut` had no automatic producer while the error text and the docs both described one |
| fork-local **Wave C / .7** — non-blocking ask-policy permission (`bd-ib-bb41.7`) | under `acp.permission_policy="ask"` the `session/request_permission` handler resolves and responds from a SPAWNED TASK, so the connection's dispatch loop keeps processing `session/update` — agent text, tool events and the activity heartbeat — while the human is deciding; the per-request timeout record is a bounded `Option` (`get_or_insert`, first-writer-wins) and each spawned task is turn-scoped (a drop-guard cancellation token releases a still-parked task when the turn ends, answering `Cancelled`); `auto` stays byte-identical | before Wave C the resolver awaited the human INLINE in the handler, and `agent-client-protocol`'s Deadlock Risk means the loop processes no other message while a handler runs, so the whole wait froze every update — the Wave A progress evidence went stale at exactly the moment an operator inspects a run that looks stuck (a stall, not a hang). Proven by a mutation-verified non-blocking unit test and a live ask-policy control (an interleaved update reached the run WHILE the permission was parked) |
| fork-local **S4** — bounded in-node ACP candidate failover (`bd-ib-mujvyn`, fork PR **9**, plan `bd-ib-jxvgq5`) | an optional `acp.fallback_chain` node attribute (closed JSON grammar, `schema_version` 1) carries an ordered candidate chain; one handler visit tries each candidate at most once, in order, under the node's ORIGINAL deadline, in the same sandbox, with a closed typed eligibility decision separate from `classify_failure_reason`, a durable side-effect onset ledger that fails closed, versioned `agent.acp.failover` / `agent.acp.exhausted` / `agent.acp.side_effect` events, and the capability `acp.fallback_chain.v1` advertised on `GET /system/info`; a node without the attribute is byte-identical to before | the Dispatcher (S1–S3, merged) resolves an ordered candidate chain per node, but the engine consumed exactly one `acp.command`, so a model removed from the catalog or a provider out of quota killed the node after every earlier node had done its work. **Carried on the branch, NOT pinned on either host as of 2026-09-12** — pinning, the `dispatcher.minimum_release` floor and the end-to-end proof are S7 |

The Wave B "known limitation" note for `bd-ib-bb41.7` is **resolved by the Wave C
row above**: under `ask` the permission handler no longer blocks the dispatch
loop. `auto` remains the default and no workflow in this fleet sets `ask`.

Failure-cause attributes are queryable in Honeycomb, but not as `run_turn`
span attributes. Filter the separate failure-event span in the same trace as
`run_turn` instead: the failure-event span has `error=true` and `level=ERROR`
and carries `category`, `signature`, and `cause_count` (for example, a
`Pipeline cancelled` span with `category=canceled` and `cause_count=0`).

`config_name` reaches Honeycomb as an EMPTY STRING on every `run_turn` span this
repo's workflow produces, and that is BY DESIGN — the attribute is neither dropped
by the receiver nor lost in transit. Measured 2026-08-22 on the `fabro` dataset:
present on 381/381 `run_turn` spans in a 24h window, `distinct_values = 1`, and
that one value is `""`.

The reason is structural. O4 populates `config_name` from the ACP process spec's
name, which is set only when a node resolves a NAMED `acp.config`. Every acp node
in `.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro` declares an
inline `acp.command` instead, and `AcpProcessSpec::from_command_attr`
(`lib/crates/fabro-acp/src/command.rs` at the pinned build) sets that name to
`None` explicitly, which the span records as the empty string. The two attributes
are MUTUALLY EXCLUSIVE — supplying both is an error, not a merge — so populating
`config_name` would mean replacing the workflow's templated per-node adapter
inputs with static configs, on the one surface the 0.254 version ceiling already
constrains. That trade was declined (ledger `bd-ib-98c.16`).

Nothing is lost by this. `command` is populated on 381/381 spans and carries the
full argv, so it already answers WHICH agent invocation ran at strictly finer
grain than `config_name` could. Do not read the empty column as a telemetry
defect, and do not "fix" it by widening the receiver's allowlist — `config_name`
is already allowlisted, and was allowlisted throughout the window in which every
value was empty.

### Dispatch Traps

If a consumer is refused as `not in the ready set` while its only dependency is
verifiably closed in a sibling tenant, suspect a sibling-read failure. Targeted
dispatcher refusals now include the sibling lookup diagnostic; check for messages
such as `sibling tenant read failed for <repo>:<id>`, `no clone configured for
<repo>:<id>`, or `<id> not found in <repo>`.

**Base is pinned to 0.254 — do NOT modernize.** The factory MUST NOT pin any fabro
build ≥ 0.256 until the `workflow.fabro` migration lands: fabro #474 de-templates
`acp.command`, so our `acp.command="{{ inputs.acp_adapter }}"` node goes through
literally and every dispatch dies `exit 127`. Deferred modernization: ledger
`bd-ib-6qu`. Rollout/revert state for the 0.254 cutover: ledger `bd-ib-2nq.4`.

**Rebuild + re-pin** (whenever the carried-fix set changes). Keep the outgoing
binary as a rollback artifact — the pin is a file swap, so the revert is one too:

```bash
# in the fork worktree, on factory-integration. A FRESH worktree has no
# node_modules, and the SPA embed then fails with `Could not resolve: "react"
# ... Maybe you need to "bun install"?` — so install first (measured 2026-09-06):
bun install --frozen-lockfile
# invalidate any assetless cached embedding crate, then refresh and embed the SPA:
cargo clean --release -p fabro-spa
cargo dev build --release -p fabro-cli
# retain the CURRENT binary before overwriting it:
cp ~/.fabro/bin/fabro ~/.fabro/bin/fabro.<outgoing-sha>-<label>.bak
# stage + ATOMIC RENAME into place (see the Text-file-busy note below):
cp target/release/fabro ~/.fabro/bin/fabro.new
mv -f ~/.fabro/bin/fabro.new ~/.fabro/bin/fabro
~/.fabro/bin/fabro --version          # confirm the new integration commit
```

**hp takes the vps-built binary.** hp carries only a stable toolchain, and the
vps build runs there (both x86_64; hp's glibc 2.43 is newer than vps's 2.42, and
the 0.254 floor is 2.39). Stage it beside the running one, then swap as the
service user and restart hp's unit — which kills every foreign run on hp, so wait
for a drain window:

```bash
scp ~/.fabro/bin/fabro root@hp-xubuntu.perch-rudd.ts.net:/home/cwoolley/.fabro/bin/fabro.new
ssh root@hp-xubuntu.perch-rudd.ts.net 'chown cwoolley:cwoolley /home/cwoolley/.fabro/bin/fabro.new \
  && chmod 0755 /home/cwoolley/.fabro/bin/fabro.new \
  && cp -p /home/cwoolley/.fabro/bin/fabro /home/cwoolley/.fabro/bin/fabro.<outgoing-sha>.bak \
  && mv -f /home/cwoolley/.fabro/bin/fabro.new /home/cwoolley/.fabro/bin/fabro \
  && systemctl restart fabro-server && /home/cwoolley/.fabro/bin/fabro --version'
```

`chmod 0755` is load-bearing, not decoration: `scp` as root lands the file
**mode 0644** (it does not preserve the source exec bit without `-p`, and even
`-p` from a differently-umasked source is not guaranteed), so `chown` alone
leaves it non-executable. The `cwoolley`-run unit then fails
`status=203/EXEC ... Permission denied`, systemd sits in `activating`/`start-post`
while its readiness curl loops on `Could not connect to 127.0.0.1:32276`, and the
tailnet API returns **502** — a failure that reads like the server crashed rather
than a mode bit. Measured 2026-09-07 during the Wave C re-pin. vps never hits this
because it runs as the file's owner.

When gating a restart on `fabro ps --server <host>` being idle, match run ROWS
(for example `grep -E '^ ?01[A-Z0-9]{10,}.*running'`): the idle message
`No running processes found` also contains the word `running`, and a bare
`grep running` aborts on an idle factory.

**Why `mv`, not a plain `cp` over the target.** While the server is running it is
*executing* `~/.fabro/bin/fabro`, so overwriting that path in place fails with
`cp: cannot create regular file ...: Text file busy` (`ETXTBSY`). Staging to a
temp name in the same directory and `mv`-ing over the target is a rename: the
running process keeps its old inode, and the path immediately points at the new
build. Two traps this avoids: a silently-failed `cp` followed by a restart brings
the server back up on the OLD binary (the swap never happened), and waiting for
the listening port to free is NOT sufficient — the port frees before the process
fully exits, so a stop-then-`cp` can still hit `ETXTBSY`. If you do stop first,
wait for the PROCESS to exit (`kill -0 <pid>` fails), not just the port.

Then restart the system service (next section) and confirm `fabro doctor` is
green. Verify
the running daemon actually picked up the new build by comparing inodes — a
mismatch (or an `exe` link reading `(deleted)`) means it is still running the old
image:

```bash
PID=$(ss -ltnp | grep '127.0.0.1:32276' | grep -oP 'pid=\K[0-9]+')
stat -Lc %i /proc/$PID/exe; stat -c %i ~/.fabro/bin/fabro   # must match
```

**Then rebuild the orchestrator image — this step is REQUIRED, not optional.** The image
bakes a COPY of the host binary (`COPY fabro` in the Dockerfile, staged from
`$HOST_FABRO_BIN`, which defaults to `~/.fabro/bin/fabro`). Re-pinning the host alone
leaves an already-built image running the OLD fabro, so the containerized server and the
host-direct server would silently disagree about which engine they run — exactly the split
the ratified constraint forbids:

```bash
./orchestrator-image/build-and-verify.sh   # restages $HOST_FABRO_BIN into the image
```

To **roll back**, copy the `.bak` binary over `~/.fabro/bin/fabro`, restart, and rebuild
the image the same way. The current rollback artifact is
`~/.fabro/bin/fabro.9081419-pre-wave-b.bak` (the Wave A build: everything above
through `.1 fork half`); `fabro.8de6611-pre-wave-a.bak` is the pre-Wave-A build
and `fabro.b9b63a8-pre-checkpoint-timeout.bak` the pre-#552 build.

### Candidate build + Enemy Unit Test comparison

The Enemy Unit Test comparison harness checks a candidate Fabro build against
the pinned factory build without touching the production host service on
`127.0.0.1:32276`.

Build the candidate from the fork worktree on `factory-integration`:

```bash
cargo clean --release -p fabro-spa
cargo dev build --release -p fabro-cli
```

Use the produced candidate binary at `target/release/fabro`. Start the
candidate server on **`127.0.0.1:32286`** so it cannot collide with the
production systemd unit on `32276`. Keep its Fabro home outside the production
state directory and launch it from a foreground shell you can stop directly:

```bash
FABRO_CANDIDATE_HOME="$(mktemp -d /tmp/fabro-candidate.XXXXXX)"
mkdir -p "$FABRO_CANDIDATE_HOME/storage"

cat > "$FABRO_CANDIDATE_HOME/settings.toml" <<'SETTINGS'
_version = 1

[cli.target]
type = "http"
url = "http://127.0.0.1:32286"

[server.api]
url = "http://127.0.0.1:32286/api/v1"

[server.listen]
address = "127.0.0.1:32286"
type = "tcp"

[server.web]
enabled = true
url = "http://127.0.0.1:32286"
SETTINGS

HOME="$FABRO_CANDIDATE_HOME" target/release/fabro server start --no-upgrade-check
```

When the comparison is complete, stop that foreground process with `Ctrl-C` (or
kill only the candidate server PID) and remove `$FABRO_CANDIDATE_HOME`. Do not
stop, restart, or overwrite the production `fabro-server.service` unit for this
comparison.

Run the harness from the orchestrator checkout. The default invocation compares
the pinned pair against itself and should emit an empty delta:

```bash
just fabro-enemy-compare
```

Run pinned versus candidate by supplying the second binary and server URL:

```bash
FABRO_EUT_CANDIDATE_BIN=/path/to/fabro/target/release/fabro \
FABRO_EUT_CANDIDATE_SERVER=http://127.0.0.1:32286 \
just fabro-enemy-compare
```

When the candidate's reported version, commit, date, or completed-run fixture
differs from the pinned defaults, set the candidate-scoped forms. The harness
maps them onto the generic `FABRO_EUT_*` names only for the candidate pytest
leg:

```bash
FABRO_EUT_CANDIDATE_EXPECTED_CLIENT_VERSION=0.254.0 \
FABRO_EUT_CANDIDATE_EXPECTED_CLIENT_COMMIT=<candidate-short-sha> \
FABRO_EUT_CANDIDATE_EXPECTED_CLIENT_DATE=<candidate-client-date> \
FABRO_EUT_CANDIDATE_EXPECTED_SERVER_VERSION=0.254.0 \
FABRO_EUT_CANDIDATE_EXPECTED_SERVER_COMMIT=<candidate-short-sha> \
FABRO_EUT_CANDIDATE_EXPECTED_SERVER_DATE=<candidate-server-date> \
FABRO_EUT_CANDIDATE_COMPLETED_RUN_ID=<candidate-completed-run-id> \
FABRO_EUT_CANDIDATE_BIN=/path/to/fabro/target/release/fabro \
FABRO_EUT_CANDIDATE_SERVER=http://127.0.0.1:32286 \
just fabro-enemy-compare
```

The artifact is written to `fabro-enemy-unit-tests/comparison.md` by default. It
contains a per-assertion table for pinned and candidate results plus a `Delta`
section that counts regressions, improvements, skip deltas, assertions present
on only one side, and the total of all four.

**The exit code is the verdict, and it is a function of that delta.** The
harness exits 0 only when both pytest legs exited 0 AND every delta count is
zero, so `just fabro-enemy-compare` can be gated on directly to assert an empty
delta. A skip counts as a delta — skipping is how the suite expresses a
capability present on one target and absent on the other, which is the whole
question this comparison answers — but it is reported as a `skip-delta` rather
than folded into the regression count, so a genuine failure stays
distinguishable from a capability gap.

### Start / restart

**There are TWO factory hosts.** Everything in this section describes the
**vps** host unless it says otherwise; the commands below act on whichever host
you are logged into, so running them from a vps shell restarts vps, never hp.
See "The hp factory host" below before touching hp.

The vps host server is owned by the `fabro-server.service` unit distributed from
`/data/projects/vps-info/services/fabro-server/`. Restart it through systemd:

```bash
sudo systemctl restart fabro-server
/usr/local/libexec/fabro-server-verify-web
```

- The unit runs Fabro in the foreground, passes `--web` explicitly, and uses
  `Restart=always` so crashes and host reboots relaunch it with the console.
- Its `ExecStartPost` gate requires `/runs` to exist, then requires the local
  `/login` shell and referenced JavaScript bundle to load. A health-only/API-only
  process is rejected rather than left running.
- Build with `cargo clean --release -p fabro-spa` followed by
  `cargo dev build --release -p fabro-cli`. The targeted clean is required
  because Cargo does not notice when the gitignored asset directory has changed
  behind an already-cached release embedding crate. A plain `cargo build` leaves
  the embedded SPA empty and will fail the service readiness gate.
- The unit strips `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`; OAuth credentials are
  still injected only into each dispatched sandbox.
- Never invoke `fabro server start` or `fabro server restart` directly on this
  host. Doing so bypasses supervision and the web-readiness invariant.

### The hp factory host

`hp-xubuntu` is the fleet's **second** factory and, since the
`default_factory` rollout, the **primary** one: every `.livespec.jsonc` in the
workspace that carries a `factories` block sets `default_factory: "hp"`. vps is
the fallback. Provisioned under plan epic `bd-ib-l3nptz`.

**Shell access — use the `cwoolley` account.** Probes with the default user
fail, which is why early notes recorded hp as unreachable:

```bash
tailscale ssh cwoolley@hp-xubuntu 'fabro --version'
```

Facts verified on the host 2026-08-19:

- Binary `fabro 0.254.0 (8de6611 2026-08-16)` — same version **and commit** as
  vps, so the `constraints.md` pin holds on both. (Each host built the fork
  independently, so their embedded SPA assets differ; that is expected and is
  *not* evidence of a version skew.)
- Unit is `active` + `enabled`, runs as **`cwoolley`**, `HOME=/home/cwoolley`,
  `WorkingDirectory=/home/cwoolley/repos/livespec-orchestrator-beads-fabro`.
  Note hp diverges from vps by service user, home, and checkout root — not just
  the two per-host edits older notes predicted.
- OAuth-only posture intact: the unit carries
  `UnsetEnvironment=ANTHROPIC_API_KEY OPENAI_API_KEY` and `server.env` (mode
  `600`) holds only `FABRO_DEV_TOKEN` and `SESSION_SECRET`.
- Capacity: 16 CPUs, 30 GiB RAM, 302 G free disk — comfortably more than the
  4-CPU/8 GB per-run plan needs.

**Verifying hp — do NOT use `fabro doctor --server`.** Against a remote host it
reports `[✗] Fabro server (health check failed)` for a perfectly healthy
server; the CLI's `auth.json` entry is keyed by URL, which is also why
`[cli.target]` stays on loopback. Use the readiness gate and `ps` instead:

```bash
FABRO_BASE_URL=https://hp-xubuntu.perch-rudd.ts.net:32276 \
FABRO_CANONICAL_HOST=hp-xubuntu.perch-rudd.ts.net:32276 \
  /data/projects/vps-info/services/fabro-server/fabro-server-verify-web

fabro ps --server https://hp-xubuntu.perch-rudd.ts.net:32276
```

A bare `curl .../runs` returns **404 from a healthy server** — fabro 404s a
request without `Accept: text/html` and the canonical `Host` header. Two
identical 404s against hp *and* vps mean the probe is wrong, not that both
factories are down.

**Two known gaps, tracked:**

- `bd-ib-l3nptz.14` — hp's unit, drop-in, serve proxy, and `settings.toml` URLs
  exist **only as live host state**; nothing is in version control, and
  `install.sh` was never deployed there. hp was stood up by hand.
- `bd-ib-l3nptz.15` — hp does **not** carry the
  `FABRO_WEB_VERIFY_ATTEMPTS=300` crash-loop mitigation that vps got via
  `bd-ib-l3nptz.2`; it runs the default of 60. That fix landed in vps-info's
  versioned unit and had no path to hp's unversioned one.

### Enabling fabro span export (O1 Lever A — opt-in)

The server's tracing spans (the top-level `run` span it mints per dispatch) are
bridged to OTLP **only when the OTLP endpoint env is present at start**.

- On **vps** the unit carries none, so export is inert there — the default this
  section describes. (Its only drop-in is `verify-timeout-override.conf`.)
- On **hp** export is already **ACTIVE**: hp carries an `otel.conf` drop-in with
  all three variables below. Do not assume a factory's export is off without
  checking `systemctl show fabro-server -p Environment` on that host.

To turn it on where it is off, add a systemd drop-in with the three
**non-secret** OTLP variables:

```ini
# sudo systemctl edit fabro-server
[Service]
Environment=OTEL_EXPORTER_OTLP_ENDPOINT=http://172.17.0.1:4318
Environment=OTEL_EXPORTER_OTLP_PROTOCOL=http/json
Environment=OTEL_SERVICE_NAME=fabro
```

Then run `sudo systemctl restart fabro-server` in a quiet window.

- **`http/json` is mandatory.** The upstream exporter defaults to
  `http/protobuf`, but the local receiver is json-only, so protobuf POSTs are
  silently dropped.
- **Never set `OTEL_EXPORTER_OTLP_HEADERS` on the server.** The server exports to
  the **local** receiver (`172.17.0.1:4318`, no auth); the receiver holds the
  Honeycomb egress key and adds it on egress. The key must stay off the server
  (the exporter would otherwise send it). This mirrors the OAuth-only posture:
  no outbound-auth secret in the server env.
- **Restart required, so pick a quiet window.** A restart interrupts every
  in-flight dispatch — check `~/.fabro/bin/fabro ps` for running runs first.
- **Pairs with Lever B** (the worker OTLP re-injection,
  `fabro-server/spawn_env.rs`). Lever A lights up the **server-side** `run`
  span; the **worker/agent-side** spans only export once the pinned host binary
  is rebuilt from a `factory-integration` that carries Lever B (it forwards
  these same server vars into the worker, minus `OTEL_*HEADERS`). Until then
  Lever A alone yields the server `run` span only. See the livespec O1 plan
  (`plan/codex-factory-telemetry/o1-worker-exporter-plan.md`) for the full
  two-lever design.

### Fabro `run_turn` absence guard

The Dispatcher records a post-verdict assertion for every green dispatch before
mechanical reflection runs: the host-local OTLP receiver writes
`$XDG_STATE_HOME/livespec-orchestrator-beads-fabro/run-turn-exports/fabro.json`
(else `~/.local/state/...`) only after Honeycomb export succeeds for a span named
`run_turn` in the `fabro` dataset. The receiver's bind address is host-global,
so any repo's dispatcher may own the one process that writes the marker.
Real Fabro `run_turn` spans do not carry `work.item.id` or
`livespec.dispatch.id`. The guard accepts the
timestamp-bounded global Fabro `run_turn` marker for the dispatch window and also
indexes those correlation ids if a future span shape carries them. A green dispatch with no matching export emits a
`run-turn-telemetry-absent` critical
reflection finding in the same loop-exit reflection window, normally seconds
after the run returns and within the next dispatcher loop pass.

This is the cheap per-dispatch layer. It is paired with a Honeycomb-side
dead-man trigger, `Fabro run_turn dead-man` (id `q33z6VbrjT6`), provisioned on
the `fabro` dataset 2026-08-20: zero `run_turn` spans over the trailing hour
fire an `on_change` alert to the recipient selected by
`HONEYCOMB_OPERATOR_ALERT_RECIPIENT`.

**The window is 8 hours, not the 10 minutes originally specified, and that is
deliberate.** The factory dispatches episodically, so a short window measures
IDLENESS rather than a broken pipeline. Measured 2026-08-20 on the `fabro`
dataset: 8 `run_turn` spans across the trailing 3 hours, all inside a single
10-minute bucket — a 600s window flaps alarm/clear on nearly every bucket. The
`bd-guard` telemetry trigger took the same correction (1h → 8h, 2026-07-18) for
the same reason, and this trigger now matches its 8h/2h shape.

The valid window is bounded **relative to `frequency`**, not by a fixed ceiling.
Both walls were hit against the live API while provisioning: at `frequency=900`
it answers `query: time_range: must be no greater than 3600.`, and at
`frequency=7200` it answers `query: time_range: must be no less than 7200.`. So
raising the evaluation cadence is what buys a longer window — an 8h dead-man
requires the 2h cadence. Override with
`HONEYCOMB_FABRO_RUN_TURN_WINDOW_SECONDS` and
`HONEYCOMB_FABRO_RUN_TURN_FREQUENCY_SECONDS`, keeping the two in step; the
script refuses a window smaller than the frequency rather than emitting a
payload that 422s.

Provision or repair that trigger with the livespec Honeycomb configuration key:

```bash
HONEYCOMB_CONFIG_KEY_LIVESPEC=... \
HONEYCOMB_OPERATOR_ALERT_RECIPIENT=operator@example.com \
  bash orchestrator-image/provision-honeycomb-run-turn-trigger.sh
```

The script is idempotent by trigger name (`Fabro run_turn dead-man`), resolves
the configured recipient by id, email address, name, webhook name, or Slack
channel, and creates or updates the `fabro` dataset trigger with `COUNT`
filtered to `name = run_turn`, `time_range = 28800`, `frequency = 7200`, and
threshold `<= 0`. If the selector is missing or does not match, the script lists
the available recipient ids, types, and redacted email addresses. Set
`DRY_RUN=1` to print the exact payload without changing Honeycomb.

Two Honeycomb API constraints this script had to be corrected for, recorded
because both fail as an opaque 422 with the detail only in the response body:
`query.time_range` is bounded relative to `frequency` (see above), and a tag KEY
must contain only lowercase letters — the original `work-item` tag key was
refused and is now `workitem`.

Verification is still live: break `OTEL_EXPORTER_OTLP_ENDPOINT` on a scratch run
and confirm the dispatcher finding appears and the Honeycomb trigger fires
within the window; restore the endpoint and confirm both clear after the next
successful `run_turn` export. Note that the dispatcher-side half of that check is
unreliable until the marker anomaly tracked by `bd-ib-jb7rzr.9` is resolved; the
Honeycomb-trigger half is independent of it.

### Auth posture (OAuth-only)

- **Never put `ANTHROPIC_API_KEY` in the server's env.** It bills API cost and
  can leak into the sandbox. The agent's model auth is `CLAUDE_CODE_OAUTH_TOKEN`,
  which the Dispatcher injects into the *sandbox* per dispatch — not the server.
- `fabro doctor` on this server should read: GitHub App **configured**, Storage
  OK, Version parity `0.254.0`, and **`[✗] LLM Providers (none configured)` —
  which is CORRECT** (the model key is never on the server). `[!] Sandbox`
  (Daytona) and `[!] Web Search` (Brave) are optional and expected-unconfigured;
  the factory uses the local **Docker** sandbox, not Daytona.
- Credentials live in `~/.fabro/` (the GitHub App integration + `auth.json` +
  SlateDB `storage/`). If `fabro doctor` shows GitHub App **not** configured, the
  vault didn't load — stop and reassess; do not add `ANTHROPIC_API_KEY` to
  "fix" it.

### Tailscale-served

Each factory host runs its own proxy, on the same port, terminated locally by
that host's own `tailscaled` — hp's cannot be set from vps.

| Host | Served URL | Backend |
|---|---|---|
| vps | `https://vps.perch-rudd.ts.net:32276` | `http://127.0.0.1:32276` |
| hp | `https://hp-xubuntu.perch-rudd.ts.net:32276` | `http://127.0.0.1:32276` |

Both are **tailnet-only** (not funneled). On vps, `tailscaled` holds a standing
`tailscale serve` proxy
`https://vps.perch-rudd.ts.net:32276 → http://127.0.0.1:32276`. It persists
across server restarts and returns connection-refused while the loopback backend
is down — so a `:32276` listener owned by `tailscaled` (not `fabro`) means the
proxy is up but the backend is not.

### Host Codex credential refresher timer

The Dispatcher projects the host's Codex `~/.codex/auth.json` into worker
sandboxes with the real refresh token replaced by the non-rotatable sentinel.
The host is therefore the only process allowed to refresh or rotate the real
Codex refresh credential. Today that host credential has measured as a
240-hour / 10-day access token. If no host Codex process runs near the end of
that window, the token reaches a cliff: the dispatch freshness gate refuses new
runs until an operator runs `codex login` on the orchestrator host.

The fix is a host-side user timer that runs the guarded refresher about every
five minutes. The refresher first decodes the access-token `exp` locally and
invokes `codex exec` only when the credential is inside the refresh guard. This
guard matters: Codex has no force-refresh command, and read-only commands such
as `codex login status` and `codex doctor --json` do not refresh `auth.json`.
A naive hourly `codex exec` cron would spend roughly 240 real Codex requests per
10-day cycle. The guarded timer normally spends none, then roughly one to three
tiny requests near the cliff.

The actual host install is a manual maintainer step. Install these as the
`ubuntu` user on the orchestrator host, replacing the checkout path only if the
host checkout differs:

```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/livespec-codex-cred-refresh.service <<'EOF'
[Unit]
Description=Refresh the host Codex credential for the livespec dark factory
Documentation=file:/data/projects/livespec-orchestrator-beads-fabro/orchestrator-image/README.md

[Service]
Type=oneshot
WorkingDirectory=/data/projects/livespec-orchestrator-beads-fabro
ExecStart=/usr/local/bin/with-livespec-env.sh -- python3 /data/projects/livespec-orchestrator-beads-fabro/.claude-plugin/scripts/bin/dispatcher.py codex-cred-refresh --json
EOF

cat > ~/.config/systemd/user/livespec-codex-cred-refresh.timer <<'EOF'
[Unit]
Description=Run the livespec host Codex credential refresher every five minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
AccuracySec=30s
Persistent=true
Unit=livespec-codex-cred-refresh.service

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now livespec-codex-cred-refresh.timer
```

Verify the timer and one manual dry run:

```bash
systemctl --user list-timers livespec-codex-cred-refresh.timer
systemctl --user status livespec-codex-cred-refresh.timer
journalctl --user -u livespec-codex-cred-refresh.service -n 50 --no-pager

/usr/local/bin/with-livespec-env.sh -- \
  python3 /data/projects/livespec-orchestrator-beads-fabro/.claude-plugin/scripts/bin/dispatcher.py \
    codex-cred-refresh --dry-run --json
```

The status command is the alerting surface:

```bash
/usr/local/bin/with-livespec-env.sh -- \
  python3 /data/projects/livespec-orchestrator-beads-fabro/.claude-plugin/scripts/bin/dispatcher.py \
    codex-cred-status --json
```

`codex-cred-status --json` exits `0` when `"alarm": false` and exits `1` when
`"alarm": true`; wire external monitoring to that exit code. The JSON includes
`remaining_seconds`, `remaining_days`, `expires_at_iso`, `refresh_due`, and a
human-readable `message`. The alarm threshold is two days before expiry. The
refresh guard is six minutes before expiry, matching Codex's five-minute
proactive refresh window with a small scheduler margin. A status alarm means the
10-day cliff is close and deserves attention; a timer run returning non-zero or
a repeated `"refresh_due": true` after a non-dry-run refresh means the maintainer
should run `codex login` on the host and then re-check status.

## Real-work substrate (production)

For routine cross-repo work the Dispatcher runs on the **real-work substrate**:
it mounts **no host checkout**. Every git working tree the Dispatcher needs is
fresh-`git clone`d from GitHub *inside* the container, so the only host coupling
is the explicit `-e` secret set. Use the `real-work-dispatch.sh` helper (wired
as `just w7-real-work-dispatch`), which clones impl-beads (the dispatcher code +
the `.fabro/workflows/implement-work-item/` graph) and the dispatch target,
`uv sync`s the dispatcher clone, regenerates the gitignored
`.beads/metadata.json` in the target clone (the `project_id` is server-stable,
so the regenerated value is identical), and dispatches one ready item:

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  just w7-real-work-dispatch -- --target-repo <repo-name> --item <id> --run
```

Under the hood the helper runs the container with **no `-v <host-checkout>`
bind-mount**, only the substrate volume + the injected secrets, then clones
fresh and points the Dispatcher at the clones:

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- docker run -d \
  --name livespec-orchestrator \
  --privileged \
  --cgroupns=host \                                  # nested resource-limited Fabro sandboxes on cgroup v2
  -v livespec-orch-varlib:/var/lib/docker \          # ext4-backed inner graph store (NOT host checkout state)
  -p 127.0.0.1:32276:32276 \                         # web UI / control plane, HOST LOOPBACK ONLY
  --network host \                                   # to reach the EXTERNAL family-tenant Dolt (127.0.0.1:3307)
  -e GITHUB_APP_ID \                                 # GitHub App id (token mint; clone/push/PR)
  -e GITHUB_PRIVATE_KEY \                            # GitHub App private key PEM (token mint)
  -e ANTHROPIC_API_KEY_LIVESPEC_E2E \                # fabro LLM provider key
  -e CLAUDE_CODE_OAUTH_TOKEN \                       # model auth the dispatcher projects per-dispatch
  -e BEADS_DOLT_PASSWORD_<target-tenant> \           # external tenant Dolt password (tenant DB == target repo)
  -e BEADS_DOLT_PASSWORD="$BEADS_DOLT_PASSWORD_<target-tenant>" \
  -e HONEYCOMB_INGEST_KEY_LIVESPEC \                 # telemetry egress key
  livespec-orchestrator:dev \
  sleep infinity
# then, INSIDE the container (the helper does this for you):
#   git clone https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro.git /workspace/livespec-orchestrator-beads-fabro
#   (cd /workspace/livespec-orchestrator-beads-fabro && uv sync --all-groups)
#   git clone https://github.com/<org>/<target>.git /workspace/dispatch-target
#   regenerate /workspace/dispatch-target/.beads/metadata.json  (bd init --server --external)
#   python3 /workspace/livespec-orchestrator-beads-fabro/.claude-plugin/scripts/bin/dispatcher.py \
#     loop --repo /workspace/dispatch-target --budget 1 --mode autonomous --item <id>
```

There is **no read-write host checkout to refresh**: the Dispatcher's post-merge
primary refresh and the post-merge janitor worktree both operate on the
in-container *target clone* (`/workspace/dispatch-target`), which lives under
`/workspace` — not `/tmp` — so the janitor worktree at
`<target-clone>/worktrees/janitor-<id>` is measured by coverage (the family
pyproject's `[tool.coverage.run]` omit excludes `/tmp/*`). The clone origins are
**token-free URLs**; the container's `gh auth setup-git` supplies the credential
out of band, so no token-bearing URL is ever printed or stored.

> The legacy **bind-mount** invocation (`-v /data/projects/livespec-orchestrator-beads-fabro:
> /workspace/livespec-orchestrator-beads-fabro` + `--repo` pointed at it) survives only in the
> Tier-2 *proof* runner (`tier2-dispatch-proof.sh`). It is a proof harness, not
> the production substrate; real work runs on the fresh-clone path above.

> **`--network host` vs `-p`.** If you use `--network host` (to reach the
> external family-tenant Dolt on `127.0.0.1:3307`), the `-p` publish is ignored
> and the fabro web UI is reachable directly on the host's `127.0.0.1:32276`
> (the entrypoint binds `0.0.0.0:32276` inside the container; under host
> networking that is the host's all-interfaces bind — restrict with a firewall
> or prefer a bridge network + explicit route to the Dolt server if you do not
> want the UI on non-loopback interfaces). For a pure-bridge run, drop
> `--network host` and publish only `-p 127.0.0.1:32276:32276`.

### Injectable externals (all runtime-injected; none baked into the image)

| Env var | Purpose | Used by |
|---|---|---|
| `GITHUB_APP_ID` + `GITHUB_PRIVATE_KEY` | the GitHub App credential (thewoolleyman-factory-bot for the fleet; adopters bring their own App), injected by the dispatch TARGET's credential_wrapper on the host and forwarded in. The SOLE GitHub credential source — there is NO fleet-PAT fallback (fail-closed per the github-app-auth design). The entrypoint mints an installation token to `gh auth login` the container (which also authenticates the in-container fresh clones via the `gh` git credential helper; clone origin URLs stay token-free); the Dispatcher's caching provider re-mints before EVERY subprocess so the ~76-minute merge-poll and any >1-hour operation survive token expiry | entrypoint + dispatcher + in-container clones |
| `GITHUB_APP_INSTALLATION_ID` / `GITHUB_API_URL` | optional: pin the App installation (multi-install Apps) / override the API root (GitHub Enterprise) | entrypoint + dispatcher |
| `GH_TOKEN` (host) / `GITHUB_TOKEN` (sandbox) | freshly minted installation tokens. HOST-SIDE, the Dispatcher populates `GH_TOKEN` in its OWN env, re-minted before every subprocess, so the ~76-minute merge-poll and any >1-hour host operation survive token expiry (github-app-auth Pillar 1). INTO THE SANDBOX, the per-dispatch overlay projects the token under the FULL name `GITHUB_TOKEN`, NOT `GH_TOKEN`: `gh` and git-via-`gh` prefer `GH_TOKEN` over `GITHUB_TOKEN`, and Fabro re-projects its OWN re-minted installation token per exec under `GITHUB_TOKEN` (`export GITHUB_TOKEN=<fresh>`). A projected `GH_TOKEN` would SHADOW Fabro's fresh value and expire past the ~60-min TTL at the publish node of a >60-min run (`Invalid username or token`); projecting `GITHUB_TOKEN` lets Fabro's per-exec re-mint overwrite the bootstrap value so the in-sandbox PR node's `gh pr create` / `git push` stays fresh. Never injected at container launch (`gh auth login --with-token` refuses when a token env var is already set, and a launch-time value would expire mid-run) | dispatcher (host `GH_TOKEN`) / sandbox PR node (`GITHUB_TOKEN`) |
| `ANTHROPIC_API_KEY_LIVESPEC_E2E` | fabro LLM-provider API key (name overridable via `FABRO_LLM_API_KEY_ENV`; exported as `ANTHROPIC_API_KEY` into the fabro server's env) | fabro server |
| `CLAUDE_CODE_OAUTH_TOKEN` | model auth the dispatcher projects into each sandbox per-dispatch (run-scoped overlay) | dispatcher |
| `BEADS_DOLT_PASSWORD_<tenant>` | external family-tenant Dolt password (tenant DB == repo name) | dispatcher / `bd` |
| `BEADS_DOLT_PASSWORD` | generic password name consumed by `bd`; set from the tenant-scoped variable at `docker run` time | `bd` |
| `HONEYCOMB_INGEST_KEY_LIVESPEC` | OTel/Honeycomb telemetry egress key | dispatcher |
| `FABRO_PORT` | control-plane / web-UI port (default `32276`) | entrypoint |
| `FABRO_SKIP_LLM` | set non-empty to provision GitHub only (no LLM) | entrypoint |
| `ORCHESTRATOR_SKIP_FABRO` | set non-empty to bring up dockerd only (skip fabro provisioning) | entrypoint |

The **external** family-tenant ledger (the production beads/Dolt store) is *not*
run inside the container — it is reached as an endpoint (`127.0.0.1:3307`, per
the repo's committed `.beads/config.yaml`). The image also ships `dolt` for an
*ephemeral / scratch* in-container ledger (the spike's Goal-5 pattern), which is
a separate, optional substrate used by tier-1 verification — not the family
tenant.

## Observing the dark factory (Fabro web UI)

Fabro serves a web UI from its server on the control-plane port (default
`32276`). It lets a human watch runs, attach to a parked human-gate
(`fabro attach <run-id>`), and inspect the orchestrator's activity from a
browser.

- **URL / port.** `http://127.0.0.1:32276` (the `[server.web]` URL; port set by
  `[server.listen] address`). The entrypoint binds `0.0.0.0:32276` *inside the
  container* so a published port is reachable, and `EXPOSE 32276` documents it.
- **Auth (dev-token).** The control plane is protected by fabro's `dev-token`
  auth. The token is a **secret** — anyone holding it controls the orchestrator
  (GitHub + model creds, dispatch power) — so transfer it over a private channel
  only and never commit it or paste it into a shared log.
  - **Where the token lives / how to retrieve it.** It is stored in fabro's CLI
    auth state at `~/.fabro/auth.json`, under `servers["<server-url>"].token`
    (with sibling keys `kind` = `dev-token` and `logged_in_at`). On the host:

    ```bash
    jq -r '.servers["http://127.0.0.1:32276"].token' ~/.fabro/auth.json
    ```

    For the containerized orchestrator the entrypoint's hand-provisioning
    generates it; retrieve it from the running container the same way, e.g.
    `docker exec <name> jq -r '.servers["http://127.0.0.1:32276"].token' /root/.fabro/auth.json`
    (the server side also persists it under `~/.fabro/storage/`). Note:
    `fabro server start` prints `Auth: dev-token` but does **not** print the
    token value.
  - **Logging a browser in.** `fabro auth login --no-browser` prints an
    `http://127.0.0.1:32276/auth/cli/start?…` PKCE URL to open in a browser. Its
    redirect target is a localhost callback, so it completes cleanly when the
    browser and the server share a host (local use); for a pure SSH-tunnel setup,
    authenticate the UI with the dev-token value retrieved above.
- **Remote access = SSH tunnel, NOT a 0.0.0.0 host bind.** The host publish is
  loopback-only (`-p 127.0.0.1:32276:32276`) by default, so the control plane is
  **not** network-exposed. To view it from your laptop, tunnel over SSH:

  ```bash
  ssh -L 32276:127.0.0.1:32276 <orchestrator-host>
  # then open http://127.0.0.1:32276 in your local browser
  ```

- **Security posture (read this).** The fabro web UI is a **credential-bearing
  control plane**: the server it fronts holds the GitHub token and the model
  API key, and can launch sandboxed runs that clone/push/PR against the family
  repos. Exposing it on a non-loopback interface would hand anyone who can reach
  the port (subject only to dev-token auth) control of those credentials and the
  ability to dispatch work. **Bind the host port to loopback only** (the default
  here) and reach it via SSH tunnel; never `-p 0.0.0.0:32276:32276` on a
  reachable host.

## Secret hygiene

- The image contains **no secret** — no token, key, or password is baked into
  the Dockerfile, the entrypoint, or any committed file. Every credential is
  injected at `docker run` via `-e VAR` (docker forwards the value from the
  invoking process's env; under the 1Password wrapper that value never lands in
  a file or a log).
- Tokens flow into tools via **stdin / env only**; the entrypoint never `echo`es
  a secret and never prints `git remote -v`, env, or token-bearing URLs.
- The staged `fabro` binary is gitignored and never committed.
