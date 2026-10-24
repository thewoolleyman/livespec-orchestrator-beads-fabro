#!/usr/bin/env bash
# PROVISIONAL / EXPERIMENTAL — fleet launch for one work-item.
#
# A stopgap captured from the launcher the factory seats ran by hand during plan
# petri-factory-on-gmktec. Its first-class replacements are the livespec console
# application and the committed launch-loop tool bd-ib-jr6w7v; see README.md for
# why it exists and when it is retired.
#
# It is a CALLER-side launch loop (SPECIFICATION/contracts.md, "Dispatcher admission,
# WIP cap, and post-merge acceptance": "A caller MAY add gates of its own for
# conditions the Dispatcher does not own"). It decides only WHEN to invoke
# `drive --action impl:<item>`; every admission condition stays the Dispatcher's.
#
# Usage: dispatch-dual.sh <item-id>
# Environment (all optional):
#   REPO_OVERRIDE=<path>   the tenant repository (default: this orchestrator repo)
#   WRAPPER=<path>         that tenant's credential wrapper (see wrappers/)
#   ONLY_GMK=1             launch onto the petri factory (gmktec :32276) only, taking
#                          a FIFO ticket at start
#   ONLY_HL=1              launch onto the mi-homelab instance (gmktec :32277) only
#   CAPTURE_NULL=1         dispatch naming NO factory, and require the run's argv to
#   CAPTURE_EXPECT=<name>    carry --server of the registry-resolved CAPTURE_EXPECT
#   TICKET_NS=<ns>         reuse a queue position (restart without losing FIFO order)
#   REWORK=1               ask the Dispatcher's loop dry-run instead of the ready set
#   RELEASE_BLOCKED=1      run resolve-blocked:<item>:ready just before launching
#
# Gates, in order: the Dispatcher's own ready set; the shared fleet cap (live runs on
# every declared board plus launches not yet listed); the launch-time
# Definition-of-Done preflight; the hold file; gmktec's own ceiling and idle CPU; a
# per-factory FIFO ticket and mutex; a binding re-count that includes this launch's
# in-flight marker; and a usable-credential probe. An unreadable board counts as
# UNKNOWN and is never green.
set -u
FLEET_LAUNCH_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=fleet-launch/config.sh
. "$FLEET_LAUNCH_DIR/config.sh"

ITEM=${1:?usage: dispatch-dual.sh <item-id>}
SEAT=$FLEET_LAUNCH_SEAT
REPO=${REPO_OVERRIDE:-$FLEET_LAUNCH_ORCH_REPO}
OUT=$FLEET_LAUNCH_STATE_DIR
WRAP=${WRAPPER:-$FLEET_LAUNCH_DEFAULT_WRAPPER}
GMK=$FLEET_LAUNCH_GMK_SERVER
HL=$FLEET_LAUNCH_HL_SERVER
FABRO=$FLEET_LAUNCH_FABRO
INFLIGHT=$FLEET_LAUNCH_INFLIGHT_DIR
GMK_Q=$FLEET_LAUNCH_GMK_QUEUE_DIR
GMK_LOCK=$FLEET_LAUNCH_GMK_LOCK_DIR
deadline=$(( $(date +%s) + FLEET_LAUNCH_MAX_WAIT_S ))
ticket=""; lock=""; marker=""; FLEET_CAP=0
gmk_rows=""; hl_rows=""; gmk_live=U; hl_live=U; markers=U; fleet=U; gmk_idle=""
mkdir -p "$OUT"

drop_ticket() { [ -n "$ticket" ] && rm -f "$ticket"; ticket=""; }
release_lock() {
  if [ -n "$lock" ] && grep -q "pid=$$ " "$lock/holder" 2>/dev/null; then rm -f "$lock/holder"; rmdir "$lock" 2>/dev/null; fi
  lock=""
}
trap 'drop_ticket; release_lock; [ -n "$marker" ] && rm -f "$marker"' EXIT
trap 'exit 143' TERM INT

read_fleet_cap() { FLEET_CAP=$(tr -dc 0-9 < "$FLEET_LAUNCH_FLEET_CAP_FILE" 2>/dev/null); FLEET_CAP=${FLEET_CAP:-0}; }

# board_rows <fabro> <server>: one line per NON-TERMINAL run ("<id> <status> <duration> <item>"),
# nothing for an empty board, or the single token U when the board cannot be read.
board_rows() {
  local out
  out=$("$1" ps -a --server "$2" 2>/dev/null) || { echo U; return; }
  # An empty board exits 0 with nothing on stdout ("No runs found." goes to stderr): a reading of
  # zero, not an unreadable board.
  [ -z "$out" ] && return 0
  printf '%s\n' "$out" | head -1 | grep -q '^RUN ID' || { echo U; return; }
  printf '%s\n' "$out" \
    | awk 'NR>1 && length($1)==12 && $1 ~ /^[0-9A-Z]+$/ && $3 !~ /^(succeeded|failed|cancelled|canceled|timeout|timed_out|aborted|removed|dead|completed)$/ {print $1, $3, $5, $NF}'
}
rows_count() { if [ "$1" = U ]; then echo U; else printf '%s' "$1" | grep -c .; fi; }

# unlisted_markers <listed-rows>: in-flight markers of launches whose run has not listed yet.
unlisted_markers() {
  local listed="$1" f p it n=0
  mkdir -p "$INFLIGHT" 2>/dev/null
  [ -d "$INFLIGHT" ] && [ -r "$INFLIGHT" ] && [ -x "$INFLIGHT" ] || { echo U; return; }
  for f in "$INFLIGHT"/*; do
    [ -e "$f" ] || continue
    [ -r "$f" ] || { echo U; return; }
    p=$(grep -oE 'pid=[0-9]+' "$f" | head -1 | cut -d= -f2)
    it=$(grep -oE 'item=[^ ]+' "$f" | head -1 | cut -d= -f2)
    # A dead-pid marker is stale only when no drive.py impl dispatch for its item is alive.
    if ! { [ -n "$p" ] && kill -0 "$p" 2>/dev/null; }; then
      [ -n "$it" ] && pgrep -u "$(id -u)" -f -- "drive.py .*--action impl:${it}( |$)" >/dev/null 2>&1 || continue
    fi
    printf '%s\n' "$listed" | awk -v it="$it" '$4==it {found=1} END{exit !found}' && continue
    n=$((n + 1))
  done
  echo "$n"
}

# read_boards: sets gmk_live, hl_live, markers and fleet (a number, or U when any reading is unknown).
read_boards() {
  gmk_rows=$(board_rows "$FABRO" "$GMK")
  hl_rows=$(board_rows "$FABRO" "$HL")
  gmk_live=$(rows_count "$gmk_rows"); hl_live=$(rows_count "$hl_rows")
  if [ "$gmk_live" = U ] || [ "$hl_live" = U ]; then markers=U; fleet=U; return; fi
  markers=$(unlisted_markers "$(printf '%s\n%s\n' "$gmk_rows" "$hl_rows")")
  if [ "$markers" = U ]; then fleet=U; else fleet=$(( gmk_live + hl_live + markers )); fi
}
gt() { awk "BEGIN{exit !($1 > $2)}"; }
mpstat_idle() { ssh -o BatchMode=yes -o ConnectTimeout=15 "$1" 'mpstat 5 2' 2>/dev/null | awk '/^Average/ {print $NF}'; }
fleet_green() {
  read_fleet_cap; read_boards
  [ "$fleet" != U ] && [ "$FLEET_CAP" -gt 0 ] && [ "$fleet" -lt "$FLEET_CAP" ]
}
# bind_count <factory>: write this launch's marker, then re-count with it included; proceed only at or under the cap.
bind_count() {
  marker="$INFLIGHT/$(date +%s%N)-$SEAT-$ITEM"
  mkdir -p "$INFLIGHT" 2>/dev/null
  echo "owner=$SEAT pid=$$ item=$ITEM factory=$1 at=$(date -u +%FT%TZ)" > "$marker" || { marker=""; return 1; }
  read_fleet_cap; read_boards
  if [ "$fleet" != U ] && [ "$FLEET_CAP" -gt 0 ] && [ "$fleet" -le "$FLEET_CAP" ]; then return 0; fi
  echo "$(date -u +%T) binding count with our marker: fleet=$fleet cap=${FLEET_CAP:-?}: delete marker, skip"
  rm -f "$marker"; marker=""; return 1
}
gmk_green() {
  [ "$gmk_live" != U ] && [ "$gmk_live" -lt "$FLEET_LAUNCH_GMK_CAP" ] || return 1
  gmk_idle=$(mpstat_idle "$FLEET_LAUNCH_GMK_SSH"); [ -n "$gmk_idle" ] && gt "$gmk_idle" "$FLEET_LAUNCH_GMK_MIN_IDLE"
}
holder_dead() {
  local age h pid
  age=$(( $(date +%s) - $(stat -c %Y "$1/holder" 2>/dev/null || date +%s) ))
  [ "$age" -gt "$FLEET_LAUNCH_MUTEX_HOLD_S" ] || return 1
  h=$(cat "$1/holder" 2>/dev/null)
  pid=$(printf '%s' "$h" | grep -oE 'pid[=:] *[0-9]+' | grep -oE '[0-9]+' | head -1)
  [ -n "$pid" ] || return 1
  ! kill -0 "$pid" 2>/dev/null
}
# oldest_live_ticket <queue-dir>: the oldest ticket whose launcher is alive; dead tickets are removed.
oldest_live_ticket() {
  local q="$1" f p
  for f in $(command ls -1 "$q" 2>/dev/null | sort); do
    p=$(grep -oE 'pid=[0-9]+' "$q/$f" 2>/dev/null | head -1 | cut -d= -f2)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then echo "$q/$f"; return; fi
    rm -f "$q/$f"
  done
}
# take_mutex <queue-dir> <lock-dir>: FIFO ticket, 10 s polls, abandon after FLEET_LAUNCH_ABANDON_S.
take_mutex() {
  local q="$1" l="$2" queued early=""
  mkdir -p "$q"
  # Reuse a ticket taken at launcher start, so its FIFO place is when the launch was queued.
  if [ -n "$ticket" ] && [ "${ticket%/*}" = "$q" ] && [ -f "$ticket" ]; then early=1; else
    ticket="$q/$(date +%s%N)-$SEAT"; echo "owner=$SEAT pid=$$ item=$ITEM" > "$ticket"; fi
  queued=$(date +%s)
  while [ $(( $(date +%s) - queued )) -lt "$FLEET_LAUNCH_ABANDON_S" ]; do
    if [ -d "$l" ] && holder_dead "$l"; then echo "$(date -u +%T) dead holder on $l: $(cat "$l/holder" 2>/dev/null); removing"; rm -f "$l/holder"; rmdir "$l" 2>/dev/null; fi
    if [ ! -d "$l" ] && [ "$(oldest_live_ticket "$q")" = "$ticket" ] && mkdir "$l" 2>/dev/null; then
      # An EARLY ticket is kept while the lock is held: if bind_count then fails, the launcher keeps its
      # FIFO place instead of polling ticketless. The ticket is dropped only once the launch binds.
      lock="$l"; echo "owner=$SEAT pid=$$ item=$ITEM at=$(date -u +%FT%TZ)" > "$l/holder"; [ -n "$early" ] || drop_ticket; return 0
    fi
    sleep 10
  done
  [ -n "$early" ] || drop_ticket; return 1
}

installed_build() {
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print([e["version"] for e in d["plugins"][sys.argv[2]] if e.get("projectPath")==sys.argv[3]][0])' \
    "$FLEET_LAUNCH_PLUGIN_REGISTRY" "$FLEET_LAUNCH_PLUGIN_KEY" "$REPO" 2>/dev/null
}

echo "=== fleet-launch dispatch $ITEM at $(date -u +%FT%TZ)"
ready_check() {
  local p pick
  p="$FLEET_LAUNCH_PLUGIN_CACHE/$(installed_build)"
  if [ -n "${REWORK:-}" ]; then
    # A rework:pending row is `active`, so it is never in ready_items(); ask the Dispatcher's own loop
    # selection (the path drive impl:<id> runs) whether it would pick this item.
    pick=$(cd "$REPO" && "$WRAP" -- python3 "$p/scripts/bin/dispatcher.py" loop --repo "$REPO" --budget 1 --item "$ITEM" --dry-run --json --invoker "claude:$SEAT" 2>/dev/null)
    if printf '%s' "$pick" | python3 -c 'import json,sys; rows=json.loads(sys.stdin.read() or "[]"); sys.exit(0 if any(r.get("stage")=="loop-pick" and r.get("status")=="dry-run" and r.get("work_item_id")==sys.argv[1] for r in rows) else 3)' "$ITEM"; then
      echo "READY-CHECK $ITEM: REWORK, the Dispatcher's loop dry-run picks it"; return 0
    fi
    echo "READY-CHECK $ITEM: REWORK, the Dispatcher's loop dry-run does NOT pick it"; return 3
  fi
  (cd "$REPO" && "$WRAP" -- python3 "$FLEET_LAUNCH_DIR/ready-set-check.py" "$p" "$REPO" "$ITEM" 2>/dev/null)
}
rcout=$(ready_check); rcrc=$?; echo "$(date -u +%T) $rcout"
[ $rcrc = 0 ] || { echo "$(date -u +%T) ready-set check refused (rc=$rcrc): no slot taken, no launch"; exit 3; }

# The launch-time Definition-of-Done preflight runs at launch, just before the marker, and a pass is
# reused for FLEET_LAUNCH_PREFLIGHT_REUSE_S so a repeatedly-green launcher does not re-run it every poll.
pf_ok_at=0
launch_preflight() {
  local now prc pf="$OUT/$ITEM-preflight-launch.txt"; now=$(date +%s)
  [ $(( now - pf_ok_at )) -lt "$FLEET_LAUNCH_PREFLIGHT_REUSE_S" ] && return 0
  (cd "$REPO" && "$WRAP" -- "$FLEET_LAUNCH_ORCH_REPO/dev-tooling/dod-preflight.sh" "$ITEM") > "$pf" 2>&1; prc=$?
  if [ $prc = 0 ]; then pf_ok_at=$now; echo "$(date -u +%T) launch-time preflight PASS"; return 0; fi
  if [ $prc = 1 ]; then echo "$(date -u +%T) launch-time preflight FAILED: $(tail -1 "$pf" | cut -c1-300): no slot, no launch"; exit 4; fi
  # A fenced JSON verdict makes dod-preflight.sh exit 2; a failed outcome inside it is a finding.
  if [ $prc = 2 ] && grep -q '^{"outcome": "failed"' "$pf"; then echo "$(date -u +%T) launch-time preflight FAILED (fenced verdict): $(grep -m1 '^{"outcome": "failed"' "$pf" | cut -c1-300): no slot, no launch"; exit 4; fi
  echo "$(date -u +%T) launch-time preflight TOOL FAILURE rc=$prc: no slot, no launch"; exit 70
}

target=""; taken=0
# A gmktec-only launch takes its FIFO ticket NOW and holds it while it polls, so a launcher queued
# later cannot win the next freed slot ahead of it.
if [ -n "${ONLY_GMK:-}" ] || [ -n "${ONLY_HL:-}" ]; then
  mkdir -p "$GMK_Q"; ticket="$GMK_Q/${TICKET_NS:-$(date +%s%N)}-$SEAT"; echo "owner=$SEAT pid=$$ item=$ITEM" > "$ticket"
  echo "$(date -u +%T) gmktec FIFO ticket taken at start: ${ticket##*/}"
fi
while [ -z "$target" ]; do
  if [ -n "$ticket" ] && [ "${ticket%/*}" = "$GMK_Q" ]; then
    ahead=$(oldest_live_ticket "$GMK_Q")
    if [ -n "$ahead" ] && [ "$ahead" != "$ticket" ]; then
      [ "$(date +%s)" -lt "$deadline" ] || { echo "no slot within ${FLEET_LAUNCH_MAX_WAIT_S}s: give up"; exit 75; }
      echo "$(date -u +%T) queued behind an older gmktec ticket: $(cat "$ahead" 2>/dev/null)"; sleep "$FLEET_LAUNCH_POLL_S"; continue
    fi
  fi
  [ "$(date +%s)" -lt "$deadline" ] || { echo "no slot within ${FLEET_LAUNCH_MAX_WAIT_S}s: give up"; exit 75; }
  gmk_idle=
  if ! fleet_green; then echo "$(date -u +%T) fleet not green: gmktec=$gmk_live hl=$hl_live markers=$markers fleet=$fleet cap=${FLEET_CAP:-?}"; sleep "$FLEET_LAUNCH_POLL_S"; continue; fi
  if [ -e "$FLEET_LAUNCH_HOLD_FILE" ]; then echo "$(date -u +%T) hold file present ($FLEET_LAUNCH_HOLD_FILE): wait"; sleep "$FLEET_LAUNCH_POLL_S"; continue; fi
  launch_preflight
  if [ -n "${ONLY_HL:-}" ]; then
    if [ "$hl_live" != U ] && [ "$hl_live" -lt "$FLEET_LAUNCH_HL_CAP" ]; then
      echo "$(date -u +%T) mi-homelab green (live=$hl_live fleet=$fleet): queue for the gmktec mutex"
      if take_mutex "$GMK_Q" "$GMK_LOCK"; then
        taken=$(date +%s)
        if bind_count mi-homelab && [ "$hl_live" -lt "$FLEET_LAUNCH_HL_CAP" ]; then drop_ticket; target=mi-homelab; break; fi
        [ -n "$marker" ] && { rm -f "$marker"; marker=""; }
        echo "$(date -u +%T) under the gmktec mutex: mi-homelab no longer green (hl=$hl_live fleet=$fleet): release"; release_lock
      fi
    else echo "$(date -u +%T) mi-homelab not green: live=$hl_live cap=$FLEET_LAUNCH_HL_CAP"; fi
    sleep "$FLEET_LAUNCH_POLL_S"; continue
  fi
  if { [ -z "${CAPTURE_NULL:-}" ] || [ "${CAPTURE_EXPECT:-}" = petri ]; } && gmk_green; then
    echo "$(date -u +%T) gmktec green (live=$gmk_live hl=$hl_live idle=$gmk_idle fleet=$fleet): queue for the gmktec mutex"
    if take_mutex "$GMK_Q" "$GMK_LOCK"; then
      taken=$(date +%s)
      if bind_count petri && gmk_green; then drop_ticket; target=petri; break; fi
      [ -n "$marker" ] && { rm -f "$marker"; marker=""; }
      echo "$(date -u +%T) under the gmktec mutex: no longer green (gmktec=$gmk_live fleet=$fleet): release"; release_lock
    fi
    sleep "$FLEET_LAUNCH_POLL_S"; continue
  fi
  echo "$(date -u +%T) no factory green: gmktec=$gmk_live (idle ${gmk_idle:-?}) markers=$markers fleet=$fleet/$FLEET_CAP"
  sleep "$FLEET_LAUNCH_POLL_S"
done

# Release the launch mutex right after the binding count; the in-flight marker stays until the run
# lists or the dispatch exits.
release_lock; echo "$(date -u +%T) mutex released after the count (marker kept)"
if [ "$target" = petri ]; then
  FABRO_DEV_TOKEN__petri=$(ssh -o BatchMode=yes "$FLEET_LAUNCH_GMK_SSH" cat "$FLEET_LAUNCH_GMK_SERVER_ENV" | sed -n 's/^FABRO_DEV_TOKEN=//p' | tail -n 1)
  export FABRO_DEV_TOKEN__petri
  tserver=$GMK
else
  tserver=$HL
fi
if [ -n "${CAPTURE_NULL:-}" ]; then
  [ "$target" = "${CAPTURE_EXPECT:-}" ] || { echo "CAPTURE_NULL but target=$target (expected ${CAPTURE_EXPECT:-unset}): refuse"; exit 70; }
  unset LIVESPEC_FABRO_FACTORY; echo "$(date -u +%T) CAPTURE_NULL: LIVESPEC_FABRO_FACTORY unset, no --factory"
else
  export LIVESPEC_FABRO_FACTORY=$target
fi
git -C "$REPO" fetch -q origin && git -C "$REPO" merge --ff-only -q origin/master
build=$(installed_build)
plugin="$FLEET_LAUNCH_PLUGIN_CACHE/$build"
build_version=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['version'])" "$plugin/plugin.json" 2>/dev/null)
cred=$(cd "$REPO" && timeout 120 "$WRAP" -- python3 "$plugin/scripts/bin/dispatcher.py" claude-cred-status 2>/dev/null)
printf '%s\n' "$cred" | grep -q "is usable" || { echo "$(date -u +%T) credential probe NOT usable: hold, no launch"; printf '%s\n' "$cred" | tail -3; rm -f "$marker"; marker=""; release_lock; exit 75; }
echo "$(date -u +%T) credential probe usable (HTTP 200)"
rcout=$(ready_check); rcrc=$?
if [ $rcrc != 0 ]; then echo "$(date -u +%T) ready-set re-check refused before launch: $rcout"; rm -f "$marker"; marker=""; release_lock; exit 3; fi
echo "$(date -u +%T) LAUNCH target=$target head=$(git -C "$REPO" rev-parse --short HEAD) build=$build version=${build_version:-?}"
if [ -n "${RELEASE_BLOCKED:-}" ]; then
  rel=$(cd "$REPO" && "$WRAP" -- python3 "$plugin/scripts/bin/drive.py" --repo "$REPO" --action "resolve-blocked:${ITEM}:ready" --invoker "claude:$SEAT" --json 2>&1); rrc=$?
  echo "$(date -u +%T) resolve-blocked:${ITEM}:ready rc=$rrc $(printf '%s' "$rel" | tr '\n' ' ' | cut -c1-300)"
  [ $rrc = 0 ] || { echo "release refused: no launch"; exit 75; }
fi
(cd "$REPO" && "$WRAP" -- python3 "$plugin/scripts/bin/drive.py" --repo "$REPO" --action "impl:$ITEM" --invoker "claude:$SEAT" --json) > "$OUT/$ITEM-r267.json" 2>"$OUT/$ITEM-r267.stderr" &
drive_pid=$!
if [ -n "${CAPTURE_NULL:-}" ]; then
  # Watch for the first fabro run of THIS item and check that its argv names the expected server.
  while kill -0 "$drive_pid" 2>/dev/null; do
    fp=""
    for p in $(pgrep -f "fabro run"); do a=$p; while [ "$a" -gt 1 ]; do [ "$a" = "$drive_pid" ] && { fp=$p; break 2; }; a=$(ps -o ppid= -p "$a" 2>/dev/null | tr -d ' '); [ -n "$a" ] || break; done; done
    if [ -n "$fp" ]; then
      argv=$(tr '\0' ' ' < "/proc/$fp/cmdline" 2>/dev/null)
      echo "$(date -u +%T) CAPTURE fabro run pid=$fp argv: $argv" | tee "$OUT/$ITEM-r267.capture-argv"
      if printf '%s' "$argv" | grep -q -- "--server $tserver"; then echo "$(date -u +%T) CAPTURE argv OK: --server $tserver"; else
        kill -TERM "$fp" 2>/dev/null; echo "$(date -u +%T) CAPTURE FAILURE: argv lacks --server $tserver; killed fabro run pid $fp"; fi
      break
    fi
    sleep 0.2
  done
fi
run_row=""
while :; do
  run_row=$(board_rows "$FABRO" "$tserver" | awk -v it="$ITEM" '$4==it {print; exit}')
  if [ -n "$run_row" ]; then echo "$(date -u +%T) LISTED on $target: $run_row"; break; fi
  if ! kill -0 "$drive_pid" 2>/dev/null; then echo "$(date -u +%T) drive exited before listing"; break; fi
  if [ -n "$lock" ] && [ $(( $(date +%s) - taken )) -ge "$FLEET_LAUNCH_MUTEX_HOLD_S" ]; then echo "$(date -u +%T) mutex hold elapsed: release (marker kept until listing or drive exit)"; release_lock; fi
  sleep 15
done
release_lock; rm -f "$marker"; marker=""
echo "$(date -u +%FT%TZ) target=$target build=$build version=${build_version:-?} listed=${run_row:-none}" > "$OUT/$ITEM-r267.verdict"
wait "$drive_pid"; rc=$?
echo "$(date -u +%T) drive rc=$rc"
echo "$(date -u +%FT%TZ) drive rc=$rc" >> "$OUT/$ITEM-r267.verdict"
exit "$rc"
