# Factory dispatch: preflight checks and failure triage

Operating notes for a session that dispatches work-items to the factory or
triages a dispatch that ended badly. Each entry was first measured by a
session and recorded as a Claude Code auto-memory note; this file is their
durable home (migrated 2026-10-18, plan `block-auto-memory-coverage`). The
dated "measured" line in each entry is the original observation, not a
re-measurement, unless it says otherwise.

## Before every dispatch

### Hand-check the Definition of Done; `filing_display` passing does not mean `dod_gate` will

The factory refuses an item before any run exists unless the description's
FIRST heading is `## Definition of Done`, holding `- ` bullets as the
assertions and one `References: ## <existing spec H2>` line (the dispatcher
has walled on this since v0.158.0, measured 2026-10-01; the parser is
`definition_of_done(description=...)` in
`commands/_dispatcher_definition_of_done.py`). After a run, an item with no
declared proof modes parks at `acceptance` for the human accept valve, with
"absent evidence" per assertion. That is the designed human leg, not a lost
run.

Passing the mechanical parse is not enough. `filing_display` printed
"definition-of-done findings: none" for `bd-ib-wehfpc` and `bd-ib-gj6amh`
(filed 2026-10-14), and the factory `dod_gate` still rejected both, costing a
dispatch slot each. The fleet coordinator counted these Definition-of-Done
rejections as the largest dogfood defect class: 6 of 21 dispatch endings. The
gate grades meaning that the display does not, so read every bullet against
these rules by hand, at filing time AND before each dispatch:

- An assertion whose subject is tests or checks passing is a test-existence
  assertion. It is legal only when the deliverable is itself a test, check or
  gate. Otherwise restate it as the behaviour.
- Any assertion that needs the beads ledger, a host, or a live factory to
  prove (for example "item X carries a valid rank") belongs under
  `### Host-captured` with its `Reason:` line. Sandboxes have no `bd`, no
  tenant password and no route to `127.0.0.1:3307`.
- Name the governing `## Scenario NN` heading in References, not a generic
  heading.
- Read the governing scenario's Given clause, not only the bullet. If it says
  "normally installed releases" or "a real authenticated Codex coordinator in
  Herdr", the bullet is host-captured even when its own words look
  sandbox-testable. `bd-ib-zejlae` (run `01M4YT29J8EK`, 2026-10-15) burned a
  slot this way after passing a hand-check.
- Never assert that a probe, test or check PASSES against a target the
  description says exhibits the failure it detects. That contradicts the
  item's own record and makes completion depend on someone else's fix; assert
  a definite verdict instead. `bd-ib-54q7fn` (run `01M4Z5Y7SF57`, 2026-10-15)
  was refused this way after an earlier run had passed the same text. The
  gate's judgement is not deterministic, so one pass is not evidence that the
  wording is safe.

Filing through the raw `append_work_item` primitive also leaves an item at
`backlog`, where `drive --action impl:<id>` refuses it; route it through
`apply_intake_dor` first (see `.ai/plan-archive-completeness-gate.md` and
`.ai/plan-session-lessons.md`).

### Re-read the registered build immediately before each dispatch

A build check is good only for the dispatch it precedes; releases land several
times a day. Measured 2026-10-16: a session confirmed its build
(`25fee9c3185e`) once at 16:08Z, then dispatched `bd-ib-26deyw` twice more, at
18:05Z and 20:09Z, from that build after the registered install had moved to
v0.203.2 and then v0.203.3 (`e577243f0853`). The dispatcher's stderr said
`plugin build 25fee9c3185e lags latest release` at 19:44Z, and the session read
it as ambient noise.

Immediately before every `drive --action impl:<id>` or
`dispatcher.py dispatch|resume`, read this project's entry in
`~/.claude/plugins/installed_plugins.json`. If it differs from the build your
session's lease is under, update and rebind first
(`.ai/plugin-cache-lease-and-rebind.md`). Treat any `lags latest release`
line in dispatcher stderr as a stop, not a warning; AGENTS.md §"Stop the line
for breakages" governs.

The dispatching session takes these halt-gate reads itself, and a helper never
gates its own dispatch (fleet capacity coordinator
`gitops-fleet-capacity-monitoring`, 2026-10-17). Right before each dispatch,
read `mpstat 5 2` on the factory host while a capacity hold is in force, a
fresh `fabro ps -a --server <factory>` board count, the target repo's master
CI, and the registered build. Record them verbatim, then dispatch or hand a
helper an explicit go. Twice in one day a helper briefed to gate its own
dispatch skipped reads (capacity and CI on `bqoany`; `mpstat` during a hold on
`2v3hxz`).

### Fast-forward the dispatching primary first

Fabro's pre-run precondition pushes the source checkout's branch to origin so
the sandbox base carries its HEAD. When the dispatching primary is BEHIND
origin, that push is refused by the primary's own commit-refuse hook, and the
run dies at 0 ms with `Precondition failed: pre-run push of branch 'master' to
'origin' failed`. Measured 2026-09-30 on `livespec-driver-codex` and
`livespec-driver-pi`, both clean and two commits behind; re-measured
2026-10-14 by the fleet coordinator on build 0.196.10, after the
origin-proven staging change, because staging still pushes the LOCAL
primary's HEAD.

`dispatcher.py reconcile-runs` reports `reconciled: []` for such a 0 ms
failure, so the item is left `active` with a dead run; clear the stranded
claim with `drive --action move:<id>:ready`. Before any
`drive --action impl:<id> --repo <path>`, run `git pull --ff-only origin
master` in that primary (it is clean by discipline) and confirm that HEAD
equals the green `origin/master` SHA immediately before launching.

### A workflow or prompt fix reaches dispatches only through a release

A dispatch submits `implement-work-item` from the PLUGIN PAYLOAD, not from the
`--repo` checkout: the dispatch journal's `workflow_toml` field reads
`/tmp/livespec-orchestrator-beads-fabro-payload-<release>-…/payload/.fabro/workflows/implement-work-item/workflow.toml`.
Only `dispatcher.workflows` entries in `.livespec.jsonc` (for example
`groom-work-item`) resolve from the repo. So a merged change to
`workflow.fabro` or its prompts reaches dispatches only after a release that
contains it AND a session rebind to that build, exactly like a dispatcher
`.py` change.

It also needs a releasable subject. release-please cuts a release only for
`fix:` or `feat:`, so a workflow or prompt fix committed as `chore(workflow):`
merges and never ships until someone else's `fix:` or `feat:` lands.
Measured 2026-10-15: `bd-ib-wqypwm` (PR #3029, `acef2ef3`) sat unreleased
after v0.198.4 for exactly this reason. Use `fix(workflow):` for any workflow
or prompt change that must reach dispatches; the Red-Green hook then takes its
no-Red full-suite path, because no product `.py` is staged. Before claiming a
merged workflow change is live, read a dispatch's `workflow_toml` path and
confirm the release with
`git merge-base --is-ancestor <merge-sha> <cache-build-hash>`.

## Triaging a dispatch that ended badly

### Janitor green, then a `pr`-stage pre-push red: a sibling merged mid-run

The `implement-work-item` workflow runs the janitor BEFORE the `pr` stage's
base refresh, so an integration conflict with a concurrent merge is invisible
until the push. Measured 2026-09-30 on run `01M3R6ACRHVB` (`bd-ib-kc7vzk`):
implement, janitor and review all passed against base `f5529486`; sibling
`bd-ib-xtgwpz` merged as `009b15d0` while the run was in flight; the base
refresh rebased onto it; the sibling's modules called `repository_acp_chains`
without the `catalogs` parameter the run had added; and the sandbox pre-push
hook failed `check-types`, `check-per-file-coverage` and `check-coverage`. The
`pr` stage has no fix loop, so the run parked at needs-human after three hours,
and the `pr` agent misreported it as "the implementation has bugs".

The discriminator is `failure_signature = pr|deterministic|pre-push hook
detected coverage/test failures` while `preferred_label = approve`. Read
`fabro inspect --server <factory> <run>` context values and
`fabro dump --server <factory>` the `pr` stage before believing the run's own
account. The ref "preserved on `refs/heads/needs-human/<run>`" exists only in
the SANDBOX when the push itself failed; check `git ls-remote origin` before
assuming it is on origin. Rework by resolving the item to `ready` with a rider
naming the sibling's call sites, and re-dispatch from current master seeded
from the preserved implement diff.

### A post-merge janitor red names no failing target

The post-merge janitor runs `just check` in a fresh checkout and, on failure,
records a `detail` string truncated to its tail: the generic
``error: Recipe `check` failed with exit code 1`` plus whatever unrelated log
lines preceded it. The last recipe named in that text is merely the last one
to print, not the one that failed. The drive loop then reports
`status: failed` / `Dispatcher did not report green`, and the item stays
`active` with a merged PR, which reads exactly like a real regression on
master and invites a revert or a re-dispatch of good work.

The janitor keeps its checkout (`~/.worktrees/<repo>/janitor-<item-id>`; the
detail says "kept for diagnosis", from
`commands/_dispatcher_janitor_check_venue.py`). Re-run the aggregate there at
the same SHA through the detached runner, which records per-target evidence:
`cd <janitor checkout> && mise exec -- just gate-start -- mise exec -- just check`,
then `just gate-wait <run-id>`. A pass prints `targets completed : N
(failed: 0)`, which marks the red as transient; then run
`dispatcher.py reconcile-merged --repo <repo> --item <id>` to close the item,
and remove the diagnostic worktree. Measured 2026-09-06 on `bd-ib-kpqsk6`
(PR #2210, master `484ecd08`): the janitor went red, the same checkout re-run
passed 80 targets with 0 failed, and the reconcile then printed green.

Two host-only causes have produced such a red:

- **The Codex picker test meets a model-retirement modal.**
  `check-codex-skill-picker` (`tests/e2e-cli/test_codex_skill_picker.py`) is
  skipped in CI and runs only on an authenticated host, so master CI cannot
  catch it. The test writes its own isolated `config.toml` pinning a model
  plus `[tui.model_availability_nux]` and `[notice.model_migrations]`
  suppressors. When that model enters retirement, Codex opens a "retires on
  …; Switch to …" modal, the picker never appears, and the test times out with
  "Timed out waiting for Codex picker state". Measured 2026-09-30 on
  `bd-ib-xtgwpz`; fixed by PR #2499 (`498c3495`), and the template now pins
  `gpt-5.6-sol`. The host's own `~/.codex/config.toml` is the wrong file to
  check. Read the last TUI frame in the assertion, bump the template one
  generation (the model, the nux key and the migration pair), and verify with
  `bash dev-tooling/just-check-codex-skill-picker.sh` (about 60 s).
  `livespec-overseer` carries the same template.
- **A whole-tree scan test reads the primary's gitignored journals.** A test
  that walks `root.rglob("*")` for a forbidden token fails on the primary
  checkout, where gitignored journals (`.beads/interactions.jsonl`,
  `tmp/fabro-dispatch-journal.jsonl`) quote old records, while worktrees and
  CI pass. Seen 2026-09-30 with
  `test_running_release_env_seam_is_absent_from_the_tree`; sibling class
  `bd-ib-z9dz`. When a primary `just check` is red on exactly one tree-scan
  test, run `git check-ignore` on the matched paths and `git grep` on tracked
  files before blaming the change under test, and do not "clean" the journals
  to make it pass.

### Gate-run records: where they live, how to read them, and what they prove

`just gate-start` writes its run directory under the PRIMARY checkout's
`tmp/gate-runs/<run-id>/` regardless of which worktree launched it
(`dev-tooling/gate-run.sh`); the run's `cwd` / `worktree` file names the
launching worktree. Each directory keeps `head`, `command`, `branch`,
`worktree`, `exit_code`, `started_at` and the full `output.log`.

`output.log` contains bytes that make grep treat it as binary, and on this
host `grep` is aliased to `rg`, which then prints nothing, so a failure hunt
reads as "no failures". Use `/usr/bin/grep -a`, or strip ANSI first. Measured
2026-09-30 chasing a `check-per-file-coverage` red, where the wrong directory
and then the binary suppression each read as a clean log.

The directory is also a historical control. Grep every log for a failure
signature and tabulate by `head`: the first run that hit it, and whether an
EARLIER run at the SAME head passed. A same-head pass/fail split means the
cause is host state (credential wrapper, guard, venv, PATH), not a commit;
`stat` the host files for a modification time inside the bracket. Measured
2026-09-12: head `385cf51c` passed `just check` at 05:46Z and failed at 07:27Z
with `/usr/local/bin/bd-guard-emit.py` in the coverage report, because
`with-livespec-env.sh` had been rewritten at 06:21Z to pass the caller's whole
environment (including a venv-first PATH and `COVERAGE_PROCESS_START`)
through the sudo hop. Ledger item `bd-ib-apffmn` carries the write-up.

The CI-wait hooks deny `gh` polling loops and a bare-backgrounded
`gh pr checks --watch`. The sanctioned form is
`just gate-start -- gh run watch <run-id> --exit-status --interval 30`, then a
backgrounded `just gate-wait`.
