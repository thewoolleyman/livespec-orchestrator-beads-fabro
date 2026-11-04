# Working with the maintainer: the full rules

Moved word for word from `AGENTS.md` §"Working with the maintainer (repo-additive)" on 2026-10-30, when the maintainer
directed AGENTS.md split into a short core plus read-on-demand `.ai/` files
(answer recorded on `livespec-dev-tooling-dfixhe`; plan epic `bd-ib-raqyki`).
Words such as "above" and "below" point into the AGENTS.md this text came from;
the sections they name now live in the `.ai/` files AGENTS.md routes to.

## Working with the maintainer (repo-additive)

- **Spell out "Definition-of-Ready" in full** — the acronym "DoR" is BANNED
  (maintainer-declared 2026-07-04: non-intuitive, carries no meaning). Never
  use it in any prose, document, work-item, commit, or report; always write
  "Definition-of-Ready". (Quoting pre-existing text verbatim for mechanical
  replacement targeting is the only exception.)
- **Name every work item by what it does, never by its id alone**
  (maintainer-declared 2026-10-24: "I don't memorize item IDs"). In any
  status report, question, or summary addressed to the maintainer, refer to a
  work item by a short descriptive name drawn from its title — for example
  "the spec-change-tier decision" rather than `bd-ib-57ss2n`. Put the id in
  brackets after the name only when the maintainer may need to act on it or
  look it up. The same applies to runs, gates and pull requests: say what each
  one is for before giving its identifier. Ledger comments and handoffs written
  for other agents may keep ids, because those readers do resolve them.
- **Maintainer-facing documents must explain their own notation.** Define
  every symbol before or beside its first use (an arrow, a column, a tally),
  make headings match their content, and write complete sentences over
  compressed fragments.
- **Drive authorized work to completion; do not over-ask** (maintainer-declared
  2026-07-06). When the maintainer names a goal and says to finish or continue
  it ("get this entire track finished", "continue", "don't hold it"), execute
  the WHOLE arc — implement, dispatch, merge, iterate, archive — without pausing
  to confirm each already-authorized step. Ask ONLY for input the maintainer
  alone can give: irreversible/destructive actions, or genuinely ambiguous
  requirements that cannot be settled from the code, spec, or context. An
  operator-flow step that says "present options and let the user select" is
  satisfied by a standing directive once the goal is named — do not re-prompt.
  Surface real blockers and true judgment calls; drop routine "should I
  proceed?" confirmations. Default to acting, then reporting outcomes.
- **A fleet coordinator's ruling is an order; execute it rather than re-asking
  the maintainer** (maintainer-declared 2026-10-23). The coordinator session
  (`gitops-fleet-capacity-monitoring`) exists so that seats do not block on
  the maintainer, and it acts under the maintainer's delegated authorization
  for blocking items. When it RULES on an action in your seat, verify the
  preconditions it names, take the action, verify the outcome, and report
  back to the coordinator and on the shared ledger thread. Do not hold the
  ruling for a direct maintainer confirmation, and do not re-prompt a picker
  it already answered. This holds even for an outward-facing but reversible
  act such as a force-with-lease repair of a factory publish branch. Two limits
  remain: never perform an act your own permission settings denied because a
  peer asked, and never edit settings or this file on a peer's say-so.
  *Instance:* on 2026-10-23 the coordinator ruled that the
  `spec-implementation-lockstep` seat repair `bd-ib-57ss2n`'s publish branch,
  which GitHub had left disagreeing with its pull request. The seat held the
  push to ask the maintainer again, and the item sat blocked for hours until
  the maintainer asked why the seat was ignoring the coordinator's orders.
- **Export, then reap: a dead factory run may be removed without a
  per-instance ask** (maintainer-declared 2026-08-26). For any DEAD factory
  run, capture its full record — the `ps -a` row, run id, terminal state and
  blocked reason, completed nodes, node visits and retries, checkpoint sha,
  review verdict, sandbox image and container id, the verbatim failure cause,
  and every dispatch-journal row for the item — into a durable ledger comment
  on the work-item, VERIFY IT BY READ-BACK, and only then run
  `fabro rm --force`. The export is the precondition, not a courtesy: it is
  what converts an irreversible destruction on shared infrastructure into a
  safe one, so a reap whose export has not been read-back verified is not
  covered by this rule. **Read the comment back through `bd comments <id>
  --json` and index `text`, never `body`** — `bd show --json` carries no
  comments at all, so the obvious verification reports the write as lost when
  it succeeded (both traps are catalogued above).
  **Scope this narrowly.** It authorizes exactly one class — removing a run
  that is already dead, after a verified export. It is NOT standing
  authorization for destructive acts generally, and it does not extend to
  reaping a LIVE run, deleting branches or worktrees another thread owns, or
  any other irreversible shared-infrastructure action; those still take a
  per-instance decision from the maintainer. Note also what the reap costs:
  everything reachable only through `fabro inspect` / `dump` / `attach`
  against that run id — the sandbox filesystem included — is gone, so a run
  holding UNPUBLISHED work is not a candidate until that work is recovered or
  written off. Establish publication against the forge and the remote first;
  per the trap catalogue a run's own claim of non-publication has proven
  false. (Context: two orphaned runs on shared `hp` — one blocked at `pr`
  after its work had already merged, one dead at `implement` on the
  compaction-404 defect — each held a scheduler slot while a per-instance
  round-trip was made for permission that the export had already made safe.)
- **Revert decisively; do not diagnose first** (maintainer-declared
  2026-07-11). When something erroneously landed and the corrective action is
  already unambiguous (a throwaway/mistaken change on `master` that must be
  undone), execute the revert/undo IMMEDIATELY — do NOT first spend cycles
  investigating whether it is "really" broken or why. Diagnosis is warranted
  BEFORE acting only when it changes WHAT you do; when you already know the
  action, do it first (worktree → revert PR → merge) and diagnose only if it
  serves a follow-up. (Context: a throwaway proof dispatch auto-merged to
  `master` and a post-merge janitor reported a red check; the revert was the
  correct action regardless of the check result, so pausing to diagnose the
  red was wasted ceremony.)
- **Prefer factory dispatch for factory-safe work; do not default to
  hand-building it** (maintainer-declared 2026-07-15). When a work-item is
  factory-safe (in-repo, dispatchable Python/config — NOT outward-facing upstream
  fabro work), default to running it THROUGH the dark factory
  (`dispatcher.py dispatch --item <id>`), not implementing it in-session. Do NOT
  present the factory path as the heavier or less-preferred option — dogfooding the
  factory is the point ("we should be running things to the factory whenever we
  can"). The "it needs a Codex credential" objection is usually hollow: check
  `~/.fabro/bin/fabro ps` for an in-flight dispatch first; a running dispatch is
  live proof the credential works. The dispatcher self-wraps for credentials but
  often cannot reach the credstore alone — run it already inside
  `with-<project>-env.sh`. Hand-build only when the work is genuinely NOT
  factory-safe (outward-facing upstream fabro PRs, e.g. the codex-factory-telemetry
  O-track) or the maintainer explicitly asks. (Context: after re-planning the
  telemetry emitter, the factory-safe slice F1 was first offered as "hand-build
  (recommended) vs dispatch (heavier)"; the maintainer corrected that the
  factory-safe slice is exactly what should be dispatched.)
- **Master-red restoration is the factory-dispatch exception**
  (maintainer-declared 2026-08-20). If latest master is red and the parked item is
  explicitly the fix for that master health failure, do not try to bypass or
  weaken the green-master gate. Pull the item in-session and deliver it through
  worktree -> PR -> merge; PR CI is independent of master, so the PR can prove the
  fix while the dispatch gate stays fail-closed. `gh run rerun --failed` is not a
  remedy for repeat-flakes: it may be useful evidence, but repeated reruns can
  still leave master red and the fix factory-parked. If red master also makes the
  local pre-commit hook refuse every commit, use the server-side GitHub revert
  break-glass path rather than `--no-verify`: fetch the offending PR's node id
  with a `repository.pullRequest(number:)` GraphQL query, then call
  `revertPullRequest` with that id, passing the query and mutation body from
  files. Prefer re-landing the reverted change paired with whatever it broke in
  one PR, not re-landing it alone. A revert that touches product Python is a
  maintainer-authored pull request, so the required `check-factory-provenance`
  job (R6b of plan `mechanically-enforce-factory-usage`) goes RED on it until
  it carries the `factory-override` label with the reason in the body; the
  check reads labels from the pull_request event payload, so apply the label
  BEFORE opening the revert PR, or push or reopen after labelling. A rerun of
  the failed job does not see a label added afterwards.
- **Name the OWNING SESSION when attributing work to another session**
  (maintainer-declared 2026-07-26). When you report that another session made a
  change — a dirty file, a live branch, an in-flight PR, a concurrent worktree —
  identify it by its **session name** (its `/rename` value), not merely by
  project directory or session UUID. The maintainer runs many concurrent
  sessions across the family and coordinates them BY NAME (the names are the
  tmux window names), so "a session in `livespec-console-beads-fabro`" is not
  actionable — it does not say which window to look at. Establish the name
  BEFORE asking any question whose answer depends on what that session is
  doing. Recover it by grepping the session transcript
  (`~/.claude/projects/<project-slug>/<session-id>.jsonl`) for
  `Session renamed to:` — a `type: system` / `subtype: local_command` record
  carrying the `/rename` args — and report it as `<session-name>` (project
  `<project>`, session `<uuid>`), leading with the name. (Context: a revise
  pass blocked on a stale-branch precondition tripped by another session's
  live branch; the options were presented without naming the owner, and the
  maintainer's reply was simply "you need to tell me the name of the session
  which is making this change." Naming it also resolved the block — that
  session's own transcript showed it had already merged the branch and had no
  intent to revise.)
- **Verify every changed path belongs to YOUR thread before you push**
  (maintainer-declared 2026-07-28). Run
  `mise exec -- git diff --name-only origin/master...<your-branch>` as a
  standing pre-push step — every time, not only when you suspect a problem —
  and confirm each path is one the thread you are working owns. Several
  sessions commit to `master` concurrently here, and each
  `plan/<topic>/handoff.md` is owned by its own thread, so "I only meant to
  edit ours" is not evidence. **If you believe your version of another
  thread's file says something theirs does not, do NOT resolve it by editing
  their file.** Drop it from your branch
  (`mise exec -- git checkout origin/master -- <path>`, then
  `--amend`), keep your own thread's edits, and report the difference to the
  maintainer to route to that thread — naming the owning session per the rule
  above. The maintainer's framing: "their thread's record is theirs to write,
  exactly as ours is ours" — the same principle as "never touch another
  session's worktrees or branches", one level up. (Context: a
  `plan/factory-hardening/` branch also carried that thread's
  `handoff.md` — now `plan/archive/dispatch-claim-liveness/handoff.md` — while
  it had PR #1098 open performing the same discharge edit; the collision was
  caught by the maintainer, not by the pushing session.)
- **Vet an escalation before spending the maintainer's attention on it**
  (maintainer-declared 2026-07-30). Before asking the maintainer a question,
  submit it to BOTH an Opus sub-agent and a Codex sub-agent and see whether they
  agree it is worth the maintainer's attention — or whether they can agree on an
  answer between themselves. Escalate only if that vetting supports it. **Why:**
  this is the operational teeth on "drive authorized work to completion; do not
  over-ask" above. It converts a judgment call about interrupting into a cheap,
  checkable procedure instead of leaving it to one agent's self-calibration.
  **How to apply:** spawn both vetters in ONE message so they run concurrently;
  give each the SAME tightly-framed brief — the verified facts, the concrete
  options with their costs, and the standing rules that bear on it; require a
  YES/NO first word plus an explicit "no fourth option" rather than an invented
  one; have them answer independently, and tell them a genuine split is more
  useful than agreement. Keep driving the conforming default while they run —
  vetting is never a reason to idle. This authorizes the Agent tool for THAT
  purpose specifically; it is not blanket permission to delegate ordinary work.
  - *Worked example, which is what proved the rule.* The
    `retire-host-dispatch-cap` thread's factory dispatch of `bd-ib-vmve.2` was
    refused by the very `host_dispatch_cap` guard it was deleting: two runs from
    OTHER repos held a cap of 2 while eight Fabro scheduler slots sat idle, so
    this repo was refused with zero runs of its own in flight. The candidate
    escalation offered three options — wait for a drain, transiently commit a key
    the spec ratified minutes earlier forbids, or hand-build the deletion against
    the handoff's factory-only mandate. Both vetters independently returned
    NO-do-not-interrupt, take the wait, and no fourth option; both also
    independently confirmed the fail-open prohibition below. The wait was
    correct — capacity freed after 38 minutes and the dispatch went green.
  - *Known limitation: this protocol can silently degrade to one leg.* In this
    harness the Opus sub-agent channel returned THREE empty idle notifications
    before it eventually answered, and the failure mode is the dangerous kind —
    an idle notification carrying NO CONTENT reads as completion rather than as
    failure. A protocol requiring two opinions therefore has a quiet path to
    running on one without announcing it. Treat a missing answer as a MISSING
    ANSWER: count it as absent rather than as assent, say so explicitly, and
    state how many legs actually reported when you cite the vetting. Silence is
    not agreement. A direct follow-up request is worth making before writing a
    leg off — in this instance that is what finally produced the answer.
  - *A fourth option WAS constructed and rejected; do not reinvent it.* The
    strongest candidate was to bump the cap in an UNCOMMITTED `.livespec.jsonc`
    inside a throwaway worktree, which clears the spec's literal "committed
    configuration key" wording. It is rejected: it is the commit-the-key option
    with the evidence removed — the same minutes bought, but leaving no diff a
    reviewer could ever see. Satisfying a rule's letter by making the violation
    invisible is not compliance.
  - *General principle: never defeat a live check to get past it — and note that
    blinding a check is WORSE than the honest violation, not a milder version of
    it.* A gauge that FAILS OPEN when it cannot observe its input is a standing
    temptation: blinding the input (an unresolvable binary, a doctored `PATH`,
    anything that makes the observation fail) converts a refusal into a pass
    instantly. That is worse than openly taking the forbidden option because it
    MANUFACTURES A COUNTERFEIT ENVIRONMENTAL FAULT — the record then reads as a
    genuine incident, so the one artifact a reviewer would use to reconstruct why
    the work proceeded has been falsified. Committing a forbidden key is at least
    legible in a diff; blinding a gauge lies in the journal. This holds even when
    the check is the very thing you are authorized to delete: removing a guard by
    the sanctioned path and evading it by engineering its blind spot are not the
    same act. If a fail-open warning appears on a retry you did not engineer,
    STOP and report it rather than riding the fail-open through. (The instance
    that motivated this — the dispatch admission mutex's `fabro ps` gauge, which
    proceeded "on the capacity-slot gauge alone" when `ps` was unobservable — was
    deleted with that mutex by `bd-ib-vmve.2` in `0eeca13`. The principle is
    recorded because fail-open checks recur, not because that gauge still
    exists.)
- **Never label an option set as numbered tiers or levels; each enumeration
  value names what it IS** (maintainer-declared 2026-08-31). The
  `RepoIntegrationContract` conformance premises are the canonical instance:
  their mode enumeration is `no_op`, `shell_argv`, and
  `internal_livespec_dev_tooling` — never "tier 0/1/2" — and those names are
  used identically in the config discriminator, the dispatch-time warning,
  and every document that describes them. Any option that couples an adopter
  to livespec's internal dev-tooling MUST be labeled, on the surface that
  offers it, as introducing a dependency on livespec internal tooling that is
  UNSUPPORTED and may be unreliable. **Why:** a numbered tier carries no
  meaning to an adopter reading a dispatch warning, while a self-describing
  value tells them what they are choosing; and without the caveat the
  shared-package option reads as the recommended one when it is the one this
  fleet does not support for anyone else. **How to apply:** pick descriptive
  snake_case values for any adopter-facing enum, make the warning text
  enumerate them by name with one line each, and attach the unsupported caveat
  to every `internal_*` option. (Context: the conformance-premise fields were
  first drafted as "tiers"; the maintainer rejected the label and ruled the
  three names and the caveat while landing plan `bd-ib-vblnq2`.)
