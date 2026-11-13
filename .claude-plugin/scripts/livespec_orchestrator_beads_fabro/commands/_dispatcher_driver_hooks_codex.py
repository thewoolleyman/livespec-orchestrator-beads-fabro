"""Release-byte verification and trust reconciliation for the Codex Driver."""

from __future__ import annotations

import shlex
import textwrap

_MARKETPLACE = "livespec-driver-codex"
_PLUGIN = "livespec"
_REPOSITORY = "https://github.com/thewoolleyman/livespec-driver-codex.git"

__all__: list[str] = ["codex_materialize_script"]


def codex_materialize_script() -> str:
    """Render setup that verifies materialized hooks before establishing trust."""
    read_version = shlex.quote(
        textwrap.dedent(
            """\
            import json
            import sys
            from pathlib import Path

            version = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")).get("version")
            if not isinstance(version, str) or not version:
                raise SystemExit("livespec-driver-codex: released plugin has no version")
            print(version)
            """
        )
    )
    reconcile = shlex.quote(
        textwrap.dedent(
            """\
            import json
            import sys
            from pathlib import Path

            from codex_config_write import ConfigWriteError, rewrite_config
            from codex_hook_release import verified_hook_keys
            from codex_hook_trust import reconcile_trust

            config_path, cache_root, release_payload = map(Path, sys.argv[1:4])
            codex_version = sys.argv[4].removeprefix("codex-cli ").strip()
            payloads = tuple(
                path
                for path in cache_root.iterdir()
                if path.is_dir()
                and not path.is_symlink()
                and (path / ".codex-plugin/plugin.json").is_file()
            ) if cache_root.is_dir() else ()
            if len(payloads) != 1:
                raise SystemExit(
                    "livespec-driver-codex: expected exactly one materialized plugin payload"
                )
            payload = payloads[0]
            version = json.loads(
                (payload / ".codex-plugin/plugin.json").read_text(encoding="utf-8")
            ).get("version")
            release_version = json.loads(
                (release_payload / ".codex-plugin/plugin.json").read_text(encoding="utf-8")
            ).get("version")
            if not isinstance(version, str) or version != release_version:
                raise SystemExit(
                    "livespec-driver-codex: materialized plugin does not match the pinned release"
                )
            hooks, problems = verified_hook_keys(
                marketplace="livespec-driver-codex",
                plugin="livespec",
                payload=payload,
                release_payload=release_payload,
            )
            if problems:
                raise SystemExit("\\n".join(problems))
            if not hooks:
                raise SystemExit("livespec-driver-codex: no materialized hooks were verified")
            if codex_version.startswith("0.153."):
                def legacy_rewrite(text: str) -> str:
                    if "[hooks.state." in text:
                        raise ConfigWriteError(
                            "livespec-driver-codex: unexpected existing Codex 0.153 trust state"
                        )
                    records = "".join(
                        f'\\n[hooks.state.{json.dumps(key)}]\\n'
                        f'trusted_hash = {json.dumps(value)}\\n'
                        for key, value in hooks
                    )
                    return text.rstrip() + records

                problem = rewrite_config(config_path=config_path, rewrite=legacy_rewrite)
                if problem:
                    raise SystemExit(problem)
            else:
                report = reconcile_trust(
                    config_path=config_path,
                    marketplace="livespec-driver-codex",
                    plugin="livespec",
                    payload=payload,
                    release_payload=release_payload,
                )
                if not report.ok:
                    raise SystemExit("\\n".join(report.problems))
            """
        )
    )
    return textwrap.dedent(
        f"""\
        set -eu
        acp="$(command -v codex-acp)"
        acp_root="$(CDPATH= cd -- "$(dirname "$(readlink -f "$acp")")/.." && pwd)"
        codex="$(node -p \
            "require.resolve('@openai/codex/bin/codex.js', {{ paths: [process.argv[1]] }})" \
            "$acp_root")"
        node "$codex" plugin marketplace add {_REPOSITORY} --ref release
        node "$codex" plugin add {_PLUGIN}@{_MARKETPLACE}
        cache="$CODEX_HOME/plugins/cache/{_MARKETPLACE}/{_PLUGIN}"
        release="$CODEX_HOME/livespec-driver-codex-release"
        test ! -e "$release"
        git clone --quiet --depth=1 --branch release {_REPOSITORY} "$release"
        release_version="$(python3 -c {read_version} "$release/livespec/.codex-plugin/plugin.json")"
        git -C "$release" fetch --quiet --depth=1 origin "refs/tags/v$release_version"
        test "$(git -C "$release" rev-parse HEAD)" = "$(git -C "$release" rev-parse FETCH_HEAD)"
        codex_version="$(node "$codex" --version)"
        PYTHONPATH="$release/dev-tooling" python3 -c {reconcile} \
            "$CODEX_HOME/config.toml" "$cache" "$release/livespec" "$codex_version"
        """
    ).strip()
