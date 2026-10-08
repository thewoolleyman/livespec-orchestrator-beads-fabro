## The maintainer's statement of what done means

- **One controller per run:** an exclusive lease with a generation number; reject commands from competing or expired owners.
- **Versioned instructions:** every queued instruction names its intended run, stage and revision. Recheck those when delivering it; reject obsolete instructions and expose cancellation and supersession.

These controls need fault tests that reproduce the failures: deliver a stale instruction after recovery, introduce a second controller, end the coordinator before the factory fails, and attempt closure without real Herdr proof.

## Definition of Done assertions derived from that statement

- A steer, cancel or reconcile command issued against a live factory run by a session that does not hold the run's current controller lease, or holds an expired generation of it, is refused at the factory boundary and reaches no worker, while an observation from that same session is still answered.
- Every mutation of a run on the shared factory is attributed, on the run's own event record and in the dispatch journal, to the principal that issued it, and one documented command maps every live run to its work-item, repository and controller.
- An instruction queued for a run carries its id, content hash, target run, stage and expected revision, is rechecked against the run's current stage and revision at delivery, and an obsolete instruction is rejected with no reset, edit or recommit in the worker.
- A queued instruction can be inspected, cancelled and superseded, and its submitted, delivered, acknowledged and verified-effect states are recorded separately on the run's record.
- A recovered or resumed run is launched from one authoritative current instruction revision, superseded handoffs are retained as history and never re-delivered, and an incomplete or mismatched recovery bundle starts zero actors.
- Fault tests that introduce a second controller, deliver a stale instruction after recovery and submit a partial recovery bundle through real CLI and agent sessions each reproduce the original failure against the unprotected path and pass against the released protection.

# Run-control lease and versioned instructions: scope, prior art and the gap (2026-10-08)

Status of this note: the opening research note of plan
`run-control-lease-and-versioned-instructions`. It records where the two
disciplines above came from, what the originating session measured, what this
repository and its siblings already carry, and what is new. It decides nothing
that binds an implementer; the scoping event and the child work-items follow.

The Definition of Done assertions above this heading are SESSION-DERIVED. The
maintainer adopted the statement verbatim from the `overseer-herdr-rewrite`
session's proposal on 2026-10-08 and instructed that plans be opened for it; the
assertions were derived by the `factory-reliability` session (Claude Code,
`livespec-orchestrator-beads-fabro`) without the maintainer present to confirm
them, so they are a proposal to be confirmed, not a ruling.

All times are UTC. "The overseer session" means the Codex session
`overseer-herdr-rewrite`, driving plan `herdr-overseer` (epic `overseer-uzvcbn`)
in the `livespec-overseer` tenant from herdr pane `w1:p5`. A "run" is one Fabro
run on the shared factory (`hp`); a "controller" is the agent session that
dispatched it or is steering it; an "instruction" is any message, correction or
directive that a controller submits for a run or for the worker inside it.

## 1. Provenance

On 2026-10-08 the overseer session, after four days of factory failures on plan
`herdr-overseer`, wrote a six-point proposal opening "We need enforced state
transitions at the factory boundary. Prompts alone won't prevent these
failures." The maintainer pasted it into the `factory-reliability` session and
asked for a review of general applicability against every open plan in this
repository, `livespec-overseer` and the other livespec repositories. That review
(three parallel surveys, 2026-10-08 06:10–06:16Z) found six of the fourteen
distilled improvements had no owning plan; they cluster into this plan and its
sibling `failure-evidence-retention`. The session's own consolidated note,
"Mechanical safeguards for factory-driven plans", existed only at
`/tmp/herdr-factory-mechanical-safeguards.md` on the `vps` host; it is copied
verbatim into this plan as research note 002 so the record survives the file.

## 2. What the overseer session measured (epic `overseer-uzvcbn` comments)

Every instance below produced a plausible result at the surface the controller
was watching, which is why none of them self-announced.

- **A continuation landed in the wrong stage.** A capture-stage continuation
  was delivered into the review stage; the reviewer treated it as a closeout,
  skipped review, and the run failed closed (comment 47, 2026-10-06T17:48Z).
- **A late steer reset completed work.** A correction submitted after the
  worker had already repaired the defect made it soft-reset a clean commit
  (comment 85).
- **An older queued directive was consumed instead of the current one.** A
  directive submitted at 01:33 "was NOT received", an older queued one was, and
  the actor reset completed source (comment 86).
- **A foreign instruction was consumed first.** A CI instruction from ANOTHER
  plan's owner was consumed ahead of this session's correction (comment 92).
- **Ownership was procedural.** The session's answer was a file,
  `/root/resume_execution_owner`, which it describes as "procedural ownership,
  not a server-enforced lease" (comment 93, 2026-10-08T04:05Z).
- **A build was deleted under a live dispatch.** The plugin cache build was
  removed while `drive.py` was executing from it (comment 23, `bd-ib-3ftj`).

The same shapes exist in this repository's own ledger, filed independently and
earlier, which is what makes the discipline general rather than Herdr-specific:

- `bd-ib-gbu3k6` (2026-07-23): with two tracks dispatching concurrently an
  operator killed the OTHER track's run by elimination, because nothing names
  which container belongs to which work-item.
- `bd-ib-m1av` (2026-09-06, P1): a second dispatcher engine's preflight
  `reconcile-runs` cancelled a sibling engine's just-launched run as
  `superseded-run` inside the ~40 s window before `dispatch-run-stamp`.
  `bd-ib-cewr.5` under plan `silent-failure-surfaces` is the watchdog
  orphan-sweep form of the same hazard and stays under that plan because its
  dotted id binds it there; the two must be designed together.
- `bd-ib-opvf7x` (2026-09-10): three running runs across three repositories
  were cancelled within five seconds under the shared `fabro:dev` token; the
  server logs nothing per request, so the cancel is unattributable.

## 3. What already exists, and why it is not this

- `commands/_dispatcher_dispatch_lock.py`: a per-item PID-liveness lock
  (`tmp/fabro-dispatch-<item>.lock`, pid plus start epoch). It serialises two
  dispatches of ONE item on ONE host; it has no generation, it is not known to
  the factory, and `reconcile-runs`, the watchdog and `fabro run cancel` do not
  consult it.
- `commands/_dispatcher_claim_reclaim.py`, `_dispatcher_pre_run_claim.py`:
  ledger-side claims on the ITEM, not on the run; they say who may dispatch,
  not who may steer or cancel a live run.
- `commands/_dispatcher_reconcile_runs_attribution.py::_orphan_reason`: the
  code path that produced `bd-ib-m1av`. It attributes a live run to an item by
  journal lookup and cancels on a mismatch; it has no notion of a controller.
- Plan `agent-session-stall-prevention` (`bd-ib-jnpvh4`), child `bd-ib-dle6l3`
  and overseer carrier `overseer-okf6bu`: a generation-fenced lease on the
  RECOVERY OWNER of a durable obligation. That is the right primitive one level
  down (it fences who may recover), and this plan should reuse its vocabulary —
  attempt id, generation, fenced writer — rather than invent another. It does
  not fence who may steer or cancel a live run.
- Plan `relay-delivery-and-progress-deadline` (`bd-ib-lrik25`), children
  `bd-ib-t3znvw` and `bd-ib-zi5ygh`: a stable id, typed expected result,
  deadline and result epoch for PLAN-LEVEL relays between sessions. Same shape,
  different object: nothing versions an instruction addressed to a factory run
  by run, stage and revision, and there is no cancel or supersede surface for
  one. The in-run human gate was retired by `bd-ib-dgs54p` ("ledger is the only
  gate"), so today an instruction to a run is a ledger comment the worker reads
  whenever it next reads the item — which is exactly how comment 86's older
  directive was consumed.
- Fabro itself (fork `thewoolleyman/fabro`, branch `factory-integration`):
  `run.cancel.requested` carries an actor of kind `user`, issuer `fabro:dev`,
  subject `dev` — the one shared dev token every client uses. There is no
  per-client identity and no request log (`bd-ib-opvf7x` remedy options a/b).

## 4. The gap this plan owns

1. **Controller lease with generation.** A run has at most one controller; the
   lease is held at the factory boundary (Fabro's control service, per the
   fork), carries a generation, and every mutating verb — steer, cancel,
   reconcile-terminate, restart — presents it. A competing session or an
   expired generation is refused before the worker sees anything; observations
   (`ps`, `inspect`, `dump`) need no lease.
2. **Mutation attribution.** Every mutation names the principal that issued it
   — a per-client identity on the server instead of the shared dev token, or a
   request-level audit log shipped through the host OTel collector, or both
   (`bd-ib-opvf7x`); and the Dispatcher exposes an ownership surface mapping
   runs to work-item, repository and controller (`bd-ib-gbu3k6`).
3. **Versioned, cancellable instructions.** An instruction to a run carries an
   id, a content hash, the target run, stage and expected revision; delivery
   re-checks applicability and refuses an obsolete one with zero side effects;
   `submitted`, `delivered`, `acknowledged` and `verified effect` are separate
   recorded states; inspect, cancel and supersede exist as verbs.
4. **Authoritative-revision recovery.** A recovered or resumed run is built from
   ONE current instruction revision; superseded handoffs are retained as
   history, never re-delivered; an incomplete or mismatched recovery bundle
   starts zero actors. This is the sibling of `bd-ib-fngpwg` (resume a
   terminated run from its published pull request, plan
   `definition-and-proof-of-done`), which owns WHAT is resumed; this plan owns
   which INSTRUCTIONS the resumed actor receives.
5. **Fault tests** that reproduce comments 47, 85, 86, 92 and 93 through real
   CLI and agent sessions — a second controller, a stale instruction delivered
   after recovery, a partial recovery bundle — and that fail against the
   unprotected path before they pass against the released protection.

## 5. Boundary against sibling plans

- `agent-session-stall-prevention` owns the durable OBLIGATION and who may
  RECOVER it after a coordinator's turn ends. This plan owns who may STEER a
  live run while a controller exists.
- `relay-delivery-and-progress-deadline` owns relays BETWEEN SESSIONS and the
  progress deadline. This plan owns instructions TO A RUN.
- `silent-failure-surfaces` keeps `bd-ib-cewr.5`; the fix for the orphan sweep
  and for `bd-ib-m1av` should land once a run carries a controller and a
  stamped start, and both items must be read together.
- `failure-evidence-retention` owns what a failed run leaves behind; the
  attribution surface here is about who ACTED, not what was printed.
- `definition-and-proof-of-done` owns resume-from-published-work
  (`bd-ib-fngpwg`); this plan owns the instruction set a resumed actor gets.

## 6. Where the work lands

The lease and the per-client identity are Fabro control-service changes and
therefore fork work on `thewoolleyman/fabro` `factory-integration`, driven
through the host-routed door in `.ai/fabro-fork-hand-build.md` (the fork has no
ledger tenant and the sandbox cannot build it). The attribution surface,
instruction versioning on the Dispatcher side, recovery-bundle verification and
the fault tests are in-repo and factory-dispatchable. The maintainer's standing
direction (2026-09-30) is to stay current on Fabro and contribute upstream where
possible, so the lease design should be written as an upstream-shaped change.

## 7. Items re-parented under this plan at opening

- `bd-ib-gbu3k6` — ownership-attribution surface (assertion 2).
- `bd-ib-opvf7x` — unattributable cancel on the shared factory (assertion 2).
- `bd-ib-m1av` — sibling engine's reconcile cancels a just-launched run
  (assertion 1; the defect a controller lease makes impossible).

Assertions 3–6 have no carrier yet; the design children are filed after the
maintainer confirms the Definition of Done, and the carrier map is re-recorded
then.

## 8. Noted, not owned here

The session's note (research 002) also proposes two controls this plan does not
take: a mediated validation budget ("discretionary reruns need an explicit
allowance"), which the note itself concedes is mechanical only if the execution
service mediates every launch; and a typed `needs_groom` recoverable outcome so
a routine decomposition request does not route to `needs_human`, which belongs
with the needs_human terminal redesign in plan `pr-stage-backgrounded-push-fault`
(`bd-ib-ctagnf`). Both are recorded there for the owning sessions to pick up.
