# Independent Codex review — revision 6

Reviewed 2026-10-15. **BLOCKERS remain.** Revision 6 governs revision 5, which governs the earlier mechanisms. This is a design review, not implementation acceptance. Evidence uses `design-rev6.md` unless another file is named. Earlier reviewers' host and systemd-259 measurements are attributed evidence, not measurements repeated here. I performed no remote commands, package operations, service changes, repository changes or ledger changes. This explicitly requested report is the only write.

## Ranked findings

### BLOCKER 1 — The observer is neither a singleton nor quiesced by rollback; it can mutate Docker after its run loses ownership

Evidence: `design-rev6.md:809-812` gives each invocation a distinct `<seq>` unit; `877-888` requires `started`, leaves the lock free during observation, and checks phase when recording progress; `643-653` and `895-907` specify rollback without stopping the observer. The rollback predicate lists the three Docker units, their jobs and the sandbox slice, not outstanding observer processes or API requests.

A concrete execution remains allowed:

1. Observer A checks `started`, then pauses immediately before submitting its canary creation request. It is outside the lock.
2. A deadline firing or another controller rolls A back. The rollback kills Docker and the sandbox, checks its postconditions and records `rolled-back`. Observer A lives in its own guard unit and is not among the killed cgroups.
3. B reserves, publishes and starts Docker before A's observer lifetime expires.
4. A resumes and submits its pending `docker run` to B's daemon. It can create a container and firewall rules in B's observation window. Its later phase check may reject its progress record, but cannot undo the already-issued mutation safely.

This does not require an untrusted Docker client: the stale client is part of the guard. A systemd bound eventually killing A is not an ownership fence. There is also no atomic claim distinguishing an already-running observer from a second `observe A`: both require the unchanged `started` phase, and different `<seq>` names allow both units to execute. They can run two canaries and overwrite the shared challenge.

Required: atomically claim a unique observer instance under the lock; fence its Docker mutations against rollback entry; and make observer/API-client quiescence a prerequisite for rollback's final check and reservation handoff. Specify how rollback stops the observer without deadlocking against its progress-lock acquisition or an observer synchronously waiting for the rollback it launched. A fixed unit name alone prevents duplicate activation but does not solve stale requests. Test a paused observer immediately before canary creation, rollback plus a new run, then resumption; also test concurrent duplicate observers and failure-triggered rollback while the observer is exiting.

### BLOCKER 2 — Releasing a confirmed run does not define a safe lifecycle for subsequent converges

Evidence: `design-rev6.md:247-251` retains validate-only behavior for an already-confirmed installation; `705-717` retains the global confirmed marker and post-commit reconfiguration; `828-847` defines the new run phases; `864-873` requires reconfiguration to name the current confirmed run, but makes the next reserve release that run and allocate another. Start permission is existence of the global marker, independent of the newly reserved run (`48-65`).

Let A be successfully confirmed. The next converge reserves B and marks A `released`, while `/var/lib/docker-engine-guard/confirmed` still names A. There is no specified transition for B to finish a validate-only converge: B is `reserved`, has no observation or challenge, and cannot legitimately use `confirm B`. `release` has a budget in G1 but no entry conditions, effects or caller. Reconfiguration also has no eligible identity: A is no longer current/confirmed, and B is not confirmed.

The dangerous alternative is treating B as another ordinary publish/start transition. A's durable permission already permits all three units to start; B's rollback cannot revoke it by removing `allow-start`, and the retained R1 rule refuses a marker naming another run. Such a transition cannot satisfy the pre-commit inhibition or rollback predicates. Removing A's marker to manufacture a fresh transition would violate the established post-commit contract and is not an authorized fix.

Keep the committed installation identity and permission distinct from a short-lived converge reservation, or explicitly retain A for validation/reconfiguration. Define a terminal outcome for every validate-only run and a matching reserve rule. Forbid entering the initial guarded transition while any committed installation marker exists. Acceptance must include two consecutive no-op converges, a post-commit configuration change, and interruption of each of those operations. The current G8 omits these cases.

### SHOULD-FIX 3 — Automatic attachment rolls back a healthy controller's live run

Evidence: `design-rev6.md:866-869` tells a controller finding any nonterminal run to attach and call rollback; `684-688` and `790-792` previously required a second controller to be refused. G3 takes precedence.

There is no distinction between an abandoned run and a healthy run whose first controller is still installing, starting or observing. A routine overlapping converge now actively tears down the first one's work. The lock serializes the commands but does not confer recovery authority. Combined with the unlocked observer this also supplies a trigger for blocker 1 before the deadline.

Refuse an overlapping live run, or attach read-only and wait for its existing owner/outcome. Define automatic recovery eligibility using the boot identity, deadline and active operation/timer state, with an explicit takeover path when needed. A new controller's mere presence must not mean the existing run has failed. Update the simultaneous-controller acceptance case to exercise the actual role behavior, not only the `reserve` subcommand in isolation.

### SHOULD-FIX 4 — The timer no longer fires at the run's recorded deadline

Evidence: `design-rev6.md:657-660` arms `--on-active=<N>` before start; `829-831,889-891` sets the absolute deadline at reserve. Local `/usr/share/man/man5/systemd.timer.5.gz`, `OnActiveSec=`, defines that interval relative to timer activation, not reservation.

If reserve is at R, timer arming is at A, and the stored deadline is R+N, the supplied timer command first fires at A+N. Publication, package work and controller delays make A later than R. Confirmation can be refused at the recorded deadline while Docker remains permitted until the later timer fires. G1's advertised recovery-delay bound omits this discrepancy. The wall-clock deadline also uses a different clock from the monotonic timer.

Persist one boot-scoped monotonic deadline for this transition, derive the initial timer delay from the remaining interval at arming, and refuse start if the deadline has already passed. Keep a wall-clock timestamp for reporting if desired. Define exactly when arming occurs and include the install budget in the deadline calculation; G4 currently lists publish/start/observe/confirm but G7 does not place installation clearly within that sequence. Test a delayed arm and clock adjustment. The repeating `--on-unit-inactive=60` mechanism itself is not the defect.

### SHOULD-FIX 5 — Interrupted installation recovery is not connected to the new phase machine

Evidence: `design-rev6.md:837-840` admits start only from `published`, then writes `started` before its work; `858-861` admits publish only from `reserved`; `866-873` sends an attaching controller through rollback, verify and a new reservation; `923-930` instead promises recovery on the next publish/start attempt **for that run**. R7's durable intended-package record remains required at `538-546`.

G7 improves package process ownership and explicitly admits trigger-handler recovery. But it does not assign the install transaction to an operation/phase, nor explain how its promised retry is admitted. If installation is part of start, a crash after the early `started` write makes the next start refuse. If it is part of publish, the design must specify its order relative to snapshot completion, configuration publication and the `published` transition. The automatic attach path instead terminates the original run and reserves a different one; no rule transfers or reuses its interrupted-install provenance and snapshot. These are different recovery protocols, not interchangeable implementation choices.

Define one executable sequence with durable install intent, an explicit recoverable phase, complete snapshot requirements, and an exact allowed resume or rollback/re-reserve path. Bind the frontend helper's lifetime and the run's deadline to its install budget. Fault-inject before dpkg starts, during unpack/configure and during trigger processing; show the next normal converge reaches an admissible recovery command without broadening the package allowlist or replacing the original baseline with a partially mutated one.

### SHOULD-FIX 6 — Recovery dispatch and verify must use the commit marker before the phase

Evidence: `design-rev6.md:705-710` makes rename the irrevocable commit; `841-847` performs rename before writing `committed`; `866-869` chooses rollback or confirm from phase and then unconditionally calls verify; `689-691` defines verify as the rollback postcondition check that marks `rolled-back`. R1 at `399-405` correctly made the marker authoritative over state.

Crash after rename but before writing `committed`: the disk phase can still be `observed`. G3 therefore dispatches rollback. The retained F1 committed-marker check makes that rollback a harmless no-op, which is good, but the next verify cannot pass: a committed installation intentionally has a permission, socket, processes, bridge and Docker rules. Even the ordinary `committed` branch calls confirm and then this same rollback verifier. Recovery stops instead of finishing and releasing normally.

Make attachment inspect the authoritative marker first, and define separate successful finalization paths. A committed run needs confirmation validation, not a verifier that asserts absence of all Docker state and can write `rolled-back`. If a persisted phase says committed but the marker is absent after uncertain durability/reboot, preserve R1's marker-first rule rather than recreating permission from phase alone. Include a crash between rename and the phase update and a reboot after a failed directory fsync in acceptance.

### SHOULD-FIX 7 — Complete the external and per-phase bounds rather than claiming every operation is covered

Evidence: `design-rev6.md:805-824` lists budgets for reserve/publish/start/observe/confirm/rollback/release but none for `verify` or `reconfigure`; `642-643,895-907` wraps phases in timeouts without specifying termination escalation or an aggregate phase budget. Local `/usr/share/man/man5/systemd.service.5.gz`, `TimeoutStartSec=`/`RuntimeMaxSec=`, and `/usr/share/man/man5/systemd.kill.5.gz`, `KillMode=`/`SendSIGKILL=`, support G1's basic bounded-oneshot repair.

G1 fixes the previous unlimited simple service and makes SIGSTOP recovery credible for ordinary killable processes. Specify budgets for the other lock holders as well. Specify a kill-after grace for phase children, lock descriptor noninheritance, and a total budget that leaves time for the final all-postconditions check. Otherwise a child ignoring TERM can consume the whole parent budget; G5's attempt exhaustion eventually makes progress, but that is not F9's stated promise that later steps run in the same firing after a hung step.

G5's isolated children plus recorded attempts address the earlier repeated-parent-death objection. Retain that improvement, and state which records must be durable before phase entry and how a postcondition that regresses after a recorded success becomes eligible for repair again. Do not claim an unconditional finite recovery bound for kernel/storage failure; the useful bound is under the stated process-failure model.

### NOTE 8 — Timer/confirmation arbitration and F5's instruments are substantially repaired; acceptance remains outstanding

Evidence: `design-rev6.md:633-655,703-710,815-824,841-851,902-919`; `review-round5-fable.md:31-90` records target-v259 source/host checks; local `systemd.timer(5)` documents relative timers and that an already-active triggered service is not restarted.

For a single correctly owned run, a bounded confirm and a repeating dead-man can arbitrate through the lock. Stopping the timer does not have to cancel a firing already waiting for that lock: after the commit it sees the authoritative marker and must do nothing. Do not make confirmation synchronously stop that lock-waiting service. Before commit, rollback entry makes confirmation ineligible. G2 correctly adds boot/deadline checks and permits post-commit confirm retries without an expired challenge. G5 now stops terminal/exhausted timers and avoids disabling transient units.

F5 plus G6 is a meaningful improvement: use the target's v259 `cat --root` behavior, include/reject unexpected drop-ins, then inspect effective parsed conditions, with all real permissions absent before fresh installation. The prior target checks are evidence for the instruments, not proof that an implementation has passed them. Preserve the real-package disposable-host test and report structured journal fields where possible.

Small unfinished items from round 5 remain: creating `/run/docker-engine-guard` after reboot before opening its fixed lock path is not explicit; the primary-group admission check is still stated only before reserve, although the fresh install creates the Docker group; the socket-stop step still lacks nonblocking ordering; the 120-second challenge has no defined reissue path. The obsolete “three subcommands” and “at most one permission” text should be removed when consolidating the design.

No completed companion merge, corrected host records, proven gmktec LAN fallback or fault-injection results are supplied. Those remain explicit gates (`378-383,599-607,788-794,934-943`), not findings that can be closed by describing acceptance tests. This report does not authorize convergence.

## One-line verdicts on every round-5 Codex finding

1. **RESOLVED** — B1: G1 replaces the inert simple-service timeout and bounds start/confirm/rollback externally with group termination; the omitted secondary-operation budgets are finding 7 above.
2. **RESOLVED** — B2: G2 requires published for start, forbids rollback re-entry into forward work, checks boot/deadline and recognizes already-committed confirmation retries.
3. **RESOLVED** — B3: G3 moves shared configuration publication/reconfiguration into ownership-checked locked helpers and gives delayed uploads a per-run destination; observer mutation is the separate new blocker 1.
4. **RESOLVED** — B4: G4 assigns canary, window, evidence, challenge and teardown to an observer; its missing singleton/quiescence protocol is new blocker 1.
5. **RESOLVED** — SF5: G5 isolates phase work and records bounded interrupted attempts so repeated death at one phase need not permanently starve later phases, subject to the implementation details in finding 7.
6. **NOT RESOLVED** — SF6: boot-scoped challenges are repaired, but attachment, committed recovery and later-run completion still fail as described in findings 2, 5 and 6.
7. **RESOLVED** — SF7: G6 adds the full drop-in check, parsed effective conditions and absence of the durable permission before fresh installation.
8. **NOT RESOLVED** — SF8: G7 supplies installer parentage and trigger states, but its recovery command is not integrated with phase eligibility and reservation replacement (finding 5).
9. **NOT RESOLVED** — NOTE9: several mechanisms remain sound, but companion work, fallback proof and representative acceptance evidence remain required and unsupplied (note 8).

## One-line verdicts on every round-5 Fable finding

1. **RESOLVED** — B1: G4 supplies the missing observation owner, canary lifecycle, evidence and failure-triggered rollback, and G8 restores the failed-sample test; ownership races are new blocker 1.
2. **RESOLVED** — SF2: G1 makes the dead-man a bounded oneshot with termination escalation; per-child timeout details remain finding 7.
3. **NOT RESOLVED** — SF3: G3 adds an attachment path, but confirmed validate-only runs still lack a defined completion path, and recovery indiscriminately rolls back live runs (findings 2, 3 and 6).
4. **RESOLVED** — SF4: G2 explicitly enables all three units during idempotent confirmation finalization; validation should assert that this completed.
5. **RESOLVED** — SF5: G2's exact published-phase predicate prevents start after rollback entry or a prior start.
6. **RESOLVED** — SF6: G5 stops the timer on rolled-back/exhausted partial outcomes, bounds futile retries and forbids transient-unit disable; a committed but unfinished run still depends on a later valid finalization path.
7. **RESOLVED** — SF7: G3 places the snapshot in the host run directory before publishing eligibility for start; completeness/durable recovery ordering must be specified with finding 5, and verify's phase-specific meaning with finding 6.
8. **RESOLVED** — NOTE8: the repeating-timer mechanism remains usable and an already-queued firing must harmlessly recognize commitment; the newly split reservation/arming deadline is finding 4.
9. **RESOLVED** — NOTE9: F5 retains target-v259 instruments and G6 strengthens effective-condition checks; structured journal matching remains an implementation recommendation.
10. **NOT RESOLVED** — NOTE10: G7 chooses installer placement and trigger recovery, but recovery eligibility remains incomplete and blocking socket-stop ordering is unchanged (findings 5 and 7, note 8).
11. **NOT RESOLVED** — NOTE11: the obsolete count/permission wording, post-reboot lock-directory initialization and admission-check timing are still not explicitly corrected (note 8).

REVIEW-COMPLETE: BLOCKERS
