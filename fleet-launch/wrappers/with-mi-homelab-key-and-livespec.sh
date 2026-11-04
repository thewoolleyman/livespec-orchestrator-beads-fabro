#!/usr/bin/env bash
# PROVISIONAL / EXPERIMENTAL — part of fleet-launch/, a stopgap whose first-class
# replacements are the livespec console application and the committed launch-loop
# tool bd-ib-jr6w7v (see fleet-launch/README.md).
#
# Runs a livespec-dev-tooling just recipe with homelab's org App key bound (hl param run,
# OUTER: it scrubs the environment) and the livespec family wrapper INNER.
# Usage: with-mi-homelab-key-and-livespec.sh <repo-dir> <just-recipe-args...>
set -euo pipefail
FLEET_LAUNCH_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=fleet-launch/config.sh
. "$FLEET_LAUNCH_DIR/config.sh"
cd "$1"; shift
exec "$FLEET_LAUNCH_HOMELAB_AWS_WRAPPER" --role homelab-workload "$FLEET_LAUNCH_HL_CLI" param run \
  --bind MI_HOMELAB_GITHUB_PRIVATE_KEY=/homelab/v1/providers/github/mi-homelab-factory-bot/private-key -- \
  "$FLEET_LAUNCH_DEFAULT_WRAPPER" -- /usr/bin/mise exec -- just "$@"
