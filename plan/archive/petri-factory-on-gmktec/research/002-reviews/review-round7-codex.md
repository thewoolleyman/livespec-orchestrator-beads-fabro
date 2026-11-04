# Independent Codex review — revision 7

Reviewed 2026-10-15. **BLOCKERS remain.** Later revisions govern earlier ones. This is a design review, not implementation acceptance. No remote commands, package operations, service operations, repository changes or ledger changes were performed. This explicitly requested report is the only write. Earlier reviewers' host/source measurements are attributed evidence, not measurements repeated here. `review-round6-fable.md` was absent at the start and remained absent when checked before writing; there are no round-6 Fable findings available to adjudicate.

## Ranked findings

### BLOCKER 1 — H1's admission predicate rejects the current run's own forward and recovery operations

Evidence: `design-rev7.md:954-963` requires, before **any guarded operation**, no nonterminal run and no active/activating guard unit or dead-man; G1 at `803-819` requires every subcommand to execute inside a guard transient unit; H4 at `1000-1018` prescribes reserve → publish → arm → start → observe → confirm.

After reserve succeeds, the current run is nonterminal. The next publish therefore fails H1. Even if the nonterminal-run test is informally waived for the owning run, arm deliberately activates the dead-man timer, so start fails the no-active-timer test. If the check is implemented inside the locked helper, the helper also sees its own activating oneshot unit. If it is instead a controller-side check before launching the helper, it is not the atomic reservation predicate promised by H1 and must not substitute for that predicate.

This is an executable-contract contradiction, not a demonstrated new lockout: a literal implementation fails closed and cannot install successfully. Relaxing the predicate ad hoc is also dangerous because the design does not state which exemptions preserve recovery authority. In particular, rollback must be allowed while the observer and dead-man are active; H2 specifically relies on rollback stopping the observer.

Required: scope the no-existing-run/no-old-unit predicate to **admission of a new reservation**, with the reserving invocation itself excluded. Existing-run operations must instead check the current reservation identity and their exact allowed phases under the lock. Explicitly admit the deadline rollback and named operator recovery while the relevant run is nonterminal. Preserve H1's refusal of a second controller rather than equating that refusal with a ban on the owner's next operation. Test the ordinary successful sequence and deadline rollback with an active observer, as well as competing controllers.

### BLOCKER 2 — H5 turns every first confirmation into rollback and overrides the promised install-resume branch

Evidence: `design-rev7.md:1023-1033` says **every dispatch**, expressly including `confirm`, first reads the marker and, if it is absent, the run “is rolled back.” G2 at `841-847` requires an uncommitted, observed run to publish that marker only after checking evidence, nonce and deadline. H4 at `1005-1010` permits explicit recovery to resume an interrupted `publishing` run. H5 is later and governs both.

On an entirely healthy first run, the marker is necessarily absent when confirm begins. H5 therefore sends that run to rollback before G2 can create the marker. There is no first successful confirmation under the governing rule. Similarly, an interrupted inert publish necessarily has no confirmed marker; the operator recovery invocation is routed to rollback, making H4's promised resume choice unreachable.

Marker-first authority is correct. The error is equating **uncommitted** with **must roll back for every command**. Absence of the marker is also the normal state for authorized forward work.

Required: define dispatch by both command and marker. A matching marker always selects idempotent finalization/committed validation; a foreign or invalid marker refuses. With no marker, an ordinary confirm evaluates G2's pre-commit eligibility and may commit; rollback performs rollback; explicit recover selects the documented inert-publish resume or rollback branch. A persisted committed phase without a marker after reboot must still select rollback rather than recreate permission. All marker reads and subsequent decisions must remain under the same lock. Include a normal first confirmation and explicit interrupted-publish resume in acceptance, alongside the crash-after-rename cases.

### SHOULD-FIX 3 — Give the start operation the unit identity that rollback actually stops

Evidence: `design-rev7.md:809-812` assigns operation units `docker-engine-guard-<op>-<run>-<seq>`. H2 explicitly replaces that naming rule for observe (`967-970`), but names `docker-engine-guard-start.service` as a stop target at `972-977` without explicitly replacing start's G1 launch name.

Following the launch recipe creates a start unit that the named stop does not target. This does not, by itself, recreate the old observer race: start still holds the common lock and has an external bound, and H2 does explicitly fix the observer identity. Nevertheless, the claimed start-unit quiescence check is aimed at an unspecified unit and cannot establish that the actual start invocation is inactive.

Specify a fixed start unit too, or record and stop the exact generated identity. Use the same identities in admission, rollback and acceptance. Also make H1's handoff predicate include deactivating units and pending jobs where they can retain execution; active/activating alone is not a complete quiescence predicate. H2 already requires the observer and start units to be inactive, and that stronger requirement should be used consistently.

### SHOULD-FIX 4 — Explicit boot initialization and post-install admission checks remain missing

Evidence: the fixed lock path is `/run/docker-engine-guard/lock` (`627-628,818-819`); F3 explicitly loses tmpfs state on reboot (`693-701`); H5 defines post-reboot recovery but does not initialize that directory (`1023-1033`). F7 still checks Docker group credentials only before reserve (`763-766`). These were explicitly retained in `review-round6-codex.md`, NOTE 8.

Specify creation of the root-owned runtime directory before every helper opens the fixed lock file, without replacing or unlinking an existing lock inode. Otherwise the promised post-reboot recovery has an unstated prerequisite. Repeat the primary/supplementary Docker-group admission check after installation creates the group and before permission is granted. A check performed when the group does not yet exist is not the final admission check for the installed socket.

These are small implementation-contract fixes; neither requires changing the transaction architecture.

### NOTE 5 — The repeating dead-man, commitment arbitration and F5/G6 instruments remain credible

Evidence: `design-rev7.md:657-660,703-738,803-824,841-851,902-919,1012-1021,1035-1050`; target-v259 measurements/source findings recorded in `review-round5-fable.md:27-107` and its NOTES 8–9; `review-round6-codex.md`, NOTE 8.

Subject to fixing findings 1–2, the intended arbitration is sound: confirm and rollback serialize their decisions under the lock. A firing already waiting for that lock need not be cancelled when confirm stops the timer; it must recognize the marker after acquiring the lock and perform only the committed path. Do not make confirm synchronously stop the lock-waiting dead-man service. Bounded oneshots address stalled lock holders, and repeated firings address an interrupted rollback. H6 now supplies secondary-operation budgets, child kill escalation and close-on-exec lock handling. These are meaningful repairs.

H4 also correctly separates inert installation from the network-risk deadline and uses a boot-scoped monotonic deadline. The timer still has its stated accuracy/scheduling allowance; acceptance should not interpret “at the recorded deadline” as zero scheduling latency. Pre-commit reboot still inhibits starts because neither permission survives; post-commit recovery correctly follows a surviving marker rather than the phase record. An absent marker after uncertain durability must remain uncommitted.

F5 uses the target-v259 scratch-root cat capability and the correct trigger-condition journal text; G6 adds unexpected-drop-in rejection and inspection of parsed effective conditions, with all actual permission paths absent before fresh installation. I found no new instrument defect in revision 7. Preserve the actual-package disposable-host test and preferably match structured journal fields. Earlier source checks establish that these instruments can work, not that a future implementation has passed them.

### NOTE 6 — Convergence gates remain unevidenced

Evidence: `design-rev7.md:298-319,378-383,599-607,786-794,932-943,1052-1061`; `review-round6-codex.md`, NOTE 8.

No implementation/fault-injection results, companion merge, corrected host records or demonstrated gmktec LAN fallback accompany this revision. The stubbed VM test does not exercise live k3s coexistence. Keep these as explicit convergence gates; this review does not authorize applying Docker to gmktec. The remaining bounded socket-stop ordering and challenge-reissue suggestions in round-6 NOTE 8 are still suggestions, not newly demonstrated safety blockers.

## One-line verdicts on every round-6 Codex finding

1. **RESOLVED** — B1: H2 atomically claims a singleton observer, stops it before daemon cleanup/handoff and launches failure rollback without waiting; H1's overbroad admission predicate is the separate new blocker 1.
2. **RESOLVED** — B2: H3 forbids new guarded reservations once confirmed, preserves the committed identity and uses validation/reconfigure for subsequent converges.
3. **NOT RESOLVED** — SF3: automatic takeover is removed, but H1's replacement predicate also rejects the owning run's normal operations and must be scoped as finding 1 specifies.
4. **RESOLVED** — SF4: H4 starts the deadline after inert installation and derives the timer's initial interval from a boot-scoped monotonic deadline.
5. **NOT RESOLVED** — SF5: H4 assigns installation to publishing with intended provenance and a retained snapshot, but H5 overrides its explicit no-marker resume branch with unconditional rollback (finding 2).
6. **RESOLVED** — SF6: H5 makes the marker authoritative and separates committed validation from rollback verification; its unconditional absent-marker branch introduces the different defect in finding 2.
7. **RESOLVED** — SF7: H6 supplies all listed operation budgets, timeout kill escalation, aggregate phase headroom, close-on-exec locking, durable attempts, success invalidation and the process-failure scope.
8. **NOT RESOLVED** — NOTE8: the timer and condition instruments remain credible, but boot-directory/admission details and the unevidenced acceptance/companion/fallback gates remain (findings 4–6).

## Round-6 Fable findings

No verdicts available: `review-round6-fable.md` did not exist at the start of this review or at the final existence check. Earlier Fable reviews were considered as prior evidence, not substituted for a missing round-6 report.

REVIEW-COMPLETE: BLOCKERS
