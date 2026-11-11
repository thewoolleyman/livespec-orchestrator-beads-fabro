#!/usr/bin/env bash
# Deliberately omit errexit: grep returns 1 for an empty changed set, which is
# a clean no-op surface for consumers.
set -uo pipefail

{
    git diff --name-only origin/master...HEAD
    git diff --cached --name-only --diff-filter=AM
} | {
    grep -E '^(\.claude-plugin/scripts/livespec_orchestrator_beads_fabro/|\.claude-plugin/scripts/bin/|dev-tooling/checks/|\.claude/hooks/|\.claude-plugin/hooks/).*\.py$' || true
} | sort -u
