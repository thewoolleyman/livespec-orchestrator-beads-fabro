## The maintainer's statement of what done means

The cleanup job only does cleanup, no LLM spend, and it runs as intended. The drift check should be split out to its own separate job, but then it also needs to be improved so it doesn't waste tokens. It needs to be stopped after the split-out.

## Definition of Done assertions derived from that statement

- Each 10-minute reconcile-runs cleanup pass reconciles only factory runs and work-item claims and invokes no LLM.
- The reconcile-runs cleanup timer is enabled and running on the host every 10 minutes.
- The spec-drift check runs as its own separate job, not from the reconcile-runs cleanup pass, and the specification no longer binds the drift pass to every reconcile pass.
- The drift job judges each default-branch merge at most once per ratified spec revision, so a stalled frontier does not re-judge the same merges.
- The drift judge, and every caller of it including the pre-dispatch governing-heading check, uses no hard-coded Claude model and follows the configured Codex-first model routing.
- A drift judge call does not resend the entire spec tree for every merge.
- The drift job stays stopped after the split and is scheduled only once assertions 4 to 6 hold and the maintainer turns it on.

# 001 - Spend incident and the split of the drift check from the cleanup timer

Recorded 2026-10-25T16:18:15Z by spec-implementation-lockstep (session eed499b0), at the maintainer's direction.

## Maintainer's Definition of Done, verbatim

> The cleanup job only does cleanup, no LLM spend, and it runs as intended. The drift check should be split out to its own separate job, but then it also needs to be improved so it doesn't waste tokens. It needs to be stopped after the split-out.

## Derived assertions (confirmed by the maintainer, attended creation)

1. Each 10-minute reconcile-runs cleanup pass reconciles only factory runs and work-item claims and invokes no LLM.
2. The reconcile-runs cleanup timer is enabled and running on the host every 10 minutes.
3. The spec-drift check runs as its own separate job, not from the reconcile-runs cleanup pass, and the specification no longer binds the drift pass to every reconcile pass.
4. The drift job judges each default-branch merge at most once per ratified spec revision, so a stalled frontier does not re-judge the same merges.
5. The drift judge, and every caller of it including the pre-dispatch governing-heading check, uses no hard-coded Claude model and follows the configured Codex-first model routing.
6. A drift judge call does not resend the entire spec tree for every merge.
7. The drift job stays stopped after the split and is scheduled only once assertions 4 to 6 hold and the maintainer turns it on.

## What happened (measured 2026-10-25)

- The coordinator gitops-fleet-capacity-monitoring, relaying token-spend-analysis, measured about $135 of
  about $194 local Anthropic spend between 15:37:35Z and 16:02Z as 50 one-shot `claude -p --model
  claude-opus-4-8` calls, about $4.30 each, because each call writes a fresh ~425k-token spec-tree prompt.
- The caller is the DRIFT lane of the root `reconcile-runs.timer` (`/etc/systemd/system/reconcile-runs.*`,
  installed from `orchestrator-image/`, committed b3ee5c9ba on 2026-08-30). The service runs
  `dispatcher.py reconcile-runs` from the orchestrator primary checkout every 10 minutes
  (`OnUnitActiveSec=10min`, `OnBootSec=5min`).
- Since 357919fd7 (2026-10-22, "run the drift pass from every reconcile pass"),
  `_dispatcher_reconcile_runs_command._run_drift_lane_if_live` runs `run_drift_lane` on every non-dry
  pass, with `drift_judge` from `_drift_run_judge.py`, where `DEFAULT_DRIFT_JUDGE_MODEL = "claude-opus-4-8"`.
  The binding comes from SPECIFICATION/contracts.md: each reconcile pass MUST enumerate every
  default-branch merge after the recorded frontier and MUST run the drift pass over each merge's diff.
- The drift frontier on the detection-coverage anchor bd-ib-j5fzyo has been stuck at 303bc8f6 since
  the last completed record at 2026-10-24T04:58:29Z. Twelve `livespec-drift-held-finding` records
  (2026-10-24T13:45Z to 2026-10-25T10:39Z) await human disposition, and a held finding withholds the
  completed record. So every pass re-judges all 76 first-parent merges after the frontier.
- While every Claude account was exhausted (about 11:18Z to 15:37Z) those calls failed cheaply. When
  caam selected anthropic-6 at 15:37:29Z they began to bill. Each pass then ran the full 10 minutes.
- The pre-dispatch governing-heading judge (`_dod_governing_heading_judge.py`) calls the same
  `drift_judge`, so each dispatch also pays one hard-coded Opus full-tree call.

## Containment already taken

- About 16:05Z: `sudo systemctl stop reconcile-runs.timer` and `stop reconcile-runs.service`, and the
  in-flight judge child was killed.
- About 16:15Z, at the maintainer's direction: `sudo systemctl disable reconcile-runs.timer`, so a
  reboot does not re-arm it. The RUNS lane (stranded-run completion, claim release) is down with it
  until assertion 1 lands and the timer is re-enabled.

## Why the split, in the maintainer's framing

The runs lane is deterministic inventory reconciliation and needs no model. The drift check is an
unrelated judgement that was attached to the cleanup clock only because the spec bound it to every
reconcile pass. The fix is to separate the jobs, restart cleanup at once with no LLM, and keep the drift
job stopped until it is cheap: one judgement per merge per spec revision, Codex-first routing instead
of a hard-coded Claude model, and no full spec-tree resend per merge.

## Open for the next session

- File the spec change (unbind the drift pass from the reconcile pass) through propose-change and revise.
- File and factory-dispatch the cleanup-only change first, so the timer can be re-enabled quickly.
- File the drift-job improvements (verdict reuse, model routing, prompt size) and the separate unit.
- Do NOT run any drift judgement on Claude meanwhile; the maintainer directed minimal Anthropic spend.
