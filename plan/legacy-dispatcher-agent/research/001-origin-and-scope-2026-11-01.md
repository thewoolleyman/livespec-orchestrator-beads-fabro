## The maintainer's statement of what done means

Each has ONE Definition-of-Done assertion: retire when dispatch-control-plane's re-architecture is complete enough to replace it. Each EXPLICITLY takes on no other responsibilities and has no direct responsibilities. Everything must be owned by another plan that is not about coordinating or dispatching. legacy-dispatcher-agent: Lives in livespec-orchestrator-beads-fabro and takes over petri's tab (w6:pH). Runs the existing tmp/petri-canary launchers break-fix only: no new features, no new scripts, nothing committed. Exit: dispatch-control-plane's scheduler admits gmktec work and the tmp/ launchers are retired. dispatch-control-plane must NOT absorb today's operations, so that its context stays on its re-architecture mandate.

## Definition of Done assertions derived from that statement

- dispatch-control-plane's scheduler admits work to the gmktec factory, and no tmp/ launcher process (tmp/petri-canary/dispatch-dual-r681b.sh or the tmp/petri-refill feeder, refill and screen-ticket scripts) runs on the dispatching host.

# legacy-dispatcher-agent: plan origin

Source: the maintainer-approved LEGACY CUTOVER design, recorded as a coordinator handoff on livespec-dev-tooling-dfixhe at 2026-11-01 ~19:2xZ (MAINTAINER DECISIONS (2) and (4), CUTOVER STEP 3). The Definition-of-Done statement above is quoted verbatim from that handoff. This unattended petri seat (session 1afc2bea) derived the single assertion from the stated exit; the first handoff entry records that derivation.

## Scope

- No direct responsibilities. Every piece of work is owned by another plan that is not about coordinating or dispatching.
- The seat runs the existing tmp/petri-canary and tmp/petri-refill launchers break-fix only: no new features, no new scripts, nothing committed.
- It carries the queue obligations it inherits from petri-factory-on-gmktec (bd-ib-fyozyd): ticket order, holds (including the gmktec hold that only legacy-coordinator-agent lifts) and the ending watch. Each ending is reported to legacy-coordinator-agent and to the work item's owning plan.
- It exits once dispatch-control-plane (bd-ib-k6dqwc) admits gmktec work and the tmp/ launchers are retired. dispatch-control-plane does not absorb today's operations.
