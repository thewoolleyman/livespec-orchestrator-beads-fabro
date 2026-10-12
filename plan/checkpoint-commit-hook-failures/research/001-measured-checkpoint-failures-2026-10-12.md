## The maintainer's statement of what done means

"The HP Fabro factory is very overloaded. But what's even worse is that most of the recent runs are failing. There have only been a couple of successes." ... "For 2 and 3, ensure that work items are created to cover all aspects, and that the work items are all assigned to an appropriate existing/new plan"

## Definition of Done assertions derived from that statement

- A factory run's engine checkpoint commits do not run the governed repository's commit hooks, so a run continues to its next node when its tree would fail the pre-commit aggregate.
- A commit made inside a factory sandbox is not refused because master CI is red, queued or running.
- A run that still ends on a failed engine checkpoint commit leaves its item blocked with a reason naming the node and the failed hook targets, with its tree preserved.
- Over the seven days after the fixes are released, no hp run in the fleet ends with a git checkpoint commit failure or a checkpoint budget expiry.

# Engine checkpoint commits killed by repository hooks — measured 2026-10-12

Measured 2026-10-12 by session factory-failure-mitigation (project livespec-orchestrator-beads-fabro) from the dispatch journals of every repo dispatching to hp since 2026-10-08 (301 distinct runs: 72 green, 114 blocked at needs_human, 57 failed, 12 post-merge janitor red, 6 watchdog-cancelled), the hp fabro-server journal since 2026-10-09 (213 runs), per-run `fabro events` and `fabro inspect` reads against https://hp-xubuntu.perch-rudd.ts.net:32276, and this tenant's full ledger. hp was at load 25 to 38 on 16 cores with 14 of 15 scheduler slots busy; sandbox janitor (`just check`) duration rose from a 3.4 min median on 2026-10-05 to 6.5 min (max 21 min) on 2026-10-12.

## Finding

27 hp runs since 2026-10-09 ended with `git checkpoint commit failed for node <n>: git commit
failed (exit 1)`, a 900 s checkpoint commit timeout, or a checkpoint budget expiry. The
`checkpoint.failed` event in each run's `fabro events` stream carries the lefthook stderr
tail; reading all 27 gives:

| Failing hook target(s) | Runs |
|---|---|
| check-per-file-coverage and/or check-coverage (unfinished tree at node end) | 15 |
| check-master-ci-green (alone in 2, with coverage in 3) | 5 |
| commit-msg 01-red-green-replay | 2 |
| commit timed out after 900 s | 4 |
| lint, types, lloc, no-subprocess-spawn, heading-coverage register (with or without coverage) | 5 |
| git add failed | 1 |

(Rows overlap where a run listed several targets.) Example: run 01M4PEXR2PY808VPN0807FTF5Y
passed every target except `check-master-ci-green` in an 88 s
`03-check-pre-commit`, and the run died.

Mechanism. `.claude-plugin/.fabro/workflows/implement-work-item/workflow.toml` sets
`[run.checkpoint] skip_git_hooks = false` and `commit_timeout = "15m"`. The deployed engine
(fabro 0.254.0 8869e88, `lib/crates/fabro-workflow/src/sandbox_git.rs`) adds `--no-verify` to
the run-branch checkpoint commit only when `skip_git_hooks` is true. So every node's
checkpoint of whatever the agent left uncommitted runs `just check-pre-commit` (the full
aggregate minus a skip list) and the commit-msg Red-Green-Replay gate. A refusal is an engine
error, not a stage failure, so the graph cannot route it: the run ends `workflow_error`,
the dispatcher outcome carries only `git commit failed (exit 1)`, and the item is
re-dispatched from scratch (bd-ib-z46mth hit this four times).

The comment above that table records why hooks were kept on (the content-trigger
red-green-replay gate passes empty machine commits). That reasoning predates the measured
cost: the janitor node already runs the declared check suite after implement, and
publish_draft's pre-push runs the aggregate again, so a hook-gated checkpoint adds a third
full run and converts an unfinished tree, which janitor's fix loop would repair, into run
death. `commit_timeout` is also billed three times into the Dispatcher's credential-lifetime
floor (`_dispatcher_credential_requirement.py`), so a hook-free checkpoint lets it shrink.

`check-master-ci-green` is environmental: master CI re-queues on every merge, and with many
sessions merging per hour it is often running. It reaches sandbox commits through
`dev-tooling/just-check-pre-commit.sh`, which does not skip it, for the agent's own Red and
Green commits as well as the engine checkpoint.

Prior art read: bd-ib-qhv7qs (ready, no parent; the Red-open fix-stage timeout case,
adopted into this plan), bd-ib-wcuauj.2 (backlog, plan runaway-process-containment; H2
investigation whose hypothesis b, hooks inside the checkpoint commit, this measurement
confirms), closed bd-ib-6ka (30 s budget), closed bd-ib-jm4efv (budget misclassified),
bd-ib-g5hp (pyright on the Red commit). None proposes skipping hooks or removing
check-master-ci-green from sandbox pre-commit.