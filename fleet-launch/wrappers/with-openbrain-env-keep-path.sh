#!/usr/bin/env bash
# PROVISIONAL / EXPERIMENTAL — part of fleet-launch/, a stopgap whose first-class
# replacements are the livespec console application and the committed launch-loop
# tool bd-ib-jr6w7v (see fleet-launch/README.md).
#
# Runs a command under openbrain's committed credential wrapper (pass as WRAPPER= to dispatch-dual.sh). It keeps the caller's PATH, which the underlying wrapper scrubs, so claude and mise stay reachable.
# Usage: with-openbrain-env-keep-path.sh -- <command...>
set -euo pipefail
FLEET_LAUNCH_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=fleet-launch/config.sh
. "$FLEET_LAUNCH_DIR/config.sh"
[ "${1:-}" = "--" ] && shift
exec "$FLEET_LAUNCH_OPENBRAIN_WRAPPER" -- env PATH="$PATH" "$@"
