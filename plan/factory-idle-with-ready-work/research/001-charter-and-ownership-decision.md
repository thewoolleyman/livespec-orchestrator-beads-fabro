## The maintainer's statement of what done means

ensure they get through the factory and get done correctly.

## Definition of Done assertions derived from that statement

- When a factory host has free slots, the credential probe reports usable and dispatch-ready work exists in a fleet tenant, a dispatch starts within the configured bound without any interactive session starting an engine.
- An idle-with-ready-work condition that persists past that bound is surfaced on needs-attention.

# Charter: the factory idles with ready work when no session runs an engine

## The incident

On 2026-10-13 the hp fleet Fabro server (cap 10) started no ImplementWorkItem
run between about 18:27Z and 22:56Z. For about 4.5 hours there were 0 runs in
flight, the Claude credential probe reported `usable` (HTTP 200), and
dispatch-ready work existed. No dispatcher or drain engine process was running
on the dev host. Dispatch resumed only when a session started an engine again.
The evidence is recorded on plan `gitops-fleet-capacity-monitoring`
(livespec-dev-tooling, epic `livespec-dev-tooling-dfixhe`). Work-item
`bd-ib-hlfw5p` records the same measurement.

The cause is structural rather than a fault. Every dispatch on this host comes
from a process that some interactive session started: a hand-picked
`drive --action impl:<id>`, a `dispatcher.py loop` launched by a plan session,
or a `drain-backlog` engine. Each of those is a bounded CLI invocation that
exits. Nothing on the host starts a dispatch on a clock.

## Where the implementation belongs: this repository (decided 2026-10-14)

The question the adopting directive asked was whether `bd-ib-hlfw5p` belongs
here (the Dispatcher drain) or in livespec-overseer. It belongs here, for four
measured reasons:

1. **The drain is this repository's surface.** `dispatcher.py loop` is "the
   factory's drain entry point" and the unattended drain "is the factory's
   steady-state path" (`SPECIFICATION/contracts.md` §"Dispatcher loop
   invocation surface", lines 3636-3663). Run without `--item`, it drains the
   ranked queue `next` reports, honours `wip_cap`, and applies the fail-closed
   unattended cost gate (lines 3665-3686; Scenarios 43 and 45).
2. **The clock-fired precedent is already here.** `reconcile-runs.timer`
   (`orchestrator-image/services/reconcile-runs/`) is a committed systemd
   oneshot+timer whose own header says it "covers the interval NOTHING
   dispatches". A work-supply timer is its sibling. It is not a daemon, so it
   respects `constraints.md` "Each skill invocation is a single Python process;
   no daemons" and `spec.md` "this plugin MUST NOT introduce another daemon".
3. **livespec-overseer has no dispatch mandate.** Its `SPECIFICATION/spec.md`
   limits it to session supervision, caam and the LLM provider manager.
   `overseerd` never invokes `dispatcher.py`. Its archived plan
   `deprecate-unused-seats-simplify-to-overseerd-and-caam` retired the foreman
   seat (its nearest thing to work supply) and sent re-dispatch behaviour to
   "dispatcher policy". Its `drain-backlog` skill is session-driven by design
   ("The session IS the loop") and always passes `--item`. That flag marks a
   human as present, so reusing it unattended would weaken the cost gate.
4. **The orchestrator must not read overseer surfaces** (`contracts.md`
   §"Orchestrator-owned attention facts", ownership boundary, lines
   1073-1078). The idle surfacing therefore cannot depend on the overseer.

So `bd-ib-hlfw5p` stays in this tenant and is implemented here. Nothing is
re-targeted to livespec-overseer and no overseer session needs to act.

## Mechanism

The mechanism is a committed systemd timer template under
`orchestrator-image/services/`, a sibling of `reconcile-runs`. One instance is
installed per fleet tenant. It fires `dispatcher.py loop --repo <tenant>
--budget <n>` with no `--item`, through the tenant's env wrapper, on a
configured interval. That interval is the "configured bound" of plan
assertion 1.

Three properties make it correct rather than merely present:

- **No overlap with itself.** A oneshot service is never started while it is
  still active, so a long wave is not joined by a second timer pass.
- **No stale build.** `reconcile-runs.service` bakes `@PLUGIN_ROOT@` in at
  install time, so a plugin release does not reach the unit until it is
  reinstalled. That is the stale-build trap AGENTS.md catalogues, moved from
  a session to a timer. The work-supply unit must resolve the registered
  plugin install when it fires.
- **No new idle fact needed.** The idle-with-work surface already exists.

## Plan assertion 2 is already mostly shipped

Plan `idle-factory-visibility` (epic `bd-ib-zlpeyg`, archived 2026-09-08)
ratified and implemented `hygiene:idle-factory:<repo>`. The spec clause is
`contracts.md` line 1019, in §"The skill surface". The scenario is Scenario 120
("An idle factory with dispatchable work surfaces its first dispatch"), and the
implementation is `commands/_needs_attention_idle_factory.py` (bd-ib-lphazz).

The fact fires at high urgency the moment all three conditions hold: there is
an admission-eligible ready item, the repository has zero counted claims, and
fallback candidates are available. That is a stronger trigger than "persists
past the bound". Assertion 2 is therefore carried by plan-level proof: a host
capture showing the row during an observed idle window. It needs no new child.

Open sibling work that changes that composer:

- `bd-ib-ynz3n7` (pending-approval, plan
  `factory-configurable-model-fallback-priority`) moves condition (c) onto the
  shared admission verdict.

It stays with its own plan. The completeness review should confirm it has not
broken the row before the plan proof is taken.

## Risks this plan accepts knowingly

An always-on drain adds an engine that runs alongside whatever engines
sessions start. Two open P1 defects are about exactly that concurrency:

- `bd-ib-2vda`: `wip_cap` is enforced per admission pass with no cross-engine
  exclusion, so N engines admitting in the same instant oversubscribe the cap.
- `bd-ib-m1av`: reconcile-runs in a sibling engine's preflight cancels a
  freshly launched re-dispatch as `superseded-run` during the roughly 40s
  window before `dispatch-run-stamp`.

Neither is caused by this plan, but a timer pass makes each more likely. They
are not adopted as children. Each is a standalone defect with its own fix
shape, and `.ai/ledger-writers-are-multi-host.md` forbids the cheap host-local
fence that would hide 2vda here. They are recorded as explicit deferrals in the
scoping event and are re-checked at the completeness review.

## Carriers

1. Assertion 1 (an unattended dispatch starts within the bound): carried by
   `bd-ib-hlfw5p` (the work-supply timer), then discharged by plan-level proof
   on the host after a release and install.
2. Assertion 2 (an idle-with-work condition is surfaced): plan-level proof
   against the shipped `hygiene:idle-factory` row.
