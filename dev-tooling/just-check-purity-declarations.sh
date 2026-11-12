#!/usr/bin/env bash
# Refuse an aggregate member whose purity declaration is missing.
set -euo pipefail

mapfile -t targets < <(bash dev-tooling/aggregate-targets.sh)
exec uv run python -m livespec_dev_tooling.green_token undeclared "${targets[@]}"
