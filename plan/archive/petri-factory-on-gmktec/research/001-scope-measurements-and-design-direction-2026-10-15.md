## The maintainer's statement of what done means

What do you think about temporarily moving the new server to gmktec-xububtu, Until it is fully proven, cut over, andCompleted under your plan. ? You would drive this via the proper repo via gitops. Then at that point, we could make the call with her to move it back to HP or just leave it there for now. [...] First of all the plan is to move the server to run on Kubernetes anyway in the future so we should remove all of the references to a hard-coded GitOps machine anyway. Take this opportunity to not have it hard-coded to machine hostnames. Secondly estimates like a week are meaningless for AI and there is no deadline. You just made it better or somebody else did. We just need to get this done. Next you are talking about the plan to do it. You are assuming that this will be run in a new dedicated plan and session so that your attention is not split, correct? As soon as it is up and running, then you can take back over responsibility for it and the rollout once it is able to run items to the same degree that the HP one is, correct? Finally I am on a trip and not physically in my house to reboot this machine if you break it. So the new plan needs to be absolutely careful to not screw up any networking and make the machine inaccessible. [...] Okay but you can't just generically refer to the Fabro server. You should refer to the old one as the legacy Fabro server on HP and the new one just as the current Fabro server. [...] And also let's not frame this as temporary. This machine has more capacity so let's just assume this is where it will live until we finally move Faber onto Kubernetes.

## Definition of Done assertions derived from that statement

- The current Fabro server runs on gmktec-xubuntu, installed and converged by the livespec-dev-tooling gitops playbook. Nothing on that host is set up by hand beyond the fabro_server role's documented out-of-band state: the binary, the generated server.env, the GitHub App private key in the instance's vault, and the tailscale serve mapping owned by the tailscale-admin repository.
- Dispatches routed to the current Fabro server on gmktec-xubuntu run work items through every workflow stage to a merged pull request, to the same degree as the legacy Fabro server on hp.
- No playbook, role or committed factory entry names a machine hostname; a factory is bound to a machine only in the gitops inventory's host groups and host variables.
- Throughout the move, gmktec-xubuntu stays reachable over Tailscale SSH and its local LLM service and k3s agent keep running. No step reboots it or changes tailscaled, its network interfaces or its routes, and every step that changes its firewall rules carries an automatic rollback that restores the prior rules unless reachability is confirmed afterwards.
- The current Fabro server's instance on hp-xubuntu (port 32278) is stopped through the gitops playbook after its in-flight runs finish, with its binary and storage retained.
- Responsibility for the current Fabro server and its cutover is handed back to the fabro-currency plan in a recorded handoff on both plan epics.

## Why this plan exists

Opened 2026-10-15 by session `petri-factory-on-gmktec` from the brief that
session `fabro-currency` wrote at the maintainer's direction
(`tmp/petri-factory-on-gmktec-brief.md` in the primary checkout, gitignored).
The maintainer supplied and confirmed the topic, the slug and the Definition of
Done in that conversation; the statement above is theirs, verbatim.

Terminology, maintainer-declared and binding in every record of this plan:

- **The legacy Fabro server on hp** is the 0.254 carrier engine, unit
  `fabro-server`, port 32276 on hp-xubuntu. It serves the fleet today.
- **The current Fabro server** is the Petri-era engine, carrier
  `0.382.0-nightly.0 (adeefec 2026-10-11)`, binary sha256
  `effe9d03c859e8072934947ce598980ea337065df17e737867685a1508514799`. Today it
  runs as unit `fabro-server-candidate` on hp-xubuntu port 32278. This plan
  moves it to gmktec-xubuntu, its home until Fabro moves onto Kubernetes.

Ownership: this plan owns the move and the hostname-free placement. The
`fabro-currency` plan (epic `bd-ib-6tcjfx`) owns the cutover and the canaries,
and takes the current Fabro server back once assertion 2 is proven.

## Goal served, and the measurement behind it

Goal: own our compute and relieve the one shared resource that caps the
factory. Measurement: on hp-xubuntu every sandbox of both Fabro servers shares
one `docker_sandbox_slice` envelope (24G memory max, 1400% CPU), because the
current Fabro server starts containers with no per-run limits. That envelope is
why the fleet coordinator caps combined runs. gmktec-xubuntu has 32 threads,
62 GiB OS-visible RAM (the LLM weights sit in a separate 64 GiB iGPU carve-out)
and 367 GB free on `/`.

## Measured state, 2026-10-15 (this session, read-only)

gmktec-xubuntu, over Tailscale SSH as `cwoolley`:

- Ubuntu 26.04 LTS (`resolute`), Python 3.14.4, passwordless sudo.
- `k3s-agent`, `local-homelab-llama-server.service` and `tailscaled` active;
  `docker` and `containerd` inactive and not installed. The Ubuntu archive
  offers `docker.io 29.1.3-0ubuntu4.1`, `containerd 2.2.2-0ubuntu1.1` and
  `runc 1.4.0-0ubuntu1`.
- Load averaged 2 to 8 during the probe, from CI runner pods (`coverage`,
  `uv`, an Actions runner). The node carries CI work today.
- Interfaces: `eno1` 192.168.1.156/24 (default route metric 100) and
  `wlp195s0` 192.168.1.66/24 (metric 600) on the same /24; `tailscale0`
  100.79.195.82; `flannel.1` 10.42.1.0 and `cni0` 10.42.1.1/24 with eleven pod
  veths.
- `net.ipv4.ip_forward = 1`. iptables FORWARD policy **ACCEPT**, chain order
  KUBE-ROUTER-FORWARD, KUBE-PROXY-FIREWALL, KUBE-FORWARD, KUBE-SERVICES,
  KUBE-EXTERNAL-SERVICES, the kube-router mark ACCEPT, `ts-forward`,
  FLANNEL-FWD. INPUT policy ACCEPT ending in `ts-input`.
- No Fabro state, no checkout of this repository, no Docker apt source.

hp-xubuntu, the measured precedent for Docker beside a k3s agent:

- Same OS (`resolute`), same k3s agent, and Docker from the Ubuntu archive
  (`docker.io 29.1.3-0ubuntu4.1`, `containerd 2.2.2`, `runc 1.4.0`), installed
  by hand. `/etc/docker/daemon.json` holds only
  `{"cgroup-parent": "fabro-sandbox.slice"}`.
- FORWARD policy **DROP**, with Docker's `DOCKER-USER` and `DOCKER-FORWARD`
  inserted after the kube-router mark ACCEPT and before `ts-forward` and
  FLANNEL-FWD. The k3s agent stays active under that policy, because flannel's
  and kube-router's own ACCEPT rules carry pod traffic. That is evidence the
  combination works on this OS and these versions; it is not proof for
  gmktec, whose node carries CI pods where hp's carries none.
- Two listeners on the Docker bridge gateway serve the sandboxes:
  `sccache-redis` on 172.17.0.1:6379 (role `sccache_redis`) and an OTLP
  receiver on 172.17.0.1:4318 (a `python3` process; the `fabro_server` role's
  `otel.conf` drop-in points at it). Its owner in version control is not yet
  established.
- The current Fabro server's unit, as installed: `HOME` and state under
  `/home/cwoolley/.fabro-candidate`, `WorkingDirectory` the host's primary
  checkout of this repository, `--bind 127.0.0.1:32278 --web`, the OTLP
  drop-in, and a `CPUWeight=1000` drop-in. `settings.toml` names
  `https://hp-xubuntu.perch-rudd.ts.net:32278` as the web and API URL.
- `fabro ps --server https://hp-xubuntu.perch-rudd.ts.net:32278` listed one
  running run at the time (fabro-currency's canary on `bd-ib-kgo6f6`).

## Where hostnames are hard-coded today

- `livespec-dev-tooling/ansible/fabro-hosts.yml`: `hosts: hp-xubuntu` and
  `hosts: vps`. Also `dev-host.yml` (`hosts: vps`) and `poweredge-backup.yml`
  (`hosts: poweredge-xubuntu`).
- Role defaults and tasks that name a machine, found by a grep of
  `roles/*/{defaults,tasks,templates}` for the four machine names: twenty
  roles, among them `fabro_server`, `docker_sandbox_slice`, `disk_guard` and
  `sccache_redis`. Each hit still has to be classified: a value or a branch on
  a machine name is placement; a comment recording where a number was
  measured is provenance.
- This repository's `.livespec.jsonc`: `dispatcher.factories.hp.server` is
  `https://hp-xubuntu.perch-rudd.ts.net:32276`. fabro-currency's canary
  posture (uncommitted, worktree `canary-hp-candidate`) adds `hp-candidate` =
  `https://hp-xubuntu.perch-rudd.ts.net:32278`.
- Each Fabro instance's `canonical_host` and settings URLs are a tailnet name
  by construction, and they live in `host_vars`, which assertion 3 permits.

## Design direction

1. **Plays target groups.** A factory host is a member of a factory group in
   `inventory/legacy.yml`; every play names a group, never a machine. The
   sandbox-host facilities a factory host needs (Docker, the sandbox slice,
   the Fabro instances, container and disk hygiene) are selected by group
   membership, and machine-specific extras (hp's second disk, for example) by
   host variables or a narrower group.
2. **A committed Docker-engine role with a dead-man rollback.** Before any
   change it snapshots `iptables-save`, `ip6tables-save` and
   `nft list ruleset`, and starts a transient systemd timer that, unless a
   confirmation file appears in time, restores the snapshot and stops and
   masks docker. The confirmation is written only after a fresh Tailscale SSH
   round-trip from the control node AND after k3s pod networking and the
   llama server both answer. `daemon.json` states its firewall posture
   explicitly (`iptables`, `ip-forward`, and whether Docker may set the
   FORWARD policy) chosen for coexistence with flannel and kube-router. The
   design is reviewed by an independent read-only Codex reviewer before the
   first converge on gmktec.
3. **The fabro_server role covers the gaps a fresh host exposes.** On gmktec
   the role's preflight will refuse today: no checkout of this repository at
   `fabro_server_host_checkout`, and no `server.env`. The checkout is
   provisioning, so the role (or a sibling role) clones and pins it. The
   `server.env`, the GitHub App private key and the `tailscale serve` mapping
   stay out-of-band exactly as the role documents, which assertion 1 allows.
4. **Factory addresses become logical.** A committed factory entry names a
   logical factory and an address that does not name a machine. The candidate
   mechanism is a Tailscale Service (a tailnet-wide virtual name that the
   hosting node advertises through `tailscale serve`), which also carries over
   to the Kubernetes operator later. It needs a `policy.hujson` change in the
   `tailscale-admin` repository and is a serve-config change, not a tailscaled
   restart or reconfiguration. fabro-currency is told before any committed
   factory-table change here, because its canaries dispatch by factory name.
5. **Parity is measured, not asserted.** Assertion 2 is proven by dispatches
   routed to the gmktec instance that reach a merged pull request through every
   workflow stage, including the four stages fabro-currency had not yet seen on
   Petri at 2026-10-15 03:37Z (`proof_verify`, `pr_refresh`, `pr`,
   `verify_pr`). Every dispatch needs the fleet coordinator's allowlist
   admission and runs under the host-wide dispatch lock.

## Safety constraints, binding on every step

The maintainer is travelling and cannot reach gmktec-xubuntu physically.

- Access is Tailscale SSH only; OpenSSH is inactive.
- Never restart, reconfigure or upgrade tailscaled. Never change netplan,
  NetworkManager, interfaces, routes, or forwarding sysctls. Never reboot.
  Never run an apt upgrade that pulls kernel, systemd, network or tailscale
  packages; package installs name exact packages with no upgrade of others.
- Every step that changes firewall rules carries the automatic rollback above.
- `local-homelab-llama-server.service` and `k3s-agent` keep running.
- Coordinate with `k3s-on-gmktec-for-vps-usage` (owns this host's k3s plan,
  livespec repository) before claiming CPU, disk or firewall changes; also
  `factory-worker-nodes-gitops` and
  `gitops-deployment-instructions-and-enforcement`.
- The fleet coordinator `gitops-fleet-capacity-monitoring` runs a factory
  stability freeze (epic `livespec-dev-tooling-dfixhe`). It confirmed on
  2026-10-15 that this plan holds a dedicated slot on the current Fabro server
  at hp:32278, that both dedicated slots move with the server to gmktec, that
  every dispatched item needs its allowlist admission, and that
  infrastructure pull requests in livespec-dev-tooling follow that
  repository's mutation protocol without admission. It sets the gmktec
  instance's ceiling once told the URL and cap.
- Do not stop the hp:32278 instance until fabro-currency confirms its
  in-flight canaries have ended; the stop is the gitops
  `service_state: stopped` converge with `fabro_server_interrupt_runs_allowed`
  left false.
- Host changes go only through `just ansible-drift` then `just ansible-apply`
  from the control node; the fleet host guard denies hand mutation.

## Prior art (livespec-dev-tooling ledger, `--status all`, 838 items)

- `livespec-dev-tooling-3zsngb` (acceptance): per-instance binary install from
  the control node. The gmktec instance uses it.
- `livespec-dev-tooling-fe62lh` (closed): per-instance sandbox environment
  catalog. The gmktec instance declares `livespec-ci` through it.
- `livespec-dev-tooling-vmeiv6` (acceptance): deferred restart markers.
- `livespec-dev-tooling-ig5iwg` (closed): the Docker sandbox slice on hp.
- `livespec-dev-tooling-7we6po` (acceptance): hp joins the k3s pool as a
  factory-only agent; the reference for Docker-beside-k3s on hp.
- `livespec-dev-tooling-frei6s`, `-a2kwn3`, `-hatvwq`, `-z7nfhx` (backlog):
  gmktec pool-member obligations owned by the k3s plan; none touch Docker.
- No item installs Docker by role; hp's Docker was installed by hand.
