#!/usr/bin/env bash
set -euo pipefail

# The affected-tests gate. `_affected_tests_selection.py` selects, for every
# changed product module, its mirror-paired test and every test module that
# imports it directly or through another imported module, for a changed
# `workflow.fabro` every test that reads the graph, and for a changed test
# itself; runs them under coverage; and holds each changed product module to
# 100% line and branch coverage over that whole selection, naming each missing
# line. It exits 75 when it cannot determine the affected tests (a shared
# configuration file, a file that does not parse, a module no test reaches, a
# diff that could not be taken). The pre-commit hook reads 75 as "run the full
# check aggregate instead"; this script must pass the status through unchanged.
echo ":: check-changed: affected-tests gate; 'just check' runs the FULL suite and AST scans at pre-push + CI"
exec uv run python dev-tooling/checks/_affected_tests_selection.py
