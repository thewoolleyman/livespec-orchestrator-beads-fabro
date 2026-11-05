#!/usr/bin/env bash
# Route a refused command commit only after its policy recorder reserved a budget.

set -euo pipefail

node="${1:?commit node name required}"
authorized="$(git rev-parse --git-path "livespec-commit-${node}-reentry-authorized")"
cause_path="$(git rev-parse --git-path livespec-stage-cause)"

if test -s "$authorized"; then
    kind="$(cat "$authorized")"
    rm -f "$authorized"
    echo "LIVESPEC_COMMIT_${kind^^}_REENTRY: $node commit refusal reserved its $kind re-entry" >&2
    exit 0
fi

if test -s "$cause_path"; then
    sed -n 's/^cause: //p' "$cause_path" >&2
else
    echo "LIVESPEC_COMMIT_REENTRY_UNAUTHORIZED: $node commit refusal did not reserve a re-entry" >&2
fi
exit 1
