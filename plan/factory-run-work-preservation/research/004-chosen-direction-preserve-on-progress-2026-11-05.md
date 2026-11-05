# 004 — Chosen direction: preserve each node visit to a work-in-progress ref (2026-11-05)

Session: factory-run-work-preservation plan seat, 2026-11-05, attended. This note records the direction the maintainer chose. It
REPLACES the recommendation in note 003 §5 (the outbox mirror) and the option to turn on the engine's run-branch push.

## 1. The ruling

Maintainer, verbatim, 2026-11-05:

> I like this direction. It prioritizes simplicity. And I am fine accepting the loss of a single node if the entire server crashes
> or the run is cancelled.

Follow-up, verbatim:

> Yes, update everything in that direction, and then spin up two new reviewers again.

The ruling is recorded on epic `bd-ib-nckst7` as scope event `frwp-ruling-direction-2026-11-05`.

## 2. Why the engine push and the outbox mirror were dropped

Measured in the serving fork lineage `carrier-candidate-registered-20261023`:

- **Where and how the engine pushes.** The engine pushes from inside the sandbox workspace
  (`lib/components/fabro-petri/src/checkpoint.rs:239-262`, `:849-875`). Its refspec is `"{sha}:refs/heads/{branch}"`
  (`lib/apps/fabro-cli/src/commands/run/publish.rs`), with no `+`, so the push is **never forced**.
- **Our Red/Green flow rewrites the run branch on purpose.** `commit_green` amends the Red commit, and a re-entered `red` turn
  starts again from the dispatch base. With the engine push on, three things follow:
  - The checkpoint after `commit_red` publishes a lone Red commit.
  - Every push after the Green amend is non-fast-forward and is rejected. The engine only logs a warning and retries at the
    next checkpoint (`hooks.rs:706-716`).
  - Preservation therefore stalls silently at the Red commit for the rest of the run.
- **The outbox mirror inherits the same defect.** It receives the same non-forced engine push.
- **The outbox mirror also needs a lot of new infrastructure:**
  - a new git server on every factory host, reachable from Kubernetes pods;
  - Ansible or GitOps provisioning per host and per tenant;
  - a relay loop and a cleanup loop;
  - a fork change to aim the push at the mirror.
  - In addition, a mirror that holds no credential lets any sandbox overwrite another run's refs.
- **The credential argument in note 003 was real but secondary.** The engine hands the server's GitHub App token to `git` in the
  sandbox as `GIT_CONFIG_VALUE_0` (`lib/components/fabro-petri/src/source.rs:71-83`). Repository hooks are off for that push
  (`-c core.hooksPath=/dev/null`). Even so, an agent that writes `.git/config` (`http.proxy` plus `http.sslVerify=false`), or
  that leaves a process running as the same user that can read `/proc/<pid>/environ`, can still capture the token.
  - Today that adds little exposure, because agent stages still hold the token. bd-ib-w64kr3 and bd-ib-sgnfom will withdraw it,
    and preservation must not be built on what they remove.
- **Not found.** No record was found of the push being turned off because a Red commit reached origin. The only stated reason
  is the workflow comment "fabro/run/* never pollutes the remote" (commit `d49e76314`, 2026-06-11). Scope searched:
  - this repository's `.ai/`, `plan/`, `SPECIFICATION/` and git log;
  - ledger titles via `bd search`;
  - markdown and toml files under `/data/projects`.

## 3. The chosen design

Three parts. None changes Fabro or the fork; every part lives in this repository.

1. **Preserve step (progress leg).**
   - **When it runs.** A node visit of the implement-work-item workflow ends, whatever its outcome, and the engine's checkpoint
     moved the tip of the run branch `fabro/run/<run-id>`. Before the next agent turn starts, the run puts that tip on origin
     under `refs/livespec/wip/<work-item-id>/`.
   - **Which ref it writes.**
     - The first push creates `refs/livespec/wip/<work-item-id>/<run-id>`.
     - A later tip that descends from an existing work-in-progress ref of the run fast-forwards that ref.
     - A tip that descends from none of them, because the run branch was rewritten (an amend, a rebase), goes to a new sibling
       `refs/livespec/wip/<work-item-id>/<run-id>-<sha12>` and every existing ref stays where it is.
     - Nothing is ever forced, and no ref is moved to a commit that does not descend from it.
   - **What it pushes.** The run branch's tip, never the workspace `HEAD`, which a node such as `refresh_repair` can leave
     detached on another commit.
   - **What it never does:**
     - make a commit, or move `HEAD`, the index or the working tree;
     - run with repository hooks enabled;
     - fail the run when the push fails.
   - **Where it lives.** It is a command step (or a workflow run hook) in
     `.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro`, the same mechanism as today's `needs_human`
     preservation script. Its push tooling is Dispatcher-materialized and sits outside the working tree. The spec's
     credential-confinement clause is amended to name it, limited to its own ref.
2. **Preserve-then-destroy step (gate leg).**
   - **What it does.** Every Dispatcher cancel, run-record removal and sandbox delete goes through one step. That step:
     - performs the publications the spec already requires for that ending (Scenario 183, Scenario 306);
     - reads the run's work-in-progress ref;
     - writes the `livespec-preserved-tree` comment naming the newest preserving ref;
     - then destroys, even when nothing was preserved.
   - **What the receipt proves.** The comment names every work-in-progress ref of the run with its commit and marks the newest.
     It records ancestry, not only presence: a ref's presence on the forge is never by itself reported as the run's latest
     work, and a ref holding only the item's base commit is never named as preserving the run.
   - **What it does not do.** It adds no new read of a live sandbox, which removes the dependency on Fabro's `/runs/{id}/files`
     transport on Kubernetes. The work in progress that no ref carries is the loss the maintainer accepted.
   - **Enforcement.** The `fabro_port_seam` family of checks fails any Dispatcher module that destroys a run another way. This is
     the spec basis for `bd-ib-xdhe5z`.
3. **Retention.**
   - **The rule.** When the Dispatcher observes that an item is closed, it deletes the item's `refs/livespec/wip/<item>/*`,
     `refs/livespec/preserved-publish/<item>/*` and the `refs/heads/needs-human/<run-id>` refs of its runs.
   - **No age limit.** An item waiting on a human never loses its seed.
   - **Not in scope.** Refs whose item closed before the rule took effect stay where they are. Deleting today's 617 refs needs a
     separate maintainer go (scope-event deferral).

**Recovery (assertion 2).** Recovery routing counts the work-in-progress ref as the run's preserved work. A needs-human or
preserved-publish ref published at the same run's ending is preferred over it. A seed taken from the work-in-progress ref is
taken exactly as a seed from a needs-human ref, so it rides on whatever the current graph does with a seed that carries an earlier
run's checkpoint commits (bd-ib-lmwyfj fixed that for the split graph, which is being reverted).

**Accepted residual loss.** At most the node visit in progress when:

- a run is cancelled outside the Dispatcher;
- the Fabro server crashes;
- an operator runs `fabro rm`.

## 4. Two corrections from legacy-coordinator-agent (2026-11-05, at the maintainer's direction)

**A measured regression rules out the forced update this note first proposed.**

- At 06:20Z an interim preserve pass for bd-ib-rhivsm (run 01M6MHQE92Q4) force-pushed the workspace `HEAD`.
- `refresh_repair` had left that `HEAD` detached on master `df5df9c86`.
- Both preserve refs moved off the run's real tip, and the reviewed tree `63afe28e` (52 files of disposition, review_fix and
  settle checkpoints) was left on no origin ref.
- It was recovered only because the Dispatcher's launch clone still held the objects; it is restored to `86018f18`.
- `git ls-remote` had reported the wrong SHA as verified, because it proves presence, not that the SHA is the run's latest work.

Three guards follow, all now in section 3 and in the spec proposal:

- preserve the run branch tip, never a detached `HEAD`;
- never move a ref to a commit that does not descend from it, and write a SHA-suffixed sibling instead;
- the receipt records ancestry, not only presence.

The kubernetes-sandbox-backend session's interim `preserve_runs.sh` already does the first two and is the reference.

**The split red/green graph is being reverted.** The maintainer directed a revert of the v0.287.0 split (`e7f5ec757`,
bd-ib-yuwftp). The implement stage returns to the single `implement` node with its detached commit runner. The design is
unaffected, because the spec rule names no node: it fires on every node visit that moved the run branch tip, which covers
`implement`, `fix`, `review_fix`, the settle steps and `refresh_repair` alike. Three consequences:

- **One push per visit, not only after commit steps.** That still bounds the loss to one visit.
- **The step must leave local state untouched.** It must not run the `git add` and `git commit` that `needs_human` does.
- **Rewrites now open a sibling ref instead of being forced.** These are the amend inside `implement`, a `refresh_repair`
  rebase, and the Red-retry rewind if the split ever returns.
- **The push skips repository hooks.** The pre-push aggregate would run the full check suite. Its Red/Green replay check could
  also refuse checkpoint commits that change product files without TDD trailers.
- **The tooling must not be a script the repository carries.** `bd-ib-sdumcm` (P0, active) shows what happens otherwise: other
  tenants' runs die at `commit_red` with status 127.
- **A saved Red commit never enters the pull-request flow.** `ci.yml` triggers only on pull requests and pushes to `master`, and
  `refs/livespec/wip/*` is not a publish branch.

## 5. Where the requirements land

| Plan assertion | Carrier |
|---|---|
| 1 — every ending leaves the latest committed tree on a named ref, with its id on the ledger | preserve-step child; bd-ib-xdhe5z |
| 2 — a re-dispatch starts from the preserved tree | recovery-preference child; depends on bd-ib-lmwyfj |
| 3 — a check catches a destroy path that skips preservation | bd-ib-xdhe5z |
| 4 — preserved refs are removed by a stated retention rule | retention child |
| 5 — seven days after release, no run ending loses committed work | plan-level proof |
| 6 — best-practices research note, with the chosen direction recorded against it | plan-level proof (notes 003 and 004) |

**Spec basis.** Proposal `SPECIFICATION/proposed_changes/factory-run-work-preserved-on-progress.md`. Its four findings are
Scenarios 314 to 317, plus the credential-clause amendment.

**The three per-path fixes in flight stay under plan `bd-ib-acrr56` and become callers of the preserve-then-destroy step:**

- bd-ib-adcaa6 (cancel-for-restart);
- bd-ib-vraou4 (outside cancel);
- bd-ib-ds4yrm (wall-budget cancel).

## 6. Open design point for the reviewers

**Command node or run hook?** The preserve step could be either:

- **Explicit command nodes after each agent node of the graph.** The cost is that the agent's outcome conditions on its outgoing
  edges must move onto the new node.
- **One `stage_complete` run hook declared in `workflow.toml`.** It is simpler, but it is fail-open, and per note 003 §1 its
  firing on failed and cancelled visits is not established.

The spec text allows either. The implementing child decides, with a measurement.
