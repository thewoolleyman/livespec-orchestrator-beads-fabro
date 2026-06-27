#!/usr/bin/env bash
# worktree-hydrate.sh — per-ecosystem worktree hydration hook (python profile)
# for the livespec-orchestrator-beads-fabro orchestrator.
#
# "Hydrate" means: prepare a freshly-created linked worktree so this repo's
# checks and tooling can run inside it. What that entails is ECOSYSTEM-SPECIFIC
# — there is NO neutral default that fits Python, Rust, and JavaScript — so the
# portable, ecosystem-NEUTRAL core (dev-tooling/worktree-lib.sh) delegates
# hydration here. This file is the python-profile specialization; unlike a
# copier-rendered impl-plugin, this orchestrator repo authors and tracks it
# directly (it is NOT part of the installed worktree-discipline pack).
#
# The worktree-lifecycle CORE and the commit-refuse gate stay pure-git and
# ecosystem-neutral; ONLY this hydration script varies by ecosystem.
#
# Resolution: worktree-lib.sh runs, in order, the WORKTREE_HYDRATE_HOOK env
# command if set, else this executable script, else a friendly no-op. Override
# the default command without editing this file by exporting
# WORKTREE_HYDRATE_OVERRIDE="<command>" (takes precedence over the default
# below), or replace the whole hook via WORKTREE_HYDRATE_HOOK.
#
# Idempotent and safe to re-run: worktree-lib.sh only invokes this from inside
# a linked worktree, and `./dev-tooling/worktree-lib.sh hydrate` re-runs it.

set -euo pipefail

# The dependency-resolution command this repo's python profile uses.
# Overridable at runtime via WORKTREE_HYDRATE_OVERRIDE.
HYDRATE_CMD="uv sync --all-groups"
if [ -n "${WORKTREE_HYDRATE_OVERRIDE:-}" ]; then
    HYDRATE_CMD="${WORKTREE_HYDRATE_OVERRIDE}"
fi

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

# -------------------------------------------------------------------------
# Python hydration = CREATE THE .venv via the uv cache.
#
# uv resolves and materializes a project-local .venv from pyproject.toml +
# uv.lock; this is cheap because uv reuses its global wheel/download cache
# across worktrees rather than re-downloading. `uv sync --all-groups` installs
# the dev dependency group too (ruff/pyright/pytest/…), so the worktree can run
# the full `just check` aggregate. There is no shared in-tree dep dir to copy —
# the .venv is per-worktree and cheap to recreate.
echo "worktree-hydrate (python): $HYDRATE_CMD"
${HYDRATE_CMD}
echo "worktree-hydrate (python): done."
exit 0
