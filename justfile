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
#   aggregate (with zero-py subsetting) at pre-push.
#
# Authority: livespec/SPECIFICATION/contracts.md
#   §"Shared code sync — livespec-dev-tooling" (v094 wiring-
#   completeness invariant) — every canonical slug emitted by
#   `livespec_dev_tooling.canonical_checks` MUST be wired in this
#   `check:` aggregate in alphabetical order; livespec-orchestrator-beads-fabro-
#   private extras MAY follow after the canonical block. The in-repo
#   gate `check-aggregate-completeness` enforces this on every run.

# `skip` — space-separated list of `check:` targets to omit from a single run.
# Default empty (full aggregate). Overridden on the command line by the Red-mode
# pre-commit hook (see check-pre-commit). When empty, the green token is written
# after a full green aggregate pass for the pre-push short-circuit.
skip := ""

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

acceptance-live item:
    bash orchestrator-image/tier2-dispatch-proof.sh --run --item {{item}}

# W7 LIVE Beads/Fabro golden-master tier. The REAL end-to-end proof: creates a
# throwaway `livespec-e2e/livespec-e2e-*` repo, seeds it with the hello-world
# fixture SPECIFICATION + an embedded beads ledger carrying one ready greeting
# item, runs the production container/Fabro factory so Fabro implements + PRs +
# merges, clones the merged repo, asserts greet("Ada")=="Hello, Ada!", and
# deletes the repo (with reaper stale-sweep on entry, teardown on exit). Run
# under the 1Password wrapper:
#   with-livespec-env.sh -- just acceptance-live-golden-master -- --run
acceptance-live-golden-master *ARGS:
    bash orchestrator-image/acceptance-live-golden-master.sh {{ARGS}}

# ---------------------------------------------------------------
# First-time setup.
# ---------------------------------------------------------------

install-commit-refuse-hooks:
    # Idempotent `livespec.primaryPath` on the primary checkout's
    # git-common-dir config (per livespec/SPECIFICATION/
    # non-functional-requirements.md §"Primary-checkout commit-refuse
    # hook" / §"Commit-refuse hook bootstrap procedure" — family-wide
    # invariant inherited by every livespec-impl-* sibling). The
    # commit-refuse hook reads this config value to recognize the
    # primary checkout and refuse commits/pushes there, forcing every
    # edit through `git worktree add`. Targets the absolute path of
    # the git common dir's parent so the recipe writes the right
    # value when invoked from the primary checkout AND from secondary
    # worktrees.
    git config --file "$(git rev-parse --git-common-dir)/config" livespec.primaryPath "$(realpath "$(dirname "$(git rev-parse --git-common-dir)")")"
    # Install the commit-refuse hook (vendored from livespec-dev-
    # tooling v0.5.0 — see dev-tooling/livespec-commit-refuse-hook.sh)
    # at pre-commit AND pre-push. Refuses at the primary checkout;
    # delegates to lefthook at secondary worktrees via mise. The
    # commit-msg path keeps the legacy git-hook-wrapper since it
    # routes argv[1] to the v034 D3 replay-hook stage.
    install -D -m 755 dev-tooling/livespec-commit-refuse-hook.sh "$(git rev-parse --git-common-dir)/hooks/pre-commit"
    install -D -m 755 dev-tooling/livespec-commit-refuse-hook.sh "$(git rev-parse --git-common-dir)/hooks/pre-push"
    install -D -m 755 dev-tooling/git-hook-wrapper.sh "$(git rev-parse --git-common-dir)/hooks/commit-msg"

bootstrap:
    just install-commit-refuse-hooks
    # Harden the beads tenant-pointer dir to owner-only on first-touch (bd
    # recommends 0700; only the owning user's bd reads it — the Dolt server
    # connects over TCP and never reads this dir). Guarded: repos with no beads
    # tenant have no .beads.
    [ -d "$(dirname "$(git rev-parse --git-common-dir)")/.beads" ] && chmod 700 "$(dirname "$(git rev-parse --git-common-dir)")/.beads" || true
    just ensure-plugins
    just ensure-codex-plugins

# Idempotent: `claude plugin marketplace add` and `claude plugin install`
# both exit 0 when the target is already present. livespec@livespec is
# the core artifact carrier (prose + reference CLIs);
# livespec@livespec-driver-claude is the Claude Code Driver that
# exposes the /livespec:* commands — both are required for the
# spec-side surface.
ensure-plugins:
    claude plugin marketplace add --scope project thewoolleyman/livespec
    claude plugin marketplace add --scope project thewoolleyman/livespec-driver-claude
    claude plugin marketplace add --scope project thewoolleyman/livespec-orchestrator-beads-fabro
    claude plugin install -s project livespec@livespec
    claude plugin install -s project livespec@livespec-driver-claude
    claude plugin install -s project livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro

# Idempotent host-wide Codex plugin provisioning. Codex does not support
# project-scoped plugin enablement, so these registrations intentionally land in
# the user's default CODEX_HOME and are visible to every repo on the host. Codex
# is an optional dogfooding runtime; bootstrap skips this target when the CLI is
# absent but fails on real install errors when Codex is present.
ensure-codex-plugins:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v codex >/dev/null 2>&1; then
        echo "codex CLI not found; skipping host-wide Codex plugin install." >&2
        exit 0
    fi
    codex plugin marketplace add thewoolleyman/livespec
    codex plugin marketplace add thewoolleyman/livespec-driver-codex
    codex plugin marketplace add thewoolleyman/livespec-orchestrator-beads-fabro
    codex plugin marketplace upgrade livespec
    codex plugin marketplace upgrade livespec-driver-codex
    codex plugin marketplace upgrade livespec-orchestrator-beads-fabro
    codex plugin add livespec@livespec
    codex plugin add livespec@livespec-driver-codex
    codex plugin add livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro

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

check:
    #!/usr/bin/env bash
    set -uo pipefail
    # Sync the environment ONCE per aggregate pass, then run every
    # target with UV_NO_SYNC=1 so the per-target `uv run`
    # invocations skip their redundant per-invocation re-sync
    # (work-item livespec-7dro). The single up-front sync
    # keeps the freshness guarantee — a stale lockfile/venv still
    # fails here, loudly, before any target runs. This also caps the
    # cost of a corrupted-venv re-sync loop (e.g. an orphaned
    # dist-info missing its RECORD file, which a sync can never
    # uninstall and therefore retries on EVERY invocation) at one
    # sync attempt per pass instead of one per target, and shrinks
    # the concurrent-sync race window that produces that corruption
    # in the first place. Standalone `just check-<x>` invocations
    # keep uv's default sync-on-run behavior; CI's per-target matrix
    # jobs each sync their own fresh runner and are unaffected.
    if ! uv sync --all-groups; then
        echo "ERROR: up-front 'uv sync --all-groups' failed; aborting the check aggregate" >&2
        exit 1
    fi
    export UV_NO_SYNC=1
    # Canonical-check aggregate, per SPECIFICATION/contracts.md
    # §"Wiring-completeness invariant" (v094): every canonical slug
    # emitted by `livespec_dev_tooling.canonical_checks` MUST appear
    # here in alphabetical order; livespec-impl-beads-private
    # checks MAY follow after the canonical block in any order. The
    # in-repo gate is `check-aggregate-completeness`, which fails if
    # any canonical slug is missing or out-of-order.
    #
    # Aggregator continues on failure (matches CI fail-fast: false)
    # and exits non-zero with the failure list if any target failed.
    #
    # `skip` is a just VARIABLE (declared at the top of this justfile,
    # default empty): a space-separated list of target names to omit from
    # this run (epic li-cvaudit, cvredmd). The Red-mode pre-commit invokes
    # `just skip="check-coverage check-per-file-coverage" check` so coverage
    # is not gated at the Red commit (it is verified at the Green amend) —
    # a self-contained just variable that replaces the prior ambient
    # `LIVESPEC_PRECOMMIT_RED_MODE` env var. The recipe header stays the
    # bare `check:` the wiring-completeness checks parse for. Pre-push and
    # CI invoke `just check` with no `skip`, so the full aggregate stays
    # the safety net.
    read -ra skip_targets <<< "{{skip}}"
    targets=(
        check-aggregate-completeness
        check-all-declared
        check-assert-never-exhaustiveness
        check-branch-protection-alignment
        check-check-coverage-incremental
        check-check-mutation
        check-check-tools
        check-claude-md-coverage
        check-comment-line-anchors
        check-commit-pairs-source-and-test
        check-file-lloc
        check-global-writes
        check-heading-coverage
        check-keyword-only-args
        check-main-guard
        check-master-ci-green
        check-match-keyword-only
        check-newtype-domain-primitives
        check-no-direct-destructive-cli
        check-no-direct-tool-invocation
        check-no-except-outside-io
        check-no-inheritance
        check-no-lloc-soft-warnings
        check-no-raise-outside-io
        check-no-todo-registry
        check-no-write-direct
        check-pbt-coverage-pure-modules
        check-per-file-coverage
        check-primary-checkout-commit-refuse-hook-installed
        check-private-calls
        check-public-api-result-typed
        check-red-green-replay
        check-rop-pipeline-shape
        check-skill-invocation-paths
        check-supervisor-discipline
        check-tests-mirror-pairing
        check-tests-no-subprocess-spawn
        check-tool-backed-check-completeness
        check-vendor-manifest
        check-wrapper-shape
        # ---- livespec-impl-beads-private block ----
        # Tool-backed checks (ruff lint, ruff format, pyright types,
        # aggregate coverage) — helper recipes, NOT canonical slugs
        # (not under livespec_dev_tooling/checks/), so check-aggregate-
        # completeness does not enforce them. They are wired here as
        # LITERAL members so the local `just check` aggregate gives full
        # lint / format / types / coverage feedback and matches the CI
        # check-python matrix; the check-tool-backed-check-completeness
        # meta-check (canonical block above, dev-tooling v0.8.0)
        # enforces that both-surfaces wiring (epic li-pyright-gate,
        # work-item li-pyright-gate-wi3, LITERAL-membership design).
        # check-coverage gates the aggregate `fail_under = 100` off the
        # SINGLE pytest run that the canonical check-per-file-coverage
        # already performed (it reads the existing `.coverage`), so
        # wiring it here adds NO duplicate suite run. In Red-mode
        # pre-commit, check-coverage + check-per-file-coverage are
        # omitted by `check-pre-commit` via `just skip="..."` — a
        # self-contained just variable, no ambient env var (epic
        # li-cvaudit, cvredmd).
        check-format
        check-lint
        check-types
        check-coverage
        # Beads-private merge-evidence static check (R7). Reads the
        # AuditRecord from each closed issue's `metadata` via the store
        # (hermetic fake in the default tier → empty tenant → passes
        # trivially); same git-reachability rules as the plaintext sibling's
        # JSONL-shaped equivalent; epics exempt. Not a canonical slug, so it
        # rides in the private block after the canonical set.
        check-work-item-merge-evidence
        # Beads-private closed-item-integrity static check
        # (SPECIFICATION/contracts.md §"Closed-item-integrity check").
        # Enumerates every closed gap-tied work-item via the store
        # (hermetic fake in the default tier → empty tenant → passes
        # trivially) and flags any "closed but unproven" item — one whose
        # clauses[]-resolved acceptance scenario is still TODO-bound or
        # which lacks the resolution:completed label. ALWAYS-WIRED +
        # ALWAYS-RUNNING; severity rides the LIVESPEC_CLOSED_ITEM_INTEGRITY
        # lever (default warn → exit 0, advisory). Not a canonical slug, so
        # it rides in the private block after the canonical set.
        check-closed-item-integrity
        # Codex cross-runtime structural check (P3). Pure-filesystem gate
        # validating the orchestrator plugin's Codex surface (repo-root
        # .agents/plugins/marketplace.json catalog, nested
        # .claude-plugin/.codex-plugin/plugin.json manifest, the seven present
        # .codex-plugin/skills/<op>/SKILL.md bindings — four wrapper-backed thin
        # ops plus three prose-backed capture ops). No beads / no store,
        # so it runs in any tier. Enforces the no-Codex-hooks contract (NO
        # `hooks` key, no `.codex-plugin/hooks/` dir — the orchestrator's
        # Claude surface ships no hooks, so a Codex-only guard would be
        # asymmetric). Not a canonical slug, so it rides in the private block
        # after the canonical set.
        check-codex-plugin-structure
        # Live Codex TUI `/skills` picker acceptance. This is intentionally a
        # private, host-aware gate: it drives the actual Codex picker path that
        # operators use, while CI skips unless explicitly opted into an
        # authenticated Codex runner.
        check-codex-skill-picker
    )
    failed=()
    ran=0
    for t in "${targets[@]}"; do
        skip_this=0
        for s in "${skip_targets[@]:-}"; do
            if [[ "$t" == "$s" ]]; then
                skip_this=1
                break
            fi
        done
        if [[ "$skip_this" -eq 1 ]]; then
            printf '\n::: just %s (skipped)\n' "$t"
            continue
        fi
        ran=$((ran + 1))
        printf '\n::: just %s\n' "$t"
        if ! just "$t"; then
            failed+=("$t")
        fi
    done
    if [[ ${#failed[@]} -gt 0 ]]; then
        printf '\nFailed targets (%d):\n' "${#failed[@]}"
        printf '  - %s\n' "${failed[@]}"
        exit 1
    fi
    printf '\nAll %d targets passed.\n' "${#targets[@]}"
    if [[ -z "{{skip}}" ]]; then uv run python -m livespec_dev_tooling.green_token write || true; fi

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
    #!/usr/bin/env bash
    set -euo pipefail
    uv run ruff format --check .
    uv run ruff check .
    uv run pyright

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
    #!/usr/bin/env bash
    set -uo pipefail
    # `grep` exits 1 on zero matches; an empty changed set is normal (a
    # clean branch), so swallow that into exit 0 via `|| true` — the
    # consuming `check-changed` treats empty as "nothing to gate".
    { git diff --name-only origin/master...HEAD;
      git diff --cached --name-only --diff-filter=AM; } \
        | { grep -E '\.py$' || true; } | sort -u

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
    #!/usr/bin/env bash
    set -uo pipefail
    mapfile -t changed < <(just changed-files)
    if [[ "${#changed[@]}" -eq 0 ]]; then
        echo ":: check-changed: no changed .py vs origin/master (and none staged); nothing to gate"
        echo ":: the authoritative full gate remains 'just check' (run at pre-push + CI)"
        exit 0
    fi
    echo ":: check-changed: scoping the test subset + per-file coverage gate to ${#changed[@]} changed .py:"
    printf '   %s\n' "${changed[@]}"
    echo ":: INNER-LOOP ONLY — 'just check' runs the FULL suite/AST scans at pre-push + CI"
    just check-check-coverage-incremental --paths "${changed[@]}"

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
    #!/usr/bin/env bash
    set -uo pipefail
    if [[ -f .coverage ]]; then
        echo ":: check-coverage: reading existing .coverage (produced by check-per-file-coverage); no duplicate suite run"
        uv run coverage report --fail-under=100
    else
        echo ":: check-coverage: no .coverage data file (CI standalone job); running the suite"
        uv run pytest -n auto --cov --cov-branch --cov-config=pyproject.toml --cov-report=term-missing
    fi

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

# ---------------------------------------------------------------
# Canonical structural checks (shared from livespec-dev-tooling).
# Wired in alphabetical order to match the aggregate above.
# ---------------------------------------------------------------

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
check-check-coverage-incremental *args:
    uv run python -m livespec_dev_tooling.checks.check_coverage_incremental {{args}}

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
# blocking per-commit `just check`); set (CI sets it to `true`) → they
# fail. Replaces the prior LIVESPEC_RELEASE_GATE skip carve-out, which
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
    #!/usr/bin/env bash
    set -uo pipefail
    # pytest-cov defaults `--cov-config` to `.coveragerc`, which
    # bypasses pyproject.toml's `[tool.coverage.run]` (including
    # the `omit = [...]` carve-outs). Pass the config path
    # explicitly so the vendored-tree exclusion takes effect.
    uv run pytest -n auto --cov --cov-branch --cov-config=pyproject.toml --cov-report=term-missing
    uv run python -m livespec_dev_tooling.checks.per_file_coverage

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
check-red-green-replay *args:
    uv run python -m livespec_dev_tooling.checks.red_green_replay {{args}}

check-rop-pipeline-shape:
    uv run python -m livespec_dev_tooling.checks.rop_pipeline_shape

check-skill-invocation-paths:
    uv run python -m livespec_dev_tooling.checks.skill_invocation_paths

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
# `/skills` -> "List skills" -> search `orchestrate`, then require the picker
# to render `orchestrate (livespec-orchestrator-beads-fabro)` as a Skill row.
check-codex-skill-picker:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ "${CI:-}" == "true" && "${LIVESPEC_REQUIRE_CODEX_TUI_PICKER:-}" != "1" ]]; then
        echo ":: check-codex-skill-picker: skipped in CI; set LIVESPEC_REQUIRE_CODEX_TUI_PICKER=1 on an authenticated Codex runner to enforce it"
        exit 0
    fi
    if ! command -v codex >/dev/null 2>&1; then
        echo ":: check-codex-skill-picker: codex CLI not found; skipping live TUI picker acceptance"
        exit 0
    fi
    LIVESPEC_CODEX_SKILL_PICKER=1 uv run pytest tests/e2e-cli/test_codex_skill_picker.py -v

# W7 Tier-2 containerized dispatch proof. Pass script args after `--`, e.g.:
#   just w7-tier2-dispatch-proof -- --preflight
#   just w7-tier2-dispatch-proof -- --run --item <tiny-ready-item>
w7-tier2-dispatch-proof *ARGS:
    bash orchestrator-image/tier2-dispatch-proof.sh {{ARGS}}

# W7 step-5 REAL-WORK containerized dispatch path: the production substrate the
# Dispatcher runs on for routine cross-repo work. Unlike the Tier-2 proof it
# mounts NO host checkout — it fresh-`git clone`s impl-beads (dispatcher code +
# .fabro/workflows graph) AND the dispatch target INSIDE the container, so the
# only host coupling is explicit secret provisioning (`-e VAR`). Run under the
# 1Password wrapper. Pass script args after `--`, e.g.:
#   with-livespec-env.sh -- just w7-real-work-dispatch -- --target-repo <name> --preflight
#   with-livespec-env.sh -- just w7-real-work-dispatch -- --target-repo <name> --item <id> --run
w7-real-work-dispatch *ARGS:
    bash orchestrator-image/real-work-dispatch.sh {{ARGS}}

# W7 mechanical fail-safe reaper for orphaned `livespec-e2e-*` throwaway
# repos in the disposable `livespec-e2e` GitHub org. Org- and name-scoped by
# construction; age-gated so an in-progress run's repo is not reaped. Run only
# when no dispatch is in flight (session-start / post-merge / teardown). Pass
# script args after `--`, e.g.:
#   just reap-e2e-repos -- --dry-run
#   just reap-e2e-repos -- --dry-run --max-age 60
#   just reap-e2e-repos                 # real reap, default 120m age gate
reap-e2e-repos *ARGS:
    bash orchestrator-image/reap-e2e-repos.sh {{ARGS}}

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
    #!/usr/bin/env bash
    set -uo pipefail
    staged=$(git diff --cached --name-only --diff-filter=AM)
    py_staged=$(echo "$staged" | grep -E '\.py$' || true)
    test_staged=$(echo "$staged" | grep -E '^tests/.*\.py$' || true)
    impl_staged=$(echo "$staged" | grep -E '^(\.claude-plugin/scripts/|dev-tooling/checks/).*\.py$' || true)
    test_count=0
    impl_count=0
    [[ -n "$test_staged" ]] && test_count=$(echo "$test_staged" | wc -l)
    [[ -n "$impl_staged" ]] && impl_count=$(echo "$impl_staged" | wc -l)
    if [[ -z "$py_staged" ]]; then
        echo ":: doc-only mode detected (zero .py files staged): running just check-pre-commit-doc-only"
        echo ":: pre-push + CI keep the full aggregate as the load-bearing safety net"
        just check-pre-commit-doc-only
        exit $?
    fi
    if [[ "$test_count" -eq 1 ]] && [[ "$impl_count" -eq 0 ]]; then
        echo ":: Red-mode shape detected: $test_staged"
        echo ":: skipping coverage gates and same-repo live TUI picker gate in pre-commit"
        just skip="check-coverage check-per-file-coverage check-codex-skill-picker" check
        exit $?
    fi
    # Green-amend shape: impl staged while HEAD still carries Red-only
    # trailers (the Green amend has not yet written its TDD-Green-*
    # trailers — the commit-msg `check-red-green-replay {1}` hook writes
    # AND verifies them immediately after this pre-commit pass). The
    # no-arg `check-red-green-replay` aggregate variant validates HEAD,
    # which during a Green amend is the in-progress Red commit; it would
    # otherwise reject a perfectly valid Green amend. Skip the aggregate
    # variant here (the commit-msg hook is the load-bearing per-commit
    # verifier). Also skip the same-repo live TUI picker gate here, matching
    # the Red path above; standalone `just check`, pre-push's green-token path,
    # and CI keep the completed Red->Green HEAD covered after the amend lands.
    head_msg=$(git log -1 --format=%B 2>/dev/null || true)
    if [[ "$impl_count" -ge 1 ]] \
        && grep -q 'TDD-Red-Test-File-Checksum:' <<< "$head_msg" \
        && ! grep -q 'TDD-Green-Verified-At:' <<< "$head_msg"; then
        echo ":: Green-amend shape detected (impl staged; HEAD carries Red-only trailers)"
        echo ":: skipping no-arg check-red-green-replay and same-repo live TUI picker gate"
        just skip="check-red-green-replay check-codex-skill-picker" check
        exit $?
    fi
    just check

# When zero `.py` files are staged, `check-pre-commit` delegates here.
# Pre-push delegates here via `check-pre-push` for zero-py changesets.
# check-claude-md-coverage and check-heading-coverage are intentionally
# absent here: backlog work-items li-bb5suo (CLAUDE.md backfill) and
# li-4liaxt (heading-coverage backfill) close the gap; until those land
# they would force every doc-only commit to fail the pre-commit gate.
# They remain wired in the full `just check` aggregate (and surface in
# pre-push) as the load-bearing canonical contract.
check-pre-commit-doc-only:
    #!/usr/bin/env bash
    set -uo pipefail
    targets=(
        check-vendor-manifest
        check-no-direct-tool-invocation
        check-check-tools
    )
    failed=()
    for t in "${targets[@]}"; do
        printf '\n::: just %s\n' "$t"
        if ! just "$t"; then
            failed+=("$t")
        fi
    done
    if [[ ${#failed[@]} -gt 0 ]]; then
        printf '\nFailed targets (%d):\n' "${#failed[@]}"
        printf '  - %s\n' "${failed[@]}"
        exit 1
    fi
    printf '\nAll %d doc-only targets passed.\n' "${#targets[@]}"

# Skip the Python-code check subset when the pushed commits contain
# zero `.py` changes; those checks are deterministic functions of
# the source tree and would pass-or-fail identically against the
# merge-base. Falls back to `origin/master` when no upstream branch
# is configured locally.
check-pre-push:
    #!/usr/bin/env bash
    set -uo pipefail
    upstream=$(git rev-parse --abbrev-ref --symbolic-full-name @{upstream} 2>/dev/null || echo "origin/master")
    changeset=$(git diff --name-only "${upstream}..HEAD")
    py_changed=$(echo "$changeset" | grep -E '\.py$' || true)
    if [[ -z "$py_changed" ]]; then
        echo ":: doc-only push detected (zero .py changes vs ${upstream}): running check-pre-commit-doc-only"
        just check-pre-commit-doc-only
        exit $?
    fi
    if uv run python -m livespec_dev_tooling.green_token check 2>&1; then
        echo ":: pre-push: green token matched — tree byte-identical to last green check; skipping full aggregate (CI is authoritative)"
        exit 0
    fi
    just check

# ---------------------------------------------------------------
# Pre-commit auxiliary gates.
# ---------------------------------------------------------------

# Ruff fix + format on staged .py files BEFORE the rest of the
# pre-commit gate runs. Non-blocking — unfixable issues fall through
# to check-lint / check-format inside `just check` later. Re-stages
# post-autofix bytes.
lint-autofix-staged:
    #!/usr/bin/env bash
    set -uo pipefail
    staged=$(git diff --cached --name-only --diff-filter=AM | grep -E '\.py$' || true)
    if [[ -z "$staged" ]]; then
        exit 0
    fi
    echo "$staged" | xargs uv run ruff check --fix --exit-zero
    echo "$staged" | xargs uv run ruff format
    echo "$staged" | xargs git add

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
vendor-update lib:
    uv run python -m livespec_dev_tooling.vendor_update {{lib}}
