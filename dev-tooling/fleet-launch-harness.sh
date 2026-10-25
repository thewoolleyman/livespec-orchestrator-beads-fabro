#!/usr/bin/env bash
# The hermetic harness `check-fleet-launch` runs over the provisional launcher.
#
# `SPECIFICATION/contracts.md` §"Provisional fleet launch scripts" requires
# `just check` to run a `check-fleet-launch` target that shellchecks every shell
# script under `fleet-launch/` AND runs a hermetic harness, and it says outright
# that "a syntax check alone MUST NOT be treated as satisfying this obligation".
# This file is that harness; `just-check-fleet-launch.sh` is the target that
# composes it with the shellcheck leg.
#
# WHY IT DRIVES THE REAL LAUNCHER END TO END rather than sourcing its functions.
# `fleet-launch/dispatch-dual.sh` is a gate SEQUENCE: its refusals come from the
# ORDER its gates run in (the ready set, then the shared fleet cap, then the
# hold file, then the factory ceiling and idle CPU, then the FIFO ticket and
# mutex, then the binding re-count), and every one of them reads a value through
# `config.sh`. A harness that called `board_rows` in isolation would assert the
# parse and prove nothing about the sequence, which is where the expensive
# defects live — a gate reordered, a refusal that stops refusing, a `U` reading
# treated as green. So each case below launches the actual script, as a
# subprocess, and reads its own diagnostics back.
#
# WHAT MAKES IT HERMETIC. Two mechanisms, and both are load-bearing:
#
#   - EVERY `FLEET_LAUNCH_` value is set explicitly, never defaulted. The clause
#     requires each host value to be overridable from an environment variable of
#     that prefix, and `stub_world` exercises exactly that: boards become stub
#     files, the fabro client a stub script, the state, queue, lock and in-flight
#     directories throwaway ones under `mktemp -d`. Setting them ALL rather than
#     only the ones a case cares about is deliberate — an unset value silently
#     falls back to a real operator path, and the first thing a leaked default
#     reaches is the live factory board.
#   - Every host COMMAND the launcher shells out to is shadowed on `PATH`:
#     `fabro`, `ssh`, `git` and `pgrep`, plus a stub credential wrapper standing
#     in for `with-livespec-env.sh`. The launcher therefore reaches no network,
#     no real repository and no real process table.
#
# WHY EACH REFUSAL CASE CARRIES A POSITIVE CONTROL. A launcher that refused
# EVERYTHING would pass every refusal assertion here, which is the failure mode
# `AGENTS.md` §"Verification discipline" calls an instrument that cannot return
# the other answer. So the fleet-cap case re-runs the identical world with the
# cap raised by one and requires a launch, and the hold-file case re-runs it with
# the hold file removed and requires a launch. The refusal is then attributable
# to the gate under test rather than to anything else in the sequence.
#
# Usage: fleet-launch-harness.sh
# Environment:
#   FLEET_LAUNCH_HARNESS_DIR=<dir>         the launcher directory under test
#                                          (default: this repository's
#                                          fleet-launch/), so a caller can
#                                          harness a mutated copy.
#   FLEET_LAUNCH_HARNESS_LAUNCH_DEADLINE_S how long a leg that MUST launch waits
#                                          for that launch (default 40).
#
# WHY THAT DEADLINE IS A KNOB, AND WHY IT IS A SAFE ONE. It bounds only the legs
# that must SUCCEED, and a launch against stubs takes a second or two — the
# figure exists for a loaded host, not for the happy path. A broken launcher
# never launches, so every one of those legs waits the whole deadline out, and
# the negative case that mutates a launcher on purpose would otherwise spend
# minutes waiting for launches it has itself made impossible. Lowering the knob
# can only make a launch leg fail sooner; it can never turn a failing case into a
# passing one, so the one direction it moves the harness in is stricter. The
# refusal legs are NOT tunable: a refusal is observed by the launcher giving up,
# so their deadline is the thing under test.
set -uo pipefail

HARNESS_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$HARNESS_DIR/.." && pwd)
TARGET_DIR=${FLEET_LAUNCH_HARNESS_DIR:-$REPO_ROOT/fleet-launch}
LAUNCHER=$TARGET_DIR/dispatch-dual.sh
LAUNCH_DEADLINE_S=${FLEET_LAUNCH_HARNESS_LAUNCH_DEADLINE_S:-40}
# A refusal leg's deadline IS the refusal: the launcher refuses by polling its
# gates until it gives up, so this is short and fixed.
REFUSAL_DEADLINE_S=6
# The FIFO case needs room for two launchers plus the preflight pause that holds
# the first inside the gate sequence, and for one pass through `take_mutex`'s own
# fixed ten-second poll should the second arrive while the first holds the lock.
FIFO_DEADLINE_S=$((LAUNCH_DEADLINE_S + 30))

WORK=$(mktemp -d "${TMPDIR:-/tmp}/fleet-launch-harness.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

cases_total=0
cases_failed=0
# Reasons the case currently being graded failed; empty means it passed.
reasons=()
WORLD_ENV=()

note() { printf '  %s\n' "$*"; }

# begin_case / end_case <name>: one graded case, reported as the ONE line
# `check-fleet-launch` and the integration test both read.
begin_case() {
    reasons=()
    printf '::: case %s\n' "$1"
}
end_case() {
    cases_total=$((cases_total + 1))
    if [ ${#reasons[@]} -eq 0 ]; then
        printf 'CASE %s: PASS\n' "$1"
        return 0
    fi
    cases_failed=$((cases_failed + 1))
    # Joined by hand rather than through `IFS`, which takes only its FIRST
    # character as the separator and so would run the reasons together.
    printf 'CASE %s: FAIL — %s' "$1" "${reasons[0]}"
    printf '; %s' "${reasons[@]:1}"
    printf '\n'
    return 1
}

expect_in() {
    local log=$1 needle=$2
    grep -qF -- "$needle" "$log" || reasons+=("expected $(basename "$log") to carry '$needle'")
}
expect_not_in() {
    local log=$1 needle=$2
    if grep -qF -- "$needle" "$log"; then
        reasons+=("expected $(basename "$log") NOT to carry '$needle'")
    fi
}
expect_rc() {
    local label=$1 actual=$2 wanted=$3
    [ "$actual" = "$wanted" ] || reasons+=("$label exited $actual, wanted $wanted")
}

# stub_world <root>: the throwaway directories, the PATH stubs and the full
# `FLEET_LAUNCH_` environment (left in WORLD_ENV) for one case.
stub_world() {
    local root=$1
    # The lock directory is deliberately NOT created: `take_mutex` creates it
    # with `mkdir`, which is how it is a mutex at all.
    mkdir -p "$root/state" "$root/inflight" "$root/queue" "$root/repo" "$root/bin" \
        "$root/boards" "$root/plugins/cache/0.0.0-stub"

    cat > "$root/bin/fabro" <<'FABRO_STUB'
#!/usr/bin/env bash
# Stub fabro client: answers `ps -a --server <url>` from a board file.
#
# An EMPTY board file reproduces a real empty board exactly — exit 0, nothing on
# stdout, "No runs found." on stderr — because that distinction is what the
# retired-factory case turns on. A `<tag>.unreadable` marker reproduces the
# other reading: a board that cannot be read at all.
set -u
server=""
while [ $# -gt 0 ]; do
    if [ "$1" = --server ]; then
        server=${2:-}
        shift 2
        continue
    fi
    shift
done
file="$FLEET_LAUNCH_HARNESS_BOARDS/${server#stub://}"
if [ -e "$file.unreadable" ]; then
    echo "stub fabro: that board cannot be read" >&2
    exit 1
fi
if [ -s "$file" ]; then
    cat "$file"
else
    echo "No runs found." >&2
fi
exit 0
FABRO_STUB

    cat > "$root/bin/ssh" <<'SSH_STUB'
#!/usr/bin/env bash
# Stub ssh: the launcher asks the factory host for exactly two things — its idle
# CPU through mpstat, and the server env file holding the dev token.
set -u
for arg in "$@"; do
    case "$arg" in
    *mpstat*)
        printf 'Average:     all   1.00   0.00   1.00   0.00   0.00   0.00   0.00   0.00   0.00   %s\n' \
            "${FLEET_LAUNCH_HARNESS_IDLE:-90.0}"
        exit 0
        ;;
    cat)
        printf 'FABRO_DEV_TOKEN=stub-dev-token\n'
        exit 0
        ;;
    esac
done
exit 0
SSH_STUB

    cat > "$root/bin/git" <<'GIT_STUB'
#!/usr/bin/env bash
# Stub git: the launcher fetches and fast-forwards the tenant repository and
# reads its short HEAD for the launch line. Nothing here touches a real clone.
set -u
for arg in "$@"; do
    if [ "$arg" = rev-parse ]; then
        printf 'deadbee\n'
        exit 0
    fi
done
exit 0
GIT_STUB

    cat > "$root/bin/pgrep" <<'PGREP_STUB'
#!/usr/bin/env bash
# Stub pgrep: no dispatch is alive, so a dead-pid in-flight marker is stale.
# Present so the launcher never reads the real process table.
set -u
exit 1
PGREP_STUB

    cat > "$root/bin/wrap" <<'WRAP_STUB'
#!/usr/bin/env bash
# Stub credential wrapper, in the `<wrapper> -- <command...>` shape every real
# `with-<project>-env.sh` takes. It answers the four commands the launcher runs
# through a wrapper and injects no secret of any kind.
set -u
while [ $# -gt 0 ] && [ "$1" != -- ]; do shift; done
[ $# -gt 0 ] && shift
joined="$*"
case "$joined" in
*ready-set-check.py*)
    printf 'READY-CHECK: the stub ready set contains this item\n'
    exit 0
    ;;
*dod-preflight.sh*)
    # A slow preflight is how the FIFO case holds the first launcher inside the
    # gate sequence long enough for the second to observe that it is queued.
    sleep "${FLEET_LAUNCH_HARNESS_PREFLIGHT_SLEEP:-0}"
    printf 'stub Definition-of-Done preflight: PASS\n'
    exit 0
    ;;
*claude-cred-status*)
    printf 'stub probe: the credential is usable (HTTP 200)\n'
    exit 0
    ;;
*drive.py*)
    printf '{"stub": "drive", "status": "ok"}\n'
    exit 0
    ;;
esac
exit 0
WRAP_STUB

    chmod 0755 "$root/bin/fabro" "$root/bin/ssh" "$root/bin/git" "$root/bin/pgrep" \
        "$root/bin/wrap"

    # The plugin registry and cache the launcher resolves the installed build
    # from. Hand-written rather than copied from a host registry, so no real
    # build path can leak into a case.
    cat > "$root/plugins/registry.json" <<REGISTRY
{"plugins": {"harness@harness": [{"version": "0.0.0-stub", "projectPath": "$root/repo"}]}}
REGISTRY
    printf '{"version": "0.0.0-stub"}\n' > "$root/plugins/cache/0.0.0-stub/plugin.json"

    WORLD_ENV=(
        "PATH=$root/bin:$PATH"
        "FLEET_LAUNCH_HARNESS_BOARDS=$root/boards"
        "FLEET_LAUNCH_ORCH_REPO=$root/repo"
        "FLEET_LAUNCH_SEAT=harness-seat"
        "FLEET_LAUNCH_STATE_DIR=$root/state"
        "FLEET_LAUNCH_FLEET_CAP_FILE=$root/state/fleet-cap"
        "FLEET_LAUNCH_HOLD_FILE=$root/state/hold-harness"
        "FLEET_LAUNCH_GMK_SERVER=stub://gmk"
        "FLEET_LAUNCH_HL_SERVER=stub://hl"
        "FLEET_LAUNCH_GMK_SSH=stub-factory-host"
        "FLEET_LAUNCH_GMK_SERVER_ENV=$root/state/server.env"
        "FLEET_LAUNCH_GMK_CAP=8"
        "FLEET_LAUNCH_HL_CAP=2"
        "FLEET_LAUNCH_GMK_MIN_IDLE=25"
        "FLEET_LAUNCH_FABRO=$root/bin/fabro"
        "FLEET_LAUNCH_INFLIGHT_DIR=$root/inflight"
        "FLEET_LAUNCH_GMK_QUEUE_DIR=$root/queue"
        "FLEET_LAUNCH_GMK_LOCK_DIR=$root/lock"
        "FLEET_LAUNCH_PLUGIN_REGISTRY=$root/plugins/registry.json"
        "FLEET_LAUNCH_PLUGIN_CACHE=$root/plugins/cache"
        "FLEET_LAUNCH_PLUGIN_KEY=harness@harness"
        "FLEET_LAUNCH_DEFAULT_WRAPPER=$root/bin/wrap"
        "FLEET_LAUNCH_DOLT_SERVER_WRAPPER=$root/bin/wrap"
        "FLEET_LAUNCH_OPENBRAIN_WRAPPER=$root/bin/wrap"
        "FLEET_LAUNCH_RESUME_WRAPPER=$root/bin/wrap"
        "FLEET_LAUNCH_HOMELAB_AWS_WRAPPER=$root/bin/wrap"
        "FLEET_LAUNCH_HL_CLI=$root/bin/wrap"
        "FLEET_LAUNCH_MAX_WAIT_S=$REFUSAL_DEADLINE_S"
        "FLEET_LAUNCH_ABANDON_S=60"
        "FLEET_LAUNCH_POLL_S=1"
        "FLEET_LAUNCH_PREFLIGHT_REUSE_S=600"
        "FLEET_LAUNCH_MUTEX_HOLD_S=120"
    )
}

# live_board <root>: a stub board carrying two live runs, one terminal run, and
# one row whose id is not a run id. The last two are what make a reading of `2`
# evidence that the launcher's own filters ran, rather than evidence that it
# counted lines.
live_board() {
    cat > "$1/boards/gmk" <<'BOARD'
RUN ID       NAME               STATUS     STAGE DURATION ITEM
01ABCDEFGH01 ImplementWorkItem  running    impl  10m00s   bd-harness-one
01ABCDEFGH02 ImplementWorkItem  blocked    impl  20m00s   bd-harness-two
01ABCDEFGH03 ImplementWorkItem  succeeded  done  30m00s   bd-harness-three
notarunid    ImplementWorkItem  running    impl  40m00s   bd-harness-four
BOARD
    : > "$1/boards/hl"
}

# launch <root> <log> <item> [env assignment...]: run the launcher under test
# in this world, append its output to <log>, and leave its status in LAUNCH_RC.
LAUNCH_RC=0
launch() {
    local root=$1 log=$2 item=$3
    shift 3
    env "${WORLD_ENV[@]}" "$@" bash "$LAUNCHER" "$item" >> "$log" 2>&1
    LAUNCH_RC=$?
}

# ---------------------------------------------------------------------------
# board-read — the launcher's own reading of a stub factory board.
#
# Asserted through the diagnostic the launcher prints rather than by calling
# `board_rows`: the number that matters is the one the GATES consume, and the
# whole line pins four behaviours at once — the `RUN ID` header requirement, the
# terminal-status filter, the 12-character run-id filter, and an empty second
# board read as zero.
# ---------------------------------------------------------------------------
case_board_read() {
    local name=board-read
    local root=$WORK/$name log
    begin_case "$name"
    stub_world "$root"
    live_board "$root"
    echo 1 > "$root/state/fleet-cap"
    log=$root/launcher.log
    : > "$log"
    launch "$root" "$log" bd-harness-board
    expect_rc "launcher" "$LAUNCH_RC" 75
    expect_in "$log" "gmktec=2 hl=0 markers=0 fleet=2 cap=1"
    expect_not_in "$log" "LAUNCH target="
    end_case "$name"
}

# ---------------------------------------------------------------------------
# fleet-cap-refusal — at the shared fleet cap the launcher takes no slot.
#
# The cap is reached, not exceeded, because the launcher's test is `-lt`: a
# launcher that refused only ABOVE the cap would put one more run on the fleet
# than the cap allows, every time. The control raises the cap by exactly one over
# the identical world and requires a launch.
# ---------------------------------------------------------------------------
case_fleet_cap_refusal() {
    local name=fleet-cap-refusal
    local root=$WORK/$name refused control
    begin_case "$name"
    stub_world "$root"
    live_board "$root"
    refused=$root/refused.log
    control=$root/control.log
    : > "$refused"
    : > "$control"

    echo 2 > "$root/state/fleet-cap"
    launch "$root" "$refused" bd-harness-cap
    expect_rc "at-cap launcher" "$LAUNCH_RC" 75
    expect_in "$refused" "fleet not green"
    expect_in "$refused" "fleet=2 cap=2"
    expect_not_in "$refused" "LAUNCH target="

    echo 3 > "$root/state/fleet-cap"
    launch "$root" "$control" bd-harness-cap "FLEET_LAUNCH_MAX_WAIT_S=$LAUNCH_DEADLINE_S"
    expect_rc "under-cap control launcher" "$LAUNCH_RC" 0
    expect_in "$control" "LAUNCH target=petri"
    end_case "$name"
}

# ---------------------------------------------------------------------------
# fifo-two-tickets — two queued launchers launch in the order they queued.
#
# The second launcher is started AFTER the first and must observe that it is
# queued behind the first's ticket before launching itself. Both must reach a
# launch: a FIFO queue that let only the head through would satisfy an
# ordering-only assertion while starving everything behind it.
#
# The first launcher is held inside its Definition-of-Done preflight, which sits
# AFTER the queue check in the gate sequence and BEFORE the ticket is dropped at
# the binding count. That is the one window in which the second can observe the
# queue, so pausing there rather than at the dispatch is what makes the
# observation reliable instead of a race.
# ---------------------------------------------------------------------------
case_fifo_two_tickets() {
    local name=fifo-two-tickets
    local root=$WORK/$name first second first_pid second_pid
    local first_rc=0 second_rc=0
    begin_case "$name"
    stub_world "$root"
    : > "$root/boards/gmk"
    : > "$root/boards/hl"
    echo 8 > "$root/state/fleet-cap"
    first=$root/first.log
    second=$root/second.log
    : > "$first"
    : > "$second"

    env "${WORLD_ENV[@]}" ONLY_GMK=1 TICKET_NS=000001-first \
        "FLEET_LAUNCH_MAX_WAIT_S=$FIFO_DEADLINE_S" FLEET_LAUNCH_HARNESS_PREFLIGHT_SLEEP=4 \
        bash "$LAUNCHER" bd-harness-first >> "$first" 2>&1 &
    first_pid=$!
    sleep 1
    env "${WORLD_ENV[@]}" ONLY_GMK=1 TICKET_NS=000002-second \
        "FLEET_LAUNCH_MAX_WAIT_S=$FIFO_DEADLINE_S" \
        bash "$LAUNCHER" bd-harness-second >> "$second" 2>&1 &
    second_pid=$!
    wait "$first_pid" || first_rc=$?
    wait "$second_pid" || second_rc=$?

    expect_rc "first launcher" "$first_rc" 0
    expect_rc "second launcher" "$second_rc" 0
    expect_in "$first" "gmktec FIFO ticket taken at start: 000001-first-harness-seat"
    expect_in "$second" "gmktec FIFO ticket taken at start: 000002-second-harness-seat"
    expect_in "$second" "queued behind an older gmktec ticket"
    expect_in "$second" "item=bd-harness-first"
    expect_not_in "$first" "queued behind an older gmktec ticket"
    expect_in "$first" "LAUNCH target=petri"
    expect_in "$second" "LAUNCH target=petri"
    end_case "$name"
}

# ---------------------------------------------------------------------------
# hold-file — a launch waits while the hold file exists.
#
# The hold gate sits after the fleet-cap gate, so the world is deliberately well
# under the cap: a refusal observed with the cap also reached would be
# unattributable. The control removes the hold file and nothing else.
# ---------------------------------------------------------------------------
case_hold_file() {
    local name=hold-file
    local root=$WORK/$name held control
    begin_case "$name"
    stub_world "$root"
    : > "$root/boards/gmk"
    : > "$root/boards/hl"
    echo 8 > "$root/state/fleet-cap"
    held=$root/held.log
    control=$root/control.log
    : > "$held"
    : > "$control"

    : > "$root/state/hold-harness"
    launch "$root" "$held" bd-harness-hold
    expect_rc "held launcher" "$LAUNCH_RC" 75
    expect_in "$held" "hold file present ($root/state/hold-harness)"
    expect_not_in "$held" "LAUNCH target="

    rm -f "$root/state/hold-harness"
    launch "$root" "$control" bd-harness-hold "FLEET_LAUNCH_MAX_WAIT_S=$LAUNCH_DEADLINE_S"
    expect_rc "released control launcher" "$LAUNCH_RC" 0
    expect_in "$control" "LAUNCH target=petri"
    end_case "$name"
}

# ---------------------------------------------------------------------------
# retired-board-zero — a retired factory's EMPTY board counts as zero, not as
# unknown.
#
# `hp-xubuntu` and `vps` are retired, so a declared board that lists nothing is
# the normal steady state. The launcher reserves the token `U` for a board it
# could not READ, and every gate treats `U` as never-green — so conflating the
# two stops the launcher launching at all, silently, with no error anywhere.
# Scenario 242 names this as the mutation that must turn the check red.
#
# The second leg is the other reading, and it is the reason the first is not
# merely a tautology: a board the client CANNOT read must still be `U`, so this
# case cannot be satisfied by a launcher that simply calls every board zero.
# ---------------------------------------------------------------------------
case_retired_board_zero() {
    local name=retired-board-zero
    local root=$WORK/$name empty unreadable
    begin_case "$name"
    stub_world "$root"
    cat > "$root/boards/gmk" <<'BOARD'
RUN ID       NAME               STATUS   STAGE DURATION ITEM
01ABCDEFGH01 ImplementWorkItem  running  impl  10m00s   bd-harness-live
BOARD
    : > "$root/boards/hl"
    echo 2 > "$root/state/fleet-cap"
    empty=$root/empty.log
    unreadable=$root/unreadable.log
    : > "$empty"
    : > "$unreadable"

    launch "$root" "$empty" bd-harness-retired "FLEET_LAUNCH_MAX_WAIT_S=$LAUNCH_DEADLINE_S"
    expect_rc "empty-retired-board launcher" "$LAUNCH_RC" 0
    expect_in "$empty" "LAUNCH target=petri"
    expect_not_in "$empty" "hl=U"
    expect_not_in "$empty" "fleet=U"

    : > "$root/boards/hl.unreadable"
    launch "$root" "$unreadable" bd-harness-retired
    expect_rc "unreadable-board launcher" "$LAUNCH_RC" 75
    expect_in "$unreadable" "hl=U"
    expect_in "$unreadable" "fleet=U"
    expect_not_in "$unreadable" "LAUNCH target="
    end_case "$name"
}

if [ ! -f "$LAUNCHER" ]; then
    printf 'fleet-launch harness: no launcher at %s\n' "$LAUNCHER"
    exit 2
fi
printf 'fleet-launch harness: exercising %s\n' "$LAUNCHER"
case_board_read || true
case_fleet_cap_refusal || true
case_fifo_two_tickets || true
case_hold_file || true
case_retired_board_zero || true
printf 'fleet-launch harness: %d cases, %d failed\n' "$cases_total" "$cases_failed"
[ "$cases_failed" -eq 0 ] || exit 1
note "every launch gate held against stubs"
