# 003 — Hostname-free factory entries: a gitops-rendered factory registry

Date: 2026-10-15. Author: session `petri-factory-on-gmktec`. Plan assertion
ordinal 4 ("No playbook, role or committed factory entry names a machine
hostname; a factory is bound to a machine only in the gitops inventory's host
groups and host variables"). This note covers the committed-factory-entry half;
the playbook and role half is carried by `livespec-dev-tooling-prdxxe`.

## Measured scope

Fifteen fleet repositories commit a `dispatcher.factories` table in
`.livespec.jsonc` whose `server` values name a machine:

| repositories | entries |
| --- | --- |
| dolt-server, livespec-console-beads-fabro, livespec-dev-tooling, livespec-driver-claude, livespec-driver-codex, livespec-driver-pi, livespec, livespec-orchestrator-git-jsonl, livespec-overseer, livespec-runtime | `hp` = `https://hp-xubuntu.perch-rudd.ts.net:32276`, `vps` = `https://vps.perch-rudd.ts.net:32276` |
| homelab | `hp` and `vps` on port 32277 (the mi-homelab org instances) |
| livespec-orchestrator-beads-fabro, livespec-tdd-proof | `hp` only |
| openbrain, resume | `default` = vps:32276, `hp` = hp-xubuntu:32276 |

The factory NAMES are machine names too (`hp`, `vps`). fabro-currency's
uncommitted canary posture adds `hp-candidate` = hp-xubuntu:32278.

## What the dispatcher does with an entry today

`_config.resolve_fabro_factory` picks a name (explicit flag, then
`LIVESPEC_FABRO_FACTORY`, then `dispatcher.default_factory`) and builds a
`FactoryTarget` from that entry's `server`, `bin` and `environment`. A dev token
comes from `LIVESPEC_FABRO_DEV_TOKEN_<name>` (none is set in the fleet wrapper
today, measured by name only). An entry with NO `server` resolves to
`server=None`, which means "the ambient local Fabro CLI target". So simply
deleting `server` values would silently re-route every dispatch to the local
server: the new mechanism must refuse an unresolved factory, never fall back.

## Why not a Tailscale Service

A Tailscale Service gives a machine-free tailnet name, but only a TAGGED device
can host one. `tailscale-admin`'s ruling of 2026-08-17 forbids any agent adding
a tag, and a tagged gmktec-xubuntu would leave `autogroup:member` and lose the
member SSH grant, which is its only remote access. Ruled out.

## Why not DNS aliases or /etc/hosts

Every factory URL is HTTPS through `tailscale serve`, whose certificate names
the machine. Any alias name fails TLS verification unless the factory serves
plain HTTP, which would change every client's trust model. Ruled out.

## Proposal: the inventory renders a factory registry on each dispatching host

1. **Gitops (livespec-dev-tooling).** Each Fabro instance mapping in host_vars
   gains a logical `factory_name` (for example `fabro-current` for the Petri
   engine and `fabro-legacy` for the 0.254 engine). A role on every host that
   dispatches (the `dev_hosts` group today) renders
   `/etc/livespec/fabro-factories.json` from the inventory:
   `{factory_name: {"server": "https://" + canonical_host}}` for every instance
   of every host in the factory group, read through `hostvars`. Moving a
   factory to another machine is then a host_vars change and a converge;
   nothing committed outside the inventory names a machine. When Fabro moves
   onto Kubernetes, the registry entry points at the cluster's address and no
   repository changes.
2. **Dispatcher (this repository, spec-governed).** A factory entry may carry
   `"registry": true` (or omit `server`, if the spec prefers) and is then
   resolved by name from the registry file; `LIVESPEC_FABRO_FACTORY_REGISTRY`
   names an alternative path for tests. An entry that names a factory absent
   from the registry, or a registry that cannot be read, is REFUSED before the
   item is claimed, naming the factory and the path. A `server` key remains
   valid for repositories outside the fleet, so the change is additive.
   Recorded `dispatch_factory` metadata keeps carrying the resolved server URL
   for provenance, as it does today.
3. **Fleet sweep.** Each of the fifteen repositories changes its table to
   logical names with no `server`, once the registry is rendered on every
   dispatching host and each repository's resolved plugin build reads it.
   `livespec-orchestrator-git-jsonl` has its own dispatcher and needs its own
   change. The legacy factory's rename is coordinated with `fabro-currency`,
   because items carry recorded factory names and its canaries dispatch by
   name; a renamed factory leaves a recorded old name unusable, which today
   falls back to the default.

## Decisions settled with fabro-currency (2026-10-15)

- **Factory names name the INSTANCE, not its role.** Each factory is named
  for the Fabro instance, stable for that instance's whole life, and the role
  ("which engine serves the fleet") is carried only by
  `dispatcher.default_factory`. A cutover is then one `default_factory` flip
  with no rename and no orphaned item record. Role words such as "current" or
  "fleet" would have to move at every engine migration, and the next one
  (Kubernetes) is already planned. Names: `legacy` for the 0.254 instance
  (its role never changes again; it only retires) and `petri` for the current
  Fabro server. The Kubernetes move adds a new name and retires `petri`.
- **Recorded pins are re-routed, not refused.** Measured by fabro-currency on
  this tenant: 425 items carry a recorded `dispatch_factory` of `hp` (54 of
  them open). `_dispatcher_factory_ledger._usable_recorded_factory` ignores a
  recorded name the table no longer declares and falls back to
  `default_factory`, so renaming `hp` silently re-routes those items'
  re-dispatches to the default. That is acceptable, and desirable after the
  cutover, and the proposal says so. The registry's "absent name refuses" rule
  applies only to registry resolution of a DECLARED entry; it is distinct from
  this recorded-pin fallback and must not change it.
- **Recorded URLs keep resolving.** 252 of those records embed
  `https://hp-xubuntu.perch-rudd.ts.net:32276`; that address keeps answering
  until the legacy server is stopped after the cutover soak. And
  `https://hp-xubuntu.perch-rudd.ts.net:32278` stays resolvable until
  fabro-currency's recorded proofs and preserve-by-reference comments that cite
  it (they carry literal `fabro dump --server` retrieval commands) are
  replayed or retired. Plan child `livespec-dev-tooling-hkf457` stops that
  instance's service but must keep its tailscale serve mapping and storage, so
  a stopped server's URL still answers once restarted for a retrieval.
- **Who writes which entry.** fabro-currency's cutover item `bd-ib-sxcnj7`
  already owns adding the committed factory entry for the current Fabro
  server; it writes that entry in the registry form once this plan's spec
  proposal ratifies. This plan owns the proposal, the dispatcher change, the
  registry role and the sweep of the other repositories.
- **The canary posture is host-side.** fabro-currency's `hp-candidate` entry
  is uncommitted, in worktree `canary-hp-candidate`. This plan messages
  fabro-currency when the registry file lands; fabro-currency switches its own
  posture, never while a canary drive is reading that worktree.

## Remaining decisions for the spec proposal

- The marker: an explicit `"registry": true` versus "no `server` means
  registry". The explicit form cannot be confused with the implicit `default`
  target; it is the recommendation.
- The registry path, its owner and mode (root-owned, world-readable; it holds
  no secret).
