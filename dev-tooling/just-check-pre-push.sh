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

# The DELEGATED-GATE fall-through (work-item bd-ib-idp5g7, a child of the
# livespec-dev-tooling plan `delegated-gate-fleet-rollout`; the contract is that
# repository's SPECIFICATION/contracts.md section "Delegated pre-push gate").
# This repository HAS opted in - `delegated_gate = true` in its own
# `[tool.livespec_dev_tooling]` block - so which branch a push takes is decided
# by the HOST, not by this file. A push from the VPS otherwise runs the whole
# aggregate below on the VPS, measured here at about 17 minutes; delegated, that
# same aggregate runs as a Job in the self-hosted k3s cluster's `gates`
# namespace and this push gates on its verdict.
#
# Only the FALL-THROUGH is ever replaced. The green-token skip above is
# untouched, because a delegated pass writes the SAME token through the SAME CLI
# a local aggregate does, so a byte-identical tree is skippable whichever path
# gated it. The deletion-only skip at the top of this file is untouched for a
# stronger reason still: it publishes no tree, so there is nothing for EITHER
# gate to judge.
#
# The probe's exit code is the whole answer, and it answers for THIS PUSH: the
# switch AND whether the pushing user can read the gates kubeconfig on this
# host. From the VPS, which holds the credential, that is 0 and the gate runs on
# the cluster; from a Fabro sandbox or a laptop it is non-zero and the probe
# itself prints that this push is gating locally. Every doubt it can have - an
# absent key, a `false`, a malformed pyproject, a traceback, no credential -
# exits non-zero and lands here, on the strict local path, which is the only
# direction in which a mistake is merely expensive rather than an ungated push.
# Nothing re-delegates inside the gate pod either: it holds no gates kubeconfig,
# so the `check-pre-push` the Job runs takes this same local fall-through.
#
# Once delegation IS selected, this is the last local branch, and the `exec` is
# what makes that so: a delegated run that reaches no verdict must REFUSE the
# push rather than fall through to the aggregate below. "We could not gate this"
# must never quietly become "we gated it some other way".
if uv run python -m livespec_dev_tooling.gate_remote_delegate enabled; then
    echo ":: pre-push: delegated gate is enabled for this repo; gating on the cluster"
    exec uv run python -m livespec_dev_tooling.gate_remote_delegate run
fi

echo ":: pre-push: skipping same-repo live TUI picker gate; run just check-codex-skill-picker explicitly for live Codex picker acceptance"
just check-skipping check-codex-skill-picker
