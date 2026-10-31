# Progressive guidance index: the long form of each pointer

Moved word for word from `AGENTS.md` §"Progressive guidance (repo-additive)" on 2026-10-30, when the maintainer
directed AGENTS.md split into a short core plus read-on-demand `.ai/` files
(answer recorded on `livespec-dev-tooling-dfixhe`; plan epic `bd-ib-raqyki`).
Words such as "above" and "below" point into the AGENTS.md this text came from;
the sections they name now live in the `.ai/` files AGENTS.md routes to.

## Progressive guidance (repo-additive)

Repo-specific operational notes live under `.ai/`, loaded on demand rather
than inlined here (livespec core contracts §"Fleet agent-instruction core"
— the progressive-disclosure convention; every reference below MUST
resolve, which `check-agents-ai-references-resolve` enforces).

Both files below existed before this section did, and neither was reachable
from this file — an agent following AGENTS.md as its entry point was never
routed to them. That is the failure mode the resolve check structurally
cannot catch: it verifies that references RESOLVE, so a repo that makes no
references passes with its guidance orphaned.

- Read `.ai/cross-tenant-execution-mirror.md` BEFORE working a work-item
  whose tenant repo differs from the repo that must receive the
  implementation. The Dispatcher sandboxes the `--repo` tenant repo and has
  no per-item repo targeting, so the mirror convention is the only correct
  route; guessing at it is how a change lands in the wrong repo.
- Read `.ai/supervisor-protocol.md` before driving a worker as supervisor —
  the HALT-first preconditions, and the rule that new supervisor handoffs
  are ledger epic entries, never files under `plan/<topic>/`.
- Read `.ai/plan-archive-completeness-gate.md` BEFORE archiving a plan, and
  before closing any plan epic whose directory is already under
  `plan/archive/`. Moving that directory BY HAND in a pull request runs
  NEITHER of `archive_thread`'s two gates, so a merged archive move is not
  evidence the archive is complete — and the completeness review it skips is
  the only thing that catches debt an OWNED `test: "TODO"` entry hides from
  `check-no-todo-registry` and from the child-disposition gate alike.
- Read `.ai/master-ci-green-preflight.md` BEFORE watching master CI to open a
  dispatch window. The green-master preflight gates on the aggregate job
  `ci-green`, resolved from `dispatcher.master_ci.job`; that name shares no
  prefix with the `check-` family, so an anchored check-run filter assembled
  from the names you remember can EXCLUDE the deciding job and report GREEN
  falsely. The file also records why `gh run list` and the per-commit
  check-runs endpoint can disagree, and that any merge to master re-queues CI
  and closes the window.
- Read `.ai/plugin-cache-lease-and-rebind.md` BEFORE concluding anything about
  which plugin build a running session is executing — and before removing a
  plugin cache build. Each cache build's `.in_use` lease directory is the
  instrument for "is any live session still bound to this build"; a running
  session binds its plugin root once at session start; and the OLD build's lease
  file survives a rebind, so a stale lease file's presence is NOT evidence of
  current binding. The file also records that the plugin prune verb is not an
  eviction verb. Read it also BEFORE reloading plugins in your own herdr pane,
  or before telling the maintainer a reload is theirs to do: a session rebinds
  itself through a detached waiter that sends `/reload-plugins` only once the
  pane is idle and then submits the follow-up prompt separately with
  `herdr agent prompt`. Text typed into your own pane while your turn is
  running joins into one unsubmitted line, and a reload with no follow-up
  prompt leaves the session idle; every herdr call still exits 0.
- Read `.ai/fabro-fork-hand-build.md` BEFORE starting a work-item whose
  implementation lands in the Fabro fork (`thewoolleyman/fabro`,
  `factory-integration`). The fork has no ledger tenant, so neither the
  factory sandbox nor the execution-mirror convention can carry it; the file
  records the host-routed door (`driver-dispatch` in, `close-work-item` with
  the merge SHA out), the shared build cache, the pinned nightly the fork's
  own CI uses, and the fact that a fork pull request against the carrier
  branch shows NO checks — the merge gate is local and must be recorded before
  merging. It also records that merging into the carrier deploys nothing.
- Read `.ai/herdr-plan-tabs.md` BEFORE opening a plan session as a herdr tab,
  moving one out of tmux, or placing or moving any herdr tab. Tab label, Claude
  session name and plan slug are identical by maintainer direction, and a herdr
  agent name is capped at 32 characters, so a slug chosen without that limit
  cannot carry the matching session name. The file carries the measured recipe
  and the kill-the-tmux-session-first rule. It also records that herdr CAN move
  tabs, through the socket API's `tab.move` method, even though the `herdr tab`
  command line has no `move` subcommand. Never tell the maintainer a tab cannot
  be placed.
- Read `.ai/host-captured-proof-replay.md` BEFORE taking or replaying a
  host-captured proof. It states the procedure in order — declare the assertion
  under `Host-captured` with a `Reason:` line, let the merged item rest in
  `acceptance`, capture on the host against the released build, publish with
  `post-host-record`, then have a SEPARATELY STARTED agent session replay and
  publish its own verdict — and it records the two ways a replay has already
  gone wrong here: a publish branch seeded at an ancestor of master, which the
  next run fast-forwards so nothing is demonstrated, and a `herdr` agent pane
  that finishes at agent status `done` rather than `idle`, which is what a wait
  watching only for `idle` sits through. The self-replay refusal is in
  §"Proof-of-Done, publish-branch reclaim, and drive action-id traps" above;
  that file is the procedure the refusal sits inside.
- Read `.ai/plan-session-lessons.md` BEFORE proposing a direction in a plan
  session, filing a plan child, or spinning up an independent reviewer. It
  carries the maintainer's 2026-10-10 rule to route decisions by the stated
  goals and source measurements rather than by prior ledger text, the
  working form for a read-only Codex reviewer on the newest model in a
  herdr pane, and the plan-primitive gaps (no `title` on `update_issue`, no
  Definition-of-Done amend primitive, `create_thread` writes into
  `project_root`) that stall a ledger rewrite.
- Read `.ai/ledger-writers-are-multi-host.md` BEFORE designing anything that
  serializes, locks or fences ledger writers. The maintainer ruled that writers
  may share nothing but the Beads server, so a host-scoped fence is invalid even
  though the tenant listens on loopback today. The file also records which public
  `bd` writes are server-side compare-and-swap operations, and that the exit code
  of `bd close` does not identify the winner.
- Read `.ai/herdr-helper-sessions.md` BEFORE opening a second agent session
  in herdr for a bounded job (an independent critique, a host-proof replay, a
  second opinion). It records that a helper is a SPLIT of your own pane in the
  current tab and never a new tab, that `herdr pane run` word-splits a prompt so
  the agent never starts, and that the pane is closed in the same turn its
  output is consumed — each from a maintainer correction on 2026-10-10. Read it
  also BEFORE messaging any other session: inter-session messages go through
  Claude's `SendMessage`, never `herdr agent prompt` into another session's
  pane (maintainer ruling 2026-10-14).
- Read `.ai/factory-dispatch-preflight-and-triage.md` BEFORE dispatching a
  work-item or triaging a dispatch that ended badly — `filing_display`
  passing does not mean `dod_gate` will, a primary behind origin fails every
  dispatch at 0 ms, a workflow fix ships only through a `fix:` release, and a
  post-merge janitor red names no failing target.
- Read `.ai/factory-working-method.md` BEFORE starting a canary, test
  campaign or local build, proposing an upstream Fabro change, designing a
  measurement, or retracting a claim — the maintainer's throughput,
  host-load, upstream-last-resort and instrument-in-Honeycomb directions.
- Read `.ai/hosts-and-shell-gotchas.md` BEFORE reaching a factory host or
  scripting with `ls`, `cat` or `grep` — this checkout runs ON vps, hp
  accepts only `root` or `cwoolley`, and the shell aliases corrupt command
  substitution.
- Read `.ai/fabro-dispatch-diagnosis.md` BEFORE reading a factory run with the
  host PATH `fabro` — it cannot decode a Petri-era factory's runs, and a
  failed read there is not missing data; `dispatcher.py inspect --factory
  <name> <run-id>` is the reader that uses that factory's own client.
- Read `.ai/git-pr-and-release-mechanics.md` BEFORE arming auto-merge,
  staging an `AGENTS.md` edit, surveying `spec/*` branches, or touching
  `.github/workflows/` — each trap ships a change without its content or
  reports landed work as unlanded.
- Read `.ai/local-implementation-close-path.md` BEFORE opening a non-factory
  pull request that touches product `.py`, running `reconcile-merged` or
  `accept` on an item built in a session, filing follow-up items through the
  capture seam, or diagnosing `needs_attention.py` exiting 124 at its 900 s
  budget — the `factory-override` label reaches CI only on a close/reopen
  event, `approve:` refuses an auto-admission item by design, the filing seam
  takes five minutes per item, and the two in-process probes that name a
  per-item `bd` fan-out's call site (paid for 2026-10-25).
- Read `.ai/gitops-deployment.md` BEFORE any deployment, Ansible, GitOps,
  host-provisioning, `kubectl`, or ssh-to-a-fleet-host action. It carries
  this repository's layer map — which committed artifact deploys each of the
  four in-repository installers, and which three nothing applies at all, so
  a hand install is recognized as a gap in the automation to fix rather than
  a procedure to repeat. No live fleet host is changed by hand; the
  fleet-canonical rules the map sits under are the six in livespec's
  `gitops-deployment-discipline.md` topic, which that file cites by path
  (it lives in livespec, so it is not resolvable from this repository).
