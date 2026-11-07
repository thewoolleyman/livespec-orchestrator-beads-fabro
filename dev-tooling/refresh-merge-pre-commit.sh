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

bash dev-tooling/record-refresh-merge-evidence.sh "$output_file"
