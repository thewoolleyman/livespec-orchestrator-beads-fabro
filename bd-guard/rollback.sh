#!/usr/bin/env bash
# rollback.sh — restore the real `bd`, removing the guard wrapper (NOT run by CI).
#
# Undoes install.sh:
#   1. move /usr/local/bin/bd-real -> /usr/local/bin/bd  (restoring the real bd)
#
# It is IDEMPOTENT: if bd-real is absent, the guard was never installed (or was
# already rolled back) and there is nothing to do. This makes the guard
# TRIVIALLY REMOVABLE — a maintainer runs this, then may delete bd-guard/.
#
# This is a HOST MUTATION and is deliberately NOT executed by the test suite or
# CI. A maintainer runs it explicitly (see bd-guard/README.md).
#
# Requires write access to /usr/local/bin (typically `sudo`).

set -euo pipefail

BIN_DIR="${BD_GUARD_BIN_DIR:-/usr/local/bin}"
REAL_TARGET="${BD_GUARD_REAL_TARGET:-${BIN_DIR}/bd-real}"
WRAPPER_TARGET="${BIN_DIR}/bd"

if [ ! -e "$REAL_TARGET" ]; then
    echo "rollback.sh: no '$REAL_TARGET' present; nothing to roll back." >&2
    exit 0
fi

# Only remove $WRAPPER_TARGET if it is our guard (avoid clobbering a real bd
# that a fresh provision may have re-installed there). Recognize the guard by
# grepping the whole file for its sentinel marker (the shebang is line 1, so a
# line-1-anchored check would never match — that bug made rollback always abort).
if [ -e "$WRAPPER_TARGET" ]; then
    if grep -q 'bd-guard-wrapper-sentinel' "$WRAPPER_TARGET"; then
        echo "rollback.sh: removing guard wrapper at '$WRAPPER_TARGET'" >&2
        rm -f "$WRAPPER_TARGET"
    else
        echo "rollback.sh: '$WRAPPER_TARGET' is not the guard; leaving it, aborting." >&2
        echo "rollback.sh: inspect manually — refusing to overwrite a non-guard bd." >&2
        exit 1
    fi
fi

# Best-effort removal of the OTLP emit helper install.sh laid down beside the
# wrapper. `rm -f` is a no-op when it is absent, so this never fails a rollback
# (older installs predate the helper).
if [ -e "${BIN_DIR}/bd-guard-emit.py" ]; then
    echo "rollback.sh: removing OTLP emit helper at '${BIN_DIR}/bd-guard-emit.py'" >&2
    rm -f "${BIN_DIR}/bd-guard-emit.py"
fi

echo "rollback.sh: restoring '$REAL_TARGET' -> '$WRAPPER_TARGET'" >&2
mv "$REAL_TARGET" "$WRAPPER_TARGET"

echo "rollback.sh: done. Verify with: bd --version" >&2
