# Independent review, round 2 — Docker on gmktec-xubuntu

Reviewed 2026-10-15 against revision 2. **BLOCKERS remain; do not converge this design on gmktec as written.**

Scope: design review, not implementation acceptance. No packages, services, firewall rules, host configuration, ledgers or tracked repository files were changed. This explicitly requested, gitignored report is the only file written. Remote commands were restricted to the brief's allowed reads. No install/simulation, restart, rollback, container launch, pod exec or active health test was performed. `design.md` references are to this directory's revision 2; `ansible/` and `ci-runner/` references are relative to `/data/projects/livespec-dev-tooling/`. Round-1 evidence was read but is distinguished below from checks performed in this round.

## Ranked findings

### BLOCKER 1 — The atomic directory is not a crash-safe outcome, and prevents recovery from retrying

Evidence: `design.md:151–163,176–186,219–221`.

`mkdir claim` and writing `claim/winner` are two operations. If the confirmer dies between them, the timer loses the mkdir race and does nothing, although no confirmation exists. The boot guard also skips this run because its claim exists. The same hole exists when rollback creates the directory and dies before recording its winner or `rollback-started`. Even with a complete `winner=rollback`, a rollback killed halfway through cannot resume: the next invocation loses the same mkdir and exits. Recording a partial result or refusing a later play is not recovery of the current unreachable host.

Confirmation is also underspecified after winning: a death after `winner=confirm` but before enablement, timer cancellation or `confirmed` leaves an outcome the timer treats as accepted, the boot guard describes ambiguously, and preflight may treat as unresolved. Network verification has passed at this point, so failure to cancel the timer alone need not cause rollback; the problem is the absence of a defined, resumable finalization contract.

Require atomic publication of a fully formed durable decision, explicit handling of incomplete/corrupt state, and resumable rollback owned by the rollback decision rather than barred by it. Boot recovery must cover incomplete rollback and interrupted publication, not only absent claims. Fault-injection acceptance must kill the process at each transition, including immediately after claiming and during confirmation finalization. A transient systemd unit merely existing does not prove this recovery protocol works.

### BLOCKER 2 — Initial activation is outside the arbiter, and disabled-at-boot is asserted rather than established

Evidence: `design.md:69–97,161–183,188–191`; allowed hp reads of `/var/lib/dpkg/info/docker.io.postinst`, `/var/lib/dpkg/info/containerd.postinst`, `/usr/bin/deb-systemd-helper`, and `/usr/lib/systemd/system/docker.service`.

The rule that every activating task requires `claim=confirm` cannot literally apply to step 6: confirmation follows the first start and verification. If step 6 is exempt, consider a pause after successful arming: expiry masks and cleans up Docker; the resumed play executes its pending unmask and start. A separate read-before-action check still permits expiry between that read and unmask/start. The claim arbitrates confirmation against rollback, not the actual operations rollback must fence. Boundaries and nominal timeout sums do not close this race.

Define an explicit armed-to-start permission and serialize local activation with the rollback transition. No controller task may unmask or submit a start job once rollback owns the run, including a task delayed before its command executes. Avoid a long-held lock that would itself prevent recovery.

There is also no explicit disable-and-verify step before unmasking. hp's postinst scripts attempt to enable all three units. Its helper's `enable` path invokes `systemctl preset --preset-mode=enable-only` on initial install (`/usr/bin/deb-systemd-helper:310–338`). The helper's `unmask_service` preserves an administrator-created mask unless its own mask state file exists (`:543–565`), so I am **not** claiming postinst necessarily removes these masks. Nor did I execute a masked-install experiment. The issue is that the design treats “masked” and “disabled” as interchangeable without verifying the boot links after the actual transaction.

Explicitly establish and verify disabled boot state while persistent masks still hold. Also define a boot dependency that fails closed: `Before=` orders jobs but does not require the boot guard to succeed. This distinction is documented in local `/usr/share/man/man5/systemd.unit.5.gz`, `Wants=`, `Requires=` and `Before=/After=`. A failed boot guard must not merely finish and allow a queued Docker/socket start to proceed. Runtime rollback masks disappear on reboot, so the durable inhibition and incomplete-run cases matter.

### BLOCKER 3 — Apt lock waiting still does not fence the approved transaction or unrelated restart hooks

Evidence: `design.md:55–82,289–293`; fresh gmktec `systemctl is-active unattended-upgrades apt-daily.timer apt-daily-upgrade.timer` returned `active` for all three; `apt-cache policy docker.io containerd runc needrestart` reported all four absent, with the three proposed package versions available. [Ansible apt documentation](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/apt_module.html), `lock_timeout`, describes waiting to acquire the apt database lock.

A simulation can pass, another apt operation can change the package database, and the real install can then obtain its lock and execute against a different state. A diff taken afterward detects the change after its effects. It cannot enforce the promised refusal before dependency upgrades, pending configuration or hooks run. Moving apt outside the timer correctly removes the apt-versus-watchdog deadline race; it does not solve this separate transaction race.

Masking Docker/containerd units prevents those activation paths. It does not make every dependency maintainer script, apt hook or concurrent unattended upgrade network-inert. The inspected hp scripts also perform AppArmor profile loading and systemd operations; they are not the complete target transaction. Absence of needrestart is useful, but not an audit of every restart path. No concrete complete dependency allowlist or target hook audit is supplied.

Specify coordination that keeps the validated package state and actual transaction consistent, with revalidation after contention and a pre-mutation refusal of forbidden actions. Audit the actual dependency scripts/hooks and define interruption recovery while masks remain installed. Do not claim that unrelated services cannot restart merely because three units are masked. This is still round-1 blocker 5, not a request to run a risky experiment on gmktec.

### BLOCKER 4 — The rollback's global timeout can kill it before policy/interface repair, and no retry survives that kill

Evidence: `design.md:165–172,185–217`; hp service reads confirmed Docker `TimeoutSec=0`, `KillMode=process`, and containerd `KillMode=process`, `Restart=always`. Local `/usr/share/man/man5/systemd.service.5.gz`, `TimeoutStartSec=`, defines the service start timeout, including execution of a oneshot.

The guard has a 300-second oneshot limit, but firewall deletion gives **each** rule a ten-second xtables-lock wait, followed by chain cleanup and up to three passes across both families. Thirty contended commands alone consume that budget; the bounded stop already consumes up to thirty seconds. No inventory-derived bound or per-phase budget reserves time for FORWARD restoration, docker0 deletion, sysctl comparison and final result recording. The prose says every step is independent, but systemd terminating the entire executable defeats that independence. Chain flush/delete bounds and the other systemctl calls are not specified either.

The budget asserted below N concerns the start/verification window, not completion of rollback within its separate 300-second ceiling. Fix both budgets explicitly. Prioritize restoration needed for access, give each phase a deadline and reserved follow-on time, persist progress, verify residual rules/processes, and permit an interrupted rollback to resume (blocker 1). Three passes are a finite attempt, not proof that a concurrent reconciler cannot leave a half-applied state.

### SHOULD-FIX 5 — Default address pools neither constrain explicit networks nor leave room for automatic allocation

Evidence: `design.md:115–133,300–302`; [Docker network-create documentation](https://docs.docker.com/reference/cli/docker/network/create/), advanced options, documents explicit subnet selection and non-overlap requirements. Fresh gmktec `ip route` showed LAN 192.168.1.0/24 and pod routes 10.42.0.0/24, 10.42.1.0/24 and 10.42.2.0/24, without a 172.17 route.

The default bridge consumes 172.17.0.0/16, while the automatic pool consists solely of /24s inside that same /16. Those prospective allocations overlap the existing bridge; this is not a usable future-network pool. More fundamentally, defaults do not prohibit a caller choosing an explicit `--subnet`, another driver, or an IPv6 network. Thus “no Docker network can claim a range” is false. `ipv6:false` is a default-bridge setting, not a ban on all IPv6 networks.

For this first install, explicitly restrict the guarded scope to docker0 with no additional networks or consumers, and verify that scope. If future automatic networks are supported, choose a separately verified, non-overlapping pool and define their ownership/recovery. The current cleanup deletes only docker0; it cannot justify guarantees for other bridges, veths, routes or sysctls. Snapshotting all route tables is helpful, but neither collision refusal nor a route/interface before/after acceptance predicate is presently specified.

### SHOULD-FIX 6 — “No installed packages” does not establish an empty Docker data store or exclude concurrent consumers

Evidence: `design.md:55–60,83–104,134–135,192–198`; [dockerd reference](https://docs.docker.com/reference/cli/dockerd/), `data-root`, cgroup namespace and live-restore options; hp unit uses `KillMode=process`.

Preflight does not reject retained `/var/lib/docker` or `/var/lib/containerd` state, a prior daemon configuration, standalone runtimes, or another consumer of the system Docker socket. Packages can be absent while containers and network definitions persist on disk. Starting the daemon can therefore restore networks/containers before the intended throwaway test. This invalidates both the narrow firewall inventory and “first container is born in this slice” assumption. Explicitly prove empty/absent supported runtime state and exclusive admission; never silently erase a retained store to obtain that condition.

Also, `live-restore:false` is not proof that SIGKILLing dockerd stops every container. The proposed rollback deliberately bypasses graceful daemon shutdown and matches daemon/shim executables, not arbitrary workload executables in independent container cgroups. Either establish and maintain zero containers during this guarded phase, or define container/cgroup-owned termination and verification that excludes k3s. This matters especially if the container acceptance test is moved under the guard.

### SHOULD-FIX 7 — The real-container acceptance check cannot reliably prove host slice ancestry from inside a private cgroup namespace

Evidence: `design.md:98–104,136–141`; [dockerd reference](https://docs.docker.com/reference/cli/dockerd/) lists the default cgroup namespace mode as private. `ansible/roles/docker_sandbox_slice/tasks/main.yml:65–97,108–135,161–180,198–225` checks the systemd driver, starts the slice, merges the parent key, and currently infers loaded parent from the file.

A container's cgroup path can appear as `/` in its private namespace; ancestor slice paths and their limits are not necessarily exposed there. Reading the container's own `memory.max`/`cpu.max` is not proof of its parent slice's limits. Inspect the actual container PID's cgroup from the host and read the ancestor slice's effective files there. Compare expected host-specific values, not merely the existence of a limit.

The first container also adds endpoint/veth/raw rules only **after** confirmation disables the watchdog. An idle-daemon network check does not exercise those mutations. Prefer a tightly bounded canary and repeat the independent tailnet/pod probes with it running before irrevocable confirmation, with its cleanup included in rollback. Otherwise state clearly that the guarded acceptance covers only an idle daemon, and keep post-confirmation testing from being described as proof of the whole networking transition.

The intended role split and effective-reservation gate are sound design changes. They have not yet been implemented in the inspected roles. Preserve their existing daemon-key merge and restart-pending behavior when making the split; use one host-specific slice name/value source for both roles.

### SHOULD-FIX 8 — Refusal after any successful installation leaves no supported resume path

Evidence: `design.md:58–61,78–82,89–104,219–221`.

If installation succeeds but arming fails, the safe result is masked installed packages. If verification fails and rollback succeeds, packages likewise remain installed. Both cases fail the next run's unconditional “no Docker or containerd package” preflight. A successfully confirmed host also fails this preflight during a later whole factory-play converge. Acknowledging a partial run does not waive this independent condition, and the design does not say it should.

Define a supported distinction between foreign existing Docker (refuse), this role's interrupted inert installation (resume only with verified provenance), confirmed installation (validate/no-op), and rollback requiring repair. Do not require package purging or ad hoc unmasking as an unstated prerequisite for retrying. This also determines how the companion factory play remains convergent without touching hp's existing Docker.

### SHOULD-FIX 9 — The verification predicates need more precise scope and measured resync timing

Evidence: `design.md:233–253`; fresh gmktec `sudo -n iptables -S` contained ARC listener pod chains and KUBE-ROUTER/KUBE-FORWARD/FLANNEL/ts-* chains; its six required/network/package-timer services reported active.

A kubelet local healthz success is not equivalent to the Kubernetes Node Ready condition. Specify these as separate observations; do not substitute one while reporting the other. Revalidate the chosen container PID and network namespace across listener churn, require a non-host-network pod on this node, and prove the DNS endpoint actually crosses nodes. Merely saying a 120-second delay spans both controllers' resyncs supplies no configuration or observed-cycle evidence; choose the window from the running controllers' effective intervals, including scheduling allowance.

Canonicalize firewall snapshots without counters before comparing. Exact INPUT/ts-* equality can fail due to legitimate reconciliation unrelated to Docker; retain fail-closed behavior but distinguish that diagnostic from proof Docker changed Tailscale. Request/reply probes substantially fix the round-1 counter error, but two samples do not establish uninterrupted service throughout the interval.

### NOTE 10 — The revised targeted firewall footprint addresses the demonstrated omission, within its stated scope

Evidence: `design.md:199–209`; fresh hp `sudo -n nft list ruleset` showed direct raw rules such as `ip daddr 172.17.0.2 iifname != "docker0" ... drop`, the 172.17.0.0/16 POSTROUTING masquerade, and IPv4/IPv6 DOCKER, DOCKER-BRIDGE, DOCKER-CT, DOCKER-FORWARD, DOCKER-INTERNAL and DOCKER-USER chains. [Upstream 29.1.3 iptabler source](https://raw.githubusercontent.com/moby/moby/docker-v29.1.3/daemon/libnetwork/drivers/bridge/internal/iptabler/iptabler.go), lines 13–32 and 55–80, confirms the current chain model and independent IPv6 chain setup.

Those direct rules are selected by the new docker0/subnet predicates, so the original omission is resolved at design level. Use parsed, exact rule tokens; normalize counters away; flush all owned chains before deleting any; verify residuals after the final pass. Set difference plus a textual reference is not universal proof of ownership if other writers add rules about Docker during the window. Keep the exclusive first-install scope explicit. No actual rollback executable or fault-injection result was supplied, so this is not certification of cleanup implementation.

### NOTE 11 — Sysctl/Tailscale scope is materially improved, but recovery is intentionally incomplete for shared-state damage

Evidence: `design.md:12–19,64–68,126–129,213–215,229–251`; fresh gmktec reads of IPv4 forwarding, IPv6 all/default forwarding and bridge IPv4/IPv6 filtering returned `1,0,0,1,1`. [Upstream 29.1.3 forwarding source](https://raw.githubusercontent.com/moby/moby/docker-v29.1.3/daemon/libnetwork/drivers/bridge/setup_ip_forwarding.go), lines 35–55,73–108,112–126, skips unchanged values and gates policy changes.

The normal IPv4-only first start has a credible path without changing the measured global forwarding values. Both-family comparisons and avoiding blind shared-sysctl restore are improvements. However, recording unexpected shared sysctl damage does not repair it. Describe this as a detected partial recovery condition, not guaranteed restoration of access. None of the inspected Docker/containerd postinst scripts directly invokes tailscaled or an interface/route command, but that does not audit the full apt transaction or authorize arbitrary future Docker networks.

### NOTE 12 — Companion implementation and stale host records remain outstanding

Evidence: `ansible/fabro-hosts.yml:17–18,32–44` still targets hp literally and orders redis before the existing slice role; `ansible/inventory/legacy.yml:49–64` still omits gmktec from sandbox_hosts. `ansible/roles/fabro_server/tasks/main.yml:977–1020` supports stopped-and-disabled instances, and `templates/fabro-server.service.j2:36–37` Wants Docker and tailscaled. hp host_vars is generated from role-owned HOST_VARS.md and contains hp-specific capacity, identities and instances.

The revision specifies the appropriate fresh-host order and parked gmktec instance, but referring to carrier `livespec-dev-tooling-2puzjr` does not prove the inspected play now supports it. This is a design dependency, not a reason to edit those files during review. Gate convergence on the companion implementation and verify tag/limit behavior cannot accidentally run first-install logic on hp.

The gmktec host AGENTS.md still describes the old NoSchedule/0-versus-32 admission state, while `ci-runner/k3s/phase0-bare-metal/profiles/gmktec-xubuntu.env:296,361–363` has empty KUBELET_ARGS, empty NODE_TAINTS and capacity 12. Its llm-server.md Host section still gives the older 64-GB unified-memory description, whereas AGENTS.md records 128 GB installed with a 64-GiB firmware carveout. Notification to another session is not correction. Use the authoritative profile and actual effective reservation; keep the LLM's host CPU/memory needs in capacity accounting.

## Verdict per round-1 finding

1. **NOT RESOLVED** — Shutdown ordering improves, but the global rollback deadline can abort later recovery steps and the claim prevents retry; container termination is not proven under SIGKILL (findings 1, 4, 6).
2. **NOT RESOLVED** — Atomic mkdir leaves interrupted-publication holes; initial activation is not serialized with expiry; boot and half-confirmation recovery remain incomplete (findings 1–2).
3. **RESOLVED** — The revised exact-spec, both-family cleanup includes the demonstrated raw and direct NAT rules within a proven docker0-only clean-install scope; implementation remains untested (finding 10).
4. **RESOLVED** — Baselined fresh request/reply pod-network tests replace unsound counter predicates; refine namespace identity and measured resync coverage (finding 9).
5. **NOT RESOLVED** — Masks and moving apt outside the timer fix activation/deadline aspects, but lock_timeout plus a post-hoc diff does not fence the validated transaction or unrelated hooks (finding 3).
6. **NOT RESOLVED** — The proposed role split and effective reservation are correct, but the specified inside-container ancestry/ancestor-limit check is not a valid proof under private cgroup namespaces (finding 7).
7. **RESOLVED** — Both-family snapshots, fixed initial configuration, comparisons and ownership-aware handling address the original overclaim for this first-start scope; recording damage is not complete restoration (finding 11).
8. **NOT RESOLVED** — Route snapshots and refusal of pre-existing docker0 improve scope, but the overlapping default pool does not constrain explicit networks or justify future interface/route guarantees (finding 5).
9. **NOT RESOLVED** — Revision 2 describes the desired integration, but the inspected play/inventory still cannot target gmktec; companion implementation remains a convergence prerequisite (finding 12).
10. **RESOLVED** — Revision 2 explicitly disclaims network-isolation-as-egress-policy; actual destination reachability remains subject to destination policies.
11. **RESOLVED** — Tailscale userspace interception and independent SSH/LLM paths are described correctly, with preflight baselines.
12. **NOT RESOLVED** — The design uses the current active-CI assumption, but the requested host records are still stale; telling another session is not a completed correction (finding 12).

REVIEW-COMPLETE: BLOCKERS
