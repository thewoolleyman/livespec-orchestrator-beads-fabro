# Independent review, round 6 — Docker on gmktec-xubuntu (design revision 6)

Reviewed 2026-10-15 by a Fable reviewer with no part in the design. **No
BLOCKER.** Revision 6 closes every round-5 blocker of both reviewers with
mechanisms I could verify against the systemd 259 source the hosts run:
every lock holder is a `Type=oneshot` transient unit whose `TimeoutStartSec`
genuinely bounds it (G1), the run has one forward-only phase machine with
the deadline and boot id checked under the lock at every decision (G2), all
in-place writes go through the locked `publish`/`reconfigure` helper (G3),
the observation window has an owner that triggers rollback on a failed
sample and issues the challenge (G4), and the rollback driver cannot be
pinned behind one crashing phase (G5). What remains is seven specification
gaps, each of which an implementer following the text literally would
build wrong, and none of which produces a lockout or an unbounded Docker
exposure on its own. The most important two are structural: revision 6
makes EVERY converge reserve a new run, which leaves the committed Docker
protected only by convention once a second run exists, and the one
precondition that made `start` safe in revision 5 — "the dead-man is
armed" — is no longer in `start`'s restated precondition list and no
section says who arms it.

Scope: design review, not implementation acceptance. Nothing on any host,
repository or ledger was changed; this requested file is the only file
written (plus the fetched systemd sources in my scratchpad). Remote reads:
gmktec (`systemctl --version`, `systemctl show`, `ls`, `cat
/proc/sys/kernel/random/boot_id`), hp (`systemctl cat`, `systemctl show`,
`ls`, `cat` of two drop-ins). Local reads: `systemd.service(5)`,
`systemd-run(1)`, `systemd.kill(5)`, `systemd.unit(5)`, `systemd.timer(5)`
on the control node (systemd 257), `busctl get-property` on the local
manager, and the v259 sources `src/core/service.c`,
`src/shared/bus-unit-util.c`, `src/run/run.c`,
`src/systemctl/systemctl-show.c`. `design-rev6.md` line numbers refer to
the file named in the brief.

## Facts measured this round

- gmktec: `systemd 259 (259.5-0ubuntu3.4)`; `/run/docker-engine-guard` and
  `/var/lib/docker-engine-guard` absent; the three Docker units
  `LoadState=not-found`; `DefaultTimeoutStartUSec=1min 30s`,
  `DefaultTimeoutStopUSec=1min 30s`.
- gmktec AND hp, systemd 259: `systemctl show -p Conditions
  systemd-binfmt.service` (a unit with five `|` trigger conditions) prints
  `Conditions=[unprintable]`; the same for `docker.service` on hp. The
  local 257 does the same. `busctl get-property org.freedesktop.systemd1
  /org/freedesktop/systemd1/unit/systemd_2dbinfmt_2eservice
  org.freedesktop.systemd1.Unit Conditions` (local) prints `a(sbbsi) 6
  "ConditionDirectoryNotEmpty" true false "/run/binfmt.d" 0 ...` — type,
  trigger flag, negate flag, parameter, tristate — with the tristate `0`
  on every condition of an ACTIVE unit whose `ConditionResult=yes`.
  v259 `systemctl-show.c:2228` maps `Conditions` only for the `status`
  renderer (`map_conditions`), not for `show`.
- hp: `/etc/systemd/system/docker.service.d/10-requires-sandbox-storage.conf`
  and `/etc/systemd/system/containerd.service.d/10-requires-sandbox-storage.conf`,
  both "Managed by Ansible (role: sandbox_storage)", each one line of
  `[Unit] RequiresMountsFor=/var/lib/docker` (resp. `/var/lib/containerd`).
  No `docker.socket.d`. hp's `docker.service`: `Type=notify`,
  `Requires=docker.socket`, `Wants=containerd.service`, `TimeoutSec=0`,
  `Restart=always`, `KillMode=process`; `containerd.service` the same
  shape; both `UnitFileState=enabled`.
- v259 `bus-unit-util.c:2574,2614`: `"Type"` is a settable transient
  service property (`bus_append_string`), so `--property=Type=oneshot` is
  accepted exactly as `--service-type=oneshot` is (`run.c:1449-1450`).
- v259 `service.c:4491-4497`: a `SERVICE_START` timeout with the default
  `TimeoutStartFailureMode=terminate` calls
  `service_enter_signal(SERVICE_STOP_SIGTERM, SERVICE_FAILURE_TIMEOUT)`;
  `service_enter_signal` (`service.c:2277ff`) kills the whole context per
  `KillMode` and arms `timeout_stop_usec`; on its expiry
  (`service.c:4547-4561`) `SendSIGKILL=yes` sends SIGKILL to the remaining
  control group. A SIGSTOP'd main process dies at that SIGKILL. So G1's
  "budget plus 30 s" bound holds for a oneshot.
- `systemd.service(5)` (local): `TimeoutStartSec=` "Defaults to
  DefaultTimeoutStartSec= ... except when Type=oneshot is used, in which
  case the timeout is disabled by default"; `RuntimeMaxSec=` "does not have
  any effect on Type=oneshot services ... (use TimeoutStartSec= to limit
  their activation)". `systemd-run(1)`: `--collect` "unloads units
  regardless if they exited successfully or failed" and `CollectMode=`
  notes unit results are then "flushed out immediately after the unit
  completed, except for what is stored in the logging subsystem".

## Ranked findings

### SHOULD-FIX 1 — Every converge after confirmation reserves a new run, which releases the confirmed run, breaks `reconfigure`'s own precondition, and leaves the committed Docker protected only by the convention that a later run's `rollback` "only releases the reservation"

Evidence: `design-rev6.md:866-873` (G3: `reserve` refuses unless the
current run is `rolled-back`, `confirmed` or `released`; a controller that
finds any other phase ATTACHES and runs `rollback <run>`; "rollback on
[a reserved run] only releases the reservation (nothing was started)"; "A
`confirmed` run is `released` by the next `reserve`, so every later
converge after a confirmation reserves normally"); `864-865` (G3:
`reconfigure <run>` "requires the run to be the current, `confirmed` one");
`679-688` (F2: "The role's FIRST action on the host is `reserve`");
`247-256` (Mechanism 6: `confirmed` present → "validate only"); `712-717`
(F4: a later converge with a different owned-keys digest is "a post-commit
reconfiguration ... never a guarded transition"); `833-835` (G2: rollback
is "never [reachable] from `committed` or `confirmed`"); rev5 `638-639`
(`rollback` is a no-op only when `confirmed` names THIS run).

Three consequences follow from "every converge reserves":

1. **`reconfigure` can never run.** The converge's first act reserves R2,
   which marks R1 `released`; `reconfigure` then requires "the current,
   `confirmed`" run, and R1 is neither current nor (by phase) `confirmed`.
   F4's post-commit reconfiguration path has no executable entry.
2. **Every validate-only converge leaves a `reserved` run** that the NEXT
   converge must attach to and roll back before it can reserve — a
   rollback invoked on a host where the committed Docker is live. G3 says
   that rollback "only releases the reservation", so it is specified, but
   the safety of production Docker now rests on `rollback` branching on
   the run's phase before touching any of its GLOBAL steps (`allow-start`,
   the socket, the kill, the rules, `docker0`, the enablement). The
   marker check in rev5 F1 does not help: `confirmed` names R1, and the
   run being rolled back is R2.
3. **There is no host-side guard against a forward run on a confirmed
   host.** `publish R2` requires only `reserved` and currency; `start R2`
   only `published`. A controller that misclassifies (Mechanism 6 is
   controller-side) can `publish`, `start`, `observe` and — on any failed
   sample — `rollback R2`, whose phase 3 kills `docker.service`,
   `containerd.service` and `fabro-sandbox.slice`, phase 6 disables the
   units and phase 4 strips the rules: the committed Docker is torn down
   by a run that was never committed, and G2's "never from committed"
   invariant is true of R2 and irrelevant to the host.

Required: do not reserve on a confirmed host. Make the controller classify
first (read the `confirmed` marker through a read-only `status`
subcommand) and `reserve` only in the fresh-install and resume rows; make
`reserve` itself REFUSE while a `confirmed` marker exists, so the
`reserved → published → started` path is unreachable after the commit
point by construction; route post-commit changes through `reconfigure`
keyed on the run the MARKER names, not on the reservation. If a reserve
after confirmation is kept for some reason, then `publish` and `start`
must refuse while the marker exists, and the rollback driver must run its
global phases only for a run whose phase is `started` or later. Add to G8:
"converge twice after `confirmed` (validate-only both times, no rollback
invoked, Docker never stopped)".

### SHOULD-FIX 2 — `start`'s restated preconditions no longer include an armed dead-man, and revision 6 never says who arms it or when; a `start` on a run with no timer is Docker with no host-side bound

Evidence: `design-rev6.md:837-840` (G2: "`start` requires exactly
`published` and an unexpired deadline on the same boot"); `889-891` (G4:
"The deadline `N` is set at `reserve`" — set, not armed); `800-801` ("Where
this section and an earlier one disagree, this section governs"); rev5
`629-632` (F1 `start`: "refuse unless ... the dead-man timer for `<run>` is
armed"); rev5 `657-660` (the dead-man is "armed by the role BEFORE
`start`"); `886-889` (G4: "If the controller dies at any point, nothing
else is needed: the dead-man rolls the run back at the deadline" — which
presumes it is armed).

Revision 5 had the one precondition that makes `start` safe without a
live controller; revision 6's `start` paragraph lists its preconditions
with the word "exactly" and omits it, and no section of revision 6 names
the arming step at all. Read literally, an implementer builds `start`
without the check and the role arms the timer at some point the design
does not fix. A controller that reaches `start` without arming (ordering
slip, a retry that skipped the arming task, an SSH drop between the two
tasks) leaves Docker running on the live CI node with no dead-man;
Mechanism 1 bounds that only at the next reboot or the next converge's
attach. That is the exposure the whole design exists to bound, so the
precondition must be explicit, and the arming should not be a controller
step at all.

Required: have `reserve` arm the dead-man itself, under the lock, with
`--on-active=<deadline - now>` computed from the absolute deadline it
records, so that no run can exist without its timer; state that `start`
refuses unless `docker-engine-deadman-<run>.timer` is `ActiveState=active`
with a `NextElapseUSecMonotonic` in the future (a read through `systemctl
show`, which works for these properties). A dead-man armed at `reserve`
also retires the "reserved run with no outcome" state of round-5 Fable
SHOULD-FIX 3 on its own: a converge that reserves and then fails is
rolled back (released) at `N` with no attach needed.

### SHOULD-FIX 3 — The package transaction has no place in G2's lifecycle, `publish`'s 120-second budget cannot contain it, and the lock-holding helper is specified with two incompatible bounds

Evidence: `design-rev6.md:833` (G2's phases: `reserved → published →
started → ...`, nothing between `published` and `started` and nothing in
`publish` about packages); `858-863` (G3 `publish`: "takes the snapshot,
installs the inputs into place, and moves the run to `published`");
`820` (G1: `publish` 120 s); `921-924` (G7: "`dpkg -i` runs inside the
lock-holding helper's transient unit on the host (G1), never from the
controller's session"; "If the helper is killed during the install, the
recovery branch (F6) runs on the next `publish`/`start` attempt for that
run and only for this run's packages"); `742-747` (F6: the helper is
`systemd-run --wait --collect --property=RuntimeMaxSec=...`); `803-812`
(G1: every guard operation is `Type=oneshot` with `TimeoutStartSec`);
`538-543` (R7's `installing` / `installed-inert` states); local
`systemd.service(5)` `RuntimeMaxSec=` "does not have any effect on
Type=oneshot services". Mechanism 1 (`46-73`) requires the drop-ins to be
in place BEFORE the install, and F5/G6 run checks before and after it.

Four gaps, one subject:

1. **Where the install sits is undecidable from the text.** The drop-ins
   are installed into place by `publish`; `start` requires `published`;
   so `dpkg -i` is either inside `publish` or between `publish` and
   `start`. If inside, `publish` holds the guard lock AND the dpkg
   frontend lock across the F5.1 probe, the G6 scratch-root check, the
   audit, the unpack of three packages, `daemon-reload` and the G6
   post-install checks within 120 s, 60 of which may be the lock wait. If
   between, the biggest shared write of the whole design is launched by
   the controller outside the phase machine, contrary to G3's own
   principle, and a delayed controller of an older run can launch it.
2. **The helper's bound.** G7 says the helper has G1's shape (oneshot,
   `TimeoutStartSec`); F6 bounds it with `RuntimeMaxSec`, which does
   nothing on a oneshot. One of them is wrong; say which, and state the
   budget exceeds the worst-case install.
3. **`reserved` conflates "nothing happened" with "install
   interrupted".** G3's attach rule rolls back a `reserved` run by
   "only releas[ing] the reservation (nothing was started)". A `publish`
   killed by its budget (or a reboot) mid-`dpkg -i` is also a `reserved`
   run, with packages half-installed and drop-ins in place. R7's
   `installing` / `installed-inert` states exist for this and G2 drops
   them.
4. **Recovery keyed to the run id strands the host.** G7 restricts the
   interrupted-install recovery to "this run's packages", but the attach
   path releases the interrupted run and reserves a NEW one, whose
   `publish` then meets pending packages that belong to no current run
   and "anything else pending refuses". Key the recovery to the committed
   allowlist (package, version, SHA256), which is identical across runs,
   not to the run id.

Required: put the transaction inside the phase machine (`reserved →
published → installed → started`, with `install <run>` a locked oneshot
whose budget is the install budget, holding the dpkg frontend lock inside
it), give `publish` only the snapshot and the in-place inputs, and make
the attach rule's `rollback` run the F6 recovery branch for an
`installing` run before releasing it.

### SHOULD-FIX 4 — The attach rule rolls back ANY non-terminal run without a liveness test, so a concurrent converge destroys a healthy in-flight transition — and contradicts F9's "second controller ... refused"

Evidence: `design-rev6.md:866-870` (G3: "A controller that finds a run in
any other phase ATTACHES to it: it runs `rollback <run>` (for any
pre-commit phase)"); `791-792` (F9: "start a second controller while a run
is reserved (refused)"); `933-943` (G8 keeps F9 and adds no concurrent
case); `884-885` (G4: `observe` "aborts if the run has left `started`").

A second converge (an operator's retry in another window, a scheduled
fleet converge, a herdr pane resuming a plan) that lands while run R is
`started` and its `observe` is mid-window will, per G3, run `rollback R`.
The rollback is the safe direction, so this is not a lockout: it sets
`rolling-back`, kills Docker, the first controller's `observe` sees the
phase change and aborts, and its `confirm` refuses. But the healthy run
is lost, and F9's acceptance case says the opposite should happen. Since
the dead-man already bounds every live run, the correct attach rule is
narrower.

Required: attach only to a run that is NOT live — its dead-man timer is
absent (reboot) or its deadline has expired, or its last in-flight unit
(`docker-engine-guard-<op>-<run>-*`) is not active; otherwise `reserve`
refuses and prints the holder and its remaining deadline, as F2 said. Add
to G8: "a second converge during a healthy window is refused and the first
confirms".

### SHOULD-FIX 5 — G6's named instrument cannot return a hit: `systemctl show -p Conditions` prints `[unprintable]` on systemd 259; the D-Bus property through `busctl` does, and its per-condition tristate is not a result

Evidence: `design-rev6.md:913-917` (G6: "reads the manager's parsed
condition list (`systemctl show -p Conditions` parsed through `busctl` /
the D-Bus `Conditions` property, which carries type, trigger flag and
path) and requires exactly the two OR conditions"); measured this round
on gmktec and hp (259) and locally (257): `Conditions=[unprintable]` for
`systemd-binfmt.service` and for hp's `docker.service`; v259
`systemctl-show.c:2228` (`Conditions` is mapped for the `status` renderer
only); local `busctl get-property ... Conditions` returns the full
`a(sbbsi)` array with every tristate `0` on an active unit whose
`ConditionResult=yes`.

The sentence names two instruments as if they were one. The `systemctl
show` form returns a constant string on every unit, so a check written
against it either fails on every host or — if the implementer matches
loosely — passes on every host. `busctl get-property` (or
`sd_bus_get_property` from Python through `busctl --json=short`) is the
instrument. Note also that the fifth field is NOT the condition's result:
on an active, condition-passed unit it reads `0` for every entry. Take the
result from `ConditionResult=` and the shape (type, trigger flag, negate
flag, path) from the array.

Required: replace the `systemctl show -p Conditions` wording with the
`busctl get-property` call and the exact expected array, two entries,
each `"ConditionPathExists" true false "<path>"`, and assert
`ConditionResult=no` separately. This is the positive control the F5.3
journal line pairs with; without it G6's "effective conditions, not text"
is text again.

### SHOULD-FIX 6 — The fleet's `sandbox_storage` role writes its own drop-in into `docker.service.d` and `containerd.service.d`, which G6 refuses; the gmktec play order does not place that role

Evidence: hp, measured this round:
`/etc/systemd/system/docker.service.d/10-requires-sandbox-storage.conf`
and `.../containerd.service.d/10-requires-sandbox-storage.conf`, "Managed
by Ansible (role: sandbox_storage)", `RequiresMountsFor=/var/lib/docker`
and `/var/lib/containerd`; `design-rev6.md:912-913` (G6: "the role
refuses any drop-in other than its own"); `288-292` (the fresh-host
order: "slice unit (systemd only), `docker_engine` (through `confirmed`),
the slice role's daemon-dependent half, `otel_receiver`, `sccache_redis`,
`container_reclaim`, `disk_guard`, `fabro_server`" — no `sandbox_storage`);
`23-28` (gmktec has no `/var/lib/docker` and no sandbox storage mount is
mentioned anywhere in the design).

If `sandbox_storage` runs before `docker_engine` on gmktec (it does on hp,
by the evidence of its drop-ins), G6 refuses the install. If it runs
after, it adds a `RequiresMountsFor=` on a path that is not a mount point
on gmktec (harmless: it resolves to the root mount) and leaves a drop-in
that a later resume branch would refuse. Either way the design is silent
on a role that demonstrably owns part of the same unit directories.

Required: state whether gmktec receives the sandbox-storage layout; place
`sandbox_storage` in the gmktec order explicitly (after `confirmed` if at
all); and make G6's refusal an allowlist (the guard's own drop-in plus
`10-requires-sandbox-storage.conf` with its committed digest) rather than
"any other".

### SHOULD-FIX 7 — One challenge, 120 seconds, no re-issue; and the controller is never instructed to call `rollback` on a failure it sees, so for a failed `start`, a dead `observe` unit or a failed controller probe the deadline is the PRIMARY trigger

Evidence: `design-rev6.md:843-845` (G2 `confirm`: "the matching nonce of
a challenge issued on this boot and younger than 120 s"); `886-889` (G4:
`observe` "issues the challenge ... and moves the run to `observed`"; "If
the controller dies at any point, nothing else is needed: the dead-man
rolls the run back at the deadline"); `573-579` (R8: the controller's
three probes — a new Tailscale SSH session, the LLM `/health`, a LAN login
through poweredge — run only after reading the challenge); round-4 Fable
NOTE 11 and round-5 Fable BLOCKER 1 (item 2) on the same window; G8
(`933-943`) has no "controller sees `start`/`observe` fail" case.

After `observe` exits, the controller must read the challenge, run three
network probes (two of them fresh SSH logins over Tailscale, each an
Ansible task with its own connection setup) and then reach `confirm`
through another `systemd-run` over SSH, inside 120 s. A slow handshake
past 120 s is not a safety problem — it is a full rollback and a repeat
of the entire window, because no subcommand can re-issue a challenge and
`observe` requires `started`. Separately, the design relies on the
deadline for every failure the controller CAN see: a `start` killed by
its budget with containerd up and dockerd starting, an `observe` unit
killed by its budget mid-window (run stays `started`, nobody samples), a
failed controller probe. Each leaves Docker running on the CI node for up
to `N` when a `rollback` invocation would end it in a minute.

Required: add `challenge <run>` (locked; requires `observed`, an unexpired
deadline, a bounded count of re-issues, and ONE fresh host sample before
issuing, so the host is re-observed at each re-issue), or raise the
window to 300 s with the same one-sample re-check inside `confirm`. State
outright that the controller runs `rollback <run>` immediately on any
non-zero `start`, `observe` or `confirm`, and on any failed controller
probe — the dead-man is the backstop, never the first responder. Add both
to G8.

### NOTE 8 — Budgets equal their internal sums, and the dead-man's stop timeout is unstated

Evidence: `design-rev6.md:819-824` (G1 budgets: `start` 180 s, `publish`
120 s, dead-man `TimeoutStartSec=600`); rev5 `624-628` (lock wait 60 s);
`101-104` (60 s bounded waits for containerd and for docker); gmktec
`DefaultTimeoutStopUSec=1min 30s`.

`start` = 60 s lock wait + 60 s containerd + 60 s docker = 180 s = its
budget, so a `start` that is slow but about to report cleanly is killed
by the unit at the instant its own wait would have returned, losing the
recorded outcome. `publish` 120 s includes a possible 60 s lock wait.
Give each budget a margin over its internal sum, or subtract the lock
wait from the internal waits. The dead-man's service gets only
`TimeoutStartSec=600`; with the default `TimeoutStopSec` of 90 s its
SIGTERM-to-SIGKILL window is three times the 30 s G1 states for the
others — set it. G1's recovery-delay bound ("one in-flight operation's
budget plus 30 s, plus 60 s, plus one rollback budget") is ~23 minutes on
the `observe` path (720 + 30 + 60 + 600); say so as a number.

### NOTE 9 — Round-5 small items not carried into revision 6

Evidence: `design-rev6.md:816-818` (the lock is "a fixed file created
once, never replaced"); gmktec measured: `/run/docker-engine-guard`
absent; `820-821` (budgets list `release` but G3 never invokes it —
"released by the next `reserve`" — and `verify` / `reconfigure` have no
budget); `385-390` (R1 "at most one [permission] is in force", still
unamended against F4's overlap); `762-763` (F7's `docker`-group check
"before `reserve`", before the group exists).

`/run` is tmpfs: "created once" must mean a `tmpfiles.d` entry (`d
/run/docker-engine-guard 0700 root root -` and `f
/run/docker-engine-guard/lock 0600 root root -`) or create-on-open with
`O_CREAT` by every subcommand, else the first post-boot `rollback` or
`reserve` fails on the lock path. The other three are text fixes; none is
dangerous.

### NOTE 10 — The deadline is wall clock while the dead-man's `OnActiveSec` is monotonic; safe either way, but say why

Evidence: `design-rev6.md:830-832` (G2: "the run's absolute deadline (wall
clock plus the boot id it was set under)"); local `systemd.timer(5)`
(`OnActiveSec=` is a monotonic clock, `CLOCK_MONOTONIC` or
`CLOCK_BOOTTIME` per `WakeSystem=`); `849-851` (G2: rollback wins at the
decision point because `confirm` re-checks the deadline under the lock).

An NTP step forward makes `confirm` refuse early (safe); a step backward
lets `confirm`'s wall-clock check pass after the monotonic dead-man has
fired — but the dead-man's `rollback` set `rolling-back` under the lock
first, so `confirm` still refuses. Record the deadline as
`CLOCK_BOOTTIME` plus boot id (boot-scoped by construction and the same
clock the timer uses) and the two can never disagree; a suspend/resume on
a server is not expected, so `CLOCK_MONOTONIC` is equivalent.

### NOTE 11 — Rollback attempt counters and the kill phase

Evidence: `design-rev6.md:895-899` (G5: `runs/<run>/rollback/<phase>.attempts`,
skipped after 3 without success); `904-907` (`rollback-partial`: re-run
only non-exhausted failing phases, then stop).

The counters live on `/var/lib` and survive a reboot, so a phase
exhausted before a reboot stays skipped after it, although a reboot
changes everything the phase acts on (its postcondition is still checked,
so the outcome is right; the skip is merely pointless). Key the counters
by boot id. Separately, the attempt cap exists for phases that can crash
the driver (the rule parser); the kill-by-cgroup phase is cheap,
idempotent and the one that most matters for the CI node — exempt it
from the cap, or state that it is retried on every firing regardless.

### NOTE 12 — Two post-commit edges

Evidence: `design-rev6.md:845-847` (G2 `confirm`: publish marker →
`committed` → remove `allow-start` → enable → stop dead-man →
`confirmed`); `900-903` (G5: the dead-man stops itself on `rolled-back`);
`247-251` (Mechanism 6 validate-only); rev5 `699-701` (F3).

(a) A `confirm` that crashes after the marker and before stopping the
timer leaves the dead-man firing a no-op `rollback` every 60 s until the
attach path's `confirm` finishes; have `rollback` stop the timer when it
finds the marker too, not only on `rolled-back`. (b) A reboot between
`committed` and `confirmed` on a host whose units a previous rollback
disabled boots with `confirmed` present and nothing started; the attach
`confirm` enables but never starts. Make the validate-only path assert
`UnitFileState=enabled` and `ActiveState=active` on the three units and
start them if not — post-commit, Docker is an ordinary service.

### NOTE 13 — Observer mechanics

Evidence: `design-rev6.md:883-885` (G4: `observe` "takes the lock only to
record progress, and it aborts if the run has left `started`"); rev5
`626-628` (lock wait 60 s, then exit non-zero); `809` (unit names
`docker-engine-guard-<op>-<run>-<seq>`); `877-878` (`observe` "pulls and
runs the canary").

If the rollback driver holds the lock for up to 600 s, `observe`'s
per-sample lock wait times out; it should then read the phase file
LOCKLESS (it is replaced atomically) and abort on `rolling-back` rather
than exit with no record. `<seq>` is allocated by three different parties
(controller, `observe`, the dead-man's fixed name) — a collision makes
`systemd-run` refuse with "Unit already exists"; use a timestamp or UUID.
`docker pull` has no timeout of its own; wrap it so a slow registry does
not eat the window's budget. The in-place install of inputs by `publish`
should be atomic per file (tmp + rename), since `publish` can be killed
by its budget mid-write.

### NOTE 14 — What I verified as sound and do not re-open

G1's shape (`service.c:4491-4497`, `service_enter_signal` arming
`timeout_stop_usec`, SIGKILL at `4547-4561`; `bus-unit-util.c:2574` for
`Type` via `--property`); the `confirm`/dead-man interplay in both orders
(the marker is checked under the lock before `rolling-back` is set; a
firing already waiting on the lock finds `committed` and exits; stopping
the timer does not stop a running trigger service, round-5 NOTE 8); the
commit point (F4 stands); reboot behaviour (tmpfs `allow-start`, tmpfs
challenge with boot id, boot-id-bound deadline, snapshot in
`runs/<run>/before/` on `/var/lib`, attach path); the rollback driver's
bounded-attempt progress argument; and `--wait` with `--collect` on a
oneshot (results are lost from the manager on unload, which is why the
run directory, not the unit, carries the outcome — consistent with G2).

## Verdict per round-5 finding — Fable reviewer

1. **RESOLVED** — G4 assigns the window, the canary, its teardown, the
   failed-sample rollback and the challenge to the bounded `observe` unit;
   G8 restores the failed-sample case. Residuals: no challenge re-issue
   and no controller-initiated rollback on visible failures (SHOULD-FIX
   7), and a controller that dies between `start` and launching `observe`
   leaves an unsampled window until `N`.
2. **RESOLVED** — G1 makes every operation and the dead-man's service
   `Type=oneshot` with `TimeoutStartSec`, `TimeoutStopSec=30`,
   `KillMode=control-group`, `SendSIGKILL=yes`; verified against v259
   `service.c:4491-4561` and `bus-unit-util.c:2574`. `timeout -k` on the
   steps is moot under a cgroup kill.
3. **RESOLVED** — G3 defines reclamation (attach: `rollback` → `verify` →
   `reserve`; a `reserved` run releases; a `confirmed` run is `released`
   by the next `reserve`). Residuals: the attach rule has no liveness
   test (SHOULD-FIX 4) and the reserve-after-confirmation path it
   introduces is the subject of SHOULD-FIX 1.
4. **RESOLVED** — G2's `confirm` "ENABLES the three units" after the
   commit point. Residual: the validate-only path still does not assert
   enabled/active (NOTE 12b).
5. **RESOLVED** — G2: `start` requires exactly `published`, never runs on
   `rolling-back` / `rolled-back` / `rollback-partial`, and sets `started`
   before creating `allow-start`; G8 tests the duplicate start.
6. **RESOLVED** — G5: the dead-man stops itself on `rolled-back` with
   `stop`, never `disable`; under `rollback-partial` it re-runs only
   non-exhausted failing phases and stops when all are exhausted, which
   also ends the compare-only-postcondition retry. Residual: NOTE 12a.
7. **RESOLVED** — `publish` takes the snapshot into `runs/<run>/before/`
   on `/var/lib`, and `start` requires `published`, so the snapshot's
   existence is a precondition of any forward step.
8. **RESOLVED (accepted)** — G1 shapes the dead-man's service as a
   oneshot; the two behaviours noted (redundant elapse while active;
   `confirm` must `stop`, never `kill`) are consistent with G2/G5.
9. **RESOLVED** — G6 adds the manager's condition list and the
   `confirmed`-absent assertion; but the instrument it names,
   `systemctl show -p Conditions`, prints `[unprintable]` on 259
   (SHOULD-FIX 5) — the busctl half of the sentence is the working half.
10. **RESOLVED** — G7 states `dpkg -i` runs inside the helper's transient
    unit, never the controller's session. Residual: the helper is given
    two incompatible bounds and the transaction has no lifecycle phase
    (SHOULD-FIX 3); the `--no-block` socket-stop advice is not restated.
11. **NOT RESOLVED** — none of the four small items was carried in: the
    subcommand set is now seven-plus with `release` listed but never
    invoked and `verify`/`reconfigure` unbudgeted; `/run/docker-engine-guard`
    creation after boot is unaddressed and "created once" contradicts
    tmpfs; the `docker`-group check timing is unchanged; R1 is unamended
    (NOTE 9). Minor, none dangerous.

## Verdict per round-5 finding — Codex reviewer

1. **RESOLVED** — G1: every lock holder is a bounded oneshot transient
   unit with escalation and cgroup cleanup; the lock file has a stable
   inode; a total recovery-delay bound is stated; G8 adds SIGSTOP of each
   subcommand while holding the lock. Verified against v259 as above.
2. **RESOLVED** — G2: forward-only phases, `start` only from `published`
   and never from any rollback phase, deadline plus boot id re-checked
   under the lock at every decision (so an armed-but-expired timer cannot
   admit a `start`), rollback wins over a waiting `confirm` at an expired
   deadline, and `confirm` recognises `committed`/`confirmed` first and
   finishes without a challenge; G8 covers each sequence.
3. **RESOLVED** — G3: the controller uploads immutable per-run inputs
   into a directory `reserve` created for that run; the locked `publish`
   installs them only for the current `reserved` run; post-commit
   changes go through locked `reconfigure`; G8 tests the delayed
   `publish` after a newer reservation. Residuals: `reconfigure`'s
   precondition is unsatisfiable under "every converge reserves"
   (SHOULD-FIX 1), and the package install is not routed through the
   phase machine (SHOULD-FIX 3).
4. **RESOLVED** — G4 assigns canary, observation, challenge and teardown
   to `observe`, binds the evidence record to run id, boot id and
   configuration digest, and makes `confirm` require it. Residual:
   SHOULD-FIX 7.
5. **RESOLVED** — G5: a minimal driver runs each phase as a separate
   child with its own timeout and records attempts before entry; a phase
   is skipped after three unsuccessful attempts with its postcondition
   still reported; G8 tests repeated parent death at the same phase.
6. **RESOLVED** — G3 defines the attach/repair/release entry after a
   reboot and the crash-after-`reserve` case; the challenge is on tmpfs
   and carries the boot id, and `confirm` requires a challenge "issued on
   this boot"; the deadline carries the boot id.
7. **RESOLVED** — G6 puts every existing host drop-in into the scratch
   root, refuses unexpected overrides, reads the manager's parsed
   condition list and requires `confirmed` absent before `dpkg -i`. The
   named `systemctl show` instrument cannot return a hit and must be the
   D-Bus property through `busctl` (SHOULD-FIX 5); the refusal of "any
   other" drop-in collides with the fleet's `sandbox_storage` drop-in
   (SHOULD-FIX 6).
8. **RESOLVED** — G7: `dpkg -i` inside the host-owned helper unit;
   `triggers-awaited`/`triggers-pending` allowed only on this run's
   packages or the handlers they activate (systemd, man-db), completed
   with `dpkg --triggers-only` restricted to them, anything else refuses.
   Residuals: the helper's bound (oneshot versus `RuntimeMaxSec`) and the
   run-id-keyed recovery after the attach path releases the interrupted
   run (SHOULD-FIX 3).
9. **NOT RESOLVED** — the companion carrier, the LAN-fallback proof on
   gmktec, the corrected host records and the disposable-VM fault
   injection remain gates by the design's own statement (`599-607`,
   `794`, `932-943`); no completion evidence is supplied, and correctly
   none is claimed. This review is not approval to converge gmktec.

REVIEW-COMPLETE: NO-BLOCKERS
