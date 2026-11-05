#!/usr/bin/env bash
# Structural regression checks for the Scenario 297 harness's fast, bounded
# state polling. The harness itself supplies the behavioural FIFO checks.

set -euo pipefail

harness="$(cd -- "$(dirname -- "$0")" && pwd -P)/run-tests.sh"

require_line() {
    local expected="$1"
    if ! grep -qxF -- "$expected" "$harness"; then
        printf 'missing Scenario 297 polling configuration: %s\n' "$expected" >&2
        exit 1
    fi
}

function_body() {
    sed -n "/^$1() {/,/^}/p" "$harness"
}

require_fast_bounded_poll() {
    local name="$1" body
    body="$(function_body "$name")"
    if ! grep -qF 'sleep "$HARNESS_POLL_S"' <<<"$body" \
        || ! grep -qF 'deadline=$(( $(date +%s) + limit ))' <<<"$body"; then
        printf '%s does not use the bounded Scenario 297 state poll\n' "$name" >&2
        exit 1
    fi
}

require_line '    export FLEET_LAUNCH_POLL_S=0.01'
require_line '    export FLEET_LAUNCH_MUTEX_POLL_S=0.01'
require_line '    export FLEET_LAUNCH_LISTING_POLL_S=0.01'
require_fast_bounded_poll wait_for_preflight
require_fast_bounded_poll await_both
require_fast_bounded_poll wait_for_line

preflight_stub="$(sed -n '/dod-preflight.sh)/,/^[[:space:]]*;;/p' "$harness")"
if ! grep -qF 'sleep "$HARNESS_POLL_S"' <<<"$preflight_stub" \
    || ! grep -qF 'deadline=$(( $(date +%s) + STUB_PREFLIGHT_SLOW_S ))' <<<"$preflight_stub"; then
    printf 'the held preflight does not use the bounded Scenario 297 state poll\n' >&2
    exit 1
fi
