#!/usr/bin/env bash
# Print the `just check` aggregate's declared target list, one slug per line.
#
# The justfile `check:` recipe holds the aggregate's ONE declaration: the
# `targets=(...)` array that the shared `aggregate_completeness` gate parses to
# prove every canonical slug is wired. This script derives that same list for
# `just-check.sh` to EXECUTE, so the certified set and the executed set are one
# set by construction.
#
# They were two sets for eight weeks. `just-check.sh` carried its own hardcoded
# copy of the array and ignored the declaration, so ten declared slugs never ran
# under `just check`, pre-push or the in-run janitor gate, and
# `check-spec-governance-default-block` sat red on master for six weeks while
# gate runs reported `All 80 targets passed` against a 90-slug declaration
# (work-item bd-ib-mxqrr4).
#
# The parse mirrors the shared gate's rules exactly, so the two readings of one
# declaration cannot come to disagree: the `check:` recipe body runs to the next
# unindented line carrying a colon, the FIRST `targets=(` opens the array, a
# bare `)` closes it, and each line is comment-stripped, trimmed, and kept only
# when it starts with `check-`. An array that never closes, or one that yields
# no slug at all, is a hard failure rather than an empty list — a runner that
# silently executed nothing would print the same passing summary a fully green
# aggregate prints, which is the exact false green this script removes.
set -uo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
justfile="${repo_root}/justfile"

if [[ ! -f "$justfile" ]]; then
    echo "ERROR: no justfile at ${justfile}; cannot derive the aggregate target list" >&2
    exit 1
fi

if ! targets="$(
    awk '
        !seen_recipe && /^check:[[:space:]]*$/ { in_recipe = 1; seen_recipe = 1; next }
        in_recipe && /^[^[:space:]]/ && /:/ { in_recipe = 0 }
        in_recipe && !taken && !in_array && /^[[:space:]]*targets=\([[:space:]]*$/ {
            in_array = 1
            next
        }
        in_array && /^[[:space:]]*\)[[:space:]]*$/ { in_array = 0; taken = 1; next }
        in_array {
            sub(/#.*/, "")
            sub(/^[[:space:]]+/, "")
            sub(/[[:space:]]+$/, "")
            if ($0 ~ /^check-/) { print }
        }
        END { if (in_array) { exit 3 } }
    ' "$justfile"
)"; then
    echo "ERROR: the justfile \`check:\` recipe's targets=(...) array is unterminated" >&2
    exit 1
fi

if [[ -z "$targets" ]]; then
    echo "ERROR: the justfile \`check:\` recipe declares no check-* targets" >&2
    exit 1
fi

printf '%s\n' "$targets"
