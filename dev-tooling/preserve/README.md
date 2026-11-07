# Preserve live factory runs before a cancel

These two scripts are the fleet's stopgap for the standing rule "preserve before any cancel". They copy a
live factory run's committed git tree out of its Kubernetes sandbox and push it to the run's own origin. A
cancelled or restarted run's work then survives.

They were written in a session scratchpad during plan kubernetes-sandbox-backend (bd-ib-nmuyjc) and are
committed here so that the dispatcher and any successor session can run them. The durable product path
that retires them is bd-ib-vraou4 (cancel-for-restart preserve path).

## Usage

Run from the control node (the VPS) with this host's own GitHub auth:

```bash
dev-tooling/preserve/preserve_runs.sh [RUN_ULID ...]   # no args: every Running pod in the factory namespace
dev-tooling/preserve/represerve.sh <UTC HH:MM> <RUN_ULID> <alias>
dev-tooling/preserve/preserve_dispatch.sh [--dry-run] <DISPATCH_ID> [<factory-url>]
dev-tooling/preserve/parity_read.sh <DISPATCH_ID> [<factory-url>] | --pod <namespace> <pod>
```

- `preserve_runs.sh` prints one TSV row per run: `RUN NODE REPO SHA REF VERDICT SECONDS`.
- `represerve.sh` waits until `HH:MM` UTC (a past time means now), runs one preserve, and on success also
  writes `refs/heads/preserve/<alias>`, for example `bd-ib-<item>-<RUN12>`, in the run's own repository.
- `preserve_dispatch.sh` takes the Dispatcher's DISPATCH ID, the id the dispatcher and coordinator quote, instead of
  the run ULID. It resolves the run through the factory server's `livespec.dispatch.id` run label, checks that the
  sandbox clone's `livespec.factoryRunId` git-config marker names the same dispatch id, then runs
  `preserve_runs.sh <RUN_ULID>`. `--dry-run` resolves and locates without pushing. It refuses, pushing nothing, with
  `RESOLVE_FAILED` (zero or several runs carry that id), `NO_POD` (no Running sandbox pod, as for any terminal run),
  `MARKER_MISMATCH` (the pod's clone names another dispatch) or `NO_CLIENT` (no fabro client). The client defaults to
  `.livespec.jsonc`'s petri `bin`, the client of the build petri serves; override it with `FABRO_BIN`.
- `parity_read.sh` is the sandbox canary's exec-environment parity read (livespec-dev-tooling
  `.ai/coordinator-duties.md`, "A sandbox driver bump's canary checks environment parity"). For one live sandbox
  pod it prints the QoS class, container requests and limits, pod- and container-level `cpu.max` and `memory.max`,
  every process's Umask with its argv, and the environment variable NAMES (never values) of one exec'd command.
  Compare that against the previous driver's baseline, which the script's header records. It resolves a dispatch
  id exactly as `preserve_dispatch.sh` does, and adds the refusal `NODE_UNREACHABLE` when the pod's node is not an
  ssh alias from here.
- `PRESERVE_WORK` sets the local working directory. The default is
  `${XDG_STATE_HOME:-~/.local/state}/livespec-preserve`.
- For many runs, start one `represerve.sh` per run in parallel. Each process uses its own ssh master
  connection.

## Guard rules (do not weaken)

1. **Read-only on every fleet host.** The scripts use only `kubectl get`, `crictl ps` / `crictl inspect`,
   `sudo find` and `sudo cat` over ssh (fleet_host_guard refuses `tar`).
   - The tree is copied with ONE `find -printf '%s %P'` and ONE bulk `cat`, then split locally by size.
   - A per-file ssh round trip starved at 16 runs in parallel.
2. **Copy the run branch, never HEAD.** The script uses the tip of `refs/heads/fabro/run/<RUN>` when it
   exists. A late node (refresh_repair) can leave HEAD detached on master, and preserving HEAD then drops
   the run's work (rhivsm, 2026-11-05).
3. **fsck before push.** `git fsck --connectivity-only` must pass on the chosen sha. A commit that lands
   mid-copy fails it, and the copy is retried up to 3 times.
4. **Ancestry guard.** A preserve ref or alias is never moved to a tip that does not contain its old
   value. That pass is written to a `-<sha12>` sibling ref instead, and the newest tip is on the suffixed
   ref.
5. **Push retry.** GitHub answers `[remote rejected] ... (failed)` to concurrent pushes into one
   repository. Each push retries 5 times with backoff.
6. **ls-remote verify.** A row reads `VERIFIED` only after `git ls-remote` returns the pushed sha. It
   re-reads up to 5 times, because GitHub can lag.
7. **Create-only needs-human ref.** After VERIFIED, the script writes `refs/heads/needs-human/<RUN_ULID>`
   at the same sha, which is the only ref `route_recovery` seeds from. If that ref already exists at
   another sha, it is never moved and the row reads `VERIFIED+NH_KEPT:<sha12>`. The `preserve/` ref
   remains the audit copy.
8. **The pod must still be Running.** A run whose sandbox has already been torn down has no tree to copy.
   Its row reads `FAILED(... sha=none)`.

## Shell gotcha

In zsh, `"$sha:refs/..."` applies the `:r` modifier to `$sha`. Always write `"${sha}:${ref}"`.
