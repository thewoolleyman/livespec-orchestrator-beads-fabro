# research/

Durable scratch for analyses, measurement baselines, and exploratory
notes that inform future work in this repo without being spec
content. Mirrors the livespec repo's `research/` convention (seeded
here the same way livespec-dev-tooling's `research/` was, by
dev-tooling PR #116). Per livespec core's Planning Lane guidance this
is the repo's SINGLE standalone-research tree: analysis that belongs
to an ACTIVE planning thread lives under `plan/<topic>/research/`
instead, and archives with its thread (to `plan/archive/<topic>/`)
when the thread's epic closes.

## What lives here

Subdirectories group docs by topic. As of writing:

- `loop-reflection-gate/` — best-practices survey + design docs for
  the fabro factory loop's eval/audit/reflection gate, plus the
  human-ratified `lessons.md` digest. **LOAD-BEARING — do not move or
  archive without a coordinated code change:** the out-of-band
  reflector's default lessons path is
  `research/loop-reflection-gate/lessons.md`
  (`commands/_dispatcher_reflector_oob.py`), and the telemetry
  modules (`_otel_receive.py`, `_otel_scrub.py`,
  `_dispatcher_cost_pricing.py`, `_dispatcher_heartbeat_probe.py`)
  cite these docs as design-of-record.
Completed research topics are moved WHOLE (one subdirectory per
topic) to the top-level `archive/research/<topic>/` once their
work-items close. The former repo-local `research/archive/<topic>/`
home is RETIRED in favor of that fleet-wide top-level location.
Archived files are frozen historical evidence — do not edit; they
remain citable at their archived paths (e.g.
`archive/research/w7-orchestrator-convergence/`,
`archive/research/context-completeness/`).

## What this directory is NOT

- **Not `SPECIFICATION/`.** Files here are NOT requirements. Anything
  that matures into a rule the system must honor flows through
  `/livespec:propose-change` → `/livespec:revise`.
- **Not a planning thread.** Multi-session planning work with a
  resumable handoff belongs in `plan/<topic>/` (see the `plan`
  skill), not here.

## When to add a doc

When an investigation produces something worth re-reading later —
a measurement baseline, an audit, a design deliberation — that is
not (yet) a requirement. Markdown, free-form, no required template.
