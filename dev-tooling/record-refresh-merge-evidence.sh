#!/usr/bin/env bash
set -euo pipefail

# Both Git merge's pre-merge-commit hook and `git commit` after a resolved
# merge retain MERGE_HEAD. Only the workflow marks those factory refreshes, so
# this token never changes ordinary developer merge behavior.
if [[ "${LIVESPEC_FACTORY_REFRESH_MERGE:-}" != "true" ]] \
    || ! [[ -f "$(git rev-parse --git-path MERGE_HEAD)" ]]; then
    exit 0
fi

output_checksum="$(uv run --no-sync python -c '
from pathlib import Path
from livespec_dev_tooling.checks._red_green_replay_suite import canonical_output_checksum
import sys
print(canonical_output_checksum(output=Path(sys.argv[1]).read_text(encoding="utf-8")))
' "$1")"
tree_hash="$(git write-tree)"
uv run --no-sync python -m livespec_dev_tooling.green_token write-pre-commit \
    "factory-refresh-merge:${tree_hash}" "$output_checksum"
