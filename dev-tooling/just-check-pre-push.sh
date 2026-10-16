#!/usr/bin/env bash
set -euo pipefail

# A DELETE-ONLY PUSH publishes no tree, so there is nothing for any gate below
# to judge (work-item bd-ib-qy5wol.1, porting livespec-dev-tooling-r4oj47, which
# fixed only that repo's own copy; the rule is ratified in this repository's
# SPECIFICATION/constraints.md section "Pre-push gate refinements" at v151 and
# exercised by Scenario 188). git feeds the pre-push hook one `<local ref>
# <local oid> <remote ref> <remote oid>` line per ref update on standard input
# and spells a deletion as an ALL-ZERO local oid. Read unread, those lines made
# a pure `git push origin :<branch>` run the same aggregate a publish runs,
# against whatever happened to be checked out — a tree unrelated to the ref
# being removed. Measured 2026-10-16: the Dispatcher's post-run source-branch
# delete ran check-pre-push, check-skipping, check-per-file-coverage and pytest
# on the factory host, and because the Dispatcher holds the item's ownership
# lock until the push returns, a needs-human recovery could not resume for 60
# to 100 minutes under load.
#
# This is NOT a change-class subset. Such a branch runs FEWER checks over a tree
# it is still PUBLISHING, and it fails by PASSING — this fleet has shipped that
# hole once. Here nothing is published, so there is no weaker verdict to issue:
# the gate is not narrowed, it is inapplicable. And the discrimination is keyed
# on the refs git itself names, not on a change class read off the working tree,
# so there is no predicate that can rot into a subset.
#
# Fail-CLOSED on emptiness: no input is no EVIDENCE, not "nothing to publish".
# A hand-run `just check-pre-push`, a lefthook build that does not forward
# standard input, or any future transport that stops naming refs all arrive as
# emptiness, and reading that as a delete-only push would skip the gate on every
# push. Likewise a line whose oid field is missing or unparseable counts as a
# ref update, so a shape this loop does not understand still gates.
#
# The `-t 0` guard is load-bearing in the other direction: lefthook forwards the
# hook's standard input only to a command declaring `use_stdin: true` (the
# `01-check-pre-push` entry does, and `just` passes its own standard input
# through to this script), while a `just check-pre-push` run by hand from a
# terminal has no refs to read at all — reading it there would block on the tty
# forever rather than gate.
#
# The skip lives HERE, inside the `check-pre-push` recipe, and never at the
# lefthook level: `02-ledger-conformance` is a separate always-run pre-push step
# whose subject — the beads tenant's state — is not tree-derived, so it is owed
# on a deletion-only push too. A lefthook-level short-circuit would take it down
# with the aggregate.
push_refs=""
if [ ! -t 0 ]; then
    push_refs="$(cat)"
fi

ref_updates=0
deleted_refs=0
while IFS=' ' read -r local_ref local_oid _; do
    [ -n "${local_ref}" ] || continue
    ref_updates=$((ref_updates + 1))
    case "${local_oid}" in
        "" | *[!0]*) ;;
        *) deleted_refs=$((deleted_refs + 1)) ;;
    esac
done <<<"${push_refs}"

if [ "${ref_updates}" -gt 0 ] && [ "${ref_updates}" -eq "${deleted_refs}" ]; then
    echo ":: pre-push: skipping the gate - this push only deletes refs (${deleted_refs}), and a deletion publishes no tree to check"
    exit 0
fi

if uv run python -m livespec_dev_tooling.green_token check 2>&1; then
    echo ":: pre-push: green token matched - tree byte-identical to last green check; skipping full aggregate (CI is authoritative)"
    exit 0
fi
echo ":: pre-push: skipping same-repo live TUI picker gate; run just check-codex-skill-picker explicitly for live Codex picker acceptance"
just check-skipping check-codex-skill-picker
