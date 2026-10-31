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

started_at="$(python3 -c 'import time; print(time.monotonic())')"
if output="$(CAPTURE_SERVER_FAIL_STATUS=23 \
    CAPTURE_SERVER_FAIL_STDERR='synthetic capture startup failure' \
    bash "$HARNESS" 2>&1)"; then
    echo "FAIL: a failed capture server did not fail the harness" >&2
    exit 1
fi
elapsed="$(python3 - "$started_at" <<'PY'
import sys
import time

print(time.monotonic() - float(sys.argv[1]))
PY
)"
if printf '%s\n' "$output" \
        | grep -qF 'telemetry: capture server did not start (9.1): exit status 23; stderr=synthetic capture startup failure' \
        && python3 - "$elapsed" <<'PY'
import sys

assert float(sys.argv[1]) < 5.0, sys.argv[1]
PY
then
    printf '%s\n' "ok: failed capture server names its exit status and stderr (${elapsed}s)"
else
    printf '%s\n' "$output" >&2
    echo "FAIL: failed capture-server diagnostic was incomplete or delayed (${elapsed}s)" >&2
    exit 1
fi
