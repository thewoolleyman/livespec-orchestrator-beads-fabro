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

# Telemetry is default-ON in the wrapper, but the hermetic suite must (a) keep
# every EXISTING case a pure `exec` passthrough — the exact argv/stream/exit
# semantics those cases assert — and (b) NEVER emit a span to a real collector on
# a maintainer's host (a live OTLP endpoint may be listening at :4319). So
# default telemetry OFF for the whole harness; the dedicated telemetry section
# (§9) opts back IN per-invocation, always pointed at a throwaway capture server
# or a dead port, never the real endpoint.
export LIVESPEC_BD_GUARD_OTLP=off

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

# --- OTLP telemetry test infrastructure -------------------------------------
# A throwaway HTTP capture server: binds a RANDOM loopback port, appends each
# received POST body (one JSON object per line) to $1, and writes the chosen
# port to $2 so the caller can point the wrapper's emitter at it. Runs until
# killed. Stdlib http.server only — no network, no external deps.
CAP_PY="${WORK}/capture.py"
cat > "$CAP_PY" <<'CAPPY'
import http.server, sys
OUT, PORTF = sys.argv[1], sys.argv[2]
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(n)
        with open(OUT, "ab") as f:
            f.write(body)
            f.write(b"\n")
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()
    def log_message(self, *a):  # silence access log
        return
srv = http.server.HTTPServer(("127.0.0.1", 0), H)
with open(PORTF, "w") as f:
    f.write(str(srv.server_address[1]))
srv.serve_forever()
CAPPY

# A JSON payload verifier: parses the LAST captured OTLP object and asserts the
# bd.invoke span shape. Args: <capture-file> <subcommand> <warned:true|false>
# <exit_code>. Parsing (not grepping) makes it whitespace-insensitive.
VERIFY_PY="${WORK}/verify.py"
cat > "$VERIFY_PY" <<'VERIFYPY'
import json, sys
path, sub, warned, exit_code = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
lines = [b for b in open(path, "rb").read().splitlines() if b.strip()]
obj = json.loads(lines[-1])
rs = obj["resourceSpans"][0]
res = {a["key"]: a["value"] for a in rs["resource"]["attributes"]}
assert res["service.name"]["stringValue"] == "bd-guard", res
span = rs["scopeSpans"][0]["spans"][0]
assert span["name"] == "bd.invoke", span["name"]
attrs = {a["key"]: a["value"] for a in span["attributes"]}
assert attrs["bd.subcommand"]["stringValue"] == sub, attrs["bd.subcommand"]
assert attrs["guard.warned"]["boolValue"] is (warned == "true"), attrs["guard.warned"]
assert attrs["exit_code"]["intValue"] == exit_code, attrs["exit_code"]
assert span["status"]["code"] == (2 if exit_code != "0" else 1), span["status"]
sys.exit(0)
VERIFYPY

CAP_PID=""
CAP_PORT=""
# start_capture <out-file> <port-file> — launch the capture server and block
# (up to ~2s) until it has published its port into CAP_PORT.
start_capture() {
    rm -f "$1" "$2"
    python3 "$CAP_PY" "$1" "$2" &
    CAP_PID=$!
    local i=0
    while [ ! -s "$2" ] && [ "$i" -lt 40 ]; do
        sleep 0.05
        i=$((i + 1))
    done
    CAP_PORT="$(cat "$2" 2>/dev/null || echo "")"
}
# stop_capture — kill the capture server if running.
stop_capture() {
    if [ -n "$CAP_PID" ]; then
        kill "$CAP_PID" 2>/dev/null
        wait "$CAP_PID" 2>/dev/null
    fi
    CAP_PID=""
}
# poll_capture <out-file> — wait up to ~2s for at least one captured POST body
# (the emit is DETACHED/async, so it may land shortly after the wrapper returns).
poll_capture() {
    local i=0
    while [ "$i" -lt 40 ]; do
        [ -s "$1" ] && return 0
        sleep 0.05
        i=$((i + 1))
    done
    return 1
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
# 9. OTLP telemetry (default-ON in the wrapper; opted-in here per-invocation).
#    The wrapper fires a DETACHED, FAIL-OPEN `bd.invoke` span AFTER running the
#    real bd, so bd's stdout/stderr/exit are never affected. These cases point
#    the emitter at a throwaway capture server (or a dead port) — never a real
#    collector — and prove: emit-happens + payload shape, fail-open on a dead
#    endpoint, no-emit when disabled, and exit-code fidelity with telemetry ON.
# ===========================================================================
TCAP="${WORK}/tel-cap.txt"
TPORT="${WORK}/tel-port.txt"

# 9.1 emit happens + payload shape. Real bd = /bin/echo, so passthrough stdout
#     genuinely reflects argv. `--claim` is a warn-mode violation -> warned=true.
start_capture "$TCAP" "$TPORT"
if [ -n "$CAP_PORT" ]; then
    LIVESPEC_BD_REAL=/bin/echo \
    LIVESPEC_BD_GUARD_OTLP=on \
    LIVESPEC_BD_GUARD_OTLP_ENDPOINT="http://127.0.0.1:${CAP_PORT}/v1/traces" \
        "$WRAPPER" update x --claim >"$OUT_FILE" 2>"$ERR_FILE"
    TRC=$?
    if [ "$TRC" -eq 0 ] && stdout_is "update x --claim" \
            && poll_capture "$TCAP" \
            && python3 "$VERIFY_PY" "$TCAP" update true 0; then
        pass "telemetry: bd.invoke span emitted (service.name=bd-guard, subcommand=update, warned=true, exit=0) AND bd passthrough intact (stdout+exit)"
    else
        fail "telemetry: emit/payload shape (rc=$TRC, stdout=$(cat "$OUT_FILE"), cap=$(cat "$TCAP" 2>/dev/null))"
    fi
else
    fail "telemetry: capture server did not start (9.1)"
fi
stop_capture

# 9.2 fail-open when the endpoint is dead. Point at a refused port; the emit is
#     detached, so the wrapper returns immediately and bd is unaffected — no
#     multi-second hang regardless of the collector being down.
T92_START=$(date +%s)
LIVESPEC_BD_REAL=/bin/echo \
LIVESPEC_BD_GUARD_OTLP=on \
LIVESPEC_BD_GUARD_OTLP_ENDPOINT="http://127.0.0.1:1/v1/traces" \
    "$WRAPPER" list >"$OUT_FILE" 2>"$ERR_FILE"
T92_RC=$?
T92_ELAPSED=$(( $(date +%s) - T92_START ))
if [ "$T92_RC" -eq 0 ] && stdout_is "list" && stderr_empty && [ "$T92_ELAPSED" -lt 2 ]; then
    pass "telemetry: dead endpoint is fail-open (bd stdout/exit unchanged, returns promptly in ${T92_ELAPSED}s)"
else
    fail "telemetry: dead-endpoint fail-open (rc=$T92_RC, elapsed=${T92_ELAPSED}s, stdout=$(cat "$OUT_FILE"), stderr=$(cat "$ERR_FILE"))"
fi

# 9.3 disabled -> transparent passthrough, NO emit attempted.
start_capture "$TCAP" "$TPORT"
if [ -n "$CAP_PORT" ]; then
    LIVESPEC_BD_REAL=/bin/echo \
    LIVESPEC_BD_GUARD_OTLP=off \
    LIVESPEC_BD_GUARD_OTLP_ENDPOINT="http://127.0.0.1:${CAP_PORT}/v1/traces" \
        "$WRAPPER" list >"$OUT_FILE" 2>"$ERR_FILE"
    TRC=$?
    sleep 0.3   # give any (erroneous) emit time to arrive before asserting none did
    if [ "$TRC" -eq 0 ] && stdout_is "list" && [ ! -s "$TCAP" ]; then
        pass "telemetry: LIVESPEC_BD_GUARD_OTLP=off is transparent passthrough (no span emitted)"
    else
        fail "telemetry: disabled still emitted (rc=$TRC, cap=$(cat "$TCAP" 2>/dev/null))"
    fi
else
    fail "telemetry: capture server did not start (9.3)"
fi
stop_capture

# 9.4 exit-code fidelity with telemetry ON. Real bd = /bin/false (exits 1); the
#     wrapper must still exit 1, and the emitted span must reflect exit_code=1 +
#     error status. Capture-backed so we prove the emit rides along, not just
#     that bd's code is preserved. (Dead-safe: capture, never a real collector.)
start_capture "$TCAP" "$TPORT"
if [ -n "$CAP_PORT" ]; then
    LIVESPEC_BD_REAL=/bin/false \
    LIVESPEC_BD_GUARD_OTLP=on \
    LIVESPEC_BD_GUARD_OTLP_ENDPOINT="http://127.0.0.1:${CAP_PORT}/v1/traces" \
        "$WRAPPER" list >"$OUT_FILE" 2>"$ERR_FILE"
    TRC=$?
    if [ "$TRC" -eq 1 ] && poll_capture "$TCAP" \
            && python3 "$VERIFY_PY" "$TCAP" list false 1; then
        pass "telemetry ON: nonzero real bd exit (1) preserved by wrapper AND span reflects exit_code=1 + error status"
    else
        fail "telemetry: exit-code fidelity (rc=$TRC expected 1, cap=$(cat "$TCAP" 2>/dev/null))"
    fi
else
    fail "telemetry: capture server did not start (9.4)"
fi
stop_capture

# 9.5 install.sh lays down bd-guard-emit.py beside the wrapper; rollback removes
#     it. Reuses the same temporary BD_GUARD_BIN_DIR discipline as §6.
EBIN="${WORK}/ebin"
mkdir -p "$EBIN"
cp "$ORIG_BD" "$EBIN/bd"
BD_GUARD_BIN_DIR="$EBIN" bash "$INSTALL" >/dev/null 2>&1
if [ -x "$EBIN/bd-guard-emit.py" ] \
        && cmp -s "$EBIN/bd-guard-emit.py" "${SCRIPT_DIR}/../bd-guard-emit.py"; then
    pass "install: bd-guard-emit.py laid down next to the wrapper (0755, byte-identical to source)"
else
    fail "install: emit helper install (present? $([ -e "$EBIN/bd-guard-emit.py" ] && echo yes || echo no))"
fi

BD_GUARD_BIN_DIR="$EBIN" bash "$ROLLBACK" >/dev/null 2>&1
if [ ! -e "$EBIN/bd-guard-emit.py" ] && cmp -s "$EBIN/bd" "$ORIG_BD" && [ ! -e "$EBIN/bd-real" ]; then
    pass "rollback: bd-guard-emit.py removed, original bd restored, bd-real gone (trivially removable holds)"
else
    fail "rollback: emit-helper removal (emit present? $([ -e "$EBIN/bd-guard-emit.py" ] && echo yes || echo no))"
fi

# rollback tolerates a MISSING emit helper (older install predating it): remove
# it by hand, then rollback again from a fresh install -> still succeeds.
cp "$ORIG_BD" "$EBIN/bd"
BD_GUARD_BIN_DIR="$EBIN" bash "$INSTALL" >/dev/null 2>&1
rm -f "$EBIN/bd-guard-emit.py"
BD_GUARD_BIN_DIR="$EBIN" bash "$ROLLBACK" >/dev/null 2>&1; ERC=$?
if [ "$ERC" -eq 0 ] && cmp -s "$EBIN/bd" "$ORIG_BD" && [ ! -e "$EBIN/bd-real" ]; then
    pass "rollback: absent emit helper does not fail the rollback (best-effort removal)"
else
    fail "rollback: absent-emit tolerance (rc=$ERC)"
fi

# ===========================================================================
echo ""
echo "bd-guard tests: ${PASS} passed, ${FAIL} failed"
[ "$FAIL" -eq 0 ]
