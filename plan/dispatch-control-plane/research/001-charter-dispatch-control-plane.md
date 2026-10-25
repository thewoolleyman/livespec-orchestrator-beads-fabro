## The maintainer's statement of what done means

2026-10-25 ~00:3xZ, verbatim: "I still don't even know where this data store came from. It was not part of my original design and it is something that the agents must have evolved themselves. I want you to trace the history and genesis of it because I never would have made such a decision to have this critical path be stored in a temporary file like this. The bigger question is how this relates to the dispatcher and I recognize that this is a hole in the design that I have been ignoring and hand-waving around. There was a vague plan that the factory would just auto-dispatch work items but that has fallen apart because the number of work items always exceeds the number of tokens (and compute capacity) that I have available, or at least tokens anyway. And the other path was to have this driven through the livespec console applications, the current CLI, and eventually a web application so that the automation would be driven through there. But my guess is that this is something that has evolved through the third way of driving these through interactive LLM sessions. There therefore remains the main question of where this should live in the official livespec ecosystem. I think it seems like it needs to be related to the foreman skill. Or somewhere in the overseer app but it should definitely be anchored to some sort of skill or official thing. I know. I think somewhere in the console app there was a plan that was retiring the supervisor skills and possibly leaving the foreman skill around, but migrating to the console. You can look there for some context. I know that's pretty hand-wavy but the bottom line here is we need to anchor this in real API surface mechanisms (whether it's the overseer skills like the foreman or the supervisor or the console or otherwise). We need to not just have it randomly floating and not be clearly specified, and have a solid UX stance."

Earlier the same evening, verbatim: "I am really worried that we are dependent upon something that has persisted only in the temp directory but it contains historical data. If we lose this file, or move to another host, or start running this on containerized sessions, then it will not work. We need to step back and completely rethink this ... Not just because of the performance problems but because of portability, persistence, and backup discipline."

## Definition of Done assertions derived from that statement

- A research note in the plan traces the dispatch journal's genesis: the commits, spec revisions and work items that introduced it and each decision-bearing reader, with dates.
- A research note maps every way work is driven into the factory today (the Dispatcher's auto loop, the console, interactive seat sessions and their tmp/ launchers) and which host-local state each reads or writes.
- The plan records the maintainer's ruling on which official livespec surface owns dispatch control and its state (foreman skill, overseer, console or other), with the alternatives weighed.
- The governing specification states where every piece of state a dispatch decision depends on lives, and states that none of it is a host-local file.
- With the dispatch journal absent, a dispatch from a fresh checkout on another host makes the same admission, hold and recovery decisions as on the primary host.
- The chosen surface has a specified operator UX: the commands or views through which dispatch is started, held and observed.

# Charter — dispatch-control-plane

## Topic

Where dispatch control, and the state dispatch decisions depend on, should live in the official livespec
ecosystem. Today that state is a per-repo, gitignored, host-local `tmp/fabro-dispatch-journal.jsonl`, and
dispatch is driven ad hoc from interactive seat sessions through uncommitted `tmp/` launchers.

## How this plan is worked

The maintainer approved creating this plan with the Definition of Done above and DRIVES it interactively:
discussion, exploration and research come first. The six assertions were confirmed by the maintainer
("Create as drafted") before creation; this note records them beside the statements they derive from. No
child work-item is filed and no scope event is recorded until the maintainer has ruled on the owning surface
(assertion 3). The brief that chartered this plan was prepared by the coordinator session
`gitops-fleet-capacity-monitoring` (plan epic `livespec-dev-tooling-dfixhe`) on 2026-10-25.

## Why this plan exists

The Dispatcher's decision-bearing state lives in an append-only JSONL file under each repository's gitignored
`tmp/` directory, on one host. Nothing in the specification places it there, names its durability or retention,
or says what a dispatch should do when it is absent. The maintainer did not design that and wants its genesis
traced (assertion 1). The way work reaches the factory has also drifted from both intended paths (an
auto-dispatching factory; the livespec console) into a third, evolved one: interactive LLM seat sessions
running uncommitted launchers (assertion 2). The plan's purpose is to anchor dispatch control and its state in
a real, specified livespec surface with an operator UX (assertions 3, 4, 6), and to make a dispatch portable
across hosts and checkouts (assertion 5).

## Starting evidence

Measured 2026-10-25 by the coordinator session. VERIFY before relying on any of it; it is a starting point for
the research, not a finding of this plan.

- Fifteen repositories each keep their own journal in a gitignored `tmp/`: this one is 326 MB / 504k lines
  (since 2026-06-22), overseer 57 MB, dev-tooling 46 MB, console 26 MB, the rest small. The path is
  `_dispatcher_paths.journal_path` (default `<repo>/tmp/fabro-dispatch-journal.jsonl`), overridable only by
  `--journal`. Several readers hard-code the default. Nothing rotates or compacts it. It is backed up only
  incidentally, by the host's `/data` restic and Arq jobs.
- Class-A readers, where an EMPTY journal makes the Dispatcher do something WRONG:
  - the degraded post-merge step gate, `_dispatcher_step_persistence` ("THE JOURNAL IS THE STATE, deliberately");
  - provider-exhaustion holds, `_dispatcher_provider_exhaustion` (journal-only);
  - the model-fallback warning ledger, `_acp_fallback_warning_ledger`;
  - consecutive-stall detection, `_dispatcher_stall_disposition`;
  - recovery routing, `_dispatcher_recovery_routing`;
  - proof attribution, `_dispatcher_proof_attribution`.
- Class-B readers fail closed when the journal is empty: claim reclaim, publish-branch reclaim, merge-hold release.
- Specification lines found in `SPECIFICATION/contracts.md` (line numbers as of 2026-10-25): 8320-8322 (holds
  MUST stay reconstructible without the journal; only ACP holds comply); 5016-5018 (per-checkout by design);
  4455-4457 (another host's journal is invisible); 1783 (parse at most once per pass); 4319 (an append-only
  audit record). The specification says nothing about location, durability or retention.
- On 2026-10-25 the maintainer authorized pruning unread noise from the journals, with a backup under
  `/data/backups/dispatch-journals/`. That is a stopgap, not this plan's answer.

## Ledger prior art to read first

A survey of this tenant's titles on 2026-10-25 (all statuses, `list-work-items --json`) found no plan or epic on
this topic. These items touch the journal's identity or reach and are context, not carriers:

- `bd-ib-47gr` (closed): reconcile-merged's ambiguous-PR refusal deleted the SHARED cross-item dispatch journal.
- `bd-ib-ewdqub` (backlog): the publish-branch reclaim cannot see a dispatch journaled in a different checkout.
- `bd-ib-pjkyoo` (backlog): reconcile-merged reads the merging run id only from the `--repo` checkout's journal.
- `bd-ib-xw2k` (backlog): the dispatch-journal path has two conventions; some writers and readers bypass the resolver.
- `bd-ib-c4jfp6` (backlog): drive reports green on an empty journal plus exit 0.
- `bd-ib-vwwlwp` (closed): journal invoker attribution and the append chokepoint (spec v073).

## Context to read

- The console repository's plan that retired tmux and the overseer's foreman/supervisor seats
  (`retire-overseer-and-redesign-control-plane-around-console`), decisions D1, D4 and D5.
- This repository's plan `provisional-fleet-launch` (epic `bd-ib-klkbxp`) and its
  `research/002-analysis-coordinator-seats-vs-console.md`.
- The `fleet-launch/` directory and `tmp/petri-canary/` on the operator host.

## Open questions for the maintainer-driven discussion

1. Which official surface owns dispatch control and its state: the overseer's foreman skill, the overseer
   application, the console, or something else? What are the alternatives and their costs?
2. What is the authoritative home for each piece of decision-bearing state (holds, stall counts, fallback
   warnings, step persistence, proof attribution): the ledger, the factory's own run store, a committed file,
   or a service?
3. What does the operator UX look like for starting, holding and observing dispatch on the chosen surface?
4. What retention and backup discipline does the historical journal data need, and what, if anything, must be
   migrated before the host-local file is retired?
