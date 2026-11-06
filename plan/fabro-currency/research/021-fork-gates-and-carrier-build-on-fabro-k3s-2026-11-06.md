# 021 — Fork gates and carrier builds move to the `fabro-k3s` ARC scale set (2026-11-06)

Written by `claude:fabro-currency` (Claude Code session 4dfa9268) on 2026-11-06. It closes
work-item `bd-ib-dqxcsh` (Fabro-fork Rust gates and carrier builds run on the ARC k3s runners,
not on the dev host). That item's spec clause is `SPECIFICATION/constraints.md`
§"Fabro runtime constraints", "Fork gate and build venue". The ledger records are the plan
epic `bd-ib-6tcjfx` handoffs at 2026-11-06T00:20:24Z and 01:18:44Z, and this session's closing
handoff. All times are UTC.

## Why it was parked, and what unparked it

The fork had no self-hosted runners. `thewoolleyman/fabro` was not in the
`thewoolleyman-ci-runners` GitHub App installation `146033367`, so the item was parked on
2026-11-05 at 17:59Z (scope event). The maintainer added it at about 22:25Z. The ARC listener
`fabro-k3s-66ccd4c4-listener` registered at 22:48Z (plan `dev-host-test-gate-load`). The scale
set's `minRunners` is 0, so an idle scale set lists no runners. The listener is its health
signal.

## What landed

| Fork PR | Into | Merge | What |
| --- | --- | --- | --- |
| #27 | `carrier-candidate-registered-20261023` | `0d5ce5f60` | `fork-gates.yml` (Format, Clippy, Test on `fabro-k3s`) and `carrier-build.yml` |
| #28 | `factory-integration` | `161890e36` | the same commits, on the fork's default branch, which `workflow_dispatch` needs |
| #29 | `factory-integration` | `8b82e99bb` | `carrier-build.yml`: system `safe.directory` before the first git read; the job's steps run under bash |
| #30 | `carrier-candidate-registered-20261023` | `711a96404` | the same two fixes on the carrier |

The guidance is orchestrator PR #4507 (`9d383285`). It rewrote `.ai/fabro-fork-hand-build.md`
so that `fabro-k3s` is the merge gate and the carrier build venue, the dev-host throttle is a
recorded fallback only, and "The merge gate is local" and the Target-cache retention section are
retired. The shared vps target's `debug/` was already empty (4.0K) at the retirement.

## Three container defects the first runs found

Every one of these passed on a GitHub-hosted runner and failed only in the ARC
kubernetes-container-mode pod. That pod runs as root in a user namespace with no reaper and a
`sh` default shell.

1. **Git refuses the checkout** with `detected dubious ownership`, because the files keep the
   runner's ownership. fork-gates runs 42124630229 and 42128065950 hit it, and so did the first
   carrier build, 42143474207, which failed after 19 s. The fix is
   `git config --system --add safe.directory "$GITHUB_WORKSPACE"`. It must be SYSTEM scope:
   the `fabro-cli` test harness calls `env_clear()` and sets a temporary `HOME`, so a
   `--global` entry is never read.
2. **The Petri crash scenarios hang.** They poll `process_running`, which counts a zombie as
   running, and nothing in the container reaps it (run 42130472837). The fix is to run nextest
   under `tini -s`.
3. **`${sha:0:12}` exits 2** under the container's default `sh -e` (dash). Validation build
   42145878202 hit it. The fix is `defaults.run.shell: bash` on the carrier-build job.

## Proof

All three are host-captured assertions of `bd-ib-dqxcsh`.

- **Gates on the carrier run on ARC.** The push run 42135969934 on the carrier at `0d5ce5f60`
  passed Format, Clippy and Test. They ran on pods `fabro-k3s-4pn2q-runner-m6g6n`, `-k9nl8` and
  `-fsn2g`, each labelled `fabro-k3s`. Fork PRs #28, #29 and #30 showed the three checks in their
  status rollups.
- **A carrier build is produced on ARC from a named ref.** Run 42149380640 ran on pod
  `fabro-k3s-4pn2q-runner-wfckk` from 02:31:41Z to 02:55:39Z. It was dispatched from the fix
  branch before #29 merged, with `ref=carrier-candidate-registered-20261023`, and it published
  the artifact `fabro-engine-0d5ce5f605eb` (61.5 MB, kept until 2027-02-04). The artifact's
  `BUILD_INFO` reads
  `source=thewoolleyman/fabro ref=carrier-candidate-registered-20261023 commit=0d5ce5f605eb70140eae2da034997609b2d2813e`.
  Its `VERSION` is `fabro 0.393.0-nightly.1 (0d5ce5f 2026-11-06)`, and its
  `fabro` sha256 `11ff437d0955fcc06c5fe80db2d9618ab3b924e7b4bab9051ada2626891da7d6`
  matched `SHA256SUMS` after `gh run download` on vps, with no build there.
- **No fork cargo or rustc runs on the dev host.** Detached samplers took
  `pgrep -x -c 'cargo|rustc|clippy-driver|cargo-nextest'` once a minute on vmi3006760. On
  2026-11-05 they took 87 samples across the PR #27 runs. On 2026-11-06 they took 50 across the
  failed build and the #28/#29 gates, and 39 from 02:17:54Z to 02:56:02Z, covering all of
  build 42149380640. Every sample read 0.

## What it changes for the parked fork items

`bd-ib-oeckki`, `bd-ib-aqcgxz`, `bd-ib-4uge7u`, `bd-ib-adrhkf` and `bd-ib-sltfyg` were parked
behind this item, because their gates could not run on vps. They can now be fork PRs against
the carrier, gated by fork-gates on `fabro-k3s`, with the RED evidence taken by pushing the
test-only commit first.
