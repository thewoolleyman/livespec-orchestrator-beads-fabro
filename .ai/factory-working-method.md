# Factory working method: throughput, host load, upstream, measurement and claims

Maintainer directions and hard-won method for running canaries, test
campaigns and build cycles in this fleet, and for keeping claims honest. Each
entry was first recorded as a Claude Code auto-memory note and is migrated
here (2026-10-18, plan `block-auto-memory-coverage`); the dates are those of
the original direction or measurement.

## Get more out of every canary and test run (maintainer-declared 2026-10-15 and 2026-10-17)

On disposable infrastructure (acceptance VMs, throwaway containers, canary
items), go as fast and as wide as the hardware allows, without being asked.
Slow down only on a LIVE machine, such as an attended converge of a real host.

Before and during any canary campaign or acceptance suite, unprompted:

1. **Pick the smallest dispatchable item as the pipeline canary first**, and
   run any real item beside it rather than instead of it. Start every
   independent plan track in the same turn. An inherited handoff's canary
   choice is not a reason to skip this.
2. **Statically audit for a defect's whole class** once one instance is found,
   and fix the siblings before the next run. For engine migrations, grep the
   dispatcher, `workflow.fabro` and prepare scripts for layout assumptions:
   fixed `/workspace` paths, files written into the clone, checkpoint commits,
   context carried versus the model window, node timeouts versus measured
   durations. A grep for fixed `/workspace` paths found `bd-ib-5qxa5q` (a Codex
   `auth.json` that would have been committed) with no run at all.
3. **Run independent cases in parallel** across every available VM or slot.
4. **Resume a run that failed after publishing** from its PR
   (`dispatcher.py resume`) rather than re-running implement.
5. **Harvest every run, not only its failure**: review findings and
   advisories, warnings, per-node context peak versus window, stage minutes
   versus node timeout, and harness-made files in the branch diff. A guard-file
   leak was found in a review advisory, not in the failure.
6. **Measure where wall time goes and cut fixed costs** (restores, downloads,
   re-converges, test-only waits), and keep long commit and push gates off the
   critical path.

Why: Petri-migration canaries cost two to three hours each and stop at the
first failure; eight canaries had each surfaced one defect when the maintainer
asked "Are you actually making any progress?" (2026-10-15; the method is
recorded on epic `bd-ib-6tcjfx`). On 2026-10-17 (plan `bd-ib-fyozyd`, the
FAULTS suite) one case was re-run three times serially at about 15 minutes
each, each run surfacing one leftover-state defect of the same class, while
three VMs sat idle ("They're all throwaway. You can parallelize this and go as
fast as you want."; recorded as a binding scope event on `bd-ib-fyozyd`). It
recurred on 2026-10-18: a real item was run alone, twice, as the canary; the
dispatch gate refused it both times, about 20 minutes were lost, and smaller
proof items sat idle.

## Run `uptime` before any large local build; dispatch is the default (2026-08-22)

1. **Factory dispatch is the default for build and test cycles** on in-repo,
   factory-safe work: prefer `dispatcher.py dispatch --item <id>` over a local
   compile or a local full test run (consistent with AGENTS.md's "Prefer
   factory dispatch for factory-safe work"). The exemption bar is evidence,
   not preference; "it was easier locally" or "quick check" does not qualify.
   A targeted single-test invocation for a fast red/green check is fine.
2. **Run `uptime` BEFORE launching a large local build or full test run**, even
   when exempt from dispatching. If load is high, wait, narrow the target, or
   ask for it to be sequenced. The measured defect was a from-scratch Rust
   dependency compile launched blind: 352% CPU across 19 concurrent `rustc`
   processes on a box at load 113 with about 7 GB of RAM free, shared by
   roughly 180 sessions on 18 cores. `.ai/fabro-fork-hand-build.md` carries
   the bounded-compile recipe for the fork.

When claiming the outward-facing upstream-Fabro exemption (the Dispatcher has
no per-item repo targeting, so no dispatch route exists for a Fabro-repo edit
from this tenant; see `.ai/cross-tenant-execution-mirror.md` and
`.ai/fabro-fork-hand-build.md`), cite the governing text on the first ask.

## Upstream Fabro changes are a last resort (maintainer-declared 2026-10-15)

Do not propose, or even draft, an upstream Fabro or Petri change unless it is
absolutely necessary. First prove that adapting our own workflow, Dispatcher,
sandbox setup or prompts cannot meet the need on the current engine. List the
in-house adaptations first (workflow edges, prompts, Dispatcher handling,
sandbox setup, guards) and test whether existing engine surfaces cover the
need; only if none can, bring the upstream case to the maintainer with that
proof.

Why: an upstream issue was drafted to route Petri checkpoint failures into the
graph, and the maintainer asked to be shown "why we have to make an upstream
change rather than just going with the current Fabro paradigms and adapting
our workflows to it". It was not necessary: the work tree survives server-side
and is readable through the supported `GET /api/v1/runs/{id}/files` endpoint,
so Dispatcher-side preservation works on the current engine. This narrows
AGENTS.md's "preferably by contributing it upstream" direction for building
what the factory needs: staying current remains the goal, and an upstream
contribution is the last resort, not the default.

## A "measure it" fix rides OpenTelemetry into Honeycomb (maintainer-declared 2026-09-30)

When a fix calls for measurement, instrument it through OpenTelemetry into
Honeycomb on the existing path, never as a journal-only counter or a one-off
script. The maintainer's words, ruling on option C of the factory test-first
plan (`bd-ib-q622ls`): "we want to lean into Honeycomb and open telemetry
observability like we have everywhere else. We should instrument it."

The path already exists: sandbox, then the Dispatcher's OTLP receiver at
`LIVESPEC_SANDBOX_OTEL_ENDPOINT`, then the `_otel_enrich` scrub, then
Honeycomb egress, plus the per-dispatch `dispatcher.calibration` span. A
counter that lives only in a journal cannot be queried, boarded or triggered
on, which is how the fleet-wide post-hoc Red pattern went unseen for months.
Design the measurement as spans or span attributes on that path (name the
span, its attributes, its join to the run's trace, and the Honeycomb board or
trigger that consumes it), and treat the Honeycomb query as the acceptance
evidence.

## A false prior-art hit closes the question (measured 2026-08-22)

AGENTS.md's trap catalogue covers instruments that cannot return a hit
reporting no hits. The mirror image is worse: a prior-art query that returns a
plausible, non-empty, WRONG hit. A bad measurement is contradicted by the next
reader, but a gap declared "already tracked" is never re-tested, so it
produces silence that looks like completeness.

The failure is matching words instead of checking the system. A dispatch
factory-failover gap was ruled "already tracked" on three items matching
*failover*, *standby host* and the repo name; all three were about Dolt
database replication, which their own printed titles said. Where a database is
replicated and where its dispatches run are different systems. It was filed
correctly afterwards as `dolt-server-4i7qos`.

Before accepting that prior art covers your concern, state which system each
candidate is about and check it against the system yours is about. Search with
`--status all`, since closed items are where "already built" hides. If the
candidates concern a different system, say so with their titles quoted, and do
not file over an explicit do-not-file instruction; hand back the evidence and
let the router rule. Report your own near-false-positives too (in the same
exchange a grep for `vps` hit the generic noun "any VPS/cloud", not the host);
doing so against your own interest is what makes the rest of a report
credible.

## A retraction must reach everyone the claim reached (measured 2026-08-27)

When a claim you made turns out to be wrong, send the correction to everyone
the original claim went to, not to whoever is in front of you when you
realise. Measured twice in one day in two sessions: a session promised a peer
"both fixes will be on master before any release is cut", then found that
release PRs auto-merge here (`.github/workflows/auto-enable-merge.yml`), so
holding a release was never in its power. It told its own user and not the
peer, which kept operating on the dead commitment and discovered the partial
v0.84.1 release itself. The peer then had to send a separate retraction of a
claim it had relayed onward, for the same reason.

Before considering a correction done, list who received the original claim:
the user, each peer session, any ledger comment, any merged PR body. Send or
record the correction to each. A merged PR body cannot be edited, so that
correction goes in a ledger comment on the item. Nothing records who a claim
was sent to, which is why this has to be a deliberate step.

The remedy that actually caught this family of errors is a READ-BACK, not
care. Across six instances in one day, at least three were caught by
re-reading the artifact afterwards with the specific claim in hand, and none
by being careful. Assert the read-back, not the write: after filing a ledger
item, re-read it from the store and check parent, status and criteria; after
promising a line is in a file, grep the merged ref for it; after recording a
comment, read it back through `bd comments <id> --json` and index `text`.
"The write returned success" is the claim, not the evidence. Likewise, verify
the CLAIM YOU MADE, not the ARTIFACT YOU BUILT: reviewing a module for
correctness says nothing about whether it contains the line you promised.
