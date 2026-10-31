#!/usr/bin/env bash
# Regression checks for the telemetry capture-server start contract.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd -P)"
HARNESS="${SCRIPT_DIR}/run-tests.sh"

if [ ! -x "$HARNESS" ]; then
    echo "test-capture-start.sh: harness not executable: $HARNESS" >&2
    exit 1
fi

started_at="$(python3 -c 'import time; print(time.monotonic())')"
if output="$(CAPTURE_START_DELAY_SECONDS=2.1 bash "$HARNESS" 2>&1)"; then
    elapsed="$(python3 - "$started_at" <<'PY'
import sys
import time

print(time.monotonic() - float(sys.argv[1]))
PY
)"
    if python3 - "$elapsed" <<'PY'
import sys

assert float(sys.argv[1]) >= 6.0, sys.argv[1]
PY
    then
        printf '%s\n' "ok: telemetry capture starts after a delay longer than two seconds (${elapsed}s)"
    else
        echo "FAIL: slow capture-server startup was not observed (${elapsed}s)" >&2
        exit 1
    fi
else
    printf '%s\n' "$output" >&2
    echo "FAIL: slow capture-server startup made the harness fail" >&2
    exit 1
fi
