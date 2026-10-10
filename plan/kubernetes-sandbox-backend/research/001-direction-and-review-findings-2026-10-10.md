## The maintainer's statement of what done means

we are going to be managing our own Kubernetes cluster (currently on HP and, in the future, with other workers elsewhere to provide capacity)

## Definition of Done assertions derived from that statement

- A dispatch routed to the hp factory with the Kubernetes provider selected runs its ImplementWorkItem workflow in a pod on the maintainer-owned cluster and produces a merged pull request.
- The pod that runs a dispatch carries CPU and memory requests and limits equal to the workflow's declared resources, and `kubectl describe pod` on the factory host shows them.
- A dispatch that reaches the needs-human exit on the Kubernetes backend terminates its run with its workspace retained, and `fabro dump` of that run on the factory host exports the implement stage diff.
- A dispatch executes on a worker node other than hp and its run_turn record in Honeycomb names the stable factory identity and the node that ran it.
- After `dispatcher.default_factory` selects the Kubernetes backend, the Docker sandbox slice on hp is retired and the runbook records the retirement and the rollback to the Docker backend.

# 001 — direction, review findings and sequencing (2026-10-10)

## Why this plan exists

Plan fabro-currency (epic bd-ib-6tcjfx) moves the self-hosted dark factory
onto the Petri-era Fabro. Measured 2026-10-09 and 2026-10-10 in that plan:
Petri's Docker backend runs sandboxes unconstrained by design (its own
frontend diagnostic: resource limits apply to a Daytona runner; the host and
Docker providers run unconstrained), so the cutover drops the per-run CPU
and memory limits the hp over-subscription plan relies on. Daytona, the
backend Petri does constrain, is a hosted service whose open-source
repository is archived (last push 2026-07-24). The maintainer ruled on
2026-10-10 that the factory's sandboxes move to a maintainer-owned
Kubernetes cluster: hp first, more worker nodes later for capacity. Per-run
limits then come from pod requests and limits; no Petri fork and no Petri
resource-forwarding change is made.

## What upstream has said

- fabro-sh/fabro PR 567 (a Firecracker provider) was closed on 2026-10-07:
  backends are third-party plugins over the sandbox-driver JSON-RPC
  protocol v2, maintained and distributed by their authors.
- fabro-sh/fabro issue 937 (open, 2026-10-07) is the missing wiring: Fabro
  constructs Petri with only Host, Docker and Daytona factories, so a
  configured plugin cannot yet execute workflows. It requires lifecycle,
  configuration, capability, network, recovery and pruning consistency.
- A complete Kubernetes provider exists in mhermann/fabro PR 4 (merged into
  that fork 2026-09-11, pod per run, exec API, NetworkPolicy, about 5,000
  lines) against the pre-Petri sandbox layer; never offered upstream. No
  published implementation or commitment for Kubernetes was found in
  fabro-sh/fabro, lithoscomputer/petri or lithoscomputer/sandbox-driver.

## Findings from the 2026-10-10 independent review that bind this plan

Full critique: plan/fabro-currency/research/008-independent-review-and-corrections-2026-10-10.md.

1. Kubernetes does not close the resource gap until the full path
   workflow resources -> Fabro -> Petri -> plugin SandboxSpec -> pod
   requests and limits is proven. Petri's SandboxOptions has no generic
   resource field, its routing selects only Docker and Daytona for container
   execution, and its in-process path refuses missing providers rather than
   launching a plugin. The first deliverable is the minimal generic
   extension design across Fabro and Petri, proposed upstream early and
   independently of building the backend.
2. Protocol v2 is a local contract: control over stdin and stdout, data
   over authenticated Unix-domain sockets in a private directory,
   interleaved operations, reserved cancellation capacity. The plugin runs
   beside the Fabro worker and talks to the cluster remotely. Petri's ACP
   step needs a long-lived process with writable stdin and readable
   stdout, not a buffered exec response. The plugin host's own capture
   memory is bounded by configuration, not by pod limits.
3. Retained workspace, stop and start fencing, attach, retention and
   pruning must be designed before cutover. Petri selects Retention::Always
   and LostSandbox::Refuse and fences recovery with stop then start; the
   fork's pod manifest has no durable workspace volume and uses
   restart_policy Never. A logical sandbox identity independent of a pod
   UID, a workspace persistence choice and node-loss policy are required.
   Petri labels (petri.run, petri.lease, petri.workspace with a slash) need
   lossless encoding as Kubernetes label values.
4. k3s on hp coexists with the Docker slice only under a shared budget:
   k3s pods run under containerd, not the Docker slice; at 8 GB requests a
   30 GB host schedules three such pods, not fifteen; Traefik and ServiceLB
   defaults take ports 80 and 443; reservations and eviction thresholds
   must be set deliberately.
5. Pod connectivity is an end-to-end contract: which process receives
   each credential by which existing channel (Petri resolves only named
   secret references into the agent environment; the protocol scrubs the
   plugin environment and defers host credentials), the guarded bd binary
   and tenant pointers, GitHub App clone, push and PR flow, OAuth-only ACP
   authentication, registry pulls, DNS, the telemetry receiver, and
   tailnet reach from a second node.
6. Factory identity stays livespec.dispatch.factory; cluster, node,
   namespace, pod and lease are added dimensions.
7. Ownership: backend releases, checksums and protocol compatibility
   belong to the plugin repository; generic integration belongs with
   Fabro and Petri; hp provisioning belongs with the infrastructure owner.

## Sequencing

1. Design: minimal generic provider and resource extension across
   fabro-petri and Petri, proposed upstream as an issue; capability
   contract limited to streamed stdio, exec, files, labels, lifecycle and
   required network policy; logical sandbox identity and workspace
   persistence; coexistence budget and network design for hp.
2. Cluster: k3s on hp under the agreed budget; registry access for the
   sandbox image; pod-to-tailnet reach to the beads Dolt tenant and the
   telemetry receiver verified; the credential contract proven.
3. Plugin: a Kubernetes sandbox-driver plugin (protocol v2) in a
   maintainer-owned repository, ported from the fork's pod and exec
   mechanics, proven against the sandbox-driver conformance suite, pinned
   by checksum on every execution host.
4. Fabro wiring for plugin execution through Petri (issue 937): a branch
   on the existing thewoolleyman/fabro fork cut from the carrier rebuilt by
   fabro-currency's bundle, offered upstream once proven.
5. Lifecycle proofs before cutover: cancel, crash and restart, API outage
   after create, node loss, resume on the original workspace, retained
   attach, dump and rescue, cleanup, pod resource enforcement.
6. Canary dispatches; default_factory cutover to the Kubernetes backend;
   retirement of the Docker slice; rescue tooling ported to pod equivalents.
7. Version floor gate regroomed from the currency admission work.
8. Worker nodes elsewhere for capacity; the correlation attribute gains
   node and pod dimensions and is re-proven on a second node.

Hard dependency: step 4 starts after fabro-currency's bundle
(bd-ib-sxcnj7) lands. Steps 1 to 3 are independent of fabro-currency.
