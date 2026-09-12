# SEV-1: a released factory graph that fabro validate rejects

Opened 2026-09-10. This thread governs the remediation of a fleet-wide factory
outage caused by this repo's own release, and the closure of the mechanical gap
that let it ship. The thread carries the original `fix-plugin-install` mandate
too, because the outage was produced by the same session arc and the two share
one root cause shape: a resolution/verification surface nobody gates.

## Part 1 - the original mandate (2026-09-09, largely discharged)

The thread began as "why is the orchestrator plugin not installed properly
across the fleet". Diagnosis: the plugin was ENABLED for a project by committed
`.claude/settings.json` while no install record existed for that project.
Claude Code resolves that state to NO operations and reports NO error, so
`/livespec-orchestrator-beads-fabro:*` skills were silently absent in every
checkout but one. The SessionStart `ensure-plugins` hook that should have
repaired it was itself failing before reaching the install step.

Work that landed and is GOOD (do not redo):

- Marketplace-ref clobber fixed; registry ref returned to `release`; console
  un-pinned (livespec-console-beads-fabro PR #1150).
- Guard check `check-marketplace-ref-release-only` merged (livespec-dev-tooling
  PR #2136) so a pinned ref cannot silently return.
- AGENTS.md build notes merged (PR #2398).
- `bd-ib-cewr.4` — fabro pre-run push precondition now ASKS origin via
  `ls-remote` instead of pushing — fixed via fork PR #7; both factories on
  `fabro 0.254.0 (977cb67)`. CLOSED.
- `bd-ib-loks` — PR-tier model pin corrected to `gpt-5.3-codex-spark`
  (`gpt-5.4-mini` is refused by codex-acp 1.10.0, and a refused pr-tier model
  makes the pr stage report succeeded with NO PR). CLOSED.

`openbrain` and `resume` carry deliberate old pins and were intentionally NOT
touched.

## Part 2 - the SEV-1 this thread now exists to remediate

The `bd-ib-loks` tail above motivated `bd-ib-32xd`: add a `verify_pr` breaker
so a pr stage that publishes nothing fails loud instead of exiting green. The
intent was sound. The delivery was not.

`bd-ib-32xd` shipped as PR #2412, merged as **af366d59**, released as plugin
build **d6ca5151c2bf = 0.146.0**. It replaced the edge `pr -> exit` with
`pr -> verify_pr -> exit` using only CONDITIONAL edges, leaving both `pr` and
the new `verify_pr` with no unconditional fallback. Fabro rejects that graph,
so every dispatch on that build dies before doing any work.

### Measured control (2026-09-10, this session, fabro 0.254.0 (977cb67))

Run against the exact SHIPPED artifact in the released plugin cache, not a
worktree rendering:

    $ fabro validate <cache>/d6ca5151c2bf/.fabro/workflows/implement-work-item/workflow.fabro
    Workflow: ImplementWorkItem (14 nodes, 24 edges)
    error [node: pr]:        Node 'pr' has all conditional outgoing edges with
                             no unconditional fallback (all_conditional_edges)
    error [node: verify_pr]: Node 'verify_pr' has all conditional outgoing edges
                             with no unconditional fallback (all_conditional_edges)
    warning [node: pr]:        orphan_custom_outcome
    warning [node: verify_pr]: orphan_custom_outcome
    Validation failed                                          EXIT=1

    $ fabro validate <cache>/2cf04367f4bf/.fabro/workflows/implement-work-item/workflow.fabro
    Workflow: ImplementWorkItem (13 nodes, 22 edges)
    Validation: OK                                             EXIT=0

Two facts this measurement adds to the original report. First, `pr` is broken
as well as `verify_pr` — inserting the breaker removed `pr`'s OWN unconditional
fallthrough — so a fix that only gives `verify_pr` a fallback is incomplete.
Second, the prior release is a clean positive control, which establishes the
instrument is aimed correctly rather than merely functioning.

### Blast radius (measured 2026-09-10 from installed_plugins.json)

On the BROKEN build d6ca5151c2bf: livespec, livespec-dev-tooling,
livespec-overseer, livespec-console-beads-fabro, AND
livespec-orchestrator-beads-fabro itself — the SessionStart hook moved this
repo from f954334cbb44 onto d6ca5151c2bf at 2026-09-10T15:18, so the blast
radius is FIVE repos, one more than the original handoff recorded.

On the prior good build 2cf04367f4bf: livespec-runtime, dolt-server,
livespec-driver-{claude,codex,pi}, livespec-orchestrator-git-jsonl, homelab.

Both factories (hp, vps) idle at the time of measurement; both run the GOOD
engine fabro 0.254.0 (977cb67). The ENGINE is healthy. The broken artifact is
this repo's released workflow graph.

## Part 3 - root cause, and the prior art that already named it

The proximate cause is a graph edit that was never validated. The systemic
cause is that NOTHING validates it.

`bd-ib-6t4` (P1, BUG, status **backlog**, filed 2026-07-16, owner
thewoolleyman) says so verbatim, and was filed after an IDENTICAL outage:

> Child O8 (PR #680) merged a graph whose review node had ALL-conditional
> outgoing edges - which fabro validate rejects (all_conditional_edges; a node
> needs exactly one unconditional fallthrough). Every dispatch on the post-O8
> graph then failed - the factory was DOWN - until a parallel session landed
> the one-line fix (commit 3c832d6, release 0.41.1). It went uncaught because
> O8's own tests + its acceptance evidence checked DOT structure / build_plan,
> NOT an actual fabro validate on the new graph, and no gate runs fabro
> validate.

So 2026-09-09 is the SECOND occurrence of one defect class, with the same
error code, the same missing-fallback shape, and the same acceptance-evidence
failure mode (structural tests standing in for a real `fabro validate`). The
guard was specified, prioritized P1, and left in backlog for 55 days. That is
the finding this thread must not lose: the incident is not "an agent skipped a
check", it is "the repo has no such check, and already knew".

`bd-ib-6t4` carries zero comments and is free of template-opener tokens, so it
is dispatchable as written.

## Part 4 - what proof this remediation owes

Proxy signals are what produced the outage: CI green, a run reporting
"succeeded", and a merged PR were all true while the factory was down. This
thread therefore treats the following as the ONLY acceptable evidence.

1. `fabro validate` EXIT=0 with zero diagnostics on the fixed graph, run from
   the RELEASED plugin cache after the release, not only from a worktree.
2. The broken control still failing, retained and re-runnable.
3. No repo, host, or plugin runtime resolving d6ca5151c2bf.
4. Cross-repo canaries that CREATE real Fabro runs and reach a healthy
   TERMINAL state, on more than one repo.

A green `just check`, a merged PR, a live process, or one repo's success is
explicitly NOT sufficient for any claim this thread makes.
