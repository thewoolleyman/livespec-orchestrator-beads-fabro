# justfile — livespec-orchestrator-beads-fabro dev-tooling task runner.
#
# Generated from livespec/templates/impl-plugin/justfile.jinja at
# copier-copy time; re-sync via `copier update --vcs-ref=master` when livespec
# publishes a new release.
#
# Authority: livespec/SPECIFICATION/non-functional-requirements.md
#   §"Enforcement-suite invocation" — `just` is the canonical entry
#   point for every dev-tooling invocation. Lefthook and CI MUST
#   delegate to `just <target>`; direct tool invocations are banned
#   (enforced by livespec_dev_tooling.checks.no_direct_tool_invocation).
#
# Authority: livespec/SPECIFICATION/contracts.md
#   §"Pre-commit step ordering" — the gates wired here mirror the
#   spec-required ordering: 00-lint-autofix-staged, 01-commit-pairs-
#   source-and-test, 02-check-pre-commit at pre-commit;
#   no-commit-on-master + red-green-replay at commit-msg; full
#   aggregate at pre-push (PR gate ≡ master gate — the zero-.py
#   pre-push subset was retired; only the green-token clean-tree
#   skip remains).
#
# Authority: livespec/SPECIFICATION/contracts.md
#   §"Shared code sync — livespec-dev-tooling" (v094 wiring-
#   completeness invariant) — every canonical slug emitted by
#   `livespec_dev_tooling.canonical_checks` MUST be wired in this
#   `check:` aggregate in alphabetical order; livespec-orchestrator-beads-fabro-
#   private extras MAY follow after the canonical block. The in-repo
#   gate `check-aggregate-completeness` enforces this on every run.

# Default to listing targets when no recipe is invoked.
default:
    @just --list

# Golden-master acceptance harness. Kept outside `just check` so the fast
# aggregate remains the local/pre-push safety net while CI can expose this as a
# separate merge-gate status.
acceptance:
    uv run pytest acceptance -q

# Live Beads/Fabro tier entrypoints. These intentionally delegate to the
# existing production container proof and require the 1Password-provisioned
# operator env documented in orchestrator-image/tier2-dispatch-proof.sh.
acceptance-live-preflight:
    bash orchestrator-image/tier2-dispatch-proof.sh --preflight

[positional-arguments]
acceptance-live item:
    bash orchestrator-image/tier2-dispatch-proof.sh --run --item "$1"

# Fabro Enemy Unit Tests tier 0. Real Fabro dependency calls through the
# dispatcher FabroPort against the live host server, but no workflow run is
# launched. Kept outside `just check`; run under the operator environment when
# evaluating the pinned build or an upgrade candidate:
#   FABRO_EUT_BIN=/path/to/fabro just fabro-enemy-tier0
fabro-enemy-tier0:
    uv run pytest fabro-enemy-unit-tests/test_tier0_*.py -q

# Fabro Enemy Unit Tests tier 1. Launches real, intentionally tiny workflows
# against the configured Fabro server to assert terminal stop reasons, failed
# inspect payload shape, event stream liveness fields, and forced removal.
# This spends real runtime; run only when deliberately evaluating the pinned
# build or an upgrade candidate:
#   FABRO_EUT_BIN=/path/to/fabro just fabro-enemy-tier1
fabro-enemy-tier1:
    uv run pytest fabro-enemy-unit-tests/test_tier1_*.py -q

# Compare the tier-0 Enemy Unit Tests across two independently configured Fabro
# client/server pairs and write a Markdown delta artifact. Exits 0 only when both
# pytest legs exited 0 AND the rendered delta is empty, so this recipe may be
# gated on directly; a skip on one target is a delta, counted separately from a
# regression. Defaults compare the pinned pair against itself, which proves the
# artifact shape without requiring a candidate server:
#   just fabro-enemy-compare
# Candidate override example:
#   FABRO_EUT_CANDIDATE_BIN=/path/to/fabro \
#   FABRO_EUT_CANDIDATE_SERVER=http://127.0.0.1:32286 \
#   just fabro-enemy-compare
fabro-enemy-compare:
    uv run python fabro-enemy-unit-tests/compare.py

# Beads Enemy Unit Tests tier 0. Real `bd` reads/contracts against a candidate
# binary and an isolated store, no item mutation. The pure-contract assertions
# run always; the live-store assertions SKIP without BEADS_EUT_BIN. Kept outside
# `just check`. BEADS_EUT_CWD is a scratch client dir whose .beads/config.yaml
# routes bd auto-discovery at the isolated server (no family password):
#   BEADS_EUT_BIN=/path/to/bd BEADS_EUT_CWD=/scratch/client just beads-enemy-tier0
beads-enemy-tier0:
    uv run pytest beads-enemy-unit-tests/test_tier0_*.py -q

# Beads Enemy Unit Tests tier 1. Live create/update/close/dependency/comment
# round-trips, the two-step create normalization, assignee clearing, and the
# metadata compact-JSON round-trip -- all against a THROWAWAY isolated store.
# Mutates data; run only when deliberately evaluating a pinned or candidate bd
# binary against the isolated server:
#   BEADS_EUT_BIN=/path/to/bd BEADS_EUT_CWD=/scratch/client just beads-enemy-tier1
beads-enemy-tier1:
    uv run pytest beads-enemy-unit-tests/test_tier1_*.py -q

# Compare the tier-0 Beads Enemy Unit Tests across two independently configured
# bd binary/store pairs and write a Markdown delta artifact. Exits 0 only when
# both pytest legs exited 0 AND the rendered delta is empty, so this recipe may
# be gated on directly; a skip on one target is a delta, counted separately from
# a regression. The delta artifact IS the upgrade risk assessment:
#   BEADS_EUT_PINNED_BIN=/usr/local/bin/bd-real BEADS_EUT_PINNED_CWD=/scratch/pinned \
#   BEADS_EUT_CANDIDATE_BIN=/path/to/bd-candidate BEADS_EUT_CANDIDATE_CWD=/scratch/candidate \
#   just beads-enemy-compare
beads-enemy-compare:
    uv run python beads-enemy-unit-tests/compare.py

# W7 LIVE Beads/Fabro golden-master tier. The REAL end-to-end proof: creates a
# throwaway `livespec-e2e/livespec-e2e-*` repo, seeds it with the hello-world
# fixture SPECIFICATION + an embedded beads ledger carrying one ready greeting
# item, runs the production container/Fabro factory so Fabro implements + PRs +
# merges, clones the merged repo, asserts greet("Ada")=="Hello, Ada!", and
# deletes the repo (with reaper stale-sweep on entry, teardown on exit). Run
# under the 1Password wrapper:
#   with-livespec-env.sh -- just acceptance-live-golden-master -- --run
[positional-arguments]
acceptance-live-golden-master *ARGS:
    bash orchestrator-image/acceptance-live-golden-master.sh "$@"

# ---------------------------------------------------------------
# Worktree-discipline recipes (the Worktree Discipline Pack).
#
# The four `just worktree-{create,hydrate,land,reap}` lifecycle recipes are
# SINGLE-SOURCED from the livespec-dev-tooling package's canonical
# `worktree.just` fragment, installed into `dev-tooling/worktree.just` by
# `just install-worktree-pack` (run from `bootstrap` and CI) and IMPORTED
# here — so this repo no longer copies the recipe text into its own justfile.
# The recipes are ecosystem-neutral one-line pass-throughs onto the portable,
# ecosystem-neutral worktree core (dev-tooling/worktree-lib.sh), which they
# call DIRECTLY. The CORE is the single source of truth for the lifecycle
# (create / hydrate / land / reap) and the primary-vs-linked detection; the
# recipes carry NO logic of their own — they only forward arguments. `just`
# and `lefthook` are mandated non-functionally across the fleet + adopters
# (the Conformance Pattern: Installer = a `just` recipe; commit gate wired via
# `lefthook → just check`); they never enter livespec core's public functional
# surface or the /livespec:* skills. Where this repo's ecosystem (python) has a
# native tool, expose it as a STRICT PASS-THROUGH wrapper onto these recipes —
# never an alternative runner: e.g. rust `cargo xtask worktree create` →
# `just worktree-create`; javascript package.json
# `"wt:create": "just worktree-create"`. Keeping the logic in the core — not
# in any wrapper — is what stops ecosystems from drifting; the drift workflow
# + `copier update` exist to catch any divergence.
#
# Hydration is the python-profile specialization in
# dev-tooling/worktree-hydrate.sh, which the core's `create`/`hydrate` verbs
# invoke automatically.
#
# OPTIONAL import (`import?`, NOT plain `import`): `dev-tooling/worktree.just`
# is gitignored + installed (written by `install-worktree-pack`, never
# tracked-committed), so it is ABSENT in a fresh clone until `just bootstrap`
# runs. A plain `import` of a missing file makes `just` fail to parse the
# ENTIRE justfile — which would brick `just bootstrap` on a fresh clone. The
# optional `import?` silently no-ops while the file is absent (the worktree-*
# recipes simply aren't available until `install-worktree-pack` materializes
# the fragment) and resolves once installed.
# ---------------------------------------------------------------

import? 'dev-tooling/worktree.just'

# ---------------------------------------------------------------
# Server-side worktree discipline: GitHub branch protection.
#
# The local commit-refuse hook (the structural canonical body installed at
# .git/hooks from the shared livespec-dev-tooling package) blocks commits on the
# primary checkout, but it is LOCALLY BYPASSABLE (`--no-verify`, or simply never
# installed). Branch protection is
# the server-enforced backstop: the default branch advances only via PR/merge;
# direct + force pushes are rejected by GitHub itself.
#
# The two `protect-default-branch` (INSTALLER) and `check-branch-protection`
# (VERIFIER / "tripwire") recipes are SINGLE-SOURCED from the livespec-dev-tooling
# package's canonical `branch-protection.just` fragment, installed into
# `dev-tooling/branch-protection.just` by `just install-worktree-pack` (run from
# `bootstrap` and CI) and IMPORTED here — so this repo no longer copies the recipe
# text into its own justfile. Both recipes are ecosystem-neutral one-line
# pass-throughs onto the portable, ecosystem-neutral dev-tooling/branch-protection.sh
# (the single source of truth) — `just` is the mandated runner and the recipes
# carry no logic of their own, exactly like the worktree-* recipes above.
#
# `protect-default-branch` (the INSTALLER) establishes baseline protection on a
# fresh repo (requires an admin-scoped gh token); it is idempotent and
# non-weakening — it leaves an existing, possibly richer, protection untouched
# unless FORCE=1. `check-branch-protection` (the VERIFIER / "tripwire") asserts
# protection is present and is fail-closed, but capability-aware: it SKIPs with
# a NAMED notice when it cannot read protection (no gh / no admin token /
# non-GitHub origin) so it never makes `just check` flaky, and honours the
# LIVESPEC_BRANCH_PROTECTION_CHECK severity lever (fail [default] | warn | skip).
# The authoritative bite belongs to the Fleet-time conformance/orchestrator
# tier, where an admin token exists.
#
# OPTIONAL import (`import?`, NOT plain `import`): `dev-tooling/branch-protection.just`
# is gitignored + installed (written by `install-worktree-pack`, never
# tracked-committed), so it is ABSENT in a fresh clone until `just bootstrap`
# runs. A plain `import` of a missing file makes `just` fail to parse the
# ENTIRE justfile — which would brick `just bootstrap` on a fresh clone. The
# optional `import?` silently no-ops while the file is absent (the
# protect-default-branch / check-branch-protection recipes simply aren't
# available until `install-worktree-pack` materializes the fragment) and
# resolves once installed.
# ---------------------------------------------------------------

import? 'dev-tooling/branch-protection.just'

# ---------------------------------------------------------------
# First-time setup.
# ---------------------------------------------------------------

install-commit-refuse-hooks:
    # Install the STRUCTURAL commit-refuse hook at pre-commit, pre-push
    # AND commit-msg via the livespec-dev-tooling installer module —
    # the SINGLE canonical-body carrier (the body ships in the wheel as
    # `livespec_dev_tooling.install_commit_refuse_hooks.CANONICAL_HOOK_BODY`,
    # so there is no per-repo vendored `.sh` copy to drift). The installer
    # resolves `git rev-parse --git-common-dir` and writes all three hooks
    # into the primary's shared `.git/hooks/`. The installed body refuses
    # commits/pushes at a primary checkout STRUCTURALLY — it exits 1 when
    # `git rev-parse --git-dir` equals `git rev-parse --git-common-dir`
    # (a primary; a worktree's git-dir differs) UNLESS
    # `git config livespec.sandboxExempt` is `true` — so it is ARMED
    # ON INSTALL with no `livespec.primaryPath` arming step (which
    # failed OPEN whenever its arming step was missed). It derives its
    # hook name from `basename "$0"` and passes `"$@"` through to
    # `lefthook run <hook-name> "$@"`, so the commit-msg argv (the
    # message-file path the red-green-replay stage reads via `{1}`)
    # routes correctly. Per livespec/SPECIFICATION/
    # non-functional-requirements.md §"Primary-checkout commit-refuse
    # hook" / §"Commit-refuse hook bootstrap procedure" (family-wide
    # invariant).
    uv run python -m livespec_dev_tooling.install_commit_refuse_hooks

install-worktree-pack:
    # Install the canonical worktree-discipline PACK (worktree-lib.sh +
    # branch-protection.sh + the worktree.just / branch-protection.just
    # recipe fragments) by REUSING the shared livespec-dev-tooling
    # installer module — the SINGLE canonical source of all four bodies
    # (pinned in pyproject.toml). NOT a repo-vendored copy: there is
    # exactly ZERO drift-prone pack copy in this repo. This is the
    # Installer slot for the pack facet of the Worktree-discipline
    # concern, mirroring `install-commit-refuse-hooks` exactly: `bootstrap`
    # delegates to it, and CI runs it before the
    # `check-primary-checkout-commit-refuse-hook-installed` verifier so the
    # verifier VALIDATES the installed pack (byte-identical to the package
    # source) rather than skipping it. The installer writes the two shell
    # scripts into `dev-tooling/` with the executable bit and the two
    # `.just` fragments the root justfile `import?`s; all four are
    # gitignored (installed, not tracked), exactly as the commit-refuse
    # hooks are installed into the untracked `.git/hooks/` dir. Idempotent.
    uv run python -m livespec_dev_tooling.install_worktree_pack

# First-touch setup — a THIN delegator to the shipped LOCAL first-touch
# reconcile verb (`livespec_dev_tooling.fleet.local_reconcile`), the
# generalized successor to this recipe's former inline steps (livespec-zs22.8
# M5), PLUS the member-specific worktree-pack tail the verb does not cover.
# Reuse-first: NO copied logic — the verb walks the LOCAL obligation partition
# (`contract.LOCAL_OBLIGATION_ROWS`): mise trust/install, uv sync, the
# structural commit-refuse hooks (subsuming `lefthook install`), the advisory
# `refs/notes/*` refspec, the worktree-root mise-trust entry, the beads
# tenant-dir hardening, the beads-runtime detect-and-guide probes, and
# project-scoped Claude/Codex plugin registration via THIS repo's own
# `ensure-plugins` / `ensure-codex-plugins` recipes. The verb resolves the
# target checkout worktree-safely via `git rev-parse --git-common-dir`. The
# TAIL below installs the worktree-discipline pack (worktree-lib.sh +
# branch-protection.sh + the `.just` recipe fragments) and keeps the tracked
# worktree-hydrate.sh executable — neither is a verb obligation row, so both
# MUST survive the rewire. The verb's uv-sync row precedes the tail's `uv run`,
# so the venv is ready.
bootstrap:
    bash dev-tooling/just-bootstrap.sh

# The standard shared derive-from-settings wrapper: reads the committed
# `.claude/settings.json` (`extraKnownMarketplaces` incl. ref, `enabledPlugins`)
# at runtime and issues the marketplace add / install / update commands for
# exactly what it finds — one source of truth, recipe-content drift structurally
# impossible. Registers this repo's full project-scope Claude plugin set
# (livespec core, the Claude Driver, and this orchestrator plugin) so the
# spec-side surface is present.
ensure-plugins:
    mise exec -- uv run --no-sync python -m livespec_dev_tooling.fleet.ensure_plugins

# Idempotent host-wide Codex plugin provisioning. Codex does not support
# project-scoped plugin enablement, so these registrations intentionally land in
# the user's default CODEX_HOME and are visible to every repo on the host. Codex
# is an optional dogfooding runtime; bootstrap skips this target when the CLI is
# absent but fails on real install errors when Codex is present.
ensure-codex-plugins:
    bash dev-tooling/just-ensure-codex-plugins.sh

[positional-arguments]
refresh-codex-full-access-marker manifest='.livespec-fleet-manifest.jsonc':
    uv run python3 .claude-plugin/hooks/codex_yolo_gate.py refresh "$1"

# factory-bypass-audit — REPORT-ONLY, on-demand attention surface. Surfaces
# recently-merged PRs that changed product `.py` without going through the
# factory GitHub App (an in-session factory bypass). Network-using (`gh`), so
# it is DELIBERATELY kept OUT of the `check:` aggregate and every hook; it
# exits 0 regardless of findings. Empirical signal for the force-factory
# decision (plan/force-factory/findings.md; epic bd-ib-y2xro4, work-item
# bd-ib-c4a2bi). Pass flags through, e.g.
#   just factory-bypass-audit --limit 50 --json
[positional-arguments]
factory-bypass-audit *args:
    uv run python3 .claude-plugin/scripts/bin/factory_bypass_audit.py "$@"

# ---------------------------------------------------------------
# Aggregate check — canonical full-set stamped at copier-copy time.
#
# The `targets=(...)` array below is Jinja-rendered from the committed
# copier-template DATA file `canonical-slugs.yml`, which is a
# release-time projection of
# `livespec_dev_tooling.canonical_checks.canonical_check_slugs()` (the
# single source of truth) regenerated in livespec via
# `just stamp-canonical-slugs`. The block is Jinja-included from that
# data file and line-parsed below — import-free, so it renders
# correctly on BOTH the smoke-check flow AND the consumer
# `copier update` flow (copier clones the template to an ephemeral
# checkout with no PYTHONPATH injection, where a render-time copier
# jinja-extension importing the dev-tooling module cannot resolve).
# Per livespec/SPECIFICATION/contracts.md
# §"Shared code sync — livespec-dev-tooling" → Template gate, every
# newly-generated `livespec-impl-*` sibling inherits the full canonical
# aggregate from inception; existing siblings see canonical-set growth
# as a real reviewable diff on `copier update` (3-way merge surfaces
# canonical drift).
#
# The data file resolves at the Jinja loader root, which differs
# between the two flows (smoke-check flow: loader root is
# templates/impl-plugin/; consumer flow: loader root is the repo/clone
# root, with _subdirectory routing). A Jinja list-include tries
# "canonical-slugs.yml" then "templates/impl-plugin/canonical-slugs.yml"
# and uses the first that exists, so one physical data file serves both
# flows import-free.
#
# Slugs are stamped in alphabetical order (sorted at the source). DO
# NOT hand-edit this list — extend the canonical set by adding
# `livespec_dev_tooling/checks/<name>.py` in the dev-tooling sibling
# repo, re-run `just stamp-canonical-slugs` in livespec, cut a template
# release, then re-run `copier update --vcs-ref=master` here.
# ---------------------------------------------------------------

# Deliberately omit errexit so the aggregate reports every failing target before exiting non-zero.
check:
    #!/usr/bin/env bash
    set -uo pipefail
    : <<'LIVESPEC_AGGREGATE_TARGETS'
    targets=(
        check-agents-ai-references-resolve
        check-aggregate-completeness
        check-all-declared
        check-assert-never-exhaustiveness
        check-branch-protection-alignment
        check-canonical-recipe-fidelity
        check-check-coverage-incremental
        check-check-mutation
        check-check-tools
        check-ci-gate-parity
        check-ci-matrix-completeness
        check-claude-md-coverage
        check-comment-line-anchors
        check-commit-pairs-source-and-test
        check-file-lloc
        check-fleet-marketplace-relative-sources
        check-global-writes
        check-handoff-dispatch-routing
        check-heading-coverage
        check-hook-trees-not-io-exempt
        check-keyword-only-args
        check-local-memory-drift-audit
        check-main-guard
        check-master-ci-green
        check-match-keyword-only
        check-newtype-domain-primitives
        check-no-direct-destructive-cli
        check-no-direct-tool-invocation
        check-no-except-outside-io
        check-no-fmt-directives
        check-no-inheritance
        check-no-lloc-soft-warnings
        check-no-raise-outside-io
        check-no-shadow-ledger-body-identical
        check-no-shadow-ledger-body-typechecks
        check-no-todo-registry
        check-no-write-direct
        check-partition-completeness
        check-pbt-coverage-pure-modules
        check-per-file-coverage
        check-plan-anchor-declared
        check-plan-epic-parity
        check-plan-no-tombstone
        check-plan-record-conformance
        check-plugin-resolution
        check-primary-checkout-commit-refuse-hook-installed
        check-private-calls
        check-public-api-result-typed
        check-red-green-replay
        check-required-role-keys-declared
        check-rop-pipeline-shape
        check-self-hosted-routing
        check-self-hosted-uv-lane
        check-shell-quality
        check-skill-invocation-paths
        check-source-trees-scoped-to-consumer
        check-supervisor-discipline
        check-tests-mirror-pairing
        check-tests-no-subprocess-spawn
        check-tool-backed-check-completeness
        check-vendor-manifest
        check-work-item-interpolation-delimiters
        check-work-item-status-vocabulary
        check-wrapper-shape
        check-format
        check-lint
        check-types
        check-coverage
        check-work-item-merge-evidence
        check-work-item-state-invariants
        check-status-conformance
        check-closed-item-integrity
        check-needs-attention-surface-ownership
        check-spec-id-presence-discipline
        check-no-fleet-toolchain-literals
        check-codex-plugin-structure
        check-pi-plugin-structure
        check-bd-guard
        check-codex-skill-picker
        check-no-fleet-pat-dispatch-surface
        check-spec-governance-default-block
        check-seam-equivalence
        check-ci-wires-repo-local-gates
        check-no-workflow-edits
        check-fresh-clone-setup
        check-doctor-static
    )
    LIVESPEC_AGGREGATE_TARGETS
    bash dev-tooling/just-check.sh

[positional-arguments]
check-skipping *skip_targets:
    bash dev-tooling/just-check.sh "$@"

# ---------------------------------------------------------------
# Tool-backed checks (livespec-impl-beads-private).
# ---------------------------------------------------------------

check-lint:
    uv run ruff check .

check-format:
    uv run ruff format --check .

check-types:
    uv run pyright

# `check-static` — fastest-first fail-fast helper for fast agent/dev
# feedback (work-item livespec-dev-tooling-7us.8). Runs ONLY the cheap
# static checks — `ruff format --check .`, `ruff check .`, `pyright`
# (i.e. check-format, check-lint, check-types) — as a fail-fast
# sequence: it STOPS at the first failing check and exits non-zero, so
# a sub-2s ruff/pyright failure surfaces immediately instead of after
# `just check`'s slow pytest+coverage tail. This is a developer/agent
# convenience like the helper recipes above; it is deliberately NOT a
# member of the `check:` aggregate `targets=(...)` array, NOT a
# canonical slug (no livespec_dev_tooling/checks/ module), and NOT in
# the CI matrix. The authoritative full gate remains `just check`
# (still run at pre-push and in CI) — `check-static` is a fast
# pre-flight, never a replacement for it.
check-static:
    bash dev-tooling/just-check-static.sh

# `changed-files` — print the changed `.py` set this branch touches,
# repo-root-relative, one path per line, sorted + de-duplicated
# (work-item livespec-dev-tooling-7us.9). The set is the UNION of two
# git views, so an agent gets the live working set whether or not it has
# committed yet:
#   - `git diff --name-only origin/master...HEAD` — every `.py` this
#     branch's commits changed vs the merge-base with origin/master;
#   - `git diff --cached --name-only --diff-filter=AM` — added/modified
#     `.py` currently staged but not yet committed.
# This is the exact set `check-changed` consumes for its scoped gate.
# Helper recipe (like `check-static`): NOT a member of the `check:`
# aggregate `targets=(...)` array, NOT a canonical slug, NOT in the CI
# matrix.
changed-files:
    bash dev-tooling/just-changed-files.sh

# `check-changed` — modified-files INNER-LOOP gate for fast scoped
# feedback during iteration (work-item livespec-dev-tooling-7us.9). Feeds
# the `changed-files` set into `check-check-coverage-incremental --paths
# <set>`, which already (a) resolves each changed impl `.py` to its
# mirror-paired test and runs that pytest SUBSET, and (b) applies the
# path-scoped per-file coverage gate — i.e. it composes the existing
# scoping plumbing rather than re-deriving it. An empty changed set is a
# no-op (exit 0): nothing changed, nothing to gate.
#
# SCOPE — INNER-LOOP SPEEDUP ONLY, NOT a replacement for the final gate.
# It runs only the test subset + path-scopable checks for the files this
# branch touched, so an agent gets sub-suite feedback while iterating. The
# AUTHORITATIVE gate remains `just check`, which runs the FULL suite + the
# full AST scans + the aggregate 100% coverage gate at pre-push and in CI.
# Like `check-static`, this is a developer/agent convenience: NOT a member
# of the `check:` aggregate `targets=(...)` array, NOT a canonical slug,
# and NOT in the CI matrix.
check-changed:
    bash dev-tooling/just-check-changed.sh

# Aggregate (total) coverage gate at `fail_under = 100` (pyproject.toml
# [tool.coverage.report]). Wired as a LITERAL member of the `check:`
# targets array (private block) AND the CI check-python matrix; the
# check-tool-backed-check-completeness meta-check (dev-tooling v0.8.0)
# enforces that both-surfaces wiring. To avoid a DUPLICATE full pytest
# run when invoked inside `just check`, this recipe gates off the
# EXISTING `.coverage` data file when present — the canonical
# check-per-file-coverage slug runs `pytest --cov` upfront and sorts
# alphabetically BEFORE this private extra, so `.coverage` already
# exists by the time this runs locally. When `.coverage` is ABSENT —
# the CI check-python matrix runs check-coverage as a standalone job in
# its own runner with no prior pytest — the recipe runs the suite
# itself so the aggregate gate still fires there. In Red-mode pre-commit
# this target is omitted by `check-pre-commit` via the `just skip=...`
# argument (coverage is verified at the Green amend), so no ambient
# env-var read is needed here (epic li-cvaudit, cvredmd). Mirrors
# dev-tooling's coverage-reuse recipe.
check-coverage:
    bash dev-tooling/just-check-coverage.sh

# Beads-private merge-evidence static check (R7; SPECIFICATION/contracts.md
# §"`work_item_merge_evidence` static check"). Walks every materialized
# work-item from the store descriptor, reading the AuditRecord from each
# closed issue's `metadata` column through the same beads client the runtime
# uses. In the hermetic default tier (LIVESPEC_BEADS_FAKE) the tenant is
# empty, so the walk yields nothing and the check passes trivially; the
# git-reachability rules (cat-file / merge-base --is-ancestor) and the
# epics-exempt rule match the plaintext sibling's JSONL-shaped equivalent.
# This is an impl-beads-private check (NOT a canonical livespec-dev-tooling
# slug), so it is wired here in the private block after the canonical set.
# Runs in the hermetic FAKE tier (LIVESPEC_BEADS_FAKE=1) so `just check`
# never requires a live `bd` / dolt-server: the fake tenant is empty, the
# walk yields nothing, and the check passes trivially. A live-tier audit of
# real closures runs out-of-band with the connection env configured.
check-work-item-merge-evidence:
    LIVESPEC_BEADS_FAKE=1 uv run python dev-tooling/checks/work_item_merge_evidence.py

# `check-work-item-state-invariants` — beads-private work-item-state doctor
# check (SPECIFICATION/contracts.md §"Work-item beads-issue mapping" invariants
# block; L1a slice S6). Walks every materialized work-item and applies the
# fail-soft non-sentinel-`rank` + rank-key-length WARNINGS (advisory, exit 0)
# for live heads plus the hard `active ⟹ assignee` and stored
# `blocked ⟹ blocked_reason ∈ {needs-human, infra-external}` ERRORS (exit
# non-zero). Like the merge-evidence sibling, the aggregate run forces the
# hermetic empty tenant (LIVESPEC_BEADS_FAKE=1), so this never requires a live
# bd / dolt-server: the fake tenant is empty, the walk yields nothing, and the
# check passes trivially. A live-tier audit of real heads runs out-of-band with
# the connection env configured. Not a canonical livespec-dev-tooling slug, so
# it is wired in the private block.
check-work-item-state-invariants:
    LIVESPEC_BEADS_FAKE=1 uv run python dev-tooling/checks/work_item_state_invariants.py

# `check-status-conformance` — beads-private status-conformance doctor check
# (bd-ib-2wq). Wires the Dispatcher's `status-conformance` Ledger invariant
# (commands/_dispatcher_ledger_checks.py) into `just check` / `/livespec:doctor`
# so it fires from the aggregate, not only at dispatch time. FAILS (exit 1) when
# any LIVE (non-done) work-item's stored beads status is outside
# ALLOWED_BEADS_STATUSES — the 7-state lifecycle projected through the adapter's
# done→closed rename, DERIVED from the WorkItemStatus Literal (never hand-typed),
# naming the offending id(s) + status. Like the state-invariants sibling, the
# aggregate run forces the hermetic empty tenant (LIVESPEC_BEADS_FAKE=1), so it
# never requires a live bd / dolt-server: the fake tenant is empty, the walk
# yields nothing, and the check passes trivially. A live-tier audit of real heads
# runs out-of-band with the connection env configured. Not a canonical slug, so
# it is wired in the private block.
check-status-conformance:
    LIVESPEC_BEADS_FAKE=1 uv run python dev-tooling/checks/status_conformance.py

# `check-ledger-conformance-live` — ALWAYS-RUN pre-push tenant-conformance
# gate (PROTOTYPE for fleet-wide rollout on the ledger-status-conformance
# thread). Unlike `check-status-conformance` (the FAKE-mode aggregate member,
# which runs an empty hermetic tenant and passes trivially), THIS recipe reads
# the repo's REAL beads tenant LIVE and AUTO-HEALS it. Tenant state is not
# tree-derived, so this is deliberately wired as a SECOND, standalone lefthook
# pre-push command (never a `just check` aggregate member and never subject to
# the pre-push green-token / doc-only skips).
#
# AUTO-HEAL-LOUD. Under the credential wrapper, `ledger-normalize --gate` heals
# the two definitionally-safe beads-native transient statuses IN PLACE (open ->
# backlog, in_progress -> active) and PRINTS every remap it writes. A push CAN
# therefore mutate the tenant — but only via these two safe remaps and never
# silently. This removes the cross-session friction of blocking one session on
# another session's fresh transient item on a shared tenant.
#
# FAIL-SOFT BY CONSTRUCTION — the top correctness requirement. Because it runs
# on EVERY push, a false-fail would brick all pushes to the repo. It therefore
# BLOCKS a push (exit 1) ONLY when the gate positively CONFIRMS a RESIDUAL
# out-of-lifecycle work-item that no safe remap can heal — i.e. `ledger-normalize
# --gate` exits 1 AND its machine-checkable `LIVESPEC_LEDGER_GATE: DRIFT` stdout
# marker is present. EVERY other outcome — conformant, healed-in-place,
# could-not-check (creds unavailable / 1Password locked / Dolt unreachable /
# unparseable output / missing tenant config / a heal write that raised an
# expected beads error), or even an unhandled crash — SKIPS with exit 0. The
# exit-code contract of `ledger-normalize --gate` is: 0 = conformant or healed,
# 1 = residual drift, 2 = could-not-check; this recipe maps (1 && DRIFT marker)
# -> block and maps EVERYTHING else -> fail-soft skip.
check-ledger-conformance-live:
    bash dev-tooling/just-check-ledger-conformance-live.sh

# `check-closed-item-integrity` — beads-private closed-item-integrity static
# check (SPECIFICATION/contracts.md §"Closed-item-integrity check"). Enumerates
# every closed gap-tied work-item from the store, resolves each item's gap-id
# to an acceptance scenario via the clauses[] gap-id->scenario map in
# tests/heading-coverage.json, and flags any "closed but unproven" item (a
# TODO-bound or unresolvable acceptance scenario, or a missing
# resolution:completed label). ALWAYS-WIRED + ALWAYS-RUNNING; the
# LIVESPEC_CLOSED_ITEM_INTEGRITY lever (default warn → exit 0, advisory; fail →
# exit non-zero) is the SEVERITY switch only, never a wiring carve-out. Like the
# merge-evidence sibling, the aggregate run forces the hermetic empty tenant
# (LIVESPEC_BEADS_FAKE=1), so this never requires a live bd / dolt-server: the
# fake tenant is empty, the enumeration yields nothing, and the check passes
# trivially. A live-tier audit of real closures runs out-of-band with the
# connection env configured.
check-closed-item-integrity:
    LIVESPEC_BEADS_FAKE=1 uv run python dev-tooling/checks/closed_item_integrity.py

# `check-needs-attention-surface-ownership` — v079 ownership-boundary guard.
# Scans only `commands/needs_attention.py` and `commands/_needs_attention*.py`
# for executable overseer/foreman references, while leaving docstring prose and
# plan-lane modules out of scope. Not a canonical slug, so it is wired in the
# private block.
check-needs-attention-surface-ownership:
    uv run python dev-tooling/checks/needs_attention_surface_ownership.py

# `check-spec-id-presence-discipline` — executable guard for the narrowing that
# four consumers of the OVERLOADED spec id field each got wrong. AST-scans the
# orchestrator package for a bare presence / truthiness test on
# `spec_commitment_hint` / `spec_id` and fails unless the site is in the
# measured allowlist; everything else must ask `is_spec_commitment` or
# `is_plan_anchor`. Because it reports an absence, it refuses to report a clean
# scan unless its discovery and matcher positive controls both hold. Pure AST
# read of committed files: no beads, no store, no network. Not a canonical
# livespec-dev-tooling slug, so it is wired in the private block.
check-spec-id-presence-discipline:
    uv run python dev-tooling/checks/spec_id_presence_discipline.py

# `check-no-fleet-toolchain-literals` — SPECIFICATION/constraints.md
# §"Fleet-toolchain literal ban". Fails on any fleet-toolchain literal (`mise`, a
# fleet `just` recipe name, `lefthook`, `livespec_dev_tooling`,
# `livespec-step-timer`, or a bare default-branch name used as a ref) in the
# dispatcher package outside the single fleet-defaults module the
# `RepoIntegrationContract` schema designates, so a new hardcoded premise cannot
# be reintroduced by a later change. The package scan is AST-based, so comments,
# docstrings and `__all__` symbol lists are out of scope; the workflow payload
# and the prompt files are allow-listed pending their conversion by carrier
# C5-payload, which deletes that list. A STALE allow-list entry fails too, which
# is what makes the deletion mechanical. Because it reports an absence, it
# refuses to report a clean scan unless its discovery, designation and matcher
# positive controls all hold. Pure AST/text read of committed files: no beads, no
# store, no network. Not a canonical livespec-dev-tooling slug, so it is wired in
# the private block.
check-no-fleet-toolchain-literals:
    uv run python dev-tooling/checks/no_fleet_toolchain_literals.py

# `check-bd-guard` — lint + hermetically test the warn-first `bd` guard wrapper
# (bd-guard/), the stopgap that fronts every `bd` call and warns/blocks the
# explicit non-lifecycle ops (`update --status <non-lifecycle>`, `update
# --claim`). Pure shell: no beads / no store / no product .py, so it runs in any
# tier with no live bd / dolt-server. shellcheck runs when present; when absent
# it is a loud WARNING, not a silent skip (a severity lever — a minimal runner
# may lack shellcheck), while the hermetic harness is the hard gate and always
# runs. Not a canonical livespec-dev-tooling slug, so it is wired in the
# private block.
check-bd-guard:
    bash dev-tooling/just-check-bd-guard.sh

# `check-bd-guard-candidate` — explicit Beads v1.2.2 qualification leg. It
# downloads the official Linux amd64 release into a temporary directory, verifies
# upstream and derived hashes, then runs the tracked guard with LIVESPEC_BD_REAL
# pointed at that temporary binary. All repositories, config, and Dolt data are
# temporary; it never installs or copies a host binary.
check-bd-guard-candidate:
    bash bd-guard/test/run-v1-1-2-candidate-tests.sh

# `check-codex-plugin-structure` — Codex cross-runtime structural check (P3).
# Validates the orchestrator plugin's Codex surface (per
# livespec/SPECIFICATION/constraints.md §"Codex support"): the repo-root
# .agents/plugins/marketplace.json catalog, the nested
# .claude-plugin/.codex-plugin/plugin.json manifest (name; version in lockstep
# with the Claude plugin.json; skills path; description SoT; NO `hooks` key),
# and the seven present .codex-plugin/skills/<op>/SKILL.md bindings (frontmatter
# name==dir, non-empty description, NO allowed-tools; body carries the $PLUGIN_ROOT
# resolution block + the codex-plugin-list snippet and no live ${CLAUDE_PLUGIN_ROOT}
# token; the four wrapper-backed thin ops self-invoke scripts/bin/<op>.py, the
# three prose-backed capture ops read prose/<op>.md instead). The two remaining
# heavyweight ops (implement, groom) are asserted ABSENT pending their own
# prose extraction. Pure-filesystem (no beads / no store), so it runs in any tier
# with no live bd / dolt-server.
# It also ENFORCES the no-Codex-hooks contract (no `.codex-plugin/hooks/` dir).
# Not a canonical livespec-dev-tooling slug, so it is wired in the private block.
check-codex-plugin-structure:
    uv run python dev-tooling/checks/codex_plugin_structure.py

# `check-pi-plugin-structure` — pi cross-runtime structural check. Validates the
# orchestrator plugin's pi surface (per SPECIFICATION/contracts.md §"pi skill
# surface"): the repo-root package.json pi manifest (name; pi-package keyword;
# pi.skills naming the bindings tree; NO pi.extensions), the one shared
# plugin-root resolver, and one thin
# .claude-plugin/.pi-plugin/skills/livespec-orchestrator-beads-fabro-<op>/SKILL.md
# binding per operation the plugin ships. Both the operation set and each
# operation's backing are DERIVED from the tree rather than enumerated, so the
# check cannot fall out of lockstep with the shipped surface. Pure-filesystem
# (no beads / no store), so it runs in any tier with no live bd / dolt-server.
# Not a canonical livespec-dev-tooling slug, so it is wired in the private block.
check-pi-plugin-structure:
    uv run python dev-tooling/checks/pi_plugin_structure.py

# `check-spec-governance-default-block` — consumer-side guard for the commented
# spec_governance defaults block in `.livespec.jsonc`. The implementation lives
# in livespec-runtime so consumers validate against the current shared manifest,
# not a copied or justfile-pinned checker.
check-spec-governance-default-block:
    uv run python dev-tooling/check-spec-governance-default-block.py

# `check-seam-equivalence` — the CI half of SPECIFICATION/contracts.md
# §"Repository integration contract", clause "Typed workflow inputs and the
# seam-equivalence check". Asserts, over the committed `implement-work-item`
# payload, that the set of integration `inputs.*` tokens the workflow
# references equals the set the Dispatcher renders from the
# ResolvedIntegrationContract in BOTH directions, that both agree with the
# schema's projectable fields, and that every such token sits in a position the
# pinned fabro build actually expands — a templated duration attribute leaves
# the node with no timeout and reports nothing, so the question is answered
# statically rather than by a production dispatch. Scoped to the integration
# subset: the six ACP adapter inputs and the two review/cap policy inputs are
# excluded, and that exclusion is itself checked for disjointness and coverage.
# Pure-filesystem (no beads / no store / no network).
check-seam-equivalence:
    uv run python dev-tooling/checks/seam_equivalence.py

# The two repo-local integration gates above are ratified as running in CI
# and on pre-push, but ci.yml enumerates its batches by hand and a
# payload-only push takes the doc-only pre-push path; this guard fails when
# either gate (or the guard itself) is absent from the CI metadata batch or
# the doc-only target list. Pure-filesystem.
check-ci-wires-repo-local-gates:
    uv run python dev-tooling/checks/ci_wires_repo_local_gates.py

# livespec core's doctor STATIC phase (reference-discipline + out-of-band
# invariants) against THIS repo's SPECIFICATION/ tree, wired fleet-wide per
# livespec epic livespec-6jfq. core ships the checker: doctor_static.py is
# self-contained (vendored deps + bare python3), so it runs under plain
# python3 and NEVER `uv run`. Resolve core's plugin root via
# LIVESPEC_CORE_PLUGIN_ROOT (CI sets it to a livespec checkout at this repo's
# .livespec.jsonc compat.pinned tag) → else the installed livespec@livespec
# plugin cache (local dev). The two reference-discipline checks
# (no-cross-spec-reference, no-spec-section-citation-in-code) are pure reads;
# doctor-out-of-band-edits is self-healing — on a drifted tree it writes a
# history backfill into the worktree and fails, and committing that backfill
# heals the track; on a clean tree it never fires.
check-doctor-static:
    bash dev-tooling/just-check-doctor-static.sh

# ---------------------------------------------------------------
# Canonical structural checks (shared from livespec-dev-tooling).
# Wired in alphabetical order to match the aggregate above.
# ---------------------------------------------------------------

# Static check that every `.ai/<topic>.md` reference in an AGENTS.md
# (any directory level) resolves to an existing file. Shipped by
# livespec-dev-tooling (>=v0.21.0, from livespec b288fdb); enforces
# the fleet agent-instruction `.ai/` convention so a dangling
# progressive-disclosure reference fails CI.
check-agents-ai-references-resolve:
    uv run python -m livespec_dev_tooling.checks.agents_ai_references_resolve

# In-repo gate for the wiring-completeness invariant
# (SPECIFICATION/contracts.md v094 §"Shared code sync —
# livespec-dev-tooling"). Parses the local `justfile`'s `check:`
# recipe and verifies every canonical slug emitted by
# `livespec_dev_tooling.canonical_checks` is wired in alphabetical
# order, with private extras appearing only after the canonical
# block. Self-bootstrapping: the slug `check-aggregate-completeness`
# is itself canonical, so dropping it would fail this check on the
# next run.
check-aggregate-completeness:
    uv run python -m livespec_dev_tooling.checks.aggregate_completeness

check-all-declared:
    uv run python -m livespec_dev_tooling.checks.all_declared

check-assert-never-exhaustiveness:
    uv run python -m livespec_dev_tooling.checks.assert_never_exhaustiveness

# Layer 1 mechanical check: shells out to `gh api` to read remote
# GitHub state; exits 0 with a structured warning when `gh` is
# unavailable or unauthenticated locally so per-commit pre-commit
# runs are not blocked. CI with GH_TOKEN exercises the full
# enforcement path.
check-branch-protection-alignment:
    uv run python -m livespec_dev_tooling.checks.branch_protection_alignment

# Path-scoped fast-feedback variant of check-coverage. With explicit
# `--paths <impl_path> [<impl_path>...]` (repo-root-relative) it scopes
# the per-file 100% gate to those paths. With NO args (the canonical
# aggregate / `just check` invocation) the check DERIVES the changed
# impl-`.py` set from `git diff --name-only origin/master...HEAD` and
# gates those — no longer a no-op (epic li-cvaudit, cvnoarg). The
# interactive developer use case still passes `--paths` explicitly:
# `just check-check-coverage-incremental --paths .claude-plugin/scripts/bin/foo.py`.
[positional-arguments]
check-check-coverage-incremental *args:
    uv run python -m livespec_dev_tooling.checks.check_coverage_incremental "$@"

# Always invoked plainly; the module self-manages its RUN/SKIP lever
# (epic li-cvaudit, cvtodo). `LIVESPEC_RUN_MUTATION` unset → the check
# logs "skipped" and exits 0; set to a non-empty value (CI sets it to
# `true`) → the mutmut suite runs. No external gate, no silent skip.
check-check-mutation:
    uv run python -m livespec_dev_tooling.checks.check_mutation

check-check-tools:
    uv run python -m livespec_dev_tooling.checks.check_tools

check-claude-md-coverage:
    uv run python -m livespec_dev_tooling.checks.claude_md_coverage

check-comment-line-anchors:
    uv run python -m livespec_dev_tooling.checks.comment_line_anchors

# Commit-pair gate: every commit touching source files also touches
# tests. Lefthook pre-commit only is the load-bearing per-commit
# invocation; wired into the aggregate per the wiring-completeness
# invariant.
check-commit-pairs-source-and-test:
    uv run python -m livespec_dev_tooling.checks.commit_pairs_source_and_test

check-file-lloc:
    uv run python -m livespec_dev_tooling.checks.file_lloc

# Fleet marketplace ref-pin guard: catalog plugin sources MUST stay
# checkout-relative (`./...` strings, or the Codex catalog's
# `{"source": "local", "path": "./..."}` object form). Github-type or
# other non-relative sources silently ignore the registered
# marketplace ref pin and clone default HEAD instead.
check-fleet-marketplace-relative-sources:
    uv run python -m livespec_dev_tooling.checks.fleet_marketplace_relative_sources

check-global-writes:
    uv run python -m livespec_dev_tooling.checks.global_writes

check-heading-coverage:
    uv run python -m livespec_dev_tooling.checks.heading_coverage

check-keyword-only-args:
    uv run python -m livespec_dev_tooling.checks.keyword_only_args

check-main-guard:
    uv run python -m livespec_dev_tooling.checks.main_guard

# Layer 1 mechanical check: shells out to `gh api` to read remote
# GitHub state; exits 0 with a structured warning when `gh` is
# unavailable or unauthenticated locally so per-commit pre-commit
# runs are not blocked. CI with GH_TOKEN exercises the full
# enforcement path.
check-master-ci-green:
    uv run python -m livespec_dev_tooling.checks.master_ci_green

check-match-keyword-only:
    uv run python -m livespec_dev_tooling.checks.match_keyword_only

check-newtype-domain-primitives:
    uv run python -m livespec_dev_tooling.checks.newtype_domain_primitives

# Destructive-default CLI wrapping gate (livespec/SPECIFICATION/
# non-functional-requirements.md §"Destructive-default CLI wrapping"):
# greps the agent-facing trees (dev-tooling/, .claude-plugin/,
# .claude/plugins/) for direct invocations of known-destructive-default
# CLIs (bd init, git push --force/-f, git reset --hard, gh repo delete)
# outside the explicit `[tool.livespec_dev_tooling].
# destructive_cli_allowlist` path-prefix allowlist.
check-no-direct-destructive-cli:
    uv run python -m livespec_dev_tooling.checks.no_direct_destructive_cli

check-no-direct-tool-invocation:
    uv run python -m livespec_dev_tooling.checks.no_direct_tool_invocation

# Delegates to the worktree pack's single canonical body (livespec-dev-tooling-fy02),
# installed untracked at dev-tooling/ by `just install-worktree-pack` and
# byte-verified fleet-wide. Unlike the previous hard block (which forced the
# 2026-09-05 authorized workflow landing through the GitHub API, PR #2160), the
# pack body honours a HUMAN authorization recorded on the ledger: a tracked
# `.livespec-workflow-edit-exemption` declaration authored in the change, whose
# named work item carries the human-set `approval:workflow-edit` label. The
# Python module `_dispatcher_workflow_guard.py` (and its `workflow_guard.py` bin
# wrapper) stays for the Dispatcher engine's programmatic use.
check-no-workflow-edits:
    bash dev-tooling/check-no-workflow-edits.sh

# ADOPTION gate for a livespec-dev-tooling release (livespec-dev-tooling-wvuefu
# / bd-ib-u46hcv). Replays the dispatch workflow's conformance setup steps —
# read FROM workflow.toml, not duplicated — against a fresh, un-bootstrapped
# clone. This is the tree state the Fabro sandbox actually runs them in, and the
# one `just check` never exercised: v0.54.24 made an absent gitignored pack a
# FAIL, so every dispatch died at setup while this repo's gate stayed green.
check-fresh-clone-setup:
    bash orchestrator-image/fresh-clone-setup-gate.sh

check-no-except-outside-io:
    uv run python -m livespec_dev_tooling.checks.no_except_outside_io

check-no-inheritance:
    uv run python -m livespec_dev_tooling.checks.no_inheritance

# Always invoked plainly; the module self-manages its severity lever
# (epic li-cvaudit, cvtodo). The 201-250 LLOC soft-band scan ALWAYS
# runs; `LIVESPEC_FAIL_IF_LLOC_SOFT_WARNINGS_EXIST` unset → soft-band
# offenders warn + exit 0; set (CI sets it to `true`) → they fail.
check-no-lloc-soft-warnings:
    uv run python -m livespec_dev_tooling.checks.no_lloc_soft_warnings

check-no-raise-outside-io:
    uv run python -m livespec_dev_tooling.checks.no_raise_outside_io

# Always invoked plainly; the module self-manages its severity lever
# (epic li-cvaudit, cvtodo). The heading-coverage.json TODO scan ALWAYS
# runs; `LIVESPEC_FAIL_IF_HEADING_COVERAGE_TODOS_EXIST` unset → TODO
# offenders warn + exit 0 (authoring placeholders surface without
# blocking per-commit `just check`); set by the doc-only pre-commit path
# for authored unowned TODO entries → they fail. Replaces the prior
# LIVESPEC_RELEASE_GATE skip carve-out, which
# silently skipped the scan entirely when the gate was unset.
check-no-todo-registry:
    uv run python -m livespec_dev_tooling.checks.no_todo_registry

check-no-write-direct:
    uv run python -m livespec_dev_tooling.checks.no_write_direct

check-pbt-coverage-pure-modules:
    uv run python -m livespec_dev_tooling.checks.pbt_coverage_pure_modules

# Full per-file 100% line+branch coverage gate. Canonical-slug
# alias for the shared per_file_coverage check. In Red-mode pre-commit
# this target is omitted by `check-pre-commit` via the `just skip=...`
# argument (coverage is verified at the Green amend), so no ambient
# env-var read is needed here (epic li-cvaudit, cvredmd).
check-per-file-coverage:
    dev-tooling/just-check-per-file-coverage.sh

# Shared baseline Verifier: validates this repo's harness-conformance
# declaration against the plugin-resolution invariant. Shipped by
# livespec-dev-tooling (>=v0.21.0); with `harnesses` declared in
# .livespec.jsonc it runs the mock-mode declaration-integrity pass.
check-plugin-resolution:
    uv run python -m livespec_dev_tooling.checks.plugin_resolution

# Family-wide commit-refuse hook invariant per livespec/SPECIFICATION/
# non-functional-requirements.md §"Primary-checkout commit-refuse hook"
# (v095). Supersedes the v091-v094 bare-flag mechanism, which caused
# stale-on-disk-read failures at primaries. The check is shipped by
# livespec-dev-tooling (>=v0.5.0); this recipe is the project-root-
# scoped CI/just-check adoption that the spec mandates for every
# consumer repo.
check-primary-checkout-commit-refuse-hook-installed:
    uv run python -m livespec_dev_tooling.checks.primary_checkout_commit_refuse_hook_installed

check-private-calls:
    uv run python -m livespec_dev_tooling.checks.private_calls

check-public-api-result-typed:
    uv run python -m livespec_dev_tooling.checks.public_api_result_typed

# Trailer-based Red→Green replay verification (hard gate). Invoked by
# lefthook commit-msg stage with the commit-message file path as argv[1]
# (the load-bearing per-commit verifier). The canonical aggregate /
# `just check` invokes this with NO msg_path; the module then DERIVES
# the message from `git log -1 --format=%B` (HEAD) and validates it —
# no longer a no-op (epic li-cvaudit, cvnoarg).
[positional-arguments]
check-red-green-replay *args:
    uv run python -m livespec_dev_tooling.checks.red_green_replay "$@"

check-rop-pipeline-shape:
    uv run python -m livespec_dev_tooling.checks.rop_pipeline_shape

check-skill-invocation-paths:
    uv run python -m livespec_dev_tooling.checks.skill_invocation_paths

check-source-trees-scoped-to-consumer:
    uv run python -m livespec_dev_tooling.checks.source_trees_scoped_to_consumer

check-supervisor-discipline:
    uv run python -m livespec_dev_tooling.checks.supervisor_discipline

check-tests-mirror-pairing:
    uv run python -m livespec_dev_tooling.checks.tests_mirror_pairing

check-tests-no-subprocess-spawn:
    uv run python -m livespec_dev_tooling.checks.tests_no_subprocess_spawn

# Tool-backed-check completeness meta-check (epic li-pyright-gate,
# work-item li-pyright-gate-wi3; shared from livespec-dev-tooling
# v0.8.0). Asserts each tool-backed check (check-lint / check-format /
# check-types / check-coverage) is a LITERAL member of BOTH this
# justfile's `check:` targets=(...) array AND the CI check-python
# matrix. Self-passes because the targets array (private block) + CI
# matrix wire all four literally.
check-tool-backed-check-completeness:
    uv run python -m livespec_dev_tooling.checks.tool_backed_check_completeness

check-vendor-manifest:
    uv run python -m livespec_dev_tooling.checks.vendor_manifest

check-wrapper-shape:
    uv run python -m livespec_dev_tooling.checks.wrapper_shape

# ---------------------------------------------------------------
# CLI end-to-end harness (top-of-pyramid, user-surface tier).
# ---------------------------------------------------------------

# Run the CLI end-to-end harness against this plugin's own per-skill
# fixtures (per livespec/SPECIFICATION/contracts.md §"CLI end-to-end
# harness contract"). The harness ships from livespec-dev-tooling
# (v0.8.0) and is consumed via the imported test_workflow_full_round_
# trip entry point wired in tests/e2e-cli/. Defaults to the MOCK tier
# (LIVESPEC_E2E_HARNESS=mock — the one mocked boundary is the
# `claude -p` subprocess; real install-shape setup, real structural
# skill discovery, the real fail-closed time-bomb coverage gate, and
# the real per-skill orchestration loop all run). The fail-closed
# coverage gate raises CoverageGateError when a `/livespec-impl-
# beads:*` skill lacks a fixture, failing this target. The CI
# `e2e-cli` job delegates here (no direct tool invocation in the
# workflow). The mock-tier test ALSO runs as part of the normal suite
# under check-per-file-coverage; this target is the dedicated,
# explicitly-named tier entry point CI reports as its own status.
check-e2e-cli:
    uv run pytest tests/e2e-cli -v

# Live Codex TUI `/skills` picker acceptance for the human discovery path:
# `/skills` -> "List skills" -> search `drive`, then require the picker
# to render `drive (livespec-orchestrator-beads-fabro)` as a Skill row.
check-codex-skill-picker:
    bash dev-tooling/just-check-codex-skill-picker.sh

# Tree-wide dispatch-surface guard for the retired fleet PAT env name. The
# allowlisted historical/negative-assertion material lives outside these
# dispatch surfaces (tests, SPECIFICATION/history, and archived research), so
# this can fail on any tracked hit under the surfaces without path exceptions.
check-no-fleet-pat-dispatch-surface:
    bash dev-tooling/just-check-no-fleet-pat-dispatch-surface.sh

# W7 Tier-2 containerized dispatch proof. Pass script args after `--`, e.g.:
#   just w7-tier2-dispatch-proof -- --preflight
#   just w7-tier2-dispatch-proof -- --run --item <tiny-ready-item>
[positional-arguments]
w7-tier2-dispatch-proof *ARGS:
    bash orchestrator-image/tier2-dispatch-proof.sh "$@"

# W7 step-5 REAL-WORK containerized dispatch path: the production substrate the
# Dispatcher runs on for routine cross-repo work. Unlike the Tier-2 proof it
# mounts NO host checkout — it fresh-`git clone`s impl-beads (dispatcher code +
# .fabro/workflows graph) AND the dispatch target INSIDE the container, so the
# only host coupling is explicit secret provisioning (`-e VAR`). Run under the
# 1Password wrapper. Pass script args after `--`, e.g.:
#   with-livespec-env.sh -- just w7-real-work-dispatch -- --target-repo <name> --preflight
#   with-livespec-env.sh -- just w7-real-work-dispatch -- --target-repo <name> --item <id> --run
[positional-arguments]
w7-real-work-dispatch *ARGS:
    bash orchestrator-image/real-work-dispatch.sh "$@"

# W7 mechanical fail-safe reaper for orphaned `livespec-e2e-*` throwaway
# repos in the disposable `livespec-e2e` GitHub org. Org- and name-scoped by
# construction; age-gated so an in-progress run's repo is not reaped. Run only
# when no dispatch is in flight (session-start / post-merge / teardown). Pass
# script args after `--`, e.g.:
#   just reap-e2e-repos -- --dry-run
#   just reap-e2e-repos -- --dry-run --max-age 60
#   just reap-e2e-repos                 # real reap, default 120m age gate
[positional-arguments]
reap-e2e-repos *ARGS:
    bash orchestrator-image/reap-e2e-repos.sh "$@"

# ---------------------------------------------------------------
# Pre-commit aggregate — Red-mode-aware. Classifies the staged
# tree shape; in Red mode it passes a self-contained `skip=...` recipe
# argument to `just check` so coverage and same-repo live TUI gates are
# omitted from pre-commit. The commit-msg replay hook verifies the Red
# leg; coverage runs at the Green amend; and pre-push / CI keep invoking
# `just check` directly. There is NO ambient env var (epic li-cvaudit,
# cvredmd).
# ---------------------------------------------------------------

check-pre-commit:
    bash dev-tooling/just-check-pre-commit.sh

# When zero `.py` files are staged, `check-pre-commit` delegates to this
# conservative doc-only subset. This is a LOCAL pre-commit speed optimization
# only — it is NOT a merge gate, and pre-push no longer delegates here.
check-pre-commit-doc-only:
    bash dev-tooling/just-check-pre-commit-doc-only.sh

# Run the full `just check` aggregate (PR gate ≡ master gate — the zero-.py
# pre-push subset was retired so a doc-only push runs the same gate a code
# push does). The only skip is the green-token clean-tree memoization: when
# the working tree is byte-identical to the last green `just check`, the
# aggregate is skipped because CI is authoritative.
check-pre-push:
    bash dev-tooling/just-check-pre-push.sh

# ---------------------------------------------------------------
# Pre-commit auxiliary gates.
# ---------------------------------------------------------------

# Ruff fix + format on staged .py files BEFORE the rest of the
# pre-commit gate runs. Non-blocking — unfixable issues fall through
# to check-lint / check-format inside `just check` later. Re-stages
# post-autofix bytes.
lint-autofix-staged:
    bash dev-tooling/just-lint-autofix-staged.sh

# ---------------------------------------------------------------
# Mutating targets (opt-in; not run in CI).
# ---------------------------------------------------------------

fmt:
    uv run ruff format .

lint-fix:
    uv run ruff check --fix .

# Re-vendor an upstream-sourced library into .claude-plugin/scripts/_vendor/
# from the upstream ref recorded in .vendor.jsonc (the only blessed
# mutation path per livespec/SPECIFICATION/constraints.md §"Vendoring
# procedure"). Maintainer-only; NOT run in CI. The family's
# release->bump-pin automation invokes this so cross-repo auto-bump can
# re-vendor. Shim entries (shim: true) are NOT re-vendored.
[positional-arguments]
vendor-update lib:
    uv run python -m livespec_dev_tooling.vendor_update "$1"

check-partition-completeness:
    uv run python -m livespec_dev_tooling.checks.partition_completeness

check-canonical-recipe-fidelity:
    uv run python -m livespec_dev_tooling.checks.canonical_recipe_fidelity

check-ci-matrix-completeness:
    uv run python -m livespec_dev_tooling.checks.ci_matrix_completeness

check-no-fmt-directives:
    uv run python -m livespec_dev_tooling.checks.no_fmt_directives

check-local-memory-drift-audit:
    uv run python -m livespec_dev_tooling.checks.local_memory_drift_audit

check-no-shadow-ledger-body-identical:
    uv run python -m livespec_dev_tooling.checks.no_shadow_ledger_body_identical

check-handoff-dispatch-routing:
    uv run python -m livespec_dev_tooling.checks.handoff_dispatch_routing

check-self-hosted-routing:
    uv run python -m livespec_dev_tooling.checks.self_hosted_routing

check-shell-quality:
    uv run python -m livespec_dev_tooling.checks.shell_quality

check-no-shadow-ledger-body-typechecks:
    uv run python -m livespec_dev_tooling.checks.no_shadow_ledger_body_typechecks

check-required-role-keys-declared:
    uv run python -m livespec_dev_tooling.checks.required_role_keys_declared

check-hook-trees-not-io-exempt:
    uv run python -m livespec_dev_tooling.checks.hook_trees_not_io_exempt

check-plan-anchor-declared:
    uv run python -m livespec_dev_tooling.checks.plan_anchor_declared

check-plan-epic-parity:
    uv run python -m livespec_dev_tooling.checks.plan_epic_parity

check-plan-no-tombstone:
    uv run python -m livespec_dev_tooling.checks.plan_no_tombstone

check-self-hosted-uv-lane:
    uv run python -m livespec_dev_tooling.checks.self_hosted_uv_lane

check-ci-gate-parity:
    uv run python -m livespec_dev_tooling.checks.ci_gate_parity

check-work-item-interpolation-delimiters:
    uv run python -m livespec_dev_tooling.checks.work_item_interpolation_delimiters

check-plan-record-conformance:
    uv run python -m livespec_dev_tooling.checks.plan_record_conformance

check-work-item-status-vocabulary:
    uv run python -m livespec_dev_tooling.checks.work_item_status_vocabulary
