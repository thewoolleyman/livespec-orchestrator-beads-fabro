#!/usr/bin/env bash
set -euo pipefail

if [[ "${LIVESPEC_CI_LANE:-local}" == "hosted" ]]; then
    printf '%s\n' "auto"
    exit 0
fi
if [[ -n "${LIVESPEC_TEST_PARALLELISM:-}" ]]; then
    printf '%s\n' "$LIVESPEC_TEST_PARALLELISM"
    exit 0
fi
# nproc honours process affinity but does not account for a cgroup CPU quota.
cpu_max=$(cat /sys/fs/cgroup/cpu.max 2>/dev/null || true)
if [[ "$cpu_max" =~ ^([1-9][0-9]*)[[:space:]]+([1-9][0-9]*)$ ]]; then
    cores=$((BASH_REMATCH[1] / BASH_REMATCH[2]))
else
    cores=$(nproc 2>/dev/null || echo 4)
fi
workers=$((cores / 4))
if [[ "$workers" -lt 1 ]]; then
    workers=1
fi
printf '%s\n' "$workers"
