# W7 Tier-2 Containerized Dispatch Proof

This note is the runbook for `livespec-impl-beads-dn9`, the next W7
Beads/Fabro slice after the DinD spike (`livespec-impl-beads-o2f`) and the
production orchestrator image (`livespec-impl-beads-8bc`). The step-1 image
proved Tier 1: build, inner Docker daemon health, Fabro provisioning, web UI
reachability, and an ephemeral Dolt / `bd` round trip. Tier 2 proves one real
dispatcher invocation from inside that container.

## Proof Shape

Use `orchestrator-image/tier2-dispatch-proof.sh`. It starts the
`livespec-orchestrator:dev` image, lets the normal entrypoint provision the
inner Docker daemon and Fabro server, then runs:

```bash
python3 /workspace/livespec-impl-beads/.claude-plugin/scripts/bin/dispatcher.py \
  loop \
  --repo /workspace/livespec-impl-beads \
  --budget 1 \
  --mode shadow \
  --item <tiny-ready-item> \
  --no-close-on-merge \
  --journal /tmp/livespec-tier2-dispatch-journal.jsonl \
  --poll-attempts 3 \
  --poll-interval-seconds 10 \
  --json
```

The item is explicit and shadow-mode only. The script never selects from the
ready queue, never creates a work item, and passes `--no-close-on-merge` so the
proof cannot close the ledger item automatically. The operator must provide a
deliberately tiny, isolated, ready work item that is safe for a one-dispatch
probe.

The production tenant is the host's Dolt sql-server at `127.0.0.1:3307`, as
recorded in the repo's `.beads/config.yaml`. The proof runner therefore starts
the orchestrator container with host networking by default
(`TIER2_USE_HOST_NETWORK=1`) so that loopback still reaches the host tenant.
This is still Docker-in-Docker, not Docker-outside-of-Docker: the host Docker
socket is not mounted, and the script verifies that absence before dispatch.
The runner also maps `BEADS_DOLT_PASSWORD_livespec_orchestrator_beads_fabro` into the generic
`BEADS_DOLT_PASSWORD` process variable consumed by `bd`, without printing the
secret value.
It also maps `LIVESPEC_FAMILY_GITHUB_TOKEN` into the conventional `GH_TOKEN`
process variable before invoking the Dispatcher; the Dispatcher materializes
that `GH_TOKEN` into the mode-600 Fabro run overlay so the in-sandbox PR node can
run `gh pr create`.

With host networking enabled, the runner defaults Fabro to `32281` instead of
`32276` unless `FABRO_PORT` is explicitly set. That avoids colliding with a
maintainer's existing host Fabro server on the normal default port. The
dispatcher is executed with the mounted repo as its working directory so `bd`
can auto-discover `.beads/`.

The outer orchestrator container also runs with `--cgroupns=host`. Plain nested
containers work without it, but Fabro's sandbox launch applies the workflow's
CPU/memory resources; on cgroup v2 those resource-limited nested containers
fail without the host cgroup namespace.

The runner marks the mounted checkout as a Git `safe.directory` inside the
orchestrator container before invoking Fabro. Without that trust entry, root
inside the container rejects the host-owned checkout as dubious ownership;
Fabro cannot derive a clone source and falls back to an empty `/workspace`.

`MOUNT_REPO` must point at a checkout with both Beads pointer files present:
the committed `.beads/config.yaml` and the gitignored `.beads/metadata.json`.
Fresh worktrees usually lack `metadata.json`; use the primary checkout or
regenerate/copy the pointer before running the proof from a worktree.

## Running

Preflight only:

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  bash orchestrator-image/tier2-dispatch-proof.sh --preflight
```

Build the image first if needed:

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  bash orchestrator-image/tier2-dispatch-proof.sh --preflight --build-image
```

Run the proof:

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  bash orchestrator-image/tier2-dispatch-proof.sh --run --item <tiny-ready-item>
```

The script requires these environment variable names to be present, normally
from the 1Password wrapper:

- `LIVESPEC_FAMILY_GITHUB_TOKEN`
- `ANTHROPIC_API_KEY_LIVESPEC_E2E`
- `CLAUDE_CODE_OAUTH_TOKEN`
- `BEADS_DOLT_PASSWORD_livespec_orchestrator_beads_fabro`
- `HONEYCOMB_INGEST_KEY_LIVESPEC`

It reports only presence and byte counts for secret variables. It does not
print values.

## Evidence To Capture

Record the following in this file or in a successor note before closing
`livespec-impl-beads-dn9`:

- the exact item id used for the tiny ready-item proof;
- the script invocation;
- the inner Docker storage driver;
- confirmation that no host Docker socket was mounted;
- the dispatcher exit code;
- the redacted dispatcher journal tail;
- the inner `docker ps -a` summary after dispatch;
- whether cost/telemetry spans were token-observable, dollar-overlay-only, or
  still dark.

## Evidence So Far

2026-06-20 local time / 2026-06-19 UTC:

- `mise exec -- just w7-tier2-dispatch-proof -- --help` succeeded after the
  script was adjusted to tolerate the bare `--` that `just` forwards.
- `/data/projects/1password-env-wrapper/with-livespec-env.sh -- bash
  orchestrator-image/tier2-dispatch-proof.sh --preflight --build-image`
  succeeded:
  - all required secret env var names were present; the script printed only
    byte counts;
  - the script staged the host Fabro binary into the gitignored build context;
  - Docker built `livespec-orchestrator:dev`;
  - built image id:
    `sha256:913eeda6955aa58dff51b6950f34a7d2342e6928b4a8df6894243b8d234543a2`;
  - image size reported by Docker: `1064148333` bytes.
- A second preflight without `--build-image` succeeded and confirmed the image
  is present.
- First real-dispatch attempt reached the inner Docker proof, then failed
  before journaling because the image was missing `typing_extensions`, which
  the mounted dispatcher import graph uses.
- After adding that image dependency, the next attempt reached the ledger and
  failed before journaling because the bridge-networked container could not
  reach the host's `127.0.0.1:3307` Dolt tenant and had not projected the
  family-scoped password into `BEADS_DOLT_PASSWORD`. A host-networked minimal
  probe then succeeded: inside `livespec-orchestrator:dev`,
  `bd list --status all --limit 1 --json` reached the tenant and produced a
  JSON response.
- After adding host networking, the next attempt first collided with the host's
  existing Fabro server on `127.0.0.1:32276`, then with `FABRO_PORT=32281`
  reached dispatch startup but still failed before journaling because
  `docker exec` launched the dispatcher from `/`; `bd` therefore could not
  auto-discover the mounted repo's `.beads/` directory.
- After adding a dispatcher working directory, the next attempt reached the
  dispatch command line but failed before journaling because `docker exec`'s
  `-w` option was ordered after the container name; Docker treated `-w` as the
  executable.
- After fixing `docker exec`, the next attempt wrote a dispatcher journal and
  launched Fabro run `01KVH5KTRRQ08ZR8W24NXP27BF`, but the Fabro sandbox failed
  to initialize on the inner Docker daemon with a cgroup-v2 error:
  `cannot enter cgroupv2 "/sys/fs/cgroup/docker" with domain controllers`.
  Controlled probes showed plain nested `hello-world` and the pinned sandbox
  image run successfully, but `docker run --cpus 4 --memory 8g ...` reproduces
  the error unless the outer container is launched with `--cgroupns=host`; with
  that flag, the resource-limited pinned sandbox image prints `cgroupns-ok`.
- After adding `--cgroupns=host`, Fabro run `01KVH6N9SEZDCKV1HDNCRG8C4H`
  reached `Sandbox: docker (ready in 39s)`, but setup failed on
  `git fetch --unshallow --quiet` because Fabro logged
  `Clone source missing for clone-based sandbox`; inspection of the preserved
  container showed `git -C /workspace/livespec-impl-beads status` failed with
  Git's dubious-ownership guard. The runner now installs a `safe.directory`
  entry for the mounted repo before dispatch.
- Minimal wrap boundary: with the safe-directory fix in place, the same proof
  command against `livespec-impl-beads-ctq` reached Fabro run
  `01KVH6WANRMTRTM7EBRFB5TGBF`. The run launched the pinned sandbox image on the
  inner Docker daemon, cloned `https://github.com/thewoolleyman/livespec-impl-beads`
  at base `master` `a269ac88e1cb`, completed `Implement (Red-Green-Replay)` in
  54s, and completed `Janitor: just check` in 2m17s. Fabro then pushed branch
  `feat/livespec-impl-beads-ctq` with doc-only sentinel commits, but the PR node
  failed because the sandbox had no GitHub credential under `GH_TOKEN` and no
  `gh` auth config. That PR-creation credential projection is deliberately
  deferred to follow-on item `livespec-impl-beads-5qv`; the Tier-2 minimal proof
  is considered green only through real dispatch, sandbox clone, implementation,
  janitor, and branch push.
- Follow-on `livespec-impl-beads-5qv` fixes that final credential-projection
  gap by requiring the Dispatcher to project `GH_TOKEN` into the sandbox env
  table and by having this proof wrapper source it from
  `LIVESPEC_FAMILY_GITHUB_TOKEN`.

Current tiny proof target: `livespec-impl-beads-ctq`, a P3 doc-only item
created specifically for this Tier-2 run. Do not use `dn9` itself as the
dispatch target. The actual Tier-2 run is:

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  bash orchestrator-image/tier2-dispatch-proof.sh --run --item livespec-impl-beads-ctq
```

## Codex Runtime Classification

Tier 2 still runs the Beads/Fabro orchestrator, not a Codex driver. Codex
participation in this tier is therefore evidence classification:

- `livespec-impl-beads` has no Codex project adapter today; Codex support is
  contributor-workflow support through `AGENTS.md`, repo hooks, and stable
  CLI/script entry points.
- The core `livespec` checkout has verified Codex project-local adapters for
  `help`, `next`, and `doctor`; use those only where the proof touches core
  spec-side commands.
- Any Claude-only mechanics encountered by the run, especially Claude Code
  hooks or Fabro ACP behavior, must be named as Claude-driver-only or Codex
  replacement-required rather than silently inherited.

## Telemetry Rule

Tier-2 evidence remains token-first. Claude Code dollar estimates are a
provider-specific overlay. Codex/OpenAI evidence must not be inferred from
Claude Code cost spans; a future OpenAI extractor must map OpenAI token fields
explicitly.
