# shellcheck shell=bash
# PROVISIONAL / EXPERIMENTAL — fleet-launch's shared factory-board reader.
#
# This directory is a stopgap; its first-class replacements are the livespec
# console application and the committed launch-loop tool bd-ib-jr6w7v (see
# README.md). Sourced by dispatch-dual.sh and resume-capped.sh after config.sh.
#
# WHY A SHARED SNAPSHOT. Every queued launcher used to run `fabro ps -a --server
# <factory>` on each poll, and one run listing costs the petri server 25-40 s
# whatever it returns (bd-ib-busjvz). With dozens of launchers queued the server
# answered a listing roughly every second. The listing is now taken ONCE per
# FLEET_LAUNCH_BOARD_TTL_S per factory, into a file every launcher on the host
# reads:
#
#   - A snapshot younger than the TTL is read as is.
#   - An older one is refreshed before it is used. One launcher refreshes while
#     the rest wait for it behind a lock directory, so a burst of launchers that
#     all find the snapshot stale still sends the server one listing.
#   - A refresh that cannot read the board writes nothing and the reading is
#     unknown (U), never a stale snapshot and never zero.
#   - The binding count a launcher takes under the launch mutex reads the board
#     DIRECTLY (board_rows_direct): that count is the one that admits a launch.
#
# Snapshots only ever advance in time, so a launcher that drops its in-flight
# marker after a snapshot lists its run is followed by readers whose snapshot
# lists it too; the marker-before-board ordering in read_boards relies on this.

# board_snapshot_file <server>: the snapshot path for one factory server.
board_snapshot_file() {
  printf '%s/%s.ps' "$FLEET_LAUNCH_BOARD_SNAPSHOT_DIR" "$(printf '%s' "$1" | tr -c 'A-Za-z0-9' _)"
}

# board_snapshot_age_ok <file> <max-age-s>: the snapshot exists and is younger than <max-age-s>.
board_snapshot_age_ok() {
  local mtime
  [ -f "$1" ] || return 1
  mtime=$(stat -c %Y "$1" 2>/dev/null) || return 1
  [ $(( $(date +%s) - mtime )) -lt "$2" ]
}

# board_refresh_lock_stale <lock-dir>: the refreshing launcher is dead, or has held the lock past the wait bound.
board_refresh_lock_stale() {
  local pid mtime
  pid=$(grep -oE 'pid=[0-9]+' "$1/holder" 2>/dev/null | head -1 | cut -d= -f2)
  if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then return 0; fi
  mtime=$(stat -c %Y "$1" 2>/dev/null) || return 1
  [ $(( $(date +%s) - mtime )) -ge "$FLEET_LAUNCH_BOARD_REFRESH_WAIT_S" ]
}

# board_snapshot_text <fabro> <server>: the raw `fabro ps -a` listing from the shared snapshot, refreshing it when
# it is older than FLEET_LAUNCH_BOARD_TTL_S. Non-zero when the board cannot be read.
board_snapshot_text() {
  local fabro="$1" server="$2" file lock tmp started waited=0 contended=""
  file=$(board_snapshot_file "$server"); lock="$file.refresh.d"; tmp="$file.tmp.$$"; started=$(date +%s)
  mkdir -p "$FLEET_LAUNCH_BOARD_SNAPSHOT_DIR" 2>/dev/null || return 1
  while :; do
    if board_snapshot_age_ok "$file" "$FLEET_LAUNCH_BOARD_TTL_S"; then cat "$file" 2>/dev/null; return; fi
    if [ -n "$contended" ] && [ ! -d "$lock" ]; then
      # The refresh this launcher waited on has ended. Its snapshot is the reading; when it left none, that
      # refresh could not read the board, so this launcher reports it unreadable too instead of sending the
      # server a failing read of its own.
      if board_snapshot_age_ok "$file" $(( $(date +%s) - started + 1 )); then cat "$file" 2>/dev/null; return; fi
      return 1
    fi
    if mkdir "$lock" 2>/dev/null; then
      echo "pid=$$" > "$lock/holder"
      # Another launcher can finish its refresh after our stale check and before
      # this launcher takes the lock. Re-check while holding it so that handoff
      # is read from the shared snapshot instead of issuing a second listing.
      if board_snapshot_age_ok "$file" "$FLEET_LAUNCH_BOARD_TTL_S"; then
        rm -f "$lock/holder"; rmdir "$lock" 2>/dev/null
        cat "$file" 2>/dev/null; return
      fi
      if "$fabro" ps -a --server "$server" > "$tmp" 2>/dev/null && mv -f "$tmp" "$file"; then
        rm -f "$lock/holder"; rmdir "$lock" 2>/dev/null
        cat "$file" 2>/dev/null; return
      fi
      rm -f "$tmp" "$lock/holder"; rmdir "$lock" 2>/dev/null
      return 1
    fi
    contended=1
    if board_refresh_lock_stale "$lock"; then rm -f "$lock/holder"; rmdir "$lock" 2>/dev/null; contended=""; continue; fi
    [ "$waited" -lt "$FLEET_LAUNCH_BOARD_REFRESH_WAIT_S" ] || return 1
    sleep 1; waited=$((waited + 1))
  done
}

# board_parse_rows: the raw listing on stdin as one line per NON-TERMINAL run ("<id> <status> <duration> <item>"),
# nothing for an empty board, or the single token U when it is not a board listing.
board_parse_rows() {
  local out
  out=$(cat)
  # An empty board exits 0 with nothing on stdout ("No runs found." goes to stderr): a reading of
  # zero, not an unreadable board.
  [ -z "$out" ] && return 0
  printf '%s\n' "$out" | head -1 | grep -q '^RUN ID' || { echo U; return; }
  printf '%s\n' "$out" \
    | awk 'NR>1 && length($1)==12 && $1 ~ /^[0-9A-Z]+$/ && $3 !~ /^(succeeded|failed|cancelled|canceled|timeout|timed_out|aborted|removed|dead|completed)$/ {print $1, $3, $5, $NF}'
}

# board_rows <fabro> <server>: the board's non-terminal runs from the shared snapshot, or U when it cannot be read.
board_rows() {
  local text
  text=$(board_snapshot_text "$1" "$2") || { echo U; return; }
  printf '%s' "$text" | board_parse_rows
}

# board_rows_direct <fabro> <server>: the same reading taken from the factory itself, for a binding count.
board_rows_direct() {
  local text
  text=$("$1" ps -a --server "$2" 2>/dev/null) || { echo U; return; }
  printf '%s' "$text" | board_parse_rows
}
