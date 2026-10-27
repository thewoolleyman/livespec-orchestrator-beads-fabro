#!/usr/bin/env bash
# A green token is a tree verdict, not an unconditional cache entry. The shared
# utility records only `tree_hash`; this adapter stores the excluded targets too.
set -euo pipefail

operation=${1:-}
if [[ "$operation" != write && "$operation" != check ]]; then
    exit 2
fi
shift
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
python3 - "$token_path" "$tree_hash" "${targets[@]}" <<'PY'
import json
import pathlib
import sys

try:
    token = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
except (OSError, ValueError):
    raise SystemExit(1)
stored = token.get("skipped_targets") if isinstance(token, dict) else None
if not isinstance(stored, list) or not all(isinstance(one, str) for one in stored):
    raise SystemExit(1)
if (
    token.get("tree_hash") != sys.argv[2]
    or len(stored) != len(set(stored))
    or set(stored) != set(sys.argv[3:])
):
    raise SystemExit(1)
PY
