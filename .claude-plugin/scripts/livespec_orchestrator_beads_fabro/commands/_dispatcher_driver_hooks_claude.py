"""Release-pinned Claude Driver plugin-cache materialization."""

from __future__ import annotations

import shlex
import textwrap

_MARKETPLACE = "livespec-driver-claude"
_PLUGIN = "livespec"
_REPOSITORY = "https://github.com/thewoolleyman/livespec-driver-claude.git"

__all__: list[str] = ["claude_materialize_script"]


def claude_materialize_script() -> str:
    """Render the fresh cache and registry records Claude reads at session start."""
    read_version = shlex.quote(
        textwrap.dedent(
            """\
            import json
            import sys
            from pathlib import Path

            version = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")).get("version")
            if not isinstance(version, str) or not version:
                raise SystemExit(
                    "livespec-driver-claude: materialized plugin has no release version"
                )
            print(version)
            """
        )
    )
    write_registries = shlex.quote(
        textwrap.dedent(
            """\
            import json
            import sys
            from pathlib import Path

            root, marketplace, cache = map(Path, sys.argv[1:4])
            revision = sys.argv[4]
            key = "livespec@livespec-driver-claude"
            registry_path = root / "installed_plugins.json"
            try:
                registry = json.loads(registry_path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                registry = {"version": 2, "plugins": {}}
            if not isinstance(registry, dict) or not isinstance(registry.get("plugins"), dict):
                raise SystemExit("livespec-driver-claude: malformed installed plugin registry")
            registry["plugins"][key] = [{
                "scope": "project",
                "installPath": str(cache),
                "version": revision[:12],
                "gitCommitSha": revision,
            }]
            registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
            marketplaces_path = root / "known_marketplaces.json"
            try:
                marketplaces = json.loads(marketplaces_path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                marketplaces = {}
            if not isinstance(marketplaces, dict):
                raise SystemExit("livespec-driver-claude: malformed marketplace registry")
            marketplaces["livespec-driver-claude"] = {
                "source": {
                    "source": "github",
                    "repo": "thewoolleyman/livespec-driver-claude",
                    "ref": revision,
                },
                "installLocation": str(marketplace),
            }
            marketplaces_path.write_text(json.dumps(marketplaces, indent=2), encoding="utf-8")
            """
        )
    )
    return textwrap.dedent(
        f"""\
        set -eu
        root="${{LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT:-$HOME/.claude/plugins}}"
        marketplace="$root/marketplaces/{_MARKETPLACE}"
        test ! -e "$marketplace"
        mkdir -p "$root/marketplaces"
        git clone --quiet --depth=1 --branch release {_REPOSITORY} "$marketplace"
        revision="$(git -C "$marketplace" rev-parse HEAD)"
        version="$(python3 -c {read_version} "$marketplace/.claude-plugin/plugin.json")"
        git -C "$marketplace" fetch --quiet --depth=1 origin "refs/tags/v$version"
        test "$revision" = "$(git -C "$marketplace" rev-parse FETCH_HEAD)"
        cache="$root/cache/{_MARKETPLACE}/{_PLUGIN}/$revision"
        mkdir -p "$cache"
        cp -a "$marketplace/.claude-plugin/." "$cache/"
        test -f "$cache/hooks/pretooluse_dispatch.py"
        python3 -c {write_registries} "$root" "$marketplace" "$cache" "$revision"
        """
    ).strip()
