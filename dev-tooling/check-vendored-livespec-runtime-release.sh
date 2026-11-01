#!/usr/bin/env bash
# Prove the vendored livespec-runtime tree equals the release its OWN manifest pins.
#
# The instrument for the two assertions of work-item `bd-ib-ouk27x` that cannot be
# proved hermetically: they compare the vendored tree against the release, so they
# need the release's bytes and therefore a network fetch. That is why this lives
# here and NOT in the `just check` aggregate — every target of that aggregate runs
# offline in CI. `tests/test_vendored_livespec_runtime.py` carries the two
# assertions that ARE hermetic.
#
# TWO THINGS THIS SCRIPT REFUSES TO DO, each because a first attempt at this bump
# did it and the review caught it:
#
# 1. IT NAMES NO RELEASE OF ITS OWN. The pin is READ from `.vendor.jsonc` at run
#    time and echoed. A hardcoded `v0.28.0` would print the release the script's
#    author believed was pinned rather than the one the repository actually
#    resolves, so the output would stay green through a manifest edit that moved
#    the pin somewhere else entirely — evidence about the wrong artifact, with
#    nothing in the output to say so.
#
# 2. IT EXCLUDES NO FILE FROM THE COMPARISON. Every vendored file must equal the
#    release's copy byte for byte; the one exception is the preserved `LICENSE`,
#    and only while the release ships none. `work_items/types.py` used to carry a
#    local `WorkItem.rework_pending` carve-out (since commit 74a97bf9); v0.29.0
#    upstreamed that field, so from v0.29.1 the carve-out is retired and the file
#    is compared like every other.
set -euo pipefail

readonly manifest='.vendor.jsonc'
readonly lib='livespec_runtime'
readonly vendor_root=".claude-plugin/scripts/_vendor/${lib}"

if ! test -f "$manifest"; then
    printf '%s\n' "run this from the repository root: no $manifest here" >&2
    exit 2
fi

# The manifest is JSON with `//` line comments, so it is parsed as the manifest's
# own syntax rather than grepped: a pattern read would answer "absent" for a pin
# spelled in any shape it did not anticipate, which is the failure mode that makes
# a green result meaningless.
read_manifest_field() {
    python3 - "$manifest" "$lib" "$1" <<'PY'
import json
import re
import sys

path, name, field = sys.argv[1:4]
line_comment = re.compile(r'("(?:\\.|[^"\\])*")|(//[^\n]*)')
with open(path, encoding="utf-8") as handle:
    stripped = line_comment.sub(lambda m: m.group(1) or "", handle.read())
[entry] = [one for one in json.loads(stripped)["libraries"] if one["name"] == name]
value = entry[field]
if not isinstance(value, str) or not value:
    raise SystemExit(f"{path}: {name}.{field} is not a non-empty string")
sys.stdout.write(value)
PY
}

upstream_url="$(read_manifest_field upstream_url)"
upstream_ref="$(read_manifest_field upstream_ref)"
printf 'manifest=%s\n' "$manifest"
printf 'manifest_upstream_url=%s\n' "$upstream_url"
printf 'manifest_upstream_ref=%s\n' "$upstream_ref"

scratch="$(mktemp -d)"
# shellcheck disable=SC2064  # Expand $scratch now; the trap must not read a later value.
trap "rm -rf '$scratch'" EXIT

release="$scratch/release"
git init --quiet "$release"
git -C "$release" remote add origin "$upstream_url"
GIT_TERMINAL_PROMPT=0 git -C "$release" fetch --quiet --depth 1 origin \
    "refs/tags/${upstream_ref}:refs/tags/${upstream_ref}"
git -C "$release" checkout --quiet --detach "refs/tags/${upstream_ref}"
printf 'release_commit=%s\n' "$(git -C "$release" rev-parse HEAD)"

python3 - "$release/$lib" "$vendor_root" <<'PY'
"""Compare one vendored tree against one release tree, byte for byte.

Every refusal below fails the whole comparison. The only file not compared is
the preserved LICENSE, and that exception is itself checked: it holds only while
the release ships no LICENSE of its own.
"""

import sys
from pathlib import Path

release_root, vendored_root = (Path(one) for one in sys.argv[1:3])

PRESERVED = "LICENSE"

failures: list[str] = []


def files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


release_files = files(release_root)
vendored_files = files(vendored_root)

# The preserved LICENSE is an exception only while upstream genuinely ships none;
# asserting that is what keeps a release that STARTS shipping one from being
# silently overridden by this repository's copy.
if PRESERVED in release_files:
    failures.append(f"the release now ships {PRESERVED}, so preserving ours is no longer correct")
if PRESERVED not in vendored_files:
    failures.append(f"the vendored tree is missing the preserved {PRESERVED}")
vendored_files.pop(PRESERVED, None)

missing = sorted(set(release_files) - set(vendored_files))
extra = sorted(set(vendored_files) - set(release_files))
if missing:
    failures.append(f"absent from the vendored tree: {missing}")
if extra:
    failures.append(f"present in the vendored tree but not the release: {extra}")

differing = sorted(
    path
    for path in set(release_files) & set(vendored_files)
    if release_files[path] != vendored_files[path]
)
if differing:
    failures.append(f"differ from the release: {differing}")

if failures:
    for failure in failures:
        sys.stderr.write(f"vendored-release-mismatch: {failure}\n")
    raise SystemExit(1)

spec_stated = "spec_stated.py"
if spec_stated not in release_files:
    sys.stderr.write(f"vendored-release-mismatch: the release carries no {spec_stated}\n")
    raise SystemExit(1)

sys.stdout.write(f"compared_files={len(release_files)}\n")
sys.stdout.write(f"preserved_file={PRESERVED}\n")
sys.stdout.write("vendored-tree-equals-release=passed\n")
PY

PYTHONPATH='.claude-plugin/scripts/_vendor:.claude-plugin/scripts' python3 - <<'PY'
from pathlib import Path

from livespec_runtime.spec_stated import classify, judge, parse_verdict

resolved = Path(judge.__code__.co_filename).resolve()
vendored = Path(".claude-plugin/scripts/_vendor/livespec_runtime").resolve()
if not resolved.is_relative_to(vendored):
    raise SystemExit(f"spec_stated resolved outside the vendored tree: {resolved}")
for name, value in (("classify", classify), ("parse_verdict", parse_verdict)):
    if not callable(value):
        raise SystemExit(f"{name} is not callable")

print(f"vendored_spec_stated_module={resolved}")
print("vendored-spec-stated-import=passed")
PY
