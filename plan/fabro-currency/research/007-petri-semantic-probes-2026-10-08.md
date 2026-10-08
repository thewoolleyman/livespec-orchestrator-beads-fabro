# Petri semantic probes, pinned versus candidate, 2026-10-08

P3 of plan `fabro-currency` (`bd-ib-4jzql3`), second session of the day.
Research note 006 stood the `hp-candidate` instance up and ran the existing
Enemy Unit Test suite; this note records the targeted probes that answer the
semantic-gap questions assessment 001 said could only be settled on a real
build. Each probe is a tiny script-node graph run through the matching client
from the orchestrator checkout; the candidate is `v0.378.0-nightly.0`
(`64b9d88`) on `hp:32278`, the pinned control is `0.254.0` (`8869e88`) on
`hp:32276`. Production was not touched; the pinned probes used six of its
fifteen scheduler slots for about two minutes.

## Results

The a2 row writes the template opener and closer as U+27E6 and U+27E7 (the
fleet convention from `livespec-dev-tooling-9yb4`) because the literal pair
poisons ledger and goal rendering; the probe file itself carries the literal.

| Probe | Pinned 0.254 | Candidate 0.378 | Consequence |
| --- | --- | --- | --- |
| p1 failed script node WITH an edge to exit | SUCCEEDED (`01M4DCTZKQ2N`) | SUCCEEDED (`01M4DCQPCX6Z`) | unchanged: a failed node routes along its edges |
| p2 `goal_gate=true` on a failing script node | FAILED, `goal gate unsatisfied for node fail and no retry target` (`01M4DCVER067`) | FAILED, `script exited with status 1` + the script's stderr (`01M4DCR2T008`) | the Petri-valid failing fixture; and stderr is now readable in `conclusion.failure.detail.message` |
| p3 self-loop guarded by `context.internal.node_visit_count < 3` | (no stage data on pinned) | looped ZERO times: routing took the unconditional exit edge at visit 1 (`01M4DCRF60HP`) | visit-count conditions are dead |
| p3e upstream-documented fixed loop: diamond gate, `gate -> exit [condition="node_visit_count >= 3"]`, unconditional back-edge | not run | gate fired 8 times and never exited; a file-counter safety failed the run at improve visit 9 (`01M4DD5K8H88`) | the key the docs still document is not populated |
| p3c self-loop guarded by `outcome=succeeded` with a counter that fails at visit 3 | not run | looped 3 times, then exited: `step@1, step@2, step@3` (`01M4DD6WXJGW`) | outcome conditions work |
| p3f `max_visits=3` on the looping node | not run | FAILED after 3 firings: `node 1 exceeded its firing budget of 3` (`01M4DD88R59M`) | the loop cap that works is a hard failure, not a route |
| p4 Docker resources (`cpu 2`, `memory 4GB` resolved into the run spec) | container `CpuQuota=200000 Memory=4000000000` (`01M4DCWK7PMR`) | container `CpuQuota=0 Memory=0` (`01M4DCRXVPRJ`) | limits are dropped on the Docker path; `bd-ib-otyq6l` |
| p5 shell quoting in `script` | SUCCEEDED (`01M4DCX1FCCG`) | SUCCEEDED (`01M4DCSA55FP`) | verbatim shell on both |
| p6 goal-gated script prints `LIVESPEC_NEEDS_HUMAN: …` to stderr and exits 1 | FAILED, message `goal gate unsatisfied…` (`01M4DCXHTECH`) | FAILED, message carries the marker line (`01M4DCSSJM6C`) | the port reads the marker from `conclusion.failure.detail.message` on Petri |
| a1 ACP node, `acp.config` JSON, fake agent from research 004 | not run | SUCCEEDED, agent answered (`01M4DDF7ZV5B`) | the literal JSON form works |
| a2 ACP node, templated `acp.command="⟦ inputs.adapter ⟧"` with the input supplied | not run | FAILED, `the agent process exited before the protocol completed` (`01M4DDFP0FH5`) | templated `acp.command` is dead (fabro 474) |
| a3 ACP node, literal `acp.command="FAKE_PROBE=1 python3 …"` | not run | SUCCEEDED (`01M4DDG2QHXN`) | a literal command with a leading `KEY=value` still launches |

Note on the a-probes: the first attempt at each failed at run creation with
`backend=api cannot use acp configuration`; the node needs `backend="acp"`
(graph- or node-level) on this engine. Before that, all three were refused at
admission with `fabro.model.no_ready_provider` until a placeholder
`OPENAI_API_KEY` (not a real key) was stored in the candidate's vault with
`fabro secret set --value-stdin`. That placeholder is a cutover decision for
`bd-ib-sxcnj7` and `bd-ib-4ipmub`, because the OAuth-only posture says the
server holds no provider key.

Production runs on pinned today start their sandbox with `CpuQuota=400000
Memory=8000000000` (container `fabro-run-01M4DA4F5WAY…`, measured with
`docker inspect` on hp). The candidate's Docker containers are named
`petri-<run-id>-l0`.

## What validate cannot tell you

`validate --json` on the candidate client accepted every ACP shape tried: the
`acp.config` JSON form, the same with an unknown `cwd` key, a templated
`acp.command`, a literal `acp.command`, and an `x.` namespace attribute. The
only errors it raised on the production graph were the three
`attractor.condition.syntax` errors from `inputs.*` tokens inside edge
conditions. So graph validity is necessary and nowhere near sufficient: every
ACP shape question above was answered only by a launch.

## Source trail for the resource gap

`lib/components/fabro-petri/src/engine.rs` at the tag converts the resolved
`EnvironmentResourcesSettings` into `DaytonaResources` only (upstream PR 910,
merged 2026-09-29, "forward configured resources"); Petri's
`crates/core/executor-sandbox/src/backend.rs` has no Docker counterpart, and
`sandbox-driver-docker/src/create.rs` applies `memory` and `cpu_quota` from
`spec.resources` whenever they are present. The fix is a forwarding change in
Fabro, upstream first.

## One more trap, recorded because it cost three runs

A `fabro run` from a checkout whose HEAD commit is no longer a branch tip on
origin is refused with `the exact local Git commit could not be made available
from the canonical GitHub origin; push the commit and try again`, even though
the commit exists on origin. It happened here because two docs pull requests
merged between probe batches and moved `origin/master` past the primary. A
fast-forward cleared it. This is the primary-behind-origin trap from the
beads catalogue, now with the Petri-era wording.
