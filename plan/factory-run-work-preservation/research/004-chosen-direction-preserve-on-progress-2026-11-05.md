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
     moved the run branch's head. The run then pushes that head to `refs/livespec/wip/<work-item-id>/<run-id>` on origin, as a
     forced update, before the next agent turn starts.
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
taken exactly as a seed from a needs-human ref, so it rides on bd-ib-lmwyfj's fix for seeds that carry an earlier run's checkpoint
commits.

**Accepted residual loss.** At most the node visit in progress when:

- a run is cancelled outside the Dispatcher;
- the Fabro server crashes;
- an operator runs `fabro rm`.

## 4. How the Red/Green node split shapes the design

The split has landed (bd-ib-yuwftp closed): red, then commit_red, then green, then implement_completion, then commit_green.

- **Push after every node visit that moved the head, not only after `commit_red` and `commit_green`.**
  - A refused `commit_red` re-enters `red`, possibly several times. Pushing only after commit steps could therefore lose several
    laps.
  - Pushing after every visit that moved the head caps the loss at one visit.
- **The step must leave local state untouched.** `commit_red` compares the tree against the dispatch base after folding the
  engine's checkpoint commits. So the step must not run the `git add` and `git commit` that `needs_human` does.
- **The forced update handles both rewrites:** the Green amend, and the rewind before a re-entered `red`.
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
