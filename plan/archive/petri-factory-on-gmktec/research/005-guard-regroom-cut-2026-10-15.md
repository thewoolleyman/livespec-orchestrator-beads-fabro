# 005 — Regrooming livespec-dev-tooling-xxfqqr: the guard goes through the factory

Date: 2026-10-15. Session: petri-factory-on-gmktec.

## Why

xxfqqr was filed as one host-routed item. Research/002's own acceptance section
has two layers: (a) unit tests of the guard's phase machine against a fake host,
and (b) an integration run on a disposable QEMU VM. Layer (a) is ordinary Python
that a factory sandbox can write and test. The capacity coordinator
(gitops-fleet-capacity-monitoring) ruled at 2026-10-15 13:44Z that anything a
factory run can implement and test goes through the factory, and accepted this
regroom. A first record on xxfqqr (12:17:47Z) called the whole item
factory-ineligible; it was corrected on the item, and the correction was sent to
the coordinator.

## The cut

Six factory-safe children carry the guard, and xxfqqr keeps the host-routed
remainder. The design is copied verbatim into livespec-dev-tooling at
docs/docker-engine-guard-design.md, because a factory run clones only that
repository.

| child | module | depends on |
| --- | --- | --- |
| 1a lifecycle | `fleet/docker_engine_guard.py` plus three stub modules | — |
| 1b observer and commit | `fleet/docker_engine_guard.py` (bodies 1a's table names) | 1a |
| 2 rollback driver | `fleet/_docker_engine_guard_rollback.py` | 1a |
| 3a host actions | `fleet/_docker_engine_guard_host.py` | 1a |
| 3b package step | `fleet/_docker_engine_guard_packages.py` | 1a |
| 4 preflight and probes | `fleet/_docker_engine_guard_host.py` (after 3a) | 3a |

1a creates the three sibling modules as stubs, so 1b, 2, 3a and 3b never edit the
same file and can run in parallel after 1a; 4 runs after 3a.

## Review

Two read-only Fable review rounds shaped this cut.

- Round 1 returned CHANGES with 18 findings: missing operations, missing probes,
  bundled bullets, and both children oversized.
- Round 2 returned CHANGES: split the control plane into 1a and 1b, give the
  rollback driver its own module, add ten host actions, and split five bullets.

All findings are applied below. Two further changes are this session's own:

- the package step moved into its own child 3b;
- 1a creates stubs for the sibling modules.

## The filing drafts, verbatim

Each block below is the description that is filed; the child ids replace the
placeholders in xxfqqr's remainder.

### 1a-lifecycle

````text
TITLE: docker-engine-guard 1a: lock, dispatch table and pre-start lifecycle

Plan: livespec-orchestrator-beads-fabro plan petri-factory-on-gmktec, epic bd-ib-fyozyd (ledger of repository livespec-orchestrator-beads-fabro). Repo: livespec-dev-tooling. Regroomed out of livespec-dev-tooling-xxfqqr (see its 2026-10-15 correction comment). The guard is six factory-safe children: 1a lifecycle (this one), 1b observer and commit, 2 rollback driver, 3a host actions, 3b package step, 4 preflight and probes. xxfqqr keeps the host-routed role, the QEMU VM harness and the attended converge. 1b, 2, 3a and 3b depend on this child, and 4 depends on 3a. Which plan assertions this child carries is recorded only in that epic's carrier-map scope event.

Governing design: docs/docker-engine-guard-design.md in this repository. Revisions 5 to 8 govern: F1-F3, G1-G3, H1, H3, H4, H6 and I1-I4, plus rider points 3 and 8.

Deliverable: livespec_dev_tooling/fleet/docker_engine_guard.py, a stdlib-only module runnable as `python3 docker_engine_guard.py <op> <run> ...`. The package floor is Python 3.10, so use no newer syntax. The tests are in tests/livespec_dev_tooling/fleet/test_docker_engine_guard_lifecycle.py. This child defines:
- the HostOps protocol, including a `sample` method for 1b and the rollback-phase methods for child 2;
- a FakeHost with an injectable clock, boot id and state roots;
- the lock;
- the run directory and its phase records, with durable writes (write, fsync, rename, then fsync the directory);
- the deadline;
- ONE dispatch table registering every operation (reserve, publish, arm, start, observe, confirm, rollback, recover, verify and reconfigure) with its decision and phase transition.
It implements reserve, publish, arm, start and recover. For observe, confirm, verify and reconfigure it implements the table decision and raises NotImplementedError past that point; 1b fills them in this module. So that no other sibling ever edits this module, this child also creates three STUB modules that the siblings replace:
- livespec_dev_tooling/fleet/_docker_engine_guard_rollback.py (child 2): rollback's entry calls its `run_rollback` after the table decision;
- livespec_dev_tooling/fleet/_docker_engine_guard_host.py (children 3a and 4): the CLI builds its RealHost;
- livespec_dev_tooling/fleet/_docker_engine_guard_packages.py (child 3b): the package step behind HostOps.
Each stub's functions raise NotImplementedError. This child ships no real host action. State lives under /var/lib/docker-engine-guard and /run/docker-engine-guard.

## Definition of Done

- `reserve <run>` creates a reservation only when the confirmed marker is absent, any current reservation's run is rolled-back, every guard unit other than the invoking unit is inactive with no queued job, and no account is in the docker group.
- A refused `reserve` prints the holding run id, its phase and its deadline.
- Every operation takes an exclusive lock on the lock file opened with O_CREAT and close-on-exec, waits at most 60 seconds, and exits non-zero without acting when the wait expires.
- Every operation first ensures /run/docker-engine-guard exists with mode 0700.
- Every operation on a run refuses when that run is not the current reservation.
- The module holds one dispatch table mapping each operation and confirmed-marker state to its allowed phases, and a parametrized test exercises every cell of it at the decision level.
- `publish` records the snapshot once, before the first package step, and a resumed `publish` from publishing keeps the first snapshot.
- `publish` moves the run to publishing before the package step and to published after it.
- `arm` records the deadline as the current boot id plus a monotonic instant.
- `arm` passes the remaining interval as the dead-man timer's on-active value and 60 seconds as its on-unit-inactive repeat, and succeeds when that timer unit already exists.
- `arm` refuses and triggers rollback when any account is in the docker group.
- A deadline recorded under a different boot id counts as passed for every operation.
- `start` refuses when the dead-man timer unit is not active.
- `start` moves the run to started before it grants the start permission.
- `recover` resumes `publish` for a run in publishing and rolls back a run in any other pre-commit phase.
- `recover` performs its work through the same locked helper as the other operations and runs under its own stated time budget.

References: ## Fabro factory host provisioning
````

### 1b-observer-commit

````text
TITLE: docker-engine-guard 1b: observer, challenge, commit and post-commit operations

Plan: livespec-orchestrator-beads-fabro plan petri-factory-on-gmktec, epic bd-ib-fyozyd (ledger of repository livespec-orchestrator-beads-fabro). Repo: livespec-dev-tooling. Child 1b of the six factory-safe guard children regroomed out of livespec-dev-tooling-xxfqqr; depends on 1a, and only fills operation bodies that 1a's dispatch table already names. Which plan assertions this child carries is recorded only in that epic's carrier-map scope event.

Governing design: docs/docker-engine-guard-design.md in this repository: F4, G2's confirm, G4, H2's observer rules, H3, H5 and I2's confirm, verify and reconfigure rows, plus rider points 5 (the challenge half; the role-side rescue stays in xxfqqr) and 9.

Deliverable: the bodies of observe, confirm, verify and reconfigure in livespec_dev_tooling/fleet/docker_engine_guard.py, tested against 1a's FakeHost in tests/livespec_dev_tooling/fleet/test_docker_engine_guard_observer.py. Stdlib only, no syntax newer than Python 3.10. observe calls HostOps.sample for each sample.

## Definition of Done

- `observe` moves the run from started to observing under the lock before its first sample.
- `observe` stops sampling when a lock-held check finds the run no longer observing.
- On a failed sample `observe` records the failure in the evidence record, starts `rollback <run>` through the host runner without waiting, and exits.
- On a passing window `observe` writes a challenge carrying the run id, the boot id and a fresh nonce under the runtime root, then moves the run to observed.
- Each passing `observe` window issues a nonce that differs from every earlier one.
- `confirm` commits only from observed with passing evidence, an unexpired deadline and a challenge from the current boot younger than 120 seconds carrying the matching nonce.
- A `confirm` carrying an expired or already-used challenge refuses.
- `confirm` writes the confirmed marker as the run id plus the canonical digest of the owned daemon keys.
- A failed directory fsync after the marker rename records a durability warning and leaves the run committed.
- A `confirm` for a run the confirmed marker names repeats the post-commit steps and starts the three units without a challenge.
- After the post-commit steps `confirm` validates that the three units are enabled and running, the start permission is present and the owned keys match.
- `verify` re-evaluates the rollback postcondition set read-only and rewrites rollback-partial as rolled-back only when every postcondition holds.
- `reconfigure` is allowed only when the confirmed marker names the current run, writes the owned daemon keys and records a pending drained restart.

References: ## Fabro factory host provisioning
````

### 2-rollback-driver

````text
TITLE: docker-engine-guard 2: rollback driver, phase order, attempt budget, outcome and dead-man self-stop

Plan: livespec-orchestrator-beads-fabro plan petri-factory-on-gmktec, epic bd-ib-fyozyd (ledger of repository livespec-orchestrator-beads-fabro). Repo: livespec-dev-tooling. Child 2 of the six factory-safe guard children regroomed out of livespec-dev-tooling-xxfqqr; depends on 1a, whose HostOps protocol (with its rollback-phase methods) and FakeHost it uses. Which plan assertions this child carries is recorded only in that epic's carrier-map scope event.

Governing design: docs/docker-engine-guard-design.md in this repository: F1's rollback, R4's ordering, G5, H2's stop-first rule and H6's bounds.

Deliverable: a new module livespec_dev_tooling/fleet/_docker_engine_guard_rollback.py, which 1a's rollback entry dispatches to, tested in tests/livespec_dev_tooling/fleet/test_docker_engine_guard_rollback.py against 1a's FakeHost. Stdlib only, no syntax newer than Python 3.10. It calls only HostOps methods and implements no host action itself.

## Definition of Done

- `rollback` records rolling-back before any other step, after which `start` and `confirm` refuse for that run.
- `rollback` on a run the confirmed marker names exits 0.
- `rollback` stops the observe and start units before it revokes the start permission.
- After revoking the start permission the driver runs its phases in the order socket stop, job cancel, FORWARD restore, cgroup kill and stop, unit disable, footprint removal, interface deletion, sysctl comparison, final check.
- The final check runs after every stop phase and reads all postconditions together.
- The driver records an attempt for a phase durably before entering it.
- The driver runs each phase as a child process under `timeout -k 10` with that phase's budget.
- The phase budgets sum to 600 seconds.
- The driver skips a phase whose recorded attempts reach three without a recorded success.
- The driver runs every later phase when an earlier phase fails, times out or is skipped.
- The driver clears a phase's success record when the final check finds that phase's postcondition failing.
- The driver writes rolled-back only when every postcondition holds in the final check.
- The driver writes rollback-partial naming each failed postcondition when any postcondition fails.
- With a rolled-back outcome the driver issues `systemctl stop` for its own dead-man timer unit.
- With a rollback-partial outcome a later firing re-runs only the phases whose postcondition fails and whose attempts are under three.
- The driver issues `systemctl stop` for its own dead-man timer once every failing phase has exhausted its attempts.

References: ## Fabro factory host provisioning
````

### 3a-host-actions

````text
TITLE: docker-engine-guard 3a: host actions (snapshot, firewall footprint, unit and job control, conditions, dead-man recipe)

Plan: livespec-orchestrator-beads-fabro plan petri-factory-on-gmktec, epic bd-ib-fyozyd (ledger of repository livespec-orchestrator-beads-fabro). Repo: livespec-dev-tooling. Child 3a of the six factory-safe guard children regroomed out of livespec-dev-tooling-xxfqqr; depends on 1a, whose HostOps protocol it implements. Which plan assertions this child carries is recorded only in that epic's carrier-map scope event.

Governing design: docs/docker-engine-guard-design.md in this repository: Mechanism 4 (footprint), R4, F5 and G6 (effective conditions), and rider points 1, 2, 6, 7 and the --collect half of 9.

Deliverable: the real HostOps in a separate module, livespec_dev_tooling/fleet/_docker_engine_guard_host.py, tested in tests/livespec_dev_tooling/fleet/test_docker_engine_guard_host.py. Stdlib only, no syntax newer than Python 3.10. Every external command goes through one injectable runner with an explicit timeout. The tests drive each action against RECORDED command output (iptables-save, ip6tables-save, ip link, systemctl list-jobs, busctl) and assert on the argv each action emits. Firewall changes use only the iptables-nft commands. The package step is sibling 3b, in its own module.

## Definition of Done

- The snapshot action runs iptables-save and ip6tables-save per table without counters and stores the output, both FORWARD policies and the watched sysctls in the run's before directory.
- The footprint planner selects for deletion exactly the rules present now and absent from the snapshot that reference docker0, 172.17.0.0/16, or a chain absent from the snapshot whose name starts with DOCKER.
- The planned deletion set excludes every rule and chain that the snapshot contains.
- Footprint removal issues `iptables -D` and `ip6tables -D` with each rule's full specification, then flushes and deletes the selected chains.
- Footprint removal re-reads and repeats at most three passes and reports every residual Docker rule.
- FORWARD restore issues one `-P FORWARD` per address family with the policy recorded in the snapshot.
- Job cancellation issues `systemctl cancel` with the job ids of queued jobs whose unit is docker.service, docker.socket or containerd.service.
- The Docker stop action stops docker.socket before docker.service.
- The cgroup kill action issues `systemctl kill --kill-whom=all --signal=SIGKILL` for docker.service, containerd.service and fabro-sandbox.slice, then a bounded `systemctl stop` of those and docker.socket.
- The disable action disables docker.service, docker.socket and containerd.service.
- The interface action deletes docker0 and every veth whose master is docker0.
- The sysctl action compares the five forwarding and bridge-netfilter values with the snapshot and reports each difference.
- The unit-stop action stops docker-engine-guard-observe.service and docker-engine-guard-start.service with SIGKILL after 10 seconds and waits for both to be inactive.
- The postcondition read reports permission, socket, process, queued job, FORWARD policy, Docker rule, docker0 and sysctl state as one record.
- The condition check reads each unit's Conditions property through busctl and passes only when exactly the two expected OR path conditions are present.
- The drop-in check accepts the guard's own drop-ins and the fleet sandbox_storage drop-ins for docker.service and containerd.service.
- The drop-in check refuses a drop-in outside that set.
- The dead-man recipe passes --collect, AccuracySec=1s and TimeoutStartSec=900 to systemd-run.

References: ## Fabro factory host provisioning
````

### 3b-packages

````text
TITLE: docker-engine-guard 3b: the fenced, audited package step

Plan: livespec-orchestrator-beads-fabro plan petri-factory-on-gmktec, epic bd-ib-fyozyd (ledger of repository livespec-orchestrator-beads-fabro). Repo: livespec-dev-tooling. Child 3b of the six factory-safe guard children regroomed out of livespec-dev-tooling-xxfqqr; depends on 1a, whose HostOps protocol names the package step. Which plan assertions this child carries is recorded only in that epic's carrier-map scope event.

Governing design: docs/docker-engine-guard-design.md in this repository: Mechanism 5 as amended by R6, F6 and G7, plus rider point 4.

Deliverable: the package step in a separate module, livespec_dev_tooling/fleet/_docker_engine_guard_packages.py, tested in tests/livespec_dev_tooling/fleet/test_docker_engine_guard_packages.py against RECORDED command output (apt-get -s, apt-get download, dpkg --audit, dpkg-query, the archive Packages index) and asserting on the argv each step emits. Stdlib only, no syntax newer than Python 3.10. Every external command goes through one injectable runner with an explicit timeout. The apt timers, the dpkg frontend-lock wait and the post-install daemon-reload belong to xxfqqr's role, which runs them around this step.

## Definition of Done

- The package step refuses when the simulated transaction installs a package or version outside the committed allowlist, removes a package, or upgrades an installed package.
- The package step refuses when an installed version the audit relied on changed since the audit.
- The package step refuses when a downloaded .deb's SHA256 differs from the archive index or its maintainer scripts differ from the committed digests.
- The package step refuses when a host apt hook file or dpkg configuration file differs from its committed digest.
- The package step runs `dpkg -i` on exactly the audited .deb files with DPKG_FRONTEND_LOCKED=1 in its environment.
- The package step requires the post-install dpkg-query difference to equal the audited additions.
- The package step runs `dpkg --configure` on this run's half-installed, unpacked or half-configured packages only.
- The package step completes interrupted triggers with `dpkg --triggers-only` restricted to packages in a guard run's recorded intended set.
- The package step refuses when `dpkg --audit` names a package outside every recorded intended set.

References: ## Fabro factory host provisioning
````

### 4-preflight-probes

````text
TITLE: docker-engine-guard 4: preflight checks and observer probes

Plan: livespec-orchestrator-beads-fabro plan petri-factory-on-gmktec, epic bd-ib-fyozyd (ledger of repository livespec-orchestrator-beads-fabro). Repo: livespec-dev-tooling. Child 4 of the six factory-safe guard children regroomed out of livespec-dev-tooling-xxfqqr; depends on child 3a, adding to its module after it lands. Which plan assertions this child carries is recorded only in that epic's carrier-map scope event.

Governing design: docs/docker-engine-guard-design.md in this repository: Mechanism 3's probes as corrected by R8, R9 (exclusive admission during the window), F7 (admission and collision checks), F8 (k3s witness) and R4's comparison scope.

Deliverable: the preflight checks and HostOps.sample in livespec_dev_tooling/fleet/_docker_engine_guard_host.py, tested in tests/livespec_dev_tooling/fleet/test_docker_engine_guard_probes.py against RECORDED command output, asserting on the argv each probe emits. Stdlib only, no syntax newer than Python 3.10. The controller-side probes (a new Tailscale SSH session, the LLM /health and the LAN-fallback login) belong to xxfqqr's role.

## Definition of Done

- The preflight refuses when 172.17.0.0/16 overlaps an address on any interface, a route in any routing table, the tailnet range, or the cluster's pod or service CIDR.
- The preflight refuses when any account has docker as its primary group or is a member of it.
- The resync window is the largest effective interval read from /etc/rancher/k3s/config.yaml and its drop-ins, each recorded with its source, plus two minutes.
- The preflight refuses when any effective resync interval exceeds five minutes.
- The services probe requires k3s-agent, tailscaled and every unit in docker_engine_must_stay_running to be active.
- The Node Ready probe reads the node's own status through `get --raw /api/v1/nodes/<node>/status` with the node-status credential.
- The DNS probe requires every CoreDNS backend to be on another node, read through the k3s server at preflight and again at the end of the window, and reports a same-node result as not counting toward confirmation.
- The DNS probe sends its query to the kube-dns service address from the pod network namespace and parses the reply without a resolver file.
- The API probe completes a TLS handshake to the Kubernetes API service ClusterIP from the pod network namespace.
- The HTTPS probe connects from the pod network namespace to an address resolved on the host, sends SNI explicitly, and issues a HEAD to an Ubuntu archive mirror.
- The sysctl probe requires the five forwarding and bridge-netfilter values to equal the snapshot.
- A failed probe is re-run once immediately and counts as failed only when it fails twice.
- Every probe failure is recorded with the probe name and its error.
- The k3s witness records the containerd PID of k3s-agent.service and the paths /run/containerd/s and /run/containerd/runc/k8s.io at preflight, and fails a sample when the PID changed or a path is missing.
- The canary's cgroup is resolved through `systemctl show -p ControlGroup fabro-sandbox.slice`.
- A sample fails when any container other than the canary exists, or any Docker network other than bridge, host and none exists.
- A sample fails when an interface other than docker0 and the canary's one veth pair has appeared since the snapshot.
- The firewall comparison of a sample covers the built-in chain policies of both families, the rules of INPUT, FORWARD, OUTPUT, PREROUTING and POSTROUTING, and the contents of ts-* chains, and skips the contents of KUBE-* and FLANNEL-* chains.

References: ## Fabro factory host provisioning
````

### xxfqqr-remainder

````text
Plan: livespec-orchestrator-beads-fabro plan petri-factory-on-gmktec, epic bd-ib-fyozyd (ledger of repository livespec-orchestrator-beads-fabro). Repo: livespec-dev-tooling, ansible/roles/docker_engine (new role) and ansible/fabro-hosts.yml. Which plan assertions this child carries is recorded only in that epic's carrier-map scope event.

REGROOMED 2026-10-15 (see this item's correction comment). The guard executable, livespec_dev_tooling/fleet/docker_engine_guard.py and its sibling modules, is implemented and unit-tested through the factory by six children: <1a>, <1b>, <2>, <3a>, <3b> and <4>. This item keeps the HOST-ROUTED remainder and depends on all six:
- the docker_engine Ansible role that installs the guard, runs the apt-timer fence, the dpkg frontend-lock wait and the post-install daemon-reload around the guard's package step, writes the per-run inputs and invokes every guard operation as its bounded transient unit;
- the controller-side probes (a new Tailscale SSH session, the LLM /health and the LAN-fallback login) and the role-side rescue;
- the disposable QEMU VM integration harness on the control node, which runs every fault in the design's acceptance sections (including rider 1's respawn test);
- HOST_VARS.md;
- the attended gmktec-xubuntu converge.

Route: HOST-ROUTED, factory-ineligible for this remainder (its 12:17:47Z record, as corrected). The maintainer's binding constraint is that no step may cut gmktec off. Conditions: a notice to and ack from gitops-fleet-capacity-monitoring and the k3s sessions before any gmktec converge; nothing on a host before the VM acceptance passes; no Fabro, Tailscale or k3s unit restarts; hp untouched; every change Fable-reviewed.

Why and measurements: unchanged from the original filing. Docker is not installed on gmktec-xubuntu; installing it changes FORWARD to DROP and inserts DOCKER-USER and DOCKER-FORWARD (measured on hp); gmktec runs a k3s agent carrying CI pods and the fleet's local LLM service with FORWARD ACCEPT; Ubuntu 26.04, iptables 1.8.11 nft backend; archive docker.io 29.1.3-0ubuntu4.1, containerd 2.2.2-0ubuntu1.1, runc 1.4.0-0ubuntu1. Design: docs/docker-engine-guard-design.md.

## Definition of Done

### Host-captured
Reason: every assertion acts on a live host's packages, firewall, systemd and Tailscale SSH, proven by the disposable QEMU VM run and the attended gmktec converge; no factory sandbox has a systemd host, its firewall or KVM.
- The role installs exactly the pinned docker.io, containerd and runc package versions from the Ubuntu archive without recommended packages and without upgrading any other package.
- The role writes the Docker daemon configuration before the daemon first starts, declaring iptables, ip-forward, ip-forward-no-drop and a pinned bridge address, and preserves every key it does not own.
- Before its first change on a host, the role saves the host's iptables and ip6tables rulesets and arms a transient systemd timer that runs the rollback unless a confirmation arrives before the timer fires.
- The rollback stops and disables docker, docker.socket and containerd, removes only Docker's own chains and jumps, and restores the saved FORWARD policy.
- After a rollback the k3s, flannel, kube-router and Tailscale chains equal their state before the change.
- The role confirms only after a new Tailscale SSH session from the control node succeeds, the k3s agent is active with its node Ready, a pod-network probe answers, and the local LLM service's health endpoint answers.
- The role refuses to change a host on which tailscaled, the k3s agent or a declared must-stay-running service is not active before the change.
- After a converge the host's FORWARD policy equals the policy it had before the converge.
- On a host where the confirmation is withheld, the armed timer restores the saved FORWARD policy and removes Docker's chains, and the host stays reachable over Tailscale SSH.
- On the disposable QEMU VM every fault named in the design's acceptance sections ends rolled-back or confirmed, with no Docker process, Docker rule or docker0 left after a rollback.
- The role's HOST_VARS.md documents every variable it reads, its operator procedure, its rollback and the condition under which it is retired.

References: ## Fabro factory host provisioning
````
