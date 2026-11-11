#!/usr/bin/env bash
# PROVISIONAL / EXPERIMENTAL — fleet-launch's capped resume path.
#
# This stopgap's first-class replacements are the livespec console application
# and the committed launch-loop tool bd-ib-jr6w7v.  It gates only WHEN to invoke
# `resume --item`; the Dispatcher still owns resume admission and execution.
#
# Usage: resume-capped.sh <item-id>
set -u

FLEET_LAUNCH_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=fleet-launch/config.sh
. "$FLEET_LAUNCH_DIR/config.sh"
# shellcheck source=fleet-launch/board-snapshot.sh
. "$FLEET_LAUNCH_DIR/board-snapshot.sh"

LAUNCHER_ARGS=("$@")
SELF=$FLEET_LAUNCH_DIR/$(basename "${BASH_SOURCE[0]}")
ITEM=${1:?usage: resume-capped.sh <item-id>}
REPO=${REPO_OVERRIDE:-$FLEET_LAUNCH_ORCH_REPO}
REPO_NAME=$(basename "$REPO")
REPO_HOLD_FILE="$FLEET_LAUNCH_REPO_HOLD_DIR/hold-repo-$REPO_NAME"
SEAT=$FLEET_LAUNCH_SEAT
OUT=$FLEET_LAUNCH_STATE_DIR
FABRO=$FLEET_LAUNCH_FABRO
GMK=$FLEET_LAUNCH_GMK_SERVER
HL=$FLEET_LAUNCH_HL_SERVER
INFLIGHT=$FLEET_LAUNCH_INFLIGHT_DIR
QUEUE=$FLEET_LAUNCH_GMK_QUEUE_DIR
LOCK=$FLEET_LAUNCH_GMK_LOCK_DIR
deadline=$(( $(date +%s) + FLEET_LAUNCH_MAX_WAIT_S ))
ticket=""
ticket_number=""
lock=""
marker=""
plugin=""
FLEET_CAP=0
# Non-run exit accounting (Scenario 312): a resume launcher that exits before its resume client starts
# writes one terminal line and, when its item still reads ready, one ledger comment naming the dropped ticket.
resume_started=0
terminal_written=0
exit_cause=""
gmk_live=U
hl_live=U
markers=U
fleet=U

mkdir -p "$OUT" "$QUEUE" "$INFLIGHT"

# A bash launcher keeps executing the script content it started with, so code added to this file
# after a launcher started never reached it (bd-ib-5ycmsm). The wait loop therefore compares this
# file on disk with the content the launcher started on and re-executes itself when they differ,
# keeping its pid, its queue ticket and its give-up deadline. Replace the file atomically (write
# beside it, then mv): an in-place edit corrupts a running bash.
script_version() { sha256sum < "$1" 2>/dev/null | cut -c1-12; }
START_VERSION=$(script_version "/proc/$$/fd/255")
[ -n "$START_VERSION" ] || START_VERSION=$(script_version "$SELF")
bad_version=""
if [ "${FLEET_LAUNCH_REEXEC_PID:-}" = "$$" ]; then
  [ -f "${FLEET_LAUNCH_REEXEC_TICKET:-}" ] && grep -q "pid=$$ " "$FLEET_LAUNCH_REEXEC_TICKET" && { ticket=$FLEET_LAUNCH_REEXEC_TICKET; ticket_number=${ticket##*/}; ticket_number=${ticket_number%%-*}; }
  case ${FLEET_LAUNCH_REEXEC_DEADLINE:-} in ''|*[!0-9]*) ;; *) deadline=$FLEET_LAUNCH_REEXEC_DEADLINE ;; esac
  echo "$(date -u +%FT%TZ) launcher re-executed on script version $START_VERSION: keeping ticket ${ticket##*/}"
fi
unset FLEET_LAUNCH_REEXEC_PID FLEET_LAUNCH_REEXEC_TICKET FLEET_LAUNCH_REEXEC_DEADLINE
# script_changed: the script on disk differs from the running content and parses.
script_changed() {
  local now; now=$(script_version "$SELF")
  [ -n "$now" ] && [ "$now" != "$START_VERSION" ] || return 1
  bash -n "$SELF" 2>/dev/null && return 0
  [ "$now" = "$bad_version" ] || echo "$(date -u +%FT%TZ) launcher script changed on disk ($now) but does not parse: keep running $START_VERSION"
  bad_version=$now
  return 1
}
# reexec_on_script_change: call only where this launcher holds no mutex and no in-flight marker.
reexec_on_script_change() {
  script_changed || return 0
  echo "$(date -u +%FT%TZ) launcher script changed on disk ($START_VERSION -> $(script_version "$SELF")): re-exec, keeping ticket ${ticket##*/}"
  export FLEET_LAUNCH_REEXEC_PID=$$ FLEET_LAUNCH_REEXEC_TICKET=$ticket FLEET_LAUNCH_REEXEC_DEADLINE=$deadline
  exec bash "$SELF" "${LAUNCHER_ARGS[@]}"
}

drop_ticket() { [ -n "$ticket" ] && rm -f "$ticket"; ticket=""; }
yield_ticket() {
  [ -n "$ticket" ] && [ -f "$ticket" ] && ! grep -q '^held=' "$ticket" && echo "held=$1" >> "$ticket"
}
restore_ticket() { [ -n "$ticket" ] && [ -f "$ticket" ] && sed -i '/^held=/d' "$ticket"; }
repository_hold_applies() {
  local raw compact
  HOLD_KINDS=all
  HOLD_REASON=$(sed -n '/^reason:/ { s/^reason:[[:space:]]*//; p; q; }' "$REPO_HOLD_FILE" 2>/dev/null)
  HOLD_UNTIL=$(sed -n '/^until:/ { s/^until:[[:space:]]*//; p; q; }' "$REPO_HOLD_FILE" 2>/dev/null)
  [ -e "$REPO_HOLD_FILE" ] || return 1
  raw=$(sed -n '/^kinds:/ { s/^kinds:[[:space:]]*//; p; q; }' "$REPO_HOLD_FILE" 2>/dev/null)
  compact=$(printf '%s' "$raw" | tr -d '[:space:]')
  case "$compact" in
    dispatch|resume|dispatch,resume|resume,dispatch) HOLD_KINDS=$compact ;;
  esac
  [ "$HOLD_KINDS" = all ] && return 0
  case ",$HOLD_KINDS," in *",$1,"*) return 0 ;; esac
  return 1
}
log_repository_hold() {
  local details="kinds=$HOLD_KINDS"
  [ -n "$HOLD_REASON" ] && details="$details reason=$HOLD_REASON"
  [ -n "$HOLD_UNTIL" ] && details="$details until=$HOLD_UNTIL"
  echo "$(date -u +%FT%TZ) repository hold present ($REPO_HOLD_FILE): $details: yield FIFO head"
}
release_lock() {
  if [ -n "$lock" ] && grep -q "pid=$$ " "$lock/holder" 2>/dev/null; then
    rm -f "$lock/holder"
    rmdir "$lock" 2>/dev/null
  fi
  lock=""
}
installed_build() {
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print([e["version"] for e in d["plugins"][sys.argv[2]] if e.get("projectPath")==sys.argv[3]][0])' \
    "$FLEET_LAUNCH_PLUGIN_REGISTRY" "$FLEET_LAUNCH_PLUGIN_KEY" "$REPO" 2>/dev/null
}
item_status() {
  local out
  out=$(cd "$REPO" && "${WRAPPER:-$FLEET_LAUNCH_DEFAULT_WRAPPER}" -- python3 "$FLEET_LAUNCH_DIR/ledger-item.py" status "$plugin" "$REPO" "$ITEM" 2>/dev/null) || return 1
  out=$(printf '%s\n' "$out" | sed -n 's/^LEDGER-STATUS //p' | tail -n 1)
  [ -n "$out" ] && printf '%s' "$out"
}
# write_terminal <cause>: the one terminal line of a launcher that exits without a run.
write_terminal() {
  echo "$(date -u +%FT%TZ) terminal: item=$ITEM ticket=${ticket_number:-none} cause=$1"
  terminal_written=1
}
# report_dropped_ticket <cause>: one ledger comment naming the dropped ticket and the cause, when the item still
# reads ready. The ticket is not re-taken: this launcher is exiting.
report_dropped_ticket() {
  local status body
  [ -n "$plugin" ] || plugin="$FLEET_LAUNCH_PLUGIN_CACHE/$(installed_build)"
  status=$(item_status) || status=unreadable
  [ "$status" = ready ] || return 0
  body="Fleet launcher $SEAT exited for $ITEM before its resume started: ticket ${ticket_number:-none} was dropped and not re-taken (cause: $1). This exit was not a run ending, and the item read $status. Remedy: launch the resume again."
  (cd "$REPO" && "${WRAPPER:-$FLEET_LAUNCH_DEFAULT_WRAPPER}" -- python3 "$FLEET_LAUNCH_DIR/ledger-item.py" comment "$plugin" "$REPO" "$ITEM" "$body") >/dev/null 2>&1 \
    || echo "$(date -u +%FT%TZ) ledger comment for $ITEM failed: the dropped ticket ${ticket_number:-none} was not recorded"
}
# cleanup: every exit. The terminal line is written before the ticket file is removed.
cleanup() {
  local rc=$? cause=""
  trap - EXIT
  if [ "$resume_started" = 0 ] && [ "$terminal_written" = 0 ]; then
    case "$rc" in
      143) cause=${exit_cause:-"signal TERM (this exit was not a run ending)"} ;;
      130) cause=${exit_cause:-"signal INT (this exit was not a run ending)"} ;;
      129) cause=${exit_cause:-"signal HUP (this exit was not a run ending)"} ;;
      *) cause=${exit_cause:-"exit rc=$rc before its resume started"} ;;
    esac
    write_terminal "$cause"
  fi
  drop_ticket; release_lock; [ -n "$marker" ] && rm -f "$marker"
  [ -n "$cause" ] && report_dropped_ticket "$cause"
  return 0
}
trap cleanup EXIT

read_fleet_cap() {
  FLEET_CAP=$(tr -dc 0-9 < "$FLEET_LAUNCH_FLEET_CAP_FILE" 2>/dev/null)
  FLEET_CAP=${FLEET_CAP:-0}
}
rows_count() { if [ "$1" = U ]; then echo U; else printf '%s' "$1" | grep -c .; fi; }
# Snapshot the live in-flight markers as "<item>" lines, or U when the
# directory cannot be read.  Taken BEFORE the boards are read: a launcher drops
# its marker only after a board lists its run, so any marker that disappears
# after this snapshot belongs to a run the later board read already lists.
# Reading the boards first left a window where a run was neither listed (board
# read too early) nor marked (marker dropped since) and the fleet was
# undercounted (bd-ib-uhcn36, run 01M6H3VFB451).
marker_snapshot() {
  local f pid item items=""
  [ -d "$INFLIGHT" ] && [ -r "$INFLIGHT" ] && [ -x "$INFLIGHT" ] && command ls -1 "$INFLIGHT" > /dev/null 2>&1 || { echo U; return; }
  for f in "$INFLIGHT"/*; do
    [ -e "$f" ] || continue
    [ -r "$f" ] || { echo U; return; }
    pid=$(grep -oE 'pid=[0-9]+' "$f" | head -1 | cut -d= -f2)
    item=$(grep -oE 'item=[^ ]+' "$f" | head -1 | cut -d= -f2)
    if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then continue; fi
    items="$items$item
"
  done
  printf '%s' "$items"
}
# Count the snapshot's items that the (later) board rows do not list.
unlisted_markers() {
  local snapshot="$1" listed="$2" item count=0
  [ "$snapshot" = U ] && { echo U; return; }
  while IFS= read -r item; do
    [ -n "$item" ] || continue
    printf '%s\n' "$listed" | awk -v it="$item" '$4==it {found=1} END{exit !found}' && continue
    count=$((count + 1))
  done <<EOF_SNAPSHOT
$snapshot
EOF_SNAPSHOT
  echo "$count"
}
# read_boards [direct]: the boards come from the shared snapshot (board-snapshot.sh) unless "direct" asks for the
# factory itself, which is how the binding count under the mutex reads them.
read_boards() {
  local gmk_rows hl_rows snapshot reader=board_rows
  [ "${1:-}" = direct ] && reader=board_rows_direct
  snapshot=$(marker_snapshot)
  gmk_rows=$("$reader" "$FABRO" "$GMK")
  hl_rows=$("$reader" "$FABRO" "$HL")
  gmk_live=$(rows_count "$gmk_rows")
  hl_live=$(rows_count "$hl_rows")
  if [ "$gmk_live" = U ] || [ "$hl_live" = U ]; then markers=U; fleet=U; return; fi
  markers=$(unlisted_markers "$snapshot" "$(printf '%s\n%s\n' "$gmk_rows" "$hl_rows")")
  if [ "$markers" = U ]; then fleet=U; else fleet=$((gmk_live + hl_live + markers)); fi
}
# report_stall <ticket-file> <pid>: a queue reader met a ticket whose launcher is no longer alive. Written to
# stderr, because the reader runs in a command substitution, and before the ticket is removed.
report_stall() {
  local f="$1" it name
  name=${f##*/}
  it=$(grep -oE 'item=[^ ]+' "$f" 2>/dev/null | head -1 | cut -d= -f2)
  echo "$(date -u +%FT%TZ) stall: item=${it:-unknown} ticket=${name%%-*} dead-pid=${2:-none}: the launcher for ticket file $name is gone"
} >&2
oldest_live_ticket() {
  local f pid
  for f in $(command ls -1 "$QUEUE" 2>/dev/null | sort); do
    pid=$(grep -oE 'pid=[0-9]+' "$QUEUE/$f" 2>/dev/null | head -1 | cut -d= -f2)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      grep -q '^held=' "$QUEUE/$f" && continue
      echo "$QUEUE/$f"; return
    fi
    report_stall "$QUEUE/$f" "$pid"
    rm -f "$QUEUE/$f"
  done
}
take_mutex() {
  [ "$(oldest_live_ticket)" = "$ticket" ] || return 1
  mkdir "$LOCK" 2>/dev/null || return 1
  lock=$LOCK
  echo "owner=$SEAT pid=$$ item=$ITEM at=$(date -u +%FT%TZ)" > "$lock/holder"
}
write_marker() {
  marker="$INFLIGHT/$(date +%s%N)-$SEAT-$ITEM"
  echo "owner=$SEAT pid=$$ item=$ITEM factory=petri at=$(date -u +%FT%TZ)" > "$marker" || { marker=""; return 1; }
}
wait_for_listing() {
  local rows listing_deadline=""
  while :; do
    rows=$(board_rows "$FABRO" "$GMK")
    if [ "$rows" != U ] && printf '%s\n' "$rows" | awk -v it="$ITEM" '$4==it {found=1} END{exit !found}'; then
      rm -f "$marker"
      marker=""
      return
    fi
    if ! kill -0 "$1" 2>/dev/null; then
      [ -n "$listing_deadline" ] || listing_deadline=$(( $(date +%s) + FLEET_LAUNCH_LISTING_WAIT_S ))
      if [ "$(date +%s)" -ge "$listing_deadline" ]; then
        echo "$(date -u +%FT%TZ) resume client ended and the board never listed item=$ITEM within ${FLEET_LAUNCH_LISTING_WAIT_S}s; releasing marker"
        return
      fi
    fi
    sleep "$FLEET_LAUNCH_POLL_S"
  done
}

if [ -z "$ticket" ]; then
  ticket_number=$(date +%s%N)
  ticket="$QUEUE/$ticket_number-$SEAT"
  echo "owner=$SEAT pid=$$ item=$ITEM" > "$ticket"
  echo "$(date -u +%FT%TZ) gmktec FIFO ticket taken at start: ${ticket##*/}"
fi

while :; do
  reexec_on_script_change
  [ "$(date +%s)" -lt "$deadline" ] || { echo "resume gave up item=$ITEM queue-ticket=${ticket##*/}"; exit_cause="resume gave up: no slot within ${FLEET_LAUNCH_MAX_WAIT_S}s"; exit 75; }
  # TERM uses bash's default action because bash 5.2 can fail to parse a TERM
  # trap while a command substitution is active.  Preserve TERM's non-run
  # description for EXIT cleanup across the repository-hold read and wait.
  exit_cause="signal TERM (this exit was not a run ending)"
  if repository_hold_applies resume; then
    yield_ticket repository-hold
    log_repository_hold
    sleep "$FLEET_LAUNCH_POLL_S"
    continue
  fi
  restore_ticket
  ahead=$(oldest_live_ticket)
  if [ "$ahead" != "$ticket" ]; then
    echo "$(date -u +%FT%TZ) queued behind an older gmktec ticket: $(cat "$ahead" 2>/dev/null)"
    sleep "$FLEET_LAUNCH_POLL_S"
    continue
  fi
  if [ -e "$FLEET_LAUNCH_HOLD_FILE" ]; then
    echo "$(date -u +%FT%TZ) hold file present ($FLEET_LAUNCH_HOLD_FILE): wait"
    sleep "$FLEET_LAUNCH_POLL_S"
    continue
  fi
  if ! take_mutex; then sleep "$FLEET_LAUNCH_POLL_S"; continue; fi
  read_fleet_cap
  read_boards direct
  if [ "$fleet" = U ] || [ "$FLEET_CAP" -le 0 ] || [ "$fleet" -ge "$FLEET_CAP" ]; then
    echo "$(date -u +%FT%TZ) fleet at cap under mutex: fleet=$fleet cap=$FLEET_CAP; keep FIFO ticket"
    release_lock
    sleep "$FLEET_LAUNCH_POLL_S"
    continue
  fi
  if ! write_marker; then
    echo "$(date -u +%FT%TZ) could not write resume in-flight marker; keep FIFO ticket"
    release_lock
    sleep "$FLEET_LAUNCH_POLL_S"
    continue
  fi
  if script_changed; then
    rm -f "$marker"
    marker=""
    release_lock
    echo "$(date -u +%FT%TZ) launcher script changed on disk before launch: released the mutex and marker, keeping the ticket"
    continue
  fi
  if repository_hold_applies resume; then
    rm -f "$marker"
    marker=""
    yield_ticket repository-hold
    log_repository_hold
    release_lock
    sleep "$FLEET_LAUNCH_POLL_S"
    continue
  fi
  drop_ticket
  release_lock
  resume_started=1
  echo "$(date -u +%FT%TZ) resume marker written and mutex released: item=$ITEM"
  "$FLEET_LAUNCH_RESUME_WRAPPER" -- "$FLEET_LAUNCH_RESUME_COMMAND" --item "$ITEM" > "$OUT/$ITEM-resume.out" 2> "$OUT/$ITEM-resume.err" &
  resume_pid=$!
  wait_for_listing "$resume_pid"
  wait "$resume_pid"
  exit $?
done
