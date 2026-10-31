#!/usr/bin/env bash
set -euo pipefail

if command -v shellcheck >/dev/null 2>&1; then
    shellcheck --shell=sh bd-guard/bd-guard.sh
    shellcheck --shell=bash \
        bd-guard/install.sh \
        bd-guard/rollback.sh \
        bd-guard/test/run-tests.sh \
        bd-guard/test/run-v1-1-2-candidate-tests.sh
else
    echo "WARNING: shellcheck not found; skipping shell lint (hermetic tests still run)" >&2
fi
bash bd-guard/test/run-tests.sh
bash bd-guard/test/test-capture-start.sh
