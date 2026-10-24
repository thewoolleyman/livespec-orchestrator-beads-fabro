#!/usr/bin/env bash
# PROVISIONAL / EXPERIMENTAL — part of fleet-launch/, a stopgap whose first-class
# replacements are the livespec console application and the committed launch-loop
# tool bd-ib-jr6w7v (see fleet-launch/README.md).
#
# Runs a command under homelab's committed credential wrapper, whose argv (parameter-store
# PATHS, not secret values) is in homelab-wrapper.argv beside this file. It keeps PATH.
# Usage: with-homelab-wrapper-keep-path.sh -- <command...>
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
[ "${1:-}" = "--" ] && shift
mapfile -t W < "$HERE/homelab-wrapper.argv"
exec "${W[@]}" env PATH="$PATH" "$@"
