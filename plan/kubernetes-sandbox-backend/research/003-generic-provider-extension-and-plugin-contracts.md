# 003 — the generic provider and resource extension, the plugin capability contract, logical sandbox identity, and the credential and kubeconfig-rotation contract (2026-10-13)

## Why this note exists

This is the design every later child of plan `kubernetes-sandbox-backend`
(epic `bd-ib-nmuyjc`) builds on. It changes no code in this repository,
creates no Petri fork, touches no host, and posts nothing outside
maintainer-owned repositories. It carries four contracts and one draft
upstream issue:

1. the minimal generic provider and resource extension across `fabro-petri`
   and Petri, traced hop by hop at the pinned revisions (§2, §3);
2. the draft upstream issue text, postable verbatim (§4);
3. the plugin capability contract — which protocol v2 operations the plugin
   serves, which it refuses and with what response, where the plugin runs,
   and its host capture memory envelope (§5);
4. logical sandbox identity, workspace persistence, `LostSandbox` and
   node-loss policy, stop/start fencing mapped onto pod operations, and
   lossless label encoding — each with its recovery path after a
   control-plane rebuild that drops every API object (§6);
5. the credential contract, the kubeconfig-rotation mechanism, and the
   requirement list this plan hands to livespec plan
   `factory-worker-nodes-gitops` (§7).

Read `research/002-existing-cluster-measurements-and-scope-ruling-2026-10-10.md`
first for the cluster that exists and the scope ruling, then
`research/001-direction-and-review-findings-2026-10-10.md` for the review
findings that bind this plan (its sequencing section is superseded by 002),
then `plan/fabro-currency/research/008-independent-review-and-corrections-2026-10-10.md`
§§6–8 for the Petri and protocol evidence this note re-measures.

## 1. Revisions measured, and where the sources have moved on

Every source was cloned and read at the revision named here, on 2026-10-13.
The work-item named `v0.382.0-nightly.0`; the revisions the other two
repositories are read at are the ones **that tag's `Cargo.lock` pins**, which
is the only place the pin exists — `Cargo.toml` declares `branch = "main"`
for every Petri and sandbox-driver dependency
(`Cargo.toml:93–100`, `Cargo.toml:111–117`), so the `Cargo.toml` names no
revision at all and a reader who stops there has no pin.

| Source | Cited / pinned revision | Date | Current tip on 2026-10-13 | Moved on? |
|---|---|---|---|---|
| `fabro-sh/fabro` | tag `v0.382.0-nightly.0` = `5f82fb086e767576ccb2437fa2cd75d0a3957473` | 2026-10-10 | `v0.385.0-nightly.0` | yes, 3 nightlies |
| `lithoscomputer/petri` | `2548c104e1b0b5ac710abc59b25724d6b2c4d66d` (from `Cargo.lock:5169`) | 2026-10-08 | `8675cb898045a9f03876a3a7fe2afe6b90293850` | yes, through PR #115 |
| `lithoscomputer/sandbox-driver` | `90b0d825767105d4b42e59fdbd116c4d66b87d83` (from `Cargo.lock`) | 2026-10-08 | `b1ea75451c1c2c2790783ca2dcbb1ec36c3ae051` | yes, through PR #67 |
| `mhermann/fabro` PR 4 | merge `7c14f9ae6c3e9997a2aca487b807f0dd0e363251` | merged 2026-09-11 | — | read at the merge |

Two divergences from the citations in the notes this plan inherits, recorded
because each is a correction rather than a restatement:

- Review note 008 §7 cites protocol v2 at
  `7d1932b5fd758dbc67ae5a34aaed08d8733ddaba`. The tag pins
  `90b0d825`. This note reads `90b0d825`, the revision the factory would
  actually consume. The protocol facts 008 relies on hold at both.
- Review note 008 §6 locates container-spec construction at
  "`executor-sandbox/src/lib.rs:479`" without naming the repository.
  `executor-sandbox` is a **Petri** crate
  (`petri/crates/core/executor-sandbox/`), not a Fabro one. At the revision
  this note measures, line 479 is the doc comment immediately above the
  **generic** container path `fn build_spec` (`lib.rs:481`); the
  Daytona-specific path is `fn build_daytona_spec` (`lib.rs:402–477`), the
  method that chooses between them is `lib.rs:324`, and the choice itself is
  `lib.rs:366`. §2 traces all three.

Petri and sandbox-driver are tracked by branch, so the version floor this
plan hands to the admission work (plan child 6, regroomed from the currency
admission work) must pin by **`Cargo.lock` revision**, not by Fabro tag
alone: two builds of the same Fabro tag rebuilt a week apart can carry
different Petri revisions.

## 2. Where the workflow's resources die, traced hop by hop

The gap review note 008 §6 states is real and is one `if`. The table below
traces the field that carries workflow resources at every hop, from this
repository's own workflow declaration to pod requests and limits. Every row
was read at the revision in §1.

| # | Hop | Type and field | Location | State of the resource value |
|---|---|---|---|---|
| 1 | Workflow declaration | `cpu = 4`, `memory = "8GB"` | this repo, `.claude-plugin/.fabro/workflows/implement-work-item/workflow.toml:407–409` (`[environments.livespec-ci.resources]`) | **declared** |
| 2 | Fabro settings | `EnvironmentResourcesSettings { cpu: Option<i32>, memory: Option<Size>, disk: Option<Size> }` | fabro `lib/foundation/fabro-types/src/settings/run.rs:1145–1149` | **carried** |
| 3 | Fabro run request | `RunRequest.resources: EnvironmentResourcesSettings` | fabro `lib/components/fabro-petri/src/engine.rs:117` | **carried** |
| 4 | Fabro → Petri options | `if backend == SandboxBackend::Daytona { options.sandbox.daytona_resources = daytona_resources(&request.resources)?; }` | fabro `lib/components/fabro-petri/src/engine.rs:236–237` | **DROPPED for every backend except Daytona** |
| 5 | Petri run options | `SandboxOptions.daytona_resources: DaytonaResources { cpu_cores, memory_mb, disk_mb }` | petri `crates/core/executor-sandbox/src/backend.rs:79`, `:119–129` | Daytona-shaped only; **no generic field** |
| 6 | Petri spec build, non-Daytona | `if self.options.backend != SandboxBackend::Daytona { … return build_spec(scope, labels, name, ctx); }` | petri `crates/core/executor-sandbox/src/lib.rs:366–379`, into `fn build_spec` at `lib.rs:481` | `build_spec` **never assigns `spec.resources`** |
| 7 | Petri spec build, Daytona | `RunnerSnapshot::new(&image, self.options.daytona_resources.validated()?, …)` then `spec.resources = resources` | petri `lib.rs:380–383`; `snapshots.rs:39` | **assigned — the only populate site in the crate** |
| 8 | Driver spec | `SandboxSpec.resources: Resources` | sandbox-driver `crates/sandbox-driver/src/spec.rs:180` | field **already exists and is generic** |
| 9 | Protocol wire DTO | `SandboxSpecDto.resources: Resources` | sandbox-driver `crates/sandbox-driver-protocol/src/methods.rs:194` | **already on the wire** |
| 10 | Generic resource type | `Resources { cpu_cores: Option<u32>, memory_mb: Option<u64>, disk_mb: Option<u64>, gpus: Option<u32> }` | sandbox-driver `crates/sandbox-driver/src/spec.rs:41–49` | **already provider-neutral** |
| 11 | Pod requests and limits | — | the plugin child builds this | reachable **only if hops 4–7 are fixed** |

Read the table as one sentence: **the generic resource field already exists
at the driver layer and is already on the wire; it is Petri and Fabro that
only ever fill it for Daytona.** A Kubernetes plugin receiving
`SandboxSpec` today gets `resources: Resources::default()` — every field
`None` — for a non-Daytona backend, so it has nothing to put in pod
requests and limits. Kubernetes enforces only what it receives, which is
review note 008 §6's point, now localised to hops 4, 5, 6 and 7.

`Resources` is `#[non_exhaustive]` (`spec.rs:43`), so adding a field to it
upstream is not a breaking change for external constructors.

### 2.1 The second closure: provider selection

Resources are not the only thing closed. Two independent gates refuse a
plugin kind before any spec is built.

| Gate | Shape | Location | Behaviour for a `kubernetes` kind |
|---|---|---|---|
| Fabro's provider → backend map | `fn backend(provider: &SandboxProviderKind) -> Option<SandboxBackend>`, matching only `LOCAL`, `DOCKER`, `DAYTONA`, else `None` | fabro `fabro-petri/src/engine.rs:484–493` | `None` → `RunError::UnsupportedProvider` at `engine.rs:222–224` |
| Petri's backend enum | `enum SandboxBackend { Host, Docker, Daytona }`, closed; `FromStr` rejects anything else with "expected host, docker, or daytona" | petri `backend.rs:16–49` | unrepresentable |
| Petri's plugin-kind projection | `fn plugin_kind(&self) -> &'static str`, mapping `Host \| Docker => "docker"`, `Daytona => "daytona"` | petri `routing.rs:268–276` | can only ever name `docker` or `daytona` |
| Petri's in-process path | `factory(kind)` → "the {kind} provider is not configured in this process, and no provider plugin is launched when built-in providers are linked in" | petri `in_process.rs:194–201` | refuses rather than launching a plugin |

What is **already open**, and therefore needs no change:

- `sandbox_driver::ProviderKind` is a validated newtype, not an enum, and
  says so: "Deliberately not an enum — new providers must not require
  changes here. Kinds are lowercase ASCII letters, digits, and hyphens"
  (`sandbox-driver/src/id.rs:108–113`). `kubernetes` is a valid kind.
- `fabro_types::SandboxProviderKind` is likewise a newtype over
  `Cow<'static, str>` (`sandbox_provider.rs:24`), with the closed
  `BundledProvider` enum reserved for in-tree providers
  (`sandbox_provider.rs:31–36`) — exactly the split issue 937 proposes
  keeping.
- Plugin discovery is already fully generic over the kind string:
  `PluginSettings::from_env` reads `PETRI_SANDBOX_<KIND>_PLUGIN`,
  `PETRI_SANDBOX_<KIND>_SHA256` and `PETRI_SANDBOX_<KIND>_HOST_ADDRESS`
  by uppercasing the kind (`petri/plugin.rs:195–208`). A `kubernetes`
  kind reads `PETRI_SANDBOX_KUBERNETES_*` with no code change.
- `infer_host_address` takes an explicitly configured address first and
  only falls through to per-kind inference
  (`petri/plugin.rs:320–339`). A `kubernetes` kind supplying
  `PETRI_SANDBOX_KUBERNETES_HOST_ADDRESS` is already served; only the
  default-inference arm refuses an unknown kind.
- `supports_host_workspace()` returns `kind == "docker" && local`
  (`petri/plugin.rs:273–276`), so a `kubernetes` kind gets `false`. That
  is **correct** for a remote cluster, not a defect: there is no host
  directory to bind-mount into a pod on another node.

### 2.2 The third closure: the plugin environment allowlist

One further hardcoded per-kind list matters specifically to this plan, and
it is not in review note 008. `forwarded_env(kind)`
(`petri/plugin.rs:73–106`) is what the plugin process inherits — everything
else is scrubbed. It returns `PATH`, `HOME`, `RUST_LOG` for every kind, then
extends per kind: `host` gets `USER`/`SHELL`/`LANG`/… , `docker` gets
`DOCKER_HOST`/`DOCKER_TLS_VERIFY`/`DOCKER_CERT_PATH`/`DOCKER_API_VERSION`/`DOCKER_CONFIG`,
`daytona` gets `DAYTONA_API_KEY`/`DAYTONA_JWT_TOKEN`/`DAYTONA_ORGANIZATION_ID`/`DAYTONA_API_URL`/`DAYTONA_TARGET`,
and the default arm is `_ => {}`.

So a third-party `kubernetes` kind inherits **`PATH`, `HOME` and `RUST_LOG`
and nothing else** — in particular **not `KUBECONFIG`**.

This is a constraint, not a blocker, and §7.2 turns it into the
rotation mechanism rather than working around it: because `HOME` *is*
forwarded, the plugin reads the kubeconfig from the client-go default path
`$HOME/.kube/config`, which needs no new forwarded variable and is the
reason rotation works without a restart.

### 2.3 The minimal extension, stated as a change list

Four changes, in two repositories, no fork:

| Repository | Change | Why minimal |
|---|---|---|
| Petri | Add `SandboxOptions.resources: Resources` (the existing `sandbox_driver::Resources`) alongside `daytona_resources`, and assign `spec.resources` from it in `build_spec`'s non-Daytona path. | Reuses a type Petri already imports (`backend.rs:10`) and a `SandboxSpec` field that already exists. Leaves `DaytonaResources` and its runner-minimum validation untouched. |
| Petri | Let `SandboxBackend` name a plugin kind — either a `Plugin(ProviderKind)` variant or replacing the enum with the already-open `ProviderKind` — so `plugin_kind()` can return it. | `ProviderKind` validation already exists; `PluginSettings::from_env`, host-address configuration and pin enforcement are already generic. |
| Petri | Make `forwarded_env` extensible for a non-bundled kind (a configured allowlist), or document `HOME`-relative credential discovery as the supported route. | §7.2 shows the factory needs no new variable, so this is the *optional* half of the extension. |
| Fabro | Map an unbundled `SandboxProviderKind` to that plugin backend in `backend()`, and forward `request.resources` for **every** container backend rather than for Daytona alone (`engine.rs:233` already does exactly this for `network`). | The `network` line one above it is the precedent: it forwards to every non-`Host` backend. Resources should follow the same rule. |

The `network` precedent is worth stating plainly because it settles the
shape of the fix: `engine.rs:233` reads `if backend != SandboxBackend::Host
{ options.sandbox.network = network_policy(&request.network); }` while
`engine.rs:236` reads `if backend == SandboxBackend::Daytona`. One forwards
to every container backend; the other to one named provider. Resources want
the first form.

## 3. What this plan does **not** ask upstream for

Recorded so the issue stays minimal and so a later child does not re-open
settled scope:

- No Kubernetes provider in Fabro or Petri. The backend is a third-party
  plugin, per PR 567's closure and issue 937's own framing.
- No change to `SandboxSpec`, `Resources`, `NetworkPolicy`,
  `ProviderKind`, the protocol, or the wire DTO. All four are already
  generic (§2, hops 8–10).
- No change to plugin discovery, checksum pinning, or dev mode
  (`petri/plugin.rs:195–208` is already kind-generic).
- No telemetry carry. Plan `fabro-currency` owns that.

## 4. Draft upstream issue, for the maintainer to post verbatim

The maintainer posts this; no agent session does (see the Human-attested
assertion on `bd-ib-fghubm`). Post to **`fabro-sh/fabro`**, as a
follow-on referencing issue 937. Record the issue number back into this
section when it is posted.

> **Posted 2026-10-20, in a different shape from the draft below.** The draft
> was never posted. On 2026-10-20 a prior-art check found that the Petri
> maintainers' own lithoscomputer/petri PR #122 (for Petri issue #114) already
> does the plugin backend selection, and that fabro-sh/fabro #937 already
> states the Fabro half. The work was therefore rebased onto #122, and only
> the new gap was posted:
>
> - Issue **lithoscomputer/petri#130**: "Let a run size its sandbox on a
>   registered provider".
> - PR **lithoscomputer/petri#131**, stacked on #122: per-run resources over
>   the registered template.
> - Draft PR **fabro-sh/fabro#1048**, for #937: registering
>   `[server.sandbox.providers.<kind>]` plugins through #122's
>   `register_plugin`.
>
> Research note 004 records the finding and the measurements behind it.
> The draft below is kept as written, for the history of the reasoning.

---

**Title:** Forward workflow resource settings to every container backend, and let a plugin backend be selected through Petri

Issue #937 tracks carrying configured sandbox plugins into workflow
execution. This issue is the narrower, separable half that #937's scope
bullet "Make configured plugin providers available to Petri for sandbox
creation and execution" depends on, and which can land independently of any
particular backend: today a workflow's declared CPU, memory and disk reach
the provider **only** when the backend is Daytona, so a plugin backend that
could enforce them receives nothing to enforce.

We are building an out-of-tree Kubernetes sandbox-driver plugin (protocol
v2) for a self-hosted factory, exactly as the closure of #567 describes.
Pod `requests` and `limits` are the mechanism we need per-run CPU and memory
from. Kubernetes enforces only the resource specification it is given, so
the plugin cannot recover settings that were discarded before it was
invoked. We would rather not fork Petri to fix that, because a fork would
have to be rebased against a branch-tracked dependency indefinitely and
would give every other plugin author the same problem; the change below
looks small enough to be generally useful.

### What we measured

At `fabro-sh/fabro` tag `v0.382.0-nightly.0`, whose `Cargo.lock` pins
`lithoscomputer/petri` at `2548c104e1b0b5ac710abc59b25724d6b2c4d66d` and
`lithoscomputer/sandbox-driver` at
`90b0d825767105d4b42e59fdbd116c4d66b87d83`:

The generic plumbing already exists and is already on the wire.
`SandboxSpec.resources: Resources` is a field
(`sandbox-driver/crates/sandbox-driver/src/spec.rs:180`), `Resources` is
provider-neutral and `#[non_exhaustive]`
(`spec.rs:41–49`), and `SandboxSpecDto.resources` is serialized
(`sandbox-driver-protocol/src/methods.rs:194`). `ProviderKind` is
deliberately a validated newtype rather than an enum, with the comment "new
providers must not require changes here" (`sandbox-driver/src/id.rs:108–113`),
and `fabro_types::SandboxProviderKind` matches that shape
(`fabro-types/src/sandbox_provider.rs:24`).

Three things nonetheless close the path:

1. `fabro-petri` forwards resources to Daytona only. `engine.rs:236–237`
   reads `if backend == SandboxBackend::Daytona { options.sandbox.daytona_resources = … }`.
   The line immediately above it, `engine.rs:233`, forwards the network
   policy to **every** non-`Host` backend. Resources appear to want that
   same rule.
2. Petri's `SandboxOptions` has no generic resource field — only
   `daytona_resources: DaytonaResources`
   (`executor-sandbox/src/backend.rs:79`) — and the only site in the crate
   that assigns `spec.resources` is the Daytona snapshot path
   (`lib.rs:380–383` into `snapshots.rs:39`). The non-Daytona branch at
   `lib.rs:366` returns `build_spec(...)`, which never sets the field, so a
   non-Daytona container backend receives `Resources::default()` with every
   field `None`.
3. `SandboxBackend` is a closed three-variant enum (`backend.rs:16–49`) and
   `routing.rs:268–276` projects it to a `&'static str` that can only be
   `"docker"` or `"daytona"`, so a configured plugin kind cannot be named
   as a run's backend even though `PluginSettings::from_env` is already
   fully generic over the kind string (`plugin.rs:195–208`).

### What we propose

In Petri:

- Add a generic `SandboxOptions.resources: Resources`, reusing the
  `sandbox_driver::Resources` the crate already imports
  (`backend.rs:10`), and assign `spec.resources` from it on the generic
  container path. `DaytonaResources` and its runner-minimum validation
  (`backend.rs:142–160`) can stay exactly as they are; Daytona keeps
  overriding via its snapshot identity.
- Let a run's backend name a plugin kind — a `Plugin(ProviderKind)`
  variant, or using `ProviderKind` directly — so `plugin_kind()` can
  return it. Discovery, pinning, dev mode and configured host addressing
  already work for an arbitrary kind.

In Fabro:

- Forward `request.resources` for every container backend, matching the
  existing treatment of `network` at `engine.rs:233`.
- Map an unbundled `SandboxProviderKind` onto that plugin backend in
  `backend()` (`engine.rs:484–493`), keeping `BundledProvider` as the
  identity of in-tree providers exactly as #937 proposes.

One related detail we would welcome guidance on rather than assume:
`forwarded_env` (`plugin.rs:73–106`) carries a hardcoded per-kind
environment allowlist whose default arm is empty, so a third-party plugin
inherits only `PATH`, `HOME` and `RUST_LOG`. That is a reasonable default
and we are not blocked by it — our plugin reads its cluster credential from
a `HOME`-relative path, which also lets it pick up a rotated credential
without a restart — but if you would prefer a configured per-plugin
allowlist, we are happy to shape the change that way.

### How we would consume it

We pin Fabro by nightly tag on our own factory hosts and would consume this
from the **first `fabro-sh/fabro` nightly tag whose `Cargo.lock` carries the
Petri revision containing the change** — we pin by that lock revision rather
than by Fabro tag alone, because Petri is tracked by branch and two rebuilds
of one tag can carry different Petri commits. We are happy to open the pull
requests for both halves if the shape above is agreeable, and to test them
against a real cluster before they land.

### What this is not

Not a request for a Kubernetes provider in Fabro or Petri — our backend is
an out-of-tree plugin and stays that way, per #567's closure. Not a change
to `SandboxSpec`, `Resources`, `NetworkPolicy`, `ProviderKind` or the
protocol, all of which are already generic. Not a request to bundle,
release or support our plugin.

---

## 5. The plugin capability contract

### 5.1 Deployment topology

The plugin runs **beside the Fabro worker on the factory host** — today
`hp-xubuntu` — as a process the worker launches, and reaches the cluster
remotely over the Kubernetes API. It does **not** run in a pod, and it does
**not** sit behind a network service.

That follows from the protocol, not from preference. Protocol v2 is a local
contract: control travels over the plugin process's own stdin and stdout,
data over authenticated Unix-domain sockets in a private directory, and the
host validates the peer's credentials against the spawned plugin's PID
(`sandbox-driver-protocol/src/channel.rs:613–627`:
`TrustedPeer::Process(pid) => credentials.pid() == Some(pid)`). A plugin in
a pod has no such channel to the worker. Petri's ACP step additionally needs
a long-lived process with writable stdin and readable stdout, not a buffered
`exec` response (review note 008 §7).

Consequences this plan takes as binding:

- The kubeconfig and every provider credential stay inside the host and
  plugin trust boundary. They are never projected into an agent container.
- The plugin executable is pinned by SHA-256 on every execution host
  (`PETRI_SANDBOX_KUBERNETES_SHA256`); launching unpinned requires the
  explicit dev flag and is reported as unverified
  (`petri/plugin.rs:14–19`, `:113–116`; protocol.md:1039–1043).
- The plugin's own capture memory is bounded by **its** configuration, not
  by pod limits — pod limits cannot contain a host process (§5.4).

### 5.2 Capability declaration

The plugin declares its capabilities in its `initialize` response
(protocol.md:233–257). The protocol's honesty rule governs the table in
§5.3: "A declared capability must work; an undeclared operation must fail
with the `unsupported` error kind (§7). Capabilities optimize failure
timing; the error is still the enforcement" (protocol.md:311–314). So the
refusals below are declared **and** enforced, never one or the other.

Declared capability object, as the plugin returns it:

| Field | Value | Meaning |
|---|---|---|
| `isolation` | `"container"` | a pod container |
| `exec.live_streaming`, `exec.streams_separated`, `exec.stdin` | `true` | streamed stdio with separated stdout/stderr and writable stdin, which is what the ACP step requires |
| `fs.native`, `fs.upload`, `fs.download`, `fs.permissions` | `true` | served by tar-over-exec (§5.5) |
| `lifecycle.labels` | `true` | `sandbox/set_labels` |
| `lifecycle.update_network` | `true` | NetworkPolicy replacement |
| `lifecycle.pause`, `lifecycle.archive`, `lifecycle.fork`, `lifecycle.resize`, `lifecycle.undelete` | `false` | refused (§5.3) |
| `pty` | `null` | refused |
| `logs` | `null` | refused |
| `one_shot` | `null` | refused |
| `snapshots` | `null` | refused |
| `volumes` | `null` | the workspace volume is part of the pod the plugin builds, not a protocol-managed volume object (§6.3) |
| `access.preview_urls`, `access.ssh`, `access.web_terminal`, `access.vnc` | `false` | not a factory need |
| `access.vpn` | `false` | a compatibility tombstone, always false; Tailscale is guest software managed through exec (protocol.md:336–338) |

### 5.3 Operation table

The plan's capability scope is streamed stdio, exec, files, labels,
lifecycle and required network policy. Every operation protocol v2 defines
is listed; nothing is omitted, so a reader can see what is refused as well
as what is served.

**Refusal response.** Every refused operation returns the same shape — JSON-RPC
error code **`-32000`** (`CODE_APPLICATION`,
`sandbox-driver-protocol/src/wire.rs:114–119`) with
`data.report.kind = "unsupported"`, `data.report.retryable = false`, and
`data.detail.capability` naming the dotted capability path
(protocol.md:392–404). For example, for `pty/open`:

```json
{
  "code": -32000,
  "message": "capability pty is not supported by the kubernetes provider",
  "data": {
    "report": {
      "kind": "unsupported",
      "message": "the kubernetes provider serves no PTY; a factory run needs no terminal",
      "retryable": false,
      "causes": []
    },
    "detail": { "capability": "pty" }
  }
}
```

The two v1 tombstones are the one exception: they return
**`-32601`** (`CODE_METHOD_NOT_FOUND`) because the protocol defines them as
method-not-found rather than as unsupported capabilities.

| Operation | §protocol.md | Supported | `detail.capability` on refusal |
|---|---|---|---|
| `initialize` | §4 | **yes** | — |
| `shutdown` | §8.10 | **yes** | — |
| `provider/health` | §8.9 | **yes** | — |
| `transport/diagnostics` | §2.2 | **yes** | — |
| `sandbox/create` | §8.1 | **yes** | — |
| `sandbox/attach` | §8.1 | **yes** | — |
| `sandbox/list` | §8.1 | **yes** | — |
| `sandbox/describe` | §8.1 | **yes** | — |
| `sandbox/platform_info` | §8.1 | **yes** | — |
| `sandbox/start` | §8.3 | **yes** | — (§6.5) |
| `sandbox/stop` | §8.3 | **yes** | — (§6.5) |
| `sandbox/delete` | §8.3 | **yes** | — |
| `sandbox/recover` | §8.3 | **yes** | — (§6.6) |
| `sandbox/refresh_activity` | §8.3 | **yes** | — |
| `sandbox/set_timers` | §8.3 | **yes** | — |
| `sandbox/set_labels` | §8.3 | **yes** | — |
| `sandbox/update_network` | §8.3 | **yes** | — |
| `sandbox/environment` | §8.1 | **yes** | — |
| `exec/stream` | §9 | **yes** | — |
| `exec/stop` | §9 | **yes** | — |
| `exec/stdio_open` | §8.4 | **yes** | — |
| `exec/stdio_terminate` | §8.4 | **yes** | — |
| `exec/stdio_wait` | §8.4 | **yes** | — |
| `stream/cancel` | §8.4 | **yes** | — |
| `fs/read`, `fs/write`, `fs/delete`, `fs/exists`, `fs/metadata`, `fs/list_dir`, `fs/create_dir`, `fs/rename`, `fs/set_permissions` | §8.5 | **yes** | — |
| `git/clone` | §8.6 | **no** | `git.supported` — Fabro clones inside the sandbox; the plugin adds nothing |
| `sandbox/pause`, `sandbox/resume` | §8.3 | **no** | `lifecycle.pause` — a pod has no pause/resume; `stop`/`start` is the fence (§6.5) |
| `sandbox/archive` | §8.3 | **no** | `lifecycle.archive` |
| `sandbox/undelete` | §8.3 | **no** | `lifecycle.undelete` — a deleted pod is unrecoverable |
| `sandbox/resize` | §8.3 | **no** | `lifecycle.resize` — pod resources are fixed at admission |
| **`sandbox/fork`** (live-process fork) | §8.3 | **no** | `lifecycle.fork` — the protocol requires filesystem, memory, running processes **and process IDs** to be preserved across the fork (protocol.md:552–553); Kubernetes offers no primitive for this and no factory stage needs it |
| **`sandbox/snapshot`**, `snapshot/create`, `snapshot/get`, `snapshot/list`, `snapshot/delete`, `snapshot/activate`, `snapshot/deactivate`, `snapshot/build_logs` | §8.3, §8.7 | **no** | `snapshots` (`snapshots.from_image` / `snapshots.activation` for the narrower arms) — the sandbox image is pinned and built outside the factory; a per-run snapshot would be a second image-build path with no consumer |
| **`pty/open`**, `pty/resize`, `pty/close` | §8.4 | **no** | `pty` — every factory stage is non-interactive; `exec/stdio_*` carries the ACP channel |
| `logs/follow` | §8.4 | **no** | `logs` — `exec/stream` already carries streamed output; a second retained-log path would duplicate the capture budget in §5.4 |
| **`one_shot/run`** | §9.1 | **no** | `one_shot` — see the note below |
| `volume/create`, `volume/get`, `volume/list`, `volume/delete` | §8.7 | **no** | `volumes` — the workspace volume belongs to the pod spec the plugin builds (§6.3) |
| `access/preview_url`, `access/signed_preview_url`, `access/preview_release` | §8.8 | **no** | `access.preview_urls` |
| `access/ssh_create`, `access/ssh_revoke` | §8.8 | **no** | `access.ssh` |
| `access/web_terminal` | §8.8 | **no** | `access.web_terminal` |
| `access/vnc` | §8.8 | **no** | `access.vnc` |
| `sandbox/checkpoint`, `sandbox/restore_checkpoint` | §8.3 | **no** | v1 tombstones — return `-32601` method-not-found, not an `unsupported` report |

**On `one_shot/run` specifically.** Review note 008 §7 flags that one-shots
promise the sandbox's workspace *and network namespace*, and that an
arbitrary Kubernetes Job would provide neither. The protocol confirms it:
a one-shot "shares the sandbox's workspace at the sandbox's working
directory and the sandbox's network namespace" (protocol.md:920–924). Inside
a pod that is satisfiable — an ephemeral container in the *same pod* shares
both — but it is not satisfiable by a separate Job or pod, and no factory
stage requests it. Refused, with the reason recorded here so a later child
that wants it knows the only correct implementation is an ephemeral
container in the same pod, never a Job.

### 5.4 Host capture memory bounds, as named configuration values

The bounds are `TransportLimits` (fields at
`sandbox-driver-protocol/src/limits.rs:14–33`, defaults at `:35–57`).
Protocol.md §2.2 states the worst case: "With explicit capture, the
worst-case capture budget is twice `active_io * retained_output_bytes`;
applications must choose an affordable configuration"
(protocol.md:168–170).

**One correction to the figure this plan inherited.** Review note 008 §7
renders it as "two streams × 1,024 active I/O operations × 16 MiB retained
output". The arithmetic is right — 2 × 1024 × 16 MiB = **32 GiB** — but the
"two streams" reading is not: the factor of two is the stdout and stderr
capture pair per operation, not a count of transport channels. The formula
is `2 × active_io × retained_output_bytes`. The distinction matters because
it tells you which knob to turn: lowering `active_io` or
`retained_output_bytes` lowers the bound, and there is no "stream count" to
reduce.

32 GiB of worst case on a 30 GB factory host is not an envelope; it is the
whole machine. These are defaults to tune, so the factory sets them
explicitly:

| `TransportLimits` field | Upstream default | Factory value | Why |
|---|---|---|---|
| `active_io` | 1,024 | **64** | one sandbox per run, a handful of concurrent streams per stage; 64 leaves an order of magnitude of headroom |
| `retained_output_bytes` | 16 MiB | **4 MiB** | a stage's captured output; larger output belongs in an artifact, not in retained host memory |
| `buffered_value_bytes` | 16 MiB | **4 MiB** | matched to the above |
| `pending_opens` | 1,024 | **64** | matched to `active_io` |
| `provider_requests` | 2,048 | **256** | the plugin serves one worker |
| `reserved_requests` | 64 | **64** | unchanged — this is the protocol's reserved cancellation capacity and must not be squeezed |
| `queued_control_bytes` | 8 MiB | **8 MiB** | unchanged |
| `reserved_control_bytes` | 1 MiB | **1 MiB** | unchanged |
| `event_queue_bytes` | 1 MiB | **1 MiB** | unchanged |
| `event_queue_messages` | 256 | **256** | unchanged |
| `cached_handles` | 4,096 | **256** | matched to the run population |
| `output_progress_timeout` | 30s | **30s** | unchanged |
| `hard_cancel_drain_timeout` | 5s | **5s** | unchanged |
| `open_timeout` | 10s | **10s** | unchanged |
| `shutdown_timeout` | 5s | **5s** | unchanged |

Worst-case capture budget at the factory values:
`2 × 64 × 4 MiB = 512 MiB`, against 32 GiB at the defaults.

Every value above is admissible: `TransportLimits::validate`
(`limits.rs:59–100`) rejects only a zero or a value above
`Semaphore::MAX_PERMITS.min(u32::MAX)` for each count, and a zero or
over-one-day duration for each timeout. The plugin child calls `validate`
at startup so a mis-tuned configuration refuses at launch rather than
mid-run.

The lifecycle-proof child measures actual consumption against that ceiling;
the numbers above are a **bound, not a measurement**, and this note does not
claim otherwise.

### 5.5 Mechanics ported from `mhermann/fabro` PR 4

The fork's pod and exec mechanics are reused; its lifecycle assumptions are
not (review note 008 §8). Read at merge `7c14f9ae`, in
`lib/components/fabro-sandbox/src/kubernetes.rs` (3,046 lines; 5,081
insertions across 49 files):

| Mechanic | Fork's shape | This plan |
|---|---|---|
| Exec transport | Kubernetes `exec` subresource, `pods.exec(pod_name, argv, &params)` (`kubernetes.rs:622–625`) with `AttachParams { stdin, stdout: true, stderr: true, tty: false }` (`:615–620`) | **reuse** — it is the right API, and `tty: false` matches the `pty: null` refusal |
| Streamed output | stdout and stderr read asynchronously and demultiplexed (`:651–694`) | **reuse** — this is what `exec.streams_separated` declares |
| Long-lived stdin | kept open for the session's lifetime for ACP/MCP sessions (`:1495–1499`, `:2239–2241`) | **reuse** — this is the Petri ACP requirement |
| File transfer | tar-over-exec, `tar -c` remote / `tar -x` over stdin, hard-capped at 30s (`:859–937`, `:865`) | **reuse** for `fs/*`; the 30s cap becomes a named configuration value rather than a constant |
| Process cancellation | stop-file watcher with TERM→KILL escalation: a background shell polls for a stop file, reads the child PID, sends `kill -TERM "-$child"` then after a grace period `kill -KILL` (`:303–350`, quoted at `:322–328`); grace is 0.2s (`:74–75`) | **reuse the mechanism, move the policy** — protocol v2 gives escalation policy to the *host*, so the plugin exposes TERM-then-KILL with the host's timing rather than hardcoding 0.2s |
| NetworkPolicy | per-pod, `policyTypes: ["Egress"]`, podSelector on `sh.fabro.sandbox=<pod-name>`, `AllowAll` creates nothing, `Block` sets `egress: []`, `CidrAllowList` adds one rule per CIDR plus a DNS rule for UDP/TCP 53 (`:1727–1806`, `:1733–1774`, `:1794–1803`); carries an ownerReference to the pod for garbage collection (`:1781–1790`) | **reuse**, including the ownerReference — but see §6.6: an ownerReference is an API object and does not survive a control-plane rebuild |
| Pod manifest | `restartPolicy: Never`, command `["sleep", "infinity"]`, container `fabro`, workDir `/workspace` (`:1707–1712`) | **reuse the shape**; `restartPolicy: Never` is correct, since `start` re-creates rather than restarts (§6.5) |
| Resource requests and limits | optional CPU, memory and ephemeral-storage; when set, **requests equal limits** (`:1691`, `:1714–1717`) | **reuse** — this is the pod end of §2's hop 11, and requests-equal-limits is the right default (§6.2) |
| Node selector / affinity | **none** — the PodSpec carries no `nodeSelector` or `affinity` (`:1706–1722`) | **must be added** (§6.4) — a node-local workspace is meaningless without node affinity |
| Workspace volume | **none** — no `volumes`, no `volumeMounts`, no PVC, emptyDir or hostPath; `/workspace` is created with `mkdir -p` in the container's ephemeral filesystem (`:953–971`), and stop deletes the pod, losing it (`:2107–2135`) | **must be replaced** (§6.3) — this is the fork's central lifecycle assumption and the one this plan cannot inherit |
| ServiceAccount | not set; inherits the namespace default | **must be set** (§7.3) |

The last three rows are why this is a port and not a lift. The fork treats
Kubernetes sandboxes as non-persistent by design and recovers by re-cloning;
Petri selects `Retention::Always` and `LostSandbox::Refuse` and requires the
original workspace to survive a resume.

## 6. Logical sandbox identity, persistence, fencing, and label encoding

The organising fact for this whole section, and the reason the
2026-10-13 session ruling is satisfiable: **Petri's own run state does not
live in the cluster.** `RunIdentity` carries the run id down from the
coordinator so "the reconcile key can never disagree between a run and its
resume" (`petri/run.rs:34–40`), the lease ledger is written to the run
directory on the factory host with crash-safe staging
(`run.rs:105–116`), and the plugin runs on that same host (§5.1). A
control-plane rebuild destroys every API object and destroys **none** of
that.

So the question each subsection answers is not "how do we recover state
from the cluster" — it is "what must the plugin hold on the factory host and
on the worker's disk so that cluster objects become **re-derivable** rather
than lost".

### 6.1 Logical sandbox identity, independent of pod UID

Petri already supplies a deterministic identity and the plugin adopts it
rather than inventing one:

| Petri value | Shape | Source |
|---|---|---|
| run id | the coordinator's run key; a 26-character ULID in factory use | `run.rs:46–52`, `:72–74` |
| sandbox name | `petri-<run id>-l<lease>` | `run.rs:76–90` (`container_prefix` + `container_name`) |
| `petri.run` | the run id | `run.rs:20`, `:93–96` |
| `petri.lease` | `lease.raw()`, an integer | `run.rs:22`, `:96` |
| `petri.workspace` | `<run id>/<workspace id>` — "the reconcile key: recovery lists the provider by it and attaches the one match" | `run.rs:15–18`, `:82–85` |

**The logical sandbox identity is `petri-<run id>-l<lease>`** — Petri's own
sandbox name — carried as the **pod's `metadata.name`**. It is derived
entirely from values Petri holds on the factory host, contains no cluster-
assigned data, and is therefore reconstructible with the control plane
empty. The pod's `metadata.uid` is never an input to anything: not to
identity, not to the workspace path, not to reconcile, not to the host-side
record. A pod re-created after a control-plane rebuild has a different UID
and the *same* logical identity, which is exactly the required property.

A pod name must be a DNS subdomain (lowercase alphanumerics, `-`, `.`).
`petri-` plus a 26-character lowercased ULID plus `-l` plus a lease integer
is 35–40 characters of that alphabet, well inside the 253-character limit.
The run id is uppercase Crockford base32 in factory use, so the plugin
lowercases it for the pod name and keeps the verbatim value in the
`petri.run` label, whose charset permits uppercase (§6.7).

**Recovery after a control-plane rebuild.** Nothing to recover: the identity
is a pure function of `(run id, lease)`, both of which the factory host
still holds. The plugin recomputes it.

### 6.2 Pod requests and limits

Given §2's extension, `SandboxSpec.resources` arrives populated and the
plugin maps it to the pod's single `fabro` container:

| `Resources` field | Pod field | Mapping |
|---|---|---|
| `cpu_cores: Option<u32>` | `requests.cpu`, `limits.cpu` | `4` → `"4"` |
| `memory_mb: Option<u64>` | `requests.memory`, `limits.memory` | `8192` → `"8192Mi"` |
| `disk_mb: Option<u64>` | `requests.ephemeral-storage`, `limits.ephemeral-storage` | as the fork does (`kubernetes.rs:1714–1717`) |
| `gpus: Option<u32>` | — | refused if `Some` and non-zero: the factory declares no GPU and silently dropping a requested resource is the defect this whole section exists to prevent |

Requests equal limits, which places the pod in the Guaranteed QoS class and
is what makes `kubectl describe pod` show the workflow's declared numbers —
the Definition-of-Done assertion from note 001. A `None` field sets neither
request nor limit for that dimension, so the ResourceQuota in §7.3 is what
prevents an unconstrained pod from being admitted at all.

With this repository's workflow (`cpu = 4`, `memory = "8GB"`), the pod
carries `requests.cpu: "4"`, `limits.cpu: "4"`, `requests.memory: "8192Mi"`,
`limits.memory: "8192Mi"`.

**Recovery after a control-plane rebuild.** The resource values come from
the dispatch-time `SandboxSpec`, which the plugin records host-side (§6.6),
so a re-created pod carries identical requests and limits. Note what this
means for the ResourceQuota: it is a converge artifact, so it returns at
boot, but a re-created pod must be admitted against it afresh.

### 6.3 Workspace persistence

**Choice: a node-local directory at a deterministic path, mounted into the
pod, with the pod pinned to that node.**

The three options, and why the others lose:

| Option | Survives pod deletion? | Survives control-plane rebuild? | Verdict |
|---|---|---|---|
| Container filesystem (the fork's choice, `kubernetes.rs:953–971`) | no | no | **rejected** — incompatible with `Retention::Always`; this is the fork's lifecycle assumption this plan cannot inherit |
| Dynamically-provisioned PVC | yes | **no** — the PVC and PV are API objects, dropped with the datastore; the data may remain on disk but with no API handle naming it, so it is orphaned | **rejected as the identity carrier** |
| Node-local directory at a path derived from the logical identity, mounted via `hostPath` (or a statically re-created local PV naming the same path) | yes | **yes** — the path is a pure function of `(run id, lease)`, so the plugin re-derives it with the control plane empty | **chosen** |

The workspace path is
`<factory workspace root>/<run id>/<lease>`, where the root is a named
plugin configuration value. It is derived from the same two values as the
logical identity and from nothing else, which is the property that makes it
survivable: there is no API object to consult in order to find it again.

Two consequences stated plainly rather than buried:

- A node-local workspace is only reachable from the node holding it, so the
  pod must be pinned there (§6.4), and the plan's "the first node a factory
  pod lands on is whichever node the node plans make Ready first" (note 002)
  applies to the **first** pod of a run. Every later pod of that *same*
  sandbox is pinned to the node the first one chose.
- `hostPath` is a privileged-ish volume type. The requirement handed to the
  node plan in §7.3 therefore names the directory, its ownership and its
  exclusion from any boot-time reclamation — a workspace root on a tmpfs, or
  one the converge wipes, silently converts this design back into the
  rejected first row.

**Recovery after a control-plane rebuild.** The directory is on the worker
node's disk and the control plane's datastore is a separate tmpfs on
`poweredge`, so the data is untouched. The plugin re-derives the path and
re-creates the pod and its mount. This is the single load-bearing assumption
of §6, and it is an assumption about the **worker's** filesystem, which this
plan has **not** measured — it is handed to the node plan as a requirement
in §7.3 and must be proven by the lifecycle-proof child before cutover.

### 6.4 Node affinity and node-loss policy

The pod carries a `nodeAffinity` requiring the node that holds its
workspace, recorded in the host-side record at create (§6.6). The fork has
no node selector at all (`kubernetes.rs:1706–1722`), so this is new.

Node loss is reported honestly rather than guessed, which the protocol
requires of termination uncertainty (protocol.md §§11–12, and review note
008 §7's "output loss and termination uncertainty must be reported
honestly"):

| Observed state | Plugin's answer |
|---|---|
| Node `Ready`, pod present | sandbox running |
| Node `Ready`, pod absent | sandbox lost *if* the workspace directory is absent; **re-creatable** if it is present (§6.6) |
| Node `NotReady`, pod present or absent | **neither running nor lost** — the workspace is unreachable but not known gone; the plugin reports an unavailable provider-side state and `exec` fails with a retryable error, never with `unsupported` and never by silently creating a replacement |
| Node removed from the cluster, or reimaged | sandbox lost — the workspace went with the disk |

The `NotReady` row is the one that matters operationally here: note 002
records `gmktec-xubuntu` sitting `NotReady` with a
`node.kubernetes.io/unreachable:NoExecute` taint for ten days. A policy that
collapsed `NotReady` into "lost" would, for ten days, have reported every
sandbox on that node as destroyed and — under `LostSandbox::Replace` — have
created empty replacements for workspaces that were sitting intact on
gmktec's disk. Distinguishing "unreachable" from "gone" is the whole point.

### 6.5 `LostSandbox`, and Petri's stop/start fencing mapped onto pods

Petri fences recovery with stop-then-start. `lease.rs:646–663`:
`pending(lease, PendingIntent::Stop)` → `sandbox.stop()` →
`sandbox.start()` → `live(lease, id)`, logging "fencing a recorded
sandbox". `fabro-petri` selects `LostSandbox::Refuse`
(`engine.rs:240`) and `Retention::Always` (`engine.rs:229`, from
`pub const RETENTION: Retention = Retention::Always` at `engine.rs:373`).

A pod is not a restartable container, so the mapping is:

| Petri operation | Pod operation | Guarantee |
|---|---|---|
| `stop` | **delete** the Pod object, preserving the workspace directory and the host-side record; block until the pod is observed **fully absent** from the API, not merely `Terminating`, within a bounded grace period | every process in the sandbox is dead — strictly stronger than a Docker stop. Blocking until absence is what makes the fence a fence: returning while the pod is still terminating would let `start` create a second pod mounting the same workspace directory, and two writers on one workspace is the corruption the fence exists to prevent |
| `start` | **re-create** the Pod from the host-side record: same `metadata.name`, same labels and annotations, same node affinity, same workspace mount, same requests and limits; **refuse** if any pod of that name still exists | the sandbox resumes on its original workspace. Refusing on a surviving pod is the other half of the single-writer guarantee |
| `delete` | delete the Pod **and** the workspace directory **and** the host-side record | the only operation that destroys the workspace, so it is the only one `Retention::Always` withholds until prune |

`LostSandbox` stays **`Refuse`**, unchanged from `engine.rs:239`, and the
reason is worth stating because it is the opposite of what a
"make recovery survive a rebuild" instinct suggests. `Refuse`'s contract is
that Petri "does not replace it silently" (`backend.rs:54–63`); `Replace`
hands the host an **empty** workspace and expects the host to restore it
before any attempt runs. The factory has no such restore hook, so `Replace`
would silently start a resumed run on an empty workspace — losing the
implementation work the resume exists to continue. The correct fix for a
control-plane rebuild is therefore **not** to loosen `LostSandbox`; it is to
make the sandbox genuinely *not lost* (§6.6), so `Refuse` is never reached.

### 6.6 Recovery after a control-plane rebuild: the host-side record

A control-plane reboot drops every API object — pods, leases, PVCs,
secrets — and only converge artifacts come back (note 002). The ownerReference
the fork relies on for NetworkPolicy garbage collection
(`kubernetes.rs:1781–1790`) is itself an API relationship and goes with
them.

The plugin therefore keeps a **host-side durable record**, on the factory
host beside the Fabro worker, in its own state directory, keyed by logical
sandbox identity (§6.1). It holds exactly what is needed to rebuild the
cluster objects and nothing that could be re-derived:

| Field | Why |
|---|---|
| logical sandbox identity | the key |
| node name | where the workspace directory lives (§6.3); the one value that is **not** derivable from `(run id, lease)`, because it was the scheduler's choice |
| workspace directory path | derivable, recorded for auditability |
| the `SandboxSpec` as received — resources, labels, env keys (not values), network policy | so a re-created pod is identical to the original (§6.2) |
| the pod spec digest | to detect a re-creation that would differ |

The record is written before the pod is created, in the same crash-safe
staged-rename style Petri already uses for its own recovery metadata
(`petri/run.rs:105–116`: "a reader sees a complete record, and both its
content and directory entry survive a crash after this returns").

Recovery, on a `sandbox/attach`, `sandbox/recover` or `sandbox/list`
reconcile after the control plane returns:

1. Read the host-side record for the logical identity. Absent → the
   sandbox never existed, or was deleted; report absent.
2. Look for the pod by `metadata.name`. Present → attach; done.
3. Absent, and the recorded node is `NotReady` → report unavailable, not
   lost (§6.4).
4. Absent, recorded node `Ready`, workspace directory **present** →
   **re-create** the pod, its NetworkPolicy and its ownerReference from the
   record. The sandbox is not lost, so `LostSandbox::Refuse` is never
   reached and the resume proceeds on the original workspace.
5. Absent, recorded node `Ready`, workspace directory **absent** →
   genuinely lost; `Refuse` is correct and the run fails honestly.

So the session ruling is satisfiable **without** a persistent control-plane
datastore, and the evidence is the four facts in §6's preamble: the run id
descends from the coordinator, the lease ledger is on the factory host, the
workspace is on the worker's disk, and the plugin runs on the factory host.
Every cluster object this design needs is re-derivable from state the
rebuild does not touch.

The one requirement that does go **back** to livespec plan
`factory-worker-nodes-gitops` as a finding, rather than being assumed here,
is in §7.3: the worker's workspace root must be on a persistent filesystem
that the boot-time converge does not reclaim. That is a property of a host
this plan does not own and has not measured. If the node plan cannot provide
it, this design's step 4 degrades to step 5 — every resume across a
control-plane rebuild fails honestly rather than silently — and the plan
would then need a persistent datastore or an off-node workspace store, which
is the finding to raise, not a silent assumption to make.

### 6.7 Lossless label encoding

Petri's three labels, against the Kubernetes rules. A label **key** has an
optional DNS-subdomain prefix and a required name segment of at most 63
characters beginning and ending alphanumeric with `-`, `_`, `.` between. A
label **value** must be at most 63 characters, may be empty, and otherwise
must begin and end alphanumeric with only `-`, `_`, `.` and alphanumerics
between — so **a forward slash is not permitted in a value**.

All three keys — `petri.run`, `petri.lease`, `petri.workspace` — are valid
name segments unchanged: each begins and ends alphanumeric with interior
dots. The keys pass through verbatim.

| Label | Value shape | Valid as-is? | Encoding |
|---|---|---|---|
| `petri.run` | a 26-character Crockford base32 ULID | **yes** — alphanumeric throughout | verbatim |
| `petri.lease` | `lease.raw()`, an integer | **yes** | verbatim, decimal |
| `petri.workspace` | `<run id>/<workspace id>` (`run.rs:82–85`) | **no** — contains `/` | encoded, below |

`petri.workspace` is the reconcile key — "recovery lists the provider by it
and attaches the one match" (`run.rs:15–18`) — so its encoding must be
**injective**, or exact-match selection could attach the wrong sandbox. It
must also be **lossless**, so the original value can be read back. Two
carriers, because one cannot do both jobs:

- **The label** `petri.workspace` carries an injective, charset-safe
  encoding: every byte outside `[a-zA-Z0-9.-]` becomes `_` followed by two
  lowercase hex digits, and a literal `_` becomes `__`. This is reversible
  by construction and injective, whatever a workspace id contains. For the
  real shape it costs two characters: `<run id>/implement` becomes
  `<run id>_2fimplement`.
- **The annotation** `petri.workspace` carries the **verbatim** value.
  Annotations have no charset restriction and a far larger size budget, so
  losslessness is guaranteed there unconditionally, independent of any
  encoding argument, and an operator reading `kubectl describe pod` sees the
  real value.

Length is bounded and the bound is enforced rather than hidden: 26 (run id)
+ 3 (`_2f`) + the workspace id must not exceed 63, so a workspace id longer
than 34 characters overflows. The plugin **refuses the create**, naming the
value and the limit. It never truncates: a truncated reconcile key is one
that can match the wrong sandbox, which is strictly worse than a refusal,
and it would fail silently where a refusal cannot.

The plugin additionally carries `app.kubernetes.io/managed-by` and a
factory-owned `livespec.dispatch.factory` label, per note 001 finding 6 —
factory identity stays `livespec.dispatch.factory`, with cluster, node,
namespace, pod and lease as separate dimensions, never conflated into it.

**Recovery after a control-plane rebuild.** The labels and annotations are
rebuilt from the host-side record (§6.6) along with the pod, so the encoding
is re-applied deterministically and the reconcile key is unchanged.

## 7. The credential contract

### 7.1 Which process receives what, by which existing channel

Four credentials, four different channels, three different trust boundaries.
The column that matters is the last one: nothing in this design puts a new
credential inside the agent container, and nothing puts the cluster
credential anywhere but the host.

| Credential | Receiving process | Existing channel | Trust boundary |
|---|---|---|---|
| **kubeconfig** (namespace-scoped) | the **plugin**, on the factory host | read from `$HOME/.kube/config`, the client-go default path. `HOME` is one of the three variables every plugin kind inherits (`petri/plugin.rs:77`), so this needs **no** new forwarded variable and **no** change to `forwarded_env`'s per-kind allowlist (§2.2) | host/plugin only. **Never** projected into a pod, never mounted into the agent container, and no cluster-admin credential anywhere near either |
| **`CLAUDE_CODE_OAUTH_TOKEN`** | the ACP agent **inside the sandbox** | unchanged from today: the Dispatcher's uncommitted mode-600 run-config overlay appends the `[environments.livespec-ci.env]` table at dispatch time (this repo's `workflow.toml:411–417` records why the committed file must not declare it; `_dispatcher_credentials.py::materialize_overlay`). Petri resolves named secret references into the launched agent's environment and adds no product credential of its own (`petri/crates/attractor/steps/src/acp/command.rs:99–120`) | sandbox. Becomes the pod container's env; the plugin passes `SandboxSpec.env` through and does not read it |
| **GitHub App token** | git and `gh` **inside the sandbox** | unchanged: `GITHUB_APP_ID` and `GITHUB_PRIVATE_KEY` reach the Dispatcher through the host credential wrapper, which mints a fresh short-lived `GITHUB_TOKEN` into the same overlay per dispatch (`_dispatcher_credential_env.py:49–51`) | sandbox. Registry pulls are a **separate** credential consumed by the node's containerd (§7.3) and are not this token |
| **beads tenant password** | `bd` **inside the sandbox** | unchanged: bare `BEADS_DOLT_PASSWORD`, injected by `with-livespec-env.sh` on the host and projected through the same overlay (`_dispatcher_credential_env.py:51`). The pod reaches the Dolt tenant over the tailnet, not over `127.0.0.1` | sandbox |

The `127.0.0.1` caveat from review note 008 §10 is load-bearing here and is
recorded as a plugin-child requirement: every loopback reference in the
sandbox's configuration must be re-read as "the pod's own network
namespace", which is **not** the factory host. Any factory service the
sandbox reaches on loopback today becomes a tailnet or cluster-DNS address
in a pod, and the lifecycle-proof child must exercise each one.

### 7.2 How the plugin re-reads a rotating kubeconfig without a restart

The kubeconfig rotates at **every control-plane boot**: the datastore is a
tmpfs, so the factory ServiceAccount and its token Secret are dropped and
re-created by the converge, and the new token does not match the old
kubeconfig. The node plan delivers a kubeconfig on `hp-xubuntu` that
refreshes itself; this plan designs the plugin that must survive the
refresh.

The plugin is a long-lived process launched by the Fabro worker, so it
cannot treat its credential as launch-time state. Three rules:

1. **Load from a path, never from an environment variable.** An env-var
   credential is frozen at `exec` time and a rotation is invisible to it
   forever. `$HOME/.kube/config` is a path, and §2.2's scrubbed environment
   makes this the natural route rather than a workaround: `HOME` is
   forwarded, `KUBECONFIG` is not.
2. **Rebuild the client on an authentication failure.** On any `401
   Unauthorized` from the API, re-read the file from disk, rebuild the
   client, and retry the request once. This is the mechanism that carries a
   control-plane reboot: the first call after the reboot fails `401`, the
   re-read picks up the converged token, and the retry succeeds — with no
   restart and no dropped sandbox. A second consecutive `401` after a
   genuine re-read is reported as a provider-health failure, not retried in
   a loop.
3. **Watch the file as well, so rotation is cheap rather than only
   correct.** A filesystem watch on the kubeconfig path, debounced, reloads
   proactively. The watch is an optimisation; rule 2 is the guarantee. A
   watch alone is insufficient — an atomic-rename rotation can be missed by a
   watch on the inode, and a watch cannot detect a token that was revoked
   without the file changing.

`provider/health` reports credential state so the worker can distinguish
"the cluster is unreachable" from "my credential is stale", which are
different operator actions. Note what this design deliberately does **not**
do: it does not restart the plugin to pick up a credential, because a
restart would tear down every data channel and the PID the host validates
peers against (§5.1), turning a routine rotation into a loss of every live
sandbox.

### 7.3 Requirement list handed to livespec plan `factory-worker-nodes-gitops`

This plan provisions nothing. The list below is what plan
`factory-worker-nodes-gitops` (epic `livespec-sqvj7p`, in the `livespec`
repository) must deliver as converge artifacts for this plan's plugin and
lifecycle-proof children to proceed. Each item names why the plugin needs
it, so the owning plan can judge the requirement rather than merely
implement it.

**The factory namespace.** A dedicated namespace — `livespec-factory` is
this plan's suggested name, the owning plan's to settle — existing as a
converge artifact so it returns at every control-plane boot.

**ServiceAccount and RBAC.** One ServiceAccount in that namespace, with a
Role (not ClusterRole) granting, namespace-scoped:

| Resource | Verbs | Why |
|---|---|---|
| `pods` | `create`, `get`, `list`, `watch`, `delete` | sandbox lifecycle (§6.5) |
| `pods/exec` | `create` | the exec transport (§5.5) |
| `pods/log` | `get` | diagnostics |
| `networkpolicies` | `create`, `get`, `list`, `delete` | per-pod egress policy (§5.5) |
| `events` | `list`, `watch` | distinguishing "pending on quota" from "pending on scheduling" |
| `nodes` | `get`, `list` (cluster-scoped read only) | the `Ready`/`NotReady` discrimination in §6.4 |

No `secrets` access: the plugin holds no sandbox credential (§7.1). No
cluster-admin, no cross-namespace write.

**A namespace-scoped kubeconfig on `hp-xubuntu`.** At
`$HOME/.kube/config` for the user the Fabro worker runs as, naming that
ServiceAccount, re-converged after every control-plane boot. §7.2 is the
plugin's half of this contract; a kubeconfig that does **not** refresh
itself leaves the plugin permanently `401` after a reboot, which rule 2
reports but cannot repair.

**ResourceQuota.** On the namespace, bounding total `requests.cpu`,
`requests.memory`, `limits.cpu`, `limits.memory` and pod count. Two reasons
it is required rather than advisory: it is the backstop that refuses a pod
whose `Resources` fields were `None` (§6.2), and it is where the hp
coexistence budget from note 001 finding 4 is actually expressed — at 8 GB
requests a 30 GB host schedules roughly three such pods, not fifteen, and
the Docker slice keeps running until this plan's cutover, so the quota must
leave room for it.

**NetworkPolicy baseline.** A default-deny-egress policy for the namespace,
which the plugin's per-pod policies then open (§5.5). The baseline must
permit, for a factory pod: cluster DNS; the tailnet route to the beads Dolt
tenant on `127.0.0.1:3307` **as seen from the factory host, not the pod**
(§7.1); the GitHub API and `github.com`; the telemetry receiver; and the
container registry. Note 001 finding 5's split applies — the policy is this
plan's design, the network reach is the node plan's to provide.

**Registry reach.** The sandbox image
(`ghcr.io/thewoolleyman/livespec-fabro-sandbox:…`, per this repo's
`.livespec.jsonc` and `workflow.toml:405`) must be pullable on **every**
node that can run a factory pod. The pull credential is consumed by the
node's containerd and is **not** the pod's GitHub App token (review note
008 §10); it is an imagePullSecret or a node-level containerd registry
configuration, and it is the node plan's to provide on each node.

**The worker workspace root.** The one requirement §6.3 and §6.6 cannot
work around, and the one this plan has **not** measured: a directory on each
factory-capable worker node, on a **persistent, non-tmpfs** filesystem,
owned by the sandbox container's user, **excluded from any boot-time
converge reclamation**, with enough capacity for the concurrent workspace
population the ResourceQuota permits. If the owning plan cannot guarantee
persistence and exclusion from reclamation, that is a finding to raise back
to this plan — not something to assume — because without it every resume
across a control-plane rebuild degrades to an honest failure (§6.6 step 5)
and this plan would need either a persistent control-plane datastore or an
off-node workspace store.

**Node labelling.** A label marking factory-capable nodes, so the plugin's
first-pod scheduling can select them without naming hosts. The plugin must
not assume `hp` (note 002: "the plugin schedules by node selector and must
not assume hp").

**What this plan does not ask for.** A persistent control-plane datastore.
The 2026-10-13 session ruling withheld it and §6 shows the design does not
need it: every cluster object is re-derivable from the factory host's record
and the worker's disk.

## 8. What the later children owe

Carried forward so the sequencing in note 002 stays answerable:

- **Plugin child (note 002 step 2).** Implements §5 and §6; ports the
  mechanics in §5.5 and replaces the three rows marked "must". Proves
  §6.7's encoding round-trips and §5.3's refusals against the
  sandbox-driver conformance suite on a kind or k3d cluster in CI. Pins
  itself by checksum on every execution host.
- **Fabro wiring child (note 002 step 3).** Lands §2.3's four changes,
  upstream if §4's issue is accepted. Depends on `bd-ib-sxcnj7`.
- **Lifecycle-proof child (note 002 step 4).** Proves the control-plane-rebuild
  recovery path of §6.6 end to end — including, specifically, the one
  unmeasured assumption that the worker workspace root survives a reboot —
  plus the `NotReady` discrimination of §6.4, the single-writer fence of
  §6.5, pod requests and limits matching the workflow declaration (§6.2),
  the `401`-then-reload rotation of §7.2, and the capture-memory envelope
  of §5.4 against actual consumption.
- **Version floor child (note 002 step 6).** Pins by `Cargo.lock` Petri
  revision, not by Fabro tag alone (§1).
