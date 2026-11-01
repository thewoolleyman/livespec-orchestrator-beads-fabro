#!/usr/bin/env bash
#
# Return a rejected Red/Green lap to the dispatch base. This is deliberately the
# only location that performs the destructive reset: callers supply the
# configured default branch, while this wrapper pins the remote tracking ref
# and the cleanup flags.

set -euo pipefail

if (( $# != 1 )); then
    echo "usage: $0 <default-branch>" >&2
    exit 2
fi

readonly default_branch="$1"

case "$default_branch" in
    "" | *[!A-Za-z0-9._/-]*)
        echo "dispatch base branch is not a safe ref name: $default_branch" >&2
        exit 2
        ;;
esac

git reset --hard "origin/$default_branch"
git clean -fd
