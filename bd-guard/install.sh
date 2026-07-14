#!/usr/bin/env bash
# install.sh — codified installer for the bd-guard wrapper (NOT run by CI).
#
# Swaps the real `bd` behind the guard wrapper:
#   1. move  /usr/local/bin/bd      -> /usr/local/bin/bd-real  (idempotent)
#   2. install this repo's bd-guard.sh as /usr/local/bin/bd
#
# It is IDEMPOTENT and RECREATABLE (safe to re-run; survives a fresh
# provision): step 1 is skipped if bd-real already exists, and step 2 refreshes
# the installed wrapper from the tracked source — first relocating a fresh real
# bd (one a re-provision reinstalled over the guard) to bd-real so it is never
# clobbered.
#
# This is a HOST MUTATION and is deliberately NOT executed by the test suite or
# CI. A maintainer runs it explicitly (see bd-guard/README.md). Warn-mode is
# the default first rollout — the wrapper never blocks until
# LIVESPEC_BD_GUARD_MODE=fail is set, so installing it is safe to observe with.
#
# Requires write access to /usr/local/bin (typically `sudo`).

set -euo pipefail

BIN_DIR="${BD_GUARD_BIN_DIR:-/usr/local/bin}"
REAL_TARGET="${BD_GUARD_REAL_TARGET:-${BIN_DIR}/bd-real}"
WRAPPER_TARGET="${BIN_DIR}/bd"

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd -P)"
WRAPPER_SRC="${SCRIPT_DIR}/bd-guard.sh"
EMIT_SRC="${SCRIPT_DIR}/bd-guard-emit.py"

if [ ! -f "$WRAPPER_SRC" ]; then
    echo "install.sh: wrapper source not found: $WRAPPER_SRC" >&2
    exit 1
fi

if [ ! -f "$EMIT_SRC" ]; then
    echo "install.sh: emit helper source not found: $EMIT_SRC" >&2
    exit 1
fi

# --- Step 1: relocate the real bd to bd-real (idempotent) -------------------
if [ -e "$REAL_TARGET" ]; then
    echo "install.sh: '$REAL_TARGET' already present; leaving it in place." >&2
else
    if [ ! -e "$WRAPPER_TARGET" ]; then
        echo "install.sh: no '$WRAPPER_TARGET' to relocate; is bd installed?" >&2
        exit 1
    fi
    # A prior partial install could have left the guard AT $WRAPPER_TARGET.
    # Guard against relocating the wrapper onto itself. Recognize the guard by
    # grepping the whole file for its sentinel marker (the shebang is line 1,
    # so a line-1-anchored check would never match).
    if grep -q 'bd-guard-wrapper-sentinel' "$WRAPPER_TARGET"; then
        echo "install.sh: '$WRAPPER_TARGET' already looks like the guard; not relocating." >&2
    else
        echo "install.sh: moving '$WRAPPER_TARGET' -> '$REAL_TARGET'" >&2
        mv "$WRAPPER_TARGET" "$REAL_TARGET"
    fi
fi

# --- Step 2: install the guard wrapper as bd (always refresh) ----------------
# Fresh-provision safety: if bd-real already exists (step 1 skipped) but the
# current bd is NOT our guard (no sentinel), a re-provision reinstalled a real
# bd over the guard. Blindly overwriting it would LOSE that binary (e.g. a bd
# version bump) while rollback would restore the now-stale bd-real. Relocate
# the fresh real bd to bd-real first (replacing the stale copy) so the newest
# real bd is preserved. (When bd was moved away in step 1, WRAPPER_TARGET is
# absent and this is skipped.)
if [ -e "$WRAPPER_TARGET" ] && ! grep -q 'bd-guard-wrapper-sentinel' "$WRAPPER_TARGET"; then
    echo "install.sh: '$WRAPPER_TARGET' is a real bd (no guard sentinel); relocating it -> '$REAL_TARGET' to preserve it." >&2
    mv "$WRAPPER_TARGET" "$REAL_TARGET"
fi
echo "install.sh: installing guard wrapper -> '$WRAPPER_TARGET'" >&2
install -m 0755 "$WRAPPER_SRC" "$WRAPPER_TARGET"

# --- Step 3: install the fire-and-forget OTLP emit helper next to the wrapper -
# The guard resolves the emitter as `$(dirname bd)/bd-guard-emit.py` at runtime,
# so it MUST sit beside the installed wrapper. Telemetry is default-ON and
# fail-open: a missing helper (or a dead collector) simply means no span is
# emitted; bd's behavior, exit code, and streams are never affected.
echo "install.sh: installing OTLP emit helper -> '${BIN_DIR}/bd-guard-emit.py'" >&2
install -m 0755 "$EMIT_SRC" "${BIN_DIR}/bd-guard-emit.py"

# --- Step 4: seed the host-wide mode file (default warn; never clobber) -------
MODE_FILE="${LIVESPEC_BD_GUARD_MODE_FILE:-/usr/local/etc/livespec-bd-guard.mode}"
if [ ! -e "$MODE_FILE" ]; then
    mkdir -p "$(dirname "$MODE_FILE")"
    printf 'warn\n' > "$MODE_FILE"
    chmod 0644 "$MODE_FILE"
    echo "install.sh: seeded mode file '$MODE_FILE' = warn" >&2
else
    echo "install.sh: mode file '$MODE_FILE' already present; leaving it." >&2
fi

echo "install.sh: done. Verify with: bd --version   (should pass through to real bd)" >&2
echo "install.sh: default mode is WARN. To block host-wide, run:" >&2
echo "install.sh:     echo fail | sudo tee $MODE_FILE   (and 'warn' to revert)." >&2
echo "install.sh: the exported LIVESPEC_BD_GUARD_MODE env var is scrubbed by the" >&2
echo "install.sh: credential wrapper, so the mode FILE is the real host-wide switch." >&2
echo "install.sh: to point tooling at the wrapper, set LIVESPEC_BD_PATH=$WRAPPER_TARGET" >&2
