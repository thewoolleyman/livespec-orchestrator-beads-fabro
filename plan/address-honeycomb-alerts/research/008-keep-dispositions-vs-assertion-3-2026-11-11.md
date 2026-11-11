# 008 — "Keep" dispositions cannot satisfy assertion 3 (2026-11-11)

Session c9fdad3c (unattended overseer resume), about 01:00–02:30Z on 2026-11-11.
Everything below was read only. No trigger, host, or ledger record was changed.

## Why this note exists

Plan assertion 3 says: over a trailing 72-hour window under normal factory
load, no dispositioned alert group sends a Triggered email. Research note 002
gave two baseline groups the disposition "real condition; keep" with no
carrier: Delegated gate no-verdict (`xMggkF8364A`), and token-spend source
quiet (factory spend emitter, factory Codex spans). Neither of them can ever
reach a quiet 72 hours unless something changes. A "keep" row closes no item,
so nothing makes the condition stop.

## Triggered emails in the trailing window (Gmail, read-only)

Search: `from:noreply@honeycomb.io newer_than:4d`, Trash included, through the
claude.ai Gmail connector. Triggered messages since 2026-11-08T02:00Z:

| Group (trigger) | Triggered at (UTC) | In baseline? | Owner today |
|---|---|---|---|
| Delegated gate no-verdict (`xMggkF8364A`) | 11-09 18:53; 11-11 00:33 (each thread holds several more) | yes, "keep" | **none** |
| token-spend quiet: factory Codex spans (`9uozGZd73Qu`) | 11-09 01:49 | yes, "keep" | none; expected Codex headroom floor-skip (handoff 23) |
| post-hoc Red share (`EQMwDT61A6s`) | 11-10 09:59 | yes, cause fix | `bd-ib-z2y4ca` (open) |
| CI warm cache stale (`vnW13mLVzen`) | 11-08 12:39 | yes, cause fix | `livespec-dev-tooling-243dzr` (open) |
| CI sccache hit floor (`HfK9RB9tZYp`) | 11-08 05:40 | added 11-06 | `livespec-dev-tooling-m5m2dl` (open) |
| k8s factory OOMKilled/CrashLoop (`FWE8Bw962Pj`) | 11-08 00:25; 11-09 05:05 | added 11-09 | `bd-ib-3kdjct`, **closed 2026-11-10T21:56Z** |
| k8s controllers zero available replicas | 11-09 08:46 (resolved 08:51) | **no** | none |
| bd-guard raw non-conformant bd op | 11-09 05:48 (resolved 06:03) | **no** | none |
| token-spend quiet: caam reads (`9PRVAXHJoeJ`) | 11-10 17:51 | **no** | none |
| token-spend quiet: local Claude/Codex emitter (`mdBC2K19hfG`) | 11-10 19:17 | **no** | none |
| token-spend quiet: local account attribution (`k2wXDHgSjRA`) | 11-10 19:18 | **no** | none |

Cause-fix groups whose carriers are still open are expected to keep firing
until those carriers land, so they are not the problem this note records.

## Delegated gate no-verdict: measured

Honeycomb livespec/`livespec-delegated-gate`, 7 days (queries `dTZZSKEa59G`,
`zLoHpXy5qNT`): 999 passed, 50 failed-tree, 12 no-verdict. None of the 12
no-verdict spans carries `livespec.gate.job_name`.

- 2026-11-05 06:08–06:29Z: 4 spans with no repository. This is the
  assembly-failure path in `gate_remote_delegate.run_delegated_gate`, which
  stops before a Job exists.
- 2026-11-07T17:14Z (orchestrator, tree `6afbbd67`, a Fabro review_fix
  commit). Gate run `20261107T170438Z-2028504`: "await-gate-terminal did not
  complete … No such file or directory:
  '/home/ubuntu/.worktrees/livespec-orchestrator-beads-fabro/triage/72hvx5-seed'".
  The pushing session's worktree was removed while the gate was waiting.
- 2026-11-11T00:29Z (livespec-dev-tooling, tree `5b6764d0`). Gate run
  `20261111T002432Z-2338868`: "waiting for gate Job
  gate-livespec-dev-tooling-d4n26 was terminated by SIGTERM; the client
  deleted that Job". The waiting client was killed. A Job did exist, yet the
  span has no `job_name`, so an absent job_name does not prove that no Job
  was submitted.
- 2026-11-09T18:52Z (tree `a8384abd`, commit fdccf17a), 11-10 13:01Z
  (`8f314443`), 11-10 20:05, 20:20 and 20:44Z (the same tree `c938f86e`,
  commit 9eb16b1f with a -03:00 committer offset), and 11-11 00:35Z
  (`1eeb3fd3`, commit edfb7cfe): orchestrator pushes with NO run directory
  under the primary checkout's `tmp/gate-runs/`. Those were plain pre-push
  hook runs, and their refusal text went only to the pushing terminal. Their
  cause is **not recoverable from this host**.

Reading: at least two of the eight attributable no-verdicts were caused by the
pushing client itself (a worktree deleted mid-wait, a SIGTERM), not by the
delegation. The outcome vocabulary is fixed at three values by
livespec-dev-tooling `SPECIFICATION/contracts.md`, so the emitter cannot
separate "client interrupted" from "delegation broken" without a spec change.
No open livespec-dev-tooling item names this. The item that created the
signal, `livespec-dev-tooling-cmgqnz`, is closed.

## Local token-spend sources quiet on 2026-11-10: measured

`token-spend-fast.service` (user unit on this host, which has had no reboot
since 2026-10-27) ran every hour. From the 16:07Z run through the 19:07Z run
it reported `sent 0 caam reads`, and local Claude events fell from about 1,000
per run to 13, 20, then 0. The 20:07Z run recovered fully: 981 local Claude
events and 7 caam reads. caam reads come from
`~/.local/state/caam-usage-rotate/state.json`, so the caam rotation loop
stopped writing for about 3 hours at the same moment the local sessions went
quiet. The three triggers reported a true condition. Separately, the 19:07Z
run crashed with `KeyError: 'session.id'` in `accounts.local_sessions`.
token-spend-report commit `4d333bf` (20:11Z) fixed that crash; it was not the
cause of the gap.

## Consequence for the plan

1. The two "keep" rows in note 002 must be re-dispositioned before the 72-hour
   window for assertion 3 can be graded. For each, either name a cause-fix
   carrier (for the delegated gate: classify client-interrupted runs apart
   from delegation faults, which is a livespec-dev-tooling spec change), or
   re-scope the trigger through that repository's specification.
2. Five groups that were not in the baseline emailed in the window. They fall
   under assertion 2 at verification (real, current, and owned, or quiet), not
   under assertion 3, but each needs a disposition before the final sweep.
3. `FWE8Bw962Pj`'s owner `bd-ib-3kdjct` is closed. If the trigger fires again,
   that is a new finding.
