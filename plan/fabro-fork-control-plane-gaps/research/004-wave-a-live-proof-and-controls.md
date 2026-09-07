# 004 — Wave A live proof on vps: what each fix measured, the controls that made the zeros real, and two instruments that were wrong first

Research note for plan thread `fabro-fork-control-plane-gaps` (epic
`bd-ib-bb41`), 2026-09-06, the session that merged Wave A. Everything here
was measured on `fabro 0.254.0 (9081419 2026-09-06)`, built from
`thewoolleyman/fabro` `factory-integration` at `908141966` after fork PR #4
rebase-merged, pinned on **vps** only. Status is read from the ledger, never
from this file. Labels **measured** / **inferred** as in 001.

## 1. The build and where it runs

| Fact | Value | Instrument |
|---|---|---|
| Carrier tip | `908141966` (PR #4, four commits rebase-merged) | `git log origin/factory-integration` |
| All five fix tokens on the tip | `init:`, `diff --cached --quiet`, `CheckpointBudgetExceeded`, `ACP_TIMEOUT_NO_OUTPUT_MARKER`, `FABRO_RUN_ID` each ≥1 hit | `git grep -c <token> origin/factory-integration -- <site>` |
| vps binary | `fabro 0.254.0 (9081419 2026-09-06)`; running inode == file inode | `~/.fabro/bin/fabro --version`; `stat -Lc %i /proc/$PID/exe` |
| Rollback artifact | `~/.fabro/bin/fabro.8de6611-pre-wave-a.bak` | `ls ~/.fabro/bin` |
| Orchestrator image | `livespec-orchestrator:dev` reports `9081419`; tier-1 all pass | `build-and-verify.sh`; `docker run --entrypoint fabro … --version` |
| hp binary | still `8de6611 2026-08-16`; the new binary is staged as `fabro.new` (sha256 matches vps) | `ssh root@hp … fabro --version`, `sha256sum` |

A fresh fork worktree needs `bun install --frozen-lockfile` before
`cargo dev build --release -p fabro-cli`, or the SPA embed dies on
`Could not resolve: "react"`. Recorded in the runbook by PR #2206.

## 2. The full dispatch cycle (the proof that nothing regressed)

Run `01M1VG40W09G`, item `bd-ib-e2fi6i`, dispatched through the Dispatcher
to `--factory vps`: all seven stages green (start, implement,
implementation_diff, janitor, review, pr, exit), 34m24s, PR #2226 merged,
post-merge janitor green, item closed by the dispatcher. That is one complete
implement-work-item cycle with all five fixes live. An earlier attempt
(`01M1V4HKWKPZFWMKPYKS536CAY`, 10:35Z) never ran an agent turn because the
Claude org monthly spend limit was hit fleet-wide between roughly 10:35Z and
13:30Z; it still produced evidence (§3.1, §3.4) and is the "agent changed
nothing" control for `.5`.

## 3. Per-fix measurements

### 3.1 `bd-ib-bb41.2` — sandbox PID 1 reaps orphans — ACCEPTED

**Measured, same instrument as the 559 figure** (defunct processes counted
inside one running implement container): during run `01M1VG40W09G`, container
`ed9f5943e5fe`, PID 1 is `docker-init` (read from `/proc/1/comm`),
`HostConfig.Init=true`; 69 samples at 30s intervals across the whole run,
**max defunct 0**, mean 0.0, peak 43 processes. Against 559 on the old build.

**Why the zero is real.** The counting query
(`grep -h '^State:' /proc/[0-9]*/status | grep -c 'Z (zombie)'`) was run in
a container started *without* init after creating 3 zombies: it returned 3.
An instrument that can return a hit reported none.

**The mechanism A/B, including the arm that was wrong first.** The first
matched-arm test created zombies under a still-live parent and ran it with and
without `--init`: **both arms returned 3**, which reads as "the fix does
nothing". It is the test that is wrong: a zombie whose parent is alive belongs
to that parent, and no PID 1 can reap it. The correct test orphans the
children (a middle process forks three, exits; the three exit; they reparent to
PID 1): a PID 1 that never calls `wait()` → 3 zombies; `docker-init` → 0.
Recorded so nobody re-derives the wrong arm and files a false regression.

### 3.2 `bd-ib-bb41.5` — no empty checkpoints — ACCEPTED

Three measurements, one per criterion:

- **Empty tree is skipped and recorded distinctly.** Run `01M1VG40W09G` emitted
  FIVE `run.notice` `checkpoint_empty` events (implement, implementation_diff,
  janitor, review, pr), each naming the unchanged HEAD, and ZERO `git.commit`
  events — while making real changes (5 files, +340/−18) that published to
  PR #2226. On the old build those five nodes each wrote an `--allow-empty`
  commit on top of the agent's work.
- **A run whose agent changes nothing produces zero ordinary checkpoint
  commits.** Run `01M1V4HKWKPZFWMKPYKS536CAY`: `final_git_commit_sha` equals the
  base, `diff_summary` 0/0/0, two `checkpoint_empty` notices, no `git.commit`.
- **A run with real staged changes still checkpoints.** Probe `WaveAProbeS`
  (`01M1VNZN8AY7ZJG9S9M5F8AHGP`, a two-script-node workflow on a docker clone
  of this repo): the script left an uncommitted file; the ENGINE checkpoint
  emitted `git.commit` `5c8f7954ec42` (no `--allow-empty`); the next node
  changed nothing and got `checkpoint_empty` naming that same HEAD.

**The structural finding, which is why the third measurement needed a probe.**
In `implement-work-item` the *agent* commits its own work under the
Red-Green-Replay ritual, so by the time the engine checkpoint runs the tree is
already clean and `git add -A` stages nothing. The engine checkpoint is
therefore always empty in this workflow: the `--allow-empty` removal changes
behaviour on every node of every dispatch (a wider blast radius than
"occasionally an empty run"), and no dispatch through this workflow can
exercise the staged-changes path. A session reading only dispatch evidence
would conclude the path is untested; it is not, but it needs a workflow whose
script node leaves changes for the engine. Note also that the new `committed`
flag is not surfaced on `checkpoint.completed` properties (reads `None`); the
operator-visible discrimination is the `checkpoint_empty` notice.

### 3.3 `bd-ib-jm4efv` — typed checkpoint budget — ACCEPTED

Probe `WaveAProbeT` (`01M1VNZNRX31A6FD7FY9STWD96`): a script node installed a
`pre-commit` hook that sleeps 40s and left a staged change, with
`[run.checkpoint] commit_timeout = "5s"`. Events: `checkpoint.failed`
"git commit timed out after 5003ms", then `run.failed` with
`Checkpoint error: checkpoint operation budget exceeded on node "slow_hook": git commit timed out after 5003ms`
and **category `deterministic`**. On the old build the same message classified
`transient_infra` on its "timed out" substring and was retried as if the
network had blinked. The item carries no `acceptance_criteria` field; its title
is what was tested.

### 3.4 `bd-ib-bb41.1` — run-scoped needs-human refs, both halves — ACCEPTED

- **Run-scoped ref, live.** `01M1V4HKWKPZFWMKPYKS536CAY` preserved on
  `refs/heads/needs-human/01M1V4HKWKPZFWMKPYKS536CAY` (`LIVESPEC_NEEDS_HUMAN_PRESERVED`).
- **Two consecutive runs, two distinct refs, both resolvable.** Probe
  `WaveAProbeS` ran the exact preservation script from `workflow.fabro` (exit 0)
  and pushed `refs/heads/needs-human/01M1VNZN8AY7ZJG9S9M5F8AHGP` →
  `5c8f7954ec42`; `git ls-remote` showed both at the time. The probe ref is
  deleted once this note lands; the real one stays.
- **CORRECTED 2026-09-07 — an `unknown-run` ref DOES exist on this repo's
  origin, and the negative control cited below was the wrong run.** The
  sentence this bullet replaces claimed "no `unknown-run` ref exists" and
  attributed the loud-failure control to hp run `01M1V4T2ZXC2`. Both halves
  were wrong, and each was wrong in the reassuring direction.
  - The ref exists. Measured 2026-09-07 with
    `git ls-remote origin 'refs/heads/needs-human/*'` against this repo:
    `refs/heads/needs-human/unknown-run` resolves to `0194fd98`, whose commit
    subject is `fabro(01M1VP54H84KW396YJJJWVHV2T): implement (failed)`, dated
    `2026-09-06 15:49:01 +0000` — about an hour after the note's original
    claim. It is left in place as evidence.
  - The mechanism is a stale plugin cache, not a stale fabro build. A dispatch
    driven through a plugin cache older than the `0.133.1` release still
    renders the placeholder-carrying preservation script, so it can push
    `unknown-run` no matter which fabro binary the factory runs. That is why
    the ref appeared on a day when both the workflow fix and the fork fix were
    already live.
  - hp run `01M1V4T2ZXC2` is not this repo's negative control: it was a
    `livespec-overseer` run, so it cannot evidence a claim about this repo's
    refs. The loud-failure behaviour it showed is real and is still the reason
    the hp re-pin matters — until hp carries `9081419`, every needs-human
    preservation there fails to push — but it is a separate observation, not
    the control for criterion 3.
  - **What criterion 3 actually rests on** is the fork-side change plus its
    unit coverage, and the absence of any NEW `unknown-run` push from a
    current-cache dispatch. It is not evidenced by a global claim that no such
    ref exists anywhere, which is falsifiable by any stale cache in the fleet
    and was in fact falsified within the hour.

### 3.5 `bd-ib-bb41.3` — `AgentAcpTimedOut` progress evidence — ACCEPTED

Two probe runs, one per arm of criterion 2, both on the new build. The
`AgentAcpTimedOut` event now carries `stdout` (agent text tail or the explicit
marker), `tool_call_count`, `update_count` and `last_activity_ms`, and the
failure message summarises the counters.

| Arm | Run | `stdout` | `tool_call_count` | `update_count` | `last_activity_ms` | Failure message |
|---|---|---|---|---|---|---|
| Slow but working: Claude adapter told to run six sequential 25s sleeps under a 120s ceiling | `01M1VP8SZD0VAW2NMZHF26JE85` | the agent's narrated tail ("… Third sleep completed with exit code 0. Running the fourth sleep command.") | 10 | 93 | 106717 | `ACP turn timed out after 10 tool call(s) and 93 session update(s); last update at 106717ms` |
| Genuinely silent: `acp.command="sh -c 'sleep 600'"`, 90s ceiling | `01M1VP2YEY94DJEWAZ3F5D4SC1` | `output not captured: no agent message text before the timeout` | 0 | 0 | `null` | `ACP turn timed out after 0 tool call(s) and 0 session update(s); no updates received` |

A working-but-slow node and a dead node are distinguishable from the event
alone; `update_count == 0` is the zero-activity discriminator. Two things a
successor needs: a raw `fabro run` of an ACP node against this repo must carry
the workflow's `mise trust && mise install` prepare step (the sandbox's `npx`
is mise-provided; the first probe attempt died on the untrusted `.mise.toml`
before its turn), and the `CLAUDE_CODE_OAUTH_TOKEN` must be rendered into an
uncommitted `[environments.<id>.env]` block the way the Dispatcher's overlay
does. Criterion 3 (disposition of `bd-ib-b5dg`) belongs to plan
`acp-implement-zero-output-hang` per deferrals D4/D7. **ACCEPTED.**

## 4. Instruments and traps met this session

- **`grep -c` exits 1 on zero matches.** The sampler's `|| echo NA` fallback
  fired on every zero reading, so its own `samples`/`max` counters stayed at 0
  while the per-sample lines carried the truth. Compute from the per-line
  series, or drop the fallback. Recorded because a zero-heavy series is exactly
  where it bites.
- **`No running processes found` contains `running`.** A bare
  `grep -q running` on `fabro ps` output aborts an idle-gated restart on an idle
  factory. Match run rows: `^ ?01[A-Z0-9]{10,}.*running`. Now in the runbook.
- **The wrong-parent A/B** (§3.1). A control that returns the same answer in
  both arms has not isolated the mechanism; ask what would differ if the fix
  worked before reading the result.
- **A negative existence claim about refs is falsifiable by anyone else's
  stale cache.** §3.4 asserted "no `unknown-run` ref exists" from one
  `git ls-remote` reading. The reading was correct when taken and false about
  an hour later, because a dispatch through an older plugin cache pushed one.
  A claim of the form "this ref does not exist" is a claim about every writer
  to the remote, not about the build under test; scope it to what the fix
  controls, and timestamp the reading.
- **A four-second docker run is not a local run.** Probe S/T finished in 4s
  and 6s, which looked like they had executed in the primary checkout; the
  dumps show `provider: docker`, a cached image and a fast clone. Check the
  `sandbox.initialized` event before assuming host contamination — but check
  the host too (it was clean).

## 5. What is still open after this note

- hp re-pin: binary staged as `/home/cwoolley/.fabro/bin/fabro.new`; a
  zero-live-run watcher swaps it and restarts the unit at the first instant hp
  has no live run (other repos' dispatchers keep it busy).
- Wave B (`.4`, `.6`, `bd-ib-js4t57`, `bd-ib-i523` after `.5`) per 003 §"Effect
  on the proposed waves".
- `next` ranks `bd-ib-i523` as a dispatch candidate despite its
  `factory-ineligible` label (observed 2026-09-06); not this plan's defect.
