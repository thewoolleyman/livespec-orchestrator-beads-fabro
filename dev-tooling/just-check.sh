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

failed=()
executed=0
skipped=0
for target in "${targets[@]}"; do
    skip_this=0
    for skip_target in "${skip_targets[@]}"; do
        if [[ "$target" == "$skip_target" ]]; then
            skip_this=1
            break
        fi
    done
    if [[ "$skip_this" -eq 1 ]]; then
        printf '\n::: just %s (skipped)\n' "$target"
        skipped=$((skipped + 1))
        continue
    fi
    printf '\n::: just %s\n' "$target"
    executed=$((executed + 1))
    if ! just "$target"; then
        failed+=("$target")
    fi
done

if [[ ${#failed[@]} -gt 0 ]]; then
    printf '\nFailed targets (%d):\n' "${#failed[@]}"
    printf '  - %s\n' "${failed[@]}"
    exit 1
fi
# The count is what RAN, never the declared length: a summary that counts
# targets it skipped — or ones a stale hardcoded list named and never
# invoked — reads as broader assurance than the run earned, which is the
# false green this script's derivation removes (work-item bd-ib-mxqrr4). The
# skipped tally is printed rather than merely subtracted, so a short count is
# legible instead of mysterious.
if [[ "$skipped" -gt 0 ]]; then
    printf '\nAll %d targets passed (%d of %d declared skipped).\n' \
        "$executed" "$skipped" "${#targets[@]}"
else
    printf '\nAll %d targets passed.\n' "$executed"
fi
if [[ ${#skip_targets[@]} -eq 0 ]]; then
    uv run python -m livespec_dev_tooling.green_token write || true
fi
