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

- `preserve_runs.sh` prints one TSV row per run: `RUN NODE REPO SHA REF VERDICT SECONDS SOURCE`. `SOURCE`
  names the commit it preserved (see rule 9), and `VERDICT` reads `EMPTY` when no candidate carried work
  (rule 10).
- `represerve.sh` waits until `HH:MM` UTC (a past time means now), runs one preserve, and on success also
  writes `refs/heads/preserve/<alias>`, for example `bd-ib-<item>-<RUN12>`, in the run's own repository.
  It writes the alias only on a `VERIFIED…` row, so an `EMPTY` row gets no alias.
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
7. **Needs-human ref only at the wall-budget line or before a cancel (temporary).** Every caller: pass
   `PRESERVE_WRITE_NEEDS_HUMAN=1` on a preserve at the 330-minute wall-budget line or right before a
   cancel, and on no other. A routine preserve writes only the `preserve/` ref, because a run-keyed
   `refs/heads/needs-human/<RUN_ULID>` seeds recovery and can lead the seed list, so a mid-run copy
   pre-empts the tree the run's own ending later pushes. `preserve_dispatch.sh` and `represerve.sh`
   inherit the variable. With it set, the ref is `refs/heads/needs-human/<DISPATCH ID>`: the dispatch id
   is read from the sandbox clone's `livespec.factoryRunId` marker, because that is the name the factory's
   own needs-human ending writes and every seed lookup reads (a run-ULID-keyed ref left two names per run
   and lookups finding neither; bd-ib-mfl2qa, 2026-11-08). It is written create-only at the verified sha,
   and the row reads `VERIFIED+NH:needs-human/<dispatch id>`. If it already exists at another sha (the run
   ended on its own) it is never moved: this pass is written to `needs-human/<dispatch id>-<sha12>` and the
   row reads `VERIFIED+NH_KEPT:<old sha12>+NH_SUFFIX:<that ref>`. A clone with no marker gets no
   needs-human ref, and the row reads `VERIFIED+NH_NO_DISPATCH_ID`. The `preserve/run-<RUN ULID>` ref
   stays the run-keyed copy.
   - **Known cost, accepted by legacy-coordinator-agent on 2026-11-07:** a run preserved at 330 minutes
     that then ends on its own still gets a stale seed. The dispatcher's route read catches that before
     any ticket, whereas a wall-budget ending with no seed is caught by nothing.
   - **This rule is temporary.** When bd-ib-qshcwc ships, remove the variable and restore one behaviour.
8. **The pod must still be Running.** A run whose sandbox has already been torn down has no tree to copy.
   Its row reads `FAILED(... sha=none)`.
9. **Preserve the commit that carries the work, judged against the merge base (bd-ib-anmcjq).** A fix or
   refresh round can reset `fabro/run/<RUN>` to plain master. A preserve of that tip then holds none of
   the run's work and still read `VERIFIED` (bd-ib-7fdesc run `01M6Z3TFJRES` and bd-ib-reuccp run
   `01M6YYE03JKS`, 2026-11-09). A commit carries work when its tree differs from the tree of its merge base
   with `origin/master`. A two-way diff against master's current tip would count master's later commits as
   work, so it is never used. The bulk copy also takes the run branch's reflog and the `HEAD` reflog. The
   candidates, in order, are: the run-branch tip (`tip`, or `HEAD` with no run branch), then the run
   branch's reflog newest first (`reflog@{N}`), then the `HEAD` reflog newest first (`HEAD@{N}`). The first
   candidate that carries work and passes rule 3's fsck is preserved, and the row's `SOURCE` names it.
10. **Nothing carrying work is `EMPTY`, and `EMPTY` pushes nothing.** When no candidate carries work, the
    row reads `EMPTY` and the script pushes no `preserve/run-<RUN>` ref and no `needs-human` ref, so
    `represerve.sh` writes no alias. When the choice cannot be made at all (the copy, fsck or the
    `origin/master` fetch failed), the row reads `FAILED(...)`, never `EMPTY`. Until bd-ib-ofvsr3 and
    bd-ib-vraou4 ship and retire these scripts, an operator reading any older preserve applies the same
    test by hand: `git diff --quiet $(git merge-base <ref> origin/master) <ref>` exiting 0 means NOT
    preserved.

11. **A container worker node is read through `kubectl exec`, never ssh (livespec-dev-tooling-smzkpu).** A node
    labelled `homelab-worker.livespec.dev/class=worker` runs plain containerd, so it has no `k3s crictl`, and it
    takes no ssh login: creating one is credential creation, which stays the maintainer's (legacy-coordinator-agent
    ruling, 2026-11-09). For such a node `preserve_runs.sh` reads the sandbox through
    `k3s kubectl exec -n factory <pod> -c sandbox` on poweredge-xubuntu, the route the cluster already authorizes.
    It runs only `test -d`, `git config --get`, `cat`, `find` and `xargs -0 cat` there, still with one `find` and
    one bulk `cat`. The file list goes to `xargs` on stdin, because as exec arguments it would ride in the exec
    request's URL. Every other node keeps rule 1's ssh and crictl route. Which nodes are container workers is read
    from the cluster on each pass, so a newly enrolled worker needs no change here.

## Shell gotcha

In zsh, `"$sha:refs/..."` applies the `:r` modifier to `$sha`. Always write `"${sha}:${ref}"`.
