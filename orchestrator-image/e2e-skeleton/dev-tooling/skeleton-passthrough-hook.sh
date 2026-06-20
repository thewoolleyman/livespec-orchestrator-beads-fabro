#!/usr/bin/env bash
# skeleton-passthrough-hook.sh — a deliberately benign git hook for the W7
# live-golden-master throwaway skeleton.
#
# The production implement-work-item Fabro workflow installs the repo's
# "commit-refuse hook" at .git/hooks/pre-commit + pre-push (derived from the
# justfile's `cp dev-tooling/<hook>.sh ... hooks/pre-commit` bootstrap line).
# For a real livespec-impl repo that hook enforces the primary-checkout refuse
# branch + the Red-Green-Replay ritual. This MINIMAL skeleton deliberately
# carries NEITHER: the deliverable is the hello-world greeting program, not a
# TDD-ritual demo, so the Fabro agent commits + pushes normally. This hook is a
# pure pass-through (always exit 0) so commit/push proceed; the janitor stage's
# `just check` is the real gate on the produced code.
exit 0
