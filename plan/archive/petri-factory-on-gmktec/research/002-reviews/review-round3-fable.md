# Independent review, round 3 — Docker on gmktec-xubuntu (design revision 3)

Reviewed 2026-10-15 by a reviewer with no part in the design. **Two BLOCKERS
remain; do not converge revision 3 on gmktec as written.** Both are narrow and
cheap to fix, and the central mechanism (a `ConditionPathExists=|` OR drop-in
on all three units, one host-local actor) is sound: I verified it against the
systemd v259 source the hosts actually run and against hp's live package
scripts. What is not yet sound is (1) the actor's crash-resume guarantee, which
systemd's default start-rate limit silently cancels, and (2) the pre-install
verification of the drop-ins, which uses an instrument that cannot return a hit.

Scope: design review, not implementation acceptance. Nothing on any host,
repository or ledger was changed; this requested, gitignored report is the only
file written. Remote commands were restricted to the brief's allowed reads
(`cat`, `ls`, `systemctl is-active|is-enabled|cat|status`, `ip`, `sudo -n
iptables -S`, `sudo -n iptables-save` on hp, `sudo -n ss -ltnp`, `dpkg`,
`apt-cache`, `dockerd --help`, `sudo k3s crictl ps`). No install, simulation,
restart, kill, rollback, container launch or pod exec was performed. Upstream
sources read: systemd `v259` `src/core/{job,unit,socket}.c`; moby
`docker-v29.1.3` `daemon/config/config_linux.go`, `daemon/daemon_unix.go`.
`design.md` means revision 3 in this directory.

Facts measured this round that the findings rest on:

- Both hosts run **systemd 259** (`259.5-0ubuntu3.4`), not 258.
- gmktec: every k3s shim (five `containerd-shim-runc-v2 -namespace k8s.io
  -address /run/k3s/containerd/containerd.sock`) and k3s's containerd sit in
  `/system.slice/k3s-agent.service`; `kubepods.slice` is a sibling of
  `system.slice`; no `docker*`/`containerd*` units, no guard directories, no
  `/etc/cni/net.d`, no `policy-rc.d`; `/etc/resolv.conf` is the
  systemd-resolved stub (`nameserver 127.0.0.53`); `fabro-sandbox.slice` is
  `not-found`; `KUBE-ROUTER-INPUT` (jumped from `INPUT`) carries one per-pod
  rule per ARC listener pod; FORWARD policy ACCEPT; sysctls `1,0,0,1,1`.
- hp: `docker.service` `Requires=docker.socket`, `Wants=containerd.service`,
  `TimeoutSec=0`, `Restart=always`, `StartLimitBurst=3`/`60s`,
  `KillMode=process`, `Delegate=yes`; `containerd.service` `KillMode=process`,
  `Restart=always`. Docker's shims live in `/system.slice/containerd.service`;
  `dockerd` and `docker-proxy` in `/system.slice/docker.service`; containers in
  `/fabro.slice/fabro-sandbox.slice/docker-<id>.scope`. hp's `k3s-agent.service`
  cgroup holds only `k3s agent` and `containerd` — **no shims, no pods**, and
  `sudo k3s crictl ps` fails for want of a crictl config. hp's filter table
  policy is **`FORWARD DROP`** (its `daemon.json` lacks `ip-forward-no-drop`).
- `docker.io.postinst` starts the daemon with `invoke-rc.d docker start || :`
  after `! invoke-rc.d docker status`; it runs no `daemon-reload` of its own.
  `containerd.postinst` runs `systemctl --system daemon-reload` then
  `deb-systemd-invoke start containerd.service`. `invoke-rc.d` under systemd
  executes `systemctl start <unit>`. Neither package ships a `triggers` file.
- systemd v259 `unit.c:1952-1954`: `unit_start` returns `-ECOMM` when
  `unit_test_condition` fails, before any start-limit accounting;
  `job.c:962-963` maps `-ECOMM` to `job_finish_and_invalidate(j, JOB_DONE, …)`.
  `unit_test_condition` re-evaluates the condition list on every call
  (`unit.c:1779-`). `socket.c` performs no condition pre-check before
  `manager_add_job(JOB_START, service)` and re-enters listening when the
  service is not active (`socket_trigger_notify`, `socket.c:3496-3525`).
- moby 29.1.3 `config_linux.go:46-48,81`: keys `ip6tables`, `ip-forward`,
  `ip-forward-no-drop` (`DisableFilterForwardDrop`), `cgroup-parent` exist;
  `daemon_unix.go:591-602`: cgroup driver defaults to `systemd` on cgroup v2
  under systemd.
- Local control (systemd 257, same property model): `systemctl show -p
  ConditionPathExists apport-autoreport.service` prints **nothing** for a unit
  whose file carries `ConditionPathExists=/var/lib/apport/autoreport`; the
  D-Bus property is `Conditions` and `show` renders it `[unprintable]`;
  `ConditionResult=no` is what `show` does expose. A not-found unit reports
  `LoadState=not-found`.
- `https://api.github.com/zen` answers with `x-ratelimit-limit: 60` per hour
  for unauthenticated callers.

## Ranked findings

### BLOCKER 1 — `Restart=on-failure` does not make the actor resumable: systemd's default start-rate limit stops it after five attempts, and the design specifies no exit-code or exception contract

Evidence: `design.md` Mechanism 2 ("`Restart=on-failure` … if it does die,
`Restart=on-failure` resumes it from `state.json`"; "A rollback phase that
exceeds its deadline is recorded and the actor proceeds"); local
`systemd.unit(5)` `StartLimitIntervalSec=`/`StartLimitBurst=` defaults (5 starts
in 10 s, after which the unit enters `failed` and is no longer restarted); hp's
`docker.service` shows the same mechanism configured explicitly
(`StartLimitBurst=3`, `StartLimitInterval=60s`).

The design's crash-safety argument is: atomic `state.json` + `Restart=on-failure`
+ idempotent phases = any kill resumes from the first incomplete phase. That
holds for a one-off kill. It does not hold for the realistic failure, which is
a DETERMINISTIC crash — an unhandled exception at the same point every time —
because systemd restarts a crash-looping unit five times in ten seconds and
then marks it `failed` permanently. From that moment nothing resumes the
rollback: `Restart=` is exhausted, the boot copy needs a reboot the maintainer
may be unable to request if access is the thing that broke, and the controller
polls a `state.json` that never reaches `rolled-back` or `rollback-partial`.
The design's "proceeds to the next phase" rule covers deadline OVERRUN only; it
says nothing about an exception inside a phase, and a Python actor that lets an
exception escape exits non-zero and is restarted into the same exception.

This is not hypothetical for gmktec specifically. Rollback phase 4 parses the
live `iptables-save` of a kube-router/kube-proxy/flannel/tailscale/ipset
ruleset (153 IPv4 rules today, including `-m set --match-set …`, `-m physdev`,
`-m nfacct --nfacct-name  ct_state_invalid_dropped_pkts` with a double space in
hp's output, and `NFLOG --nflog-prefix "…"` quoted strings). The QEMU
acceptance run in "Acceptance before the gmktec converge" has no k3s, so a
parser that chokes on a gmktec-only token is exactly the case the acceptance
cannot catch, and it would fire in the phase after the access-critical ones —
leaving Docker's chains and `docker0` in place with the actor dead.

Two further gaps in the same contract:

- Exit codes are unspecified. If the actor exits non-zero on `rolled-back`
  (a failed transition is a failure from the play's point of view),
  `Restart=on-failure` restarts a FINISHED actor; if it exits 0 after an
  unexpected error, nothing restarts it. The actor must exit 0 on every
  terminal state it has recorded and non-zero only when it has not recorded
  one.
- A restart during a FORWARD phase has no stated semantics. "Resumes from the
  first incomplete phase" is written for rollback. An actor restarted while in
  `starting`/`canary`/`observing` must roll back, not continue; one restarted
  after `confirmed` was written must finish the confirm steps idempotently. The
  boot copy's "resumes any run whose state is neither `confirmed` nor
  `rolled-back`" is ambiguous in the same way.

Required: `[Unit] StartLimitIntervalSec=0` (or a burst sized to the phase
retries) and a `RestartSec=` backoff on the actor unit; a per-phase
`try/except` that records the exception in `state.json` and proceeds, matching
the deadline rule; an explicit exit-code contract; explicit forward-phase
restart semantics; and a fault-injection case "actor raises in rollback phase
4 on every attempt" that must still end in `rollback-partial` naming phase 4
with phases 5-7 completed. Also state `Type=` for the unit: with
`Type=simple`/`exec`, `TimeoutStartSec=infinity` is a no-op and the relevant
setting is that no `TimeoutStopSec`-driven kill can interrupt rollback.

### BLOCKER 2 — The pre-install verification of the drop-ins cannot return a hit, and the post-install verification runs after the postinst has already attempted the start

Evidence: `design.md` Mechanism 1 ("The role verifies the drop-ins are loaded
(`systemctl show -p ConditionPathExists` on each unit) before the install");
local control above (the property prints nothing for a unit that has the
condition; a unit without a fragment is `not-found`);
`docker.io.postinst` (`invoke-rc.d docker start || :`); `invoke-rc.d`
systemd branch (`systemctl $sctl_args "${saction}" "${UNIT}"`).

Mechanism 1 is the design's whole claim that the install is "network-inert by
construction", and it is decided at one point: the postinst's `systemctl start
docker.service` meeting an unmet condition. The verification the design places
in front of that point is vacuous twice over. First, `systemctl show -p
ConditionPathExists` is not a property name; it prints an empty result for
every unit, including units that carry the condition, so a check written
against it passes or fails independently of whether the drop-in loaded.
Second, before the install there IS no `docker.service`, `docker.socket` or
`containerd.service` fragment to load, so systemd reports them `not-found` and
drop-ins are never consulted; no instrument can verify "loaded" for a unit
that does not exist. The post-install check ("all three units are inactive")
is real evidence, but it is taken AFTER `dpkg -i` has run the postinst's start
— if the drop-in was misplaced (wrong `.d` directory, a file not ending in
`.conf`, written after rather than before), Docker is already running with
the role's `daemon.json`, with no actor, no window and no rollback: the one
state the design exists to prevent.

This is the catalogue trap of a control that proves an instrument FUNCTIONS
without proving it is AIMED: "the command succeeded" is not "the condition is
in force". Required, in place of the stated check:

1. Prove the MECHANISM before touching the host: start a throwaway unit
   (`docker-engine-guard-probe.service`, `ExecStart=/bin/true`) carrying the
   identical two `ConditionPathExists=|` lines through an identical drop-in
   layout; require `systemctl start` to exit 0, `ActiveState=inactive`,
   `ConditionResult=no`, and `ExecMainStartTimestamp` unset; then create the
   `allow-start` path, start it again and require it to run. Remove the
   probe unit afterwards.
2. Prove the REAL drop-ins will load before `dpkg -i`: extract the audited
   `.deb`s' unit files (`dpkg-deb -x` into a scratch root), copy the drop-ins
   beside them, and run `systemd-analyze verify --root=<scratch>` against the
   three units; and check the drop-in paths byte-for-byte
   (`/etc/systemd/system/<unit>.d/<name>.conf`, mode 0644, for all three
   unit names including the `.socket`).
3. After `dpkg -i`: `systemctl cat` lists the drop-in for each unit;
   `ConditionResult=no`, `ActiveState=inactive`, `ExecMainStartTimestamp`
   unset on the services; `docker.socket` has no listener in `ss -ltnxp`;
   and the journal shows the three "Condition check resulted in … being
   skipped" lines from the postinst's start attempt — that line is the
   positive control that the gate actually fired.

Note for the implementer: `docker.io.postinst` does not `daemon-reload`;
`containerd.postinst` (configured first by dependency order) does, and
systemd ≥ 246 also reloads its unit-path cache on directory mtime change, so
the drop-ins are picked up either way. That is why the mechanism works; it is
not why the stated verification does.

### SHOULD-FIX 3 — Probe 4's "INPUT … change fails the probe" will trip on healthy ARC pod churn unless it is scoped to the built-in chain's own rules

Evidence: fresh gmktec `sudo -n iptables -S INPUT` (seven stable jump rules)
and `sudo -n iptables -S KUBE-ROUTER-INPUT` (three stable rules plus ONE
`-s <podip>/32 … -j KUBE-POD-FW-<hash>` rule PER POD, five today, all
`arc-systems` listener/controller pods); profile capacity 12 churn slots.

`INPUT` jumps to `KUBE-ROUTER-INPUT`, and kube-router adds and removes a rule
there every time a pod is created or deleted on this node. If "a change in
INPUT" means the chains reachable from INPUT, every ARC job start or finish
during the 420-second window fails the sample, the window can never pass on a
busy CI node, and the actor executes a full rollback (SIGKILL plus up to sixty
`iptables -D` commands on the live host) for a non-event. If it means only the
built-in `INPUT` chain's own rule list, the comparison is stable. The design
does not say which. Specify the comparison set exactly: built-in chain POLICY
for all five chains in both families, the built-in `INPUT` and `FORWARD`
chains' own rules, and the `ts-input`/`ts-forward`/`ts-postrouting` chains'
contents — never a chain whose contents a reconciler owns. Apply the same
scoping to the snapshot diff in Mechanism 4 so that kube-router's per-pod
chains created during the window are not mistaken for residue.

### SHOULD-FIX 4 — The pod-namespace HTTPS probe cannot resolve names as specified, and its endpoint is rate-limited below the design's own sample count

Evidence: gmktec `/etc/resolv.conf` → `/run/systemd/resolve/stub-resolv.conf`,
`nameserver 127.0.0.53`; `design.md` Mechanism 3 item 3 ("from `nsenter -t
<pid> -n` with host binaries … an HTTPS request to
`https://api.github.com/zen`"), window 420 s at 15 s → 28 samples plus
preflight; `x-ratelimit-limit: 60`.

`nsenter -n` enters only the network namespace. A host binary resolving
`api.github.com` there reads the host's `resolv.conf` and sends to 127.0.0.53
— which inside the pod's namespace is the POD's loopback, where nothing
listens. The probe fails at preflight, which is a refusal (safe) but blocks
the whole transition until the implementer "fixes" it, and the obvious fix
(resolve on the host, connect by IP in the namespace) must be written down so
it is not improvised. Separately, `/zen` is an unauthenticated API call with a
60-per-hour limit per source address: one run spends 29, so a resume
(Mechanism 6) or a retry after a spurious rollback within the same hour gets
HTTP 403 mid-window, and every sample must pass, so a rate limit becomes a
rollback. Use an endpoint without a per-hour quota (an Ubuntu archive URL, or
a `204` endpoint), resolve explicitly through the cluster DNS ClusterIP inside
the namespace (which doubles as the DNS probe), and treat the canary's egress
endpoint the same way.

### SHOULD-FIX 5 — Write the `installed` record before `dpkg -i`, not after, or an interrupted install is classified as foreign Docker and refused

Evidence: `design.md` Mechanism 6 rows 2 and 5 ("`installed` names this role's
audited set" → resume; "Docker packages or state without this role's
`installed` record" → refuse: never adopted or touched); Mechanism 5 step 3.

If the controller dies between `dpkg -i` returning and the role writing
`/var/lib/docker-engine-guard/installed`, the next run finds packages and no
record and refuses as foreign, with no supported path forward except hand
editing — the same hole round 2's finding 8 was about, moved one step. Write
`installed` (as "intended: <audited set, digests>") BEFORE `dpkg -i`, and have
the resume row require that the installed versions equal the intended set.
The same ordering applies to `confirmed` versus the final `state.json` write
in confirm step 4: write `confirmed` last of the durable writes, which the
design already does, and say so.

### SHOULD-FIX 6 — Refuse to start a new actor instance while any other instance is active, activating or auto-restarting

Evidence: `design.md` Mechanism 2 (template unit
`docker-engine-transition@<run-id>.service`, `Restart=on-failure`; the
controller "starts the actor unit").

An instance for an earlier run that is still in `activating (auto-restart)`
(or crash-looping, see BLOCKER 1) and a fresh instance for a new run-id are
two actors with two state files acting on the same three units and the same
firewall. The design's "one actor" property holds only if the controller
refuses to start an instance while `systemctl list-units
'docker-engine-transition@*'` shows any non-inactive instance, and the boot
copy must do the same check against the runtime instances.

### NOTE 7 — The slice's cgroup is at `/fabro.slice/fabro-sandbox.slice`, not `/fabro-sandbox.slice`

Evidence: hp `systemctl status fabro-sandbox.slice` → `CGroup:
/fabro.slice/fabro-sandbox.slice`; `ls /sys/fs/cgroup/fabro-sandbox.slice` →
no such file.

systemd nests a dash-named slice under its parent. The canary check in
Mechanism 2 ("read that slice's `memory.max` and `cpu.max` from the host")
must resolve the path through `systemctl show -p ControlGroup
fabro-sandbox.slice`, and the canary's `/proc/<pid>/cgroup` line will read
`0::/fabro.slice/fabro-sandbox.slice/docker-<id>.scope`. A literal path is the
instrument-cannot-hit trap again, and it would fail the canary on a healthy
host. On gmktec the slice is `not-found` today, consistent with "slice unit
(systemd only)" being the first step of the fresh-host order.

### NOTE 8 — hp is not evidence that two containerds can share `/run/containerd` beside k3s shims; nothing exercises that before gmktec

Evidence: hp `systemctl status k3s-agent` cgroup holds `k3s agent` and
`containerd` only; `sudo k3s crictl ps` on hp fails (no crictl config);
gmktec holds five k3s shims; `design.md` "Measured state" ("hp-xubuntu: same
OS and the same three package versions beside a k3s agent") and "Acceptance"
("The k3s coexistence itself is not exercised before gmktec").

The design's own disclaimer is correct and the hp sentence is literally true,
but hp's k3s agent runs no pods, so hp demonstrates Docker beside an IDLE
k3s, not beside shims that keep sockets under `/run/containerd/s` and runc
state under `/run/containerd/runc/k8s.io`. My reading of containerd 2.x is
that this is safe — shim socket names are a hash of (containerd address,
namespace, id) and the two daemons differ in address; runc roots are
per-namespace (`moby` versus `k8s.io`); the system containerd reloads tasks
only from its own `/run/containerd/io.containerd.runtime.v2.task/` — and the
kill-by-cgroup argument is independently sound: on gmktec every k3s process
is in `k3s-agent.service` or `kubepods.slice`, so `systemctl kill
--kill-whom=all` on `docker.service`, `containerd.service` or
`fabro-sandbox.slice` cannot reach one. But the shared-directory question is
unmeasured. Cheap direct cover: at preflight inventory `/run/containerd/s`
and `/run/containerd/runc/k8s.io` (root read), and make "no entry
disappeared and every k3s shim PID is still alive in `k3s-agent.service`" a
sample in the observation window and a check after rollback phase 3.

### NOTE 9 — Stop `docker.socket` immediately after removing `allow-start`; a listening socket re-triggers skipped service starts until the trigger limit trips

Evidence: systemd v259 `socket.c:3496-3525` (`socket_trigger_notify` returns
the socket to listening when the service is not active; no condition
pre-check in `socket_enter_running`); `design.md` rollback phase 3 (stop of
`docker.socket` comes after the kills).

Between phase 1 and the end of phase 3, `docker.socket` is still listening.
Any connection to `/run/docker.sock` (a stray `docker` client, the role's own
`docker info`) enqueues a `docker.service` start, which is skipped
(`JOB_DONE`), after which the socket re-enters listening with the connection
still pending and triggers again; systemd's `TriggerLimitBurst` (200 in 2 s)
then fails the socket with `trigger-limit-hit`. Harmless to the host, noisy
in the journal, and avoidable: stop `docker.socket` in phase 1, right after
removing `allow-start`. The `Requires=docker.socket` on `docker.service` is
not a problem in either direction: a condition-skipped socket start is
`JOB_DONE`, so it never fails `docker.service`, and stopping the socket
propagates a stop to the service, which rollback wants anyway.

### NOTE 10 — Mechanism 4's predicates match every Docker rule on hp's live ruleset; `ip-forward-no-drop` and rollback phase 2 are load-bearing

Evidence: hp `sudo -n iptables-save`: filter `FORWARD -j DOCKER-USER`, `-j
DOCKER-FORWARD`; nat `PREROUTING … -j DOCKER`, `OUTPUT ! -d 127.0.0.0/8 … -j
DOCKER`, `POSTROUTING -s 172.17.0.0/16 ! -o docker0 -j MASQUERADE`; raw
`PREROUTING -d 172.17.0.N/32 ! -i docker0 -j DROP` ×10; chains `DOCKER`,
`DOCKER-BRIDGE`, `DOCKER-CT`, `DOCKER-FORWARD`, `DOCKER-INTERNAL`,
`DOCKER-USER`, each rule inside referencing `docker0`. hp's filter policy
`:FORWARD DROP [0:0]`.

Every rule falls under "references `docker0`, `172.17.0.0/16`, or a chain
absent from the snapshot whose name starts with `DOCKER`". hp also shows what
the gmktec configuration must prevent: without `ip-forward-no-drop` the
Ubuntu 29.1.3 build flips FORWARD to DROP (hp's kube traffic survives only
because `KUBE-FORWARD`/`FLANNEL-FWD` accept it first). The key exists in the
29.1.3 source (`config_linux.go:48`), and phase 2's policy restore is the
correct backstop. Two implementation cautions: canonicalize whitespace
identically in snapshot and current (hp's `-m nfacct --nfacct-name
 ct_state_invalid_dropped_pkts` carries a double space), and treat the
`DOCKER` chain name per table (filter and nat both have one).

### NOTE 11 — The apt fence is sound for a `dpkg -i` path; verify the downloaded `.deb`s against the index, not only their maintainer scripts

Evidence: gmktec `apt-cache policy` (all three absent, candidates at the
pinned versions), `apt-cache depends docker.io` (`adduser`, `containerd`,
`iptables`, `debconf`, `libc6`, `libnftables1`, `libsystemd0` — all installed
today except `containerd`), `containerd` → `runc`, `runc` → `libseccomp2`;
`20auto-upgrades` enables both periodic jobs; no `policy-rc.d`.

`apt-get -s` with an exact allowlist followed by `dpkg -i` of the downloaded
set does remove the resolver from the real transaction, and `dpkg -i` runs no
apt hooks, so the hook-digest check is moot but harmless. Add: compare each
downloaded `.deb`'s SHA256 with the `Packages` index entry
(`apt-cache show <pkg>=<ver>` → `SHA256:`) and its control `Version:` with
the allowlist, so the audited bytes are the installed bytes; note that
`dpkg -i` still runs pending triggers (systemd's unit-directory trigger →
`daemon-reload`, man-db), which is expected; and note that `dpkg --configure
-a` on resume re-runs `docker.io.postinst`, whose `invoke-rc.d docker start`
is condition-gated like the first attempt.

### NOTE 12 — Window and sample budget: realistic but brittle; two host-local timers can produce unrelated sample failures

Evidence: gmktec `agent-rejoin-watchdog.timer` (every 60 s; restarts
`k3s-agent` when a "node not found" wedge is unambiguous) and
`reapply-node-extended-resource.timer` (every 5 min; patches Node status);
`design.md` Mechanism 3 ("every sample must pass", 28 samples).

Each sample is an API read, a `crictl inspectp`, three namespace probes, two
`iptables-save` canonicalizations and five sysctl reads — a few seconds, so
15-second cadence is feasible. But 28 consecutive all-pass samples across
three network probes is a strict predicate on a live CI node, and a single
transient (a CoreDNS pod restart on the server, a watchdog-driven
`k3s-agent` restart if poweredge reboots during the window) forces a full
rollback — the riskiest code path in the design — for a cause unrelated to
Docker. Fail-closed is the right default; consider allowing one failed
sample to be re-probed immediately and counted only if it fails twice, and
record the failing probe and its cause in `state.json` so the operator can
tell "Docker broke the pod network" from "CoreDNS restarted".

### NOTE 13 — Minor accuracy items in revision 3

- "systemd 258+": both hosts are at 259. The semantics relied on are the
  same.
- `unit_test_condition` sets `condition_result = true` when
  `manager_get_effective_environment` fails (`unit.c:1788-1790`) — a
  fail-open arm that cannot realistically fire here, recorded for
  completeness.
- `docker.service` has `After=containerd.service`, `Wants=containerd.service`,
  so the actor's separate `systemctl start containerd.service` is correct
  but redundant; keep it, since it gives the 60-second readiness bound a
  per-daemon phase.
- The canary's `--network bridge` DNS works (Docker reads
  `/run/systemd/resolve/resolv.conf` upstream servers when the host uses the
  stub), unlike the pod-namespace probe in SHOULD-FIX 4.

## Verdict per round-1 finding

1. **RESOLVED** — kill-by-cgroup before stop, removal of the start permission first, per-phase deadlines, no systemd start timeout; the remaining resume gap is BLOCKER 1 above, which is a new defect in the fix, not the original hang.
2. **RESOLVED** — one actor, `ConditionPathExists=|` on every start path (verified in v259 source: `-ECOMM` → `JOB_DONE`, re-evaluated per start, `Requires=` unaffected), tmpfs permission covers reboot. Forward-phase restart semantics remain unspecified (BLOCKER 1).
3. **RESOLVED** — confirmed again this round against hp's live rules (NOTE 10).
4. **RESOLVED** — request/reply probes; the probes' own realism is SHOULD-FIX 3-4.
5. **RESOLVED** — timers stopped, audited `.deb` set installed by `dpkg -i`, resume via `dpkg --configure -a` under the same condition gate (NOTE 11).
6. **RESOLVED** — slice unit first, canary cgroup and limits read from the host; mind the nested cgroup path (NOTE 7).
7. **RESOLVED** — both-family comparison, differences recorded not blindly restored.
8. **RESOLVED** — `docker0`-only scope refused at preflight and in probes; no address pools.
9. **NOT RESOLVED** — still a stated convergence prerequisite (carrier `livespec-dev-tooling-2puzjr`); not a defect in this design, but the converge must gate on it.
10. **RESOLVED** — egress policy disclaimed explicitly.
11. **RESOLVED** — Tailscale SSH described correctly; SSH and LLM probes independent.
12. **NOT RESOLVED** — "fixed by a pull request … before the converge" is a plan, not a correction; gate on the merge.

## Verdict per round-2 finding

1. **RESOLVED** — no claim exists; one actor with an atomic state file. The crash-safety of that actor is BLOCKER 1.
2. **RESOLVED in mechanism, NOT RESOLVED in verification** — the condition blocks every start path fail-closed (postinst `invoke-rc.d`, socket activation, `Restart=`, boot), verified in source and against hp's postinst; the design's pre-install verification cannot observe it (BLOCKER 2).
3. **RESOLVED** — audited downloaded set under a fence, `dpkg -i`; add index-hash verification (NOTE 11).
4. **RESOLVED** — no systemd timeout; priority-ordered phases with deadlines; resume after kill — subject to BLOCKER 1's rate-limit gap.
5. **RESOLVED** — pools removed, scope enforced.
6. **RESOLVED** — foreign state refused; canary is the only container and is killed by slice cgroup (hp shows containers do land in the slice scope).
7. **RESOLVED** — host-side read of the canary PID's cgroup; path caveat in NOTE 7.
8. **RESOLVED with one ordering fix** — Mechanism 6 defines the states; write `installed` before `dpkg -i` (SHOULD-FIX 5).
9. **RESOLVED at design level** — Node Ready via credential, re-selection, cross-node DNS, measured `W`; realism defects in SHOULD-FIX 3-4.
10. **RESOLVED** — accepted as stated; predicates re-verified (NOTE 10).
11. **RESOLVED** — accepted as stated.
12. **NOT RESOLVED** — companion play/inventory and host records remain outstanding prerequisites, as the design itself says.

REVIEW-COMPLETE: BLOCKERS
