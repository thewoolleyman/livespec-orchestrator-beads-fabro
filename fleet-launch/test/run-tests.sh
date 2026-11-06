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
RESUME_LAUNCHER="$LAUNCH_DIR/resume-capped.sh"

if [ ! -f "$LAUNCHER" ] || [ ! -f "$RESUME_LAUNCHER" ]; then
    echo "run-tests.sh: launcher not found" >&2
    exit 1
fi

HARNESS_SLICE=${1:-all}
case "$HARNESS_SLICE" in
    all|scenario297|scenario316) ;;
    *)
        echo "usage: run-tests.sh [scenario297|scenario316]" >&2
        exit 2
        ;;
esac

# GNU sleep accepts hundredth-second durations.  That is the smallest useful
# non-zero launcher poll: zero would make the bounded loops spin rather than
# wait for the state they observe.  Export it because the stub wrapper runs in
# a child shell while it holds a launcher's preflight.
export HARNESS_POLL_S=0.01

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
# Every listing request is recorded, one server per line, so a case can count what the
# factory would have been asked; STUB_PS_DELAY_S makes a listing slow, as the petri server's is.
if [ -n "${STUB_PS_LOG:-}" ]; then printf '%s\n' "$server" >> "$STUB_PS_LOG"; fi
if [ -n "${STUB_PS_DELAY_S:-}" ]; then sleep "$STUB_PS_DELAY_S"; fi
# An absent fixture is the unreadable board: non-zero exit, nothing on stdout.
if [ ! -f "$board" ]; then
    echo "stub fabro: board unreadable" >&2
    exit 1
fi
rows="$(mktemp)"
trap 'rm -f "$rows"' EXIT
if [ -s "$board" ]; then tail -n +2 "$board" >> "$rows"; fi
for marker in "$STUB_DRIVEN_DIR"/* "$STUB_RESUMED_DIR"/*; do
    [ -e "$marker" ] || continue
    marker_server=$(cut -d' ' -f1 "$marker")
    marker_item=$(cut -d' ' -f2 "$marker")
    [ "$marker_server" = "$server" ] || continue
    printf 'DRIVEN000001 stub-repo running 2026-10-25 0m05s %s\n' "$marker_item" >> "$rows"
done
# A one-shot hook that runs AFTER this read has captured its rows and before it
# prints them.  It lets the harness move a launch from "in flight, unlisted" to
# "listed" exactly between a launcher's board read and its marker read, which
# is the window a concurrent impl launcher hits on a loaded host.
if [ -n "${STUB_PS_AFTER_READ_HOOK:-}" ] && [ "$server" = "$STUB_SERVER_GMK" ] \
    && [ ! -e "$STUB_PS_AFTER_READ_HOOK.done" ]; then
    : > "$STUB_PS_AFTER_READ_HOOK.done"
    bash "$STUB_PS_AFTER_READ_HOOK"
fi
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
                deadline=$(( $(date +%s) + STUB_PREFLIGHT_SLOW_S ))
                while [ ! -e "${STUB_PREFLIGHT_RELEASE:-/nonexistent}" ] \
                    && [ "$(date +%s)" -lt "$deadline" ]; do
                    sleep "$HARNESS_POLL_S"
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
        resume)
            item=""
            previous=""
            for token in "$@"; do
                if [ "$previous" = --item ]; then item=$token; fi
                previous=$token
            done
            printf '%s\n' "$item" >> "$STUB_RESUME_LOG"
            marker_state=missing
            if find "$STUB_INFLIGHT_DIR" -type f -print -quit | grep -q .; then marker_state=present; fi
            lock_state=released
            if [ -d "$STUB_LOCK_DIR" ]; then lock_state=held; fi
            printf '%s marker=%s mutex=%s\n' "$item" "$marker_state" "$lock_state" >> "$STUB_RESUME_OBSERVATION_LOG"
            if [ -z "${STUB_RESUME_UNLISTED:-}" ]; then
                printf '%s %s\n' "$STUB_SERVER_GMK" "$item" > "$STUB_RESUMED_DIR/$item"
            fi
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
RESUME_LOG=""
RESUME_OBSERVATION_LOG=""
PS_LOG=""
SNAPSHOT_DIR=""
BOARD_GMK=""
BOARD_HL=""
CAP_FILE=""
HOLD_FILE=""

# new_case <name>: a fresh set of throwaway directories and fixtures, and the
# environment every launcher invocation of this case inherits.
new_case() {
    CASE_DIR="$WORK/case/$1"
    mkdir -p "$CASE_DIR"/{boards,state,inflight,queue,lock,driven,resumed}
    rmdir "$CASE_DIR/lock"
    CASE_LOG="$CASE_DIR/launcher.log"
    DRIVE_LOG="$CASE_DIR/drive-log"
    : > "$DRIVE_LOG"
    DRIVE_MUTEX_LOG="$CASE_DIR/drive-mutex-log"
    : > "$DRIVE_MUTEX_LOG"
    PREFLIGHT_LOG="$CASE_DIR/preflight-log"
    : > "$PREFLIGHT_LOG"
    RESUME_LOG="$CASE_DIR/resume-log"
    : > "$RESUME_LOG"
    RESUME_OBSERVATION_LOG="$CASE_DIR/resume-observation-log"
    : > "$RESUME_OBSERVATION_LOG"
    PS_LOG="$CASE_DIR/ps-log"
    : > "$PS_LOG"
    SNAPSHOT_DIR="$CASE_DIR/board-snapshot"
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
    export STUB_RESUMED_DIR="$CASE_DIR/resumed"
    export STUB_DRIVE_LOG="$DRIVE_LOG"
    export STUB_DRIVE_MUTEX_LOG="$DRIVE_MUTEX_LOG"
    export STUB_PREFLIGHT_LOG="$PREFLIGHT_LOG"
    export STUB_RESUME_LOG="$RESUME_LOG"
    export STUB_RESUME_OBSERVATION_LOG="$RESUME_OBSERVATION_LOG"
    export STUB_PS_LOG="$PS_LOG"
    unset STUB_PS_DELAY_S
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
    export FLEET_LAUNCH_REPO_HOLD_DIR="$CASE_DIR/state"
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
    export STUB_INFLIGHT_DIR="$FLEET_LAUNCH_INFLIGHT_DIR"
    export STUB_LOCK_DIR="$FLEET_LAUNCH_GMK_LOCK_DIR"
    export FLEET_LAUNCH_PLUGIN_REGISTRY="$REGISTRY"
    export FLEET_LAUNCH_PLUGIN_CACHE="$PLUGIN_CACHE"
    export FLEET_LAUNCH_PLUGIN_KEY="$PLUGIN_KEY"
    export FLEET_LAUNCH_DEFAULT_WRAPPER="$STUB/wrapper"
    export FLEET_LAUNCH_RESUME_WRAPPER="$STUB/wrapper"
    export FLEET_LAUNCH_RESUME_COMMAND=resume
    # The launchers use their smallest useful non-zero poll, so a queued
    # launcher rechecks FIFO almost immediately after the harness changes it.
    export FLEET_LAUNCH_MAX_WAIT_S=4
    export FLEET_LAUNCH_ABANDON_S=60
    export FLEET_LAUNCH_POLL_S=0.01
    # Keep all launcher state polls at that step: mutex release and post-drive
    # listing are observed conditions, not reasons to wait a whole second.
    export FLEET_LAUNCH_MUTEX_POLL_S=0.01
    export FLEET_LAUNCH_LISTING_POLL_S=0.01
    export FLEET_LAUNCH_PREFLIGHT_REUSE_S=600
    # A TTL of zero keeps every board read live, so a case that changes a board fixture sees it on
    # the next poll; the snapshot cases below raise it.
    export FLEET_LAUNCH_BOARD_SNAPSHOT_DIR="$SNAPSHOT_DIR"
    export FLEET_LAUNCH_BOARD_TTL_S=0
    export FLEET_LAUNCH_BOARD_REFRESH_WAIT_S=60
    export FLEET_LAUNCH_MUTEX_HOLD_S=60
    export FLEET_LAUNCH_LISTING_WAIT_S=60
    unset STUB_RESUME_UNLISTED
    unset ONLY_GMK ONLY_HL CAPTURE_NULL CAPTURE_EXPECT TICKET_NS REWORK RELEASE_BLOCKED
}

# run_launcher <item> [log]: one launcher invocation, captured. Sets RC.
run_launcher() {
    local item="$1" log="${2:-$CASE_LOG}"
    "$LAUNCHER" "$item" > "$log" 2>&1
    RC=$?
}

log_has() { grep -qF -- "$2" "$1"; }
ps_count() { grep -cxF -- "$1" "$PS_LOG" 2>/dev/null || true; }
drive_log_items() { tr '\n' ' ' < "$DRIVE_LOG" | sed 's/ *$//'; }
preflight_count() { grep -c " $1$" "$PREFLIGHT_LOG" 2>/dev/null || true; }

# wait_for_preflight <item> <count> <seconds>: wait until the stub recorded a
# particular number of Definition-of-Done preflights for an item.
wait_for_preflight() {
    local item="$1" count="$2" limit="$3" deadline
    deadline=$(( $(date +%s) + limit ))
    while :; do
        if [ "$(preflight_count "$item")" -ge "$count" ]; then return 0; fi
        [ "$(date +%s)" -lt "$deadline" ] || return 1
        sleep "$HARNESS_POLL_S"
    done
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
# stop_launcher <pid>...: TERM each launcher, then KILL any still alive after STOP_GRACE_S.
# Bash 5.2 can lose a TERM: when the signal lands while the launcher is parsing a $(...)
# substitution, its `trap 'exit 143' TERM` fails with "trap: line 2: unexpected EOF while
# looking for matching `)'" and the launcher keeps looping. Reproduced in 1 of 200 TERMs on
# bash 5.2.37. A bare `kill -TERM; wait` then hangs the harness on a launcher that never exits,
# which is how run 18 of 30 hung. Callers keep their own `wait` to reap the launcher.
STOP_GRACE_S=${STOP_GRACE_S:-5}
stop_launcher() {
    local pid deadline
    kill -TERM "$@" 2>/dev/null
    deadline=$(( $(date +%s) + STOP_GRACE_S ))
    for pid in "$@"; do
        while kill -0 "$pid" 2>/dev/null && [ "$(date +%s)" -lt "$deadline" ]; do
            sleep "$HARNESS_POLL_S"
        done
        kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null
    done
    return 0
}

FIRST_RC=""
SECOND_RC=""
await_both() {
    local first="$1" second="$2" limit="$3" deadline
    deadline=$(( $(date +%s) + limit ))
    while :; do
        if ! kill -0 "$first" 2>/dev/null && ! kill -0 "$second" 2>/dev/null; then break; fi
        [ "$(date +%s)" -lt "$deadline" ] || break
        sleep "$HARNESS_POLL_S"
    done
    stop_launcher "$first" "$second"
    wait "$first"; FIRST_RC=$?
    wait "$second"; SECOND_RC=$?
}

# wait_for_line <log> <needle> <seconds>: poll one launcher's log for a line.
wait_for_line() {
    local log="$1" needle="$2" limit="$3" deadline
    deadline=$(( $(date +%s) + limit ))
    while :; do
        if [ -f "$log" ] && grep -qF -- "$needle" "$log"; then return 0; fi
        [ "$(date +%s)" -lt "$deadline" ] || return 1
        sleep "$HARNESS_POLL_S"
    done
}

echo "=== fleet-launch hermetic harness"

if [ "$HARNESS_SLICE" = all ]; then
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

fi

# --- 6. queued preflights, reusable passes, and FIFO binds ------------------
# The slow older ticket creates a real queue interval.  The younger ticket must
# use that interval for its own Definition-of-Done preflight, rather than wait
# for the older launcher to bind first.  The same observation also proves that
# its fresh pass is not needlessly repeated at the head.
if [ "$HARNESS_SLICE" = all ] || [ "$HARNESS_SLICE" = scenario297 ]; then
echo "--- 6. preflights while queued and reuses a fresh pass at the FIFO head"
if bash "$HARNESS_DIR/test-scenario297-polling.sh"; then
    pass "the Scenario 297 cases poll observed state at the harness interval instead of sleeping fixed seconds"
else
    fail "the Scenario 297 polling configuration regressed"
fi
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
export FLEET_LAUNCH_PREFLIGHT_REUSE_S=0
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
# A zero-second reuse window makes the observed queued pass stale as soon as
# the older launcher is released; no wall-clock delay is part of this case.
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
    stop_launcher "$younger_pid"
    wait "$younger_pid"; younger_rc=$?
    fail "the younger failing preflight did not start while its ticket was queued"
fi
if [ "$younger_rc" = 4 ] && [ ! -e "$CASE_DIR/queue/200-harness-seat" ] && [ ! -d "$CASE_DIR/lock" ]; then
    pass "a failed queued preflight exits 4, drops its ticket, and never takes the mutex"
else
    fail "queued preflight failure did not cleanly exit (rc=$younger_rc ticket=$(test -e "$CASE_DIR/queue/200-harness-seat" && echo present || echo absent) lock=$(test -d "$CASE_DIR/lock" && echo present || echo absent))"
fi
touch "$STUB_PREFLIGHT_RELEASE"
stop_launcher "$older_pid"
wait "$older_pid" || true
fi

# Cases 9-13 cover the resume launcher and the in-flight marker count, not
# Scenario 297's queued preflight, so the scenario297 slice skips them: that
# slice runs under a 60 s bound in tests/integration/test_fleet_launch_scenario297.py
# and the full set took it to about 73 s, turning master red on every CI run.
if [ "$HARNESS_SLICE" = all ]; then
# --- 9. a resume shares FIFO and waits for fleet headroom -------------------
# The older impl ticket reaches the head first, but the fleet begins at the
# shared cap.  Once the board drops by one the impl binds, restoring the cap
# with its in-flight marker/run.  The resume keeps its own ticket while it sees
# that cap, then starts only after the older run disappears.
echo "--- 9. a resume waits at the fleet cap and shares the gmktec FIFO"
new_case resume-cap-fifo
export FLEET_LAUNCH_MAX_WAIT_S=120
write_board "$BOARD_GMK" 8 gmk
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
IMPL_LOG="$CASE_DIR/impl.log"
RESUME_CASE_LOG="$CASE_DIR/resume-launcher.log"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-resume-older > "$IMPL_LOG" 2>&1 &
impl_pid=$!
if ! wait_for_line "$IMPL_LOG" "fleet not green" 30; then
    fail "the older impl ticket did not wait at the fleet cap"
fi
TICKET_NS=200 "$RESUME_LAUNCHER" bd-ib-resume > "$RESUME_CASE_LOG" 2>&1 &
resume_pid=$!
if wait_for_line "$RESUME_CASE_LOG" "queued behind an older gmktec ticket" 30; then
    pass "the resume ticket queues behind the older impl ticket"
else
    fail "the resume launcher did not queue behind the older impl ticket"
    tail -8 "$RESUME_CASE_LOG" >&2
fi
write_board "$BOARD_GMK" 7 gmk
if wait_for_line "$IMPL_LOG" "LAUNCH target=petri" 30 \
    && wait_for_line "$RESUME_CASE_LOG" "fleet at cap under mutex" 30 \
    && [ ! -s "$RESUME_LOG" ]; then
    pass "the resume keeps its FIFO ticket while the older impl refills the fleet cap"
else
    fail "the resume did not wait at the cap after the older impl bound"
    tail -8 "$IMPL_LOG" >&2
    tail -8 "$RESUME_CASE_LOG" >&2
fi
# The older run "ends" by leaving the board.  Remove its driven row only once
# the impl's stub dispatch has finished writing it: the LAUNCH line is printed
# BEFORE drive.py runs, so removing the row at LAUNCH raced the stub writing it,
# the row came back, the board stayed at the cap and the resume gave up
# (resume=75), measured 2 of 4 parallel harness runs on 2026-11-03.
wait_for_line "$IMPL_LOG" "drive rc=" 120 || fail "the older impl's dispatch did not finish"
rm -f "$CASE_DIR/driven/bd-ib-resume-older"
wait "$impl_pid"; impl_rc=$?
wait "$resume_pid"; resume_rc=$?
if [ "$impl_rc" = 0 ] && [ "$resume_rc" = 0 ] && [ "$(cat "$RESUME_LOG")" = bd-ib-resume ]; then
    pass "the resume starts after the fleet count drops below the cap"
else
    fail "the capped resume did not start cleanly (impl=$impl_rc resume=$resume_rc resumes=$(tr '\n' ' ' < "$RESUME_LOG"))"
fi
if grep -q '^bd-ib-resume marker=present mutex=released$' "$RESUME_OBSERVATION_LOG"; then
    pass "the resume in-flight marker exists before its mutex is released"
else
    fail "the resume did not retain its marker through mutex release: $(tr '\n' ' ' < "$RESUME_OBSERVATION_LOG")"
fi

# --- 10. a resume marker stays counted until the board lists the run --------
# The resume client returns at once, before the run lists on the board.  The
# launcher must keep its in-flight marker so concurrent launchers still count
# the resume, and drop it only after the board lists the run.
echo "--- 10. a resume marker stays counted after the client returns, until the board lists the run"
new_case resume-marker-retained
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
export STUB_RESUME_UNLISTED=1
RESUME_CASE_LOG="$CASE_DIR/resume-launcher.log"
"$RESUME_LAUNCHER" bd-ib-unlisted > "$RESUME_CASE_LOG" 2>&1 &
resume_pid=$!
waited=0
while [ ! -s "$RESUME_LOG" ] && [ "$waited" -lt 30 ]; do sleep 1; waited=$((waited + 1)); done
sleep 3
if kill -0 "$resume_pid" 2>/dev/null && [ -n "$(find "$CASE_DIR/inflight" -type f -print -quit)" ]; then
    pass "the resume marker is still present after the client returned before the board listed it"
else
    fail "the resume marker was dropped before the board listed the run"
fi
printf '%s %s\n' "$GMK_URL" bd-ib-unlisted > "$CASE_DIR/resumed/bd-ib-unlisted"
wait "$resume_pid"; resume_rc=$?
if [ "$resume_rc" = 0 ] && [ -z "$(find "$CASE_DIR/inflight" -type f -print -quit)" ]; then
    pass "the resume marker is removed once the board lists the run"
else
    fail "the resume marker was not cleared after listing (rc=$resume_rc)"
fi

# --- 11. an unreadable in-flight directory counts as at the cap -------------
# A regular file stands where the in-flight directory belongs, so the count of
# in-flight launches cannot be read.  With empty boards and headroom under the
# cap, the resume must still refuse to start.
echo "--- 11. a resume refuses to start when the in-flight directory cannot be read"
new_case resume-inflight-unreadable
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
rmdir "$FLEET_LAUNCH_INFLIGHT_DIR"
: > "$FLEET_LAUNCH_INFLIGHT_DIR"
RESUME_CASE_LOG="$CASE_DIR/resume-launcher.log"
"$RESUME_LAUNCHER" bd-ib-blind > "$RESUME_CASE_LOG" 2>&1; resume_rc=$?
if [ "$resume_rc" = 75 ] && [ ! -s "$RESUME_LOG" ] && grep -q 'fleet=U' "$RESUME_CASE_LOG"; then
    pass "the resume treats an unreadable in-flight directory as at the cap and does not start"
else
    fail "the resume started or misread an unreadable in-flight directory (rc=$resume_rc resumes=$(tr '\n' ' ' < "$RESUME_LOG"))"
fi

# --- 12. a launch that lists between the board read and the marker read ----
# Another launcher's in-flight marker covers a run the board does not list yet.
# During the resume's board read, that launcher sees its run listed and removes
# its marker (the hook below does both, after the read has captured its rows).
# The resume must still count that launch: its board read predates the listing,
# so the marker it read must be counted, and the fleet stays at the cap.
echo "--- 12. a launch listed between the board read and the marker read stays counted"
new_case resume-listing-race
export FLEET_LAUNCH_MAX_WAIT_S=6
write_board "$BOARD_GMK" 7 gmk
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
sleep 600 &
racer_pid=$!
racer_marker="$FLEET_LAUNCH_INFLIGHT_DIR/100-other-seat-bd-ib-racer"
echo "owner=other-seat pid=$racer_pid item=bd-ib-racer factory=petri" > "$racer_marker"
cat > "$CASE_DIR/list-racer.sh" <<HOOK
printf '%s %s\\n' "$GMK_URL" bd-ib-racer > "$CASE_DIR/driven/bd-ib-racer"
rm -f "$racer_marker"
HOOK
export STUB_PS_AFTER_READ_HOOK="$CASE_DIR/list-racer.sh"
RESUME_CASE_LOG="$CASE_DIR/resume-launcher.log"
"$RESUME_LAUNCHER" bd-ib-race-resume > "$RESUME_CASE_LOG" 2>&1; resume_rc=$?
unset STUB_PS_AFTER_READ_HOOK
kill "$racer_pid" 2>/dev/null; wait "$racer_pid" 2>/dev/null
if [ "$resume_rc" = 75 ] && [ ! -s "$RESUME_LOG" ] && grep -q 'fleet at cap under mutex: fleet=8 cap=8' "$RESUME_CASE_LOG"; then
    pass "a launch listed between the board read and the marker read keeps the fleet at the cap"
else
    fail "the resume undercounted a launch that listed mid-read (rc=$resume_rc resumes=$(tr '\n' ' ' < "$RESUME_LOG"))"
    tail -6 "$RESUME_CASE_LOG" >&2
fi

# --- 13. the impl launcher counts a launch listed mid-read too -------------
# The same race as case 12, against the impl launcher's fleet-green count.
echo "--- 13. the impl launcher keeps a launch listed mid-read counted"
new_case impl-listing-race
export FLEET_LAUNCH_MAX_WAIT_S=6
write_board "$BOARD_GMK" 7 gmk
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
sleep 600 &
racer_pid=$!
racer_marker="$FLEET_LAUNCH_INFLIGHT_DIR/100-other-seat-bd-ib-racer"
echo "owner=other-seat pid=$racer_pid item=bd-ib-racer factory=petri" > "$racer_marker"
cat > "$CASE_DIR/list-racer.sh" <<HOOK
printf '%s %s\\n' "$GMK_URL" bd-ib-racer > "$CASE_DIR/driven/bd-ib-racer"
rm -f "$racer_marker"
HOOK
export STUB_PS_AFTER_READ_HOOK="$CASE_DIR/list-racer.sh"
IMPL_CASE_LOG="$CASE_DIR/impl-launcher.log"
ONLY_GMK=1 "$LAUNCHER" bd-ib-race-impl > "$IMPL_CASE_LOG" 2>&1; impl_rc=$?
unset STUB_PS_AFTER_READ_HOOK
kill "$racer_pid" 2>/dev/null; wait "$racer_pid" 2>/dev/null
if [ ! -s "$DRIVE_LOG" ] && grep -q 'fleet not green: gmktec=7 hl=0 markers=1 fleet=8 cap=8' "$IMPL_CASE_LOG"; then
    pass "the impl launcher counts a launch listed between the board read and the marker read"
else
    fail "the impl launcher undercounted a launch that listed mid-read (rc=$impl_rc drives=$(tr '\n' ' ' < "$DRIVE_LOG"))"
    tail -6 "$IMPL_CASE_LOG" >&2
fi

# --- 14. queued launchers share one board snapshot --------------------------
# Six launchers poll one at-cap fleet at once, against a petri-sized slow listing. Each polls
# for the whole wait window, yet the factory server is asked for ONE listing per factory:
# the first launcher refreshes the snapshot and the others read it, instead of each sending the
# server a listing of its own on every poll (bd-ib-busjvz).
echo "--- 14. queued launchers read one shared board snapshot"
new_case snapshot-shared
export FLEET_LAUNCH_MAX_WAIT_S=4
export FLEET_LAUNCH_BOARD_TTL_S=300
export STUB_PS_DELAY_S=1
write_board "$BOARD_GMK" 3 gmk
write_board "$BOARD_HL" 1 hl
printf '4\n' > "$CAP_FILE"
snapshot_pids=""
for index in 1 2 3 4 5 6; do
    "$LAUNCHER" "bd-ib-shared-$index" > "$CASE_DIR/launcher-$index.log" 2>&1 &
    snapshot_pids="$snapshot_pids $!"
done
snapshot_bad=0
for snapshot_pid in $snapshot_pids; do
    wait "$snapshot_pid"; [ "$?" = 75 ] || snapshot_bad=$((snapshot_bad + 1))
done
if [ "$(ps_count "$GMK_URL")" = 1 ] && [ "$(ps_count "$HL_URL")" = 1 ]; then
    pass "six polling launchers sent each factory server one listing"
else
    fail "the factory servers were asked for gmktec=$(ps_count "$GMK_URL") mi-homelab=$(ps_count "$HL_URL") listings, not one each"
fi
if [ "$snapshot_bad" = 0 ] && [ -z "$(cat "$DRIVE_LOG")" ] \
    && [ "$(grep -lF 'gmktec=3 hl=1 markers=0 fleet=4' "$CASE_DIR"/launcher-*.log | wc -l)" = 6 ]; then
    pass "every launcher read the same fleet of four from the snapshot and held at the cap"
else
    fail "a launcher read a different fleet or launched (unexpected exits: $snapshot_bad)"
    tail -3 "$CASE_DIR/launcher-1.log" >&2
fi

# --- 15. an old snapshot is refreshed, a young one is not -------------------
echo "--- 15. a snapshot older than the TTL is refreshed before the count"
new_case snapshot-ttl
export FLEET_LAUNCH_BOARD_TTL_S=300
write_board "$BOARD_GMK" 3 gmk
write_board "$BOARD_HL" 1 hl
printf '4\n' > "$CAP_FILE"
run_launcher bd-ib-ttl-seed
write_board "$BOARD_GMK" 1 gmk
run_launcher bd-ib-ttl-young "$CASE_DIR/young.log"
if log_has "$CASE_DIR/young.log" "gmktec=3 hl=1 markers=0 fleet=4" && [ "$(ps_count "$GMK_URL")" = 1 ] && [ ! -s "$DRIVE_LOG" ]; then
    pass "a snapshot younger than the TTL is read without asking the server again"
else
    fail "a young snapshot was not shared (gmktec listings: $(ps_count "$GMK_URL"))"
    tail -3 "$CASE_DIR/young.log" >&2
fi
find "$SNAPSHOT_DIR" -name '*.ps' -exec touch -d '2 hours ago' {} +
run_launcher bd-ib-ttl-old "$CASE_DIR/old.log"
if [ "$(ps_count "$GMK_URL")" -ge 2 ] && [ "$(drive_log_items)" = "bd-ib-ttl-old" ] && [ "$RC" = 0 ]; then
    pass "control: a snapshot older than the TTL is refreshed and the launcher counts the new board"
else
    fail "an old snapshot was not refreshed (gmktec listings: $(ps_count "$GMK_URL") rc=$RC dispatches: $(drive_log_items))"
    tail -4 "$CASE_DIR/old.log" >&2
fi

# --- 16. a refresh that cannot read the board is unknown, not zero ----------
echo "--- 16. an unreadable refresh leaves the fleet count unknown"
new_case snapshot-unreadable
export FLEET_LAUNCH_BOARD_TTL_S=300
write_board "$BOARD_GMK" 0 gmk
: > "$BOARD_HL"
run_launcher bd-ib-unreadable-seed
find "$SNAPSHOT_DIR" -name '*.ps' -exec touch -d '2 hours ago' {} +
rm -f "$BOARD_GMK"
printf '8\n' > "$CAP_FILE"
run_launcher bd-ib-unreadable "$CASE_DIR/unreadable.log"
if log_has "$CASE_DIR/unreadable.log" "fleet not green: gmktec=U" && [ ! -s "$DRIVE_LOG" ]; then
    pass "the stale snapshot's empty board was not used: the count was unknown and nothing launched"
else
    fail "an unreadable refresh fell back to the stale snapshot (rc=$RC dispatches: $(drive_log_items))"
    tail -4 "$CASE_DIR/unreadable.log" >&2
fi

# --- 17. the binding count reads the factory directly -----------------------
# The snapshot says one run is live, the factory has seven. The green check reads the snapshot and
# passes; the binding count under the mutex must read the factory and refuse. Then the same
# launcher, once the factory agrees with the snapshot, launches (the positive control).
echo "--- 17. the binding count reads the board directly, not the snapshot"
new_case snapshot-binding
export FLEET_LAUNCH_BOARD_TTL_S=300
export FLEET_LAUNCH_MAX_WAIT_S=6
write_board "$BOARD_GMK" 1 gmk
: > "$BOARD_HL"
printf '9\n' > "$CAP_FILE"
FLEET_LAUNCH_GMK_CAP=1 run_launcher bd-ib-seed-binding "$CASE_DIR/seed.log"
write_board "$BOARD_GMK" 9 gmk
FLEET_LAUNCH_GMK_CAP=20 run_launcher bd-ib-binding "$CASE_DIR/binding.log"
if log_has "$CASE_DIR/binding.log" "binding count with our marker: fleet=10 cap=9" && [ ! -s "$DRIVE_LOG" ]; then
    pass "the binding count saw the factory's nine runs that the snapshot did not list"
else
    fail "the binding count did not read the board directly (rc=$RC dispatches: $(drive_log_items))"
    tail -4 "$CASE_DIR/binding.log" >&2
fi
write_board "$BOARD_GMK" 1 gmk
run_launcher bd-ib-binding-control "$CASE_DIR/control.log"
if [ "$(drive_log_items)" = "bd-ib-binding-control" ] && [ "$RC" = 0 ]; then
    pass "control: with the factory agreeing with the snapshot the same launcher launches"
else
    fail "control: the launcher did not launch (rc=$RC dispatches: $(drive_log_items))"
    tail -4 "$CASE_DIR/control.log" >&2
fi

# --- 18. launcher lines carry a UTC date-time -------------------------------
echo "--- 18. launcher log lines are stamped with an ISO-8601 UTC date-time"
new_case iso-stamp
write_board "$BOARD_GMK" 2 gmk
write_board "$BOARD_HL" 1 hl
run_launcher bd-ib-stamp "$CASE_DIR/impl-stamp.log"
printf '3\n' > "$CAP_FILE"
"$RESUME_LAUNCHER" bd-ib-stamp-resume > "$CASE_DIR/resume-stamp.log" 2>&1
stamp_pattern='^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z '
if grep -qE "$stamp_pattern" "$CASE_DIR/impl-stamp.log" && ! grep -E '^[0-9]{2}:[0-9]{2}:[0-9]{2} ' "$CASE_DIR/impl-stamp.log" | grep -q . \
    && grep -qE "$stamp_pattern" "$CASE_DIR/resume-stamp.log" && ! grep -E '^[0-9]{2}:[0-9]{2}:[0-9]{2} ' "$CASE_DIR/resume-stamp.log" | grep -q .; then
    pass "both launchers stamp every line with a date, not a time of day alone"
else
    fail "a launcher line carried a time of day without its date"
    head -4 "$CASE_DIR/impl-stamp.log" "$CASE_DIR/resume-stamp.log" >&2
fi

fi

# --- 19. repository holds scope themselves to their named launch kinds ------
# A repository hold yields its own FIFO ticket so another launch kind can run.
# The scope parser fails closed: absent, empty, and malformed kinds all retain
# the former all-kinds hold.  The launch-point case puts the hold in place only
# after the impl launcher has reached the mutex, proving that the binding path
# re-reads the hold before it can call drive.
if [ "$HARNESS_SLICE" = all ] || [ "$HARNESS_SLICE" = scenario316 ]; then
echo "--- 19. repository holds scope launch kinds and are re-read under the mutex"
new_case repository-hold-dispatch
export FLEET_LAUNCH_MAX_WAIT_S=120
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
cat > "$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$(basename "$TENANT")" <<'HOLD'
kinds: dispatch
reason: commit_green ceiling
until: PR 4440 merged
HOLD
DISPATCH_LOG="$CASE_DIR/dispatch.log"
RESUME_CASE_LOG="$CASE_DIR/resume.log"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-held-dispatch > "$DISPATCH_LOG" 2>&1 &
dispatch_pid=$!
if ! wait_for_line "$DISPATCH_LOG" "repository hold present" 5; then
    fail "a dispatch-scoped repository hold did not yield the impl launcher"
fi
TICKET_NS=200 "$RESUME_LAUNCHER" bd-ib-open-resume > "$RESUME_CASE_LOG" 2>&1
resume_rc=$?
if kill -0 "$dispatch_pid" 2>/dev/null \
    && [ -e "$FLEET_LAUNCH_GMK_QUEUE_DIR/100-harness-seat" ] \
    && [ ! -s "$DRIVE_LOG" ] \
    && [ "$resume_rc" = 0 ] \
    && [ "$(cat "$RESUME_LOG")" = bd-ib-open-resume ] \
    && grep -qF 'kinds=dispatch reason=commit_green ceiling until=PR 4440 merged' "$DISPATCH_LOG"; then
    pass "a dispatch-scoped hold keeps the impl ticket, lets resume launch, and logs its scope"
else
    fail "a dispatch-scoped hold did not keep only the impl launch parked"
    tail -n 8 "$DISPATCH_LOG" "$RESUME_CASE_LOG" >&2
fi
stop_launcher "$dispatch_pid"
wait "$dispatch_pid" 2>/dev/null

new_case repository-hold-resume
export FLEET_LAUNCH_MAX_WAIT_S=120
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
printf 'kinds: resume\n' > "$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$(basename "$TENANT")"
RESUME_CASE_LOG="$CASE_DIR/resume.log"
IMPL_LOG="$CASE_DIR/impl.log"
TICKET_NS=100 "$RESUME_LAUNCHER" bd-ib-held-resume > "$RESUME_CASE_LOG" 2>&1 &
resume_pid=$!
if ! wait_for_line "$RESUME_CASE_LOG" "repository hold present" 5; then
    fail "a resume-scoped repository hold did not yield the resume launcher"
fi
ONLY_GMK=1 TICKET_NS=200 "$LAUNCHER" bd-ib-open-dispatch > "$IMPL_LOG" 2>&1
impl_rc=$?
if kill -0 "$resume_pid" 2>/dev/null \
    && grep -lF 'item=bd-ib-held-resume' "$FLEET_LAUNCH_GMK_QUEUE_DIR"/* >/dev/null 2>&1 \
    && [ ! -s "$RESUME_LOG" ] \
    && [ "$impl_rc" = 0 ] \
    && [ "$(drive_log_items)" = bd-ib-open-dispatch ]; then
    pass "a resume-scoped hold keeps the resume ticket and lets dispatch launch"
else
    fail "a resume-scoped hold did not keep only the resume launch parked"
    tail -n 8 "$RESUME_CASE_LOG" "$IMPL_LOG" >&2
fi
stop_launcher "$resume_pid"
wait "$resume_pid" 2>/dev/null

for hold_shape in no-kinds empty-kinds malformed-kinds; do
    new_case "repository-hold-$hold_shape"
    export FLEET_LAUNCH_MAX_WAIT_S=120
    : > "$BOARD_GMK"
    : > "$BOARD_HL"
    printf '8\n' > "$CAP_FILE"
    hold_path="$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$(basename "$TENANT")"
    case "$hold_shape" in
        no-kinds) printf 'reason: all launch kinds\n' > "$hold_path" ;;
        empty-kinds) printf 'kinds: \n' > "$hold_path" ;;
        malformed-kinds) printf 'kinds: dispatch,unknown\n' > "$hold_path" ;;
    esac
    ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-held-impl > "$CASE_DIR/impl.log" 2>&1 &
    impl_pid=$!
    TICKET_NS=200 "$RESUME_LAUNCHER" bd-ib-held-resume > "$CASE_DIR/resume.log" 2>&1 &
    resume_pid=$!
    if wait_for_line "$CASE_DIR/impl.log" "repository hold present" 5 \
        && wait_for_line "$CASE_DIR/resume.log" "repository hold present" 5 \
        && kill -0 "$impl_pid" 2>/dev/null && kill -0 "$resume_pid" 2>/dev/null \
        && [ ! -s "$DRIVE_LOG" ] && [ ! -s "$RESUME_LOG" ]; then
        pass "a $hold_shape repository hold fails closed for both launch kinds"
    else
        fail "a $hold_shape repository hold did not hold both launch kinds"
    fi
    stop_launcher "$impl_pid" "$resume_pid"
    wait "$impl_pid" 2>/dev/null
    wait "$resume_pid" 2>/dev/null
done

new_case repository-hold-launch-point
export FLEET_LAUNCH_MAX_WAIT_S=120
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
mkdir "$FLEET_LAUNCH_GMK_LOCK_DIR"
sleep 600 &
holder_pid=$!
printf 'owner=other-seat pid=%s item=bd-ib-holder\n' "$holder_pid" > "$FLEET_LAUNCH_GMK_LOCK_DIR/holder"
LAUNCH_POINT_LOG="$CASE_DIR/impl.log"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-launch-point > "$LAUNCH_POINT_LOG" 2>&1 &
launch_point_pid=$!
if ! wait_for_line "$LAUNCH_POINT_LOG" "queue for the gmktec mutex" 5; then
    fail "the launch-point impl launcher did not wait for the mutex"
fi
printf 'kinds: dispatch\n' > "$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$(basename "$TENANT")"
kill "$holder_pid" 2>/dev/null
wait "$holder_pid" 2>/dev/null
rm -f "$FLEET_LAUNCH_GMK_LOCK_DIR/holder"
rmdir "$FLEET_LAUNCH_GMK_LOCK_DIR"
# The "repository hold present" line is printed before release_lock frees the mutex, and while
# the hold stands the launcher keeps re-taking and re-yielding the mutex every FLEET_LAUNCH_POLL_S.
# So the yield is judged from the launcher's state, not from one snapshot taken at that log line
# (bd-ib-eb5zl5): poll until one instant shows it alive, its ticket kept, no in-flight marker and
# the mutex free, with nothing driven. The deadline is a liveness guard only; a launcher that never
# frees the mutex, or that drives, never satisfies the condition.
hold_yield_settled() {
    kill -0 "$launch_point_pid" 2>/dev/null \
        && [ -e "$FLEET_LAUNCH_GMK_QUEUE_DIR/100-harness-seat" ] \
        && [ -z "$(find "$FLEET_LAUNCH_INFLIGHT_DIR" -type f -print -quit)" ] \
        && [ ! -d "$FLEET_LAUNCH_GMK_LOCK_DIR" ] \
        && [ ! -s "$DRIVE_LOG" ]
}
wait_for_hold_yield_settled() {
    local limit="$1" deadline
    deadline=$(( $(date +%s) + limit ))
    while :; do
        if hold_yield_settled; then return 0; fi
        [ "$(date +%s)" -lt "$deadline" ] || return 1
        sleep "$HARNESS_POLL_S"
    done
}
hold_yielded=0
if wait_for_line "$LAUNCH_POINT_LOG" "repository hold present" 5 \
    && wait_for_hold_yield_settled 5; then
    hold_yielded=1
fi
stop_launcher "$launch_point_pid"
wait "$launch_point_pid" 2>/dev/null
# Nothing may have been driven at any point, including after the settled instant was observed.
if [ "$hold_yielded" = 1 ] && [ ! -s "$DRIVE_LOG" ]; then
    pass "a hold created during the mutex wait releases the mutex and marker without driving"
else
    fail "a launch-point repository hold did not cleanly yield its bound launch"
    tail -10 "$LAUNCH_POINT_LOG" >&2
fi
fi

echo
echo "=== fleet-launch hermetic harness: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
