#!/usr/bin/env bash
# run-tests.sh — hermetic test harness for bd-guard.sh.
#
# Fully hermetic: it points LIVESPEC_BD_REAL at a generated stub ("fake bd")
# that records its exact argv, emits controlled stdout/stderr, and exits with a
# controlled code. No real `bd`, no network, no host mutation. Uses only bash +
# POSIX utilities so it runs on any CI runner (no bats dependency).
#
# Exit 0 iff every case passes; non-zero (with a summary) otherwise.

set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd -P)"
WRAPPER="${SCRIPT_DIR}/../bd-guard.sh"

if [ ! -f "$WRAPPER" ]; then
    echo "run-tests.sh: wrapper not found: $WRAPPER" >&2
    exit 1
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- the stub "real bd" ------------------------------------------------------
FAKE_BD="${WORK}/fake-bd"
cat > "$FAKE_BD" <<'STUB'
#!/bin/sh
# Records exact argv (one per line), emits controlled streams, exits controlled.
printf '%s\n' "$@" > "$FAKE_BD_ARGV_FILE"
if [ -n "${FAKE_BD_STDOUT:-}" ]; then printf '%s' "$FAKE_BD_STDOUT"; fi
if [ -n "${FAKE_BD_STDERR:-}" ]; then printf '%s' "$FAKE_BD_STDERR" >&2; fi
exit "${FAKE_BD_EXIT:-0}"
STUB
chmod +x "$FAKE_BD"

ARGV_FILE="${WORK}/argv.txt"
OUT_FILE="${WORK}/out.txt"
ERR_FILE="${WORK}/err.txt"

export LIVESPEC_BD_REAL="$FAKE_BD"
export FAKE_BD_ARGV_FILE="$ARGV_FILE"

PASS=0
FAIL=0
fail() { FAIL=$((FAIL + 1)); echo "  FAIL: $1" >&2; }
pass() { PASS=$((PASS + 1)); echo "  ok:   $1"; }

# run_wrapper MODE EXITCODE STDOUT -- <argv...>
# Sets the guard mode, the stub's exit code + stdout payload, resets the argv
# record, runs the wrapper, and captures stdout/stderr/exit into globals.
run_wrapper() {
    local mode="$1" exitcode="$2" stdout="$3"
    shift 3
    [ "$1" = "--" ] && shift
    rm -f "$ARGV_FILE"
    LIVESPEC_BD_GUARD_MODE="$mode" \
    FAKE_BD_EXIT="$exitcode" \
    FAKE_BD_STDOUT="$stdout" \
        "$WRAPPER" "$@" >"$OUT_FILE" 2>"$ERR_FILE"
    RC=$?
}

was_called()     { [ -f "$ARGV_FILE" ]; }
stderr_has()     { grep -qF -- "$1" "$ERR_FILE"; }
stdout_is()      { [ "$(cat "$OUT_FILE")" = "$1" ]; }
stderr_empty()   { [ ! -s "$ERR_FILE" ]; }

# assert_argv <expected argv...> — compares the recorded argv to the expected
# list exactly (order + count).
assert_argv() {
    local expected="${WORK}/expected.txt"
    printf '%s\n' "$@" > "$expected"
    diff -q "$expected" "$ARGV_FILE" >/dev/null 2>&1
}

# ===========================================================================
# 1. update --status in_progress -> violation
# ===========================================================================
run_wrapper warn 7 "" -- update abc-1 --status in_progress
if was_called && assert_argv update abc-1 --status in_progress \
        && [ "$RC" -eq 7 ] && stderr_has "bd update --status in_progress' is non-lifecycle; use --status active"; then
    pass "warn: --status in_progress warns, still execs, passes exit code 7"
else
    fail "warn: --status in_progress (rc=$RC, called=$(was_called && echo y || echo n))"
fi

run_wrapper fail 7 "" -- update abc-1 --status in_progress
if ! was_called && [ "$RC" -ne 0 ] && stderr_has "bd update --status in_progress' is non-lifecycle"; then
    pass "fail: --status in_progress blocks (no exec, non-zero exit, message)"
else
    fail "fail: --status in_progress (rc=$RC, called=$(was_called && echo y || echo n))"
fi

# ===========================================================================
# 2. update --claim -> violation
# ===========================================================================
run_wrapper warn 0 "" -- update abc-2 --claim
if was_called && assert_argv update abc-2 --claim && [ "$RC" -eq 0 ] \
        && stderr_has "bd update --claim' is non-lifecycle; use --status active"; then
    pass "warn: --claim warns, still execs"
else
    fail "warn: --claim"
fi

run_wrapper fail 0 "" -- update abc-2 --claim
if ! was_called && [ "$RC" -ne 0 ] && stderr_has "bd update --claim' is non-lifecycle"; then
    pass "fail: --claim blocks"
else
    fail "fail: --claim"
fi

# ===========================================================================
# 3. lifecycle statuses -> NO violation, passthrough (all 7)
# ===========================================================================
for st in backlog pending-approval ready active acceptance blocked closed; do
    run_wrapper warn 0 "" -- update abc-3 --status "$st"
    if was_called && assert_argv update abc-3 --status "$st" && [ "$RC" -eq 0 ] && stderr_empty; then
        pass "lifecycle status '$st' passes through with no warning"
    else
        fail "lifecycle status '$st' (rc=$RC, stderr=$(cat "$ERR_FILE"))"
    fi
done

# fail mode must NOT block a conformant status either
run_wrapper fail 0 "" -- update abc-3 --status active
if was_called && [ "$RC" -eq 0 ] && stderr_empty; then
    pass "fail-mode: conformant --status active still passes through"
else
    fail "fail-mode: conformant --status active"
fi

# ===========================================================================
# 4. non-update subcommands -> exact passthrough (argv + stdout + exit)
# ===========================================================================
run_wrapper warn 0 "created abc-9" -- create --title "hello world" --status open
if was_called && assert_argv create --title "hello world" --status open \
        && [ "$RC" -eq 0 ] && stdout_is "created abc-9" && stderr_empty; then
    pass "create --status open passes through UNGUARDED (create is out of scope)"
else
    fail "create --status open passthrough"
fi

run_wrapper warn 0 "issue list output" -- list
if was_called && assert_argv list && stdout_is "issue list output" && stderr_empty; then
    pass "list passes through"
else
    fail "list passthrough"
fi

# --json byte-identical passthrough
JSON='{"issues":[{"id":"abc-1","status":"active"}]}'
run_wrapper warn 0 "$JSON" -- show abc-1 --json
if was_called && assert_argv show abc-1 --json && stdout_is "$JSON" && stderr_empty; then
    pass "show --json output is byte-identical, argv exact, stderr clean"
else
    fail "show --json byte-identical (stdout=$(cat "$OUT_FILE"))"
fi

# arbitrary/unknown subcommand
run_wrapper warn 5 "" -- frobnicate --status in_progress
if was_called && assert_argv frobnicate --status in_progress && [ "$RC" -eq 5 ] && stderr_empty; then
    pass "unknown subcommand passes through even with --status in_progress (only 'update' is guarded)"
else
    fail "unknown subcommand passthrough"
fi

# ===========================================================================
# 5. edge argv forms
# ===========================================================================
# --status=in_progress (equals form)
run_wrapper warn 0 "" -- update abc-4 --status=in_progress
if was_called && [ "$RC" -eq 0 ] && stderr_has "bd update --status in_progress' is non-lifecycle"; then
    pass "edge: --status=in_progress (equals form) flagged"
else
    fail "edge: --status=in_progress"
fi

# -s in_progress (short form, separate)
run_wrapper fail 0 "" -- update abc-4 -s in_progress
if ! was_called && [ "$RC" -ne 0 ] && stderr_has "in_progress' is non-lifecycle"; then
    pass "edge: -s in_progress (short form) flagged in fail mode"
else
    fail "edge: -s in_progress"
fi

# -sin_progress (clustered short form)
run_wrapper warn 0 "" -- update -sin_progress abc-4
if was_called && stderr_has "in_progress' is non-lifecycle"; then
    pass "edge: -sin_progress (clustered short form) flagged"
else
    fail "edge: -sin_progress"
fi

# flags reordered: status before the id
run_wrapper warn 0 "" -- update --status in_progress abc-4
if was_called && assert_argv update --status in_progress abc-4 && stderr_has "in_progress' is non-lifecycle"; then
    pass "edge: reordered flags (--status before id) flagged, argv preserved"
else
    fail "edge: reordered flags"
fi

# global flag BEFORE the subcommand
run_wrapper warn 0 "" -- --json update abc-4 --claim
if was_called && assert_argv --json update abc-4 --claim && stderr_has "--claim' is non-lifecycle"; then
    pass "edge: global flag before subcommand (--json update --claim) flagged"
else
    fail "edge: global flag before subcommand"
fi

# value-taking global flag with separate value, then subcommand
run_wrapper warn 0 "" -- -C /some/dir update abc-4 --status in_progress
if was_called && stderr_has "in_progress' is non-lifecycle"; then
    pass "edge: -C /dir update ... still detects the subcommand"
else
    fail "edge: -C /dir update"
fi

# `--` terminator: --status AFTER `--` is positional, NOT a flag -> no warning
run_wrapper warn 0 "" -- update abc-4 -- --status in_progress
if was_called && stderr_empty; then
    pass "edge: '--' terminator makes trailing --status positional (not flagged)"
else
    fail "edge: -- terminator (stderr=$(cat "$ERR_FILE"))"
fi

# value misread guard: a --title value that LOOKS like --claim must NOT flag
run_wrapper warn 0 "" -- update abc-4 --title --claim
if was_called && stderr_empty; then
    pass "edge: --title value '--claim' is not misread as a flag (no warning)"
else
    fail "edge: --title --claim misread (stderr=$(cat "$ERR_FILE"))"
fi

# no args at all -> bare passthrough
run_wrapper warn 0 "" --
if was_called && [ "$RC" -eq 0 ] && stderr_empty; then
    pass "edge: no-args bare passthrough"
else
    fail "edge: no-args"
fi

# unknown mode value behaves as warn (never blocks)
run_wrapper bogusmode 0 "" -- update abc-5 --claim
if was_called && stderr_has "--claim' is non-lifecycle"; then
    pass "edge: unknown MODE value defaults to warn (does not block)"
else
    fail "edge: unknown mode"
fi

# --claim=true (equals form of the boolean) is still a claim
run_wrapper warn 0 "" -- update abc-7 --claim=true
if was_called && stderr_has "--claim' is non-lifecycle"; then
    pass "edge: --claim=true (equals form) flagged"
else
    fail "edge: --claim=true"
fi

# --claim=false is an explicit disable -> NOT a claim, no warning
run_wrapper warn 0 "" -- update abc-7 --claim=false
if was_called && stderr_empty; then
    pass "edge: --claim=false (explicit disable) not flagged"
else
    fail "edge: --claim=false (stderr=$(cat "$ERR_FILE"))"
fi

# root-level `--` BEFORE the subcommand: bd treats the rest as positional (the
# root command prints help), so no `update` runs and nothing is guarded — not
# even a trailing --claim. Must not warn, and must NOT block in fail mode.
run_wrapper warn 0 "" -- -- update abc-6 --claim
if was_called && stderr_empty && [ "$RC" -eq 0 ]; then
    pass "edge: root-level '--' before subcommand is not guarded (no wrong-warn)"
else
    fail "edge: root-level '--' before subcommand (stderr=$(cat "$ERR_FILE"))"
fi

run_wrapper fail 0 "" -- -- update abc-6 --claim
if was_called && stderr_empty && [ "$RC" -eq 0 ]; then
    pass "edge: root-level '--' does not wrong-block in fail mode"
else
    fail "edge: root-level '--' fail-mode wrong-block (rc=$RC)"
fi

# ===========================================================================
# 6. install.sh / rollback.sh round-trip (hermetic host-mutation, temp bin dir)
#    Regression guard for the self-recognition bug (the shipped scripts grepped
#    line 1 for 'bd-guard', but line 1 is the shebang, so rollback always
#    aborted and a partial re-install could relocate the guard onto bd-real ->
#    infinite exec loop). BD_GUARD_BIN_DIR keeps this off /usr/local/bin.
# ===========================================================================
INSTALL="${SCRIPT_DIR}/../install.sh"
ROLLBACK="${SCRIPT_DIR}/../rollback.sh"

# A distinctive stub standing in for the real compiled bd binary.
ORIG_BD="${WORK}/orig-real-bd"
cat > "$ORIG_BD" <<'ORIGBD'
#!/bin/sh
echo "the-genuine-bd v1.0.5 $*"
ORIGBD
chmod +x "$ORIG_BD"

# --- normal install -> rollback round-trip ---
IBIN="${WORK}/ibin"
mkdir -p "$IBIN"
cp "$ORIG_BD" "$IBIN/bd"

BD_GUARD_BIN_DIR="$IBIN" bash "$INSTALL" >/dev/null 2>&1
if cmp -s "$IBIN/bd-real" "$ORIG_BD" && grep -q 'bd-guard-wrapper-sentinel' "$IBIN/bd"; then
    pass "install: real bd relocated to bd-real (byte-identical), guard installed as bd"
else
    fail "install: relocation/guard-install"
fi

# idempotent re-install must not disturb the relocated real bd
BD_GUARD_BIN_DIR="$IBIN" bash "$INSTALL" >/dev/null 2>&1
if cmp -s "$IBIN/bd-real" "$ORIG_BD" && grep -q 'bd-guard-wrapper-sentinel' "$IBIN/bd"; then
    pass "install: idempotent re-run keeps bd-real intact (real bd never clobbered)"
else
    fail "install: idempotent re-run"
fi

# rollback must restore the ORIGINAL bd exactly and remove bd-real
BD_GUARD_BIN_DIR="$IBIN" bash "$ROLLBACK" >/dev/null 2>&1
if cmp -s "$IBIN/bd" "$ORIG_BD" && [ ! -e "$IBIN/bd-real" ]; then
    pass "rollback: original bd restored byte-identical, bd-real removed (TRIVIALLY REMOVABLE holds)"
else
    fail "rollback: restore (bd-real present? $([ -e "$IBIN/bd-real" ] && echo yes || echo no))"
fi

# idempotent rollback: nothing left -> exit 0, bd untouched
BD_GUARD_BIN_DIR="$IBIN" bash "$ROLLBACK" >/dev/null 2>&1; RRC=$?
if [ "$RRC" -eq 0 ] && cmp -s "$IBIN/bd" "$ORIG_BD"; then
    pass "rollback: idempotent re-run is a no-op (exit 0, bd unchanged)"
else
    fail "rollback: idempotent re-run (rc=$RRC)"
fi

# --- partial-install recovery: guard at bd, bd-real MISSING ---
# The old dead check would relocate the guard onto bd-real here, creating an
# infinite bd -> exec bd-real(=guard) loop. Re-install must refuse to do so.
PBIN="${WORK}/pbin"
mkdir -p "$PBIN"
cp "${SCRIPT_DIR}/../bd-guard.sh" "$PBIN/bd"
BD_GUARD_BIN_DIR="$PBIN" bash "$INSTALL" >/dev/null 2>&1
if [ ! -e "$PBIN/bd-real" ] && grep -q 'bd-guard-wrapper-sentinel' "$PBIN/bd"; then
    pass "install: partial state (guard at bd, no bd-real) does NOT relocate guard onto bd-real (no exec loop)"
else
    fail "install: partial-install recovery (bd-real present? $([ -e "$PBIN/bd-real" ] && echo yes || echo no))"
fi

# ===========================================================================
# 7. `bd reopen` subcommand (sets status to the non-lifecycle `open`)
# ===========================================================================
run_wrapper warn 0 "" -- reopen abc-8
if was_called && [ "$RC" -eq 0 ] && stderr_has "bd reopen' is non-lifecycle"; then
    pass "reopen: warns and still execs in warn mode"
else
    fail "reopen: warn (rc=$RC)"
fi

run_wrapper fail 0 "" -- reopen abc-8
if ! was_called && [ "$RC" -ne 0 ] && stderr_has "bd reopen' is non-lifecycle"; then
    pass "reopen: blocks in fail mode (no exec, non-zero exit)"
else
    fail "reopen: fail-mode block (rc=$RC)"
fi

# reopen as a VALUE of a global flag is not the subcommand -> not flagged
run_wrapper warn 0 "" -- --actor reopen list
if was_called && stderr_empty; then
    pass "reopen as --actor value (not the subcommand) is not flagged"
else
    fail "reopen as --actor value (stderr=$(cat "$ERR_FILE"))"
fi

# reopen with a global flag before it is still detected, argv preserved
run_wrapper warn 0 "" -- --json reopen abc-8
if was_called && assert_argv --json reopen abc-8 && stderr_has "bd reopen' is non-lifecycle"; then
    pass "reopen: detected after a global flag, argv preserved"
else
    fail "reopen: after global flag"
fi

# ===========================================================================
# 8. install.sh fresh-provision recovery: a NEW real bd reinstalled over the
#    guard while a STALE bd-real is present must be relocated (preserved), not
#    clobbered by the guard.
# ===========================================================================
FBIN="${WORK}/fbin"
mkdir -p "$FBIN"
NEW_BD="${WORK}/new-real-bd"
cat > "$NEW_BD" <<'NEWBD'
#!/bin/sh
echo "the-NEWER-bd v1.2.0 $*"
NEWBD
chmod +x "$NEW_BD"
printf '#!/bin/sh\necho "stale old bd v1.0.0"\n' > "$FBIN/bd-real"   # stale prior real
cp "$NEW_BD" "$FBIN/bd"                                              # fresh real over guard
BD_GUARD_BIN_DIR="$FBIN" bash "$INSTALL" >/dev/null 2>&1
if cmp -s "$FBIN/bd-real" "$NEW_BD" && grep -q 'bd-guard-wrapper-sentinel' "$FBIN/bd"; then
    pass "install: fresh real bd over guard is relocated to bd-real (newest preserved, not clobbered)"
else
    fail "install: fresh-provision relocate (bd-real is newest? $(cmp -s "$FBIN/bd-real" "$NEW_BD" && echo yes || echo no))"
fi

# ...and a subsequent rollback restores that NEW bd (not the stale one)
BD_GUARD_BIN_DIR="$FBIN" bash "$ROLLBACK" >/dev/null 2>&1
if cmp -s "$FBIN/bd" "$NEW_BD" && [ ! -e "$FBIN/bd-real" ]; then
    pass "rollback: after fresh-provision relocate, restores the NEW bd (stale copy discarded)"
else
    fail "rollback: post-fresh-provision restore"
fi

# ===========================================================================
echo ""
echo "bd-guard tests: ${PASS} passed, ${FAIL} failed"
[ "$FAIL" -eq 0 ]
