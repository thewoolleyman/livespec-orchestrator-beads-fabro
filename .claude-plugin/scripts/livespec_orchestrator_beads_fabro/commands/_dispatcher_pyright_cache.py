"""Prepare one complete, locked pyright cache before a sandbox agent can use it.

Pyright's Python wrapper treats a matching ``package.json`` as a complete npm
installation. That is unsafe on a fresh sandbox: concurrent pyright invocations
can observe that file while npm is still extracting typeshed, then analyse with
incomplete standard-library stubs. This renderer installs into a private
directory and atomically publishes it only after comparing every bundled stdlib
file with the locked package archive.
"""

from __future__ import annotations

import json

__all__: list[str] = ["pyright_cache_prepare_steps_block"]


def pyright_cache_prepare_steps_block() -> str:
    """Render the serial, archive-validated pyright cache preparation step.

    The resumed checkout precedes this block in the overlay. Re-syncing here
    therefore selects the resumed branch's locked pyright Python package rather
    than the dispatch-base package that the committed prepare chain first
    installed. Repositories without a uv lock retain their existing setup.
    """
    script = r'''set -eu
if ! test -f uv.lock; then exit 0; fi
uv sync --all-groups
version="$(
    uv run --no-sync python -c "import importlib.metadata as m; print(m.version('pyright'))" \
        2>/dev/null || true
)"
if test -z "$version"; then exit 0; fi
cache_root="${PYRIGHT_PYTHON_CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/pyright-python}"
target="$cache_root/$version"
mkdir -p "$cache_root"
archive_root="$(mktemp -d "$cache_root/.pyright-archive.XXXXXX")"
install_root="$(mktemp -d "$cache_root/.pyright-install.XXXXXX")"
cleanup() { rm -rf "$archive_root" "$install_root"; }
complete_cache() {
    root="$1/node_modules/pyright"
    installed_version="$(node -p "require(process.argv[1]).version" "$root/package.json")"
    if test "$installed_version" != "$version"; then return 1; fi
    expected="$(tar -tzf "$archive" | sed -n '\|^package/dist/typeshed-fallback/stdlib/.*|p')"
    if test -z "$expected"; then return 1; fi
    for entry in $expected; do
        if ! test -f "$root/${entry#package/}"; then return 1; fi
    done
}
trap cleanup EXIT
npm pack --silent --pack-destination "$archive_root" "pyright@$version" >/dev/null
archive="$(find "$archive_root" -maxdepth 1 -type f -name '*.tgz' -print -quit)"
test -n "$archive"
if complete_cache "$target"; then exit 0; fi
npm install --ignore-scripts --no-package-lock --prefix "$install_root" "$archive" >/dev/null
complete_cache "$install_root"
rm -rf "$target"
mv "$install_root" "$target"
trap - EXIT
rm -rf "$archive_root"'''
    lines = [
        "",
        "# --- Dispatcher-materialized pyright cache provisioning: the Python",
        "# --- wrapper accepts a matching package.json before npm has extracted its",
        "# --- bundled typeshed, so prepare one archive-validated installation and",
        "# --- publish it atomically before any agent command or hook can race it",
        "# --- (bd-ib-g5hp) ---",
        "[[run.prepare.steps]]",
        f"script = {json.dumps(script)}",
    ]
    return "\n".join(lines) + "\n"
