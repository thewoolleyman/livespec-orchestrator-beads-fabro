#!/usr/bin/env bash
# PROVISIONAL / EXPERIMENTAL — part of fleet-launch/, a stopgap whose first-class
# replacements are the livespec console application and the committed launch-loop
# tool bd-ib-jr6w7v (see fleet-launch/README.md).
#
# Hermetic test harness for dispatch-dual.sh, the provisional launcher.
#
# WHY A HARNESS AND NOT A SYNTAX CHECK. `bash -n` accepts a launcher that has
# silently stopped reading a factory board: the edit that appended a trailing
# comment to a multi-statement line dropped the mi-homelab board read on
# 2026-10-24 and parsed perfectly. `SPECIFICATION/contracts.md` §"Provisional
# fleet launch scripts" therefore states outright that "A syntax check alone
# MUST NOT be treated as satisfying this obligation", and names the five gates
# the cases below exercise.
#
# HOW IT IS HERMETIC. Every host value dispatch-dual.sh reads is assigned in
# config.sh behind a `FLEET_LAUNCH_` environment override, so the launcher is
# pointed at a stub `fabro` serving board FIXTURES, a stub credential wrapper
# that answers for the ready-set check, the Definition-of-Done preflight, the
# credential probe and `drive.py`, a stub `ssh` on a prepended PATH, and
# throwaway queue, lock, in-flight and state directories. No real factory, no
# real `drive` dispatch, no network, no host mutation. bash plus POSIX utilities
# only, so it runs on any runner.
#
# EVERY REFUSAL CASE CARRIES ITS OWN POSITIVE CONTROL — the same inputs with the
# one gate opened, which MUST launch. A refusal that is never contrasted with a
# launch passes equally well when the launcher refuses everything, which is the
# failure this directory's README records as its most expensive defect.
#
# Exit 0 iff every case passes; non-zero with a summary otherwise.

set -uo pipefail

HARNESS_DIR=$(cd -- "$(dirname -- "$0")" && pwd -P)
LAUNCH_DIR=$(cd -- "$HARNESS_DIR/.." && pwd -P)
LAUNCHER="$LAUNCH_DIR/dispatch-dual.sh"

if [ ! -f "$LAUNCHER" ]; then
    echo "run-tests.sh: launcher not found: $LAUNCHER" >&2
    exit 1
fi

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

PASS=0
FAIL=0
pass() { PASS=$((PASS + 1)); printf '  ok:   %s\n' "$1"; }
fail() { FAIL=$((FAIL + 1)); printf '  FAIL: %s\n' "$1" >&2; }

# The two stub server URLs. They are opaque to the launcher, which only passes
# them to `fabro ps -a --server`, so the stub discriminates boards on them.
GMK_URL="https://stub-gmktec.invalid:32276"
HL_URL="https://stub-mi-homelab.invalid:32277"

# --- the stubs ---------------------------------------------------------------
STUB="$WORK/stub"
mkdir -p "$STUB/bin"

# The stub `fabro`. `ps -a --server <url>` answers from a board FIXTURE file:
#   absent file  -> exit 1, which the launcher must read as an UNREADABLE board
#   empty file   -> exit 0 with nothing on stdout, a RETIRED/idle board
#   otherwise    -> the fixture, header line first
# It also lists one synthetic row per driven marker the stub `drive.py` wrote
# for that server, so a launch that has dispatched becomes visible on the board
# exactly as a real run does.
cat > "$STUB/fabro" <<'FABRO_STUB'
#!/usr/bin/env bash
set -u
server=""
previous=""
for argument in "$@"; do
    if [ "$previous" = --server ]; then server=$argument; fi
    previous=$argument
done
case $server in
    "$STUB_SERVER_GMK") board=$STUB_BOARD_GMK ;;
    "$STUB_SERVER_HL") board=$STUB_BOARD_HL ;;
    *) echo "stub fabro: no board fixture for server '$server'" >&2; exit 1 ;;
esac
# An absent fixture is the unreadable board: non-zero exit, nothing on stdout.
if [ ! -f "$board" ]; then
    echo "stub fabro: board unreadable" >&2
    exit 1
fi
rows="$(mktemp)"
trap 'rm -f "$rows"' EXIT
if [ -s "$board" ]; then tail -n +2 "$board" >> "$rows"; fi
for marker in "$STUB_DRIVEN_DIR"/*; do
    [ -e "$marker" ] || continue
    marker_server=$(cut -d' ' -f1 "$marker")
    marker_item=$(cut -d' ' -f2 "$marker")
    [ "$marker_server" = "$server" ] || continue
    printf 'DRIVEN000001 stub-repo running 2026-10-25 0m05s %s\n' "$marker_item" >> "$rows"
done
# An idle board says so with an exit of zero and an empty stdout; `No runs
# found.` goes to stderr, which is what the launcher counts as a real zero.
if [ ! -s "$rows" ] && [ ! -s "$board" ]; then
    echo "No runs found." >&2
    exit 0
fi
printf 'RUN ID       REPO      STATUS    DATE       DURATION  ITEM\n'
cat "$rows"
FABRO_STUB

# The stub credential wrapper, invoked as `wrapper -- <command...>`. It answers
# for each command the launcher routes through the wrapper, keyed on the
# BASENAME of the script being run, and records every `drive.py` dispatch.
cat > "$STUB/wrapper" <<'WRAPPER_STUB'
#!/usr/bin/env bash
set -u
if [ "${1:-}" = -- ]; then shift; fi
for argument in "$@"; do
    case ${argument##*/} in
        ready-set-check.py)
            printf 'READY-CHECK stub: in the ready set\n'
            exit "${STUB_READY_EXIT:-0}"
            ;;
        dod-preflight.sh)
            item=${!#}
            printf '%s %s\n' "$(date +%s%N)" "$item" >> "$STUB_PREFLIGHT_LOG"
            if [ "$item" = "${STUB_PREFLIGHT_SLOW_ITEM:-}" ]; then
                # HELD until the harness creates the release file (bounded by
                # STUB_PREFLIGHT_SLOW_S), not slept for a fixed time.  The older
                # launcher therefore cannot bind before the harness has seen the
                # younger launcher's queued preflight, however slow the host is.
                # A fixed sleep raced launcher start-up and failed under CI load
                # (bd-ib-x7bwug, PR #4235).
                held=0
                while [ ! -e "${STUB_PREFLIGHT_RELEASE:-/nonexistent}" ] && [ "$held" -lt "$STUB_PREFLIGHT_SLOW_S" ]; do
                    sleep 1
                    held=$((held + 1))
                done
            fi
            if [ "$item" = "${STUB_PREFLIGHT_FAIL_ITEM:-}" ]; then
                printf 'stub queued preflight failure\n'
                exit 1
            fi
            printf 'stub launch-time Definition-of-Done preflight\n'
            exit "${STUB_PREFLIGHT_EXIT:-0}"
            ;;
        dispatcher.py)
            printf 'stub: the Claude credential is usable (HTTP 200)\n'
            exit 0
            ;;
        drive.py)
            item=""
            for token in "$@"; do
                case $token in impl:*) item=${token#impl:} ;; esac
            done
            case ${LIVESPEC_FABRO_FACTORY:-} in
                petri) server=$STUB_SERVER_GMK ;;
                mi-homelab) server=$STUB_SERVER_HL ;;
                *) server="" ;;
            esac
            printf '%s\n' "$item" >> "$STUB_DRIVE_LOG"
            if [ -d "$STUB_LOCK_DIR" ]; then
                # A preceding launcher releases the mutex before it begins its
                # drive, so a following launcher may legitimately acquire it
                # first.  Record both items: only the driving launcher's own
                # held mutex violates the launcher's narrow mutex scope.
                holder_item=$(grep -oE 'item=[^ ]+' "$STUB_LOCK_DIR/holder" 2>/dev/null | head -1 | cut -d= -f2)
                if [ -n "$holder_item" ]; then
                    printf 'held driver=%s holder=%s\n' "$item" "$holder_item" >> "$STUB_DRIVE_MUTEX_LOG"
                else
                    # release_lock removes holder before rmdir, leaving a
                    # short, harmless directory-only observation window.
                    printf 'released %s\n' "$item" >> "$STUB_DRIVE_MUTEX_LOG"
                fi
            else
                printf 'released %s\n' "$item" >> "$STUB_DRIVE_MUTEX_LOG"
            fi
            if [ -n "$item" ] && [ -n "$server" ]; then
                printf '%s %s\n' "$server" "$item" > "$STUB_DRIVEN_DIR/$item"
            fi
            printf '{"status": "stub-dispatched", "work_item_id": "%s"}\n' "$item"
            exit 0
            ;;
    esac
done
exec "$@"
WRAPPER_STUB

# The stub `ssh`, reached on a prepended PATH. The launcher asks the factory
# host for its idle CPU and for the server env that carries the dev token; both
# answers are canned and neither leaves this machine.
cat > "$STUB/bin/ssh" <<'SSH_STUB'
#!/usr/bin/env bash
set -u
command_line=$*
case $command_line in
    *mpstat*)
        printf 'Linux stub\n\n'
        printf 'Average:     all    1.00    0.00    0.00    %s\n' "${STUB_SSH_IDLE:-95.00}"
        ;;
    *cat*) printf 'FABRO_DEV_TOKEN=stub-dev-token\n' ;;
    *) echo "stub ssh: unexpected command: $command_line" >&2; exit 1 ;;
esac
SSH_STUB

chmod +x "$STUB/fabro" "$STUB/wrapper" "$STUB/bin/ssh"

# --- the throwaway tenant repository ----------------------------------------
# The launcher fast-forwards the tenant repository to origin/master before it
# dispatches, so the stub tenant is a real clone of a real bare origin rather
# than a stubbed `git`.
ORIGIN="$WORK/origin.git"
TENANT="$WORK/tenant"
GIT_IDENTITY=(-c user.name=fleet-launch-harness -c user.email=harness@invalid -c commit.gpgsign=false)
git init --quiet --bare --initial-branch=master "$ORIGIN"
git "${GIT_IDENTITY[@]}" init --quiet --initial-branch=master "$WORK/seed"
: > "$WORK/seed/README"
git -C "$WORK/seed" "${GIT_IDENTITY[@]}" add README
git -C "$WORK/seed" "${GIT_IDENTITY[@]}" commit --quiet --no-verify -m "seed"
git -C "$WORK/seed" "${GIT_IDENTITY[@]}" push --quiet "$ORIGIN" master
git "${GIT_IDENTITY[@]}" clone --quiet "$ORIGIN" "$TENANT"

# --- the stub plugin install -------------------------------------------------
# `installed_build` reads the plugin registry to resolve the build this tenant
# is bound to, and the launcher reads that build's own plugin.json for the
# version it logs. Both are files, so both are fixtures.
PLUGIN_KEY="livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"
PLUGIN_CACHE="$WORK/plugins/cache"
PLUGIN_BUILD="stubbuild000"
mkdir -p "$PLUGIN_CACHE/$PLUGIN_BUILD/scripts/bin"
printf '{"version": "0.0.0-stub"}\n' > "$PLUGIN_CACHE/$PLUGIN_BUILD/plugin.json"
REGISTRY="$WORK/plugins/installed_plugins.json"
cat > "$REGISTRY" <<REGISTRY_FIXTURE
{"plugins": {"$PLUGIN_KEY": [{"version": "$PLUGIN_BUILD", "projectPath": "$TENANT"}]}}
REGISTRY_FIXTURE

# --- per-case state ----------------------------------------------------------
# A board fixture holding one live run per line, plus the terminal rows a real
# board carries. A launcher that counted terminal runs would read five live
# runs where there are two, so every fixture carries both kinds.
BOARD_HEADER='RUN ID       REPO      STATUS    DATE       DURATION  ITEM'

# write_board <file> <live-count> <item-prefix>: a board with <live-count> live
# runs and three terminal runs that MUST NOT be counted.
write_board() {
    local file="$1" live="$2" prefix="$3" index=1
    printf '%s\n' "$BOARD_HEADER" > "$file"
    while [ "$index" -le "$live" ]; do
        printf 'LIVE00000%03d stub-repo running   2026-10-25 1m%02ds     %s-live-%d\n' \
            "$index" "$index" "$prefix" "$index" >> "$file"
        index=$((index + 1))
    done
    printf 'DONE00000001 stub-repo succeeded 2026-10-25 9m00s     %s-done-1\n' "$prefix" >> "$file"
    printf 'DONE00000002 stub-repo failed    2026-10-25 9m00s     %s-done-2\n' "$prefix" >> "$file"
    printf 'DONE00000003 stub-repo cancelled 2026-10-25 9m00s     %s-done-3\n' "$prefix" >> "$file"
}

CASE_DIR=""
CASE_LOG=""
DRIVE_LOG=""
DRIVE_MUTEX_LOG=""
PREFLIGHT_LOG=""
BOARD_GMK=""
BOARD_HL=""
CAP_FILE=""
HOLD_FILE=""

# new_case <name>: a fresh set of throwaway directories and fixtures, and the
# environment every launcher invocation of this case inherits.
new_case() {
    CASE_DIR="$WORK/case/$1"
    mkdir -p "$CASE_DIR"/{boards,state,inflight,queue,lock,driven}
    rmdir "$CASE_DIR/lock"
    CASE_LOG="$CASE_DIR/launcher.log"
    DRIVE_LOG="$CASE_DIR/drive-log"
    : > "$DRIVE_LOG"
    DRIVE_MUTEX_LOG="$CASE_DIR/drive-mutex-log"
    : > "$DRIVE_MUTEX_LOG"
    PREFLIGHT_LOG="$CASE_DIR/preflight-log"
    : > "$PREFLIGHT_LOG"
    BOARD_GMK="$CASE_DIR/boards/gmktec"
    BOARD_HL="$CASE_DIR/boards/mi-homelab"
    CAP_FILE="$CASE_DIR/state/fleet-cap"
    HOLD_FILE="$CASE_DIR/state/hold-gmktec"

    export PATH="$STUB/bin:$PATH"
    export STUB_SERVER_GMK="$GMK_URL"
    export STUB_SERVER_HL="$HL_URL"
    export STUB_BOARD_GMK="$BOARD_GMK"
    export STUB_BOARD_HL="$BOARD_HL"
    export STUB_DRIVEN_DIR="$CASE_DIR/driven"
    export STUB_DRIVE_LOG="$DRIVE_LOG"
    export STUB_DRIVE_MUTEX_LOG="$DRIVE_MUTEX_LOG"
    export STUB_PREFLIGHT_LOG="$PREFLIGHT_LOG"
    export STUB_READY_EXIT=0
    export STUB_PREFLIGHT_EXIT=0
    unset STUB_PREFLIGHT_SLOW_ITEM STUB_PREFLIGHT_SLOW_S STUB_PREFLIGHT_FAIL_ITEM
    export STUB_PREFLIGHT_RELEASE="$CASE_DIR/release-held-preflight"
    export STUB_SSH_IDLE=95.00

    export REPO_OVERRIDE="$TENANT"
    export WRAPPER="$STUB/wrapper"
    export FLEET_LAUNCH_ORCH_REPO="$CASE_DIR/orch-repo"
    export FLEET_LAUNCH_SEAT="harness-seat"
    export FLEET_LAUNCH_STATE_DIR="$CASE_DIR/state"
    export FLEET_LAUNCH_FLEET_CAP_FILE="$CAP_FILE"
    export FLEET_LAUNCH_HOLD_FILE="$HOLD_FILE"
    export FLEET_LAUNCH_GMK_SERVER="$GMK_URL"
    export FLEET_LAUNCH_HL_SERVER="$HL_URL"
    export FLEET_LAUNCH_GMK_SSH="stub-factory-host"
    export FLEET_LAUNCH_GMK_SERVER_ENV="$CASE_DIR/state/server.env"
    export FLEET_LAUNCH_GMK_CAP=8
    export FLEET_LAUNCH_HL_CAP=2
    export FLEET_LAUNCH_GMK_MIN_IDLE=25
    export FLEET_LAUNCH_FABRO="$STUB/fabro"
    export FLEET_LAUNCH_INFLIGHT_DIR="$CASE_DIR/inflight"
    export FLEET_LAUNCH_GMK_QUEUE_DIR="$CASE_DIR/queue"
    export FLEET_LAUNCH_GMK_LOCK_DIR="$CASE_DIR/lock"
    export STUB_LOCK_DIR="$FLEET_LAUNCH_GMK_LOCK_DIR"
    export FLEET_LAUNCH_PLUGIN_REGISTRY="$REGISTRY"
    export FLEET_LAUNCH_PLUGIN_CACHE="$PLUGIN_CACHE"
    export FLEET_LAUNCH_PLUGIN_KEY="$PLUGIN_KEY"
    export FLEET_LAUNCH_DEFAULT_WRAPPER="$STUB/wrapper"
    # A short wait and a one-second poll: a refusal case must reach its
    # give-up exit in seconds rather than in the six hours a real launcher waits.
    export FLEET_LAUNCH_MAX_WAIT_S=4
    export FLEET_LAUNCH_ABANDON_S=60
    export FLEET_LAUNCH_POLL_S=1
    export FLEET_LAUNCH_PREFLIGHT_REUSE_S=600
    export FLEET_LAUNCH_MUTEX_HOLD_S=60
    unset ONLY_GMK ONLY_HL CAPTURE_NULL CAPTURE_EXPECT TICKET_NS REWORK RELEASE_BLOCKED
}

# run_launcher <item> [log]: one launcher invocation, captured. Sets RC.
run_launcher() {
    local item="$1" log="${2:-$CASE_LOG}"
    "$LAUNCHER" "$item" > "$log" 2>&1
    RC=$?
}

log_has() { grep -qF -- "$2" "$1"; }
drive_log_items() { tr '\n' ' ' < "$DRIVE_LOG" | sed 's/ *$//'; }
preflight_count() { grep -c " $1$" "$PREFLIGHT_LOG" 2>/dev/null || true; }

# wait_for_preflight <item> <count> <seconds>: wait until the stub recorded a
# particular number of Definition-of-Done preflights for an item.
wait_for_preflight() {
    local item="$1" count="$2" limit="$3" waited=0
    while [ "$waited" -lt "$limit" ]; do
        if [ "$(preflight_count "$item")" -ge "$count" ]; then return 0; fi
        sleep 1
        waited=$((waited + 1))
    done
    return 1
}

# await_both <pid> <pid> <seconds>: wait for two launchers to exit, terminating
# whichever is still running at the bound. Sets FIRST_RC and SECOND_RC; a
# terminated launcher reports 143, which fails the exit assertion as it should.
#
# THE HARNESS BOUNDS THIS ITSELF rather than leaning on the launchers' own
# give-up deadline, which the FIFO case raises deliberately. Against a BROKEN
# launcher the two queued launchers can never dispatch, so waiting out their
# deadlines made this one case cost minutes and left the gate slowest exactly
# when it is reporting a defect. The two are awaited TOGETHER for the same
# reason: awaited in turn, the second bound starts only once the first has
# expired, so the cost is the sum rather than the maximum.
FIRST_RC=""
SECOND_RC=""
await_both() {
    local first="$1" second="$2" limit="$3" waited=0
    while [ "$waited" -lt "$limit" ]; do
        if ! kill -0 "$first" 2>/dev/null && ! kill -0 "$second" 2>/dev/null; then break; fi
        sleep 1
        waited=$((waited + 1))
    done
    kill -TERM "$first" "$second" 2>/dev/null
    wait "$first"; FIRST_RC=$?
    wait "$second"; SECOND_RC=$?
}

# wait_for_line <log> <needle> <seconds>: poll one launcher's log for a line.
wait_for_line() {
    local log="$1" needle="$2" limit="$3" waited=0
    while [ "$waited" -lt "$limit" ]; do
        if [ -f "$log" ] && grep -qF -- "$needle" "$log"; then return 0; fi
        sleep 1
        waited=$((waited + 1))
    done
    return 1
}

echo "=== fleet-launch hermetic harness"

# --- 1. reading a factory board ---------------------------------------------
# The count must be the LIVE rows only: not the header, and not the terminal
# runs a real `ps -a` board carries beside them. The absent fleet-cap file is
# what stops the launcher here, so the refusal line carries both board counts.
echo "--- 1. reads a stub factory board"
new_case board-read
write_board "$BOARD_GMK" 2 gmk
write_board "$BOARD_HL" 1 hl
run_launcher bd-ib-boardread
if log_has "$CASE_LOG" "gmktec=2 hl=1 markers=0 fleet=3"; then
    pass "the board read counts the live runs of both factories"
else
    fail "the board read did not report gmktec=2 hl=1 fleet=3"
    tail -5 "$CASE_LOG" >&2
fi
if log_has "$CASE_LOG" "cap=0"; then
    pass "an absent fleet-cap file reads as a cap of zero, which is never green"
else
    fail "an absent fleet-cap file did not read as cap=0"
fi
if [ ! -s "$DRIVE_LOG" ]; then
    pass "no dispatch was made with the cap unreadable"
else
    fail "a dispatch was made with the cap unreadable: $(drive_log_items)"
fi

# --- 2. refusing a launch at the shared fleet cap ---------------------------
echo "--- 2. refuses a launch when the shared fleet cap is reached"
new_case fleet-cap
write_board "$BOARD_GMK" 3 gmk
write_board "$BOARD_HL" 1 hl
printf '4\n' > "$CAP_FILE"
run_launcher bd-ib-atcap
if log_has "$CASE_LOG" "fleet not green" && log_has "$CASE_LOG" "fleet=4 cap=4"; then
    pass "a fleet of four against a cap of four is refused"
else
    fail "a fleet at the cap was not refused"
    tail -5 "$CASE_LOG" >&2
fi
if [ ! -s "$DRIVE_LOG" ] && [ "$RC" = 75 ]; then
    pass "the launcher took no slot and gave up (rc=75)"
else
    fail "expected no dispatch and rc=75, got rc=$RC dispatches: $(drive_log_items)"
fi
# The positive control: the same fleet, one slot of headroom.
printf '5\n' > "$CAP_FILE"
run_launcher bd-ib-undercap "$CASE_DIR/control.log"
if [ "$(drive_log_items)" = "bd-ib-undercap" ] && [ "$RC" = 0 ]; then
    pass "control: one slot of headroom under the same cap launches"
else
    fail "control: a fleet under the cap did not launch (rc=$RC, dispatches: $(drive_log_items))"
    tail -8 "$CASE_DIR/control.log" >&2
fi

# --- 3. two queued tickets launch in FIFO order -----------------------------
# The FIFO order is the TICKET order, not the start order, so the launcher
# started FIRST here holds the LATER ticket and must lose. The hold file is the
# barrier: both launchers are parked on it, the second is then observed to have
# queued behind the older ticket, and only then is the hold released — so the
# later launcher cannot have slipped past the ticket check in the same poll.
echo "--- 3. launches two queued tickets in FIFO order"
new_case fifo
# This case PARKS both launchers on the barrier on purpose, so the give-up
# deadline every other case leans on would fire while they are waiting for each
# other. It is raised here to a bound that cannot be reached by a healthy run on
# a loaded machine, which keeps the case a test of the ticket ORDER rather than
# of how fast this host happens to be: the short deadline failed under a
# concurrent test suite while the ordering it asserts was perfectly correct.
export FLEET_LAUNCH_MAX_WAIT_S=300
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
: > "$HOLD_FILE"
LATER_LOG="$CASE_DIR/later.log"
EARLIER_LOG="$CASE_DIR/earlier.log"
ONLY_GMK=1 TICKET_NS=200 "$LAUNCHER" bd-ib-later > "$LATER_LOG" 2>&1 &
later_pid=$!
if ! wait_for_line "$LATER_LOG" "hold file present" 30; then
    fail "the later-ticket launcher never parked on the hold file"
    tail -8 "$LATER_LOG" >&2
fi
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-earlier > "$EARLIER_LOG" 2>&1 &
earlier_pid=$!
if wait_for_line "$LATER_LOG" "queued behind an older gmktec ticket" 30; then
    pass "the later ticket queues behind the older one"
else
    fail "the later ticket never queued behind the older one"
    tail -8 "$LATER_LOG" >&2
fi
rm -f "$HOLD_FILE"
await_both "$earlier_pid" "$later_pid" 45
earlier_rc=$FIRST_RC; later_rc=$SECOND_RC
# Binding order is what FIFO guarantees, not the order of the two drive calls:
# the narrow mutex is released before drive, so after both bind the drives may
# reach the stub in either order. A later ticket leaves the queue only once the
# older ticket is dropped at its bind, so "queued behind the older ticket" plus
# both launches is the order evidence.
if [ "$(drive_log_items | tr ' ' '\n' | sort | tr '\n' ' ' | sed 's/ $//')" = "bd-ib-earlier bd-ib-later" ] \
    && grep -qE "queued behind an older gmktec ticket: owner=harness-seat pid=[0-9]+ item=bd-ib-earlier$" "$LATER_LOG"; then
    pass "both queued tickets launched, oldest ticket first"
else
    fail "expected both launched with the later ticket queued behind bd-ib-earlier; drives '$(drive_log_items)'"
    tail -8 "$EARLIER_LOG" >&2
    tail -8 "$LATER_LOG" >&2
fi
if [ "$earlier_rc" = 0 ] && [ "$later_rc" = 0 ]; then
    pass "both launchers exited zero"
else
    fail "launcher exits: earlier=$earlier_rc later=$later_rc"
fi

# --- 4. holding a launch while the hold file exists -------------------------
echo "--- 4. holds a launch while the hold file exists"
new_case hold
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
: > "$HOLD_FILE"
run_launcher bd-ib-held
if log_has "$CASE_LOG" "hold file present" && [ ! -s "$DRIVE_LOG" ] && [ "$RC" = 75 ]; then
    pass "the hold file holds the launch with every other gate green"
else
    fail "the hold file did not hold the launch (rc=$RC, dispatches: $(drive_log_items))"
    tail -5 "$CASE_LOG" >&2
fi
# The positive control: the identical case with the hold file removed.
rm -f "$HOLD_FILE"
run_launcher bd-ib-released "$CASE_DIR/control.log"
if [ "$(drive_log_items)" = "bd-ib-released" ] && [ "$RC" = 0 ]; then
    pass "control: removing the hold file releases the identical launch"
else
    fail "control: the launch did not release (rc=$RC, dispatches: $(drive_log_items))"
    tail -8 "$CASE_DIR/control.log" >&2
fi

# --- 5. a retired factory's board counts as zero, not as unknown ------------
# The defect this case exists for: a launcher that reads an idle board as
# UNKNOWN sees the fleet as unknown and never launches at all. That is the
# 2026-10-24 outage the README records, and it looks exactly like a busy fleet.
echo "--- 5. counts a retired factory's board as zero, not as unknown"
new_case retired-board
write_board "$BOARD_GMK" 1 gmk
: > "$BOARD_HL"
printf '1\n' > "$CAP_FILE"
run_launcher bd-ib-retired
if log_has "$CASE_LOG" "hl=0" && log_has "$CASE_LOG" "fleet=1 cap=1"; then
    pass "an idle board counts as zero, so the fleet is a number"
else
    fail "an idle board was not counted as zero"
    tail -5 "$CASE_LOG" >&2
fi
# The positive control: the same idle board with headroom MUST launch, which is
# what an unknown reading could never do.
printf '8\n' > "$CAP_FILE"
run_launcher bd-ib-retired-ok "$CASE_DIR/control.log"
if [ "$(drive_log_items)" = "bd-ib-retired-ok" ] && [ "$RC" = 0 ]; then
    pass "control: a fleet counted past an idle board launches"
else
    fail "control: an idle board blocked the launch (rc=$RC, dispatches: $(drive_log_items))"
    tail -8 "$CASE_DIR/control.log" >&2
fi
# The mirror arm: an UNREADABLE board is not a zero. Without it, a launcher
# that answered zero for every board would pass the two cases above.
rm -f "$BOARD_HL"
: > "$DRIVE_LOG"
run_launcher bd-ib-unreadable "$CASE_DIR/unreadable.log"
if log_has "$CASE_DIR/unreadable.log" "hl=U" && log_has "$CASE_DIR/unreadable.log" "fleet=U"; then
    pass "an unreadable board is unknown, never a zero"
else
    fail "an unreadable board was not reported as unknown"
    tail -5 "$CASE_DIR/unreadable.log" >&2
fi
if [ ! -s "$DRIVE_LOG" ] && [ "$RC" = 75 ]; then
    pass "an unknown fleet is never green, so no slot was taken"
else
    fail "an unknown fleet launched (rc=$RC, dispatches: $(drive_log_items))"
fi

# --- 6. queued preflights, reusable passes, and FIFO binds ------------------
# The slow older ticket creates a real queue interval.  The younger ticket must
# use that interval for its own Definition-of-Done preflight, rather than wait
# for the older launcher to bind first.  The same observation also proves that
# its fresh pass is not needlessly repeated at the head.
echo "--- 6. preflights while queued and reuses a fresh pass at the FIFO head"
new_case queued-preflight
export FLEET_LAUNCH_MAX_WAIT_S=300
export STUB_PREFLIGHT_SLOW_ITEM=bd-ib-older
export STUB_PREFLIGHT_SLOW_S=120
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-older > "$CASE_DIR/older.log" 2>&1 &
older_pid=$!
if ! wait_for_preflight bd-ib-older 1 10; then
    fail "the older launcher did not start its preflight"
fi
ONLY_GMK=1 TICKET_NS=200 "$LAUNCHER" bd-ib-younger > "$CASE_DIR/younger.log" 2>&1 &
younger_pid=$!
# The older preflight is held, so the older launcher cannot bind until the
# release below: a younger preflight seen first ran while it was queued.
if wait_for_preflight bd-ib-younger 1 60 && [ ! -s "$DRIVE_LOG" ]; then
    pass "the younger queued launcher starts its preflight before the older binds"
else
    fail "the younger launcher waited for the FIFO head before starting its preflight"
fi
touch "$STUB_PREFLIGHT_RELEASE"
await_both "$older_pid" "$younger_pid" 90
# As in case 3: the younger ticket leaves the queue only after the older one
# was dropped at its bind; the two drive calls themselves may race.
if [ "$(drive_log_items | tr ' ' '\n' | sort | tr '\n' ' ' | sed 's/ $//')" = "bd-ib-older bd-ib-younger" ] \
    && grep -qE "queued behind an older gmktec ticket: owner=harness-seat pid=[0-9]+ item=bd-ib-older$" "$CASE_DIR/younger.log"; then
    pass "queued launchers bind in FIFO ticket order after their preflights"
else
    fail "queued launchers did not bind in FIFO order (younger never queued behind bd-ib-older, or a launch is missing); drives: $(drive_log_items)"
fi
if [ "$(preflight_count bd-ib-younger)" = 1 ]; then
    pass "a fresh queued preflight pass is reused when the younger launcher reaches the head"
else
    fail "a fresh queued preflight was run $(preflight_count bd-ib-younger) times at the head"
fi
# Each drive leaves one observation.  `released` means no launcher held the
# mutex; `held driver=A holder=B` with A != B means the older launcher had
# already released and the younger one took the mutex first, which the narrow
# mutex scope allows and which a loaded host makes likely.  Only a driver that
# still holds its OWN mutex is a violation, so count both legal shapes.
if ! grep -qE '^held driver=([^ ]+) holder=\1$' "$DRIVE_MUTEX_LOG" \
    && [ "$(grep -cE '^(released |held driver=)' "$DRIVE_MUTEX_LOG")" -ge 2 ]; then
    pass "the mutex is released before either drive --action impl starts"
else
    fail "a drive started while its launch mutex was held: $(tr '\n' ' ' < "$DRIVE_MUTEX_LOG")"
fi

# A young pass expires while the older launcher is held in its own
# preflight.  Its ticket must re-run the preflight at the FIFO head before it
# can take the mutex.
echo "--- 7. re-runs a stale queued preflight at the FIFO head"
new_case stale-preflight
export FLEET_LAUNCH_MAX_WAIT_S=300
export FLEET_LAUNCH_PREFLIGHT_REUSE_S=1
export STUB_PREFLIGHT_SLOW_ITEM=bd-ib-stale-older
export STUB_PREFLIGHT_SLOW_S=120
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-stale-older > "$CASE_DIR/older.log" 2>&1 &
older_pid=$!
wait_for_preflight bd-ib-stale-older 1 10 || fail "the stale-case older launcher did not preflight"
ONLY_GMK=1 TICKET_NS=200 "$LAUNCHER" bd-ib-stale-younger > "$CASE_DIR/younger.log" 2>&1 &
younger_pid=$!
if ! wait_for_preflight bd-ib-stale-younger 1 60 || [ -s "$DRIVE_LOG" ]; then
    fail "the stale-case younger launcher did not preflight while queued"
fi
# Let the younger pass outlive FLEET_LAUNCH_PREFLIGHT_REUSE_S=1 before the
# older launcher is released to bind.
sleep 2
touch "$STUB_PREFLIGHT_RELEASE"
await_both "$older_pid" "$younger_pid" 90
if [ "$(preflight_count bd-ib-stale-younger)" = 2 ]; then
    pass "a stale queued pass is re-run at the FIFO head before binding"
else
    fail "a stale queued pass was not re-run at the FIFO head (count=$(preflight_count bd-ib-stale-younger))"
fi

# A queued preflight failure is terminal for that launcher.  The older ticket
# is deliberately still in its preflight, so a failed younger launcher cannot
# have touched the mutex on its way out.
echo "--- 8. drops a ticket when its queued preflight fails"
new_case queued-preflight-failure
export FLEET_LAUNCH_MAX_WAIT_S=300
export STUB_PREFLIGHT_SLOW_ITEM=bd-ib-failing-older
export STUB_PREFLIGHT_SLOW_S=120
export STUB_PREFLIGHT_FAIL_ITEM=bd-ib-failing-younger
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-failing-older > "$CASE_DIR/older.log" 2>&1 &
older_pid=$!
wait_for_preflight bd-ib-failing-older 1 10 || fail "the failure-case older launcher did not preflight"
ONLY_GMK=1 TICKET_NS=200 "$LAUNCHER" bd-ib-failing-younger > "$CASE_DIR/younger.log" 2>&1 &
younger_pid=$!
if wait_for_preflight bd-ib-failing-younger 1 60 && [ ! -s "$DRIVE_LOG" ]; then
    wait "$younger_pid"; younger_rc=$?
else
    kill -TERM "$younger_pid" 2>/dev/null
    wait "$younger_pid"; younger_rc=$?
    fail "the younger failing preflight did not start while its ticket was queued"
fi
if [ "$younger_rc" = 4 ] && [ ! -e "$CASE_DIR/queue/200-harness-seat" ] && [ ! -d "$CASE_DIR/lock" ]; then
    pass "a failed queued preflight exits 4, drops its ticket, and never takes the mutex"
else
    fail "queued preflight failure did not cleanly exit (rc=$younger_rc ticket=$(test -e "$CASE_DIR/queue/200-harness-seat" && echo present || echo absent) lock=$(test -d "$CASE_DIR/lock" && echo present || echo absent))"
fi
touch "$STUB_PREFLIGHT_RELEASE"
kill -TERM "$older_pid" 2>/dev/null
wait "$older_pid" || true

echo
echo "=== fleet-launch hermetic harness: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
