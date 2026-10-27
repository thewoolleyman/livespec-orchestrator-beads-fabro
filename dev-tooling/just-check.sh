#!/usr/bin/env bash
# Deliberately omit errexit so the aggregate reports every failing target before
# exiting non-zero.
set -uo pipefail

skip_targets=("$@")

# The executed list is DERIVED from the justfile `check:` recipe's
# `targets=(...)` array — the same declaration the shared
# `aggregate_completeness` gate certifies. A hardcoded copy used to live here
# and diverged by ten slugs, so the gate certified one list while this runner
# executed another (work-item bd-ib-mxqrr4); never reintroduce one. Derived
# BEFORE `uv sync` so a broken declaration fails fast on its own error rather
# than behind an environment step.
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if ! targets_text="$(bash "${script_dir}/aggregate-targets.sh")"; then
    echo "ERROR: could not derive the aggregate target list from the justfile" >&2
    exit 1
fi
mapfile -t targets <<<"$targets_text"

if ! uv sync --all-groups; then
    echo "ERROR: up-front 'uv sync --all-groups' failed; aborting the check aggregate" >&2
    exit 1
fi
export UV_NO_SYNC=1

# Four aggregate lanes leave room for the single pytest lane's configured
# LIVESPEC_TEST_PARALLELISM workers while still running static targets beside it.
if ! uv run python -m livespec_dev_tooling.parallel_check_dispatcher \
    --workers 4 --skip "${skip_targets[*]}" -- "${targets[@]}"; then
    exit 1
fi
if [[ ${#skip_targets[@]} -eq 0 ]]; then
    uv run python -m livespec_dev_tooling.green_token write || true
fi
