# Agent instructions

This file is the canonical agent-orientation surface for this repo;
`.claude/CLAUDE.md` is a symlink to it — never maintain a separate copy.
The sections through "Red-Green-Replay commit protocol" are the livespec
family-universal agent-instruction core (shared by every family member via
the impl-plugin template); repo-specific guidance is additive on top.

This file is the short core. Everything else lives in `.ai/` files, word for
word as it stood here before 2026-10-30, when the maintainer directed the split
(answer recorded on `livespec-dev-tooling-dfixhe`; plan epic `bd-ib-raqyki`).
Every agent session and factory node loads this file on every request, so keep
detail out of it: add a trigger line under "Progressive guidance" and put the
detail in `.ai/`.

## Repository mutation protocol

Every repo change uses a worktree → PR → merge → cleanup path. Treat leaving
dirty state, committing on the primary checkout, or asking the user whether to
commit as failures of the workflow, not as acceptable stopping points.

1. Confirm the primary checkout before editing:

   ```bash
   git config --get livespec.primaryPath
   git status --short --branch
   ```

2. If the change will modify tracked files, create a dedicated worktree from the
   primary checkout's `master` and do all edits there. Every worktree lives under
   the per-user root `~/.worktrees/<repo>/<branch>` — NEVER as a peer of the
   clones under `/data/projects`, so the workspace holds only first-class clones.
   Create it with the worktree-discipline pack's recipe, which adds the
   worktree under that root, provisions the gitignored pack into it, and
   runs the hydrate hook (run it from the primary checkout):

   ```bash
   mise exec -- just worktree-create <branch>
   ```

   A raw `mise exec -- git -C /data/projects/livespec-orchestrator-beads-fabro worktree add -b <branch>
   "$HOME/.worktrees/livespec-orchestrator-beads-fabro/<branch>" master` also yields a usable
   worktree — the pre-commit and pre-push hooks install the pack before
   any gate reads it, so the worktree can commit and push with no
   `just bootstrap` — but it skips hydration, so prefer the recipe.

   `just bootstrap` registers `~/.worktrees` as one of mise's
   `trusted_config_paths`, so a freshly created worktree's `.mise.toml` is
   auto-trusted and the first `mise exec` inside it never stalls on a "config not
   trusted" prompt.

3. Use `mise exec -- git commit ...` and `mise exec -- git push ...` so the
   mise-managed lefthook hooks actually run. Never pass `--no-verify`; if a hook
   fails, fix the cause or halt with the failure.
4. Open a PR, wait for required checks, and merge through the PR using the repo's
   rebase-merge discipline.
5. After merge, refresh the primary checkout to `origin/master`, remove the
   feature worktree, delete the local branch, and verify the primary checkout is
   clean on `master`.

Do not leave orphaned worktrees. If a session must stop before cleanup, record
the active worktree path, branch, PR, validation state, and next action in the
relevant handoff document.

## Agent prerequisites for plugin work

When investigating or changing anything related to the Claude Code plugin
installation, marketplace, or distribution, establish execution context FIRST —
do not assume how the system works:

1. Run `claude plugin marketplace list` to see which marketplaces are configured
   and whether they point to local files or remote repos. Changes to a local
   `marketplace.json` do NOT affect installs from a remote GitHub marketplace.
2. Trace where the actual install command fetches from (local vs remote) before
   changing anything, and verify your change affects that code path.
3. For remote marketplaces, push to GitHub then test; for local, use
   `/plugin marketplace add ./.claude-plugin/marketplace.json`. Never test local
   changes against a remote marketplace and assume they apply.

## Beads runtime prerequisites

This plugin's work-item store is a per-repo beads/Dolt TENANT on the shared
family dolt-server — NOT JSONL files. Installing the plugin does NOT provision
the backend; a clone connects to its tenant only when ALL of the following are
present:

- **`bd` CLI, pinned**, through the public lifecycle-guard entry point at
  `/usr/local/bin/bd`. This repo's mise config MUST NOT declare or install
  `bd`: an activated mise tool or regenerated shim can shadow that policy
  boundary. When `LIVESPEC_BD_PATH` is set it MUST point at
  `/usr/local/bin/bd`; otherwise `bd` on `PATH` MUST resolve there. Normal
  plugin, ledger, and operator calls MUST NOT invoke the guard's private
  delegate executable.
- **A running Dolt `sql-server`** reachable over **TCP `127.0.0.1:3307`**. Family
  tenants force TCP (not the unix socket); `.beads/config.yaml` carries `dolt.*`
  host/port keys with NO `socket` key.
- **The tenant password** in env as a single **bare `BEADS_DOLT_PASSWORD`** —
  injected by THIS project's configured env wrapper. A FAMILY tenant shares the
  one family password via the family 1Password Environment wrapper
  `with-livespec-env.sh` (canonical copy at
  `/data/projects/1password-env-wrapper/with-livespec-env.sh`); an INDEPENDENT
  (non-family) tenant injects its own tenant password from its own 1Password
  Environment via its own `with-<project>-env.sh` wrapper. Either way `bd`
  consumes the same bare var — there is NO per-tenant
  `BEADS_DOLT_PASSWORD_<tenant>` variable and NO per-tenant→bare mapping. Real
  isolation comes from the per-tenant SQL user + DB-scoped grant, not from
  password distinctness or wrapper identity. Secrets are probe-only — `printenv
  NAME | wc -c`, never echo values — and NEVER committed to `.livespec.jsonc` or
  `.beads/`.
- **The `.beads/` pointer files**: `config.yaml` (committed; the `dolt.*` server
  keys) and `metadata.json` (gitignored, regenerable). NEVER run `bd init` inside
  a primary checkout or worktree — it auto-commits and clobbers `.beads/`.

**NEVER install beads v1.2.0 or v1.2.1.** One invocation migrates a shared
tenant's schema and strands every client in the family. Before installing,
upgrading or probing a beads binary, or when a `bd` call reports `schema version
mismatch`, read `.ai/beads-v1-2-schema-hazard.md`.

Run `bd` from the target repository's root, under its env wrapper. The ledger's
traps each return a plausible wrong answer with exit 0, so read the file named
below when you see its trigger:

- `bd` reports `Access denied`, `Error 1045`, `no beads database found` or
  `(500) Internal Server Error`; `bd ready` or a `bd list` filter returns an
  empty or short set; a comment, metadata key or child seems missing →
  `.ai/beads-ledger-traps.md`.
- A dependency row's target reads `None`, or you need an item's blockers or
  parent → `.ai/beads-dependencies-and-projection.md`.
- A query, grep, search or probe returns zero or "not found", and that absence
  decides what you do next → `.ai/instrument-aim-traps.md`.
- You are about to design a fix, file or implement an item, write acceptance
  criteria, or write template syntax into a ledger comment →
  `.ai/work-item-authoring-traps.md`.
- A dispatch fails like a factory outage from a session that started days ago,
  or shared tooling is broken and a workaround is tempting →
  `.ai/stale-plugin-build-and-stop-the-line.md`.

## Daily commands

- `just bootstrap` — first-touch setup on a fresh clone; idempotently sets
  `livespec.primaryPath`, installs the canonical commit-refuse hook at
  `.git/hooks/pre-commit` + `.git/hooks/pre-push`, installs lefthook hooks, and
  resolves plugin dependencies.
- `just check` — the full enforcement aggregate (lint, types, tests, coverage,
  AST checks). It is the load-bearing safety net; it runs locally, in pre-push,
  and in CI.

## Revise co-edit discipline — `tests/heading-coverage.json`

Every revise pass that adds, changes, or removes a `## ` heading in any spec file
MUST update `tests/heading-coverage.json` in the same change (via the revise
`resulting_files[]` mechanism) so the heading-coverage map stays in lockstep with
the spec. Diff the proposed `## ` heading set against the current spec file's H2
set; add an entry (`test` MAY be the literal `"TODO"` with a non-empty `reason`)
for each new heading, and drop entries for removed headings.

## Red-Green-Replay commit protocol

Product `.py` changes are committed via a 2-step single-commit TDD ritual,
enforced by the `red_green_replay` commit-refuse hook (it inspects the staged
tree and writes `TDD-*` trailers). The final result is ONE commit carrying the
test, the impl, and both trailer sets.

1. **Red commit.** Stage the test file ALONE — no impl — and commit with a
   `fix:`/`feat:` subject. The hook runs pytest on the staged tree; the staged
   test MUST fail on pytest (non-zero exit). An `ImportError` or a collection
   error counts as a failure to the hook, BUT you SHOULD prefer a genuine
   assertion failure so Red proves the behavior is actually unimplemented
   rather than merely unimportable — see the new-module stub technique below.
   It records `TDD-Red-*` trailers (test path, failure reason, test-file
   checksum, output checksum, captured-at).
   - Gotcha: the impl must be UNMODIFIED on disk at the Red commit, because the
     hook's pytest reads the on-disk module. If the impl already carries the
     change the test passes, and the hook rejects with `test-passed-at-red`.
2. **Green amend.** Stage the impl and run `git commit --amend`. The hook sees
   the `TDD-Red-*` trailers + the staged impl, re-runs the SAME test (now
   passing), and records `TDD-Green-*` trailers. The test file bytes MUST be
   byte-identical across the Red→Green pair; to change the test, author a fresh
   Red commit.

### New-module stub technique (avoiding false reds)

When the impl module under test does NOT exist yet, the natural Red would be an
`ImportError` or a collection error rather than an assertion failure. The hook
accepts that as a failing Red, but it does not prove the behavior is
unimplemented — only that the module is unimportable. To make Red fail on a
genuine assertion instead:

1. At Red time, create the impl module as a minimal **stub** on disk — enough
   that the test imports and runs, but its assertion FAILS (e.g. a function
   that returns a wrong/sentinel value, or raises `NotImplementedError` only
   when that still yields an assertion failure rather than a collection error).
2. The stub must NOT make the test pass — a passing test at Red trips the
   hook's `test-passed-at-red` gate.
3. Then the **Green amend** replaces the stub with the real implementation that
   makes the assertion pass.

This keeps Red honest: it proves the behavior is unimplemented, not merely that
the module is missing.

### Execution gotchas

Three failure modes that cost dispatched agents real time:

1. **Multi-test-file Red.** The Red commit must stage EXACTLY ONE test file
   (zero impl). The commit-msg `red_green_replay` hook rejects more than one
   staged test file with `multi-test-file`, AND lefthook's pre-commit only takes
   the fast coverage-skip Red path when `test_count == 1 && impl_count == 0`
   (otherwise it runs full `just check` and fails at <100% coverage). When a
   change needs multiple new/changed test files, stage only ONE at Red (a genuine
   failing assertion), then add the remaining test files + the impl + ride-along
   docs at the Green `--amend`. (The old `LIVESPEC_PRECOMMIT_RED_MODE` env
   override is gone.)
2. **Preserve the Red trailer block at Green.** On the Green `git commit
   --amend`, do NOT pass a fresh `-m` that overwrites the message — that wipes the
   inline `TDD-Red-*` trailers the hook wrote at Red. For a commit that touches a
   PRODUCT-IMPL path, the pre-push *range* replay check greps the FINAL commit body
   for BOTH `TDD-Red-Test-File-Checksum:` AND `TDD-Green-Verified-At:`; if the Red
   block is gone, the push is rejected. Use `--amend --no-edit` (or re-include BOTH
   trailer blocks). The Red and Green test-file bytes must stay byte-identical.
   **SCOPE — do not read this clause as unconditional:**
   `red_green_replay._commit_violates` derives `product_paths` from the same
   `_IMPL_PREFIXES` tuple the commit-msg leg uses and returns early when that list
   is empty, so a commit touching NO product-impl `.py` is EXEMPT from the
   both-trailers requirement rather than passing it. A dangling Red block on such a
   commit is harmless. NEVER hand-forge a `TDD-Green-*` trailer to satisfy a check
   that cannot fire — read `_IMPL_PREFIXES` and confirm whether your paths are even
   in scope before concluding you are blocked.
3. **Working-tree gate, not just staged.** lefthook's pre-commit runs the
   structural / dev-tooling checks over the WORKING TREE, not only the staged set.
   So "revert only the impl for Red" is INSUFFICIENT when the change also ADDS
   files that a working-tree gate inspects (e.g. a new structural check that
   asserts certain dirs are absent, while you've already created those dirs on
   disk). At Red, make the WHOLE working tree master-consistent: move new
   untracked files aside (e.g. to scratch) and revert modified non-test files,
   leaving only the one staged test divergent; then restore everything for the
   Green `--amend`.

**Exempt:** changesets with no product `.py` (docs, spec, work-items, shell,
config) use `chore(...)` / `docs(...)` / `chore(spec):` subjects and skip the
ritual entirely. Always use `mise exec -- git ...` so the hooks fire; never
pass `--no-verify`.

## Progressive guidance (repo-additive)

Detail lives in `.ai/` files, read on demand (livespec core contracts §"Fleet
agent-instruction core"; `check-agents-ai-references-resolve` keeps every path
below valid). Each line names what you will SEE that should send you to its
file. When you see it, read the file before acting.

Factory, Fabro and dispatch:

- `fabro ps` shows no run, a run is `blocked`, a factory reports `ENOSPC`, or
  you are about to restart, build or route to a factory →
  `.ai/host-fabro-server.md`.
- You are about to check master CI or any other condition before invoking
  `drive` or `dispatcher.py` → `.ai/dispatcher-owned-admission-conditions.md`,
  then `.ai/master-ci-green-preflight.md`.
- A stage failed with `ACP turn failed` → `.ai/acp-turn-failed-triage.md`.
- `post-host-record` refuses as a self-replay, a publish branch survived a
  dispatch, or `drive` answers `invalid-action-id` →
  `.ai/proof-of-done-reclaim-and-action-id-traps.md`.
- You are about to take or replay a host-captured proof →
  `.ai/host-captured-proof-replay.md`.
- You are about to dispatch an item, or a dispatch ended badly →
  `.ai/factory-dispatch-preflight-and-triage.md`.
- The host PATH `fabro` fails to read a factory run →
  `.ai/fabro-dispatch-diagnosis.md`.
- An item's change lands in the Fabro fork → `.ai/fabro-fork-hand-build.md`.
- You are starting a canary, test campaign, local build or measurement,
  proposing an upstream Fabro change, or retracting a claim →
  `.ai/factory-working-method.md`.
- An item's tenant repository is not the repository its change lands in →
  `.ai/cross-tenant-execution-mirror.md`.
- You are designing anything that locks, fences or serializes ledger writers →
  `.ai/ledger-writers-are-multi-host.md`.

Plugins, sessions and hosts:

- You need to know which plugin build a session runs, remove a cache build, or
  reload plugins in your own pane → `.ai/plugin-cache-lease-and-rebind.md`.
- You are driving this repository from Codex or pi →
  `.ai/codex-dogfooding.md` or `.ai/pi-dogfooding.md`.
- You need a second agent session for a bounded job, or to message another
  session → `.ai/herdr-helper-sessions.md`.
- You are opening, moving or placing a herdr tab → `.ai/herdr-plan-tabs.md`.
- You are about to ssh to a factory host, or script with `ls`, `cat` or `grep`
  → `.ai/hosts-and-shell-gotchas.md`.
- You are about to deploy, run Ansible or `kubectl`, or change a fleet host →
  `.ai/gitops-deployment.md`.

Git, pull requests and plans:

- You are about to arm auto-merge, stage an `AGENTS.md` edit, survey `spec/*`
  branches, or touch `.github/workflows/` → `.ai/git-pr-and-release-mechanics.md`.
- You are opening a non-factory pull request that touches product `.py`, or
  running `reconcile-merged` or `accept` on an item built in a session →
  `.ai/local-implementation-close-path.md`.
- You are proposing a direction, filing a plan child, or starting a reviewer in
  a plan session → `.ai/plan-session-lessons.md`.
- You are about to archive a plan or close a plan epic →
  `.ai/plan-archive-completeness-gate.md`.
- You are driving a worker as supervisor → `.ai/supervisor-protocol.md`.
- You want the longer description of any file above →
  `.ai/progressive-guidance-index.md`.

## Decision authority — when to ask, proceed, or self-resolve

**Current repository configuration governs factory routing** (maintainer
clarification 2026-10-12). Respect its adapter, provider and model selections.
Do not override them, or change shared configuration to enforce a stale
coordination message or a session's provider preference. The only exception is
temporary testing of a specific model, isolated so it cannot change shared
configuration or affect overall factory operation. A provider named in an old
handoff is historical context, not authority to reroute a current dispatch.

**No test may depend on which model a factory node runs** (maintainer ruling
2026-10-18, after a second instance). `dispatcher.acp_nodes` is an operator
dial the maintainer turns to balance provider spend, so a test that reads it
turns a routing decision into a red build. The autouse fixture
`_no_test_reads_the_committed_acp_routing` in `tests/conftest.py` enforces
this: it replaces the committed `acp_nodes` table with a tripwire that fails
any test reading it. A test that needs a routing writes its own fixture
`.livespec.jsonc` naming the agent and model it is about. Never weaken or
bypass the tripwire to get a test green.

Fleet-standard guidance, ported from
`livespec/AGENTS.md` §"When to ask, proceed, or self-resolve". The default is
to decide and report, not to escalate.

**This repo already owned half of it.** The fleet's "Drive authorized work to
completion; do not over-ask" rule is maintainer-declared (2026-07-06) and
lives below in "Working with the maintainer (repo-additive)", among the other
maintainer-declared rules. It is deliberately NOT duplicated here — that
grouping is load-bearing, and a second copy would drift from the first. Read
it there; the bullets below are what this repo was missing.

- **A recorded next action is an instruction, not a menu.** When a handoff, a
  work-item, or a plan timeline names exactly one next action, take it.
  Re-presenting it as option 1 of a picker is a documented stall shape: on
  2026-08-20 a track sat roughly sixteen hours doing exactly that, alongside
  five self-decidable engineering calls escalated as standing maintainer
  questions.
- **Research before gating.** If a question is answerable by reading the code,
  the spec, the docs, or by testing on a live system, do that, decide,
  implement, and report for objection. Reserve gates for genuine product or
  values calls, irreversible or outward-facing actions, and secret or
  host-mutation authorization.
- **Only ask on genuine doubt, one thing at a time.** Self-resolve trivial
  wording fixes, internal-consistency repairs, and items clearly aligned with
  established preferences, presenting each with its disposition. When a gate is
  warranted, ask exactly one question per turn.
- **One investigation, one finding, one question.** When a focused
  investigation surfaces unrelated discrepancies, finish the original question
  first and surface only the load-bearing finding; log side observations
  briefly. Cosmetic drift never blocks on its own.
- **Prescribed destructive ops are pre-authorized.** When a destructive git
  operation is the codified mechanism of an adopted workflow — the
  `git commit --amend` of the Red→Green step, for instance — the adoption is
  the authorization. Keep per-instance gating for ad-hoc `--amend`,
  force-push, `reset --hard`, or `branch -D` on unmerged branches.
- **An unratified filter inside a check is conformance, not ratification.**
  Narrowing, excluding, or filtering inside an enforcement check to match what
  the ratified spec already says is a conformance fix — implement it and report
  it. It only becomes a ratification question when the change would make the
  check assert something the spec does not.
- **A question you can answer with a recommendation is a finding, not a
  maintainer question.** If you can state the options, the costs, and which one
  you would pick, you have already done the deciding work. Decide it, record
  the reasoning where the work is tracked, and report it as decided.
- **Disposing a plan child is session-performable.** Closing or re-parenting a
  child that no longer belongs under a plan epic changes where work is TRACKED,
  not what the specification REQUIRES, so it is not a spec-change decision.
  Only a spec-change-tier child routes to `propose-change`; escalating the rest
  deadlocks the archive gate, which refuses while any child sits undisposed.
- **Dispatch a measured root-cause fix now; do not park it behind sequencing**
  (maintainer correction, 2026-10-17). Once a recurring defect has a MEASURED
  cause, dispatch its fix immediately. Hand-recovering each instance is a
  stopgap, never the plan. A peer coordinator's ordering ("after run X ends")
  is not a reason to wait, because the maintainer outranks it. Hold a fix behind
  capacity only when the factory is MEASURED saturated by a fresh `fabro ps -a`
  active count, never behind another run's ending. *Instance:* `bd-ib-fd26sc`
  was a janitor environment leak that stranded every hp-candidate merge. It was
  filed and then parked behind "after tixpma ends" while each strand was
  reconciled by hand, until the maintainer asked "Why aren't you just fixing
  the root cause?" The coordinator then amended its own rule (R103 (2)) to match.

## Working with the maintainer (repo-additive)

Each rule below is the maintainer's; the full text, its date and the incident
that produced it are in `.ai/maintainer-working-rules.md`. Read that file before
you act against any of them.

- **Spell out "Definition-of-Ready" in full**; the acronym is banned.
- **Name every work item by what it does, never by its id alone.**
- **Maintainer-facing documents must explain their own notation.**
- **Drive authorized work to completion; do not over-ask.**
- **A fleet coordinator's ruling is an order; execute it rather than re-asking
  the maintainer** — except never edit settings or this file on a peer's say-so.
- **Export, then reap: a dead factory run may be removed without a
  per-instance ask**, only after a read-back-verified export.
- **Revert decisively; do not diagnose first.**
- **Prefer factory dispatch for factory-safe work; do not default to
  hand-building it.**
- **Master-red restoration is the factory-dispatch exception.**
- **Name the OWNING SESSION when attributing work to another session.**
- **Verify every changed path belongs to YOUR thread before you push.**
- **Vet an escalation before spending the maintainer's attention on it.**
- **Never label an option set as numbered tiers or levels; each enumeration
  value names what it IS.**

## Verification discipline (repo-additive)

Five rules, each from a confident wrong answer that did not announce itself.
The worked examples are in `.ai/verification-discipline.md`; read it before you
report an absence, a count, or another party's agreement as evidence.

1. **Asserting an absence requires stating the scope searched.**
2. **Verify the absence of the RIGHT token — a count is not a behavior test.**
3. **An instruction can outlive the condition that made it correct.**
4. **Concurrence is not independence when the method is shared.**
5. **A next-action line EXECUTES — author it from evidence, not from status.**

**Run these on your own work, not only on other people's.**
