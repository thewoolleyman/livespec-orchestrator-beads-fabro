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

# `kill -0` can be refused for a live child by a container signal policy. The
# BASH_ENV shim reproduces that result while the real capture child publishes
# its port after 2.1 seconds. The harness must use its own job state, keep
# polling, and complete the telemetry case.
liveness_probe_env="$(mktemp)"
trap 'rm -f "$liveness_probe_env"' EXIT
cat >"$liveness_probe_env" <<'PROBE_ENV'
if [ "${CAPTURE_LIVENESS_PROBE_DENIED:-}" = 1 ]; then
    kill() {
        if [ "$1" = "-0" ]; then
            return 1
        fi
        builtin kill "$@"
    }
fi
PROBE_ENV
if output="$(CAPTURE_LIVENESS_PROBE_DENIED=1 \
    BASH_ENV="$liveness_probe_env" \
    CAPTURE_START_DELAY_SECONDS=2.1 \
    bash "$HARNESS" 2>&1)" \
        && grep -qF 'telemetry: bd.invoke span emitted' <<<"$output"; then
    printf '%s\n' 'ok: denied capture liveness probe keeps polling for the port'
else
    printf '%s\n' "$output" >&2
    echo "FAIL: denied capture liveness probe was treated as a capture-server exit" >&2
    exit 1
fi

# A capture server that ignores the stop signal must make the harness report a
# failed telemetry case after its own stop bound.  The server exits shortly
# after that bound so this regression leaves no process behind; the assertion
# observes the harness diagnostic rather than timing the host.
if output="$(CAPTURE_SERVER_IGNORE_STOP=1 \
    CAPTURE_SERVER_EXIT_AFTER_SECONDS=10.5 \
    bash "$HARNESS" 2>&1)"; then
    printf '%s\n' "$output" >&2
    echo "FAIL: an unstoppable capture server did not fail the harness" >&2
    exit 1
fi
if grep -qF 'telemetry: capture server still running after its stop (10-second bound)' <<<"$output"; then
    printf '%s\n' 'ok: unstoppable capture server is named after the stop bound'
else
    printf '%s\n' "$output" >&2
    echo "FAIL: unstoppable capture-server diagnostic was missing" >&2
    exit 1
fi

# The failed-server diagnostic is bounded on an EVENT, not on host speed: the
# harness names the server's exit status only when start_capture observed the
# process exit BEFORE its own 30-second startup bound (600 polls of 0.05 s);
# reaching that bound instead reports "still running at 30-second bound".
# Timing the whole harness run measured host load (8-26 s under load), not the
# startup contract, so no wall-clock assertion is made here.
if output="$(CAPTURE_SERVER_FAIL_STATUS=23 \
    CAPTURE_SERVER_FAIL_STDERR='synthetic capture startup failure' \
    bash "$HARNESS" 2>&1)"; then
    echo "FAIL: a failed capture server did not fail the harness" >&2
    exit 1
fi
if grep -qF 'telemetry: capture server did not start (9.1): exit status 23; stderr=synthetic capture startup failure' <<<"$output" \
        && ! grep -qF 'still running at 30-second bound' <<<"$output"; then
    printf '%s\n' "ok: failed capture server names its exit status and stderr before the 30-second startup bound"
else
    printf '%s\n' "$output" >&2
    echo "FAIL: failed capture-server diagnostic was incomplete or reached the 30-second startup bound" >&2
    exit 1
fi
