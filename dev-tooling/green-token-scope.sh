#!/usr/bin/env bash
# A green token is a tree verdict, not an unconditional cache entry. The shared
# utility records only `tree_hash`; this adapter stores the excluded targets too.
# Its `scope` operation is the one declaration both the janitor and pre-push use
# for targets their respective aggregate paths intentionally omit.
#
# TWO WRITERS leave a token in this file, and `check` reads both. The local
# aggregate writes this adapter's scoped format (`skipped_targets`). A DELEGATED
# cluster gate pass writes the shared library's format through livespec-dev-tooling's
# `gate_remote_verdict` (`tree_hash`, `mode: normal`, `scope: full-suite`, no
# `skipped_targets`), and that pass also overwrites a scoped token left on the same
# tree. The cluster gate runs this repository's own pre-push suite, which omits
# only the same-repository live picker and runs the members that read state outside
# the tree on the pushing host, so the library token vouches for the tree-pure
# members except the picker. `check` therefore accepts it for the tree it names,
# when the caller's own scope omits that picker, and `delegated` tells the caller
# which of the two it matched so that pre-push can still run every member that
# reads state outside the tree. Pre-commit evidence shares the library format but
# names its own aggregate run (`pre_commit_aggregate`) and is never a gate pass.
set -euo pipefail

operation=${1:-}
if [[ "$operation" != write && "$operation" != check && "$operation" != scope && "$operation" != delegated ]]; then
    exit 2
fi
shift

if [[ "$operation" == scope ]]; then
    [[ "$#" -eq 0 ]] || exit 2
    # Pre-push always omits the same-repository live picker acceptance. A
    # sandbox additionally omits the environmental master-CI check.
    printf '%s\n' check-codex-skill-picker
    if [[ "$(git config --get --bool livespec.sandboxExempt || printf 'false')" == true ]]; then
        printf '%s\n' check-master-ci-green
    fi
    exit 0
fi

targets=("$@")
for target in "${targets[@]}"; do
    [[ "$target" =~ ^[a-z0-9][a-z0-9-]*$ ]] || exit 2
done
if [[ ${#targets[@]} -gt 0 ]] && [[ $(printf '%s\n' "${targets[@]}" | LC_ALL=C sort -u | wc -l) -ne ${#targets[@]} ]]; then
    exit 2
fi

git_dir=$(git rev-parse --absolute-git-dir)
tree_hash=$(git rev-parse 'HEAD^{tree}')
token_path="${git_dir}/livespec-green-token.json"

if [[ "$operation" == write ]]; then
    python3 - "$token_path" "$tree_hash" "${targets[@]}" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
path.write_text(json.dumps({"tree_hash": sys.argv[2], "skipped_targets": sys.argv[3:]}), encoding="utf-8")
PY
    exit 0
fi

[[ -z $(git status --porcelain) ]] || exit 1
python3 - "$token_path" "$tree_hash" "$operation" "${targets[@]}" <<'PY'
import json
import pathlib
import sys

PICKER = "check-codex-skill-picker"
try:
    token = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
except (OSError, ValueError):
    raise SystemExit(1)
if not isinstance(token, dict) or token.get("tree_hash") != sys.argv[2]:
    raise SystemExit(1)
requested = sys.argv[4:]
stored = token.get("skipped_targets")
if stored is None:
    # The shared library's token, as a delegated cluster gate pass writes it.
    if (
        token.get("mode") != "normal"
        or token.get("scope") != "full-suite"
        or "pre_commit_aggregate" in token
        or PICKER not in requested
    ):
        raise SystemExit(1)
    raise SystemExit(0)
if sys.argv[3] == "delegated":
    raise SystemExit(1)
if (
    not isinstance(stored, list)
    or not all(isinstance(one, str) for one in stored)
    or len(stored) != len(set(stored))
    or set(stored) != set(requested)
):
    raise SystemExit(1)
PY
