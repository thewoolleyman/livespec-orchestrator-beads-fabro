#!/usr/bin/env bash
# PROVISIONAL / EXPERIMENTAL — part of fleet-launch/, a stopgap whose first-class
# replacements are the livespec console application and the committed launch-loop
# tool bd-ib-jr6w7v (see fleet-launch/README.md).
#
# Keep the gmktec launch hold in place until caam's active Claude profile is no longer
# HOLD_PROFILE (default anthropic-1), then remove the hold file so queued launchers
# release in FIFO order. Bounded: after MAX_S it leaves the hold in place and says so.
# Usage: release-hold-on-caam-rotation.sh   (HOLD_PROFILE, MAX_S optional)
set -u
FLEET_LAUNCH_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=fleet-launch/config.sh
. "$FLEET_LAUNCH_DIR/config.sh"
HOLD=$FLEET_LAUNCH_HOLD_FILE
HOLD_PROFILE=${HOLD_PROFILE:-anthropic-1}
MAX_S=${MAX_S:-10800}; start=$(date +%s)
while [ $(( $(date +%s) - start )) -lt "$MAX_S" ]; do
  [ -e "$HOLD" ] || { echo "$(date -u +%T) hold already removed by someone else; exiting"; exit 0; }
  prof=$(caam status claude 2>/dev/null | awk '$1=="claude"{print $2; exit}')
  if [ -n "$prof" ] && [ "$prof" != "$HOLD_PROFILE" ]; then
    rm -f "$HOLD"; echo "$(date -u +%T) caam active claude profile is now $prof (not $HOLD_PROFILE): hold REMOVED, launches release"; exit 0
  fi
  echo "$(date -u +%T) caam active claude profile=${prof:-unreadable}: hold stays"
  sleep 60
done
echo "$(date -u +%T) gave up after ${MAX_S}s with the profile still $HOLD_PROFILE or unreadable: hold LEFT IN PLACE"; exit 3
