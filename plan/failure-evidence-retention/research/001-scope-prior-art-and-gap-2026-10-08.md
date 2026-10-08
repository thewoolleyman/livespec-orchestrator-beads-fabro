## The maintainer's statement of what done means

- **Preserved failure evidence:** retain complete output, original exit status and source identity automatically, so diagnosing a failure doesn’t require rerunning it.

## Definition of Done assertions derived from that statement

- When any dispatch stage, gate, hook, janitor or factory node exits non-zero, its complete stdout, complete stderr, original exit status and the identity of the process or principal that ran it are retained as an immutable digest-addressed artifact outside the disposable checkout, and the journal row for that stage names the artifact path and digest beside the existing tail.
- When the artifact cannot be written, the stage's exit status and verdict are unchanged and the journal row records that retention failed and why.
- A run that reached a terminal state has its full record exported to a durable ledger comment on its work-item and read back before fabro rm removes it, on the reaper's path and the operator's, without a person performing the export.
- Forcing a hook failure on a real dispatch, the failing assertion and the original exit status are recovered from the retained artifact alone, without rerunning the stage.

# Failure-evidence retention: scope, prior art and the gap (2026-10-08)

Status of this note: the opening research note of plan
`failure-evidence-retention`. It records where the discipline came from, what
the originating session lost, what this repository already retains, and what is
new. It decides nothing that binds an implementer.

The Definition of Done assertions above this heading are SESSION-DERIVED. The
maintainer adopted the statement verbatim from the `overseer-herdr-rewrite`
session's proposal on 2026-10-08 and instructed that plans be opened for it; the
assertions were derived by the `factory-reliability` session (Claude Code,
`livespec-orchestrator-beads-fabro`) without the maintainer present to confirm
them, so they are a proposal to be confirmed, not a ruling.

All times are UTC. "The overseer session" means the Codex session
`overseer-herdr-rewrite`, driving plan `herdr-overseer` (epic `overseer-uzvcbn`)
in the `livespec-overseer` tenant. A "stage" is any dispatch stage, gate, hook,
janitor or factory node whose exit status decides something.

## 1. Provenance

Same origin as the sibling plan `run-control-lease-and-versioned-instructions`:
the overseer session's six-point proposal of 2026-10-08, reviewed by the
`factory-reliability` session against every open plan in the fleet. The
"preserved failure evidence" row had no owning plan for the general rule; one
child of plan `definition-and-proof-of-done` covers one stage of it (section 3).
The session's consolidated note is copied verbatim into the sibling plan as its
research note 002; its "Failure output is discarded or never emitted" row and
its "Enforcement boundary and honest limits" section are the source for this
plan's assertions 1, 2 and 4.

## 2. What the overseer session lost (epic `overseer-uzvcbn` comments)

- "detailed traceback was discarded by direct tail filtering" (comment 30).
- "Hook's failure text is truncated" (comment 89).
- "original hook failure cause remains UNKNOWN" (comment 90) — the failure
  that blocked the plan could not be diagnosed from its record and had to be
  re-run to be seen again.
- "host journal retains a tail only" (comment 97). Receipts the session did
  keep live in `/tmp/herdr-shared-fixture-*`, outside any durable store.

The repository's own measurement that admitted `bd-ib-nezrrh` is the same
shape: gate `20261007T142403Z-3604049` (`reconcile-merged` of `overseer-ssjzmo`,
failed 2026-10-07T14:37:09Z) retained no failing-check traceback and an empty
check cache, so the cause of a red post-merge janitor on an already-merged item
could not be established from the record. This repository's own guidance
(`AGENTS.md`, memory "Janitor red hides the failing target") already tells an
operator to re-run `just check` in the kept checkout — a rule that exists
because the record is insufficient.

## 3. What already exists, and why it is not this

- `commands/_dispatcher_engine_journal.py::journal_stage` keeps `exit_code`
  and a 2000-character `tail` of the exit-selected stream per stage; both
  streams only when the caller passes `streams=True`. Nothing keeps the whole
  output, and nothing names who ran the stage.
- Fabro failure cause, category and signature are journaled on failed outcomes
  since `bd-ib-nf39` (closed; it had been `null`). That is a classification, not
  the output.
- `bd-ib-nezrrh` (ready, today under `bd-ib-7sjdzv`, Scenario 145): the failed
  POST-MERGE JANITOR retains complete stdout, stderr and exit code as a private
  digest-named artifact the journal names, never overwritten, with a
  storage-failure arm that preserves the verdict. It is the exact mechanism this
  plan wants, scoped to one stage. It re-parents here as the first slice; the
  general rule generalises its artifact contract rather than inventing another.
- Plan `pr-stage-backgrounded-push-fault` (`bd-ib-ctagnf`), mechanism 3:
  carries the failing stage and the engine's `BackgroundedTool` / `TimedOut`
  cause through the `needs_human` terminal onto the drive result, journal and
  ledger. Cause, not output; it stays there.
- Closed prior art on PRESERVING WORK rather than output: `bd-ib-kttyks`
  (preserve committed work on publish-stage failure), `bd-ib-d0ul`, `szqb`,
  `fjtg`, `llev` (preserve-by-reference pointer to the run checkpoint),
  `bd-ib-eh6xaa` (janitor red records stderr only).
- Fabro run output is reachable only through `fabro inspect` / `dump` /
  `attach --server <factory>` while the run exists, and dies with
  `fabro rm --force`. `AGENTS.md` §"Working with the maintainer" makes
  "export, then reap" a MANUAL precondition: capture the `ps -a` row, run id,
  terminal state, nodes, checkpoint sha, review verdict, failure cause and
  journal rows into a ledger comment, read it back, then reap. Nothing performs
  that export automatically, and the reconcile-runs terminal reaper
  (`_dispatcher_reconcile_runs_terminate.py`) is the one code path that calls
  `fabro rm`.
- `bd-ib-tw4v` (ready): a dispatcher refusal exits 3 with no text at all —
  the degenerate case of this plan, where there is no evidence to retain
  because none was emitted.

## 4. The gap this plan owns

1. **Every failed stage retains its evidence.** Any dispatch stage, gate, hook,
   janitor or factory node that exits non-zero has its COMPLETE stdout and
   stderr, ORIGINAL exit status, the identity of the process or principal that
   ran it, and (where the runtime produces one) the traceback written as an
   immutable, digest-addressed artifact OUTSIDE the disposable checkout, and the
   journal row names the artifact path and digest beside today's tail.
2. **A storage failure never changes the verdict.** When the artifact cannot be
   written the stage's exit status and verdict are exactly what they were, and
   the journal row says the retention failed and why.
3. **Export-before-reap is automatic.** A run that reached a terminal state has
   its full record exported to a durable ledger comment on its work-item and
   read back BEFORE `fabro rm` removes it, on both the reaper's path and the
   operator's, so the maintainer-declared "export, then reap" rule is enforced
   rather than remembered.
4. **Diagnosis without rerun, demonstrated.** Forcing a hook failure on a real
   dispatch, the failing assertion and original exit are recovered from the
   retained artifact alone. This is the fault test the session's note names.

## 5. Boundary against sibling plans

- `definition-and-proof-of-done` keeps proof RECORDS (what was proved); this
  plan keeps FAILURE evidence (what went wrong). `bd-ib-nezrrh` moves here.
- `pr-stage-backgrounded-push-fault` carries the failing stage and CAUSE to the
  terminal; this plan carries the OUTPUT.
- `run-control-lease-and-versioned-instructions` attributes who ACTED on a run;
  the source identity retained here is who RAN the failing stage.
- `silent-failure-surfaces` owns surfaces that report success on failure
  (`bd-ib-cewr.2`, a green report hiding a FAILED verdict); the two overlap only
  where a hidden failure also has no retained output.

## 6. Where the work lands

All in-repo and factory-dispatchable: the journal artifact contract generalises
`bd-ib-nezrrh`'s; the automatic export hooks into the reconcile-runs terminal
reaper and `fabro rm` call sites; the fault test is a real dispatch with a
forced hook failure. Factory-node output beyond what the Dispatcher captures
would need a Fabro-side change and is a fork item if the Dispatcher's capture
proves insufficient.

## 7. Items re-parented under this plan at opening

- `bd-ib-nezrrh` — failed post-merge janitor retains complete output
  (assertions 1 and 2, janitor slice; re-parented from `bd-ib-7sjdzv`).

Assertions 3 and 4 have no carrier yet; children are filed after the maintainer
confirms the Definition of Done, and the carrier map is re-recorded then.
