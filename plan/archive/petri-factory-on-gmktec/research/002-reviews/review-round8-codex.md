# Independent Codex review — revision 8

Reviewed 2026-10-15. **NO-BLOCKERS at design-review level.** I found no new concrete lockout counterexample in the combined I1–I4, H1–H6 and G1–G5 protocol. The two round-7 blockers are resolved. This is not implementation acceptance or authorization to converge gmktec.

Only local reads and this explicitly requested report write were performed. No remote command, package operation, service operation, repository edit or ledger edit was performed. Earlier reviewers' host/source measurements below are attributed evidence, not measurements repeated here. `review-round6-fable.md` was absent in the initial directory listing but appeared during this review and was read before completion. `review-round7-fable.md` was absent at the final availability check; no round-7 Fable verdicts can be invented.

## Ranked findings

### SHOULD-FIX 1 — Specify how `recover` delegates, and give it an explicit lifetime if it is itself a helper

Evidence: `design-rev8.md:1089-1104` puts `recover` under the common lock and dispatches it to publish, rollback or confirmation finalization; `805-819` requires every subcommand to run in its own bounded transient unit; `1037-1044` supplies operation budgets and a close-on-exec lock descriptor, but lists no `recover` budget.

There are two safe implementations, but the text does not choose one. Recovery can be a short dispatcher that releases the lock and launches the selected operation, which must independently revalidate identity, marker and phase under its own lock. Alternatively, it can execute the selected internal handler under the existing acquisition and a sufficiently large explicit outer budget. It must not hold the lock while synchronously launching another ordinary lock-taking helper: that child waits for the parent, times out, and recovery never performs its selected action. Close-on-exec does not release the parent's lock.

Make the choice explicit. If recovery is only an alias in the controller, remove it from the table's claim that every listed operation runs under the lock and document the actual target helper's revalidation. If it is a host helper, include it in the bound and SIGSTOP acceptance cases. The existing design already requires bounded operations, so this is an incomplete execution contract rather than evidence that an unbounded implementation is intended.

### SHOULD-FIX 2 — Remove the non-working `systemctl show` spelling from the effective-condition instrument

Evidence: `design-rev8.md:911-919` still says “`systemctl show -p Conditions` parsed through `busctl` / the D-Bus `Conditions` property.” The newly available `review-round6-fable.md`, “Facts measured this round” and SHOULD-FIX 5, reports `Conditions=[unprintable]` on both target-v259 hosts, while direct D-Bus access returns the array.

Use direct `busctl get-property` (or equivalent D-Bus access) for the condition array; do not pipe or parse `systemctl show` output as if it contained that array. Require two `ConditionPathExists` entries with trigger=true, negate=false and the exact permission paths. Read the aggregate `ConditionResult` separately for the attempted inhibited start; do not treat an array entry's final integer as proof of that attempt's outcome.

G6 explicitly offers the working D-Bus route, so this does not invalidate the design's proof mechanism. It is nevertheless worth fixing the command spelling before translating the design into tasks. F5's target-v259 scratch-root `cat`, distinct probe permission and trigger-condition journal message remain credible instruments; the version-specific evidence is in `review-round5-fable.md:31-90`, not a fresh test here.

### NOTE 3 — Make retry states and the observer's lock scope explicit when consolidating the table

Evidence: `design-rev8.md:895-907` requires repeated rollback after interrupted and partial attempts; `1089-1104` summarizes rollback as allowed from “every pre-commit phase.” `881-882,982-984` explicitly release the observer's lock between progress updates, whereas `1089` says every operation runs under the lock.

I read I2 as a dispatch table whose admission/marker decision is locked, preserving H2's and G4's explicit observer exception. I also read “pre-commit” as absence of a committed marker, including `rolling-back` and `rollback-partial`, with the special absent-marker `committed` case expressly admitted by I2. Those readings preserve the repeating recovery mechanism and do not require a protocol change.

Write those interpretations directly: enumerate rollback retry states, retain terminal `rolled-back` no-op behavior, and say that the observer locks admission, claims `observing`, and later locks only its progress/final transition. Test a second firing after both parent death and `rollback-partial`; exercising each table row once is insufficient to establish retry behavior. The older G5/G8 tests should remain required alongside I5.

### NOTE 4 — The confirm/dead-man arbitration and reboot rules now have a coherent successful path

Evidence: `design-rev8.md:703-717,803-824,841-851,965-984,1002-1021,1073-1121`; timer/source evidence recorded in `review-round5-fable.md:31-90` and bounded-oneshot evidence in `review-round6-fable.md`, “Facts measured this round.”

I1 admits a new reservation without applying that predicate to the owning run's next operation. I2 then permits a first confirmation with no marker, but only after observation, evidence, boot/freshness and deadline checks. Start and observe have fixed identities, and rollback stops those producers before daemon cleanup and handoff. A failed observer launches rollback without waiting on the operation that stops it. Shared publication remains ownership-checked under the lock.

A confirm that wins the lock and commits makes a waiting dead-man firing harmless: it subsequently reads the marker and exits. A rollback that wins first records `rolling-back`, making first confirmation ineligible. A confirm arriving after expiry refuses even if the firing has not acquired the lock. Confirmation stops the timer, not synchronously the potentially lock-waiting rollback service. Preserve that distinction.

The repeating timer remains a credible retry mechanism after service exit or failure, with G1/H6 bounding hung killable processes and G5 bounding repeated interrupted phase attempts. Its first delay is now computed from the arming deadline. Scheduling tolerance and multiple failed firings still belong in measured recovery times; the single-firing expression in G1 is not a guarantee of complete recovery despite repeated failures.

Pre-commit reboot loses temporary permission and challenge and expires the old boot's deadline; the transient timer need not survive to inhibit starts. I4 supplies runtime-directory initialization for explicit later recovery. A surviving committed marker selects finalization regardless of stale phase; an absent marker cannot be recreated merely because a phase says committed. Post-commit failures may still need operator recovery, including a confirm that dies before stopping its timer; I2's committed rollback no-op is safe, not automatic finalization.

### NOTE 5 — Acceptance and companion gates remain outstanding

Evidence: `design-rev8.md:298-319,378-383,599-607,786-794,932-943,1052-1061,1123-1129`; `review-round7-codex.md`, NOTE 6; `review-round6-fable.md`, SHOULD-FIX 6–7 and NOTE 12.

No implementation results, disposable-host fault-injection results, companion merge, corrected host records or proven gmktec LAN fallback accompany this revision. Preserve these gates. Stubbed k3s/LLM probes in the VM do not demonstrate live k3s coexistence. The actual implementation must show the ordinary successful lifecycle as well as all recovery cases before convergence.

The late-arriving round-6 Fable report also leaves useful implementation questions: whether gmktec receives `sandbox_storage` and its additional drop-ins, prompt controller-triggered rollback after visible failures, challenge expiry behavior, and recovery of committed-but-inactive services. Refusing unknown drop-ins is safe; do not silently broaden that allowance to copy hp's layout. Committed validation must report inactive units accurately rather than equating enablement with running. These are not demonstrated new lockout paths in revision 8.

## One-line verdicts on every round-7 Codex finding

1. **RESOLVED** — BLOCKER 1: I1 restricts admission to a new reservation and excludes its own unit; I2 separately admits operations on the current run, including deadline rollback.
2. **RESOLVED** — BLOCKER 2: I2 explicitly permits first confirmation without a marker and resumes interrupted publishing through recover; marker authority remains intact.
3. **RESOLVED** — SHOULD-FIX 3: I3 fixes both start and observe identities, and I1/I3 require inactive units with no queued jobs at admission/handoff.
4. **RESOLVED** — SHOULD-FIX 4: I4 creates the runtime directory and stable lock on demand and repeats Docker-group admission after installation, before permission.
5. **RESOLVED** — NOTE 5: the intended serialized commit/dead-man protocol is now reachable; F5/G6 retain working instruments, with the command-spelling refinement in finding 2.
6. **NOT RESOLVED** — NOTE 6: convergence gates remain stated but no completion evidence is supplied; a design-level NO-BLOCKERS verdict does not close them.

## Round-7 Fable findings

No report was available: `review-round7-fable.md` did not exist at the final availability check. The newly available round-6 Fable report was considered as earlier evidence, not substituted for a round-7 review.

REVIEW-COMPLETE: NO-BLOCKERS
