# Independent Codex review — revision 4

Reviewed 2026-10-15. **BLOCKERS remain.** This is a design review, not implementation acceptance. Revision 4's final section governs the older text. I read the supplied design and prior reviews and checked the local systemd, dpkg and fcntl manuals. I performed no remote operations, package operations, service operations or repository/ledger changes. This requested report is the only file written. Prior reviewers' host measurements are attributed evidence, not measurements repeated here.

## Ranked findings

### BLOCKER 1 — The watchdog is not armed merely by configuring Type=notify and sending WATCHDOG=1

Evidence: `design-rev4.md:148–154,430–455`; local `/usr/share/man/man5/systemd.service.5.gz`, sections `Type=`, `WatchdogSec=`, `TimeoutStartSec=` and `TimeoutAbortSec=`. The watchdog documentation says: “The watchdog is activated when the start-up is completed.” The notify startup protocol requires `READY=1`.

R3 specifies only `WATCHDOG=1`; it never defines when `READY=1` is sent. The inherited `TimeoutStartSec=infinity` remains in force. A literal implementation can create `allow-start`, start Docker and hang while still activating: there is neither an active runtime watchdog nor a startup deadline. Sending periodic watchdog notifications alone does not complete notify startup. The “actor that never starts” invariant covers failure before permission creation, not this interval. On a recovery invocation, a hang before READY can also strand an already permitted daemon from the previous invocation.

Define a bounded startup stage, its failure/restart behavior, and an explicit READY handshake before any forward mutation. Cover recovery startup too. Explain how READY and the unit's `Before=` ordering interact: declaring the guard ready releases ordered Docker jobs, so the absent permission must still be the fence during uncommitted boot recovery. Specify bounded watchdog abort/termination and subprocess cleanup, rather than leaving the total recovery delay to inherited defaults. Ensure legitimate 60/180/300-second work advances an event loop that sends progress-based heartbeats; a synchronous call with a timeout longer than 60 seconds can otherwise trigger the watchdog while functioning correctly.

Acceptance must SIGSTOP the actor before READY, after READY, immediately after permission creation, and during recovery startup. Require a bounded transition to rollback in each relevant case. This is an unclosed liveness hole, not an objection to using systemd's watchdog.

### BLOCKER 2 — Restarting the first incomplete rollback phase does not guarantee progress after a process crash

Evidence: `design-rev4.md:439–460`; rollback budgets at `156–162`.

R3's exception handler handles catchable Python exceptions. It cannot handle SIGKILL, watchdog termination, a native crash, or a stopped process. Consider phase 4 deterministically hanging or crashing before recording completion. Systemd restarts the actor; phase 4's postcondition is still false; R3 selects phase 4 again. This repeats forever, with phases 5–7 never reached. Disabling start-rate limiting prevents abandonment by systemd, but does not prevent this loop. The stated acceptance case “repeated crash in rollback phase 4 ... phases 5-7 done” cannot follow from the specified protocol.

Persist an attempt/in-progress record before entering each hazardous phase, with a restart-surviving bounded attempt budget or absolute per-phase deadline. On recovery, distinguish an interrupted failed attempt from a never-attempted phase; after its budget is exhausted, record the unresolved postcondition and proceed to later cleanup. Catch failures in postcondition evaluation and state-recording paths explicitly as far as possible. Define terminal `rollback-partial` behavior separately from recovery of a nonterminal attempt. Test actual process death and watchdog kills, not only exceptions caught inside the same process.

### BLOCKER 3 — The actor is a singleton, but run allocation and configuration mutation are not serialized with it

Evidence: `design-rev4.md:84–90,410–425,436–445,536–546`.

The actor's lifetime flock correctly excludes a second cooperating actor. It does not lock the controllers that allocate `current-run`, publish `intended`, or write daemon/guard configuration. Two controllers can both observe no current nonterminal run, prepare different run IDs, and overwrite the shared pointer or configuration while the single actor operates. R2 states that the controller never allocates over a nonterminal run, but supplies only a check, not an atomic reservation or a shared ownership protocol. The second controller need not create a second actor process to invalidate the first actor's snapshot, configuration digest or provenance.

There is an additional handoff ambiguity: `Restart=always` restarts a terminal actor even after exit 0. Thus a successful rollback does not make the unit quiescent. Its next invocation can race the controller assigning a new run; interpreting that invocation as recovery could roll back the new prepared run, while interpreting it as a fresh start could allow stale invocation state to act on it. Terminal-state publication is not equivalent to releasing all old-run execution.

Serialize allocation, configuration/provenance publication and actor handoff on the host. One workable design is to make controllers submit immutable requests and let the sole host service reserve and mutate the active run under its lock. Another needs an explicit lock protocol covering *all* writers without blocking recovery. Define whether terminal actors remain alive and idle, are deliberately stopped, or use a distinct terminal exit status excluded from restart. Bind each invocation and controller response to the reserved run generation. Demonstrate two competing controllers, a delayed controller write, and terminal-to-next-run handoff, not just two calls to `systemctl start`.

### SHOULD-FIX 4 — R1 repairs split authority, but its permission and publication claims need precision

Evidence: `design-rev4.md:387–406`.

Making `confirmed` authoritative and irrevocable resolves the old crash between permission publication and terminal state: finalization can resume without rollback. However, “at any moment at most one” permission exists is false. The stated sequence creates `confirmed` before removing `allow-start`; both exist during normal finalization and after an intervening crash. This overlap is safe under the new irrevocable-commit rule, so document it rather than claiming mutual exclusion.

Define the rename/fsync boundary and ambiguous I/O failure handling. Rename exposes the marker to systemd before the directory fsync completes. If that fsync raises, generic “before commit failure => rollback” must not leave a visible confirmed permission while performing rollback. The live actor must use the same marker-authority rule as recovery, including a visible marker after a failed durability operation, and report durability uncertainty. Distinguish process-crash atomicity from power-loss durability. Add failures after rename and during directory fsync to acceptance, not just kills between successful operations.

### SHOULD-FIX 5 — The condition proof is substantially repaired, but the scratch-root recipe is incomplete

Evidence: `design-rev4.md:489–505`; local `/usr/share/man/man1/systemd-analyze.1.gz`, `systemd-analyze verify` documents checks for required dependencies and executable availability as well as directive syntax.

The disposable probe, exact real drop-in locations and positive post-install condition evidence fix the previous nonexistent-property check. However, a root containing only extracted unit files and drop-ins generally lacks the referenced executables and base units required by `verify`. Specify a complete scratch environment or a narrowly defined verification method that can actually pass; do not train the implementation to ignore generic verification failures.

Also assert the *effective two conditions and their exact paths* in the assembled real units; a syntax checker is not an assertion that a required condition exists. Keep the test permission isolated from production permissions and explicitly specify the substitution in the probe. Preserve the post-install skip evidence and real-package VM acceptance. The mechanism remains credible; this review does not claim a drop-in fails to work merely because its main unit is initially absent.

### SHOULD-FIX 6 — R6 uses the correct frontend protocol, but recovery and lock-holder failure need explicit treatment

Evidence: `design-rev4.md:509–534,538–546`; local `/usr/share/man/man1/dpkg.1.gz`, `DPKG_FRONTEND_LOCKED`, documents that the variable tells dpkg not to acquire the frontend lock; local `/usr/share/man/man2/fcntl.2.gz`, “Advisory record locking,” states that process-associated locks are released at process exit and are not inherited across fork.

Holding an actual fcntl frontend lock across audit and installation is the correct fix to observing a free lock. `DPKG_FRONTEND_LOCKED=1` is documented; it is neither a lock acquisition nor proof the helper remains alive. Specify that installation runs host-locally and remains supervised if the controller disappears. Test death of the helper while its dpkg child is alive: the child does not inherit the parent's POSIX record-lock ownership. Do not claim the frontend exclusion survives that death automatically, or assume dpkg's separate database lock supplies identical audit fencing. Define safe refusal/reconciliation of this case.

The clean `dpkg --audit` requirement must explicitly apply to a fresh transaction, with a separately validated recovery branch for this run's unpacked/half-configured packages. Otherwise R6 refuses exactly the interrupted states R7 promises to resume. Installed versions alone are insufficient recovery state. Enumerate allowed trigger handlers and actual trigger states, including pending work generated by this transaction; an empty `triggers/Unincorp` is not by itself a complete trigger-state predicate. R6 already acknowledges systemd/man-db handlers outside the three new packages, so distinguish such authorized recovery work from unrelated pending configuration. Include the main `/etc/dpkg/dpkg.cfg` in effective configuration auditing, not only its `.d` directory.

These are implementation-contract refinements to a sound locking approach; I am not retaining the old “no lock is held” objection.

### SHOULD-FIX 7 — Requiring every original k3s shim to survive rejects healthy CI churn

Evidence: `design-rev4.md:17–20,174–183,580–582`; prior `review-round3-fable.md:273–296` proposed this inventory check.

A shim and its runtime entries can legitimately disappear when its pod completes or is replaced. This host is explicitly a live CI pool, and the earlier probe already reselects disappearing pods. R8 nevertheless requires every preflight shim PID and entry to survive every sample and rollback phase 3. Two immediate retries cannot restore a legitimately retired shim. Healthy churn can therefore force rollback or make successful cleanup permanently partial.

Track container/pod identity and process start time, reconcile exits against workload lifecycle, and reserve strict survival assertions for a known stable witness workload. A PID alone also permits reuse. Retain checks that Docker cleanup never targets k3s cgroups or directories, but do not equate every inventory deletion with Docker damage. The Fable suggestion needed this qualification before adoption.

### SHOULD-FIX 8 — R9 does not yet establish all of its admission and routing claims

Evidence: `design-rev4.md:260–281,587–597`; earlier Codex finding 7 in `review-round3-codex.txt`.

An empty supplementary-member list for group `docker` does not exclude users whose primary GID is docker, root-run services, privileged automation, or already-running processes retaining that group. The role itself and other factory services may run as root. Socket mode plus periodic container listing detects some violations but is not literally “admitted to nobody but the actor.” Establish the actual existing consumers and group credentials, require them quiescent, and state the trusted-root assumption. Unexpected-state-to-partial handling and explicit built-in network/veth identities are useful improvements.

The prior request for explicit non-overlap predicates remains unanswered. Before creating fixed `172.17.0.0/16`, check relevant address assignments, policy-routing tables/rules and advertised/reachable remote ranges, not only Docker networks or the main table. No new conflicting route is demonstrated here; the missing item is the preflight predicate that must refuse one.

### SHOULD-FIX 9 — Final rollback must recheck the complete safety predicate after writers stop

Evidence: `design-rev4.md:127–145,463–476`; R3's rechecking rule at `441–444` applies to restarted actors, not explicitly to the normal terminal path.

FORWARD policy is restored while dockerd can still be alive. A pending operation can change it again before phase 3 quiesces writers. Later phases check firewall residue, interfaces and sysctls, but do not expressly recheck both FORWARD policies before publishing `rolled-back`. Recheck all critical postconditions together at finalization: permissions, socket, processes, jobs, policies, owned rules, interfaces and shared-state differences. A failed kill or surviving writer must keep the outcome partial regardless of a momentarily empty ruleset. This was an explicit qualification in round-3 Codex note 10 and remains necessary.

### NOTE 10 — Companion changes, fallback access and representative acceptance are still gates, not results

Evidence: `design-rev4.md:283–319,378–383,599–607`.

The explicit companion implementation/review/merge gate is appropriate. So is requiring proof of the LAN fallback before Docker convergence. Neither that proof nor implementation or fault-injection results accompany this design. The earlier host-document corrections, including memory/capacity consistency, likewise are not evidenced as completed here.

The fallback is a useful additional access path, but both paths still depend on this host's underlay and health. “INPUT ... no step ... touches” is not a proof that neither route selection nor shared host failures can affect access. The design correctly retains the limitation that its VM uses stubbed k3s/LLM probes; shim inventories do not turn it into a representative coexistence test. Preserve that limitation and do not describe this review as authorization to converge.

## Verdicts on round-3 Codex findings

Verdicts assess design closure; they do not certify unprovided implementation or tests. Numbers refer to the final ranked list in `review-round3-codex.txt`.

1. **RESOLVED** — R1 makes the marker authoritative and finalization resumable; clarify publication failure and temporary permission overlap as finding 4 above.
2. **NOT RESOLVED** — R2 excludes overlapping actor processes, but controller allocation/configuration and terminal-run handoff remain unsynchronized (finding 3).
3. **NOT RESOLVED** — Unlimited restarts and watchdog configuration improve supervision, but READY/startup coverage and repeated hard-crash progress remain unspecified (findings 1–2).
4. **RESOLVED** — R6 holds the frontend lock, scopes configure recovery and provides host-side timer restoration; preserve the crash/recovery qualifications in finding 6.
5. **RESOLVED** — R5 replaces the nonexistent show property and R4 addresses queued jobs; make the scratch proof executable and assert effective conditions (finding 5).
6. **RESOLVED** — R8 uses nodes/status, a separately authorized endpoint source, sourced resync intervals and a fresh end-window challenge; verify these in implementation.
7. **NOT RESOLVED** — Network/interface identities and partial reporting improve, but exclusive consumers and route-collision predicates remain incomplete (finding 8).
8. **RESOLVED** — R7 publishes intended provenance before mutation, and R2 requires verified repair before a new run; explicit interrupted-package recovery still needs finding 6's qualification.
9. **NOT RESOLVED** — The companion changes and corrected host records are explicit gates, not supplied completion evidence (note 10).
10. **NOT RESOLVED** — Demonstrated firewall rule selection remains addressed, but the requested complete final post-quiescence rollback check is still absent (finding 9).
11. **RESOLVED** — Narrow shared-state claims and the stubbed-coexistence limitation are retained; the new fallback is an additional prerequisite, not proof of guaranteed recovery (note 10).

## Verdicts on round-3 Fable findings

Numbers refer to `review-round3-fable.md`'s ranked findings.

1. **NOT RESOLVED** — Start-rate exhaustion and catchable exceptions are addressed, but terminal restart semantics and repeated hard-crash progression still fail the broader recovery contract (findings 1–3).
2. **RESOLVED** — R5 adopts mechanism, assembled-unit and positive post-install checks instead of the invalid property; complete the scratch-root recipe (finding 5).
3. **RESOLVED** — R4 expressly excludes reconciler-owned chain contents and defines the comparison scope; expected Docker additions must remain separate from forbidden changes.
4. **RESOLVED** — R8 resolves the external address outside the pod namespace, sends SNI, and replaces GitHub's rate-limited endpoint; DNS is sent directly to cluster DNS.
5. **RESOLVED** — R7 writes intended provenance before package mutation; R1 separately fixes confirmation authority rather than relying on the earlier review's mistaken ordering description.
6. **RESOLVED** — One non-template actor unit plus a lifetime flock excludes concurrent actor instances; controller/run-allocation races are the separate remaining finding 3.
7. **RESOLVED** — R8 obtains the nested slice path from ControlGroup.
8. **NOT RESOLVED** — Shared-directory coexistence is still not tested; the adopted immutable shim inventory misclassifies normal churn (finding 7).
9. **RESOLVED** — R4 stops docker.socket immediately after revoking the temporary permission.
10. **RESOLVED** — Exact-token, per-table, both-family selection and whitespace normalization are retained; full final safety verification is separately required by finding 9.
11. **RESOLVED** — R6 adds archive SHA256/version verification, acknowledges dpkg triggers, and now actually holds the frontend lock; failure/recovery details remain in finding 6.
12. **RESOLVED** — R8 adds immediate re-probe and error recording; the new shim-survival false positive is separately finding 7.
13. **RESOLVED** — The governing text recognizes systemd 259, retains separate daemon readiness checks, and corrects namespace DNS; the earlier minor observations create no additional blocker.

REVIEW-COMPLETE: BLOCKERS
