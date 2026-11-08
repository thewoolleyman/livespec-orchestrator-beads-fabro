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

- Base every branch on the carrier branch the SERVING factory build was cut
  from, never on `main` and never on an upstream tag. Do not assume it is
  `factory-integration`. Read the serving build's commit from the
  `binary_source` that `livespec-dev-tooling`
  `ansible/inventory/host_vars/gmktec-xubuntu.yml` pins, then from the
  `BUILD_INFO` file staged beside that binary, which names the source ref.
  CORRECTION (2026-11-02, work-item `bd-ib-voozdp`): this bullet named
  `origin/factory-integration` until then, but gmktec's `petri` and
  `mi-homelab` instances serve `carrier-candidate-registered-20261023` at
  `9f6c38fab`. That branch patches Petri to
  `thewoolleyman/petri` `fabro-integration-registered-20261023` (see
  `orchestrator-image/README.md`), so `factory-integration` no longer
  describes what serves. A fix based on it would not rebuild the serving
  lineage. Merge the fix into that same carrier branch. Worktrees live under
  `~/.worktrees/fabro/<branch>`.
- No fork build or gate runs on vps by default. The merge gate and the
  carrier build both run on the `fabro-k3s` ARC scale set (the two sections
  below); a vps build is only the fallback in "The dev-host fallback". An ad
  hoc host build on gmktec is not sanctioned either way.

## Nightly tags are release tags

- Upstream `fabro-sh/fabro` has published only nightly prerelease tags
  since stable `v0.254.0` (2026-06-04); the newest on 2026-11-02 was
  `v0.403.0-nightly.0` (2026-10-31). `SPECIFICATION/constraints.md`
  §"Fabro runtime constraints" makes an official nightly or prerelease tag
  eligible on the same terms as a stable tag, and
  `_dispatcher_fabro_currency.py` reads no release class. Never treat
  stable-versus-nightly as an open question or a blocker.
- A base fails the currency rule in only two ways: (a) it is not EXACTLY a
  published tag, or (b) its tag was published more than 30 days before the
  newest release. The serving carrier `carrier-candidate-registered-20261023`
  fails (a): it sits on upstream `main` at `9d9cbe9f4`, four commits (two
  merged PRs, #1062 and #1065) past `v0.393.0-nightly.1` (`e28675a1d`).
- "Candidate" in this repository's ops vocabulary names the
  `fabro-server-candidate` canary instance on gmktec `:32278`, not a
  release tag.

## The merge gate is the `fabro-k3s` scale set

Since 2026-11-06 (`bd-ib-dqxcsh`; `SPECIFICATION/constraints.md`
§"Fabro runtime constraints", "Fork gate and build venue") the fork carries
`.github/workflows/fork-gates.yml` on `carrier-candidate-registered-20261023`
(fork PR #27, `0d5ce5f60`) and on `factory-integration` (fork PR #28,
`161890e36`). It runs Format (`cargo fmt --check`), Clippy and Test (nextest)
on the self-hosted ARC scale set `fabro-k3s` for:

- every push to a `carrier-*` branch or `factory-integration`;
- every pull request targeting one of those branches;
- a manual `workflow_dispatch`.

So a fork pull request against a carrier branch now shows those three checks in
its status rollup, and THEY are the merge gate: merge only when all three are
green on the PR head. An EMPTY rollup on such a pull request is still not
green; it means the workflow is missing from the target branch, or the scale set
is down (see the fallback).

- The jobs run in a `buildpack-deps:noble` container on ARC's kubernetes
  container mode, with no Docker daemon. The Docker sandbox scenarios self-skip
  there, so a change that reaches the Docker backend still needs its own
  evidence. Upstream's `rust.yml` keeps running for `main` only, on its own
  runners.
- Two environment fixes live in the workflow and must survive any rewrite.
  First, `safe.directory` is set in the SYSTEM gitconfig, because the
  `fabro-cli` test harness clears the environment and sets a temporary
  `HOME`. Second, nextest runs under `tini -s`, because the Petri crash
  scenarios poll `process_running`, which counts zombies, and the container
  has no reaper.
- The scale set's `minRunners` is 0, so an idle scale set lists NO runners
  (`gh api repos/thewoolleyman/fabro/actions/runners` reports
  `total_count 0`). That is not an outage. Its health signal is the ARC
  listener `fabro-k3s-*-listener` and a queued job being picked up. The jobs
  API names the pod that ran each job (`runner_name`
  `fabro-k3s-<id>-runner-<pod>`).
- Measured on the first green run, 42132952719 (2026-11-06):
  4,421 of 4,421 tests passed and 60 were skipped. In 87 one-minute samples
  of the vps process table during that run, no `cargo`, `rustc`,
  `clippy-driver` or `cargo-nextest` process ran.

The RED/GREEN evidence for a change's own tests is still owed, and it stays
TARGETED (maintainer ruling 2026-11-03). Get it on the cluster as well. Push the
test-only commit to the pull request first and read the Test check red. Then
push the fix and read it green. Record both run ids on the ledger item. Do not
widen a local run to the whole crate or workspace to get the same evidence.
Full `fabro-petri` runs on two one-function diffs (`bd-ib-6r3yax`,
`bd-ib-bpucez`) once cost about an hour each on a loaded host. They surfaced
only pre-existing test defects.

### A test verdict never depends on load

Maintainer ruling 2026-11-03: a test's verdict must never depend on host
load or wall-clock time. The only time bound is the overall run timeout
(locally, in the factory and in CI). A test that genuinely hangs is a
separate bug. Consequences for a gate:

- A test that fails or times out on load or timing is a TEST DEFECT. File
  it once as a root-fix item, or add the instance to the existing item, and
  move on. Retries, skips, `#[ignore]` and longer deadlines are not fixes.
- Never clear a failure by rerunning it solo or at lower load; a rerun pass
  is not evidence. Never spend runs comparing a flaky test across commits:
  on 2026-11-03 that cost about two hours on the blob test and decided
  nothing the root-fix item did not already say.
- A failing test that the change's own diff cannot reach does not block the
  merge once it is tracked; one the diff can reach does.

Tracked fork test defects at 2026-11-03: `bd-ib-aqcgxz` (blob round-trip
race), `bd-ib-4uge7u` (test-local wall-clock deadlines in two tests),
`bd-ib-adrhkf` (the per-test nextest hard kill in `.config/nextest.toml`,
about 120 s in `profile.ci` and 20 s for `fabro-petri` in
`profile.default`, which kills healthy tests under load), and
`bd-ib-gmuxd4` (the stall test's real-clock budget).

Two of those are fixed since 2026-11-06. `bd-ib-aqcgxz` was a Petri
product defect: the output drain read a stalled log consumer as silence and
dropped an exited process's output tail (thewoolleyman/petri#4, pinned by
fork PR #33). `bd-ib-adrhkf` was fixed by fork PR #34 (`c2be004f5`):
`profile.ci` now flags SLOW at 30 s and terminates no test, through one
`filter = "all()"` override, because a `profile.default` override outranks
the `ci` base and would otherwise keep its kill. The fork-gates Test job's
`timeout-minutes: 120` is the run-level bound.

Work independent fork items in PARALLEL, each in its own worktree on the
carrier branch, and fold their merges into one engine build. Do not queue
them one at a time.

`nightly-2026-04-14` is the toolchain the fork's own CI pins for fmt and
clippy; a different nightly reports different lints and is not evidence.
Record which gates ran, against which commit, on the ledger item before
merging, by run id. A gate that was cancelled or superseded before it
reported is not a gate that ran.

## A fix that lands in the Petri fork

Some fork items are Petri defects. `thewoolleyman/petri`
`fabro-integration-registered-20261023` is the branch the carrier's
`[patch]` names, and its `Cargo.lock` pin says which commit serves. That
fork has NO runner: its pull requests (#3, #4) show no checks. Gate a Petri
change on `fabro-k3s` instead:

- Push a throwaway branch of `thewoolleyman/fabro` carrying a push-triggered
  workflow that fetches the Petri commit and runs fmt, clippy and the
  targeted tests.
- The attractor step tests launch the host sandbox plugin. Build it with
  `SANDBOX_DRIVER_PLUGINS=host scripts/plugins-build.sh` and export
  `PETRI_SANDBOX_HOST_PLUGIN`; without it they fail in about 0.01 s with
  stage `Failed`.
- Merge the Petri PR first, then a Fabro PR that moves every Petri entry in
  `Cargo.lock` to the merge commit; its Fork gates are the Fabro-side merge
  gate.

The worked example is plan `fabro-currency` research note 024.

## Carrier builds run on `fabro-k3s`

The release binary a factory build pins is built by `carrier-build.yml`, a
`workflow_dispatch` workflow on `factory-integration` (the fork's default
branch, which `workflow_dispatch` requires). It builds any named ref on the same
scale set, with the hand-build recipe: `bun install --frozen-lockfile`;
`cargo clean --release -p fabro-spa`; `cargo dev build --release -p fabro-cli`,
under `NODE_ENV=production`.

```bash
gh workflow run carrier-build.yml -R thewoolleyman/fabro \
  --ref factory-integration -f ref=<carrier branch, tag or commit>
gh run download <run-id> -R thewoolleyman/fabro -n fabro-engine-<sha12>
```

The artifact `fabro-engine-<sha12>` carries `fabro`, `VERSION`, `SHA256SUMS`
and a `BUILD_INFO` line naming the source repository, ref, commit, recipe,
build time, runner and run URL. The workflow fails if `fabro --version` does
not name the commit it built. GitHub keeps the artifact for 90 days. Stage it
for a host roll from the downloaded files, and verify `SHA256SUMS` and
`BUILD_INFO` before you pin it. Building the binary on vps is the fallback,
not the route.

## The dev-host fallback

Use this ONLY while the cluster venue is unavailable. That means the
`fabro-k3s` listener is absent, or a fork-gates or carrier-build job is never
picked up. Record the fallback, and why it was needed, in the work item's notes
(`SPECIFICATION/constraints.md`, "Fork gate and build venue"):

- Throttle (coordinator ruling 2026-11-02): `nice -n 19`,
  `CARGO_BUILD_JOBS=4`, nextest limited to `-p` the touched crates with a low
  `--test-threads`. Run `uptime` before every build. At nice 19 the gate takes
  only the cycles other sessions leave idle, so it pauses only when
  `mpstat 5 1` reports idle below 8%. The throttle protects the shared box. It
  never changes how a verdict is read (see "A test verdict never depends on
  load").
- Gate commands, against the branch tip:

  ```bash
  cd ~/.worktrees/fabro/<branch>
  export CARGO_TARGET_DIR=/home/ubuntu/.worktrees/fabro/factory-wave-c/target
  cargo +nightly-2026-04-14 fmt --check --all
  cargo +nightly-2026-04-14 clippy --workspace --all-targets -- -D warnings
  timeout 2h cargo nextest run --profile ci -p <crate> -E '<the tests the diff adds or changes>'
  ```

- Launch a long gate DETACHED through this repository's runner, never as an
  agent-harness background task. On 2026-09-12 a harness background task
  running a nextest gate was killed three times during the `fabro-server`
  link with "system is running low on memory", while 52 to 54 GB were free.
  The detached runner survived:

  ```bash
  run_id=$(mise exec -- just gate-start -- /path/to/gate-script.sh)
  mise exec -- just gate-status "$run_id"    # exit 75 while still running
  ```

- The shared `CARGO_TARGET_DIR` above has no host sweep (livespec-dev-tooling
  `dev_host_retention` leaves it out by design). On 2026-11-05 it had grown to
  98 G, writing about 40 G/day while every fork gate ran on vps. After a
  fallback build, cap it under both of cargo's build locks. A `flock` exit of
  75 means another build holds a lock, so delete nothing:

  ```bash
  T=/home/ubuntu/.worktrees/fabro/factory-wave-c/target
  mkdir -p "$T/debug" "$T/release"
  CARGO_TARGET_DIR="$T" flock -n -E 75 "$T/release/.cargo-lock" \
    flock -n -E 75 "$T/debug/.cargo-lock" cargo sweep --maxsize 40GB /data/projects/fabro
  ```

## Merging and the runbook duty

- Merge only when the pull request's Format, Clippy and Test checks are
  green on its head commit. Merge with
  `gh pr merge <n> --rebase -R thewoolleyman/fabro`. The fork
  rebase-merges, so the merge SHA is the LAST commit of the rebased series,
  and the branch SHA does not survive; verify the landing with a content
  check on the carrier branch it merged into, not by branch containment.
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
