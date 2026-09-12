# Hand-building a change in the Fabro fork

This note records how a work-item whose implementation lands in
`thewoolleyman/fabro` (the pinned factory engine) is carried from this
tenant's ledger to a merged fork pull request and back. It exists because
none of it is derivable from `AGENTS.md`: that file says the factory pins
`factory-integration` and forbids modernizing past 0.254, and
`.ai/cross-tenant-execution-mirror.md` covers a target repository that HAS a
ledger tenant. The fork has none, so the mirror convention cannot apply and
the Dispatcher cannot sandbox the work. The first item to walk this path was
`bd-ib-mujvyn` (plan `bd-ib-jxvgq5`, S4) on 2026-09-12; every fact below was
measured on that walk.

## When this path applies

- The change is to the Fabro engine itself: the code the factory RUNS ON, not
  code the factory runs. Set the item's `factory_safety` to
  `mutates-host-machinery` through the set-factory-safety valve (journaled) so
  the dispatcher drain can never pick it up and try to build Rust fork work
  inside this repository's sandbox.
- The maintainer has approved starting the hand-build. Filing the item and
  starting it are separate decisions on this track; the item's notes say which
  has been given.
- Open the item through `driver-dispatch:<id>` when the hand-build starts.
  Close it through `close-work-item <id> --reason "<fork PR URL> merged at
  <merge SHA>"`; the fork has issues disabled, so the pull request is the
  tracking artifact and the merge SHA is the closure evidence. Never re-open
  the driver door on an item that is already `active`.

## The worktree

- Base every branch on `origin/factory-integration`, never on `main` and never
  on an upstream tag. Worktrees live under `~/.worktrees/fabro/<branch>`; the
  fork's primary clone is `~/.worktrees/fabro/factory-integration`.
- Share the build cache: `CARGO_TARGET_DIR=/home/ubuntu/.worktrees/fabro/factory-wave-c/target`.
  A cold workspace build of the fork is a from-scratch Rust dependency compile
  on a box that runs many concurrent sessions; the shared target directory is
  what makes the gates incremental.
- Run `uptime` BEFORE any build or test run, every time, and bound the
  compile (`CARGO_BUILD_JOBS`, `nice`, `--test-threads`) when the load is
  already high. The load on 2026-09-12 was 25 to 30 on 18 cores from other
  sessions' cargo and pytest runs.

## The merge gate is local

The fork's GitHub workflows run only on `main` (`rust.yml`,
`typescript.yml`: `branches: [main]`), so a pull request against
`factory-integration` shows NO checks and `gh pr view` reports an empty
status rollup. That is not a green signal; it is the absence of an
instrument. The merge gate is therefore the same set the fork CI would run,
executed locally against the branch tip:

```bash
cd ~/.worktrees/fabro/<branch>
export CARGO_TARGET_DIR=/home/ubuntu/.worktrees/fabro/factory-wave-c/target
cargo +nightly-2026-04-14 fmt --check --all
cargo +nightly-2026-04-14 clippy --workspace --all-targets -- -D warnings
cargo nextest run -p <every crate the diff touches>
```

`nightly-2026-04-14` is the toolchain the fork's own CI pins for fmt and
clippy; a different nightly reports different lints and is not evidence.
Record which gates ran, against which commit, on the ledger item before
merging. A gate that was killed before it reported is not a gate that ran:
the S4 session's wind-down killed the server and CLI test targets and the
clippy run mid-flight, and the next session had to re-run them. Launch long
gates DETACHED through this repository's runner and watch the log, never as
a foreground call a wind-down can cancel and never as an agent-harness
background task:

```bash
cd ~/.worktrees/livespec-orchestrator-beads-fabro/<branch>   # any worktree with the pack
run_id=$(mise exec -- just gate-start -- /path/to/gate-script.sh)
mise exec -- just gate-status "$run_id"    # exit 75 while still running
```

Measured 2026-09-12 on vps: a `run_in_background` harness task running the
same nextest gate was killed three times in a row with "stopped because the
system is running low on memory" during the `fabro-server` test-binary
link, and so was a background `gate-wait` waiter, while `free -g` showed 52
to 54 GB available each time. The trigger is the harness's own heuristic,
not the kernel. The detached gate-runner job launched for the identical
script survived that window untouched and reported 2,317 passed. Wait on it
with a polling watch of `tmp/gate-runs/<run_id>/output.log` for the
script's own done marker, and keep `CARGO_BUILD_JOBS` at 4 to 6 with
`nice -n 10` on this shared box regardless.

## Merging and the runbook duty

- Merge with `gh pr merge <n> --rebase -R thewoolleyman/fabro`. The fork
  rebase-merges, so the merge SHA is the LAST commit of the rebased series,
  and the branch SHA does not survive; verify the landing with a content
  check on `origin/factory-integration`, not by branch containment.
- `SPECIFICATION/constraints.md` §"Fabro runtime constraints" requires
  `orchestrator-image/README.md` §"`factory-integration` — the carrier branch
  for unreleased fixes" to be updated IN THE SAME CHANGE whenever the
  carried-fix set changes. A merged fork PR changes that set, so the closing
  pull request in THIS repository adds the row, even when the build is not
  yet pinned on any host. Say in the row whether it is deployed.
- Merging into `factory-integration` deploys NOTHING. Re-pinning hp and vps is
  the separate runbook in the same README section, and the two hosts can
  diverge for as long as the second rollout takes. When a later dispatch is
  evidence about the new build, read `fabro --version` ON the factory host.

## Closing out

1. Close the ledger item with the PR URL and merge SHA in the reason.
2. Land the closing pull request here: the research note under the owning
   plan's `research/` directory, the README row, and any stale build lines
   the walk corrected.
3. Remove the fork worktree and delete the fork branch, local and remote:

   ```bash
   git -C /data/projects/fabro worktree remove ~/.worktrees/fabro/<branch>
   git -C /data/projects/fabro branch -D <branch>
   git -C /data/projects/fabro push origin --delete <branch>
   ```

4. Append the plan handoff naming the merge SHA, the closing PR, and what the
   deploy slice still owes.
