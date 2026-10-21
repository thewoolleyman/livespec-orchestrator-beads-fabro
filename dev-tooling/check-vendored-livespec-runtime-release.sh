#!/usr/bin/env bash
# Verify the livespec-runtime vendor carve-outs against its pinned upstream tag.
set -euo pipefail

readonly upstream_url='https://github.com/thewoolleyman/livespec-runtime.git'
readonly upstream_ref='v0.28.0'
readonly vendor_root='.claude-plugin/scripts/_vendor/livespec_runtime'

scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

GIT_TERMINAL_PROMPT=0 git -c advice.detachedHead=false clone --quiet \
    --branch "$upstream_ref" --depth 1 \
    "$upstream_url" "$scratch/upstream"
cp -a "$vendor_root" "$scratch/vendored"
rm -f "$scratch/vendored/LICENSE"

python3 - "$scratch/upstream/livespec_runtime/work_items/types.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old_docstring = '''    substrate. `False` is the legacy/default value.
    \"\"\"
'''
new_docstring = '''    substrate. `False` is the legacy/default value. `rework_pending: bool =
    False` is the same shape, backed by the `rework:pending` beads label.
    \"\"\"
'''
old_field = "    awaits_scope_override: bool = False\n"
new_field = old_field + "    rework_pending: bool = False\n"

if text.count(old_docstring) != 1 or text.count(old_field) != 1:
    raise SystemExit("upstream WorkItem carve-out anchors changed")

path.write_text(
    text.replace(old_docstring, new_docstring).replace(old_field, new_field),
    encoding="utf-8",
)
PY

if ! diff -ru --exclude='__pycache__' "$scratch/upstream/livespec_runtime" \
    "$scratch/vendored"; then
    printf '%s\n' 'vendored livespec-runtime differs from v0.28.0 beyond the approved carve-outs' >&2
    exit 1
fi

printf 'upstream_ref=%s\n' "$upstream_ref"
printf 'upstream_commit=%s\n' "$(git -C "$scratch/upstream" rev-parse HEAD)"
printf '%s\n' 'vendored-tree-release-comparison=passed'
