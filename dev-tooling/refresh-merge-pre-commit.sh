#!/usr/bin/env bash
set -euo pipefail

# This hook is deliberately inert outside the scripted factory refresh. A
# regular developer merge keeps the ordinary hook behavior; the factory marks
# only its preserve-remote-ancestry merge because the following publication
# path already owes the refreshed tree one full aggregate.
if [[ "${LIVESPEC_FACTORY_REFRESH_MERGE:-}" != "true" ]]; then
    exit 0
fi

output_file="$(mktemp)"
cleanup() {
    rm -f "$output_file"
}
trap cleanup EXIT

# Git has prepared the merge index but not committed it. Running the aggregate
# here judges exactly the tree the merge commit will carry. The commit-msg hook
# consumes the evidence keyed by `git write-tree`, so it records replay
# trailers without running a second suite-green pytest invocation.
if ! just check >"$output_file" 2>&1; then
    cat "$output_file"
    exit 1
fi
cat "$output_file"

tree_hash="$(git write-tree)"
output_checksum="$(uv run --no-sync python -c '
from pathlib import Path
from livespec_dev_tooling.checks._red_green_replay_suite import canonical_output_checksum
import sys
print(canonical_output_checksum(output=Path(sys.argv[1]).read_text(encoding="utf-8")))
' "$output_file")"
uv run --no-sync python -m livespec_dev_tooling.green_token write-pre-commit \
    "factory-refresh-merge:${tree_hash}" "$output_checksum"
