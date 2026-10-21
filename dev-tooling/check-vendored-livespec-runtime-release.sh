#!/usr/bin/env bash
# Verify the livespec-runtime vendor carve-outs against its pinned upstream tag.
set -euo pipefail

readonly upstream_url='https://github.com/thewoolleyman/livespec-runtime.git'
readonly previous_upstream_ref='v0.27.0'
readonly upstream_ref='v0.28.0'
readonly vendor_root='.claude-plugin/scripts/_vendor/livespec_runtime'

scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

git init --quiet "$scratch/upstream"
git -C "$scratch/upstream" remote add origin "$upstream_url"
GIT_TERMINAL_PROMPT=0 git -C "$scratch/upstream" fetch --quiet --depth 1 origin \
    "refs/tags/$previous_upstream_ref:refs/tags/$previous_upstream_ref" \
    "refs/tags/$upstream_ref:refs/tags/$upstream_ref"
git -C "$scratch/upstream" checkout --quiet --detach "$upstream_ref"

if git -C "$scratch/upstream" cat-file -e \
    "$previous_upstream_ref:livespec_runtime/spec_stated.py" 2>/dev/null; then
    printf '%s\n' "$previous_upstream_ref unexpectedly contains spec_stated" >&2
    exit 1
fi
git -C "$scratch/upstream" cat-file -e "$upstream_ref:livespec_runtime/spec_stated.py"

PYTHONPATH='.claude-plugin/scripts/_vendor:.claude-plugin/scripts' uv run python - <<'PY'
from pathlib import Path

from livespec_runtime.spec_stated import classify, judge, parse_verdict

module_path = Path(judge.__code__.co_filename).resolve()
vendor_root = Path('.claude-plugin/scripts/_vendor/livespec_runtime').resolve()
assert module_path.is_relative_to(vendor_root)
assert callable(classify)
assert callable(parse_verdict)

print(f'vendored-spec-stated-module={module_path}')
print('vendored-spec-stated-import=passed')
PY

PYTHONPATH='.claude-plugin/scripts/_vendor:.claude-plugin/scripts' uv run python - <<'PY'
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

config = StoreConfig(
    tenant='vendor-release-check',
    prefix='vendor-release-check',
    server_user='vendor-release-check',
    database='vendor-release-check',
    bd_path='bd',
    fake=True,
)
common = dict(
    type='chore',
    status='active',
    title='Vendor release check',
    description='Hermetic rework label observation.',
    origin='freeform',
    gap_id=None,
    rank='a0',
    assignee=None,
    depends_on=(),
    captured_at='2026-10-21T00:00:00Z',
    resolution=None,
    reason=None,
    audit=None,
    superseded_by=None,
)

reset_fake_singleton()
try:
    append_work_item(path=config, item=WorkItem(id='vendor-labelled', **common))
    append_work_item(path=config, item=WorkItem(id='vendor-unlabelled', **common))
    client = make_beads_client(config=config)
    assert isinstance(client, FakeBeadsClient)
    client.update_issue(issue_id='vendor-labelled', add_labels=['rework:pending'])
    observed = {item.id: item.rework_pending for item in read_work_items(path=config)}
    assert observed == {'vendor-labelled': True, 'vendor-unlabelled': False}
    print(f"rework-pending-labelled={observed['vendor-labelled']}")
    print(f"rework-pending-unlabelled={observed['vendor-unlabelled']}")
finally:
    reset_fake_singleton()
PY

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
printf 'previous_upstream_ref=%s\n' "$previous_upstream_ref"
printf '%s\n' 'previous-release-spec-stated=absent'
printf '%s\n' 'pinned-release-spec-stated=present'
printf '%s\n' 'vendored-tree-release-comparison=passed'
