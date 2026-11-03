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
- Share the build cache: `CARGO_TARGET_DIR=/home/ubuntu/.worktrees/fabro/factory-wave-c/target`.
  A cold workspace build of the fork is a from-scratch Rust dependency compile
  on a box that runs many concurrent sessions; the shared target directory is
  what makes the gates incremental. The directory can be EMPTY: on
  2026-11-02 no fork target directory existed on vps, so the first gate was
  a cold build anyway. Do not plan an ETA around a warm cache without
  `ls`-ing it first.
- Run `uptime` BEFORE any build or test run, every time, and bound the
  compile (`CARGO_BUILD_JOBS`, `nice`, `--test-threads`) when the load is
  already high. The load on 2026-09-12 was 25 to 30 on 18 cores from other
  sessions' cargo and pytest runs. The coordinator's standing throttle for a
  fork gate on vps (ruling 2026-11-02): `nice -n 19`, `CARGO_BUILD_JOBS=4`,
  nextest limited to `-p` the touched crates with a low `--test-threads`. At
  nice 19 the gate takes only the cycles the other sessions leave idle, so it
  pauses only when `mpstat 5 1` reports idle below 8%. There is no cluster
  venue for a fork build: `rust.yml` runs only for `main`, and an ad hoc
  host build on gmktec is not sanctioned. The throttle protects the shared
  box. It is never a reason to read a test verdict differently: see "A test
  verdict never depends on load" below.

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

## The merge gate is local

The fork's GitHub workflows run only on `main` (`rust.yml`,
`typescript.yml`: `branches: [main]`), so a pull request against
any carrier branch shows NO checks and `gh pr view` reports an empty
status rollup. That is not a green signal; it is the absence of an
instrument. The merge gate is therefore run locally against the branch tip,
and it is TARGETED (maintainer ruling 2026-11-03):

```bash
cd ~/.worktrees/fabro/<branch>
export CARGO_TARGET_DIR=/home/ubuntu/.worktrees/fabro/factory-wave-c/target
cargo +nightly-2026-04-14 fmt --check --all
cargo +nightly-2026-04-14 clippy --workspace --all-targets -- -D warnings
# RED: the change's own tests, with the fix reverted, must fail.
# GREEN: the same tests, with the fix, must pass.
cargo nextest run --profile ci -p <crate> -E '<the tests the diff adds or changes>'
```

Do NOT run the whole crate or workspace test suite for a narrow diff. The
RED/GREEN run of the change's own tests is the evidence. On 2026-11-03,
full `fabro-petri` runs on two one-function diffs (`bd-ib-6r3yax`,
`bd-ib-bpucez`) cost about an hour each on a loaded host and surfaced only
pre-existing test defects. Widen the selection only when the diff reaches
across modules or changes a shared interface, and then select the dependent
tests, not the crate.

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

Work independent fork items in PARALLEL, each in its own worktree on the
carrier branch, and fold their merges into one engine build. Do not queue
them one at a time.

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
