# Independent review, round 8 — Docker on gmktec-xubuntu (design revision 8)

Reviewed 2026-10-15 by a Fable reviewer with no part in the design. **No
BLOCKER.** Revision 8 is purely additive over revision 7 (`diff design-rev7.md
design-rev8.md` shows only the new section at lines 1062-1129), and the two
tables it adds (I1, I2) close both round-7 Codex blockers: admission is now a
predicate on a NEW reservation that excludes the reserving unit, and dispatch
on the current run is decided per (operation, marker, phase) so a first
`confirm` with no marker commits and an interrupted `publish` resumes. I
checked the lock protocol, the repeating dead-man against a confirm in
progress, the commit point and the reboot rules against the v259 sources
already in this scratchpad (`r5src/`, `systemd-src/`) and found them sound.
What I found that is new is one false mechanism claim with a bounded
consequence (SHOULD-FIX 1), one budget contradiction on the dead-man's own
path (SHOULD-FIX 2), and a set of round-6 residuals that revision 8 leaves
untouched; every one of them can be carried as an implementation rider,
because in each case the failure direction is a refusal or a rollback, never
a lockout or an unbounded Docker exposure.

Scope: design review, not implementation acceptance. Nothing on any host,
repository or ledger was changed; this file is the only write. Remote reads
(all from the brief's allowed list): gmktec — `systemctl --version`,
`ls /etc/systemd/system/` and the three `*.d` directories, `cat
/proc/mounts`, `systemctl show -p Conditions,ConditionResult,ActiveState
systemd-binfmt.service`, `apt-cache policy` / `apt-cache depends`,
`systemctl is-active` of the five units the design names, `systemctl show`
of the two slices, `systemctl cat k3s-agent.service`; hp — `ls` and `cat` of
the two `10-requires-sandbox-storage.conf` drop-ins, `cat /proc/mounts`,
`dpkg -L docker.io|containerd`, `cat` of the three packaged unit files,
`systemctl show -p Conditions,...` on the three units, `cat
/etc/docker/daemon.json`, `dockerd --help`. Local: `systemctl show` and
`busctl get-property` on the control node (systemd 257), `systemd.timer(5)`,
`systemd-run(1)`, `systemd.unit(5)`, and the v259 sources `timer.c`,
`unit.c`, `service.c`, `job.c`, `unit-dependency-atom.c`. Line numbers are
`design-rev8.md` unless another file is named.

## Facts measured this round

- gmktec: `systemd 259 (259.5-0ubuntu3.4)`; no `docker.service.d`,
  `containerd.service.d` or `docker.socket.d`; `/run/docker-engine-guard`,
  `/var/lib/docker-engine-guard`, `/var/lib/docker`, `/var/lib/containerd`
  absent; `/var/lib/docker` is not a mount point (root is `/dev/nvme0n1p1`
  ext4; the only k3s-related mounts are `/var/lib/rancher/k3s/agent/containerd`
  and `/var/lib/rancher/k3s/storage` on `nvmea-ci-*` volumes). Candidates:
  `docker.io 29.1.3-0ubuntu4.1`, `containerd 2.2.2-0ubuntu1.1`, `runc
  1.4.0-0ubuntu1` — the allowlist. `docker.io` Depends (no recommends):
  `adduser containerd iptables debconf libc6 libnftables1 libsystemd0`;
  `containerd` Depends: `runc libc6`. `libnftables1 1.1.6-1`, `iptables
  1.8.11-2ubuntu3`, `adduser`, `debconf` are all INSTALLED, so the
  three-package `Inst` set the audit expects is consistent with the live
  index. Both apt timers, `k3s-agent`, `tailscaled`,
  `local-homelab-llama-server` active. `k3s-agent.service`: `KillMode=process`,
  `Delegate=yes`, `ControlGroup=/system.slice/k3s-agent.service`. `fabro.slice`
  and `fabro-sandbox.slice` loaded, inactive, empty `ControlGroup`.
- gmktec, systemd 259: `systemctl show -p Conditions systemd-binfmt.service`
  prints `Conditions=[unprintable]` (re-measured; same as round 6). Local
  257: the same string from `systemctl show`, while `busctl get-property
  org.freedesktop.systemd1 /org/freedesktop/systemd1/unit/systemd_2dbinfmt_2eservice
  org.freedesktop.systemd1.Unit Conditions` returns the `a(sbbsi)` array
  (`"ConditionDirectoryNotEmpty" true false "/run/binfmt.d" 0 ...`).
- hp: `/etc/systemd/system/docker.service.d/10-requires-sandbox-storage.conf`
  and `.../containerd.service.d/10-requires-sandbox-storage.conf` exist,
  "Managed by Ansible (role: sandbox_storage)", `RequiresMountsFor=/var/lib/docker`
  resp. `/var/lib/containerd`; `/var/lib/docker` and `/var/lib/containerd`
  are both mounts of `/dev/sdc2`. No `docker.socket.d`. Packaged
  `docker.service`: `Type=notify`, `Requires=docker.socket`,
  `Wants=containerd.service`, `ExecStart=/usr/bin/dockerd -H fd://
  --containerd=/run/containerd/containerd.sock`, `TimeoutSec=0`,
  `RestartSec=2`, `Restart=always`, `StartLimitBurst=3`,
  `StartLimitInterval=60s`, `Delegate=yes`, `KillMode=process`.
  `docker.socket`: `ListenStream=/run/docker.sock`, `SocketMode=0660`,
  `SocketGroup=docker`. `containerd.service`: `Restart=always`,
  `RestartSec=5`, `KillMode=process`, `Delegate=yes`. `dockerd --help` lists
  `--ip-forward-no-drop`, `--cgroup-parent`, `--iptables`, `--live-restore`.
  hp's `daemon.json` is only `{"cgroup-parent": "fabro-sandbox.slice"}`.
- v259 `service.c:89-90` (and `122-123`): `[SERVICE_AUTO_RESTART] =
  UNIT_ACTIVATING`, `[SERVICE_AUTO_RESTART_QUEUED] = UNIT_ACTIVATING`.
  `unit.c:1949-1954`: "If we already are activating ... we don't want to
  recheck the condition in that case": `if (state != UNIT_ACTIVATING &&
  !unit_test_condition(u)) return ... ECOMM`. `unit_test_condition` has
  exactly ONE call site in the tree (`unit.c:1953`); `service_enter_dead`
  (`service.c:2100-2190`) decides the restart without any condition test;
  `service_start` (`3013-3035`) accepts `SERVICE_AUTO_RESTART_QUEUED` and
  proceeds. `service_stop` (`3107-3129`) sets `forbid_restart = true` and,
  from `SERVICE_AUTO_RESTART` / `_QUEUED`, "gives up on the auto restart".
  `unit-dependency-atom.c:43`: `UNIT_REQUIRED_BY` carries
  `UNIT_ATOM_PROPAGATE_STOP`.
- v259 `timer.c:490-495`: `TIMER_UNIT_INACTIVE` base is
  `MAX(trigger->inactive_enter_timestamp, last_trigger)`, skipped while
  `<= 0`; `619-659` (`timer_enter_running`): each elapse queues `JOB_START`
  with `JOB_REPLACE` and stamps `last_trigger`; `795-823`
  (`timer_trigger_notify`): in `TIMER_RUNNING` the timer re-enters waiting
  only when the trigger becomes inactive or failed; `710-717` (`timer_stop`):
  the timer goes dead by itself — nothing in it stops a running trigger
  service. `job.c:786-794`: the trigger-condition skip line is `"%s was
  skipped because no trigger condition checks were met."` with
  `JOB_ID`/`JOB_TYPE`/`JOB_RESULT` fields.

## Ranked findings

### SHOULD-FIX 1 — Mechanism 1's claim that a `Restart=` respawn re-evaluates the start condition is false on systemd 259; the rollback is safe anyway, but only because of the ORDER of its explicit stops, which the text does not identify as load-bearing

Evidence: `design-rev8.md:57-60` ("systemd evaluates the condition on EVERY
start attempt — boot, socket activation, a postinst `invoke-rc.d` start, a
`Restart=` respawn, an operator's `systemctl start`"); `68-69` ("removing
`/run/docker-engine-guard/allow-start` is the first act of a rollback, after
which `Restart=always` cannot respawn the daemon"); `643-649` (F1's rollback
order: remove `allow-start`; stop `docker.socket`; cancel queued jobs;
restore FORWARD; "kill by cgroup and stop the three units"); `464-467`
(R4.1). Measured above: `service.c:89-90`, `unit.c:1952-1954`, the single
call site of `unit_test_condition`, `service_stop` at `3107-3129`,
`unit-dependency-atom.c:43`; hp's packaged units (`Restart=always`,
`RestartSec=2` / `5`, `KillMode=process`, `-H fd://`,
`Requires=docker.socket`).

A SIGKILLed `dockerd` or `containerd` enters `SERVICE_AUTO_RESTART`, which
systemd reports as `activating`; when the restart timer fires, the queued
`JOB_START` reaches `unit_start` in state `UNIT_ACTIVATING` and the condition
list is NOT re-tested. So "remove `allow-start`, then kill" does not by itself
prevent a respawn; what prevents it is an explicit `systemctl stop` (which
sets `forbid_restart` and abandons a pending auto-restart). Rounds 3-5 judged
Mechanism 1 sound for fresh starts (job → `unit_start` → condition), which is
correct; the respawn arm of the claim was never checked.

Why this is not a blocker: in the ORDER F1 specifies, `docker.service` never
respawns, because step 2 stops `docker.socket` and `Requires=docker.socket`
propagates that stop to `docker.service` (`UNIT_ATOM_PROPAGATE_STOP`),
setting `forbid_restart` before any kill. Even if it did respawn, `dockerd -H
fd://` without socket fds exits at once and trips `StartLimitBurst=3`. The
only unit that can respawn in a gap between its kill and its stop is
`containerd.service` (`RestartSec=5`), which creates no bridge and no rule.
The repeating dead-man re-attempts every step and the final all-postconditions
check (`650-655`) requires "no ... process, job or start pending" (an
auto-restart is `activating`, so a correct check catches it) before writing
`rolled-back`. Every exposure is therefore bounded; the text is wrong about
WHY.

Required (rider): correct `57-60` and `68-69` to say the condition gates
FRESH starts (boot, socket activation, postinst, operator) and NOT an
automatic `Restart=` respawn; state that the explicit `stop` is what ends a
running unit, that `stop docker.socket` must precede any kill of
`docker.service` (it already does — make the reason explicit), and that
`containerd.service` is stopped in the same phase child as its kill, with no
durable-record write between them. Add to acceptance: on the VM, with
`allow-start` removed and no stop issued, SIGKILL `dockerd` (socket still
active) and `containerd` and observe that both respawn; then prove the
rollback's stop ends them and the final check reports them absent.

### SHOULD-FIX 2 — The dead-man's own service keeps `TimeoutStartSec=600` while H6 budgets `rollback` at 900 s, so the PRIMARY rollback path is cut off before its final postcondition check in the worst case

Evidence: `design-rev8.md:657-661` (F1's recipe:
`--property=TimeoutStartSec=600 docker-engine-guard rollback <run>`);
`821-822` (G1: "The dead-man's service is the same shape (`Type=oneshot`,
`TimeoutStartSec=600`)"); `1037-1043` (H6: `rollback` 900 s; "the phase
budgets sum to 600 s, leaving 300 s of the rollback budget for the lock wait
and the final all-postconditions check"); `624-628` (lock wait up to 60 s);
`886-889` (G4: when the controller dies "the dead-man rolls the run back at
the deadline" — this IS the primary path); gmktec `DefaultTimeoutStopUSec=1min
30s` (round 6).

A dead-man firing that waits 60 s for the lock and then runs phases to their
600 s sum is killed by its own unit at 600 s, before the final check runs and
before any outcome is written. Liveness still holds — the next firing comes
60 s later, G5's attempt counters shorten later firings, and the check
eventually runs — but the 900 s budget H6 states simply is not what this
path gets, and the SIGTERM-to-SIGKILL window on the dead-man's service is
the 90 s default, not the 30 s G1 gives every other unit.

Required (rider): give the dead-man's service `TimeoutStartSec=900` and
`TimeoutStopSec=30` (and `--collect`, see NOTE 8), and state the
worst-case recovery number once: one in-flight op budget + 30 s + 60 s + 900
s. Also (round-6 NOTE 8, still open) `start` = 60 s lock + 60 s containerd +
60 s docker = exactly its 180 s budget; give it a margin.

### SHOULD-FIX 3 — `start` still does not verify the dead-man is live, and `arm` is not stated idempotent against a timer unit that already exists

Evidence: `design-rev8.md:1098` (I2 `start`: "allowed from `armed`, deadline
not passed" — no timer check); `1012-1016` (H4 `arm`: "record the deadline
..., and arm the dead-man with `systemd-run --unit=docker-engine-deadman-<run>
...`; phase `armed`"); `1097` (I2 `arm`: allowed only from `published`);
round-6 Fable SHOULD-FIX 2 (the precondition revision 5 had at `629-632`).

Revision 7 made arming a guard subcommand, which is the right fix; what
remains is the crash seam inside it. If `arm` dies after `systemd-run`
succeeds and before writing `armed`, a re-run of `arm` meets "Unit
docker-engine-deadman-<run>.timer already exists" and fails every time; the
run sits in `published` until the orphan timer fires at `N` and rolls back a
run that never started (safe, but a wasted window). If an implementer writes
`armed` first, a crash in between leaves `start` admissible with no timer —
exactly the exposure the dead-man exists to bound.

Required (rider): `arm` creates the timer BEFORE writing `armed`, and on
re-entry adopts an existing `docker-engine-deadman-<run>.timer` whose
`NextElapseUSecMonotonic` matches the recorded deadline (else refuses);
`start` refuses unless that timer is `ActiveState=active` with a future
elapse (`systemctl show` returns these two properties correctly, unlike
`Conditions`). Add "crash inside `arm` after `systemd-run`, then re-run" to
acceptance.

### SHOULD-FIX 4 — `rollback` from `publishing` leaves a half-installed package set that no later run can recover, because the recovery branch is keyed to the run id

Evidence: `design-rev8.md:1101` (I2 `rollback`: "allowed from every
pre-commit phase"); `1102` (`recover`: "`publishing`: resume `publish`; any
other pre-commit phase: `rollback`" — but the dead-man and an operator may
still call `rollback` directly on a `publishing` run); `1006-1011` (H4: an
interrupted `publish` is resumed "for that run"); `752-756` (F6: a fresh
transaction requires an empty `dpkg --audit`; recovery allows "exactly this
run's packages"); `921-930` (G7: "anything else pending refuses");
`1078` (I1: a new reservation is admitted when the current run is
`rolled-back`); round-6 Fable SHOULD-FIX 3 item 4.

Rolling back a `publishing` run succeeds trivially (nothing was started) and
writes `rolled-back`; the next converge reserves normally, and its `publish`
refuses on a non-empty `dpkg --audit` because the pending packages belong to
a run that is no longer current. The host is stranded until an operator
repairs dpkg by hand. This is a refusal, not a safety problem, so it is a
rider — but it is the one path where the design's own rules forbid its own
recovery.

Required (rider): key the interrupted-install recovery to the committed
allowlist (package, version, SHA256), which is identical across runs, not to
the run id; or make `rollback` from `publishing` refuse while `dpkg --audit`
is non-empty and point the operator at `recover` (resume) instead.

### SHOULD-FIX 5 (carried from round-6 Fable SHOULD-FIX 7) — No controller-triggered rollback on visible failures, and one 120 s challenge with no re-issue

Evidence: `design-rev8.md:1100` (I2 `confirm`: "a current-boot challenge
younger than 120 s"); `843-844`; `1101` (I2 lists "operator" as a rollback
invoker but no section instructs the role to invoke it); `1119-1121` (I4:
`arm` "refuses (and the run is rolled back)" — passive voice, no actor named;
the dead-man is NOT armed yet at that point, so nobody rolls it back);
`886-889` (G4: the dead-man "at the deadline"); `960-963` (H1 forbids
touching ANOTHER run, which does not cover the owner's own run).

Revision 8 does not resolve this. It CAN be carried as a rider because the
failure direction is a full rollback and a repeated window (safe, costly),
and because the fix is role-side: an Ansible `rescue` that runs `rollback
<run>` on any non-zero `arm`, `start`, `observe` or `confirm` and on any
failed controller probe, so the dead-man is the backstop and never the first
responder. The challenge re-issue is a small protocol addition (a `challenge
<run>` row in I2: from `observed`, marker absent, deadline not passed, one
fresh host sample, bounded count) that disturbs nothing else in I1/I2; if the
implementer prefers to keep the 120 s window, record that a slow Tailscale
handshake costs a whole run and test that path once.

### SHOULD-FIX 6 (carried from round-6 Fable SHOULD-FIX 5; Codex round-8 SHOULD-FIX 2) — G6 still names `systemctl show -p Conditions`, which prints `[unprintable]` on 259

Evidence: `design-rev8.md:913-917` (unchanged: "`systemctl show -p
Conditions` parsed through `busctl` / the D-Bus `Conditions` property");
re-measured this round on gmktec (259) and locally (257): `[unprintable]`;
`busctl get-property ... Conditions` returns the `a(sbbsi)` array.

Not resolved in the text; rider. Replace with the `busctl get-property` call
(or `--json=short`), require exactly two entries `"ConditionPathExists" true
false "<path>"`, and take the result from `ConditionResult=` separately — the
array's fifth field is not a result.

### SHOULD-FIX 7 (carried from round-6 Fable SHOULD-FIX 6) — The fleet's `sandbox_storage` drop-ins and gmktec's play order are still unaddressed

Evidence: hp, re-measured: both `10-requires-sandbox-storage.conf` drop-ins
present, `/var/lib/docker` and `/var/lib/containerd` separate mounts;
gmktec, re-measured: neither directory, neither mount; `design-rev8.md:912-913`
(G6 "refuses any drop-in other than its own"); `288-292` (the fresh-host
order names no `sandbox_storage`).

Not resolved; rider, because every outcome is a refusal: if the role runs
before `docker_engine` on gmktec, G6 refuses the install; if after, a later
resume branch refuses. Decide whether gmktec receives the layout; if yes,
place `sandbox_storage` after `confirmed` and allow exactly its drop-in by
committed digest; if no, exclude gmktec from that role. I agree with Codex
NOTE 5 that the allowance must not be broadened silently.

### NOTE 8 — I1's quiescence predicate does not classify `failed`, and the dead-man's recipe lacks `--collect`

Evidence: `design-rev8.md:1080` (I1: "each `inactive` (not active,
activating, deactivating or reloading), with no queued job"); `1112` (I3:
"quiescent means `inactive` with no queued job"); `657-661` (F1's dead-man
`systemd-run` has no `--collect`; G1's operation recipe at `809-812` does);
`626-628` (a lock-wait timeout exits non-zero); round-5 Fable (`systemd-run(1)`:
without `--collect` failed transient units are kept).

A dead-man firing that exits non-zero on a lock-wait timeout leaves its
service loaded in `failed`; `failed` is neither in I1's accepted state nor in
its refused list, so a literal `ActiveState == inactive` check refuses forever
and a literal "not in {active, activating, ...}" check passes. Both are
defensible; say which. Simplest: add `--collect` to the dead-man (then it
unloads either way) and define quiescent as "`ActiveState` in {inactive,
failed} and no job". Keying attempt counters by boot id and exempting the
kill phase from the 3-attempt cap (round-6 NOTE 11) are still worth doing.

### NOTE 9 — `verify` and `reconfigure` take the lock and write, but have no row in I2

Evidence: `design-rev8.md:689-691` (F2: `verify` "marks it `rolled-back`");
`991-995` (H3: `reconfigure` writes owned keys); `1039-1040` (both budgeted);
`1094-1102` (I2 table: neither listed). Add the rows: `verify` allowed from
`rollback-partial` with marker absent, refused when the marker names the run;
`reconfigure` allowed only when the marker names the run and the phase is
`confirmed`.

### NOTE 10 — Two post-commit edges remain (round-6 Fable NOTE 12; Codex round-8 NOTE 4/5)

Evidence: `design-rev8.md:1101` (I2 `rollback` with marker: "no-op, exit 0"
— the dead-man does not stop its own timer in this row, only on `rolled-back`
at `900-903`); `1100` and `1027-1030` (FINISH enables but never starts the
units; validation then expects "enabled and running"). (a) A `confirm` that
dies after the marker leaves a 60-second no-op firing until an operator runs
`recover`: harmless, but have the marker-names-run row stop the timer too.
(b) After a reboot between `committed` and `confirmed`, FINISH leaves the
units enabled and inactive; make FINISH start them (post-commit Docker is an
ordinary service) or make validation report "enabled, not running" rather
than fail.

### NOTE 11 — `recover`'s lock delegation (agreeing with Codex round-8 SHOULD-FIX 1)

Evidence: `design-rev8.md:1089` ("Every operation below runs under the lock")
with `1102` (`recover` dispatches to `publish` or `rollback`, each itself a
lock-taking helper). If `recover` holds the lock while launching the target
helper synchronously, the child waits 60 s and exits. Choose: `recover` is a
controller-side dispatcher that reads marker and phase under a short lock,
releases, and launches the target (which revalidates); or it runs the handler
in-process under one acquisition with the larger budget. Rider.

### NOTE 12 — Small items, none dangerous

`design-rev8.md:385-390` (R1 "at most one permission in force") still
contradicts F4's stated overlap; `877-878` (`docker pull` in `observe` has
no timeout of its own — wrap it); `859-861` (`publish` installs inputs into
place — make each file tmp+rename, since `publish` can be killed by its
budget); `1096` (a second run's `publish` on a host whose audited set is
already installed and whose units a prior rollback disabled is the
Mechanism-6 "resume" row — say that it re-runs the audit, expects zero `Inst`
lines, and accepts an unchanged `dpkg-query` diff).

### NOTE 13 — What I verified as sound and do not re-open

- Lock protocol (I1/I2 + G1/H6): one fixed `flock` file created on open with
  `O_CREAT`, close-on-exec, every holder a bounded oneshot with cgroup kill;
  a reserving unit excluded from its own quiescence check; current-run
  operations keyed on reservation identity, then marker, then phase, all
  under one acquisition. No two forward operations can both proceed.
- Repeating dead-man vs a confirm in progress: `confirm` holds the lock;
  a firing waits at most 60 s and exits non-zero; `inactive_enter_timestamp`
  is stamped on `failed` too (round 5, `unit.c:2740`), so the timer re-arms
  (`timer.c:490-495`); the next firing reads the marker and exits 0; `confirm`
  then stops the timer, which does not touch a running trigger service
  (`timer.c:710-717`). In the other order, `rollback` writes `rolling-back`
  under the lock first and `confirm` refuses. A `confirm` arriving after the
  monotonic deadline refuses even if no firing has yet taken the lock.
- Commit point: F4 stands; the rename is the commit, the directory fsync
  failure is a durability warning, and after a reboot an absent marker means
  uncommitted whatever the phase says (I2's `rollback` row says so
  explicitly and forbids recreating permission from a phase).
- Reboot: `allow-start`, the challenge and the dead-man are tmpfs/transient;
  the deadline carries the boot id so every decision reads "deadline passed";
  units the postinst enabled stay condition-skipped (fresh starts DO test the
  condition: `unit.c:1952-1954` with state `inactive`); no automatic recovery
  runs, by H1, until an operator names the run.
- F5 instruments: `cat --root` on 259 (round 5, `systemctl-edit.c:38-62`);
  the probe unit's own permission path; the journal line (`job.c:786-794`,
  re-read); the pre-install absence assertions. G6's busctl half works.
- I3 fixed identities: with `--collect`, a finished oneshot is unloaded, so a
  later `observe` is admitted by systemd and refused by the phase check
  (`observing`/`observed` ≠ `started`), which is the intended order.
- The allowlist's dependency closure is satisfied on gmktec today (measured
  above), so the audit's "every `Inst` line in the allowlist" can pass.

## Verdict per round-7 finding (Codex, the only round-7 review)

1. **RESOLVED** — BLOCKER 1: I1 scopes the predicate to a new reservation
   and excludes the reserving unit; I2 admits the owning run's `publish`,
   `arm`, `start`, `observe`, `confirm` and the deadline `rollback` while
   the observer and dead-man are active.
2. **RESOLVED** — BLOCKER 2: I2's `confirm` row commits from `observed`
   with the marker absent; `recover` resumes `publishing`; a `committed`
   phase with no marker rolls back and never recreates permission.
3. **RESOLVED** — SHOULD-FIX 3: I3 fixes both `start` and `observe` unit
   names and uses them in admission, H2's stop and acceptance; quiescent
   includes "no queued job". Residual: `failed` unclassified (NOTE 8).
4. **RESOLVED** — SHOULD-FIX 4: I4 creates `/run/docker-engine-guard` and
   opens the lock with `O_CREAT` on every helper; the docker-group check is
   repeated by `arm` after the group exists. Residual: who rolls back on
   `arm`'s refusal (SHOULD-FIX 5).
5. **RESOLVED** — NOTE 5: the serialized confirm/dead-man protocol is now
   reachable and I re-verified it against `timer.c`; the one instrument
   spelling is SHOULD-FIX 6.
6. **NOT RESOLVED** — NOTE 6: companion carrier, LAN-fallback proof on
   gmktec, corrected host records and VM fault injection remain gates with
   no completion evidence; this review authorizes no converge.

## Verdict per round-6 Fable finding, with rider classification

1. **RESOLVED** — SF1: H3 refuses `reserve` while `confirmed` exists; no
   `release`; post-commit changes through `reconfigure`.
2. **RESOLVED** — SF2: H4 makes `arm` a guard subcommand and `start`
   admissible only from `armed`. Residual rider: SHOULD-FIX 3.
3. **RESOLVED** — SF3: H4 puts the install inside `publish` (1800 s,
   `publishing` phase, same-run resume); the oneshot/`RuntimeMaxSec`
   contradiction is moot under G1. Residual rider: SHOULD-FIX 4.
4. **RESOLVED** — SF4: H1 removes attach/takeover; a second controller is
   refused with the holder's id, phase and deadline.
5. **NOT RESOLVED, rider** — SF5: text unchanged at `915`; the working
   instrument is named in the same sentence, so it is a wording fix before
   tasks are written (SHOULD-FIX 6).
6. **NOT RESOLVED, rider** — SF6: silent on `sandbox_storage`; every
   outcome is a refusal, so it is a play-order and allowlist decision in the
   companion carrier (SHOULD-FIX 7).
7. **NOT RESOLVED, rider** — SF7: no controller-triggered rollback is
   stated and the challenge is still one-shot 120 s; failure direction is
   rollback-and-repeat, so it is a role-side `rescue` plus an optional
   one-row protocol addition (SHOULD-FIX 5).
8. **PARTIALLY RESOLVED, rider** — NOTE 8: H6 budgets rollback at 900 s
   with headroom, but the dead-man's own service keeps 600 s and the
   default stop timeout (SHOULD-FIX 2); `start` is still budget = sum.
9. **RESOLVED** — NOTE 9: I4 (runtime dir), H3 (`release` gone), H6
   (`verify`/`reconfigure` budgets), I4 (group check timing). R1's wording
   remains stale (NOTE 12).
10. **RESOLVED** — NOTE 10: H4 records a boot-scoped `CLOCK_MONOTONIC`
    deadline and derives the timer's first delay from it.
11. **NOT RESOLVED, rider** — NOTE 11: attempt counters not keyed by boot
    id; kill phase not exempt from the cap (NOTE 8).
12. **NOT RESOLVED, rider** — NOTE 12: both post-commit edges remain
    (NOTE 10).
13. **PARTIALLY RESOLVED, rider** — NOTE 13: fixed names remove the
    `<seq>` collision for `start`/`observe`; lockless phase read, pull
    timeout and atomic per-file publish are unaddressed (NOTE 12).
14. — NOTE 14 was the verified-sound list; it stands, with SHOULD-FIX 1 as
    the one correction to the round-3 reading of Mechanism 1.

## Verdict per round-8 Codex finding

1. **AGREE, rider** — SHOULD-FIX 1 (`recover` delegation): NOTE 11 above.
2. **AGREE, rider** — SHOULD-FIX 2 (busctl spelling): SHOULD-FIX 6 above,
   re-measured on 259 this round.
3. **AGREE, rider** — NOTE 3: enumerate the retry states in I2's `rollback`
   row (`rolling-back`, `rollback-partial` admitted; `rolled-back` a no-op)
   and the observer's lock scope; keep G5/G8 tests alongside I5.
4. **AGREE** — NOTE 4: the arbitration and reboot rules are coherent; I add
   that the respawn arm of Mechanism 1 is wrong but non-load-bearing
   (SHOULD-FIX 1), and that the dead-man path's budget is 600 s not 900 s
   (SHOULD-FIX 2).
5. **AGREE** — NOTE 5: gates outstanding; no converge authorized.

REVIEW-COMPLETE: NO-BLOCKERS
