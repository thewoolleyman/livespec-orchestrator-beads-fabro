# 002 — the cluster that already exists, and the ruling that keeps node provisioning out of this plan (2026-10-10)

## Why this note exists

Research note 001 sequenced this plan as "k3s on hp first, more worker nodes
later", as if no cluster existed. At the first attended resume on 2026-10-10 the
maintainer asked whether a Kubernetes worker already ran on the gmktec box. It
does, as part of a cluster this plan had not accounted for. This note records
what was measured, the maintainer's ruling on scope that followed, and the
corrected sequencing. Where this note and note 001 disagree, this note wins.

## What was measured, live, on 2026-10-10

Every figure below was read from the host named, over tailnet ssh, between
18:30 and 18:35 PDT on 2026-10-09 (01:30 to 01:35 UTC on 2026-10-10).

### The cluster

| Node | Role | Hardware | k3s | State |
|---|---|---|---|---|
| `poweredge-xubuntu` | control plane | 72 CPUs, 377 GB RAM | v1.36.2+k3s1 | Ready |
| `gmktec-xubuntu` | agent, label `k3s-role=arc-runner-host` | 32 threads, 62 GB RAM | v1.36.2+k3s1 | NotReady since 2026-09-28 19:47 PDT |
| `hp-xubuntu` | not a node | 16 CPUs, 30 GB RAM | none installed | runs the Docker Fabro sandboxes (five live containers at measurement) |

The control plane's datastore is a 2 GB tmpfs (`findmnt` on
`/var/lib/rancher/k3s/server/db`), empty at every boot; the cluster's objects
are reconstructed from git by a boot-time converge. The cluster is the fleet's
CI pool: ARC runner listeners for every livespec repository, Kueue, a registry
mirror, crates and PyPI proxies, a warm-cache cron and the delegated-gate
`gates` namespace. All of those pods run on poweredge. Nothing runs on gmktec.

### Why gmktec is NotReady

poweredge booted at 2026-09-28 19:45:18 PDT. The node object
`gmktec-xubuntu` was created at 19:46:11. gmktec's `/etc/rancher/node/password`
carries a modification time of 19:46:14, three seconds later. The kubelet
stopped posting status at 19:47:05, and the node has carried the taint
`node.kubernetes.io/unreachable:NoExecute` since. gmktec's `k3s-agent` unit has
been in state `activating` since 19:46:13 and its journal repeats, every ten
seconds:

```text
Waiting to retrieve agent configuration; server is not ready:
/var/lib/rancher/k3s/agent/serving-kubelet.crt: Node password rejected,
duplicate hostname or contents of '/etc/rancher/node/password' may not match
server node-passwd entry
```

The server holds a `gmktec-xubuntu.node-password.k3s` secret in `kube-system`
aged 10 days, created at the same rebuild. The node registered with one
password and its password file was rewritten moments later, so the stored
entry and the file no longer match. The repair is the standard k3s one: delete
that secret and restart the agent, or the owning plan's converge equivalent.
It was NOT performed by this plan's session, for the reason in the next
section.

### Who owns that cluster

livespec plan `k3s-on-gmktec-for-vps-usage` (epic `livespec-sab5gn`) joined
gmktec to the poweredge cluster and designed the delegated-gate Job primitive.
Its latest handoff (2026-09-12) carries a maintainer direction that nobody
converges or touches any host until plan `gitops-deployment-discipline` (epic
`livespec-qurhq2`) is fully landed. Both epics sit at `backlog` with no
activity since 2026-09-12. That plan's research/003 lists "moving fabro's
docker sandboxes onto the Job primitive" and "`hp-xubuntu` as a gate host" as
enabled by it and out of its scope.

## The maintainer's ruling (2026-10-10, recorded verbatim on the epic as a scope event)

> I don't think it should be part of this plan. I think we should have separate
> plans, whether they are existing ones or new ones, to get GMKTEC, and HP fully
> up with proper GitOps discipline as worker nodes. I can go ahead and wrap up
> those plans, and not muddy this plan with Kubernetes dependencies and
> infrastructure that will probably not be implemented properly because of the
> lack of focus.

Consequences, as recorded in the scope event:

- Cluster and node provisioning is out of this plan. No child of this epic
  installs, joins, repairs or converges a node or control plane.
- A Ready maintainer-owned cluster with at least one non-hp worker is a hard
  external dependency, owned by separate plans in the livespec repository that
  the maintainer drives, exactly as the fabro-currency bundle `bd-ib-sxcnj7` is
  an external dependency for the Fabro wiring child.
- This plan's scope is sandbox-side only: the generic provider and resource
  extension design across fabro-petri and Petri proposed upstream; the
  sandbox-driver protocol v2 Kubernetes plugin in a maintainer-owned
  repository; the Fabro plugin-execution wiring (fabro-sh/fabro issue 937); the
  dispatcher and credential contract from the factory host to pods; lifecycle
  proofs; canary dispatches; the `default_factory` cutover; Docker-slice
  retirement and the runbook.

The five Definition of Done assertions were confirmed as written by the
maintainer in the same exchange. Assertion 1's "maintainer-owned cluster" is
whichever cluster the node plans deliver. Assertion 4's "worker node other than
hp" is satisfied by gmktec once its owning plan brings it to Ready; this plan
does nothing to make that happen.

## What the ruling changes in note 001

- Sequencing step 2 ("Cluster: k3s on hp under the agreed budget; registry
  access; pod-to-tailnet reach; the credential contract proven") is removed as
  work and replaced by the external dependency above. The parts of it that are
  genuinely this plan's — which process receives each credential by which
  channel, and what the plugin needs from a kubeconfig that rotates at every
  control-plane boot — move into the design child and the plugin child as
  contract text, not provisioning.
- Review finding 4 ("k3s on hp coexists with the Docker slice only under a
  shared budget") becomes an input the node plan for hp must honour, not a
  deliverable here. It stays cited so the hp plan inherits it.
- Review finding 5 (pod connectivity as an end-to-end contract) is split: the
  plugin-to-cluster and pod-to-service contract is this plan's design work; the
  network reach itself (tailnet from a second node, registry pulls, DNS) is the
  node plans' to provide and this plan's lifecycle proofs to observe.
- The "hp first" ordering no longer describes topology. The first node a
  factory pod lands on is whichever node the node plans make Ready first; the
  plugin schedules by node selector and must not assume hp.

## Corrected sequencing

1. Design child (independent of everything): minimal generic provider and
   resource extension across fabro-petri and Petri, proposed upstream as an
   issue; capability contract limited to streamed stdio, exec, files, labels,
   lifecycle and required network policy; logical sandbox identity and
   workspace persistence; the credential and kubeconfig-rotation contract the
   plugin will honour.
2. Plugin child: the Kubernetes sandbox-driver plugin (protocol v2) in a
   maintainer-owned repository, ported from the mhermann/fabro fork's pod and
   exec mechanics, proven against the sandbox-driver conformance suite with a
   kind or k3d cluster in CI, pinned by checksum on every execution host.
   Depends on 1.
3. Fabro wiring child (issue 937) on the thewoolleyman/fabro fork. Depends on
   `bd-ib-sxcnj7` landing and on 1.
4. Lifecycle proofs against the real cluster: cancel, crash and restart, API
   outage after create, node loss, resume on the original workspace, retained
   attach, dump and rescue, cleanup, pod resource enforcement. Depends on 2, 3,
   and the EXTERNAL dependency: a Ready cluster with a factory namespace.
5. Canary dispatches, `default_factory` cutover, Docker-slice retirement,
   rescue tooling ported to pod equivalents, runbook with rollback.
6. Version floor gate regroomed from the currency admission work.
7. Second-node proof: a dispatch on a non-hp worker with the correlation
   attribute carrying node and pod dimensions. Depends on the external
   dependency delivering that worker.

## Open items for the maintainer's planning discussion (not this plan's)

- Which plan repairs gmktec: `k3s-on-gmktec-for-vps-usage` once un-gated, or a
  fresh one.
- Which plan joins hp as a worker, and whether the Docker slice and k3s share
  hp during the transition (review finding 4's budget).
- Whether poweredge itself should run factory pods, given it has the most
  capacity and already hosts the CI pool.
- Whether `gitops-deployment-discipline` remains the gate for all of it.
