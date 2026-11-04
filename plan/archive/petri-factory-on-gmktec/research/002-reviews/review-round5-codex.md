# Independent Codex review — revision 5

Reviewed 2026-10-15. **BLOCKERS remain.** Revision 5's final section governs this review. Evidence below uses `design-rev5.md` line numbers and local systemd manuals. Prior host measurements are attributed to the supplied reviews, not repeated measurements. No remote commands, package operations, service changes, repository changes or ledger changes were performed. The explicitly requested review file is the only write.

## Ranked findings

### BLOCKER 1 — The repeating timer does not bound a running rollback, and cannot recover a stalled lock holder

Evidence: `design-rev5.md:624-637,657-669`; local `/usr/share/man/man1/systemd-run.1.gz` (default service type), `/usr/share/man/man5/systemd.service.5.gz` (`TimeoutStartSec=`, `RuntimeMaxSec=`), `/usr/share/man/man5/systemd.timer.5.gz` (`OnUnitInactiveSec=`, already-active services).

The exact F1 command does not set `Type=oneshot`. `systemd-run` defaults to `Type=simple`, whose startup completes when the process is forked. `TimeoutStartSec=600` therefore does NOT limit the running rollback to 600 seconds. A stopped or hung guard remains active indefinitely; `OnUnitInactiveSec=60` needs deactivation to schedule its next attempt, and timer activation never replaces an already-active service. The claim that the next firing repairs a hung firing is false for this command.

There is a second independent lock-holder problem. `start` and `confirm` have no externally enforced lifetime. Per-command timeouts do not bound the parent process, a stopped interpreter, or an internal filesystem operation. Stop `confirm` after it takes the lock but before the rename: every dead-man attempt waits 60 seconds and exits without revoking `allow-start`. Repeating those failures forever does not restore access. The same problem exists if `start` stalls after granting permission. This is precisely the liveness failure the removed watchdog used to address.

Give EVERY lock-holding operation a host-owned, externally enforced lifetime, including termination escalation and descendant cleanup. For the rollback service, explicitly choose either a bounded oneshot activation or a simple/exec service with `RuntimeMaxSec`; bound stopping as well. Establish a total recovery-delay budget that includes lock acquisition, forced termination and the next timer interval. Test SIGSTOP of the guard itself, particularly `confirm` before commit, not merely a subprocess that its timeout wrapper can kill. Prevent children from retaining the lock after the parent dies, and keep the lock inode stable across invocations.

### BLOCKER 2 — `start` can undo an in-progress rollback; retries also invalidate the deadline and confirmation claims

Evidence: `design-rev5.md:629-655,665-666,681-691`.

`start` checks the reservation, `rolled-back`, `confirmed` and an armed timer. It does NOT check `rollback-started` or `rollback-partial`. A concrete permitted execution is: rollback writes `rollback-started`, revokes permission, performs partial cleanup and exits with `rollback-partial`; a delayed or retried controller calls `start` for the same reserved run; all of start's specified checks pass and Docker is permitted and started again. Mutual exclusion prevents simultaneous execution, but does not prevent this invalid sequential transition. The old dead-man then tears it down again. Worse, a guard crash after writing `rollback-started` but before recording an outcome creates the same opening.

Make rollback entry irreversible for that run across ALL subcommands, not just `confirm`. `start` must require an explicit eligible phase and reject any rollback-started/partial/terminal run. Define what a duplicate start does after its original success; do not replay permission creation after revocation. Bind eligibility to the original deadline and boot identity. Merely testing that a timer is armed does not establish that its deadline is still in the future; a repeat timer can remain armed after expiration. Enforce expiration at the locked decision point rather than allowing a delayed `confirm` to win only because the rollback service has not acquired the lock yet.

F1 also makes confirmation finalization non-resumable as written: it checks a challenge younger than 120 seconds before recognizing an already committed run. Crash after rename and retry after 120 seconds: finalization refuses, contrary to F1/F4's promise that every later confirm repeats it. Recognize a matching authoritative `confirmed` first and finalize without a fresh challenge; only an uncommitted invocation should evaluate confirmation eligibility. Cover these sequences explicitly in F9.

### BLOCKER 3 — Reservation serializes allocation, but does not fence the controller's later writes

Evidence: `design-rev5.md:681-691`; inherited controller/configuration work at `84-90,538-546`; round-4 Codex finding 3 specifically required delayed-controller-write and terminal-to-next-run handoff tests.

F2 says the role writes configuration after successful reservation. It does not require those writes to reacquire the lock and check ownership. Controller A can reserve A and then pause before a write. A later rolls back (or an explicit recovery does so), permitting controller B to reserve B. A's delayed write can now overwrite B's daemon configuration, drop-ins, probe parameters or provenance. The statement that every later *subcommand* checks the reservation does not cover the explicitly controller-owned file writes. The same race can occur after a timed-out run while the old controller continues its forward work.

Route every shared mutation through a helper that checks the reserved generation under the lock, or submit immutable per-run inputs and have the locked helper publish them. Do not hold a controller's long-lived lock across remote waits: that would reproduce blocker 1. Define how post-commit configuration is fenced too. Unique run IDs and a rule against reusing them are necessary, but are not by themselves write fencing. Test a suspended controller resuming after a different run is reserved, not only two simultaneous reserve calls.

### BLOCKER 4 — Removing the actor leaves the canary, observation and challenge protocol without an execution owner

Evidence: old actor duties at `102-120,573-579`; replacement at `617-637,657-669`; F9 at `785-793`.

The old actor pulled and ran the canary, proved slice limits and egress, sampled the host over W, issued the end-window challenge, validated the response and removed the canary before commit. F1's new `start` only starts the daemons. Its `confirm` only checks a fresh nonce and absence of rollback entry. No replacement operation is assigned canary creation/removal, the observation loop, or publication of the challenge. R8's probes are expressly retained, but R8 still says the removed actor issues and accepts the challenge. An implementation cannot follow this design literally and reach a legitimate confirmation.

Specify the executable flow and its owner. If the controller now owns sampling and canary operations, define how its results authorize a challenge, bind them to the reserved run/boot/configuration, fence its writes as in finding 3, and make controller loss leave rollback solely responsible for cleanup. Confirmation needs evidence of the complete window and canary checks, not merely a recently created nonce. Define the handling of a failed sample and the removal of the canary before commit. The observation interval must still cover the required reconciliations, and the deadline must include the whole sequence. This is a missing protocol step, not a demand to restore the long-lived actor.

### SHOULD-FIX 5 — Replaying from the top does not prove progress after repeated death of the guard itself

Evidence: `design-rev5.md:640-655,663-675,787-789`; round-4 Codex blocker 2.

F1 improves recovery from an individual *child command* failure: a surviving parent can continue to later steps. It does not resolve the earlier repeated-parent-crash case. If the guard repeatedly dies inside phase 4 (for example while parsing the ruleset), each new firing starts from the top and dies in phase 4 again; interface cleanup and the final record never execute. An external runtime bound repairs a parent hang only by terminating it, with the same replay problem. The acceptance wording conflates killing a child step with killing the guard.

Either isolate all hazardous phase work in separately bounded child processes under a minimal surviving driver, or retain durable interrupted-attempt/deadline information so repeated guard death cannot indefinitely prevent later independent repairs. Document the residual failure model. Test repeated parent death at the same point, separately from a one-time interrupted firing and a child exit. The original round-4 progress claim is not yet justified.

### SHOULD-FIX 6 — F3 provides safe inhibition after reboot, but not a complete recovery or stale-challenge rule

Evidence: `design-rev5.md:573-579,633-637,681-701`.

The pre-commit reboot argument is sound within the stated nonpersistent-network scope: tmpfs permission disappears and durable conditions inhibit starts. The transient timer disappearing is therefore not itself a blocker. However, the durable reservation remains nonterminal, so a new reserve refuses. F3 mentions a later rollback, but the role's prescribed first action is reserve, with no recovery entry path specified. Define how a controller attaches to the existing run, repairs it and releases it before reserving another; also handle a crash after reserve but before `intended` or snapshots exist.

R8 rejects pre-reboot answers, but the new confirm predicate carries only a run, nonce and age. A challenge left on disk can still be younger than 120 seconds after a quick reboot. State explicitly that challenges are boot-scoped (or tmpfs) and validate that scope. Otherwise the inhibited machine can be committed using an old window and answer without observing the rebooted host. Retain the correct distinction between atomic visibility at rename and uncertain durability if directory fsync fails; F4 does make that distinction.

### SHOULD-FIX 7 — F5 is a better instrument, but concatenated unit text is not proof of effective conditions

Evidence: `design-rev5.md:721-738`; local `/usr/share/man/man5/systemd.unit.5.gz`, condition-list reset semantics; Fable round-4 finding 3 records target systemd 259 support for `systemctl --root ... cat`.

F5 fixes the incomplete `verify` root, the real-permission test path and the journal text. Those previous objections are resolved. However, requiring the output to contain both condition lines only proves their textual presence. A later drop-in can reset `ConditionPathExists=` or add another true OR condition. Copying only the intended drop-in into scratch also omits pre-existing target overrides. Require the complete relevant target drop-in set, reject unexpected overrides, and assert the effective condition list (using the manager's `Conditions` property once units exist, with suitable parsing). Require the real `confirmed` path absent in the fresh-install branch as well as both temporary paths. Its mere existence grants permission regardless of marker contents.

Keep the successful postinst-attempt evidence and real-package disposable-VM test. The target-version `cat --root` behavior was reported by the prior reviewer; it was not exercised on a host in this read-only review.

### SHOULD-FIX 8 — Package fencing improved, but interrupted-trigger and helper-loss recovery remain underspecified

Evidence: `design-rev5.md:509-529,742-759`; round-4 Codex finding 6; local `/usr/share/man/man1/dpkg.1.gz` (`DPKG_FRONTEND_LOCKED`) and `/usr/share/man/man2/fcntl.2.gz` (process-associated record-lock ownership).

F6 supplies a host-owned bounded lock helper, audits the main dpkg configuration and separates fresh from interrupted installations. Those are real improvements. It still only permits pending states on this run's packages, without enumerating authorized trigger handlers outside that set or `triggers-awaited`. Pending work can legitimately involve an already-installed trigger consumer. Specify actual allowed package/trigger states and how to reconcile them without configuring unrelated pending work.

Also specify the helper/installer parentage and failure protocol. A database lock while dpkg is alive prevents concurrent dpkg writers, but is not the same as the frontend fence across audit, pre-dpkg startup and subsequent validation. Do not continue a previously audited installation after losing the helper before dpkg acquired its lock; abort/reconcile or reacquire and revalidate. Tests should kill the helper before and during installation and kill the controller independently. No package operation was run for this review.

### NOTE 9 — Several repairs are sound, but acceptance and companion work remain prerequisites

Evidence: `design-rev5.md:635-655,703-717,764-783,599-607,298-319`.

F4 correctly makes visible confirmation irrevocable even after a failed directory fsync, explains the temporary permission overlap and hashes owned keys semantically. F1 limits job cancellation to named units and explicitly rechecks the complete final rollback predicate after quiescence. F7 adds primary-GID and route-table checks and an explicit trusted-root assumption; its range test should distinguish address conflicts from ordinary covering default routes. F8 removes the false immutable-shim requirement. These resolve the corresponding design findings, subject to implementation evidence.

The lock orders a healthy concurrent confirm/rollback pair correctly: rollback first writes `rollback-started` and confirm refuses; confirm first publishes the marker and rollback does nothing. Stopping the timer need not cancel a queued firing for safety, because that firing checks the marker. This does not cure a stalled lock holder or invalid sequential transitions.

No completed companion merge, corrected host records, LAN fallback test, implementation or fault-injection results are supplied. The stubbed VM does not establish live k3s coexistence. This review is not approval to converge the unreachable host.

## Round-4 dispositions — Codex

1. **NOT RESOLVED** — READY/watchdog implementation is moot, but independent liveness is still absent for lock holders and the timer service (finding 1).
2. **NOT RESOLVED** — Child failures can be skipped; repeated death of the guard still prevents later phases (finding 5).
3. **NOT RESOLVED** — Locked reserve fixes allocation, but delayed controller writes remain unfenced (finding 3).
4. **RESOLVED** — F4 explicitly defines rename authority, fsync failure and safe permission overlap.
5. **RESOLVED** — F5 replaces the incomplete scratch-root verify recipe and isolates the probe path; effective-condition completeness still needs finding 7.
6. **NOT RESOLVED** — Helper lifetime, main config audit and fresh/recovery branches improved; trigger states and helper-loss reconciliation remain (finding 8).
7. **RESOLVED** — F8 removes immutable shim/PID inventory survival for churning pods.
8. **RESOLVED** — F7 adds primary-group checks, a trusted-root assumption and explicit route/CIDR collision checks; verify the assumption in implementation.
9. **RESOLVED** — F1 explicitly rechecks all critical final postconditions after writers stop.
10. **NOT RESOLVED** — Companion work, fallback proof and representative acceptance remain gates without supplied completion evidence.

## Round-4 dispositions — Fable

1. **RESOLVED** — No terminal actor respawns; intentional dead-man firings are distinct, though rolled-back timers should eventually be retired.
2. **NOT RESOLVED** — Notify/READY is moot, but replacement supervision still permits indefinite stalls (finding 1).
3. **RESOLVED** — F5 uses target-version cat, exact paths and the trigger-condition journal message; see effective-condition caveat in finding 7.
4. **RESOLVED** — F1 cancels only filtered job IDs and explicitly forbids bare cancel.
5. **NOT RESOLVED** — The impossible recover flag is moot and reserve is atomic; delayed writes, forward ownership and recovery entry remain unspecified (findings 3, 4, 6).
6. **RESOLVED** — F4 hashes parsed owned keys and defines ordinary post-commit reconfiguration.
7. **RESOLVED** — F6 bounds the host-owned helper and moves timer restoration beyond the stated worst-case budget; supervision defects must be fixed for that budget to hold.
8. **RESOLVED** — F5 gives the probe its own temporary permission and asserts both temporary paths absent before install; also assert confirmed absent as finding 7 requests.
9. **RESOLVED** — F6 corrects the trigger claim and retains the fcntl frontend-lock protocol.
10. **RESOLVED** — Cgroup-scoped killing is retained; bounded per-step socket stop avoids indefinite blockage, although no-block stop is preferable; actor RuntimeDirectory teardown is moot.
11. **NOT RESOLVED** — F7 adds config/drop-in reads and repeated DNS-placement verification, but all effective configuration sources and the replacement challenge owner are not specified (finding 4).
12. **RESOLVED** — F4 explicitly permits the safe overlap of the two permissions.
13. **RESOLVED** — F1 disables all three units on rollback and F3 documents condition-skipped enabled units after an intervening reboot.

## Round-3 dispositions — Codex

1. **RESOLVED** — F4 makes the visible marker authoritative; late finalization must bypass the nonce eligibility check (finding 2).
2. **NOT RESOLVED** — Cooperative guard calls serialize, but controller writes and lifecycle transitions remain unsafe (findings 2–3).
3. **NOT RESOLVED** — The repeating timer cannot repair a permanently active firing or stalled lock holder (finding 1).
4. **RESOLVED** — Actual frontend locking, scoped recovery and host-side timer restoration replace observation-only fencing; retain finding 8's refinements.
5. **RESOLVED** — F5 replaces the nonexistent property and F1 scopes queued-job cancellation; effective-condition verification still needs refinement.
6. **NOT RESOLVED** — Correct credential/endpoint semantics survive, but removal of the actor leaves challenge issuance and complete-window authorization undefined (finding 4).
7. **RESOLVED** — F7/R9 define route checks, consumers/trust boundary and expected network/interface identities.
8. **RESOLVED** — R7 publishes intended provenance before package mutation; reserve-before-provenance recovery remains an explicit edge case to specify.
9. **NOT RESOLVED** — Companion implementation and corrected records are required but not evidenced complete.
10. **RESOLVED** — Footprint selection is retained and F1 adds the complete final post-quiescence predicate.
11. **RESOLVED** — Narrow shared-state/access claims and the stubbed-coexistence limitation are retained.

## Round-3 dispositions — Fable

1. **NOT RESOLVED** — Terminal restart loops are removed, but bounded recovery and repeated-parent-crash progression remain unproven (findings 1, 5).
2. **RESOLVED** — F5 provides mechanism, assembled-text and post-install checks instead of the invalid property; refine effective conditions as finding 7.
3. **RESOLVED** — R4 excludes reconciler-owned chain contents and specifies the comparison scope.
4. **RESOLVED** — R8 avoids pod-local stub DNS and GitHub's hourly quota, with explicit SNI and direct cluster-DNS querying.
5. **RESOLVED** — R7 publishes intended package provenance before mutation.
6. **RESOLVED** — All cooperating guard subcommands share a flock; controller write fencing is the separate remaining finding 3.
7. **RESOLVED** — R8 resolves the nested slice path through ControlGroup.
8. **NOT RESOLVED** — F8 removes the unsound churn check, but live shim coexistence remains unmeasured; stubbed acceptance is not direct cover.
9. **RESOLVED** — Socket stop immediately follows permission revocation, with a per-step bound.
10. **RESOLVED** — Both-family exact-token selection, whitespace normalization and per-table chain identities are retained.
11. **RESOLVED** — Archive hashes/versions and a real frontend lock are specified; interrupted-trigger reconciliation remains finding 8.
12. **RESOLVED** — Immediate re-probe and failure attribution remain in R8, subject to assigning the replacement sampling owner.
13. **RESOLVED** — Prior minor version, dependency and namespace-DNS observations introduce no additional blocker.

REVIEW-COMPLETE: BLOCKERS
