#!/usr/bin/env bash
# fresh-clone-setup-gate.sh — the ADOPTION gate for a livespec-dev-tooling release.
#
# WHY THIS EXISTS. On 2026-07-26 dev-tooling v0.54.24 made an absent
# worktree-discipline pack a FAIL by default. The pack is gitignored by design,
# so it exists only after `just bootstrap` — and the Fabro sandbox is a fresh
# FULL clone that runs the conformance verifiers as SETUP steps, before
# bootstrap. Every ImplementWorkItem dispatch in this repo then died ~24s in,
# before any agent work, and the pin was reverted to v0.54.19 to recover
# (`a26228c`). Upstream fix: livespec-dev-tooling `5550a93`, released v0.54.25.
#
# WHY `just check` COULD NOT SEE IT. Both auto-bump automations
# (`pin-freshness.yml`'s cron and `bump-pin-from-dispatch.yml` on
# `sibling-released`) open AUTO-MERGE PRs gated on `just check`, which runs on
# the BOOTSTRAPPED primary checkout — where these verifiers have always passed.
# A broken factory and a healthy one were indistinguishable from where that gate
# stood, which is exactly how v0.54.24 merged green while taking every dispatch
# down. This gate closes that: it exercises the verifiers in the ORDER and the
# TREE STATE the sandbox actually uses.
#
# WHAT IT DOES. Replays the dispatch workflow's own conformance setup steps
# against a FRESH, UN-BOOTSTRAPPED clone of this repo. The steps are READ FROM
# `workflow.toml` rather than duplicated here, so a new or reordered setup step
# is picked up automatically instead of silently escaping the gate.
#
# HOW A STEP IS READ SINCE THE TYPED-WORKFLOW-INPUTS CARRIER (C5-payload, plan
# bd-ib-vblnq2). The committed prepare steps no longer spell the conformance
# commands: each reads an `inputs.<name>` token that the Dispatcher renders
# from the governed repository's RESOLVED integration contract
# (SPECIFICATION/contracts.md §"Repository integration contract"). This gate
# therefore does what the Dispatcher does — it resolves THIS repository's
# contract from its own `.livespec.jsonc` through the plugin's own resolver and
# projection, substitutes the rendered value for every token, and replays the
# resulting command. Rendering through the same code path the dispatch uses is
# what keeps the gate honest: a step is replayed exactly as a sandbox would run
# it, and a token the projection cannot render fails loudly here instead of
# reaching a dispatch as a literal.
#
# WHAT IT DELIBERATELY DOES NOT DO. It does not `uv sync` the throwaway clone:
# the property under test is that the tree is UN-BOOTSTRAPPED, not that the venv
# is fresh, and a per-run sync would add minutes and a network dependency for no
# signal. It runs the verifiers from THIS repo's already-synced venv — i.e. from
# the dev-tooling version this repo PINS, which is precisely the version whose
# adoption is being gated.
#
# INJECTED-DEFECT PROOF (recorded 2026-07-26, run against real throwaway trees):
# with the venv pinned to v0.54.24 this gate FAILS on `worktree_pack_absent`
# even with the sandbox exemption declared; on v0.54.26 it PASSES; and with the
# exemption withheld v0.54.26 still FAILS, so the required-default for ordinary
# checkouts is intact in both directions.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
WORKFLOW="$REPO_ROOT/.claude-plugin/.fabro/workflows/implement-work-item/workflow.toml"
CONFIG="$REPO_ROOT/.livespec.jsonc"

# The steps this gate replays: everything in the prepare graph that installs or
# verifies livespec conformance, plus the declared sandbox-exemption marker the
# verifiers read. Selecting by CONTENT — the integration-contract token each
# step reads, not a hardcoded step name — is what makes a newly added
# conformance premise gated automatically.
_SELECT='inputs\.(conformance_[a-z_]+|sandbox_exempt_marker)'
# A format change or a wholesale step removal must fail LOUDLY rather than
# silently reduce this gate to a no-op. Today the workflow carries four matching
# steps (hook install, exemption marker, verifier #1, verifier #2).
_MIN_STEPS=3

fail() { echo ":: fresh-clone-setup-gate: FAIL — $*" >&2; exit 1; }

[ -f "$WORKFLOW" ] || fail "workflow not found at $WORKFLOW"
[ -f "$CONFIG" ] || fail "integration-contract declaration not found at $CONFIG"

# The interpreter the pinned dev-tooling is installed into. `uv run` in the
# throwaway clone would resolve THAT clone's project, so resolve it here, once,
# against the primary.
PY="$REPO_ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
    # `just check` syncs once up front, so the venv normally exists by the time
    # this runs. A bare invocation may not have one; ask uv where its
    # interpreter is rather than skipping, because a skip here reads as a pass.
    PY="$(cd "$REPO_ROOT" && uv run python -c 'import sys; print(sys.executable)' 2>/dev/null)"
fi
if [ -z "${PY:-}" ] || [ ! -x "$PY" ]; then
    fail "could not resolve the project interpreter (no .venv and 'uv run' failed).
       This gate must not skip: a skip is indistinguishable from a pass, which is
       the exact failure mode it exists to close."
fi

# Render the conformance steps exactly as a dispatch would: select each
# `script = "..."` line that reads a conformance token, resolve this
# repository's contract, substitute every `inputs.<name>` token with the value
# the Dispatcher's projection renders, and unescape the TOML basic-string
# quoting so the bare shell command remains. One rendered command per line; a
# token the projection does not render is a hard failure, never a literal.
mapfile -t STEPS < <(
    "$PY" - "$WORKFLOW" "$CONFIG" "$_SELECT" "$REPO_ROOT" <<'PYRENDER'
import re
import sys
from pathlib import Path

workflow, config, select, repo_root = sys.argv[1:5]
scripts = Path(repo_root) / ".claude-plugin" / "scripts"
sys.path[:0] = [str(scripts), str(scripts / "_vendor")]

from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    contract_prompt_variables,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan_build import (
    resolve_repo_integration_contract,
)

resolved = resolve_repo_integration_contract(
    config_text=Path(config).read_text(encoding="utf-8"), default_branch=None
)
values = contract_prompt_variables(resolved=resolved)
token = re.compile(r"\{\{\s*inputs\.(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
selector = re.compile(select)
for line in Path(workflow).read_text(encoding="utf-8").splitlines():
    if not line.startswith('script = "') or selector.search(line) is None:
        continue
    body = line[len('script = "') : -1].replace('\\"', '"')
    rendered = token.sub(lambda match: values[match.group("name")], body)
    sys.stdout.write(rendered + "\n")
PYRENDER
)

if [ "${#STEPS[@]}" -lt "$_MIN_STEPS" ]; then
    fail "found ${#STEPS[@]} conformance setup step(s) in workflow.toml, expected >= $_MIN_STEPS.
       Either the \`script = \"...\"\` format changed, the steps stopped reading
       their integration-contract tokens, or setup steps were removed.
       This gate must never silently degrade to a no-op — fix the selector or the workflow."
fi

for step in "${STEPS[@]}"; do
    case "$step" in
        *'{{'*) fail "a conformance setup step still carries an unrendered token: $step" ;;
    esac
done

CLONE="$(mktemp -d -t fresh-clone-setup-gate.XXXXXX)"
cleanup() { rm -rf "$CLONE"; }
trap cleanup EXIT

# `--no-hardlinks` because /tmp is frequently a different device than the repo;
# `--local` keeps it off the network. The result is exactly what the sandbox
# gets: every TRACKED file, and none of the gitignored pack.
if ! git clone --quiet --no-hardlinks --local "$REPO_ROOT" "$CLONE/repo" 2>/dev/null; then
    fail "could not create the throwaway clone"
fi

if [ -e "$CLONE/repo/dev-tooling/worktree-lib.sh" ]; then
    fail "the throwaway clone already carries the worktree pack, so it is NOT a
       fresh un-bootstrapped tree and this gate would prove nothing. Is
       dev-tooling/worktree-lib.sh tracked when it should be gitignored?"
fi

echo ":: fresh-clone-setup-gate: replaying ${#STEPS[@]} conformance setup step(s) from workflow.toml"
echo ":: fresh-clone-setup-gate: fresh un-bootstrapped clone at $CLONE/repo"

for step in "${STEPS[@]}"; do
    # `uv run python` would resolve the throwaway clone as its project; use the
    # primary's synced interpreter, which carries the PINNED dev-tooling.
    cmd="${step/uv run python/$PY}"
    echo ":: fresh-clone-setup-gate:   \$ $cmd"
    if ! ( cd "$CLONE/repo" && eval "$cmd" ); then
        fail "setup step exited non-zero in a fresh clone:
         $cmd
       This is the shape that took the factory down: the dispatch gate runs
       these steps on an UN-BOOTSTRAPPED tree, so a release that cannot satisfy
       them there breaks every dispatch before any agent work. Do NOT adopt this
       dev-tooling release, and do NOT skip this gate."
    fi
done

echo ":: fresh-clone-setup-gate: OK — every conformance setup step passes on a fresh clone"
