"""Release-verified Codex Driver hook materialization for factory sandboxes."""

from __future__ import annotations

import textwrap

from livespec_orchestrator_beads_fabro.commands._dispatcher_prepare_payload import (
    PrepareStep,
    render_prepare_step,
)

__all__: list[str] = [
    "codex_driver_hooks_prepare_steps_block",
]

_DRIVER_MARKETPLACE = "livespec-driver-codex"
_DRIVER_PLUGIN = "livespec"
_DRIVER_REPOSITORY = "https://github.com/thewoolleyman/livespec-driver-codex.git"


def _materialize_script() -> str:
    """Render the sandbox operation that installs and trusts the pinned Driver.

    Codex ACP bundles the Codex CLI but does not expose it on ``PATH``. The
    package-local invocation keeps this projection coupled to the Codex build
    the adapter starts. The Driver release supplies the verifier, so its
    release-byte algorithm—not cache bytes—decides whether hooks are trusted.
    """
    return textwrap.dedent(
        f"""\
        set -eu
        acp="$(command -v codex-acp)"
        acp_root="$(CDPATH= cd -- "$(dirname "$(readlink -f "$acp")")/.." && pwd)"
        codex="$acp_root/lib/node_modules/@agentclientprotocol/codex-acp/node_modules/@openai/codex/bin/codex.js"
        test -f "$codex"
        node "$codex" plugin marketplace add {_DRIVER_REPOSITORY} --ref release \\
            --sparse .agents/plugins --sparse livespec
        node "$codex" plugin add {_DRIVER_PLUGIN}@{_DRIVER_MARKETPLACE}
        cache="$CODEX_HOME/plugins/cache/{_DRIVER_MARKETPLACE}/{_DRIVER_PLUGIN}"
        version="$(python3 - "$cache" <<'PY'
        import json
        import sys
        from pathlib import Path

        root = Path(sys.argv[1])
        payloads = (
            sorted(path for path in root.iterdir() if path.is_dir()) if root.is_dir() else []
        )
        if len(payloads) != 1:
            raise SystemExit(
                "livespec-driver-codex: expected exactly one materialized plugin payload"
            )
        manifest = payloads[0] / ".codex-plugin" / "plugin.json"
        try:
            version = json.loads(manifest.read_text(encoding="utf-8"))["version"]
        except (KeyError, OSError, ValueError, TypeError) as error:
            raise SystemExit(
                f"livespec-driver-codex: unreadable materialized plugin version: {{error}}"
            )
        if not isinstance(version, str) or not version:
            raise SystemExit("livespec-driver-codex: materialized plugin has no release version")
        print(version)
        PY
        )"
        release="$CODEX_HOME/livespec-driver-codex-release"
        git init -q "$release"
        git -C "$release" remote add origin {_DRIVER_REPOSITORY}
        if ! git -C "$release" fetch -q --depth=1 origin "refs/tags/v$version"; then
            git -C "$release" fetch -q --depth=1 origin "refs/tags/$version"
        fi
        git -C "$release" checkout -q --detach FETCH_HEAD
        PYTHONPATH="$release/dev-tooling" python3 - "$CODEX_HOME" "$cache" \\
            "$release/livespec" <<'PY'
        import sys
        from pathlib import Path

        # The reconciler writes Codex's trusted_content_hash only after its
        # declaration and entrypoint bytes match the tagged release.
        from codex_hook_trust import reconcile_trust

        home, cache, release = map(Path, sys.argv[1:])
        payloads = tuple(path for path in cache.iterdir() if path.is_dir())
        if len(payloads) != 1:
            raise SystemExit("livespec-driver-codex: expected one materialized plugin payload")
        report = reconcile_trust(
            config_path=home / "config.toml",
            marketplace="{_DRIVER_MARKETPLACE}",
            plugin="{_DRIVER_PLUGIN}",
            payload=payloads[0],
            release_payload=release,
        )
        if not report.ok:
            for problem in report.problems:
                print(f"livespec-driver-codex: {{problem}}", file=sys.stderr)
            raise SystemExit(1)
        if not report.trusted_hooks:
            raise SystemExit("livespec-driver-codex: no materialized hooks were trusted")
        PY
        """
    ).strip()


def codex_driver_hooks_prepare_steps_block() -> str:
    """Render the prepare step that installs and trusts Codex Driver hooks.

    The Driver release is selected from the materialized payload's manifest.
    Its release checkout runs the Driver's own ``codex_hook_trust`` verifier,
    which rejects changed hook declarations and entrypoints before writing
    ``trusted_content_hash`` records to ``$CODEX_HOME/config.toml``.
    """
    step = PrepareStep(script=_materialize_script())
    header = """
# --- Dispatcher-materialized Codex Driver hooks: install the pinned
# --- release and trust only hook bytes verified against that release ---
"""
    return header + render_prepare_step(step=step)
