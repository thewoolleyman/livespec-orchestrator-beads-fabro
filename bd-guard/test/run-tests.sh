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
# Records exact argv (one per line) to the single argv file (overwritten each
# call), emits controlled streams, and exits controlled.
#
# For MULTI-STEP sequences — specifically the create-normalization two-step
# (real create, then the guard's follow-up `bd update <id> --status backlog`) —
# it ALSO appends one space-joined line per invocation to FAKE_BD_LOG when that
# is set, so BOTH stub calls are assertable (the single argv file only keeps the
# last call). And it honors a per-verb FAKE_BD_UPDATE_EXIT so the follow-up
# `update` can be failed INDEPENDENTLY of the create (to exercise the
# create-enforcement fail-open path).
printf '%s\n' "$@" > "$FAKE_BD_ARGV_FILE"
if [ -n "${FAKE_BD_LOG:-}" ]; then printf '%s\n' "$*" >> "$FAKE_BD_LOG"; fi
if [ "${1:-}" = "update" ] && [ -n "${FAKE_BD_UPDATE_EXIT:-}" ]; then
    exit "$FAKE_BD_UPDATE_EXIT"
fi
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

# Insulate the whole harness from any host-wide mode file at the wrapper's
# default path (/usr/local/etc/livespec-bd-guard.mode). Point MODE_FILE at a
# path guaranteed ABSENT so an installed 'fail' file can never leak into a case
# that does not set LIVESPEC_BD_GUARD_MODE (e.g. the §9 telemetry cases). The
# dedicated mode-file section (§11) overrides this per-invocation.
export LIVESPEC_BD_GUARD_MODE_FILE="${WORK}/no-such-mode-file"

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

# --- create-normalization test infrastructure (§15) -------------------------
# CLOG records EVERY stub invocation (create + any guard follow-up `update`),
# one space-joined line per call, so the two-step is assertable.
CLOG="${WORK}/call-log.txt"

# run_create EXITCODE STDOUT -- <argv...> — run the wrapper with the call log
# enabled and the create stub output/exit set. Mode is left unset (resolves to
# warn — create is never blocked). Captures stdout/stderr/exit into globals.
run_create() {
    local exitcode="$1" stdout="$2"
    shift 2
    [ "$1" = "--" ] && shift
    rm -f "$ARGV_FILE" "$CLOG"
    FAKE_BD_LOG="$CLOG" \
    FAKE_BD_EXIT="$exitcode" \
    FAKE_BD_STDOUT="$stdout" \
        "$WRAPPER" "$@" >"$OUT_FILE" 2>"$ERR_FILE"
    RC=$?
}

# log_lines — count of recorded stub invocations (0 if the log is absent).
log_lines() { if [ -f "$CLOG" ]; then wc -l < "$CLOG" | tr -d ' '; else echo 0; fi; }
# log_has <substr> — the call log contains a line with this substring.
log_has() { [ -f "$CLOG" ] && grep -qF -- "$1" "$CLOG"; }

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
# 4. non-guarded, non-create subcommands -> exact passthrough (argv+stdout+exit).
#    NOTE: create/new/q are NO LONGER exact-passthrough — they are normalized to
#    lifecycle `backlog` (covered comprehensively in §15). This section now only
#    covers the still-exact-passthrough subcommands (list, show, unknown).
# ===========================================================================
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
# 10. --format value-skip: the hidden persistent String flag must have its value
#     CONSUMED so `update` (not `json`) is read as the subcommand. Closes the
#     parser bypass where `--format json update ID --claim` slipped past the
#     guard by mis-reading `json` as the subcommand and stopping.
# ===========================================================================
# fail mode: --format json update ID --claim must BLOCK (bypass closed).
run_wrapper fail 0 "" -- --format json update abc-f1 --claim
if ! was_called && [ "$RC" -eq 3 ] && stderr_has "bd update --claim' is non-lifecycle"; then
    pass "fmt: --format json update --claim blocks in fail mode (bypass closed, no exec, exit 3)"
else
    fail "fmt: --format json update --claim bypass (rc=$RC, called=$(was_called && echo y || echo n))"
fi

# --format json list must still pass through UNGUARDED (list is out of scope);
# proves the value-skip consumes `json` but does not over-consume the real
# subcommand.
run_wrapper warn 0 "issue list output" -- --format json list
if was_called && assert_argv --format json list && [ "$RC" -eq 0 ] && stderr_empty; then
    pass "fmt: --format json list passes through (value skipped, list seen, unguarded)"
else
    fail "fmt: --format json list passthrough (rc=$RC, stderr=$(cat "$ERR_FILE"))"
fi

# ===========================================================================
# 11. Host-wide MODE FILE fallback (precedence: env var > file > warn). The
#     fleet credential wrapper scrubs the env before bd runs, so the FILE — not
#     an exported env var — is the real host-wide switch. LIVESPEC_BD_GUARD_MODE
#     is UNSET for the file cases; the wrapper reads the file at MODE_FILE.
# ===========================================================================
MODE_FILE_T="${WORK}/guard.mode"

# file = fail (env var UNSET) -> update --claim BLOCKS (no exec, exit 3)
printf 'fail\n' > "$MODE_FILE_T"
rm -f "$ARGV_FILE"
LIVESPEC_BD_GUARD_MODE_FILE="$MODE_FILE_T" \
    "$WRAPPER" update abc-m1 --claim >"$OUT_FILE" 2>"$ERR_FILE"; MRC=$?
if ! was_called && [ "$MRC" -eq 3 ] && stderr_has "bd update --claim' is non-lifecycle"; then
    pass "mode-file: file='fail' (env unset) blocks --claim (exit 3, no exec)"
else
    fail "mode-file: file='fail' block (rc=$MRC, called=$(was_called && echo y || echo n))"
fi

# file = warn (env var UNSET) -> passthrough (stub runs) + stderr warning
printf 'warn\n' > "$MODE_FILE_T"
rm -f "$ARGV_FILE"
LIVESPEC_BD_GUARD_MODE_FILE="$MODE_FILE_T" \
    "$WRAPPER" update abc-m2 --claim >"$OUT_FILE" 2>"$ERR_FILE"; MRC=$?
if was_called && [ "$MRC" -eq 0 ] && stderr_has "bd update --claim' is non-lifecycle"; then
    pass "mode-file: file='warn' (env unset) passes through with warning (stub runs)"
else
    fail "mode-file: file='warn' passthrough (rc=$MRC, called=$(was_called && echo y || echo n))"
fi

# env var 'warn' OVERRIDES a 'fail' file -> passthrough (env precedence wins)
printf 'fail\n' > "$MODE_FILE_T"
rm -f "$ARGV_FILE"
LIVESPEC_BD_GUARD_MODE=warn \
LIVESPEC_BD_GUARD_MODE_FILE="$MODE_FILE_T" \
    "$WRAPPER" update abc-m3 --claim >"$OUT_FILE" 2>"$ERR_FILE"; MRC=$?
if was_called && [ "$MRC" -eq 0 ] && stderr_has "bd update --claim' is non-lifecycle"; then
    pass "mode-file: env var 'warn' overrides a 'fail' file (env precedence, passthrough)"
else
    fail "mode-file: env overrides file (rc=$MRC, called=$(was_called && echo y || echo n))"
fi

# ===========================================================================
# 12. Fail-mode BLOCK emits a telemetry span (blocks are OBSERVABLE). The emit
#     is DETACHED, so poll for the stub-emit's output. OTLP left default-ON here;
#     the emit is routed to a stub script (not a real collector) via
#     LIVESPEC_BD_GUARD_EMIT, which appends to a temp file when it runs.
# ===========================================================================
EMIT_STUB="${WORK}/emit-stub.py"
cat > "$EMIT_STUB" <<'EMITSTUB'
import os
p = os.environ.get("EMIT_STUB_OUT", "")
if p:
    with open(p, "a") as f:
        f.write("emitted mode=%s warned=%s exit=%s\n" % (
            os.environ.get("BDG_MODE", ""),
            os.environ.get("BDG_WARNED", ""),
            os.environ.get("BDG_EXIT", ""),
        ))
EMITSTUB
ESTUB_OUT="${WORK}/emit-stub-out.txt"
rm -f "$ESTUB_OUT" "$ARGV_FILE"
LIVESPEC_BD_GUARD_MODE=fail \
LIVESPEC_BD_GUARD_OTLP=on \
LIVESPEC_BD_GUARD_EMIT="$EMIT_STUB" \
EMIT_STUB_OUT="$ESTUB_OUT" \
    "$WRAPPER" update abc-e1 --claim >"$OUT_FILE" 2>"$ERR_FILE"; BRC=$?
if [ "$BRC" -eq 3 ] && ! was_called && poll_capture "$ESTUB_OUT" \
        && grep -q 'mode=fail warned=1 exit=3' "$ESTUB_OUT"; then
    pass "block-emit: fail-mode --claim block emits a span (guard.mode=fail warned=1 exit=3) AND exits 3, no exec"
else
    fail "block-emit: fail-mode block span (rc=$BRC, called=$(was_called && echo y || echo n), emit=$(cat "$ESTUB_OUT" 2>/dev/null))"
fi

# ===========================================================================
# 13. `bd ready --claim` (grab-work -> in_progress) and the `bd defer` SUBCOMMAND
#     (-> non-lifecycle `deferred`). The `ready` subcommand is scanned in a
#     DEDICATED phase that checks ONLY --claim, so a bare `bd ready` list and a
#     `bd ready --status <x>` filter must NEVER be misread as a status write —
#     the critical no-false-positive property (a wrong block of a legit list is
#     the exact incident this guard exists to avoid).
# ===========================================================================
# 13a. ready --claim -> blocks in fail mode (no exec, exit 3).
run_wrapper fail 0 "" -- ready --claim
if ! was_called && [ "$RC" -eq 3 ] && stderr_has "bd ready --claim' is non-lifecycle"; then
    pass "ready: --claim blocks in fail mode (no exec, exit 3, message names 'bd ready --claim')"
else
    fail "ready: --claim fail-mode block (rc=$RC, called=$(was_called && echo y || echo n))"
fi

# 13a'. ready --claim=true (equals form) -> also blocks.
run_wrapper fail 0 "" -- ready --claim=true
if ! was_called && [ "$RC" -eq 3 ] && stderr_has "bd ready --claim' is non-lifecycle"; then
    pass "ready: --claim=true (equals form) blocks in fail mode"
else
    fail "ready: --claim=true fail-mode block (rc=$RC, called=$(was_called && echo y || echo n))"
fi

# 13b. plain `bd ready` list -> PASSES even in fail mode (stub runs, no warning).
run_wrapper fail 0 "issue ready output" -- ready
if was_called && assert_argv ready && [ "$RC" -eq 0 ] && stderr_empty; then
    pass "ready: bare 'bd ready' list passes through in fail mode (no false-positive block)"
else
    fail "ready: bare list passthrough (rc=$RC, stderr=$(cat "$ERR_FILE"))"
fi

# 13b'. ready --json and ready --limit 5 -> PASS (no false positive on flags).
run_wrapper fail 0 "" -- ready --json
if was_called && assert_argv ready --json && [ "$RC" -eq 0 ] && stderr_empty; then
    pass "ready: 'bd ready --json' passes through in fail mode (no false positive)"
else
    fail "ready: --json passthrough (rc=$RC, stderr=$(cat "$ERR_FILE"))"
fi

run_wrapper fail 0 "" -- ready --limit 5
if was_called && assert_argv ready --limit 5 && [ "$RC" -eq 0 ] && stderr_empty; then
    pass "ready: 'bd ready --limit 5' passes through in fail mode (no false positive)"
else
    fail "ready: --limit passthrough (rc=$RC, stderr=$(cat "$ERR_FILE"))"
fi

# 13b''. CRITICAL: `bd ready --status <x>` is a LIST FILTER, not a status write.
#        The ready phase never scans --status, so both a lifecycle and a
#        non-lifecycle filter value MUST pass (a wrong block here is the incident
#        we are preventing). Test both `ready` and `open` filter values.
run_wrapper fail 0 "" -- ready --status ready
if was_called && assert_argv ready --status ready && [ "$RC" -eq 0 ] && stderr_empty; then
    pass "ready: 'bd ready --status ready' list-filter passes (ready phase never checks --status)"
else
    fail "ready: --status ready filter blocked (rc=$RC, stderr=$(cat "$ERR_FILE"))"
fi

run_wrapper fail 0 "" -- ready --status open
if was_called && assert_argv ready --status open && [ "$RC" -eq 0 ] && stderr_empty; then
    pass "ready: 'bd ready --status open' list-filter passes even for a NON-lifecycle value (no false-positive block)"
else
    fail "ready: --status open filter blocked (rc=$RC, stderr=$(cat "$ERR_FILE"))"
fi

# 13c. `bd defer <id>` subcommand -> blocks in fail mode, warns in warn mode.
run_wrapper fail 0 "" -- defer abc-1
if ! was_called && [ "$RC" -eq 3 ] && stderr_has "bd defer' is non-lifecycle"; then
    pass "defer: 'bd defer abc-1' blocks in fail mode (no exec, exit 3)"
else
    fail "defer: fail-mode block (rc=$RC, called=$(was_called && echo y || echo n))"
fi

run_wrapper warn 0 "" -- defer abc-1
if was_called && assert_argv defer abc-1 && [ "$RC" -eq 0 ] && stderr_has "bd defer' is non-lifecycle"; then
    pass "defer: 'bd defer abc-1' warns and still execs in warn mode (argv preserved)"
else
    fail "defer: warn-mode passthrough (rc=$RC, stderr=$(cat "$ERR_FILE"))"
fi

# ===========================================================================
# 14. Mode-file with NO TRAILING NEWLINE resolves to `fail` (footgun fix). The
#     old `read -r MODE < file` returned EOF-nonzero on a newline-less file and
#     the `|| MODE=""` fallback clobbered the valid value, silently degrading
#     `fail` to warn. Write `fail` with `printf` (no newline), env UNSET, and
#     assert a `--claim` is BLOCKED (exit 3, no exec).
# ===========================================================================
MODE_FILE_NN="${WORK}/guard-nonewline.mode"
printf 'fail' > "$MODE_FILE_NN"   # NO trailing newline (printf, not echo)
rm -f "$ARGV_FILE"
LIVESPEC_BD_GUARD_MODE_FILE="$MODE_FILE_NN" \
    "$WRAPPER" update abc-nn --claim >"$OUT_FILE" 2>"$ERR_FILE"; NNRC=$?
if ! was_called && [ "$NNRC" -eq 3 ] && stderr_has "bd update --claim' is non-lifecycle"; then
    pass "mode-file: newline-less 'fail' still resolves to fail and BLOCKS (footgun fixed)"
else
    fail "mode-file: newline-less 'fail' block (rc=$NNRC, called=$(was_called && echo y || echo n))"
fi

# ===========================================================================
# 15. CREATE NORMALIZATION: a QUALIFYING `create`/`new`/`q` is forced to the
#     lifecycle status `backlog` via a guard-side two-step (real create, then
#     `bd update <new-id> --status backlog`). Excluded/batch/dry-run/lifecycle-
#     status creates are NOT forced. Forcing is FAIL-OPEN (a follow-up failure
#     never changes the create's exit code). FAKE_BD_LOG records BOTH stub calls
#     so the two-step is assertable.
# ===========================================================================

# 15a. qualifying create -> follow-up `update <id> --status backlog` with the id
#      the create emitted; create's stdout + exit code preserved. Uses a
#      HYPHENATED-prefix id to prove the extractor handles multi-hyphen prefixes.
run_create 0 "livespec-console-beads-fabro-ble" -- create --title "hello"
if [ "$RC" -eq 0 ] && stdout_is "livespec-console-beads-fabro-ble" \
        && [ "$(log_lines)" -eq 2 ] \
        && log_has "create --title hello" \
        && log_has "update livespec-console-beads-fabro-ble --status backlog"; then
    pass "create: qualifying create forces 'update <id> --status backlog' (id extracted incl. hyphenated prefix), stdout+exit preserved"
else
    fail "create: qualifying two-step (rc=$RC, out=$(cat "$OUT_FILE"), log=$(cat "$CLOG" 2>/dev/null))"
fi

# 15b. HUMAN-format output ('✓ Created issue: <id> — <title>'): the id is the
#      FIRST lowercase-hyphenated token, so it is extracted even when the title
#      itself is hyphenated (id precedes title). Output is preserved.
run_create 0 "$(printf '✓ Created issue: bd-ib-ara4 — my-hyphenated title\n  Priority: P2\n  Status: open')" -- create "my-hyphenated title"
if [ "$RC" -eq 0 ] && grep -qF "bd-ib-ara4" "$OUT_FILE" && grep -qF "Status: open" "$OUT_FILE" \
        && [ "$(log_lines)" -eq 2 ] \
        && log_has "update bd-ib-ara4 --status backlog"; then
    pass "create: human-format id extracted despite a hyphenated title (id is the first token), output preserved"
else
    fail "create: human-format extraction (rc=$RC, out=$(cat "$OUT_FILE"), log=$(cat "$CLOG" 2>/dev/null))"
fi

# 15c. EXCLUSIONS are NOT forced (single stub call, no follow-up update).
# --type=event (equals form)
run_create 0 "bd-ib-ev1" -- create --type=event --title "audit"
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: --type=event is NOT forced (audit event bead)"
else
    fail "create: --type=event exclusion (log=$(cat "$CLOG" 2>/dev/null))"
fi

# --type event (separate form)
run_create 0 "bd-ib-ev2" -- create --type event --title "audit"
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: --type event (separate form) is NOT forced"
else
    fail "create: --type event exclusion (log=$(cat "$CLOG" 2>/dev/null))"
fi

# --ephemeral
run_create 0 "bd-ib-ep1" -- create --ephemeral --title "temp"
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: --ephemeral is NOT forced"
else
    fail "create: --ephemeral exclusion (log=$(cat "$CLOG" 2>/dev/null))"
fi

# --dry-run (nothing is created)
run_create 0 "bd-ib-dr1" -- create --title "preview" --dry-run
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: --dry-run is NOT forced (nothing created)"
else
    fail "create: --dry-run exclusion (log=$(cat "$CLOG" 2>/dev/null))"
fi

# --file (batch): documented first-cut SKIP, left to the store normalizer.
run_create 0 "bd-ib-b1" -- create --file plan.md
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: --file batch is NOT forced (documented first-cut skip; normalizer handles it)"
else
    fail "create: --file batch skip (log=$(cat "$CLOG" 2>/dev/null))"
fi

# --graph (batch)
run_create 0 "bd-ib-b2" -- create --graph plan.json
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: --graph batch is NOT forced"
else
    fail "create: --graph batch skip (log=$(cat "$CLOG" 2>/dev/null))"
fi

# 15d. existing lifecycle --status respected; a NON-lifecycle --status still
#      normalized. (bd v1.0.5 create has no --status; this future-proofs the
#      parser for when beads ships create-time --status.)
run_create 0 "bd-ib-ls1" -- create --status ready --title "x"
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: existing lifecycle --status ready is respected (NOT overridden to backlog)"
else
    fail "create: lifecycle --status not overridden (log=$(cat "$CLOG" 2>/dev/null))"
fi

run_create 0 "bd-ib-ns1" -- create --status open --title "x"
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 2 ] && log_has "update bd-ib-ns1 --status backlog"; then
    pass "create: a NON-lifecycle --status open is still normalized to backlog"
else
    fail "create: non-lifecycle --status normalized (log=$(cat "$CLOG" 2>/dev/null))"
fi

# 15e. FAIL-OPEN: create succeeds (exit 0) but the follow-up update FAILS (exit
#      5) -> the create's exit stays 0, its output is intact, update still tried.
rm -f "$ARGV_FILE" "$CLOG"
FAKE_BD_LOG="$CLOG" \
FAKE_BD_EXIT=0 \
FAKE_BD_UPDATE_EXIT=5 \
FAKE_BD_STDOUT="bd-ib-fo1" \
    "$WRAPPER" create --title "x" >"$OUT_FILE" 2>"$ERR_FILE"; FRC=$?
if [ "$FRC" -eq 0 ] && stdout_is "bd-ib-fo1" && [ "$(log_lines)" -eq 2 ] \
        && log_has "update bd-ib-fo1 --status backlog"; then
    pass "create: follow-up update FAILURE is fail-open (create exit stays 0, output intact, update still attempted)"
else
    fail "create: fail-open on follow-up failure (rc=$FRC, out=$(cat "$OUT_FILE"), log=$(cat "$CLOG" 2>/dev/null))"
fi

# 15f. a FAILED create (exit 4) is NOT forced (forcing only on success).
run_create 4 "" -- create --title "x"
if [ "$RC" -eq 4 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: a FAILED create (exit 4) is not forced (no follow-up update; exit preserved)"
else
    fail "create: failed-create no-force (rc=$RC, log=$(cat "$CLOG" 2>/dev/null))"
fi

# 15g. `bd q` quick-capture and `bd new` alias are also normalized; `bd q --type
#      event` is excluded.
run_create 0 "bd-ib-q1" -- q "quick task"
if [ "$RC" -eq 0 ] && stdout_is "bd-ib-q1" && [ "$(log_lines)" -eq 2 ] \
        && log_has "update bd-ib-q1 --status backlog"; then
    pass "create: 'bd q' quick-capture is normalized to backlog"
else
    fail "create: bd q normalization (rc=$RC, log=$(cat "$CLOG" 2>/dev/null))"
fi

run_create 0 "bd-ib-n1" -- new --title "via alias"
if [ "$RC" -eq 0 ] && stdout_is "bd-ib-n1" && [ "$(log_lines)" -eq 2 ] \
        && log_has "update bd-ib-n1 --status backlog"; then
    pass "create: 'bd new' alias is normalized to backlog"
else
    fail "create: bd new normalization (rc=$RC, log=$(cat "$CLOG" 2>/dev/null))"
fi

run_create 0 "bd-ib-qe1" -- q "event via q" --type event
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: 'bd q --type event' is NOT forced (event bead)"
else
    fail "create: bd q --type event exclusion (log=$(cat "$CLOG" 2>/dev/null))"
fi

# 15h. value-misread guard: a --title value of "--ephemeral" must NOT be read as
#      the exclusion flag -> the create is still forced.
run_create 0 "bd-ib-vm1" -- create --title "--ephemeral"
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 2 ] && log_has "update bd-ib-vm1 --status backlog"; then
    pass "create: a --title value of '--ephemeral' is not misread as the flag (still forced)"
else
    fail "create: value-misread guard (log=$(cat "$CLOG" 2>/dev/null))"
fi

# ===========================================================================
# 16. CREATE-NORMALIZATION HARDENING (fix-forward, from a beads-v1.0.5-source
#     adversarial review): form-anchored id extraction (legacy --json sorts
#     metadata keys BEFORE "id"), tenant/db-selector exclusion (a flag-less
#     follow-up update would hit the WRONG tenant), and the remaining edge forms.
# ===========================================================================

# 16a. BLOCKER 1 — legacy --json output re-marshals with ALPHABETICALLY-SORTED
#      keys, so `assignee`/`created_by`/`description`/`external_ref` precede
#      `"id"`. A `--description` carrying a REAL existing id would fool a naive
#      first-token grep. Assert the follow-up targets the NEW id (from the "id"
#      FIELD), never the id embedded in the description.
JSON_SORTED='{"assignee":"","created_by":"chad","description":"Discovered from bd-ib-3f9a2c","external_ref":"gh-9","id":"bd-ib-newone","issue_type":"task","priority":2,"status":"open","title":"t"}'
run_create 0 "$JSON_SORTED" -- create --title "t" --description "Discovered from bd-ib-3f9a2c" --json
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 2 ] \
        && log_has "update bd-ib-newone --status backlog" \
        && ! log_has "update bd-ib-3f9a2c"; then
    pass "create: legacy --json (sorted keys) — follow-up targets the NEW id from the \"id\" field, NOT a real id inside --description (BLOCKER 1 closed)"
else
    fail "create: legacy-json wrong-token extraction (log=$(cat "$CLOG" 2>/dev/null))"
fi

# 16b. envelope --json (id FIRST in data): id still extracted from the first
#      "id" field.
JSON_ENVELOPE='{"data":{"id":"bd-ib-env1","status":"open","title":"envelope"},"meta":{"ok":true}}'
run_create 0 "$JSON_ENVELOPE" -- create --title "envelope" --json
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 2 ] && log_has "update bd-ib-env1 --status backlog"; then
    pass "create: envelope --json (id-first) — id extracted from the first \"id\" field"
else
    fail "create: envelope-json extraction (log=$(cat "$CLOG" 2>/dev/null))"
fi

# 16c. `bd create --help` prints help TEXT (containing example ids like bd-20)
#      and creates nothing -> excluded, NO follow-up update.
HELP_TXT="$(printf 'Create a new issue (or batch from markdown/graph JSON)\n\nExamples:\n  bd create "Fix bug"\n  bd dep add bd-20 blocks bd-15\n')"
run_create 0 "$HELP_TXT" -- create --help
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: 'bd create --help' is excluded — no follow-up update from help-text ids (bd-20)"
else
    fail "create: --help exclusion (log=$(cat "$CLOG" 2>/dev/null))"
fi

# 16d. `=`-form booleans: --ephemeral=true / --dry-run=true are excluded (a forced
#      --dry-run would echo REAL dep ids for a create that made nothing).
run_create 0 "bd-ib-et1" -- create --ephemeral=true --title "x"
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: --ephemeral=true (=-form) is NOT forced"
else
    fail "create: --ephemeral=true exclusion (log=$(cat "$CLOG" 2>/dev/null))"
fi

run_create 0 "bd-ib-dt1" -- create --dry-run=true --title "x"
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: --dry-run=true (=-form) is NOT forced"
else
    fail "create: --dry-run=true exclusion (log=$(cat "$CLOG" 2>/dev/null))"
fi

# 16d'. ...but an explicit FALSE value DOES create a real item -> still forced
#       (truthy-check, mirroring the --claim=* idiom).
run_create 0 "bd-ib-df1" -- create --dry-run=false --title "x"
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 2 ] && log_has "update bd-ib-df1 --status backlog"; then
    pass "create: --dry-run=false (explicit false) still creates -> still forced (truthy-check)"
else
    fail "create: --dry-run=false still-forced (log=$(cat "$CLOG" 2>/dev/null))"
fi

# 16e. clustered `-fplan.md` batch form is detected -> NOT forced.
run_create 0 "bd-ib-cf1" -- create -fplan.md
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: clustered '-fplan.md' batch is NOT forced (batch detection)"
else
    fail "create: clustered -f batch skip (log=$(cat "$CLOG" 2>/dev/null))"
fi

# 16f. BLOCKER 2 — tenant/db selectors: a create under -C/--db/--global/--repo
#      mints in one tenant while the flag-less follow-up update would hit
#      another. EXCLUDE such creates from forcing (no follow-up update).
run_create 0 "bd-ib-tc1" -- -C /some/other/dir create --title "x"
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: '-C <dir>' create is excluded (wrong-tenant risk; no follow-up) — BLOCKER 2"
else
    fail "create: -C tenant exclusion (log=$(cat "$CLOG" 2>/dev/null))"
fi

run_create 0 "bd-ib-tc2" -- --db /tmp/other.db create --title "x"
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: '--db <path>' create is excluded (wrong-db risk; no follow-up)"
else
    fail "create: --db tenant exclusion (log=$(cat "$CLOG" 2>/dev/null))"
fi

run_create 0 "bd-ib-tc3" -- --global create --title "x"
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: '--global' create is excluded (shared-server db; no follow-up)"
else
    fail "create: --global tenant exclusion (log=$(cat "$CLOG" 2>/dev/null))"
fi

run_create 0 "bd-ib-tc4" -- create --repo other-repo --title "x"
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: '--repo <other>' create is excluded (cross-repo/tenant; no follow-up)"
else
    fail "create: --repo tenant exclusion (log=$(cat "$CLOG" 2>/dev/null))"
fi

# 16f'. clustered '-Cdir' tenant selector also excludes.
run_create 0 "bd-ib-tc5" -- -C/some/dir create --title "x"
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: clustered '-Cdir' tenant selector is excluded (no follow-up)"
else
    fail "create: -Cdir tenant exclusion (log=$(cat "$CLOG" 2>/dev/null))"
fi

# 16g. a plain '--silent' single-id create is STILL forced (regression guard for
#      the extractor's single-token path).
run_create 0 "bd-ib-sil1" -- create --title "x" --silent
if [ "$RC" -eq 0 ] && stdout_is "bd-ib-sil1" && [ "$(log_lines)" -eq 2 ] \
        && log_has "update bd-ib-sil1 --status backlog"; then
    pass "create: '--silent' single-id create is still forced (single-token extraction)"
else
    fail "create: --silent still-forced (rc=$RC, out=$(cat "$OUT_FILE"), log=$(cat "$CLOG" 2>/dev/null))"
fi

# ===========================================================================
# 17. POST-SUBCOMMAND tenant/db selectors. bd is cobra: persistent flags are
#     valid AFTER the subcommand too (that is how `bd create ... --json` works).
#     A selector placed after `create` must exclude the create from forcing just
#     like a pre-subcommand one — otherwise the flag-less follow-up update hits
#     the caller-cwd tenant, not the create's tenant (BLOCKER 2, narrower).
# ===========================================================================

# 17a. `bd create -C /dir --title x` (selector AFTER the subcommand) -> excluded.
run_create 0 "bd-ib-ps1" -- create -C /other/repo --title "x"
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: post-subcommand '-C /dir' is excluded (no follow-up) — narrow BLOCKER 2 hole closed"
else
    fail "create: post-sub -C exclusion (log=$(cat "$CLOG" 2>/dev/null))"
fi

# 17b. `bd create --db /x --title x` (post-subcommand) -> excluded.
run_create 0 "bd-ib-ps2" -- create --db /tmp/other.db --title "x"
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: post-subcommand '--db <path>' is excluded (no follow-up)"
else
    fail "create: post-sub --db exclusion (log=$(cat "$CLOG" 2>/dev/null))"
fi

# 17b'. `bd create --directory /dir` (post-subcommand) -> excluded (value consumed).
run_create 0 "bd-ib-ps3" -- create --directory /other/dir --title "x"
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: post-subcommand '--directory <dir>' is excluded (value consumed)"
else
    fail "create: post-sub --directory exclusion (log=$(cat "$CLOG" 2>/dev/null))"
fi

# 17c. `bd create --global --title x` (post-subcommand boolean) -> excluded.
run_create 0 "bd-ib-ps4" -- create --global --title "x"
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: post-subcommand '--global' is excluded (shared-server db; no follow-up)"
else
    fail "create: post-sub --global exclusion (log=$(cat "$CLOG" 2>/dev/null))"
fi

# 17c'. selector placed AFTER a positional/other flag (not adjacent to create) ->
#       still excluded (position within the create's args is irrelevant).
run_create 0 "bd-ib-ps5" -- create --title "x" -C /other/repo
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: a '-C /dir' after other create flags is still excluded (position-independent)"
else
    fail "create: post-sub trailing -C exclusion (log=$(cat "$CLOG" 2>/dev/null))"
fi

# 17c''. clustered post-subcommand '-Cdir' -> excluded.
run_create 0 "bd-ib-ps6" -- create -C/other/dir --title "x"
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: post-subcommand clustered '-Cdir' is excluded"
else
    fail "create: post-sub -Cdir exclusion (log=$(cat "$CLOG" 2>/dev/null))"
fi

# 17d. PRE-subcommand `--global=true` (=-form) -> excluded (previously swallowed
#      by the generic --*=* skip and left wrongly forced).
run_create 0 "bd-ib-ps7" -- --global=true create --title "x"
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: pre-subcommand '--global=true' (=-form) is excluded"
else
    fail "create: pre-sub --global=true exclusion (log=$(cat "$CLOG" 2>/dev/null))"
fi

# 17d'. post-subcommand `--global=true` -> excluded.
run_create 0 "bd-ib-ps8" -- create --global=true --title "x"
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 1 ] && ! log_has "update "; then
    pass "create: post-subcommand '--global=true' (=-form) is excluded"
else
    fail "create: post-sub --global=true exclusion (log=$(cat "$CLOG" 2>/dev/null))"
fi

# 17e. `--global=false` does NOT select the shared db -> the create is STILL
#      forced (truthy-check, so an explicit-false selector is not an exclusion).
run_create 0 "bd-ib-ps9" -- create --global=false --title "x"
if [ "$RC" -eq 0 ] && [ "$(log_lines)" -eq 2 ] && log_has "update bd-ib-ps9 --status backlog"; then
    pass "create: '--global=false' is NOT a selector -> create still forced (truthy-check)"
else
    fail "create: --global=false still-forced (log=$(cat "$CLOG" 2>/dev/null))"
fi

# ===========================================================================
echo ""
echo "bd-guard tests: ${PASS} passed, ${FAIL} failed"
[ "$FAIL" -eq 0 ]
