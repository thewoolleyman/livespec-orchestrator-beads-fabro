## The maintainer's statement of what done means

PLAN SCOPE: three deliverables, each its own child work item, split by repo and tier. No item may mix a SPECIFICATION/ change with code; if spec text is needed, route it per the prose (propose-change).

A. Prose rule, fleet-wide. Add a discipline to the fleet's agent-discipline guidance: the livespec repo's agent-disciplines document, wherever the fleet keeps disciplines like "A factory or tooling BREAKAGE stops the line"; find it. Also add a short pointer in livespec-orchestrator-beads-fabro's AGENTS.md and in livespec-overseer's `.ai/dispatch-traps.md`. Proposed text:
"Never re-attempt a failed dispatch without naming what changed. Before any retry, state in one sentence the specific difference that addresses the recorded failure: a code change in the failing check you can point to, a changed item text, or a recovered external condition. 'A newer build exists' is not a reason. Build drift is permanent in this continuous-deployment fleet, and the drift warning is ambient, not a diagnosis. If you cannot name the difference, read the refusal, find the code that produced it, and diff that code across builds before launching anything. If there is still no difference, stop and report it as a defect rather than retrying."
File the cross-repo pieces in their own repos' tenants, or as children per the prose's cross-repo rules. Be explicit about where each lands.

B. Mechanical guard in the dispatcher (livespec-orchestrator-beads-fabro). Record each failed or refused dispatch's refusal signature on the work item: stage/admission name plus error class, the build that produced it, and a timestamp. A subsequent dispatch of the same item whose last failure has the same signature is REFUSED unless the caller passes an explicit `--because "<what changed>"` argument, which is journaled on the item and in the handoff/journal. Optionally, when the refusing check's module differs between the failing build and the current build, report that fact in the refusal so the agent learns whether the code actually changed. Acceptance criteria must be concrete and testable. Must be dispatch-safe per that repo's rules: no host-side acts in acceptance, and no `{{...}}` tokens.

C. Reword the build-drift / staleness warning so it no longer suggests switching builds as a fix. It should say drift is informational and that re-dispatch requires the named-change discipline (pointing at B's `--because`).

## Definition of Done assertions derived from that statement

- The livespec repository's `.ai/agent-disciplines.md` carries a section headed `Never re-attempt a failed dispatch without naming what changed` that states the named-change retry rule, and that file's cross-cutting disciplines index lists it.
- This repository's `AGENTS.md` carries a short pointer that states the named-change retry rule and cites that livespec section by its exact heading.
- The livespec-overseer repository's `.ai/dispatch-traps.md` carries a short pointer that states the named-change retry rule and cites that livespec section by its exact heading.
- On a released orchestrator build, a dispatch of a work item whose most recent recorded dispatch outcome is a failure or refusal is refused before any factory run starts unless the caller supplies `--because` naming what changed, and the supplied reason is recorded on the item and in the dispatch journal.
- On a released orchestrator build, the build-drift and release-staleness warnings state that drift is informational and that re-dispatching a failed item requires naming what changed through `--because`, rather than presenting a build switch as the fix.

## Why this plan exists

A failed or refused factory dispatch was re-attempted twice in one session
without anyone naming what had changed since the failure. The maintainer
stopped the second re-attempt as thrashing. Re-dispatch is cheap for the agent
that launches it and expensive for the maintainer: a factory run costs hours of
wall clock and a large token budget, and a re-attempt that cannot succeed spends
both for nothing.

This note is the evidence record. It is written once; later reasoning goes in
new notes beside it.

## The incident (2026-10-11 and 2026-10-12)

A Claude session driving plan `herdr-overseer` in `livespec-overseer`
dispatched work item `overseer-fatiq3` with `drive --action impl:<id>`. The
dispatcher's Fabro currency admission refused it with "reported no server
build commit".

1. The session was bound to orchestrator build 0.182.0. In that build,
   `_dispatcher_fabro_currency_sources.py` parsed the TEXT output of
   `fabro version` with the regular expression `\(([0-9a-f]{7,40})\b`, applied
   to a line containing the word "server". Verified against the tag:
   `git show v0.182.0:.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_fabro_currency_sources.py`
   line 99 carries `_COMMIT_PATTERN = re.compile(r"\(([0-9a-f]{7,40})\b")`.
2. The `hp` factory prints `Server: <url>` and `Git SHA: 8869e88` on separate
   lines, so the pattern never matched. This was a parser defect, not a
   factory condition.
3. Meanwhile the registered build had moved to 0.187.0, and the dispatcher's
   build-drift warning (journal stage `dispatcher-registered-install-lag`)
   invited using it. Its text today ends: "Restart the session, or invoke the
   registered build's scripts/bin entry point by explicit path".
4. The agent re-launched on 0.187.0 WITHOUT first checking whether 0.187.0
   changed the failing check. It happened to: commit `6a8e35c1` ("fix: read the
   serving Fabro build from `fabro version --json`", 2026-10-11 11:10 +0200)
   switched the source to `fabro version --json` and reads `server.git_sha`.
   `git tag --contains 6a8e35c1` shows it first shipped in v0.182.1. The agent
   did not know that when it launched; it was a lucky retry, not a diagnosed
   one.
5. Earlier in the same session, a dispatch had also been re-attempted after a
   deterministic failure without a named change.

## Root causes

1. **Build drift is permanent here.** In this continuous-deployment fleet the
   registered plugin build moves forward constantly while sessions run. The
   drift warning fires on almost every dispatch, so it reads as "a newer build
   may fix it" when it is really ambient information.
2. **The cost asymmetry.** Re-dispatching costs the agent one command and costs
   the maintainer a factory run.
3. **No surface asks what changed.** Neither the agent-discipline prose nor
   the dispatcher requires naming WHAT CHANGED since the failed attempt before
   trying again.

## What the plan delivers

Three deliverables, split by repository and tier. None of them mixes a
`SPECIFICATION/` change with code.

- **A. A prose rule, fleet-wide.** A new discipline in livespec
  `.ai/agent-disciplines.md`, beside "A factory or tooling BREAKAGE stops the
  line", headed `## Never re-attempt a failed dispatch without naming what
  changed`, plus short pointers to it from this repository's `AGENTS.md` and
  from livespec-overseer's `.ai/dispatch-traps.md`. The proposed rule text:

  > Never re-attempt a failed dispatch without naming what changed. Before any
  > retry, state in one sentence the specific difference that addresses the
  > recorded failure: a code change in the failing check you can point to, a
  > changed item text, or a recovered external condition. 'A newer build
  > exists' is not a reason. Build drift is permanent in this
  > continuous-deployment fleet, and the drift warning is ambient, not a
  > diagnosis. If you cannot name the difference, read the refusal, find the
  > code that produced it, and diff that code across builds before launching
  > anything. If there is still no difference, stop and report it as a defect
  > rather than retrying.

- **B. A mechanical guard in the dispatcher (this repository).** Each failed or
  refused dispatch records a refusal signature on the work item: the stage or
  admission name, the error class, the build that produced it, and a
  timestamp. A later dispatch of an item whose most recent outcome is such a
  signature is refused unless the caller passes `--because "<what changed>"`,
  which is journaled on the item and in the dispatch journal. When the
  refusing check's module can be read from both the failing build and the
  current build, the refusal says whether the two copies differ, so the agent
  learns whether the code actually changed.

- **C. Reword the drift and staleness warnings (this repository).** They say
  that drift is informational, and that re-dispatching a failed item requires
  the named-change discipline through B's `--because`. Switching builds is no
  longer presented as a fix.

## Session decisions taken while scoping

These were decided from the commissioning brief and the source, not asked.

- **Where each piece lands.** The A pieces live in three repositories, so each
  is filed in its own repository's ledger tenant. The `bd-ib` piece is a
  parent-child child of this plan's epic. The `livespec` and `overseer` pieces
  cannot carry a parent-child edge to a `bd-ib` epic across tenants. They name
  the plan epic in their descriptions instead, and the plan's carrier map
  names them by id. No execution mirror is needed, because each item's
  deliverable is in the repository whose tenant holds it.
- **What "same signature" means mechanically.** The brief's guard keys on the
  item's most recent recorded failure. Any recorded failure or refusal arms the
  guard, and `--because` is required to proceed past it. An attempt admitted
  with `--because` that fails with the same stage and error class produces a
  refusal saying the stated reason did not change the outcome. A
  work-in-progress-cap capacity deferral is a wait, not a failure, so it
  records no signature.
- **The spec.** C stays inside the ratified contract.
  `SPECIFICATION/contracts.md` requires the needs-attention staleness fact to
  name the restart-and-update remedy, and C keeps that remedy while adding the
  informational framing. B adds a new blocking admission refusal, which the
  ratified dispatcher-admission contract does not yet name. Spec text cannot be
  factory-authored here, so it is NOT folded into B. It is routed to
  `/livespec:propose-change` as its own spec operation and recorded as a
  deferral in the scope event. B's Definition of Done references the existing
  §"Dispatcher admission, WIP cap, and post-merge acceptance".
- **Ordering.** B depends on nothing. C depends on B because its new text names
  B's `--because` argument. The three A pieces depend on nothing mechanically.
  The two pointers cite the livespec section by its exact heading, so they read
  best once the livespec item has merged.

## Code the deliverables touch (measured on master at 28328c36)

- `commands/_dispatcher_registered_install_currency.py` holds the
  registered-install lag warning text (`lag_detail`, stage
  `dispatcher-registered-install-lag`).
- `commands/_dispatcher_staleness_gate.py` holds the release-staleness warning
  (stage `dispatcher-staleness-warning`).
- `commands/_needs_attention_currency_staleness.py` holds the needs-attention
  dispatcher-currency-staleness fact.
- `commands/_dispatcher_dispatch_args.py` (`add_dispatch_common`) is the shared
  flag surface of the dispatching subcommands. `commands/_drive_impl_dispatch.py`
  (`build_dispatcher_argv`) builds the `dispatcher.py loop` argv that
  `drive --action impl:<id>` runs.
- `commands/_dispatcher_fabro_currency_gate.py` (stage
  `dispatcher-fabro-currency-refused`) is the refusal from the incident.
- `commands/_dispatcher_engine_journal.py` (`journal_stage`) writes the
  dispatch-journal records.
