# Independent review, round 4 — Docker on gmktec-xubuntu (design revision 4)

Reviewed 2026-10-15 by a Fable reviewer with no part in the design. **One
BLOCKER remains; do not converge revision 4 on gmktec as written.** It is a
one-line unit-file defect with a one-sentence contract fix, but as specified
the actor unit never terminates: `Restart=always` restarts a cleanly-exited
service, so the actor is respawned every 5 seconds forever after every
terminal state and at every boot after confirmation, and under
`rollback-partial` it re-runs the failing mutating phase against the live
CI node indefinitely. Revision 4 otherwise resolves the round-3 blockers of
both reviewers: the commit point (R1), mechanical single ownership (R2), the
condition-proof structure (R5) and the held dpkg frontend lock (R6) are
sound. The remaining findings are instrument and specification defects,
ranked below.

Scope: design review, not implementation acceptance. Nothing on any host,
repository or ledger was changed; this requested, gitignored file is the only
file written. Remote commands were restricted to the brief's allowed reads
(`cat`, `ls`, `ip -br addr`, `systemctl cat|show`, `dpkg -L`, `apt-cache
policy`, `sudo k3s kubectl get` on poweredge). Local reads: man pages on the
control node (systemd 257.9), an OFFLINE scratch-root control of
`systemd-analyze verify --root` and `systemctl --root cat` (file reads only;
no unit was installed or started anywhere). Upstream sources read: systemd
`v259` `src/core/{job,service,unit}.c`, `src/systemctl/systemctl-edit.c`.
`design-rev4.md` line numbers refer to the file named in the brief.

## Facts measured this round that the findings rest on

- Both hosts: systemd `259.5-0ubuntu3.4`, dpkg `1.23.7ubuntu1`, apt `3.2.0`;
  gmktec python3 `3.14.3`. gmktec: `docker.service`, `docker.socket`,
  `containerd.service` all `LoadState=not-found`; no `/run/docker-engine-guard`,
  `/var/lib/docker-engine-guard`, `/etc/systemd/system/docker.service.d`,
  `/run/docker.sock`; no `docker` group in `/etc/group`; `fabro-sandbox.slice`
  inactive with empty `ControlGroup`; `k3s-agent.service` `ControlGroup=
  /system.slice/k3s-agent.service`, `KillMode=process`, `Delegate=yes`.
- gmktec `k3s-agent.service` `ExecStart` carries only `--server`,
  `--token-file`, `--node-ip`, `--node-label` (the unit file ends on a
  trailing continuation); `/etc/rancher/k3s/config.yaml` (3485 bytes),
  `config.yaml.d/` and `k3s-agent.service.env` are root-only (permission
  denied to the review user). No kube-proxy or flannel flag is visible on the
  command line.
- gmktec apt timers: both `enabled`/`active`, `Persistent=yes`,
  `AccuracyUSec=1min`, `RandomizedDelaySec` 12h / 1h;
  `/var/lib/dpkg/triggers/Unincorp` is 0 bytes; `/etc/dpkg/dpkg.cfg.d` is
  empty.
- hp and gmktec `/var/lib/dpkg/info/systemd.triggers` are identical and carry
  ONLY `interest-noawait /usr/lib/systemd/catalog`, `/usr/lib/binfmt.d`,
  `/usr/lib/sysctl.d`, `libc-upgrade` — **no interest on a unit directory**.
- hp `docker.io.postinst`: `deb-systemd-helper enable 'docker.service'` and
  `enable 'docker.socket'` (dh_installsystemd 13.31ubuntu1), then `if … !
  invoke-rc.d docker status; then invoke-rc.d docker start || :` — no
  `daemon-reload`. `containerd.postinst`: `systemctl --system daemon-reload`,
  then `deb-systemd-invoke start 'containerd.service'`. `docker.io` ships
  `/usr/lib/systemd/system/docker.service` and `docker.socket` only.
  `docker.service`: `Requires=docker.socket`, `Wants=containerd.service`,
  `Type=notify`, `TimeoutSec=0`, `Restart=always`, `KillMode=process`,
  `Delegate=yes`. Local `invoke-rc.d` (lines 376-390) starts a unit only if it
  is enabled or active, and (lines 499-504) runs `systemctl start <unit>`
  unless masked.
- systemd v259 `service.c` `service_shall_restart`: `case
  SERVICE_RESTART_ALWAYS: return s->result != SERVICE_SKIP_CONDITION;` — a
  clean exit 0 is restarted; only `forbid_restart` (manual stop) and
  `RestartPreventExitStatus=` prevent it. Local `systemd.service(5)` table
  agrees ("Clean exit code or signal: always ✓").
- systemd v259 `service.c`: the watchdog is (re)armed in
  `service_enter_start_post` (`service_reset_watchdog`, line 2428), i.e. after
  start-up completes, or on the first `WATCHDOG=1` (line 5071). Local
  `WatchdogSec=` man text: "The watchdog is activated when the start-up is
  completed."
- systemd v259 `job.c:784-805` and `unit.c:6525` (`unit_find_failed_condition`):
  for a unit whose conditions are ALL `|` trigger conditions, the journal
  line is `"<ident> was skipped because no trigger condition checks were
  met."` (job.c:790); the `"… unmet condition check (<type>=<param>)"` form
  (job.c:801) is used only for a failed NON-trigger condition. `"Condition
  check resulted in %s being skipped."` (job.c:678) is the console/status
  format. `unit_test_condition` (unit.c:1785) stamps `condition_timestamp`
  on every evaluation.
- systemd v259 `unit.c:4053` `unit_kill`: common to every unit type with a
  cgroup context; `--kill-whom=all --signal=SIGKILL` reaches
  `cg_kill_kernel_sigkill(crt->cgroup_path)` — a slice IS killable.
- Local `systemctl(1)`: `cancel [JOB...]` — "If no job ID is specified,
  cancel all pending jobs."; `--kill-whom=` present.
- Local `apt-get(8)` `-s`: "Locking will be disabled (Debug::NoLocking)";
  `dpkg(1)`: `DPKG_FRONTEND_LOCKED` "notify dpkg that it should not acquire
  the frontend lock (since dpkg 1.19.1)"; `--audit` is a read-only check.
- Offline scratch-root control (local systemd 257): with ONLY the probe
  units and their `.d/50-docker-engine-guard.conf` drop-ins under
  `<root>/usr/lib/systemd/system` and `<root>/etc/systemd/system`,
  `systemd-analyze verify --root=<root> probe.service probe.socket` exits 1
  with `Failed to create probe.service/start: Unit sysinit.target not
  found.`; with the drop-in moved to a WRONG directory
  (`probe.sock.d/`) verify prints nothing about it; with a typo key in a
  correctly placed drop-in it warns `Unknown key 'ConditionPathExist' …
  ignoring`. `systemctl --root=<root> cat` is refused on 257 ("Verb 'cat'
  cannot be used with --root="), but v259 `systemctl-edit.c:38-58`
  initialises lookup paths from `arg_root` and runs `cat` client-side,
  printing fragment and drop-in paths.
- poweredge `k3s kubectl get pods -n kube-system -o wide`: `coredns-…`
  1/1 on `poweredge-xubuntu` `10.42.0.88`; the Deployment has `replicas: 1`,
  `nodeSelector` `kubernetes.io/os: linux` only, control-plane toleration,
  hostname `topologySpreadConstraints`. All three nodes `Ready`; gmktec has
  no taint (`ROLES <none>`).
- `livespec-dev-tooling/ansible/roles/docker_sandbox_slice/tasks/main.yml:168-179`
  rewrites `daemon.json` as `existing | combine({'cgroup-parent': …}) |
  to_nice_json` after Docker exists; its own comment (lines 200-203) says an
  already-correct file "whose formatting this role did not choose is a byte
  change".

## Ranked findings

### BLOCKER 1 — `Restart=always` restarts the FINISHED actor forever; every terminal state becomes a 5-second respawn loop, including every boot after confirmation and `rollback-partial`

Evidence: `design-rev4.md:433-438` ("`Restart=always`, `RestartSec=5`, and
`StartLimitIntervalSec=0` … `ExecStart` exits 0 only after recording a
terminal state … `SuccessExitStatus=` is not widened"); `design-rev4.md:
422-426` (boot recovery is the same unit, `Before=` the three units);
`design-rev4.md:443-449` (restart-in-rollback resumes at the first phase
whose postcondition fails; a phase that keeps failing ends `rollback-partial`);
v259 `service_shall_restart` (`SERVICE_RESTART_ALWAYS: return s->result !=
SERVICE_SKIP_CONDITION`); local `systemd.service(5)` Restart table.

R3 fixes round 3's rate-limit gap by never giving up on the actor, and then
specifies that the actor exits 0 on a terminal state. systemd honours both:
the clean exit is restarted after 5 s, with no start limit, forever. The
restarted actor reads `confirmed` (R1), finds the run committed, "finishes
confirmation" idempotently, exits 0, and is restarted again. Three concrete
consequences:

1. After the happy path, gmktec runs a root process every 5 seconds for the
   rest of its uptime, and because boot recovery is the same unit (R2), it
   does so from every boot thereafter — `WantedBy`/`Before=` ordering starts
   it at boot, it exits 0, and the loop begins.
2. Under `rollback-partial` the loop is not idle: R3 says a restart during
   rollback "resumes at the first rollback phase whose POSTCONDITION does not
   hold now". The phase that could not complete is exactly such a phase, so
   every 5 seconds plus its deadline the actor re-issues `systemctl kill`,
   `iptables -D` passes and interface deletions against the live CI node,
   while Mechanism 6's "refuse until an operator acknowledges" row assumes a
   quiescent host. Whether `rollback-partial` is treated as terminal (exit 0,
   loop) or as in-rollback (retry, loop) is unspecified; both loop.
3. The controller's "starts the actor unit" and "RESUMES that run" (R2) act
   on a unit that is never `inactive` — it is `active` or `activating
   (auto-restart)` — so `systemctl start` is a no-op or races the respawn,
   and the design's `ActiveState`-based checks on it are undefined.

Required: `RestartPreventExitStatus=0` on the unit (keeping `Restart=always`
so SIGTERM/SIGHUP/SIGINT — "clean" signals that `on-failure` does NOT
restart — still restart it), or equivalently `Restart=on-failure` plus
actor-installed handlers that turn those signals into a non-zero exit. And
one sentence of contract: an actor that starts and finds a recorded terminal
state (`confirmed`, `rolled-back`, `rollback-partial`) verifies nothing,
mutates nothing and exits 0; `rollback-partial` is terminal and is re-entered
only by the acknowledged repair path. Add the acceptance case "after each
terminal state the unit is `inactive` 30 s later and the journal shows no
further start".

### SHOULD-FIX 2 — The watchdog is armed only when start-up completes; the design never says when `READY=1` is sent, and `TimeoutStartSec=infinity` bounds nothing before it

Evidence: `design-rev4.md:430-432` ("`Type=notify`, `NotifyAccess=main`,
`WatchdogSec=60` … killed and restarted by systemd if it stops making
progress"); `design-rev4.md:147` (`TimeoutStartSec=infinity`, retained);
`design-rev4.md:422-426` (`Before=` the three units in recovery mode); v259
`service.c:2428` (`service_reset_watchdog` in `service_enter_start_post`),
`service.c:5071` (first `WATCHDOG=1`); local `WatchdogSec=` man text.

A `Type=notify` service is `activating` until it sends `READY=1`; the
watchdog event source is installed at start-up completion (or on the first
`WATCHDOG=1`). A hang BEFORE that point — the lock, the first state write,
the `confirmed` read, a rollback phase if `READY=1` is deferred — is bounded
only by `TimeoutStartSec`, which the design sets to infinity. The `Before=`
ordering pulls the other way: it holds Docker's boot start only until the
actor's start JOB completes, i.e. until `READY=1`, so a recovery actor that
sends `READY=1` first thing makes `Before=` vacuous, and one that sends it
last runs its whole rollback unsupervised. The design says Mechanism 1 makes
`Before=` non-load-bearing (`design-rev4.md:152-153`), which is right, so
resolve it in that direction: specify that the actor sends `READY=1`
immediately after acquiring the lock and before any other work, sends
`WATCHDOG=1` from a thread or a polling loop so a 60-second bounded
subprocess wait cannot itself starve the 60-second watchdog, and state that
`Before=` is advisory. Then `TimeoutStartSec=infinity` can stay (it covers
only the lock acquisition) or become a small finite value.

### SHOULD-FIX 3 — R5's instruments: `systemd-analyze verify --root` cannot pass on the scratch root as described and cannot fail on a misplaced drop-in; the journal string the positive control looks for is not the string systemd writes for `|` conditions

Evidence: `design-rev4.md:495-499` (step 2) and `503-505` (step 3); the
offline scratch-root control above; v259 `job.c:784-805`,
`unit.c:6525-6542`, `unit.c:1785`.

Step 2. Extracting the audited `.deb` unit files into a scratch root and
running `systemd-analyze verify --root=<scratch>` on them fails for a reason
unrelated to the drop-ins (`Unit sysinit.target not found`: default
dependencies pull in the host's unit tree), so an implementer must copy
`/usr/lib/systemd/system` into the scratch root to make it pass — after
which it passes WHETHER OR NOT the drop-in is in the right directory (the
misplaced-drop-in control printed nothing). It does catch a typo inside a
correctly placed drop-in. So as a proof that "the REAL drop-ins will load"
it is the catalogue's instrument-cannot-hit trap: green independent of the
property. The instrument that does return a hit on v259 is `systemctl
--root=<scratch> cat containerd.service docker.service docker.socket`, which
runs client-side from the scratch root and prints each unit's fragment path
AND the `# /etc/systemd/system/<unit>.d/50-docker-engine-guard.conf` drop-in
header — require all three drop-in headers to appear, with the unit names
taken from `dpkg-deb -c` of the audited `.deb` files rather than typed.
Note that the control node's systemd 257 refuses `cat --root`; the hosts'
259 accepts it (`systemctl-edit.c:38-58`), so run it on the target host.
Keep `verify` for drop-in syntax only, on a scratch root that includes the
host unit tree.

Step 3. The drop-in's two lines are both `|` trigger conditions.
`unit_find_failed_condition` returns the failed TRIGGER, and `job.c:790` then
logs `"<unit description> was skipped because no trigger condition checks
were met."` The design's expected `"condition ... was not met"` text and the
round-3 `"Condition check resulted in … being skipped"` text (console
format, job.c:678) will both return zero journal hits, and the role would
refuse after `dpkg -i` with inert packages installed — fail-closed, but it
blocks the converge on a mis-aimed grep. Use the structured fields instead of
prose: for each unit, `journalctl -o json _PID=1 UNIT=<unit> JOB_TYPE=start
JOB_RESULT=done --since <install start>` must return a record, and the
property triple `ConditionTimestamp` SET (stamped by `unit_test_condition` on
the postinst's attempt) + `ConditionResult=no` + `ExecMainStartTimestamp`
EMPTY on both services proves "a start was attempted, the gate evaluated
false, nothing ran" without any string match. The postinst attempt does
occur: `deb-systemd-helper enable` precedes `invoke-rc.d docker start`, and
`invoke-rc.d` starts an enabled unit (`/usr/sbin/invoke-rc.d:383-390,504`),
pulling `docker.socket` in through `Requires=`, so three skip records are
expected (containerd from its own postinst, socket and service from docker's).

### SHOULD-FIX 4 — `systemctl cancel` with no job id cancels EVERY pending job on the host

Evidence: `design-rev4.md:468` ("cancel any queued start job for the three
units (`systemctl cancel`)"); local `systemctl(1)` `cancel [JOB...]`: "If no
job ID is specified, cancel all pending jobs."

Written as `systemctl cancel`, rollback phase 3 cancels whatever else is
queued on a live CI node at that instant — a k3s-agent restart job from
`agent-rejoin-watchdog.timer`, a timer's service activation, a stop another
operator issued. Specify `systemctl list-jobs --output=json`, filter on the
three unit names, and `systemctl cancel <id>` per job; treat "no job" as
success.

### SHOULD-FIX 5 — "The same unit started with `--recover`" cannot be expressed, the forward-phase entry condition is unspecified, and controller-side run allocation is not mechanically exclusive

Evidence: `design-rev4.md:413-414` (ONE actor unit, not a template),
`422-426` (boot recovery "is the same unit started with `--recover`"),
`415-419` (controller allocation rule), `458-460` (acceptance: two concurrent
controller starts).

A unit has one `ExecStart`; `systemctl start` cannot pass a flag. The intent
is sound and implementable, but the design must say how: the actor derives
its mode from state, and a FORWARD phase is entered only when a
controller-written intent token exists on tmpfs (for example
`/run/docker-engine-guard/<run-id>/go`, created by the controller after
`installed-inert`), so that a boot — where `/run` is empty — can only ever
recover. Without that rule, a boot with state `installed-inert` (controller
died before starting the actor) starts a 25-minute unattended Docker window
with no controller to answer the challenge. Separately, R2 makes ACTORS
exclusive through `owner.lock`, but the controller's pre-actor steps (writing
`current-run`, `prepared`, the fence, `dpkg -i`) are serialized only by the
dpkg frontend lock; two controllers can both pass the `current-run` check
before either writes it. Allocate `current-run` with an `O_EXCL` create (or
have the controller's host-side helper take the same `owner.lock` for the
pre-actor sequence and release it before the actor starts), so the
acceptance case has a mechanism to pass on rather than a timing to win.

### SHOULD-FIX 6 — `confirmed` binds a configuration digest, but the next role in the committed order rewrites `daemon.json`, and Mechanism 6 has no row for "confirmed, configuration differs"

Evidence: `design-rev4.md:392-393,400-402` (`confirmed` holds the
configuration digest; a mismatch is a refusal), `251` (Mechanism 6 row 3:
"`confirmed` present and configuration matches: validate only"), `289-291`
(fresh-host order: `docker_engine`, then "the slice role's daemon-dependent
half"); `docker_sandbox_slice/tasks/main.yml:168-179,200-203`.

The slice role's daemon-dependent half re-serialises `daemon.json` with
`to_nice_json` even when every key is already correct, which its own comment
calls a byte change. If the digest is over file bytes, the first converge
after the slice role runs sees `confirmed` naming "another digest", and the
design's only stated response is refusal — every subsequent `docker_engine`
run on gmktec refuses. If the digest is over the role's OWN keys parsed
semantically, this is a non-event. Say which, and add the missing row: after
the commit point Docker is an ordinary enabled service, so "confirmed,
configuration differs" is either a validate-only no-op on the role-owned keys
or an explicit post-commit reconfiguration path — never a guarded-transition
refusal.

### SHOULD-FIX 7 — The frontend-lock helper has no lifetime owner, and the 30-minute timer restore can fire inside the run and catch up a missed elapse immediately

Evidence: `design-rev4.md:509-513` (helper holds the lock "from the audit
through the install"; no deadline, no owner), `530-534` (transient restore
after 30 minutes), `155-158` (budgets: `N` 1500 s plus start/canary/window,
rollback up to ~400 s); gmktec apt timers `Persistent=yes`, `AccuracyUSec=
1min`; `k3s-agent.service` `Restart=always` style of long-lived units.

Two gaps, same shape as the round-3 timer finding. (a) If the controller
dies while the helper holds `lock-frontend`, the lock is held until something
kills the helper: every nightly `unattended-upgrade` and any `apt` on the
host then fails on the lock, silently pausing security updates — the exact
condition R6's timer clause was written to prevent. Run the helper as a
transient unit with `RuntimeMaxSec=` (a bound somewhat above the audit+install
budget) and kill it in the role's `always` block; the bound is safe because
`dpkg -i` still holds `/var/lib/dpkg/lock` itself, so a helper that expires
mid-install only exposes apt to an ordinary "could not get lock" failure, not
to a concurrent write. (b) The 30-minute restore is measured from the fence,
and a run can legitimately last install + `N` (1500 s) + rollback — longer
than 30 minutes — so the apt timers can come back during the observation
window or the rollback, and with `Persistent=yes` a timer whose elapse was
missed while stopped fires its service at once. An `apt-daily-upgrade` run
then races the window (an upgrade of `containerd` would `deb-systemd-invoke
restart` it while `allow-start` exists). Set the restore deadline to the
worst-case run plus margin, or have the actor restore the timers at its
terminal state with the transient timer as the backstop only.

### SHOULD-FIX 8 — The R5 step-1 probe creates the exact file that defeats the gate; its removal must be asserted immediately before `dpkg -i`

Evidence: `design-rev4.md:489-494` ("create a test permission path, start it
again and require it to run; remove the probe and the test path"),
`452-455` (invariant: `allow-start` is created by the actor as the first act
of `starting`).

The probe's drop-in is "identical", so its test permission path IS
`/run/docker-engine-guard/allow-start` (or `confirmed`). A probe cleanup
that fails or is skipped leaves a permission in force that the postinst's
`invoke-rc.d docker start` will honour — Docker running under the role's
`daemon.json` with no actor, the state the design exists to prevent. Make the
pre-`dpkg -i` gate assert that neither permission path exists and that
`/var/lib/docker-engine-guard/confirmed` is absent, put the probe cleanup in
an `always` block, and record the probe's creation of the real path in the
run's `intended` record so a later run can tell a leftover probe permission
from an actor's.

### NOTE 9 — R6 accuracy: there is no systemd unit-directory dpkg trigger on this OS; the reload the install relies on is `containerd.postinst`'s, and the lock must be an fcntl lock

Evidence: hp and gmktec `/var/lib/dpkg/info/systemd.triggers` (catalog,
binfmt.d, sysctl.d, libc-upgrade only); `containerd.postinst` (`systemctl
--system daemon-reload`); `docker.io.postinst` (no reload); `apt-get(8)`
`-s` disables locking; `dpkg(1)` `DPKG_FRONTEND_LOCKED`.

`design-rev4.md:525-526` says the direct `dpkg -i` path runs "the systemd
unit-directory trigger [which] runs a daemon-reload". No such trigger exists
on 26.04. The gate still holds for two independent reasons: `dpkg -i` unpacks
all three packages before configuring any, and `containerd.postinst` (configured
before `docker.io` by dependency) daemon-reloads with `docker.service` already
on disk; and since v246 the manager rebuilds its unit name map when a unit
directory's mtime changes, so a first `systemctl start docker.service` loads
the fragment and its drop-ins regardless. Correct the sentence so the
implementer does not look for a trigger that cannot fire. Two implementation
notes: apt and dpkg use POSIX record locks (`fcntl`), so the helper must use
`fcntl.lockf`, not `flock` (the two families do not conflict on Linux); and
because `apt-get -s` as root disables locking, the audit can run under the
helper's lock as R6 says.

### NOTE 10 — Rollback mechanics confirmed, with two implementation cautions

Evidence: v259 `unit_kill` (cgroup-context units, `cg_kill_kernel_sigkill`);
`docker.service` `Requires=docker.socket`, `TimeoutSec=0`.

`systemctl kill --kill-whom=all --signal=SIGKILL fabro-sandbox.slice` is
valid: slices carry a cgroup context and the SIGKILL arm uses the kernel's
`cgroup.kill`. Cautions: (a) `systemctl stop docker.socket` in phase 1
propagates a stop to `docker.service` (`Requires=`), and the socket's stop
job is ordered AFTER the service's, so with a hung `dockerd` and
`TimeoutSec=0` the phase-1 command blocks until phase 3's SIGKILL — use
`--no-block` for the socket stop so phase 2 is not delayed by it. (b) If the
unit uses `RuntimeDirectory=docker-engine-guard`, systemd removes
`/run/docker-engine-guard` (and `allow-start` with it) every time the actor
stops, including before an auto-restart unless `RuntimeDirectoryPreserve=`
is set; that is fail-closed and arguably desirable, but the design should
choose it explicitly rather than inherit it.

### NOTE 11 — R8 probe details

Evidence: gmktec `k3s-agent.service` `ExecStart`; root-only
`/etc/rancher/k3s/config.yaml` + `config.yaml.d/` + `k3s-agent.service.env`;
poweredge CoreDNS Deployment (`replicas: 1`, no node pin); gmktec `Ready`,
no taint.

- The "effective k3s agent flags" are not on the command line on gmktec; the
  role must read `config.yaml`, `config.yaml.d/*` and the env file as root to
  record `kube-proxy-arg`/`flannel` sources, or it will record defaults and
  call them measured.
- CoreDNS is a single replica with no node pin; if it is rescheduled onto
  gmktec during the window the DNS probe keeps passing locally, so the
  "cross-node" property is a preflight fact, not a window-long guarantee.
  Harmless (fail-open only for that one property), worth stating.
- The challenge must be read, three controller probes run (a fresh Tailscale
  SSH session, the LLM `/health`, a LAN login through poweredge) and the
  answer written within 120 s of issue, through a controller that polls the
  state file. A slow Tailscale handshake turns into a full rollback. Either
  allow the actor to re-issue one challenge within `N`, or bound the answer at
  300 s — freshness for this purpose is unchanged.

### NOTE 12 — Minor wording in R1

`design-rev4.md:387-389` says at most one permission is in force at any
moment; between the atomic creation of `confirmed` and the removal of
`allow-start` both exist. Harmless (they grant the same thing), but the
sentence should say "before the commit point only `allow-start`; from the
commit point `confirmed`, with `allow-start` removed as the first
finalization step".

### NOTE 13 — Units are ENABLED by the postinst; the confirm-step `enable` is a no-op and a rolled-back host carries three condition-skipped boot starts forever

Evidence: `docker.io.postinst` and `containerd.postinst` `deb-systemd-helper
enable` sections; `invoke-rc.d:376-390`.

`dh_installsystemd` enables all three units on first install, which is what
makes the postinst start attempt happen at all (invoke-rc.d's local policy
refuses to start a disabled unit). After a rollback the units stay enabled
and are skipped by the condition at every boot (`docker.socket` from
`sockets.target`, the services from `multi-user.target`); that is safe and
expected, but the journal will carry three skip lines per boot indefinitely
and Mechanism 6's "validate only" should not read an enabled-but-inactive
unit as a fault. State it so a future operator does not "fix" it by removing
the drop-ins.

## Verdict per round-3 finding — Fable reviewer

1. **NOT RESOLVED** — rate limit, backoff, per-phase exception handling,
   exit-code contract and forward-restart semantics are all now specified,
   but `Restart=always` with an exit-0 terminal contract respawns the
   finished actor forever (BLOCKER 1); the fix is one line plus one sentence.
2. **RESOLVED in mechanism, NOT RESOLVED in instrument** — the throwaway
   probe unit, the path/mode check and the post-install journal control are
   the right structure; `systemd-analyze verify --root` cannot pass as
   described and cannot fail on misplacement, and the journal text expected
   cannot match a `|` condition (SHOULD-FIX 3).
3. **RESOLVED** — R4 scopes the comparison to built-in chain policies, the
   built-in chains' own rules and `ts-*`, never reconciler-owned chains.
4. **RESOLVED** — R8 resolves on the host, connects by IP with explicit SNI,
   uses an unquota'd archive mirror, and parses DNS without a resolver file.
5. **RESOLVED** — R7 writes `intended` before the first package mutation and
   reconciles actual state against it.
6. **RESOLVED** — R2: one non-template unit plus a non-blocking `flock`;
   the mode-selection gap is SHOULD-FIX 5, not a second actor.
7. **RESOLVED** — R8 resolves the slice cgroup through `ControlGroup`.
8. **RESOLVED** — R8 records the shim inventory and PIDs and checks them per
   sample and after phase 3.
9. **RESOLVED** — R4 phase 1 stops `docker.socket` right after removing
   `allow-start` (use `--no-block`, NOTE 10).
10. **RESOLVED** — whitespace canonicalization and per-table `DOCKER` handled.
11. **RESOLVED** — index SHA256 and control `Version:` checks added; the
    trigger sentence is inaccurate (NOTE 9) but not load-bearing.
12. **RESOLVED** — one immediate re-probe, failure recorded with probe and
    cause.
13. **RESOLVED** — accuracy items absorbed.

## Verdict per round-3 finding — Codex reviewer

1. **RESOLVED** — R1 defines the atomic creation of `confirmed` as the single
   commit point, `state.json` as derived, and recovery as finalize-only after
   it.
2. **RESOLVED for actors, gap for controllers** — the `flock` and the
   single unit make two actors impossible; the `--recover` flag is not
   expressible and controller-side allocation is not exclusive (SHOULD-FIX 5).
3. **RESOLVED in intent, NOT RESOLVED as specified** — watchdog, no start
   limit, backoff, bounded subprocesses and the signal/exit contract are
   present, but the watchdog is armed only at start-up completion with
   `READY=1` timing unspecified (SHOULD-FIX 2) and the exit contract loops
   (BLOCKER 1).
4. **RESOLVED** — R6 holds `lock-frontend` through audit and install with
   `DPKG_FRONTEND_LOCKED=1`, refuses pending triggers and `dpkg --audit`
   findings, scopes recovery to this run's packages, and persists timer
   state; the helper's lifetime and the restore timing remain (SHOULD-FIX 7).
5. **RESOLVED in structure, NOT RESOLVED in instrument** — as Fable item 2
   (SHOULD-FIX 3); outstanding start jobs are now cancelled, but the bare
   `cancel` cancels everything (SHOULD-FIX 4).
6. **RESOLVED** — node status subresource, server-side CoreDNS placement
   read, nonce challenge/response at the end of the window.
7. **RESOLVED** — R9 defines the exclusive-admission predicate (empty
   `docker` group, canary-only container list, built-in networks allowed,
   canary veth identified) and downgrades to `rollback-partial` on anything
   unexpected.
8. **RESOLVED** — R7 state list with `intended` before mutation.
9. **NOT RESOLVED** — companion play/inventory/slice split and the stale
   host records remain prerequisites by the design's own statement
   (`design-rev4.md:599-607`); the converge must gate on their merge.
10. **RESOLVED** — firewall selection unchanged and re-verified; final
    whole-predicate re-check after quiescing is implied by R4's "verify no
    process remains … no job is queued" and the residue check.
11. **RESOLVED** — accepted as stated; the QEMU acceptance still cannot
    exercise kube-router/kube-proxy/flannel coexistence, which the design
    records.

REVIEW-COMPLETE: BLOCKERS
