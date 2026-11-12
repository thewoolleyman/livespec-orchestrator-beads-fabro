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
    all|scenario242|scenario297|scenario312|scenario316|scenario330|launcher-reexec) ;;
    *)
        echo "usage: run-tests.sh [scenario242|scenario297|scenario312|scenario316|scenario330|launcher-reexec]" >&2
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
# A TERM test holds the direct board read that follows take_mutex, when the
# launcher has written its holder file but has not yet released the mutex.
if [ -n "${STUB_TERM_MUTEX_GATE:-}" ] && [ -f "$FLEET_LAUNCH_GMK_LOCK_DIR/holder" ]; then
    : > "$STUB_TERM_MUTEX_GATE"
    sleep 0.05
fi
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
            if [ -n "${STUB_READY_BLOCKED_UNTIL_RELEASE:-}" ] && [ ! -s "$STUB_RELEASE_LOG" ]; then
                printf 'READY-CHECK stub: blocked until the seat-gated release runs\n'
                exit 3
            fi
            if [ -n "${STUB_READY_REFUSALS:-}" ]; then
                # Refuse the first STUB_READY_REFUSALS calls with STUB_READY_REASON and record what the
                # launcher held at each call: its FIFO ticket, the launch mutex and an in-flight marker.
                count=$(( $(cat "$STUB_READY_COUNTER" 2>/dev/null || echo 0) + 1 ))
                printf '%s\n' "$count" > "$STUB_READY_COUNTER"
                ticket_state=none; lock_state=none; marker_state=none
                if find "$FLEET_LAUNCH_GMK_QUEUE_DIR" -type f -print -quit | grep . >/dev/null; then ticket_state=present; fi
                if [ -d "$STUB_LOCK_DIR" ]; then lock_state=held; fi
                if find "$STUB_INFLIGHT_DIR" -type f -print -quit | grep . >/dev/null; then marker_state=present; fi
                printf 'call=%s ticket=%s mutex=%s marker=%s\n' "$count" "$ticket_state" "$lock_state" "$marker_state" >> "$STUB_READY_OBSERVATIONS"
                if [ "$count" -le "$STUB_READY_REFUSALS" ]; then
                    printf 'READY-CHECK stub: NOT in the ready set (%s)\n' "$STUB_READY_REASON"
                    exit 3
                fi
            fi
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
        ledger-item.py)
            mode=""
            seen=0
            for token in "$@"; do
                if [ "$seen" = 1 ] && [ -z "$mode" ]; then mode=$token; fi
                case ${token##*/} in ledger-item.py) seen=1 ;; esac
            done
            case $mode in
                status)
                    if [ -e "$STUB_ITEM_STATUS_UNREADABLE_FILE" ]; then
                        printf 'unreadable at launcher re-read\n' > "$STUB_ITEM_STATUS_RE_READ_OBSERVATION_FILE"
                        exit 1
                    fi
                    # The launcher's re-read after the stop is the first status call made
                    # once every stub drive process is gone.  Case 20e's admitted arm
                    # holds that read until the TERM watcher has run its trap and its
                    # delayed writer has stored `active`, so the order is decided by
                    # these files and not by how long the stop grace took.  The wait is
                    # bounded only so a hung watcher cannot hang the harness.
                    if [ -n "${STUB_ITEM_STATUS_AWAIT_POST_STOP:-}" ] && [ -s "$STUB_DRIVE_PIDS" ]; then
                        stub_drives_gone=1
                        while read -r stub_drive_pid; do
                            if kill -0 "$stub_drive_pid" 2>/dev/null; then stub_drives_gone=0; fi
                        done < "$STUB_DRIVE_PIDS"
                        if [ "$stub_drives_gone" = 1 ]; then
                            deadline=$(( $(date +%s) + 10 ))
                            while [ ! -e "$STUB_ITEM_STATUS_ADMISSION_WRITTEN_FILE" ] \
                                && [ "$(date +%s)" -lt "$deadline" ]; do
                                sleep "$HARNESS_POLL_S"
                            done
                            if [ "$(cat "$STUB_ITEM_STATUS_FILE")" = active ]; then
                                printf 'active before launcher re-read\n' > "$STUB_ITEM_STATUS_RE_READ_OBSERVATION_FILE"
                            elif [ ! -e "$STUB_ITEM_STATUS_POST_STOP_RENDEZVOUS_FILE" ]; then
                                printf 'ready at launcher re-read: the TERM watcher never ran its trap\n' > "$STUB_ITEM_STATUS_RE_READ_OBSERVATION_FILE"
                            else
                                printf 'ready at launcher re-read: the TERM watcher ran but its writer stored nothing\n' > "$STUB_ITEM_STATUS_RE_READ_OBSERVATION_FILE"
                            fi
                        fi
                    fi
                    printf 'LEDGER-STATUS %s\n' "$(cat "$STUB_ITEM_STATUS_FILE")"
                    ;;
                comment) printf '%s\n' "${!#}" >> "$STUB_LEDGER_COMMENTS" ;;
            esac
            exit 0
            ;;
        dispatcher.py)
            printf 'stub: the Claude credential is usable (HTTP 200)\n'
            exit 0
            ;;
        drive.py)
            item=""
            for token in "$@"; do
                case $token in
                    impl:*) item=${token#impl:} ;;
                    resolve-blocked:*:ready)
                        printf '%s\n' "$token" >> "$STUB_RELEASE_LOG"
                        printf '{"status": "stub-released"}\n'
                        exit 0
                        ;;
                esac
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
                holder_item=$(grep -oE 'item=[^ ]+' "$STUB_LOCK_DIR/holder" 2>/dev/null | sed -n '1p' | cut -d= -f2)
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
            if [ -n "${STUB_DRIVE_ADMIT_GATE:-}" ]; then
                # A drive waiting in its master-CI preflight: the item reads
                # `ready` until the gate file appears, then `active` (admitted),
                # and the run is submitted only after STUB_DRIVE_SUBMIT_GATE too.
                if [ -n "${STUB_DRIVE_START_GATE:-}" ]; then
                    # A slow drive start: the drive has been invoked but has not yet
                    # reached its preflight wait. The harness opens the gate once it
                    # has advanced its own clock past any fixed startup bound.
                    : > "$STUB_DRIVE_START_GATE.reached"
                    start_deadline=$(( $(date +%s) + ${HARNESS_PREFLIGHT_HANG_GUARD_S:-300} ))
                    while [ ! -e "$STUB_DRIVE_START_GATE" ] \
                        && [ "$(date +%s)" -lt "$start_deadline" ]; do
                        sleep "$HARNESS_POLL_S"
                    done
                fi
                printf '%s\n' "$item" >> "$STUB_DRIVE_WAITING"
                printf '%s\n' "$$" >> "$STUB_DRIVE_PIDS"
                if [ -n "${STUB_DRIVE_ADMIT_ON_TERM:-}" ]; then
                    # Keep the primary drive alive until stop_drive exhausts
                    # its grace period and sends KILL, as a loaded shell can
                    # when TERM arrives during a foreground poll.
                    trap '' TERM
                    # This watcher handles TERM while the primary stub is in
                    # its polling sleep.  Its TERM trap starts a new delayed
                    # admission writer, which is not in stop_drive's PID
                    # snapshot and therefore survives the grace-period KILL.
                    # The status stub rendezvouses with that writer, so case
                    # 20e orders its post-stop read without relying on timing.
                    (
                        trap '
                            : > "$STUB_ITEM_STATUS_POST_STOP_RENDEZVOUS_FILE"
                            (
                                deadline=$(( $(date +%s) + 10 ))
                                while [ ! -e "$STUB_DRIVE_ADMIT_AFTER_STOP_GATE_FILE" ] \
                                    && [ "$(date +%s)" -lt "$deadline" ]; do
                                    sleep "$HARNESS_POLL_S"
                                done
                                if [ -e "$STUB_DRIVE_ADMIT_AFTER_STOP_GATE_FILE" ]; then
                                    printf "active\\n" > "$STUB_ITEM_STATUS_FILE"
                                    : > "$STUB_ITEM_STATUS_ADMISSION_WRITTEN_FILE"
                                fi
                            ) >/dev/null 2>&1 &
                            exit 143
                        ' TERM
                        # Armed: the harness sets the hold only after this exists, so
                        # the stop's TERM cannot reach the watcher before its trap.
                        : > "$STUB_DRIVE_WATCHER_ARMED_FILE"
                        while :; do
                            sleep 60 &
                            wait "$!"
                        done
                    ) &
                fi
                wait_deadline=$(( $(date +%s) + 60 ))
                while [ ! -e "$STUB_DRIVE_ADMIT_GATE" ] && [ "$(date +%s)" -lt "$wait_deadline" ]; do
                    sleep "$HARNESS_POLL_S"
                done
                printf 'active\n' > "$STUB_ITEM_STATUS_FILE"
                while [ -n "${STUB_DRIVE_SUBMIT_GATE:-}" ] && [ ! -e "$STUB_DRIVE_SUBMIT_GATE" ] \
                    && [ "$(date +%s)" -lt "$wait_deadline" ]; do
                    sleep "$HARNESS_POLL_S"
                done
            fi
            if [ -n "$item" ] && [ -n "$server" ]; then
                printf '%s %s\n' "$server" "$item" > "$STUB_DRIVEN_DIR/$item"
            fi
            # A gated drive lingers after submitting, as a real drive polls the run, so the
            # launcher's listing poll sees the run before it sees the drive exit.
            [ -z "${STUB_DRIVE_ADMIT_GATE:-}" ] || sleep 0.5
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
            if find "$STUB_INFLIGHT_DIR" -type f -print -quit | grep . >/dev/null; then marker_state=present; fi
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
RELEASE_LOG=""
PS_LOG=""
SNAPSHOT_DIR=""
BOARD_GMK=""
BOARD_HL=""
CAP_FILE=""
HOLD_FILE=""

# new_case <name>: a fresh set of throwaway directories and fixtures, and the
# environment every launcher invocation of this case inherits.
new_case() {
    CASE_NAME="$1"
    CASE_DIR="$WORK/case/$CASE_NAME"
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
    RELEASE_LOG="$CASE_DIR/release-log"
    : > "$RELEASE_LOG"
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
    export STUB_RELEASE_LOG="$RELEASE_LOG"
    export STUB_PS_LOG="$PS_LOG"
    unset STUB_PS_DELAY_S
    export STUB_READY_EXIT=0
    unset STUB_READY_REFUSALS STUB_READY_REASON
    export STUB_READY_COUNTER="$CASE_DIR/ready-counter"
    export STUB_READY_OBSERVATIONS="$CASE_DIR/ready-observations"
    : > "$STUB_READY_OBSERVATIONS"
    export STUB_PREFLIGHT_EXIT=0
    unset STUB_PREFLIGHT_SLOW_ITEM STUB_PREFLIGHT_SLOW_S STUB_PREFLIGHT_FAIL_ITEM
    export STUB_PREFLIGHT_RELEASE="$CASE_DIR/release-held-preflight"
    export STUB_SSH_IDLE=95.00
    export STUB_ITEM_STATUS_FILE="$CASE_DIR/item-status"
    printf 'ready\n' > "$STUB_ITEM_STATUS_FILE"
    export STUB_LEDGER_COMMENTS="$CASE_DIR/ledger-comments"
    : > "$STUB_LEDGER_COMMENTS"
    export STUB_DRIVE_WAITING="$CASE_DIR/drive-waiting"
    : > "$STUB_DRIVE_WAITING"
    export STUB_DRIVE_PIDS="$CASE_DIR/drive-pids"
    : > "$STUB_DRIVE_PIDS"
    export STUB_DRIVE_ADMIT_GATE_FILE="$CASE_DIR/admit-gate"
    export STUB_DRIVE_SUBMIT_GATE_FILE="$CASE_DIR/submit-gate"
    export STUB_ITEM_STATUS_UNREADABLE_FILE="$CASE_DIR/item-status-unreadable"
    export STUB_ITEM_STATUS_RE_READ_OBSERVATION_FILE="$CASE_DIR/item-status-re-read-observation"
    export STUB_ITEM_STATUS_POST_STOP_RENDEZVOUS_FILE="$CASE_DIR/post-stop-status-rendezvous"
    export STUB_DRIVE_WATCHER_ARMED_FILE="$CASE_DIR/watcher-armed"
    export STUB_ITEM_STATUS_ADMISSION_WRITTEN_FILE="$CASE_DIR/admission-written"
    export STUB_DRIVE_ADMIT_AFTER_STOP_GATE_FILE="$CASE_DIR/admit-after-stop-gate"
    unset STUB_DRIVE_ADMIT_GATE STUB_DRIVE_SUBMIT_GATE STUB_DRIVE_ADMIT_ON_TERM STUB_ITEM_STATUS_AWAIT_POST_STOP

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
    export FLEET_LAUNCH_STOP_GRACE_S=5
    unset STUB_RESUME_UNLISTED STUB_READY_BLOCKED_UNTIL_RELEASE
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

# This protects the harness from a hung launcher. It is not a startup budget:
# each Scenario 297 launcher normally reaches the stub preflight in milliseconds.
HARNESS_PREFLIGHT_HANG_GUARD_S=${HARNESS_PREFLIGHT_HANG_GUARD_S:-300}
PREFLIGHT_FAILURE_DETAIL=""

# wait_for_preflight <case> <launcher> <pid> <log> <item> <count>: wait until
# the stub recorded the requested number of Definition-of-Done preflights. A
# launcher that exits first is a verdict immediately; the shared guard exists
# only to stop a genuinely hung launcher from holding the harness forever.
wait_for_preflight() {
    local case_name="$1" launcher="$2" pid="$3" log="$4" item="$5" count="$6"
    local deadline launcher_rc log_tail reason launcher_alive
    deadline=$(( $(date +%s) + HARNESS_PREFLIGHT_HANG_GUARD_S ))
    while :; do
        # Liveness is sampled BEFORE the record is read: a launcher records its
        # preflight before it can exit, so a launcher seen dead here has already
        # written everything the read below can find.  Reading the record first
        # let a fast preflight finish between the two checks and be reported as
        # a launcher that never preflighted.
        launcher_alive=1
        kill -0 "$pid" 2>/dev/null || launcher_alive=0
        if [ "$(preflight_count "$item")" -ge "$count" ]; then return 0; fi
        if [ "$launcher_alive" = 0 ]; then
            wait "$pid"; launcher_rc=$?
            reason="exited rc=$launcher_rc"
            break
        fi
        if [ "$(date +%s)" -ge "$deadline" ]; then
            reason="hung past ${HARNESS_PREFLIGHT_HANG_GUARD_S}s guard"
            break
        fi
        sleep "$HARNESS_POLL_S"
    done
    log_tail=$(tail -8 "$log" 2>&1 || true)
    PREFLIGHT_FAILURE_DETAIL="case=$case_name launcher=$launcher did not reach preflight ($reason); tail of $log:
${log_tail:-<no launcher log output>}"
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

# line_has_all <log> <needle>...: some single line of the log holds every needle.
line_has_all() {
    local log="$1" line needle all
    shift
    while IFS= read -r line; do
        all=1
        for needle in "$@"; do
            case $line in *"$needle"*) ;; *) all=0; break ;; esac
        done
        [ "$all" = 1 ] && return 0
    done < "$log"
    return 1
}
# set_hold <path> <text>: create a hold file whole in one step, so a launcher polling the path never reads it half written.
set_hold() {
    printf '%b\n' "$2" > "$1.new"
    mv "$1.new" "$1"
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
if ! wait_for_preflight "$CASE_NAME" older "$older_pid" "$CASE_DIR/older.log" bd-ib-older 1; then
    fail "$PREFLIGHT_FAILURE_DETAIL"
fi
ONLY_GMK=1 TICKET_NS=200 "$LAUNCHER" bd-ib-younger > "$CASE_DIR/younger.log" 2>&1 &
younger_pid=$!
# The older preflight is held, so the older launcher cannot bind until the
# release below: a younger preflight seen first ran while it was queued.
if ! wait_for_preflight "$CASE_NAME" younger "$younger_pid" "$CASE_DIR/younger.log" bd-ib-younger 1; then
    fail "$PREFLIGHT_FAILURE_DETAIL"
elif [ ! -s "$DRIVE_LOG" ]; then
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
wait_for_preflight "$CASE_NAME" older "$older_pid" "$CASE_DIR/older.log" bd-ib-stale-older 1 \
    || fail "$PREFLIGHT_FAILURE_DETAIL"
ONLY_GMK=1 TICKET_NS=200 "$LAUNCHER" bd-ib-stale-younger > "$CASE_DIR/younger.log" 2>&1 &
younger_pid=$!
if ! wait_for_preflight "$CASE_NAME" younger "$younger_pid" "$CASE_DIR/younger.log" bd-ib-stale-younger 1; then
    fail "$PREFLIGHT_FAILURE_DETAIL"
elif [ -s "$DRIVE_LOG" ]; then
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
wait_for_preflight "$CASE_NAME" older "$older_pid" "$CASE_DIR/older.log" bd-ib-failing-older 1 \
    || fail "$PREFLIGHT_FAILURE_DETAIL"
ONLY_GMK=1 TICKET_NS=200 "$LAUNCHER" bd-ib-failing-younger > "$CASE_DIR/younger.log" 2>&1 &
younger_pid=$!
if ! wait_for_preflight "$CASE_NAME" younger "$younger_pid" "$CASE_DIR/younger.log" bd-ib-failing-younger 1; then
    stop_launcher "$younger_pid"
    wait "$younger_pid"; younger_rc=$?
    fail "$PREFLIGHT_FAILURE_DETAIL"
elif [ ! -s "$DRIVE_LOG" ]; then
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

# Cases 9-14 cover the resume launcher, seat-gated releases and in-flight marker count, not
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

# --- 10. a seat-gated direct release waits for the cap ----------------------
# A blocked item is deliberately absent from the ready set until its release
# action runs.  The release must therefore bypass that first ready-set read,
# but only after the normal FIFO/cap binding has made space and retained its
# in-flight marker.
echo "--- 10. a seat-gated direct release waits for the fleet cap"
new_case direct-release-cap
export FLEET_LAUNCH_MAX_WAIT_S=120
export STUB_READY_BLOCKED_UNTIL_RELEASE=1
write_board "$BOARD_GMK" 8 gmk
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
DIRECT_RELEASE_LOG="$CASE_DIR/direct-release-launcher.log"
RELEASE_BLOCKED=1 ONLY_GMK=1 "$LAUNCHER" bd-ib-direct-release > "$DIRECT_RELEASE_LOG" 2>&1 &
direct_release_pid=$!
if wait_for_line "$DIRECT_RELEASE_LOG" "fleet not green" 30 \
    && [ ! -s "$RELEASE_LOG" ] \
    && [ ! -s "$DRIVE_LOG" ]; then
    pass "a seat-gated direct release waits for fleet headroom before it releases or drives"
else
    fail "the direct release bypassed the fleet cap or stalled before the cap gate"
    tail -8 "$DIRECT_RELEASE_LOG" >&2
fi
write_board "$BOARD_GMK" 7 gmk
wait "$direct_release_pid"; direct_release_rc=$?
if [ "$direct_release_rc" = 0 ] \
    && grep -qx 'resolve-blocked:bd-ib-direct-release:ready' "$RELEASE_LOG" \
    && grep -qx 'bd-ib-direct-release' "$DRIVE_LOG"; then
    pass "the release and its drive run only after the capped FIFO binding"
else
    fail "the seat-gated direct release did not complete through the launcher (rc=$direct_release_rc releases=$(tr '\n' ' ' < "$RELEASE_LOG") drives=$(drive_log_items))"
    tail -8 "$DIRECT_RELEASE_LOG" >&2
fi

# --- 10b. a held direct release counts as one in-flight launch --------------
# While the direct release's drive runs and before its run lists, the marker it
# kept must count against the cap for a queued second launcher: with one slot
# free on the board, the held release fills it, so the second launcher sees the
# fleet at the cap and starts no drive of its own.
echo "--- 10b. a queued launcher counts a held direct release as in flight"
new_case direct-release-inflight-counted
export FLEET_LAUNCH_MAX_WAIT_S=120
export STUB_READY_BLOCKED_UNTIL_RELEASE=1
export STUB_DRIVE_ADMIT_GATE="$STUB_DRIVE_ADMIT_GATE_FILE"
write_board "$BOARD_GMK" 7 gmk
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
DIRECT_RELEASE_LOG="$CASE_DIR/direct-release-launcher.log"
RELEASE_BLOCKED=1 ONLY_GMK=1 "$LAUNCHER" bd-ib-held-release > "$DIRECT_RELEASE_LOG" 2>&1 &
held_release_pid=$!
held_deadline=$(( $(date +%s) + 60 ))
while ! grep -qx 'bd-ib-held-release' "$STUB_DRIVE_WAITING" && [ "$(date +%s)" -lt "$held_deadline" ]; do
    sleep "$HARNESS_POLL_S"
done
if grep -qx 'bd-ib-held-release' "$STUB_DRIVE_WAITING" \
    && grep -qx 'resolve-blocked:bd-ib-held-release:ready' "$RELEASE_LOG" \
    && [ -n "$(find "$CASE_DIR/inflight" -type f -print -quit)" ]; then
    pass "the direct release holds its in-flight marker while its drive runs and before its run lists"
else
    fail "the direct release did not hold a marker during its drive (releases=$(tr '\n' ' ' < "$RELEASE_LOG"))"
    tail -8 "$DIRECT_RELEASE_LOG" >&2
fi
SECOND_LOG="$CASE_DIR/second-launcher.log"
FLEET_LAUNCH_MAX_WAIT_S=4 ONLY_GMK=1 "$LAUNCHER" bd-ib-second > "$SECOND_LOG" 2>&1; second_rc=$?
if [ "$second_rc" = 75 ] && log_has "$SECOND_LOG" "fleet=8 cap=8" \
    && ! grep -qx 'bd-ib-second' "$DRIVE_LOG"; then
    pass "a queued launcher counts the held direct release against the cap and starts no drive"
else
    fail "a queued launcher did not count the held direct release (rc=$second_rc drives=$(drive_log_items))"
    tail -6 "$SECOND_LOG" >&2
fi
: > "$STUB_DRIVE_ADMIT_GATE_FILE"
wait "$held_release_pid"; held_release_rc=$?
if [ "$held_release_rc" = 0 ] && [ -z "$(find "$CASE_DIR/inflight" -type f -print -quit)" ]; then
    pass "the direct release drops its marker once its run lists"
else
    fail "the direct release did not finish cleanly (rc=$held_release_rc)"
    tail -8 "$DIRECT_RELEASE_LOG" >&2
fi

# --- 11. a resume marker stays counted until the board lists the run --------
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

# --- 12. an unreadable in-flight directory counts as at the cap -------------
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

# --- 13. a launch that lists between the board read and the marker read ----
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

# --- 14. the impl launcher counts a launch listed mid-read too -------------
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

# --- 14a. a refresh handoff is re-checked after taking the lock -------------
# A peer can finish its refresh after this launcher sees the snapshot as stale
# but before it takes the now-free lock. Make that window deterministic: the
# first age check says stale while writing the peer's fresh snapshot. The
# post-lock age check must then read that snapshot without another listing.
echo "--- 14a. a refresh handoff re-checks the shared board snapshot"
new_case snapshot-refresh-handoff
export FLEET_LAUNCH_BOARD_TTL_S=300
mkdir -p "$SNAPSHOT_DIR"
. "$LAUNCH_DIR/board-snapshot.sh"
handoff_snapshot=$(board_snapshot_file "$GMK_URL")
handoff_age_checks=0
board_snapshot_age_ok() {
    handoff_age_checks=$((handoff_age_checks + 1))
    if [ "$handoff_age_checks" = 1 ]; then
        printf '%s\n' "$BOARD_HEADER" > "$handoff_snapshot"
        return 1
    fi
    [ -f "$1" ]
}
handoff_text=$(board_snapshot_text "$STUB/fabro" "$GMK_URL")
handoff_rc=$?
if [ "$handoff_rc" = 0 ] && [ "$handoff_text" = "$BOARD_HEADER" ] \
    && [ "$(ps_count "$GMK_URL")" = 0 ] && [ ! -d "$handoff_snapshot.refresh.d" ]; then
    pass "a launcher that takes a refreshed lock reads the peer snapshot without listing"
else
    fail "a launcher listed after a peer refreshed the snapshot (rc=$handoff_rc listings=$(ps_count "$GMK_URL"))"
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
if grep -qE "$stamp_pattern" "$CASE_DIR/impl-stamp.log" && ! grep -E '^[0-9]{2}:[0-9]{2}:[0-9]{2} ' "$CASE_DIR/impl-stamp.log" | grep . >/dev/null \
    && grep -qE "$stamp_pattern" "$CASE_DIR/resume-stamp.log" && ! grep -E '^[0-9]{2}:[0-9]{2}:[0-9]{2} ' "$CASE_DIR/resume-stamp.log" | grep . >/dev/null; then
    pass "both launchers stamp every line with a date, not a time of day alone"
else
    fail "a launcher line carried a time of day without its date"
    head -4 "$CASE_DIR/impl-stamp.log" "$CASE_DIR/resume-stamp.log" >&2
fi

fi

# --- 18a. a marker released after its listed run leaves the board -----------
# Scenario 242 — The provisional fleet launch check fails the build on a broken
# launcher. A dead launcher may leave its marker behind while its drive
# merge-polls. Once another launcher has observed that marker's run on a board,
# the marker must no longer hold a slot after the run leaves that board. A
# never-listed marker remains counted while that drive is alive.
if [ "$HARNESS_SLICE" = all ] || [ "$HARNESS_SLICE" = scenario242 ]; then
# A stand-in for a dead launcher's live drive, whose command line the
# launcher's `pgrep -f "drive.py .*--action impl:<item>( |$)"` matches.  The
# drive arguments ride as ordinary trailing argv of a sleeping python3, never
# as a renamed argv[0]: the uutils coreutils multicall sleep refuses an
# unrecognised argv[0] ("Security violation: Requested utility ... does not
# match executable name"), and so does a mise shim ("... is not a valid
# shim") (bd-ib-jp82i).
start_named_drive() {
    python3 -c 'import time; time.sleep(600)' drive.py --action "impl:$1" &
}
echo "--- 18a. releases a listed-and-finished drive's stale marker"
new_case listed-marker-left-board
export FLEET_LAUNCH_MAX_WAIT_S=4
write_board "$BOARD_GMK" 7 gmk
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
start_named_drive bd-ib-ended
ended_drive_pid=$!
ended_marker="$FLEET_LAUNCH_INFLIGHT_DIR/100-stopped-seat-bd-ib-ended"
echo "owner=stopped-seat pid=999999 item=bd-ib-ended factory=petri" > "$ended_marker"
printf '%s %s\n' "$GMK_URL" bd-ib-ended > "$CASE_DIR/driven/bd-ib-ended"
ONLY_GMK=1 "$LAUNCHER" bd-ib-observer > "$CASE_DIR/observer.log" 2>&1 &
observer_pid=$!
if wait_for_line "$ended_marker" "listed=1" 10; then
    pass "a board observer records that the dead launcher's run listed"
else
    fail "the observed listed run was not recorded on its in-flight marker"
fi
stop_launcher "$observer_pid"
wait "$observer_pid" 2>/dev/null || true
rm -f "$CASE_DIR/driven/bd-ib-ended"
run_launcher bd-ib-after-ended "$CASE_DIR/after-ended.log"
if [ "$RC" = 0 ] && [ "$(drive_log_items)" = bd-ib-after-ended ]; then
    pass "a listed-and-finished run's merge-polling drive no longer holds a fleet slot"
else
    fail "a listed-and-finished run still held a fleet slot (rc=$RC dispatches: $(drive_log_items))"
    tail -6 "$CASE_DIR/after-ended.log" >&2
fi
kill "$ended_drive_pid" 2>/dev/null; wait "$ended_drive_pid" 2>/dev/null

new_case unlisted-marker-stays-counted
export FLEET_LAUNCH_MAX_WAIT_S=4
write_board "$BOARD_GMK" 7 gmk
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
start_named_drive bd-ib-unlisted
unlisted_drive_pid=$!
echo "owner=stopped-seat pid=999999 item=bd-ib-unlisted factory=petri" \
    > "$FLEET_LAUNCH_INFLIGHT_DIR/100-stopped-seat-bd-ib-unlisted"
run_launcher bd-ib-must-wait "$CASE_DIR/unlisted.log"
if [ "$RC" = 75 ] && [ ! -s "$DRIVE_LOG" ] \
    && log_has "$CASE_DIR/unlisted.log" "fleet=8 cap=8"; then
    pass "an unlisted marker remains counted while its dead launcher has a live drive"
else
    fail "an unlisted marker did not hold the fleet slot (rc=$RC dispatches: $(drive_log_items))"
    tail -6 "$CASE_DIR/unlisted.log" >&2
fi
kill "$unlisted_drive_pid" 2>/dev/null; wait "$unlisted_drive_pid" 2>/dev/null
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

# --- 20. a hold re-read until admission stops a launched drive ---------------
# Scenario 330. The stub drive waits in its master-CI preflight (the item reads
# `ready`) until the harness opens an admission gate, then reads `active`, and
# submits its run only after a second gate. A hold file created while the drive
# waits must stop it before any run is submitted and keep the launcher's ticket;
# a hold created once the item reads `active` must not.
if [ "$HARNESS_SLICE" = all ] || [ "$HARNESS_SLICE" = scenario330 ]; then
echo "--- 20. holds are re-read until admission"

# prepare_330_case <name>: a fresh case with empty boards and a waiting drive.
prepare_330_case() {
    new_case "$1"
    export FLEET_LAUNCH_MAX_WAIT_S=120
    : > "$BOARD_GMK"
    : > "$BOARD_HL"
    printf '8\n' > "$CAP_FILE"
    export STUB_DRIVE_ADMIT_GATE="$STUB_DRIVE_ADMIT_GATE_FILE"
    export STUB_DRIVE_SUBMIT_GATE="$STUB_DRIVE_SUBMIT_GATE_FILE"
}
# harness_now: the case-20 waits' clock. HARNESS_CLOCK_SKEW_FILE, when it names a
# file, adds its seconds, so a case can put the clock past any fixed startup bound
# while the drive is held, without sleeping that long.
harness_now() {
    local skew=0
    if [ -n "${HARNESS_CLOCK_SKEW_FILE:-}" ] && [ -s "$HARNESS_CLOCK_SKEW_FILE" ]; then
        skew=$(cat "$HARNESS_CLOCK_SKEW_FILE")
    fi
    echo $(( $(date +%s) + skew ))
}
# wait_on_launcher <launcher> <pid> <log> <condition...>: until the condition holds.
# The verdict is the launcher's own state: the condition holding passes, and the
# launcher exiting first fails at once. HARNESS_PREFLIGHT_HANG_GUARD_S only stops a
# genuinely hung launcher; it is not a startup budget, so a slow start still passes.
# On failure WAIT_FAILURE_DETAIL names the reason and the last launcher log line.
WAIT_FAILURE_DETAIL=""
wait_on_launcher() {
    local launcher="$1" pid="$2" log="$3" deadline reason alive last_line
    shift 3
    deadline=$(( $(harness_now) + HARNESS_PREFLIGHT_HANG_GUARD_S ))
    while :; do
        # Liveness first, then the condition, as wait_for_preflight samples them.
        alive=1
        kill -0 "$pid" 2>/dev/null || alive=0
        if "$@"; then return 0; fi
        if [ "$alive" = 0 ]; then reason="the launcher exited first"; break; fi
        if [ "$(harness_now)" -ge "$deadline" ]; then
            reason="hung past the ${HARNESS_PREFLIGHT_HANG_GUARD_S}s guard"
            break
        fi
        sleep "$HARNESS_POLL_S"
    done
    last_line=$(tail -n 1 "$log" 2>/dev/null || true)
    WAIT_FAILURE_DETAIL="launcher=$launcher: $reason; last launcher log line: ${last_line:-<no launcher log output>}"
    return 1
}
drive_invoked_at_least() { [ "$(wc -l < "$STUB_DRIVE_WAITING")" -ge "$1" ]; }
item_reads() { [ "$(cat "$STUB_ITEM_STATUS_FILE")" = "$1" ]; }
# wait_for_drive_invocations <count> <pid> <log>: until the stub drive has started <count> times.
wait_for_drive_invocations() { wait_on_launcher drive-start "$2" "$3" drive_invoked_at_least "$1"; }
# wait_for_item_status <status> <pid> <log>: until the stub item reads <status>.
wait_for_item_status() { wait_on_launcher item-status "$2" "$3" item_reads "$1"; }
# drive_gone: no stub drive process is left running for this case.
drive_gone() {
    local pid
    while read -r pid; do kill -0 "$pid" 2>/dev/null && return 1; done < "$STUB_DRIVE_PIDS"
    return 0
}
wait_for_drive_gone() {
    local limit="$1" deadline
    deadline=$(( $(date +%s) + limit ))
    while ! drive_gone; do
        [ "$(date +%s)" -lt "$deadline" ] || return 1
        sleep "$HARNESS_POLL_S"
    done
}
# wait_for_file: the file exists.  The limit only guards against a hang.
wait_for_file() {
    local file="$1" limit="$2" deadline
    deadline=$(( $(date +%s) + limit ))
    while [ ! -e "$file" ]; do
        [ "$(date +%s)" -lt "$deadline" ] || return 1
        sleep "$HARNESS_POLL_S"
    done
}
inflight_empty() { [ -z "$(find "$FLEET_LAUNCH_INFLIGHT_DIR" -type f -print -quit)" ]; }

# 20a. A hold set before admission stops the drive; the ticket survives; the
# positive control (hold removed, gates opened) then launches and lists.
prepare_330_case hold-before-admission
STOP_LOG="$CASE_DIR/launcher.log"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-hold-before > "$STOP_LOG" 2>&1 &
stop_pid=$!
if wait_for_drive_invocations 1 "$stop_pid" "$STOP_LOG"; then
    set_hold "$HOLD_FILE" 'engine restart'
    if wait_for_line "$STOP_LOG" "stopped the drive for bd-ib-hold-before" 10 \
        && kill -0 "$stop_pid" 2>/dev/null \
        && [ -e "$FLEET_LAUNCH_GMK_QUEUE_DIR/100-harness-seat" ] \
        && inflight_empty && drive_gone \
        && [ ! -e "$STUB_DRIVEN_DIR/bd-ib-hold-before" ] \
        && line_has_all "$STOP_LOG" 'stopped the drive for bd-ib-hold-before' 'ticket 100' 'engine restart'; then
        pass "a hold set before admission stops the drive, keeps ticket 100 and logs the hold text"
    else
        fail "a hold set before admission did not stop the drive and keep its ticket"
        tail -n 8 "$STOP_LOG" >&2
    fi
    rm -f "$HOLD_FILE"
    : > "$STUB_DRIVE_ADMIT_GATE_FILE"
    : > "$STUB_DRIVE_SUBMIT_GATE_FILE"
    wait "$stop_pid"
    stop_rc=$?
    if [ "$stop_rc" = 0 ] && [ "$(drive_log_items)" = "bd-ib-hold-before bd-ib-hold-before" ] \
        && log_has "$STOP_LOG" "LISTED on petri" && [ ! -s "$STUB_LEDGER_COMMENTS" ]; then
        pass "with the hold removed the stopped launcher re-launches and its run lists"
    else
        fail "the stopped launcher did not re-launch once the hold was removed (rc=$stop_rc)"
        tail -n 8 "$STOP_LOG" >&2
    fi
else
    fail "the stub drive never started for the hold-before-admission case ($WAIT_FAILURE_DETAIL)"
    stop_launcher "$stop_pid"
    wait "$stop_pid" 2>/dev/null
fi

# 20b. A repository hold scoped to dispatch stops the drive and logs its fields;
# one scoped to resume does not.
prepare_330_case repository-hold-before-admission
STOP_LOG="$CASE_DIR/launcher.log"
printf 'kinds: resume\n' > "$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$(basename "$TENANT")"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-repo-hold > "$STOP_LOG" 2>&1 &
stop_pid=$!
if wait_for_drive_invocations 1 "$stop_pid" "$STOP_LOG"; then
    sleep 0.3
    if log_has "$STOP_LOG" "stopped the drive"; then
        fail "a resume-scoped repository hold stopped an impl drive"
    fi
    set_hold "$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$(basename "$TENANT")" \
        'kinds: dispatch\nreason: commit_green ceiling\nuntil: PR 4440 merged'
    if wait_for_line "$STOP_LOG" "stopped the drive for bd-ib-repo-hold" 10 \
        && [ -e "$FLEET_LAUNCH_GMK_QUEUE_DIR/100-harness-seat" ] && inflight_empty \
        && line_has_all "$STOP_LOG" 'stopped the drive' 'reason=commit_green ceiling until=PR 4440 merged'; then
        pass "a dispatch-scoped repository hold stops the drive and a resume-scoped one does not"
    else
        fail "a dispatch-scoped repository hold did not stop the drive with its fields"
        tail -n 8 "$STOP_LOG" >&2
    fi
else
    fail "the stub drive never started for the repository-hold case ($WAIT_FAILURE_DETAIL)"
fi
stop_launcher "$stop_pid"
wait "$stop_pid" 2>/dev/null

# 20c. A hold set after the item reads active does not stop the drive.
prepare_330_case hold-after-admission
STOP_LOG="$CASE_DIR/launcher.log"
: > "$STUB_DRIVE_ADMIT_GATE_FILE"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-hold-after > "$STOP_LOG" 2>&1 &
stop_pid=$!
if wait_for_item_status active "$stop_pid" "$STOP_LOG"; then
    set_hold "$HOLD_FILE" 'engine restart'
    sleep 0.3
    held_alive=0
    if kill -0 "$stop_pid" 2>/dev/null && ! drive_gone; then held_alive=1; fi
    : > "$STUB_DRIVE_SUBMIT_GATE_FILE"
    wait "$stop_pid"
    stop_rc=$?
    if [ "$held_alive" = 1 ] && [ "$stop_rc" = 0 ] && ! log_has "$STOP_LOG" "stopped the drive" \
        && log_has "$STOP_LOG" "LISTED on petri" && [ "$(drive_log_items)" = bd-ib-hold-after ]; then
        pass "a hold set after the item reads active leaves the drive alone and the run lists"
    else
        fail "a hold set after admission disturbed the drive (rc=$stop_rc alive=$held_alive)"
        tail -n 8 "$STOP_LOG" >&2
    fi
else
    fail "the stub item never read active in the hold-after-admission case ($WAIT_FAILURE_DETAIL)"
    stop_launcher "$stop_pid"
    wait "$stop_pid" 2>/dev/null
fi

# 20d. With no hold file the drive proceeds from launch to listing as before.
prepare_330_case no-hold
STOP_LOG="$CASE_DIR/launcher.log"
: > "$STUB_DRIVE_ADMIT_GATE_FILE"
: > "$STUB_DRIVE_SUBMIT_GATE_FILE"
ONLY_GMK=1 TICKET_NS=100 run_launcher bd-ib-no-hold "$STOP_LOG"
if [ "$RC" = 0 ] && log_has "$STOP_LOG" "LISTED on petri" && ! log_has "$STOP_LOG" "stopped the drive" \
    && [ "$(drive_log_items)" = bd-ib-no-hold ]; then
    pass "with no hold file the drive proceeds from launch to the run listing"
else
    fail "a launch with no hold file did not proceed to listing (rc=$RC)"
    tail -n 8 "$STOP_LOG" >&2
fi

# report_case_20e_admission_order: on any case 20e failure, say whether the stub drive had written
# `active` before the launcher re-read the item's status, or that the re-read did not occur, and
# whether the watcher armed and the TERM rendezvous and the admission write happened.
report_case_20e_admission_order() {
    printf 'stub admission at launcher re-read: %s\n' \
        "$(cat "$STUB_ITEM_STATUS_RE_READ_OBSERVATION_FILE" 2>/dev/null || echo 'not-observed: the launcher never re-read the status after every stub drive was gone')" >&2
    printf 'watcher armed: %s; TERM rendezvous: %s; admission written: %s\n' \
        "$([ -e "$STUB_DRIVE_WATCHER_ARMED_FILE" ] && echo yes || echo no)" \
        "$([ -e "$STUB_ITEM_STATUS_POST_STOP_RENDEZVOUS_FILE" ] && echo yes || echo no)" \
        "$([ -e "$STUB_ITEM_STATUS_ADMISSION_WRITTEN_FILE" ] && echo yes || echo no)" >&2
}

# 20e. A drive that admits its item as the stop takes effect, or whose status
# cannot be read after the stop, ends in a stopped-after-admission non-run exit.
for after_stop in admitted unreadable; do
    prepare_330_case "stopped-after-admission-$after_stop"
    STOP_LOG="$CASE_DIR/launcher.log"
    if [ "$after_stop" = admitted ]; then
        export STUB_DRIVE_ADMIT_ON_TERM=1 STUB_ITEM_STATUS_AWAIT_POST_STOP=1
    fi
    ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-stop-admit > "$STOP_LOG" 2>&1 &
    stop_pid=$!
    if wait_for_drive_invocations 1 "$stop_pid" "$STOP_LOG"; then
        if [ "$after_stop" = unreadable ]; then : > "$STUB_ITEM_STATUS_UNREADABLE_FILE"; fi
        if [ "$after_stop" = admitted ] && ! wait_for_file "$STUB_DRIVE_WATCHER_ARMED_FILE" 10; then
            fail "the stub drive's TERM watcher never armed its trap before case 20e set the hold"
            report_case_20e_admission_order
            stop_launcher "$stop_pid"
            wait "$stop_pid" 2>/dev/null
            continue
        fi
        set_hold "$HOLD_FILE" 'engine restart'
        if [ "$after_stop" = admitted ] \
            && { ! wait_for_drive_gone 10 || ! wait_for_file "$STUB_ITEM_STATUS_POST_STOP_RENDEZVOUS_FILE" 10; }; then
            fail "the stopped drive did not exit, or its TERM watcher never ran, before case 20e released its admission rendezvous"
            report_case_20e_admission_order
            stop_launcher "$stop_pid"
            wait "$stop_pid" 2>/dev/null
            continue
        fi
        if [ "$after_stop" = admitted ]; then : > "$STUB_DRIVE_ADMIT_AFTER_STOP_GATE_FILE"; fi
        wait "$stop_pid"
        stop_rc=$?
        if [ "$stop_rc" != 0 ] \
            && line_has_all "$STOP_LOG" 'terminal:' 'item=bd-ib-stop-admit' 'ticket=100' 'cause=stopped-after-admission' \
            && [ ! -e "$FLEET_LAUNCH_GMK_QUEUE_DIR/100-harness-seat" ] \
            && [ "$(wc -l < "$STUB_LEDGER_COMMENTS")" = 1 ] \
            && grep -qF 'ticket 100' "$STUB_LEDGER_COMMENTS" \
            && grep -qF 'move' "$STUB_LEDGER_COMMENTS" \
            && [ "$(drive_log_items)" = bd-ib-stop-admit ] && inflight_empty \
            && [ -s "$STUB_ITEM_STATUS_RE_READ_OBSERVATION_FILE" ]; then
            pass "a stopped drive that admitted its item ($after_stop) exits stopped-after-admission, re-takes no ticket and comments once"
        else
            fail "a stopped drive that admitted its item ($after_stop) did not make the stopped-after-admission exit (rc=$stop_rc)"
            report_case_20e_admission_order
            tail -n 8 "$STOP_LOG" >&2
        fi
    else
        fail "the stub drive never started for the stopped-after-admission case ($WAIT_FAILURE_DETAIL)"
        report_case_20e_admission_order
        stop_launcher "$stop_pid"
        wait "$stop_pid" 2>/dev/null
    fi
done

# 20f. A slow drive start still passes the case-20 wait: the drive is held at its start
# gate while the wait's clock is put 15 s past launcher start, beyond the fixed 10 s bound
# the waits once used, and only then released. The wait is decided by the drive starting.
prepare_330_case slow-drive-start
STOP_LOG="$CASE_DIR/launcher.log"
export STUB_DRIVE_START_GATE="$CASE_DIR/drive-start-gate"
export HARNESS_CLOCK_SKEW_FILE="$CASE_DIR/clock-skew"
: > "$STUB_DRIVE_ADMIT_GATE_FILE"
: > "$STUB_DRIVE_SUBMIT_GATE_FILE"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-slow-start > "$STOP_LOG" 2>&1 &
stop_pid=$!
slow_rc_file="$CASE_DIR/slow-start-wait.rc"
if wait_for_file "$STUB_DRIVE_START_GATE.reached" "$HARNESS_PREFLIGHT_HANG_GUARD_S"; then
    ( wait_for_drive_invocations 1 "$stop_pid" "$STOP_LOG"; printf '%s\n' "$?" > "$slow_rc_file" ) &
    slow_waiter=$!
    printf '15\n' > "$HARNESS_CLOCK_SKEW_FILE"
    : > "$STUB_DRIVE_START_GATE"
    wait "$slow_waiter"
    wait "$stop_pid"
    stop_rc=$?
    if [ "$(cat "$slow_rc_file")" = 0 ] && [ "$stop_rc" = 0 ] && log_has "$STOP_LOG" "LISTED on petri"; then
        pass "a drive that starts 15 s after the launcher still passes the case-20 wait and its run lists"
    else
        fail "a slow drive start failed the case-20 wait (wait rc=$(cat "$slow_rc_file") launcher rc=$stop_rc)"
        tail -n 8 "$STOP_LOG" >&2
    fi
else
    fail "the stub drive never reached its start gate in the slow-start case"
    stop_launcher "$stop_pid"
    wait "$stop_pid" 2>/dev/null
fi
unset STUB_DRIVE_START_GATE HARNESS_CLOCK_SKEW_FILE
fi

# --- 23. a launcher that exits without a run leaves a terminal line ---------
# Scenario 312. The cases below stop, refuse or starve a launcher before its run lists and read what
# it leaves behind: one terminal line in its sequence log, written before its ticket file is removed,
# and one ledger comment on the item when the item still reads ready. Each refusal is contrasted
# with a launch that leaves neither.
if [ "$HARNESS_SLICE" = all ] || [ "$HARNESS_SLICE" = scenario312 ]; then
echo "--- 23. a launcher that exits without a run leaves a terminal line and a ledger comment"

# make_rm_probe: a PATH directory whose `rm` records, for each queue ticket it removes, whether the
# launcher's own log already carried a terminal line and a stall line at that moment.
make_rm_probe() {
    mkdir -p "$STUB/rm-probe"
    cat > "$STUB/rm-probe/rm" <<'RM_PROBE'
#!/usr/bin/env bash
for argument in "$@"; do
    case $argument in
        "$FLEET_LAUNCH_GMK_QUEUE_DIR"/*)
            terminal=no
            stall=no
            if grep -qF 'terminal:' "$STUB_RM_PROBE_LOG_SOURCE" 2>/dev/null; then terminal=yes; fi
            if grep -qF 'stall:' "$STUB_RM_PROBE_LOG_SOURCE" 2>/dev/null; then stall=yes; fi
            printf '%s terminal=%s stall=%s\n' "${argument##*/}" "$terminal" "$stall" >> "$STUB_RM_PROBE_OUT"
            ;;
    esac
done
exec "$STUB_REAL_RM" "$@"
RM_PROBE
    chmod +x "$STUB/rm-probe/rm"
}
make_rm_probe
STUB_REAL_RM=$(command -v rm)
export STUB_REAL_RM

# prepare_312_case <name>: a fresh case with empty boards, headroom and a tenant repository hold path.
prepare_312_case() {
    new_case "$1"
    export FLEET_LAUNCH_MAX_WAIT_S=120
    : > "$BOARD_GMK"
    : > "$BOARD_HL"
    printf '8\n' > "$CAP_FILE"
    TENANT_HOLD="$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$(basename "$TENANT")"
    export STUB_RM_PROBE_OUT="$CASE_DIR/rm-probe-out"
    : > "$STUB_RM_PROBE_OUT"
    export STUB_RM_PROBE_LOG_SOURCE="$CASE_DIR/probed.log"
    : > "$STUB_RM_PROBE_LOG_SOURCE"
}
count_matching() { grep -cF -- "$2" "$1" 2>/dev/null || true; }
# queue_ticket_number: the number of the one ticket in the case's queue directory.
queue_ticket_number() {
    local file
    file=$(find "$FLEET_LAUNCH_GMK_QUEUE_DIR" -type f -print -quit)
    file=${file##*/}
    printf '%s' "${file%%-*}"
}
# check_term_exit <label> <ticket-number>: the terminal line and the ledger comment a TERMed launcher leaves.
check_term_exit() {
    local label="$1" number="$2" probe last_line
    probe=$(cat "$STUB_RM_PROBE_OUT")
    last_line=$(tail -n 1 "$STUB_RM_PROBE_LOG_SOURCE")
    if [ "$term_rc" = 143 ] \
        && [ "$(count_matching "$STUB_RM_PROBE_LOG_SOURCE" 'terminal:')" = 1 ] \
        && line_has_all "$STUB_RM_PROBE_LOG_SOURCE" 'terminal:' 'item=bd-ib-term' "ticket=$number" 'TERM' \
        && case $last_line in *'terminal:'*) true ;; *) false ;; esac \
        && [ -z "$(find "$FLEET_LAUNCH_GMK_QUEUE_DIR" -type f -print -quit)" ] \
        && case $probe in *"$number-"*" terminal=yes"*) true ;; *) false ;; esac; then
        pass "$label: a TERM leaves one last terminal line naming the item, the ticket number and TERM, written before the ticket file is removed"
    else
        fail "$label: the TERMed launcher did not leave its terminal line first (rc=$term_rc; ticket probe: ${probe:-none})"
        tail -n 4 "$STUB_RM_PROBE_LOG_SOURCE" >&2
    fi
    if [ "$(wc -l < "$STUB_LEDGER_COMMENTS")" = 1 ] \
        && grep -qF "ticket $number" "$STUB_LEDGER_COMMENTS" \
        && grep -qF 'TERM' "$STUB_LEDGER_COMMENTS" \
        && grep -qF 'not a run ending' "$STUB_LEDGER_COMMENTS" \
        && ! grep -qF 'held by its owner' "$STUB_LEDGER_COMMENTS"; then
        pass "$label: the dropped ticket is reported in one ledger comment naming the number, TERM and that the exit was not a run ending"
    else
        fail "$label: the ledger comment for the dropped ticket is missing or wrong ($(cat "$STUB_LEDGER_COMMENTS"))"
    fi
}

# bash 5.2 can fail while parsing a TERM trap action when TERM arrives while a
# command substitution is active.  The launchers must therefore rely on
# bash's default TERM exit and let their EXIT cleanup describe it; INT and HUP keep their traps.
# Keep this assertion separate from the exercise below: it makes the former
# design fail deterministically, while the exercise proves the replacement.
if grep -Eq '^[[:space:]]*trap .+ TERM$' "$LAUNCHER" "$RESUME_LAUNCHER"; then
    fail "the launchers install a TERM trap whose action bash must parse during command substitution"
else
    pass "the launchers use the default TERM exit rather than a parseable TERM trap action"

    # This PATH-local sed pauses inside repository_hold_applies' $(sed ...) read.
    # The parent waits for its gate before delivering TERM, and adds a small
    # random jitter across 200 deliveries so the proof covers distinct parser
    # instants rather than a single lucky timing.
    mkdir -p "$STUB/term-sed"
    STUB_REAL_SED=$(command -v sed)
    export STUB_REAL_SED
    cat > "$STUB/term-sed/sed" <<'TERM_SED'
#!/usr/bin/env bash
printf '%s\n' "$$" >> "$STUB_TERM_SUBSTITUTION_GATE"
sleep "$STUB_TERM_SUBSTITUTION_SED_DELAY_S"
exec "$STUB_REAL_SED" "$@"
TERM_SED
    chmod +x "$STUB/term-sed/sed"

    # term_during_hold_substitution <launcher> <label>: each iteration waits
    # until the launcher has a FIFO ticket, then sends TERM while its next hold
    # read is evaluating $(sed ...).  A default TERM exit must run EXIT cleanup.
    term_during_hold_substitution() {
        local launcher="$1" label="$2" attempt term_pid term_rc gate gate_deadline failures=0 term_cause term_parse_error
        for attempt in $(seq 1 100); do
            prepare_312_case "term-substitution-$label-$attempt"
            export FLEET_LAUNCH_POLL_S=0.01
            set_hold "$TENANT_HOLD" 'reason: substitution-term'
            gate="$CASE_DIR/substitution-gate"
            export STUB_TERM_SUBSTITUTION_GATE="$gate"
            export STUB_TERM_SUBSTITUTION_SED_DELAY_S=0.01
            PATH="$STUB/term-sed:$PATH" ONLY_GMK=1 TICKET_NS="$attempt" "$launcher" bd-ib-term > "$STUB_RM_PROBE_LOG_SOURCE" 2>&1 &
            term_pid=$!
            if ! wait_for_line "$STUB_RM_PROBE_LOG_SOURCE" 'repository hold present' 5; then
                fail "$label iteration $attempt never yielded on the repository hold"
                stop_launcher "$term_pid"
                wait "$term_pid" 2>/dev/null
                failures=$((failures + 1))
                continue
            fi
            : > "$gate"
            gate_deadline=$(( $(date +%s) + 5 ))
            while [ ! -s "$gate" ] && [ "$(date +%s)" -lt "$gate_deadline" ]; do
                sleep "$HARNESS_POLL_S"
            done
            if [ ! -s "$gate" ]; then
                fail "$label iteration $attempt never entered the gated command substitution"
                stop_launcher "$term_pid"
                wait "$term_pid" 2>/dev/null
                failures=$((failures + 1))
                continue
            fi
            sleep "0.00$((RANDOM % 5))"
            stop_launcher "$term_pid"
            wait "$term_pid"
            term_rc=$?
            term_cause=no
            term_parse_error=no
            if grep -F -- 'cause=signal TERM' "$STUB_RM_PROBE_LOG_SOURCE" >/dev/null; then
                term_cause=yes
            fi
            if grep -F -- 'unexpected EOF while looking for matching' "$STUB_RM_PROBE_LOG_SOURCE" >/dev/null; then
                term_parse_error=yes
            fi
            if [ "$term_rc" != 143 ] \
                || [ -n "$(find "$FLEET_LAUNCH_GMK_QUEUE_DIR" -type f -print -quit)" ] \
                || [ -d "$FLEET_LAUNCH_GMK_LOCK_DIR" ] \
                || [ "$term_cause" != yes ] \
                || [ "$term_parse_error" = yes ]; then
                fail "$label iteration $attempt did not exit cleanly from TERM in a command substitution (rc=$term_rc)"
                tail -n 4 "$STUB_RM_PROBE_LOG_SOURCE" >&2
                failures=$((failures + 1))
            fi
        done
        if [ "$failures" = 0 ]; then
            pass "$label exits within the stop bound for 100 jittered TERMs during repository-hold command substitutions, dropping its FIFO ticket"
        fi
    }

    term_during_hold_substitution "$LAUNCHER" impl
    term_during_hold_substitution "$RESUME_LAUNCHER" resume
    unset STUB_TERM_SUBSTITUTION_GATE STUB_TERM_SUBSTITUTION_SED_DELAY_S

    # signal_during_hold <launcher> <label> <signal> <rc> <expected cause>:
    # an INT or HUP that lands in the repository-hold wait must be recorded as
    # that signal, not as the TERM description the wait loop preloads.
    signal_during_hold() {
        local launcher="$1" label="$2" sig="$3" want_rc="$4" want_cause="$5" attempt="$6" sig_pid sig_rc
        prepare_312_case "signal-$sig-$label-$attempt"
        export FLEET_LAUNCH_POLL_S=0.01
        set_hold "$TENANT_HOLD" "reason: signal-$sig"
        # A background job of a non-interactive shell starts with INT ignored,
        # and a script cannot take that back; restore the default first.  The
        # launcher gets its own process group so the signal reaches its waiting
        # child as a terminal's INT or HUP would; bash defers a signal until a
        # foreground child that the signal did not touch has exited.
        PATH="$STUB/rm-probe:$PATH" ONLY_GMK=1 TICKET_NS=7 FLEET_LAUNCH_MAX_WAIT_S=5 python3 -c 'import os, signal, sys
signal.signal(signal.SIGINT, signal.SIG_DFL)
os.setsid()
os.execv(sys.argv[1], sys.argv[1:])' "$launcher" bd-ib-term > "$STUB_RM_PROBE_LOG_SOURCE" 2>&1 &
        sig_pid=$!
        if ! wait_for_line "$STUB_RM_PROBE_LOG_SOURCE" 'repository hold present' 5; then
            fail "$label never yielded on the repository hold before $sig"
            stop_launcher "$sig_pid"
            wait "$sig_pid" 2>/dev/null
            return 0
        fi
        kill -"$sig" -- "-$sig_pid" 2>/dev/null
        wait "$sig_pid"
        sig_rc=$?
        if [ "$sig_rc" = "$want_rc" ] \
            && [ "$(count_matching "$STUB_RM_PROBE_LOG_SOURCE" 'terminal:')" = 1 ] \
            && line_has_all "$STUB_RM_PROBE_LOG_SOURCE" 'terminal:' 'item=bd-ib-term' 'ticket=' "cause=$want_cause" \
            && ! grep -qF -- 'cause=resume gave up:' "$STUB_RM_PROBE_LOG_SOURCE" \
            && { [ "$sig" = TERM ] || ! grep -qF -- 'cause=signal TERM' "$STUB_RM_PROBE_LOG_SOURCE"; }; then
            pass "$label records a $sig during the repository-hold wait as $want_cause, not as TERM"
        else
            fail "$label did not record $sig as $want_cause (rc=$sig_rc)"
            tail -n 4 "$STUB_RM_PROBE_LOG_SOURCE" >&2
        fi
    }
    # The normal gate samples each signal once.  A focused stability run sets
    # HARNESS_SIGNAL_HOLD_ATTEMPTS=200 to repeat every launcher/signal case
    # without multiplying the unrelated Scenario 312 exercises.
    for signal_attempt in $(seq 1 "${HARNESS_SIGNAL_HOLD_ATTEMPTS:-1}"); do
        signal_during_hold "$LAUNCHER" impl INT 130 'signal INT' "$signal_attempt"
        signal_during_hold "$LAUNCHER" impl TERM 143 'signal TERM' "$signal_attempt"
        signal_during_hold "$LAUNCHER" impl HUP 129 'signal HUP' "$signal_attempt"
        signal_during_hold "$RESUME_LAUNCHER" resume INT 130 'signal INT' "$signal_attempt"
        signal_during_hold "$RESUME_LAUNCHER" resume TERM 143 'signal TERM' "$signal_attempt"
        signal_during_hold "$RESUME_LAUNCHER" resume HUP 129 'signal HUP' "$signal_attempt"
    done

    # A separate gate pauses dispatch after it has recorded its mutex holder.
    # TERM must remove both that owned mutex and its ticket before the process
    # exits, rather than leaving the next launcher blocked behind either.
    prepare_312_case terminal-term-owned-mutex
    STUB_TERM_MUTEX_GATE="$CASE_DIR/mutex-gate"
    export STUB_TERM_MUTEX_GATE
    ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-term > "$STUB_RM_PROBE_LOG_SOURCE" 2>&1 &
    term_pid=$!
    gate_deadline=$(( $(date +%s) + 5 ))
    while [ ! -e "$STUB_TERM_MUTEX_GATE" ] && [ "$(date +%s)" -lt "$gate_deadline" ]; do
        sleep "$HARNESS_POLL_S"
    done
    if [ -e "$STUB_TERM_MUTEX_GATE" ] && [ -d "$FLEET_LAUNCH_GMK_LOCK_DIR" ]; then
        stop_launcher "$term_pid"
        wait "$term_pid"
        term_rc=$?
        if [ "$term_rc" = 143 ] \
            && [ -z "$(find "$FLEET_LAUNCH_GMK_QUEUE_DIR" -type f -print -quit)" ] \
            && [ ! -d "$FLEET_LAUNCH_GMK_LOCK_DIR" ]; then
            pass "a TERMed launcher that owns the gmktec mutex drops its ticket and releases the mutex"
        else
            fail "a TERMed mutex owner left a ticket or gmktec mutex behind (rc=$term_rc)"
        fi
    else
        fail "the dispatch launcher never reached the owned-mutex TERM gate"
        tail -n 8 "$STUB_RM_PROBE_LOG_SOURCE" >&2
        stop_launcher "$term_pid"
        wait "$term_pid" 2>/dev/null
    fi
    unset STUB_TERM_MUTEX_GATE
fi

prepare_312_case terminal-term-impl
export FLEET_LAUNCH_POLL_S=0.2
set_hold "$TENANT_HOLD" 'reason: harness'
PATH="$STUB/rm-probe:$PATH" ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-term > "$STUB_RM_PROBE_LOG_SOURCE" 2>&1 &
term_pid=$!
if wait_for_line "$STUB_RM_PROBE_LOG_SOURCE" 'repository hold present' 10; then
    stop_launcher "$term_pid"
    wait "$term_pid"
    term_rc=$?
    check_term_exit 'impl launcher yielding on a repository hold' 100
else
    fail "the impl launcher never yielded on the repository hold"
    stop_launcher "$term_pid"
    wait "$term_pid" 2>/dev/null
fi

prepare_312_case terminal-term-resume
export FLEET_LAUNCH_POLL_S=0.2
set_hold "$TENANT_HOLD" 'reason: harness'
PATH="$STUB/rm-probe:$PATH" "$RESUME_LAUNCHER" bd-ib-term > "$STUB_RM_PROBE_LOG_SOURCE" 2>&1 &
term_pid=$!
if wait_for_line "$STUB_RM_PROBE_LOG_SOURCE" 'repository hold present' 10; then
    resume_number=$(queue_ticket_number)
    stop_launcher "$term_pid"
    wait "$term_pid"
    term_rc=$?
    check_term_exit 'resume launcher yielding on a repository hold' "$resume_number"
else
    fail "the resume launcher never yielded on the repository hold"
    stop_launcher "$term_pid"
    wait "$term_pid" 2>/dev/null
fi

# A TERM that lands while the launcher retries a refused ready-set check, before the launcher has
# reached the later parts of its script, must still leave the terminal line and the ledger comment:
# the exit path may not depend on a helper defined below the point the signal interrupts.
prepare_312_case terminal-term-ready-retry
export FLEET_LAUNCH_POLL_S=0.2
export FLEET_LAUNCH_READY_RETRY_POLLS=99
export STUB_READY_REFUSALS=99
export STUB_READY_REASON='open blockers: bd-ib-dep=active'
PATH="$STUB/rm-probe:$PATH" ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-term > "$STUB_RM_PROBE_LOG_SOURCE" 2>&1 &
term_pid=$!
if wait_for_line "$STUB_RM_PROBE_LOG_SOURCE" 'ready-set check refused' 10; then
    stop_launcher "$term_pid"
    wait "$term_pid"
    term_rc=$?
    check_term_exit 'impl launcher retrying a refused ready-set check' 100
    if grep -qF 'command not found' "$STUB_RM_PROBE_LOG_SOURCE"; then
        fail "the TERMed ready-set retry called a helper that was not yet defined ($(grep -m 1 -F 'command not found' "$STUB_RM_PROBE_LOG_SOURCE"))"
    else
        pass "a TERM during the ready-set retry calls no helper that is not yet defined"
    fi
else
    fail "the impl launcher never logged a refused ready-set check"
    stop_launcher "$term_pid"
    wait "$term_pid" 2>/dev/null
fi
unset FLEET_LAUNCH_READY_RETRY_POLLS STUB_READY_REFUSALS STUB_READY_REASON

prepare_312_case terminal-control-launch
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-term > "$CASE_LOG" 2>&1
control_rc=$?
if [ "$control_rc" = 0 ] && [ "$(drive_log_items)" = bd-ib-term ] \
    && [ "$(count_matching "$CASE_LOG" 'terminal:')" = 0 ] && [ ! -s "$STUB_LEDGER_COMMENTS" ]; then
    pass "control: a launcher whose run lists leaves no terminal line and no ledger comment"
else
    fail "control: a launching launcher wrote a terminal line or a comment (rc=$control_rc)"
    tail -n 4 "$CASE_LOG" >&2
fi

prepare_312_case ready-refusal-clears
export FLEET_LAUNCH_READY_RETRY_POLLS=3
export STUB_READY_REFUSALS=2
export STUB_READY_REASON='open blockers: bd-ib-dep=active'
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-ready > "$CASE_LOG" 2>&1
ready_rc=$?
first_poll=$(sed -n 1p "$STUB_READY_OBSERVATIONS")
second_poll=$(sed -n 2p "$STUB_READY_OBSERVATIONS")
if [ "$ready_rc" = 0 ] && [ "$(drive_log_items)" = bd-ib-ready ] \
    && [ "$first_poll" = 'call=1 ticket=present mutex=none marker=none' ] \
    && [ "$second_poll" = 'call=2 ticket=present mutex=none marker=none' ] \
    && [ "$(count_matching "$CASE_LOG" 'terminal:')" = 0 ] && [ ! -s "$STUB_LEDGER_COMMENTS" ]; then
    pass "a ready-set refusal that clears within the retry bound keeps the ticket, holds no mutex or marker, and launches"
else
    fail "a ready-set refusal that clears within the retry bound did not keep the ticket and launch (rc=$ready_rc; polls: $first_poll / $second_poll)"
    tail -n 6 "$CASE_LOG" >&2
fi

prepare_312_case ready-refusal-exhausts
export FLEET_LAUNCH_READY_RETRY_POLLS=3
export STUB_READY_REFUSALS=99
export STUB_READY_REASON='open blockers: bd-ib-dep=active'
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-ready > "$CASE_LOG" 2>&1
ready_rc=$?
if [ "$ready_rc" = 3 ] && [ "$(cat "$STUB_READY_COUNTER")" = 3 ] && [ ! -s "$DRIVE_LOG" ] \
    && line_has_all "$CASE_LOG" 'terminal:' 'item=bd-ib-ready' 'ticket=100' 'open blockers: bd-ib-dep=active' '3 polls tried' \
    && [ -z "$(find "$FLEET_LAUNCH_GMK_QUEUE_DIR" -type f -print -quit)" ]; then
    pass "a ready-set refusal that outlasts the retry bound ends after exactly the bound with a terminal line naming the reason and the polls tried"
else
    fail "a persistent ready-set refusal did not end with the bounded terminal line (rc=$ready_rc, polls=$(cat "$STUB_READY_COUNTER"))"
    tail -n 6 "$CASE_LOG" >&2
fi
if [ "$(wc -l < "$STUB_LEDGER_COMMENTS")" = 1 ] \
    && grep -qF 'ticket 100' "$STUB_LEDGER_COMMENTS" \
    && grep -qF 'open blockers: bd-ib-dep=active' "$STUB_LEDGER_COMMENTS" \
    && grep -qF '3 polls tried' "$STUB_LEDGER_COMMENTS"; then
    pass "the persistent ready-set refusal is recorded in one ledger comment naming the ticket, the reason and the polls tried"
else
    fail "the persistent ready-set refusal left no correct ledger comment ($(cat "$STUB_LEDGER_COMMENTS"))"
fi

prepare_312_case give-up
export FLEET_LAUNCH_MAX_WAIT_S=1
printf '0\n' > "$CAP_FILE"
ONLY_GMK=1 TICKET_NS=100 "$LAUNCHER" bd-ib-giveup > "$CASE_LOG" 2>&1
giveup_rc=$?
if [ "$giveup_rc" = 75 ] \
    && line_has_all "$CASE_LOG" 'terminal:' 'item=bd-ib-giveup' 'ticket=100' 'no slot within 1s' \
    && [ "$(wc -l < "$STUB_LEDGER_COMMENTS")" = 1 ] \
    && grep -qF 'ticket 100' "$STUB_LEDGER_COMMENTS" \
    && grep -qF 'no slot within 1s' "$STUB_LEDGER_COMMENTS"; then
    pass "a launcher that gives up for want of a slot leaves a terminal line and reports its dropped ticket while the item reads ready"
else
    fail "the give-up exit left no terminal line or ledger comment (rc=$giveup_rc)"
    tail -n 4 "$CASE_LOG" >&2
fi

# check_stall <label> <log>: the stall line a queue reader writes for a ticket whose launcher is dead.
check_stall() {
    local label="$1" log="$2" probe
    probe=$(cat "$STUB_RM_PROBE_OUT")
    if [ "$(count_matching "$log" 'stall:')" = 1 ] \
        && line_has_all "$log" 'stall:' 'item=bd-ib-dead' 'ticket=100' "dead-pid=$dead_pid" \
        && case $probe in *"100-other-seat terminal=no stall=yes"*) true ;; *) false ;; esac \
        && [ ! -e "$FLEET_LAUNCH_GMK_QUEUE_DIR/100-other-seat" ]; then
        pass "$label: a dead-pid ticket is reported as one stall line naming item, ticket number and pid before it is removed"
    else
        fail "$label: the dead-pid ticket was not reported as a stall (probe: ${probe:-none})"
        tail -n 6 "$log" >&2
    fi
    if line_has_all "$log" 'stall:' 'bd-ib-live'; then
        fail "$label: a ticket with a live launcher was reported as a stall"
    else
        pass "$label: control: a ticket whose launcher is alive is not reported"
    fi
}
# seed_queue: a dead-pid ticket 100 for bd-ib-dead and a live-pid ticket 150 for bd-ib-live.
seed_queue() {
    mkdir -p "$FLEET_LAUNCH_GMK_QUEUE_DIR"
    sleep 0 &
    dead_pid=$!
    wait "$dead_pid"
    sleep 600 &
    live_pid=$!
    printf 'owner=other-seat pid=%s item=bd-ib-dead\n' "$dead_pid" > "$FLEET_LAUNCH_GMK_QUEUE_DIR/100-other-seat"
    printf 'owner=live-seat pid=%s item=bd-ib-live\n' "$live_pid" > "$FLEET_LAUNCH_GMK_QUEUE_DIR/150-live-seat"
}

prepare_312_case stall-impl
printf '0\n' > "$CAP_FILE"
seed_queue
PATH="$STUB/rm-probe:$PATH" ONLY_GMK=1 TICKET_NS=200 "$LAUNCHER" bd-ib-reader > "$STUB_RM_PROBE_LOG_SOURCE" 2>&1 &
reader_pid=$!
if wait_for_line "$STUB_RM_PROBE_LOG_SOURCE" 'stall:' 10 && wait_for_line "$STUB_RM_PROBE_LOG_SOURCE" 'queued behind' 10; then
    check_stall 'impl launcher reading the queue' "$STUB_RM_PROBE_LOG_SOURCE"
else
    fail "the impl launcher never reported the dead-pid ticket"
fi
stop_launcher "$reader_pid"
wait "$reader_pid" 2>/dev/null
kill "$live_pid" 2>/dev/null
wait "$live_pid" 2>/dev/null

prepare_312_case stall-resume
printf '0\n' > "$CAP_FILE"
seed_queue
PATH="$STUB/rm-probe:$PATH" "$RESUME_LAUNCHER" bd-ib-reader > "$STUB_RM_PROBE_LOG_SOURCE" 2>&1 &
reader_pid=$!
if wait_for_line "$STUB_RM_PROBE_LOG_SOURCE" 'stall:' 10 && wait_for_line "$STUB_RM_PROBE_LOG_SOURCE" 'queued behind' 10; then
    check_stall 'resume launcher reading the queue' "$STUB_RM_PROBE_LOG_SOURCE"
else
    fail "the resume launcher never reported the dead-pid ticket"
fi
stop_launcher "$reader_pid"
wait "$reader_pid" 2>/dev/null
kill "$live_pid" 2>/dev/null
wait "$live_pid" 2>/dev/null
fi

# --- 21. a running launcher follows its script on disk ------------------------
# A bash launcher keeps executing the script content it started with, so a hold
# check added to the script after the launcher started never reached it
# (bd-ib-5ycmsm: bd-ib-fkd4ve launched straight through a repository hold on
# 2026-11-08). Each case starts a launcher from a private copy of the committed
# scripts whose hold check is DISABLED, replaces that copy on disk with the
# committed script exactly as a deploy does (write beside, then mv), and holds a
# repository hold file. Every refusal is contrasted with a launch once the hold
# is removed.
if [ "$HARNESS_SLICE" = all ] || [ "$HARNESS_SLICE" = launcher-reexec ]; then
copy_launchers() { mkdir -p "$1" && cp "$LAUNCH_DIR"/*.sh "$1/"; }
replace_script() { cp "$2" "$1.new" && chmod +x "$1.new" && mv -f "$1.new" "$1"; }
without_hold_handling() {
    sed 's/^repository_hold_applies() {$/repository_hold_applies() { return 1/' "$1"
}
as_legacy_launcher() {
    sed -e 's/^script_changed() {$/script_changed() { return 1/' \
        -e 's/^reexec_on_script_change() {$/reexec_on_script_change() { return 0/' "$1"
}
ticket_pid() { grep -oE 'pid=[0-9]+' "$1" 2>/dev/null | sed -n 1p; }

echo "--- 21. an impl launcher started before a hold check was added honours the hold"
new_case launcher-reexec-dispatch
export FLEET_LAUNCH_MAX_WAIT_S=120
launchers="$CASE_DIR/launchers"
copy_launchers "$launchers"
cp "$launchers/dispatch-dual.sh" "$CASE_DIR/committed-dispatch-dual.sh"
without_hold_handling "$CASE_DIR/committed-dispatch-dual.sh" > "$launchers/dispatch-dual.sh"
chmod +x "$launchers/dispatch-dual.sh"
if cmp -s "$CASE_DIR/committed-dispatch-dual.sh" "$launchers/dispatch-dual.sh"; then
    fail "the harness could not disable the copy's hold check"
fi
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '0\n' > "$CAP_FILE"
ONLY_GMK=1 TICKET_NS=100 "$launchers/dispatch-dual.sh" bd-ib-reexec > "$CASE_DIR/impl.log" 2>&1 &
reexec_pid=$!
ticket_path="$FLEET_LAUNCH_GMK_QUEUE_DIR/100-harness-seat"
wait_for_line "$CASE_DIR/impl.log" "fleet not green" 10 || fail "the impl launcher never reached its waiting loop"
ticket_before=$(ticket_pid "$ticket_path")
printf 'reason: canary gate\n' > "$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$(basename "$TENANT")"
replace_script "$launchers/dispatch-dual.sh" "$CASE_DIR/committed-dispatch-dual.sh"
wait_for_line "$CASE_DIR/impl.log" "launcher script changed on disk" 10 \
    || fail "the waiting launcher never noticed its script changed on disk"
printf '8\n' > "$CAP_FILE"
wait_for_line "$CASE_DIR/impl.log" "repository hold present" 10 \
    || fail "the waiting launcher never read the repository hold"
sleep 0.3
if kill -0 "$reexec_pid" 2>/dev/null && [ ! -s "$DRIVE_LOG" ] \
    && [ -n "$ticket_before" ] && [ "$(ticket_pid "$ticket_path")" = "$ticket_before" ]; then
    pass "a hold file created while the launcher waits stops it, keeping its original queue ticket"
else
    fail "the launcher started before the hold check launched through the hold (dispatches: $(drive_log_items))"
    tail -6 "$CASE_DIR/impl.log" >&2
fi
rm -f "$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$(basename "$TENANT")"
wait_for_line "$CASE_DIR/impl.log" "drive rc=" 20
if [ "$(drive_log_items)" = bd-ib-reexec ]; then
    pass "control: removing the hold launches the same launcher"
else
    fail "control: the launcher did not launch once the hold was removed (dispatches: $(drive_log_items))"
    tail -6 "$CASE_DIR/impl.log" >&2
fi
stop_launcher "$reexec_pid"
wait "$reexec_pid" 2>/dev/null

echo "--- 21a. an impl launcher bound at the mutex re-reads changed hold code before launching"
new_case launcher-reexec-launch-point
export FLEET_LAUNCH_MAX_WAIT_S=120
launchers="$CASE_DIR/launchers"
copy_launchers "$launchers"
cp "$launchers/dispatch-dual.sh" "$CASE_DIR/committed-dispatch-dual.sh"
without_hold_handling "$CASE_DIR/committed-dispatch-dual.sh" > "$launchers/dispatch-dual.sh"
chmod +x "$launchers/dispatch-dual.sh"
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '8\n' > "$CAP_FILE"
mkdir "$FLEET_LAUNCH_GMK_LOCK_DIR"
sleep 600 &
holder_pid=$!
printf 'owner=other-seat pid=%s item=bd-ib-holder\n' "$holder_pid" > "$FLEET_LAUNCH_GMK_LOCK_DIR/holder"
ONLY_GMK=1 TICKET_NS=100 "$launchers/dispatch-dual.sh" bd-ib-reexec-bound > "$CASE_DIR/impl.log" 2>&1 &
reexec_pid=$!
wait_for_line "$CASE_DIR/impl.log" "queue for the gmktec mutex" 10 || fail "the launcher did not wait for the mutex"
printf 'reason: canary gate\n' > "$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$(basename "$TENANT")"
replace_script "$launchers/dispatch-dual.sh" "$CASE_DIR/committed-dispatch-dual.sh"
kill "$holder_pid" 2>/dev/null
wait "$holder_pid" 2>/dev/null
rm -f "$FLEET_LAUNCH_GMK_LOCK_DIR/holder"
rmdir "$FLEET_LAUNCH_GMK_LOCK_DIR"
wait_for_line "$CASE_DIR/impl.log" "repository hold present" 10 \
    || fail "the bound launcher never read the repository hold"
sleep 0.3
if kill -0 "$reexec_pid" 2>/dev/null && [ ! -s "$DRIVE_LOG" ] \
    && [ -e "$FLEET_LAUNCH_GMK_QUEUE_DIR/100-harness-seat" ] \
    && [ -z "$(find "$FLEET_LAUNCH_INFLIGHT_DIR" -type f -print -quit)" ]; then
    pass "a launcher bound at the mutex when its script changed holds under the changed code and keeps its ticket"
else
    fail "the bound launcher launched under its old hold code (dispatches: $(drive_log_items))"
    tail -6 "$CASE_DIR/impl.log" >&2
fi
stop_launcher "$reexec_pid"
wait "$reexec_pid" 2>/dev/null

echo "--- 21b. a resume launcher started before a hold check was added honours the hold"
new_case launcher-reexec-resume
export FLEET_LAUNCH_MAX_WAIT_S=120
launchers="$CASE_DIR/launchers"
copy_launchers "$launchers"
cp "$launchers/resume-capped.sh" "$CASE_DIR/committed-resume-capped.sh"
without_hold_handling "$CASE_DIR/committed-resume-capped.sh" > "$launchers/resume-capped.sh"
chmod +x "$launchers/resume-capped.sh"
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '0\n' > "$CAP_FILE"
"$launchers/resume-capped.sh" bd-ib-reexec-resume > "$CASE_DIR/resume.log" 2>&1 &
reexec_pid=$!
wait_for_line "$CASE_DIR/resume.log" "fleet at cap under mutex" 10 || fail "the resume launcher never reached its waiting loop"
ticket_path=$(find "$FLEET_LAUNCH_GMK_QUEUE_DIR" -type f -print -quit)
ticket_before=$(ticket_pid "$ticket_path")
printf 'reason: canary gate\n' > "$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$(basename "$TENANT")"
replace_script "$launchers/resume-capped.sh" "$CASE_DIR/committed-resume-capped.sh"
wait_for_line "$CASE_DIR/resume.log" "launcher script changed on disk" 10 \
    || fail "the waiting resume launcher never noticed its script changed on disk"
printf '8\n' > "$CAP_FILE"
wait_for_line "$CASE_DIR/resume.log" "repository hold present" 10 \
    || fail "the waiting resume launcher never read the repository hold"
sleep 0.3
if kill -0 "$reexec_pid" 2>/dev/null && [ ! -s "$RESUME_LOG" ] \
    && [ -n "$ticket_before" ] && [ -e "$ticket_path" ] && [ "$(ticket_pid "$ticket_path")" = "$ticket_before" ]; then
    pass "a hold file created while the resume launcher waits stops it, keeping its original queue ticket"
else
    fail "the resume launcher started before the hold check launched through the hold"
    tail -6 "$CASE_DIR/resume.log" >&2
fi
rm -f "$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$(basename "$TENANT")"
wait "$reexec_pid" 2>/dev/null
if [ "$(tr '\n' ' ' < "$RESUME_LOG" | sed 's/ *$//')" = bd-ib-reexec-resume ]; then
    pass "control: removing the hold resumes the same launcher"
else
    fail "control: the resume launcher did not resume once the hold was removed"
    tail -6 "$CASE_DIR/resume.log" >&2
fi
stop_launcher "$reexec_pid"

echo "--- 22. launcher-versions.sh marks the launcher running a stale script"
new_case launcher-versions
export FLEET_LAUNCH_MAX_WAIT_S=120
stale_dir="$CASE_DIR/stale-launchers"
fresh_dir="$CASE_DIR/fresh-launchers"
copy_launchers "$stale_dir"
copy_launchers "$fresh_dir"
as_legacy_launcher "$LAUNCHER" > "$stale_dir/dispatch-dual.sh"
chmod +x "$stale_dir/dispatch-dual.sh"
stale_started=$(sha256sum < "$stale_dir/dispatch-dual.sh" | cut -c1-12)
fresh_started=$(sha256sum < "$fresh_dir/dispatch-dual.sh" | cut -c1-12)
: > "$BOARD_GMK"
: > "$BOARD_HL"
printf '0\n' > "$CAP_FILE"
ONLY_GMK=1 TICKET_NS=100 "$stale_dir/dispatch-dual.sh" bd-ib-stale > "$CASE_DIR/stale.log" 2>&1 &
stale_pid=$!
ONLY_GMK=1 TICKET_NS=200 "$fresh_dir/dispatch-dual.sh" bd-ib-fresh > "$CASE_DIR/fresh.log" 2>&1 &
fresh_pid=$!
wait_for_line "$CASE_DIR/stale.log" "fleet not green" 10 || fail "the stale-case launcher never reached its waiting loop"
wait_for_line "$CASE_DIR/fresh.log" "queued behind an older gmktec ticket" 10 || fail "the fresh-case launcher never reached its waiting loop"
{ cat "$stale_dir/dispatch-dual.sh"; printf '# changed on disk\n'; } > "$CASE_DIR/stale-replacement.sh"
replace_script "$stale_dir/dispatch-dual.sh" "$CASE_DIR/stale-replacement.sh"
stale_on_disk=$(sha256sum < "$stale_dir/dispatch-dual.sh" | cut -c1-12)
queue_before=$(find "$FLEET_LAUNCH_GMK_QUEUE_DIR" -type f -name "[0-9]*" | sort | tr '\n' ' ')
report=$(bash "$LAUNCH_DIR/launcher-versions.sh" 2>&1)
stale_row=$(printf '%s\n' "$report" | awk -v p="$stale_pid" '$1==p')
fresh_row=$(printf '%s\n' "$report" | awk -v p="$fresh_pid" '$1==p')
stale_ok=$(printf '%s\n' "$stale_row" | awk -v r="$stale_started" -v d="$stale_on_disk" '$2=="STALE" && $3==r && $4==d {ok=1} END{if (ok) print "yes"}')
fresh_ok=$(printf '%s\n' "$fresh_row" | awk -v r="$fresh_started" '$2=="current" && $3==r && $4==r {ok=1} END{if (ok) print "yes"}')
if [ "$stale_ok" = yes ] && [ "$fresh_ok" = yes ]; then
    pass "the readback lists each launcher's running script version and marks only the one that differs from disk"
else
    fail "the readback did not mark the stale launcher (stale row: ${stale_row:-none}; fresh row: ${fresh_row:-none})"
    printf '%s\n' "$report" >&2
fi
if [ "$(find "$FLEET_LAUNCH_GMK_QUEUE_DIR" -type f -name "[0-9]*" | sort | tr '\n' ' ')" = "$queue_before" ] \
    && kill -0 "$stale_pid" 2>/dev/null && kill -0 "$fresh_pid" 2>/dev/null; then
    pass "the readback changes no queue ticket and stops no launcher"
else
    fail "the readback disturbed a launcher or its ticket"
fi
stop_launcher "$stale_pid" "$fresh_pid"
wait "$stale_pid" 2>/dev/null
wait "$fresh_pid" 2>/dev/null
fi

echo
echo "=== fleet-launch hermetic harness: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
