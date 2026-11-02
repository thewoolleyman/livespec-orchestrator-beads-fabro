# Independent review, round 5 — Docker on gmktec-xubuntu (design revision 5)

Reviewed 2026-10-15 by a Fable reviewer with no part in the design. **One
BLOCKER; do not converge revision 5 on gmktec as written.** Revision 5's
shape — three short locked subcommands plus a repeating transient dead-man —
is sound, and it genuinely closes every round-4 blocker of both reviewers:
the lock protocol gives exactly one outcome, the repeating `OnUnitInactiveSec`
timer behaves as the design assumes (verified against the systemd v259
source the hosts run), and nothing long-lived has to stay healthy. What the
revision lost when it removed the actor is the actor's OTHER job: nothing in
revision 5 runs the observation window. No component is assigned to take the
15-second host-side samples, to trigger `rollback` when a sample fails, to
issue the end-of-window challenge that `confirm` requires, or to remove the
canary — and F9's acceptance list no longer contains the failed-probe case.
As written, a Docker start that breaks the pod network on the live CI node
is rolled back only when the dead-man expires, up to `N` = 1500 s later, and
`confirm` waits on a nonce that no one writes. The fix is the design's own
pattern (a second repeating transient timer), not new protocol. The remaining
findings are specification gaps and one inert backstop, ranked below.

Scope: design review, not implementation acceptance. Nothing on any host,
repository or ledger was changed; this requested file is the only file
written. Remote commands: one read-only ssh to gmktec (`systemctl --version`,
`systemctl show`, `systemctl is-active`, `ls`, `ip -br addr`). Local reads:
`systemd-run(1)` and `systemd.service(5)` man pages on the control node
(systemd 257). Upstream sources read at tag `v259` (the hosts' version):
`src/core/{timer,unit,job,service,manager,unit-dependency-atom}.c`,
`src/run/run.c`, `src/systemctl/systemctl-edit.c`, `src/shared/install.c`.
`design-rev5.md` line numbers refer to the file named in the brief.

## Facts measured this round that the findings rest on

- gmktec 2026-10-15: `systemd 259 (259.5-0ubuntu3.4)`; `docker.service`,
  `docker.socket`, `containerd.service` `LoadState=not-found`;
  `fabro.slice` and `fabro-sandbox.slice` loaded, inactive;
  `/run/docker-engine-guard`, `/var/lib/docker-engine-guard`,
  `/etc/systemd/system/docker.service.d`, `/etc/docker` absent; both apt
  timers, `k3s-agent`, `tailscaled`, `local-homelab-llama-server` active;
  interfaces `eno1` 192.168.1.156/24, `wlp195s0` 192.168.1.66/24,
  `tailscale0` 100.79.195.82/32, `flannel.1` 10.42.1.0/32, `cni0`
  10.42.1.1/24, seven `veth*`; no `docker0`. Unchanged from round 4.
- `systemd-run(1)` (local): `--service-type=` "Defaults to simple"; the
  `--on-*` options "are shortcuts for --timer-property= with the relevant
  properties"; `--collect`: "units that ran successfully are unloaded
  immediately", failed ones are kept without it. v259 `run.c:1449-1450`
  appends `Type=` only when `--service-type` is given; v259
  `service.c:867-874` then picks `SERVICE_SIMPLE` for a unit with
  `ExecStart=` and no `Type=`.
- `systemd.service(5)` (local): `Type=simple` — "the service manager will
  consider the unit started immediately after the main service process has
  been forked off"; `TimeoutStartSec=` — "Configures the time to wait for
  start-up"; `RuntimeMaxSec=` — "Configures a maximum time for the service
  to run ... does not have any effect on Type=oneshot services ... (use
  TimeoutStartSec= to limit their activation)". v259 `service.c:2558-2562`:
  `case SERVICE_SIMPLE: ... return service_enter_start_post(s)` immediately
  after fork.
- v259 `timer.c:490-495` (`timer_enter_waiting`): `case
  TIMER_UNIT_INACTIVE: leave_around = true; base =
  MAX(trigger->inactive_enter_timestamp.monotonic,
  t->last_trigger.monotonic); if (base <= 0) continue;` — an
  `OnUnitInactiveSec=` value is skipped until the service has run once, and
  the next elapse is measured from the LATER of the service's last
  deactivation and the timer's last trigger.
- v259 `unit.c:2740-2741`: `inactive_enter_timestamp` is stamped on entering
  ANY of inactive/failed (`UNIT_IS_INACTIVE_OR_FAILED(ns)`), so a firing
  that exits non-zero (lock wait timed out) still re-arms the timer.
- v259 `timer.c:115-128`: `timer_add_trigger_dependencies` adds
  `UNIT_TRIGGERS` with `add_reference=true`; `unit.c:3233-3236` then also
  adds `UNIT_REFERENCES`; `manager.c:1341-1349` (`unit_gc_sweep`) keeps a
  unit that is `UNIT_ATOM_REFERENCED_BY` a kept unit. So the transient
  dead-man SERVICE is not garbage-collected between firings while its
  timer exists (its fragment in `/run/systemd/transient/` would be unlinked
  on GC by `unit_remove_transient`, `unit.c:669-694`). Timer unit,
  `timer.c:619-659` (`timer_enter_running`): each elapse queues a
  `JOB_START` for the trigger and stamps `last_trigger`; a start job for an
  already-active service is a no-op.
- v259 `job.c:786-791`: for a unit whose failed condition is a `|` trigger
  condition, the journal line is `"%s was skipped because no trigger
  condition checks were met."` with `%s` = `unit_status_string` (the
  Description, or the name); logged via `log_unit_struct` at the
  `JOB_DONE` level (INFO) with `JOB_ID`, `JOB_TYPE`, `JOB_RESULT` fields;
  it is suppressed only when `log_on_console()` (`job.c:764-772`). F5.3's
  expected text matches.
- v259 `systemctl-edit.c:38-62` (`verb_cat`): `lookup_paths_init_or_warn(&lp,
  arg_runtime_scope, 0, arg_root)` then client-side name mangling when
  `--root` is set; `cat --root` works on 259 (the control node's 257
  refuses it, round 4).
- v259 `install.c:1160-1162` + `398-400`: enable/disable on a unit whose
  file is under the transient path returns `-EADDRNOTAVAIL`, rendered "Unit
  ... is transient or generated".

## Ranked findings

### BLOCKER 1 — Nothing in revision 5 runs the observation window: no sampler, no rollback trigger on a failed probe, no challenge issuer, no canary teardown; F9 drops the failed-probe acceptance case

Evidence: `design-rev5.md:624-655` (F1: the subcommands are `start`,
`confirm`, `rollback`; `start` ends after `docker.service` is up; `confirm`
"refuse[s] unless the current challenge for `<run>` carries `<nonce>` and is
younger than 120 seconds"); `657-669` (the dead-man runs ONLY `rollback`,
first "at the deadline"); `609-620` ("the probes (R8) ... stand" — but R8's
probes were executed by the actor: `105-114` canary and observing phases,
`164-166` "continuously during the observation window", `573-579` "at the
END of the window the actor writes a challenge"); `671-677` (the closure
argument covers restart, watchdog, crash and serialization — not
observation); `786-794` (F9: no "fail a probe during the window" case, which
revision 3's acceptance at `298-303` had); `679-691` (F2 adds `reserve` and
`verify`, so F1's "three subcommands" is already five, with no `sample`,
`challenge` or `canary` among them).

Revision 5 removed the actor and reassigned its decision-making to the lock
protocol, but the actor also DID things between `start` and `confirm`: it
ran the canary, sampled the five host-side probes every 15 seconds for `W`
seconds, rolled back immediately on a twice-failed sample, issued the nonce
challenge at the end of the window, and stopped the canary before
confirmation. None of those is assigned to any component in F1-F9. Three
consequences:

1. **A failed probe no longer triggers rollback.** The only automatic
   rollback trigger is the dead-man at `N` = 1500 s. If Docker's first start
   breaks the pod network (the exact fault the window exists to catch),
   revision 4 rolled back within ~30 s of the first failed sample; revision
   5 as written rolls back when the deadline expires — up to 25 minutes of
   a broken CI node — unless the controller happens to call `rollback`,
   which the design never instructs it to do.
2. **`confirm` depends on a challenge nobody writes.** If the implementer
   makes the Ansible controller write it, the nonce proves only that the
   controller wrote a file less than 120 s before it called `confirm`, and
   the three controller-side probes (a fresh Tailscale SSH session, the LLM
   `/health`, a LAN login through poweredge) must all complete inside that
   120 s (round-4 Fable NOTE 11, unchanged).
3. **If the controller is the sampler**, liveness of the window once again
   depends on a process staying connected across the very host under test —
   the dependency F1 says it removed ("No process needs to stay alive for
   any of this") — and a cut-off controller degrades to case 1.

Required: assign the window to a host-side party with the design's own
pattern. A second repeating transient timer, e.g.
`systemd-run --unit=docker-engine-sampler-<run> --on-active=15
--on-unit-inactive=15 --property=RuntimeMaxSec=60 docker-engine-guard sample
<run>`, armed by the role after `start` returns: `sample` (same lock, or
lockless for reads) runs the five probes plus the R9 admission checks, calls
`rollback <run>` on a twice-failed sample, writes the challenge once the
window has closed, and refuses once `rollback-started`, `rolled-back` or
`confirmed` exists; `confirm` stops both timers; `rollback` stops the
sampler. State that the controller ALSO calls `rollback <run>` immediately
on any failure it sees (failed `start`, failed controller probe), so the
dead-man is the backstop and not the primary trigger. Put the canary under
`start` (or a `canary <run>` subcommand) and its teardown under `confirm`.
Restore the acceptance cases: a probe fails during the window (rollback
within two sample periods, not at `N`); the controller is cut off during
the window (rollback by the sampler, not the deadline); the sampler itself
hangs (its `RuntimeMaxSec` fires and the next firing resumes). Allow the
sampler to re-issue one challenge within `N` so a slow Tailscale handshake
is not a full rollback.

### SHOULD-FIX 2 — The dead-man's per-firing bound is inert: `systemd-run` defaults the service to `Type=simple`, whose start completes at `fork()`, so `TimeoutStartSec=600` never fires

Evidence: `design-rev5.md:657-661` (`systemd-run --unit=... --on-active=<N>
--on-unit-inactive=60 ... --property=TimeoutStartSec=600 docker-engine-guard
rollback <run>` with no `--service-type`); `664-666` ("a step that hangs
(killed by its own `timeout`) ... a rollback killed half way is simply
repeated a minute later"); local `systemd-run(1)` (`--service-type`
"Defaults to simple"); v259 `run.c:1449`, `service.c:867-874`,
`service.c:2558-2562`; local `systemd.service(5)` `TimeoutStartSec=` and
`RuntimeMaxSec=`.

The design's liveness argument is "the timer firing again", and the timer
fires again only after the previous firing becomes inactive
(`timer.c:492`). The per-step `timeout` wrappers bound the steps; the
manager-side `TimeoutStartSec=600` was meant to bound the firing as a
whole. For a `Type=simple` service start-up is complete the instant the
process is forked, so that property can never expire, and nothing bounds a
firing that stalls OUTSIDE a wrapped step: the 60-second lock wait is
script-enforced, the final postcondition re-check (`649-653`) is not stated
to be wrapped, a SIGSTOP of the firing (round-4 Codex demanded exactly this
case for the actor) freezes it, and `timeout` without `-k` lets a step that
ignores SIGTERM run on. In each case the firing never ends, the dead-man
never re-fires, no outcome is recorded, and the reservation is held with
`rollback-started` present. The mutating steps run first and are wrapped,
so this is a silent stall with partial cleanup rather than a lockout —
which is why it is not the blocker — but it is a one-token fix:
`--property=RuntimeMaxSec=600` (bounds a `simple` service and kills the
whole cgroup, including a stopped process) or `--service-type=oneshot`
(where `TimeoutStartSec` does bound the run). Use `timeout -k` on every
step, wrap the postcondition re-check too, open the lock fd `O_CLOEXEC`
(Python's default) so a `timeout`-wrapped child cannot inherit the flock,
and add "SIGSTOP a firing: the next firing runs within `RuntimeMaxSec` +
60 s" to F9.

### SHOULD-FIX 3 — A reservation held by a run with no outcome is never reclaimed, and the design creates that state on three ordinary paths

Evidence: `design-rev5.md:681-688` (F2: `reserve` succeeds only over an
absent run or one whose outcome is `rolled-back` or `confirmed`; "The role's
FIRST action on the host is `reserve`"); `695-701` (F3: after a reboot "the
transient dead-man does not survive the reboot and does not need to");
`657-659` (the dead-man is armed "BEFORE `start`"); `247-258` (Mechanism 6:
`confirmed` present → "validate only ... no-op").

A run reaches "reserved, no outcome, no dead-man" on three paths the design
itself describes, and F2 gives no rule for leaving it:

1. **A reboot before the commit point** (or during a rollback, with
   `rollback-started` written): the host is clean by Mechanism 1, but the
   run's outcome is never written, so the next converge's `reserve` refuses
   and prints the holder.
2. **A role run that reserves and then fails before arming the dead-man**
   (the F5 probe, the audit, the fence, `dpkg -i` or the post-install
   checks refuse): no timer, no outcome, reservation held.
3. **Every converge after `confirmed`**: the role's first action reserves a
   NEW run (the previous outcome is `confirmed`, so `reserve` succeeds),
   then Mechanism 6's validate-only path writes no outcome for it. The
   SECOND converge after confirmation therefore refuses at `reserve`, and
   every converge after that, which breaks the committed play order (the
   slice role's daemon-dependent half, `otel_receiver`, `fabro_server`
   follow `docker_engine`).

Required: define reclamation. Under the lock, a reservation whose run has
no outcome, no armed dead-man timer and no `allow-start` is reclaimable by
running `rollback <run>` first (idempotent; after a reboot every
postcondition except "units disabled" already holds, and `rollback`
disables them), after which `reserve` for the new run proceeds; a run WITH
an armed dead-man is live and `reserve` refuses. A validate-only converge
either does not reserve or records a `validated` outcome that `reserve`
accepts. Add "reboot mid-rollback, then converge" and "converge twice after
`confirmed`" to F9.

### SHOULD-FIX 4 — `confirm` never enables the three units, so a confirmed run that followed a rolled-back one leaves Docker disabled at boot

Evidence: `design-rev5.md:633-637` (`confirm`: publish `confirmed`, stop
the timer, remove `allow-start` — no `enable`); `646-648` (`rollback`:
"disable the three units (the postinst enabled them)"); `699-701` (F3: the
units "stay enabled ... until a later run's rollback disables them");
`116-118` (revision 3's confirm phase did "enable the three units", now
superseded by F1 per `614-616`); `247-251` (Mechanism 6 resume row: "start a
new actor run" after an incomplete earlier run).

Sequence: run 1 rolls back (units disabled); run 2 resumes the inert
install and confirms; `confirmed` exists and Docker is running, but
`docker.service`, `docker.socket` and `containerd.service` are disabled.
At the next reboot the factory does not come back, `confirmed` says it
should, and Mechanism 6's validate-only path has no row for "confirmed but
disabled". Add `systemctl enable` of the three units to `confirm`'s
idempotent post-commit steps, and have the validate-only path assert
`UnitFileState=enabled` on all three.

### SHOULD-FIX 5 — `start` refuses on `rolled-back` and `confirmed` only; a run whose rollback has started or ended `rollback-partial` can be started again, and the still-armed dead-man then rolls it back a minute later

Evidence: `design-rev5.md:629-632` (`start` refuses unless "`rolled-back`
and `confirmed` are both absent for it, and the dead-man timer for `<run>` is
armed"); `639-641` (`rollback` writes `rollback-started` first and "from then
on `confirm` refuses"); `666-668` ("a `rollback-partial` outcome keeps
retrying"); `689-691` (a `rollback-partial` run keeps the reservation).

After a `rollback-partial`, the reservation still names the run, the
dead-man is still firing every 60 s, `rolled-back` is absent and
`confirmed` is absent — so `start <run>` is admissible. A re-run of the
role for the same run id (the obvious operator move) creates `allow-start`
and starts Docker on a partially cleaned host; the next dead-man firing
removes the permission and kills it; `confirm` can never succeed because
`rollback-started` exists. The host flaps once a minute until someone reads
the journal. Make `start` refuse when `rollback-started` exists for the run
(the same marker `confirm` keys on), and say explicitly that a
`rollback-partial` run is re-entered only through the operator repair and
`verify` path.

### SHOULD-FIX 6 — The dead-man is stopped only by `confirm`; after `rolled-back` it fires forever, `disable` of a transient timer is an error, and a `rollback-partial` whose failed postcondition no step can establish retries to no effect

Evidence: `design-rev5.md:661-663` ("It fires at the deadline and then
again every 60 seconds after each run finishes, forever, until `confirm`
stops it"); `665-668` ("A `rolled-back` outcome makes later firings
no-ops; a `rollback-partial` outcome keeps retrying"); `636` (`confirm`:
"stop and disable the dead-man timer"); `648-649` ("compare sysctls" — a
compare-only step, as in `140-143`: "shared state is not written back
blindly"); v259 `install.c:1160-1162,398-400`.

(a) On every rolled-back run — the normal failure outcome — and on a
`confirm` that crashed after the commit point and was never repeated, the
timer keeps starting a root process every 60 s until the next reboot. Have
`rollback` stop its own timer (`systemctl stop --no-block
docker-engine-deadman-<run>.timer`; stopping the timer does not stop the
running service) when it records `rolled-back`, and `verify` likewise. Also
state outright what `665` implies: `rollback <run>` exits 0 without acting
when `rolled-back` exists for `<run>` — that rule is what makes a stale
timer from an earlier run harmless to a later one, because every mutating
step acts on GLOBAL state (`allow-start`, the three units, the rules,
`docker0`), not on anything run-scoped.

(b) `systemctl disable` on a transient unit returns `-EADDRNOTAVAIL` ("Unit
... is transient or generated"). If `confirm` treats that as a failure, its
post-commit steps never finish cleanly. `stop` (plus `reset-failed` on the
service if its last firing exited non-zero) is the whole of it.

(c) Under `rollback-partial`, every firing re-runs `systemctl kill
--signal=SIGKILL` on `fabro-sandbox.slice`, re-takes the xtables lock for
the `-P`/`-D` passes and re-attempts `ip link del`, once a minute, for as
long as the host is up. When the only failed postcondition is one the
rollback never writes (a sysctl difference, by design compare-only), no
firing can ever succeed. Stop the timer when the failed-postcondition set
contains only compare-only items, and leave the reservation for `verify`.

### SHOULD-FIX 7 — The snapshot the dead-man compares against has no stated home, and `start` does not require it

Evidence: `design-rev5.md:645-653` (`rollback` restores "each family's
FORWARD policy", removes "Docker's rule footprint", compares sysctls "as
snapshotted"); `202-211` (Mechanism 4: the footprint is "present now and
absent from the snapshot"); `184-190` (Mechanism 3 snapshot at preflight);
`629-632` (`start`'s preconditions).

Every rollback firing runs under the system manager with no controller
present, so the preflight snapshot (`iptables-save`/`ip6tables-save` per
table without counters, both FORWARD policies, the five sysctls, the k3s
containerd PID of F8) must be a host file written before the dead-man is
armed — `/var/lib/docker-engine-guard/<run>/snapshot.json` or similar — and
`start` must refuse unless it exists and is complete. Without it the
firewall step cannot compute the footprint, and the postcondition check
would either fail (permanent `rollback-partial`) or, worse, be skipped.
`verify <run>` reads the same file. Also note that `verify` is described as
read-only and as marking the run `rolled-back` (`690-691`): say it writes
exactly that one outcome.

### NOTE 8 — The repeating dead-man is mechanically sound on v259; two behaviours to write down

Evidence: v259 `timer.c:490-495`, `unit.c:2740-2741`, `timer.c:115-128`,
`unit.c:3233-3236`, `manager.c:1341-1349`, `timer.c:619-659` (facts above);
`design-rev5.md:657-669`.

Verified: `--on-active=<N>` fires once at `N` from arming;
`--on-unit-inactive=60` is skipped until the service has run (`base <= 0`),
so there is no early firing before `N`; a firing that exits non-zero (lock
wait timed out) still counts as a deactivation; the service unit is pinned
by the timer's `References=` edge and is not unloaded between firings; the
transient timer does not survive a reboot. Two things to state: (a) the
next elapse is `MAX(last deactivation, last trigger) + 60 s`, so a firing
that runs longer than 60 s sees a redundant elapse while active (a no-op
start job, harmless) — with `RuntimeMaxSec=600` per SHOULD-FIX 2 that is
the normal case for a full rollback; (b) a `confirm` that stops the timer
while a firing is waiting on the lock does not stop that firing, which then
takes the lock, finds `confirmed` and exits 0 — the designed interplay,
and the reason `confirm` must not also `kill` the service.

### NOTE 9 — F5's instruments now return hits; run F5.2 on a 259 host, and prefer the structured fields for F5.3

Evidence: v259 `systemctl-edit.c:38-62`; v259 `job.c:764-796`;
`design-rev5.md:726-738`.

`systemctl --root=<scratch> cat` is client-side on 259 and prints fragment
and drop-in paths; the control node's 257 refuses the verb with `--root`, so
the check runs on the target host. The F5.3 string is the one 259 writes for
a unit whose only conditions are `|` triggers, and it is journaled at INFO
with `JOB_TYPE=start JOB_RESULT=done` and the unit's `UNIT=` field; matching
on those fields plus `ConditionResult=no` and an empty
`ExecMainStartTimestamp` is more robust than the prose, whose `%s` is the
unit's Description rather than its name.

### NOTE 10 — F6: say where `dpkg -i` runs, and the socket-stop ordering caution still applies

Evidence: `design-rev5.md:742-747` ("If it expires during the install,
`dpkg` still holds `/var/lib/dpkg/lock` itself" — true only if dpkg is NOT a
child of the helper unit, since `RuntimeMaxSec` expiry kills the unit's
whole cgroup); `644-646` (rollback stops `docker.socket` under a step
`timeout`); round-4 Fable NOTE 10(a).

State that `dpkg -i` runs in the controller's SSH task (as the sentence
implies), that an SSH death mid-transaction is exactly F6's interrupted-
install recovery branch, and that the helper's `RuntimeMaxSec` exceeds the
worst-case install. For the socket stop: `docker.service` has
`Requires=docker.socket` and `TimeoutSec=0`, so a blocking `systemctl stop
docker.socket` waits for a hung `dockerd` until the later SIGKILL; the step's
`timeout` now bounds the CLIENT, but the stop job stays queued and the step
burns its whole budget — `--no-block` keeps the FORWARD-policy step from
waiting behind it.

### NOTE 11 — Small accuracy items

- `design-rev5.md:624-625` "ONE executable with three subcommands": there
  are five (`start`, `confirm`, `rollback`, `reserve`, `verify`), six with
  the sampler of BLOCKER 1.
- `/run/docker-engine-guard` is absent after every reboot (measured absent
  today); each subcommand must create it before taking the lock, or the
  first post-boot `rollback`/`reserve` fails on the lock path.
- F7's "refuse if any account has `docker` as its primary group": the group
  does not exist before the install (round 4), so the check runs after
  `dpkg -i` and before `start`, not "before `reserve`" as `762-763` says.
- F4's "both permissions exist briefly" supersedes R1's "at most one"
  (`385-390`); say so where R1 is, since R1 is listed as standing.

## Verdict per round-4 finding — Fable reviewer

(The brief's output section says "per round-3 finding"; the launch
instruction says round 4, and round 3's verdicts were rendered in round 4,
so these are the round-4 findings.)

1. **RESOLVED (moot)** — there is no long-lived unit to respawn; the
   residual is the dead-man firing no-ops every 60 s after `rolled-back` or
   an interrupted `confirm` until reboot (SHOULD-FIX 6a), harmless by
   comparison.
2. **RESOLVED (moot)** — no watchdog or `READY=1` is needed; the residual is
   that the one manager-side bound the design does specify is inert for a
   `Type=simple` service (SHOULD-FIX 2).
3. **RESOLVED** — F5.2 uses `systemctl --root cat`, verified client-side on
   v259; F5.3 expects the trigger-condition skip text, verified at
   `job.c:790` (NOTE 9).
4. **RESOLVED** — `rollback` cancels only jobs whose unit is one of the
   three, read from `list-jobs` and cancelled by id (`643-645`).
5. **RESOLVED** — no `--recover`; a forward phase is entered only by
   `start`, which requires the reservation and an armed dead-man, so a boot
   can never enter one; `reserve` is under the same lock (F2). The
   reclamation of a held reservation is new (SHOULD-FIX 3).
6. **RESOLVED** — F4 digests the role-owned keys parsed and canonicalized
   and adds the post-commit reconfiguration row.
7. **RESOLVED** — F6 runs the helper as a transient unit with
   `RuntimeMaxSec`, restores the apt timers at the outcome with a
   worst-case-plus-30-minute backstop.
8. **RESOLVED** — F5.1 gives the probe its own permission path and asserts
   both paths absent immediately before `dpkg -i`.
9. **RESOLVED** — F6 states there is no unit-directory trigger and runs an
   explicit `daemon-reload`.
10. **RESOLVED** — the slice kill is retained; each step is under
    `timeout`, so the socket-stop block is bounded (NOTE 10 keeps the
    `--no-block` advice); `RuntimeDirectory` is moot with no long-lived
    unit.
11. **NOT RESOLVED** — F7 reads `config.yaml` and re-reads CoreDNS
    placement, but the 120-second challenge window is unchanged and the
    challenge now has no issuer at all (BLOCKER 1).
12. **RESOLVED** — F4 states the overlap and why it is safe.
13. **RESOLVED** — F3 states the enabled-but-skipped units; `rollback`
    disables them. The mirror gap, `confirm` not enabling them, is new
    (SHOULD-FIX 4).

## Verdict per round-4 finding — Codex reviewer

1. **RESOLVED (moot)** — no notify service, no watchdog; liveness is the
   timer re-firing, verified on v259. Residual: SHOULD-FIX 2.
2. **RESOLVED** — every firing attempts every step from the top, each under
   its own `timeout`, and a half-finished firing is repeated a minute
   later; the "repeat forever" is now by stated design for
   `rollback-partial` (SHOULD-FIX 6c narrows it).
3. **RESOLVED** — F2 reserves the run under the same lock before any
   configuration is written; a second controller fails at `reserve`.
   Residual: SHOULD-FIX 3 (no reclaim rule) and SHOULD-FIX 5 (`start`
   admissible after `rollback-started`).
4. **RESOLVED** — F4 defines the rename as the commit point, treats a
   failed directory fsync as a durability warning never followed by
   rollback, and documents the permission overlap.
5. **RESOLVED** — F5.2 drops `systemd-analyze verify` for `systemctl --root
   cat` and asserts both condition lines with exact paths; F5.1 isolates
   the test permission.
6. **RESOLVED** — F6 supervises the lock holder as a transient unit with a
   lifetime, separates the fresh-transaction and interrupted-install
   branches, digest-checks `dpkg.cfg` and `dpkg.cfg.d`. Residual: NOTE 10
   (where dpkg runs).
7. **RESOLVED** — F8 drops shim survival for the k3s containerd PID, the
   two `/run/containerd` directories and Node Ready.
8. **RESOLVED** — F7 adds the primary-group check, the root-service trust
   statement, and the `172.17.0.0/16` overlap predicate over all tables and
   the cluster/tailnet ranges. (Timing nit in NOTE 11.)
9. **RESOLVED** — `rollback` re-checks all postconditions together after
   every writer is stopped and writes `rolled-back` only if all hold
   (`649-655`).
10. **NOT RESOLVED** — the companion carrier, the LAN fallback proof and
    the host-record correction remain gates by the design's own statement
    (`599-607`, `794`); unchanged in revision 5, and correctly so.

REVIEW-COMPLETE: BLOCKERS
