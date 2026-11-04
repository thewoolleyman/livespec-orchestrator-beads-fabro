## The maintainer's statement of what done means

2026-10-24 ~18:3xZ, verbatim, in order: 'Okay it's unacceptable that this logic is living in uncommitted scripts. Anything that is not committed should be committed but this is also a one-off and sort of hack workaround just for this plan. It is useful as a pattern that emerged. Ideally the long term would be that this is driven through the console application but we have had that track of work on hold for a while and probably still will. I want you to spin up a new plan which will follow all proper livespec precedents and discipline, and commit these scripts, but as provisional and experimental. Make the plan clear that driving this through the console app or another more first-class means would be preferable.' Then: 'Remember to use the same standards for where things live, for code quality, all of that stuff. Pick the right repo, pick the right directories, use the discipline, use all of the code quality standards, everything.' Then: 'Okay after you're done, you need to delete all of the other temporary crap so that it does not get used. There should be no scripts living under the tmp directory.'

## Definition of Done assertions derived from that statement

- The fleet launch scripts the factory seats run today, namely the dispatch-dual launcher, the caam-rotation hold release, the launch-time Definition-of-Done pre-screen, the per-repository credential wrappers and the default-factory resolver, are committed on livespec-orchestrator-beads-fabro master under the top-level fleet-launch/ directory, and each one opens with a banner marking it PROVISIONAL and EXPERIMENTAL that names its first-class replacement.
- fleet-launch/README.md states that the directory is a provisional, experimental stopgap for one plan's dispatch pattern, that driving fleet launch through the livespec console application, or through a first-class committed launch-loop tool (bd-ib-jr6w7v), is the preferred means, and the condition under which the directory is retired.
- `just check` runs a check-fleet-launch target that shellchecks every fleet-launch shell script, lints every fleet-launch Python file under the repository's standing Python checks, and runs a hermetic test harness covering board reading, the shared fleet-cap refusal, FIFO ticket order, the hold file and the retired-board case, so a defect in a launcher script turns master red.
- Every host-specific value a fleet-launch script reads (factory server URLs, the fleet-cap file, the queue and in-flight directories, the fabro binary paths) is declared in one configuration block at the script's head or in one sourced configuration file, never inline at its point of use.
- Every factory launch on the operator host runs a fleet-launch script from a checkout of livespec-orchestrator-beads-fabro master, and no running launcher process executes a script from a tmp/ path.
- No fleet repository's tmp/ directory on the operator host contains a shell or Python script.
- plan/provisional-fleet-launch/research/ carries an analysis, written by a session with no role in either workflow's implementation, that compares the coordinator-and-seats workflow which evolved under gitops-fleet-capacity-monitoring with the livespec console application by the human attention each needs per unit of factory throughput, states the pros and cons of each, and recommends how to run the homelab and Kubernetes conversion work.

# Charter — provisional-fleet-launch

## Why this plan exists

The gitops-fleet-capacity-monitoring plan (livespec-dev-tooling-dfixhe) drives every factory launch through hand-grown
seat scripts in `livespec-orchestrator-beads-fabro/tmp/petri-canary/`: 124 shell and Python files (819 entries
with logs), about 680 revisions of one launcher (`dispatch-dual-r681b.sh`, 60 live processes at 18:3xZ on
2026-10-24). They hold the fleet's shared cap, the per-factory FIFO, the hold file, the board and marker readers, and
the ready-set and R316 gates. None of it is committed, reviewed or tested, and two defects reached production on
2026-10-24 alone: the 13:07Z-14:37Z stall when the launchers kept reading the stopped hp board, and the 14:39Z
`hl_rows` line swallowed into a comment, which `bash -n` passed.

## What this plan is, and what it is not

It is a PROVISIONAL and EXPERIMENTAL capture of a pattern that emerged under one plan. It brings the live scripts
under the repository's standing discipline (committed, reviewed, linted, tested, released) so they stop being a
silent failure surface, and it removes every tmp copy so nothing runs uncommitted code.

It is NOT the first-class design. The maintainer's stated preference is that fleet launch be driven through the
livespec console application, whose track is on hold and expected to stay on hold, or another more first-class
means. The nearest such means already filed is bd-ib-jr6w7v, RE-SCOPED 2026-10-24 by coordinator ruling (a): the
first-class thing is a committed, tested LAUNCH LOOP, not a Dispatcher change. SPECIFICATION/contracts.md
§"Host concurrency belongs to the Fabro scheduler" (v053, plan retire-host-dispatch-cap) forbids the Dispatcher any
host-level concurrency limit, admission gauge or lock, and makes `wip_cap` its ONLY concurrency control. The fleet
cap, FIFO, hold and board readers are therefore caller-side launch-loop concerns (AGENTS.md "What a launch loop MAY
add on its own"), and a Dispatcher-owned fleet cap would reverse ratified spec. fleet-launch/ is that loop in
provisional form; it is retired when the console application or the graduated loop tool (bd-ib-jr6w7v) carries
launches and the seats use it.

## Placement, by precedent

- Repository: livespec-orchestrator-beads-fabro. The scripts already live in its working tree, it owns the
  dispatcher they wrap, and it already carries committed operator tooling (`dev-tooling/gate-run.sh`,
  `dev-tooling/dod-preflight.sh`).
- Directory: a top-level `fleet-launch/`, by the `bd-guard/` precedent. That is a stopgap shell tool with its own
  `test/` harness and a private `check-bd-guard` target in the `just check` aggregate. Shellcheck runs there and is
  a loud warning when absent; the hermetic harness is the hard gate. `dev-tooling/` is reserved for the repo's own
  enforcement and workflow scripts, and its rules (`dev-tooling/CLAUDE.md`) make the justfile the single source of
  truth for invocations.
- Quality bar: the repository's full standards. Shell is shellcheck-clean, with every host value in one
  configuration block. Python is under the standing Python checks; a product `.py` follows Red-Green-Replay. The
  aggregate declares its one new target in the justfile's `check:` targets array, never in a second list.

## Scope

IN: the live set. That is the dispatch-dual launcher (r681b and the r681 it replaced), the caam-rotation hold
release, the R316 pre-screen, the per-repository `with-*-env-keep-path.sh` wrappers, the default-factory resolver
and the host-capture payload builder the launcher calls. The banner, README, check target and harness. Moving
every seat launcher onto the committed copy. Deleting every script under every fleet repository's `tmp/`.

OUT: the ~110 dead one-off scripts (`r373`-`r471` runners, capture tails, headroom waits). They are history, not
tooling. They are deleted, not committed; the ledger comments that cite them keep their evidence. Also out: the
first-class replacement itself (bd-ib-jr6w7v, and the console track).

## Ordering constraint (the confirm-the-reader rule)

The tmp copies are DELETED LAST. Commit, then move every running launcher onto the committed path and confirm no
process reads a tmp script, and only then delete. Deleting first breaks the next launcher that sources a wrapper
from tmp, silently. Long-running launchers hold their old inode, so they are drained or restarted onto the
committed path, never killed mid-run (a factory run is never cancelled for this).

## Commissioned analysis: the evolved workflow versus the console

Maintainer direction 2026-10-24 ~18:4xZ, verbatim: 'As part of the plan I want you to have it commission an analysis
of the workflow that evolved here versus the console (and the pros and cons of each) on how to actually optimize the
level of human attention needed to keep stuff flowing through the factory for a large-scale effort like this. This
will inform how we do the home lab and Kubernetes work.'

The analysis is COMMISSIONED, not written by this plan's driver. An analyst session with no role in either workflow's
implementation compares (1) the workflow that evolved under gitops-fleet-capacity-monitoring (a coordinator seat on a
self-paced tick loop, specialist seats relaying over cross-session messages, ledger-held handoffs, seat-run launcher
scripts, and standing maintainer mandates) against (2) the livespec console application's design. Its measure is
human attention per unit of factory throughput. Evidence to read: the dfixhe timeline (e.g. 2026-10-24: the 13:07Z
stall, the a1 rotation hold, the R316 refusal tallies, maintainer interventions), the console repository's plans,
and the factory journals. It names, for each: where a human must look, decide or press; what stalls silently; what
it costs in interactive token spend (2026-10-24 17:43Z: interactive was 62% of Claude spend); and how it scales to a
large multi-repo effort. It ends with a recommendation for running the homelab and Kubernetes conversion work.

## Derivation note

The seven assertions were derived by the coordinator session from the maintainer's statements, quoted verbatim
above, and created without a confirmation round under the maintainer's 2026-10-24 direction not to block on
prompts. They are recorded as session-derived in the first handoff, for objection.
