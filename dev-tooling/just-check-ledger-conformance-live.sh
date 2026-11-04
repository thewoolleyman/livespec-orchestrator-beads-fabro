#!/usr/bin/env bash
# Deliberately omit errexit: a non-zero live ledger gate can be a fail-soft
# could-not-check path, and this wrapper must inspect the marker before blocking.
set -uo pipefail

if [[ ! -f .beads/config.yaml ]]; then
    echo ":: check-ledger-conformance-live: no .beads/config.yaml (repo has no tenant); skipping"
    exit 0
fi
# STATUS LINE FIRST, ARGV TOKENS AFTER. `resolve_credential_wrapper` returns an
# IOResult so that an UNREADABLE `.livespec.jsonc` is distinguishable from a repo
# that legitimately configures no wrapper. Both still SKIP — see the fail-soft
# contract in the justfile; this recipe runs on EVERY push and a false-fail would
# brick them all — but they are no longer REPORTED as the same thing.
#
# ⛔ THE OLD LINE DISCARDED THE DISTINCTION EVEN WHEN PYTHON HAD IT: `2>/dev/null`
# plus a bare empty-array fallback mapped every failure onto "no wrapper". That is
# why fixing the Python alone would have changed nothing observable.
mapfile -t probe < <(uv run python -c 'import sys; sys.path.insert(0, ".claude-plugin/scripts"); from pathlib import Path; from returns.io import IOFailure; from returns.unsafe import unsafe_perform_io; from livespec_orchestrator_beads_fabro.commands._config_credential_wrapper import resolve_credential_wrapper; o = resolve_credential_wrapper(cwd=Path(".")); print("UNREADABLE") if isinstance(o, IOFailure) else print("\n".join(["OK", *unsafe_perform_io(o.unwrap())]))' 2>/dev/null)
status="${probe[0]-PROBE_FAILED}"
wrapper=("${probe[@]:1}")
if [[ $status == "UNREADABLE" ]]; then
    echo ":: check-ledger-conformance-live: .livespec.jsonc EXISTS but cannot be read as a configuration object; skipping (fail-soft)"
    echo ":: check-ledger-conformance-live: ⚠️  THE PRE-PUSH LEDGER GATE IS OFF until that file parses — this is NOT 'no wrapper configured', it is a broken config"
    exit 0
fi
if [[ $status != "OK" ]]; then
    echo ":: check-ledger-conformance-live: could not probe credential_wrapper (config reader unavailable); skipping (fail-soft)"
    exit 0
fi
if [[ ${#wrapper[@]} -eq 0 ]]; then
    echo ":: check-ledger-conformance-live: no credential_wrapper configured; skipping (fail-soft)"
    exit 0
fi
out=$("${wrapper[@]}" python3 .claude-plugin/scripts/bin/dispatcher.py ledger-normalize --project-root . --gate 2>&1)
rc=$?
printf '%s\n' "$out"
if [[ $rc -eq 1 ]] && grep -q 'LIVESPEC_LEDGER_GATE: DRIFT' <<<"$out"; then
    echo ":: check-ledger-conformance-live: RESIDUAL out-of-lifecycle work-item status needs a human lane decision; blocking push (set each to a lifecycle status per the message above, then re-push)"
    exit 1
fi
echo ":: check-ledger-conformance-live: no residual drift (gate exit $rc); allowing push (any safe transient drift was auto-healed in place and printed above; a tenant it could not verify is SKIPPED, never blocked)"
exit 0
