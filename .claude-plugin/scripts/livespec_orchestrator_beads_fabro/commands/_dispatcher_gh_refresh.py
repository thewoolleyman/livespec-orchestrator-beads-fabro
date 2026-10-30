"""Sandbox-local refreshing GitHub CLI wrapper projection for Dispatcher runs."""

from __future__ import annotations

import base64
import gzip
import io
import json
import os
import tarfile
from collections.abc import Mapping
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_git_push import PUSH_ORIGIN_SOURCE
from livespec_orchestrator_beads_fabro.commands._dispatcher_prepare_payload import (
    PAYLOAD_ENV_VAR,
    PrepareStep,
    payload_write_command,
    render_prepare_step,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_worktree_exclude import (
    worktree_exclude_script,
)

__all__: list[str] = [
    "DEFAULT_SANDBOX_GH_REFRESH_ROOT",
    "SANDBOX_GH_REFRESH_ROOT_ENV_VAR",
    "refreshing_gh_env_lines",
    "refreshing_gh_prepare_steps_block",
    "resolve_sandbox_gh_refresh_root",
]

_GITHUB_APP_ENV_KEYS = (
    "GITHUB_APP_ID",
    "GITHUB_PRIVATE_KEY",
    "GITHUB_APP_INSTALLATION_ID",
    "GITHUB_API_URL",
)
# The in-sandbox bundle root the dispatcher materializes the refreshing `gh`
# wrapper into. It holds the code that mints the run's forge credential, so it
# lives beside the other Dispatcher-materialized sandbox tooling under the
# sandbox plugins root and OUTSIDE the run's working tree: an agent stage edits
# and commits the working tree, and anything it writes there could act with the
# credential when a publication stage next runs. The value is a shell
# expression, expanded by the bash that runs each prepare step, and it is the
# same spelling the workflows' push helpers resolve. The lever below exists so
# a test can execute the rendered script for real against a temporary root;
# production never sets it. Mirrors `LIVESPEC_SANDBOX_OTEL_ENDPOINT` in
# `_dispatcher_projection`.
SANDBOX_GH_REFRESH_ROOT_ENV_VAR = "LIVESPEC_SANDBOX_GH_REFRESH_ROOT"

# Base64 chunk size. Each chunk rides one prepare step's own `env` value, which
# `execve` bounds at MAX_ARG_STRLEN (131072 bytes) independently of the larger
# total, so a big value fails with E2BIG and the run dies at launch, before any
# work, leaving no branch. bd-ib-gnli: one 186KB step did exactly that to every
# dispatch in two repos. `_dispatcher_prepare_payload.MAX_PAYLOAD_VALUE_BYTES`
# enforces the cap; this chunk size stays well under it.
_B64_CHUNK_CHARS = 48000
DEFAULT_SANDBOX_GH_REFRESH_ROOT = (
    "${LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT:-$HOME/.claude/plugins}/livespec-gh-refresh"
)


def resolve_sandbox_gh_refresh_root(*, environ: Mapping[str, str]) -> str:
    """Resolve the in-sandbox `gh`-wrapper bundle root (override > default)."""
    override = environ.get(SANDBOX_GH_REFRESH_ROOT_ENV_VAR, "").strip()
    return override or DEFAULT_SANDBOX_GH_REFRESH_ROOT


_SUPPORT_ARCHIVE_RELPATHS = (
    Path("_vendor/livespec_runtime/__init__.py"),
    Path("_vendor/livespec_runtime/github_auth"),
    Path("_vendor/returns"),
    Path("_vendor/typing_extensions.py"),
)
_MINT_HELPER_SOURCE = """#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

bundle_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(bundle_root / "_vendor"))

from livespec_runtime.github_auth.config import load_github_app_config
from livespec_runtime.github_auth.errors import GithubAppAuthError
from livespec_runtime.github_auth.provider import InstallationTokenProvider
from returns.pipeline import is_successful

if len(sys.argv) != 1:
    sys.stderr.write("usage: mint_app_token.py\\n")
    raise SystemExit(2)

config = load_github_app_config(environ=os.environ)
if not is_successful(config):
    sys.stderr.write(f"ERROR: {config.failure().detail}\\n")
    raise SystemExit(3)

try:
    token = InstallationTokenProvider(config=config.unwrap()).token()
except GithubAppAuthError as exc:
    sys.stderr.write(f"ERROR: {exc.detail}\\n")
    raise SystemExit(3) from exc

sys.stderr.write("github-token source: github-app-installation-token\\n")
sys.stdout.write(token)
"""

_AGENT_PUBLICATION_GUARD_SOURCE = r"""livespec_agent_publication_action() {
    case "${1:-} ${2:-}" in
        "pr create") printf '%s' gh_pr_create ;;
        "pr ready") printf '%s' gh_pr_ready ;;
        "pr merge") printf '%s' gh_pr_merge ;;
        "pr edit") printf '%s' gh_pr_edit ;;
        "api "*) livespec_agent_api_publication_action "$@" ;;
        *) return 1 ;;
    esac
}

livespec_agent_api_publication_action() {
    shift
    endpoint=''
    method=''
    has_body=''
    unreadable=''
    query=''
    value_for=''
    for argument in "$@"; do
        case "$value_for" in
            method) method="$argument"; value_for='' ;;
            field) has_body=1; query="$query $argument"; value_for='' ;;
            typed_field)
                has_body=1
                query="$query $argument"
                case "${argument#*=}" in @*) unreadable=1 ;; esac
                value_for=''
                ;;
            input) has_body=1; unreadable=1; value_for='' ;;
            *)
                case "$argument" in
                    --method|-X) value_for=method ;;
                    --method=*) method="${argument#*=}" ;;
                    -X?*) method="${argument#-X}" ;;
                    -f|--raw-field) value_for=field ;;
                    -F|--field) value_for=typed_field ;;
                    --raw-field=*) has_body=1; query="$query ${argument#--raw-field=}" ;;
                    -f?*) has_body=1; query="$query ${argument#-f}" ;;
                    --field=*|-F?*)
                        has_body=1
                        attached="${argument#--field=}"
                        attached="${attached#-F}"
                        query="$query $attached"
                        case "${attached#*=}" in @*) unreadable=1 ;; esac
                        ;;
                    --input) value_for=input ;;
                    --input=*) has_body=1; unreadable=1 ;;
                    query=*|mutation=*) query="$query $argument" ;;
                    graphql|/repos/*|repos/*) endpoint="$argument" ;;
                esac
                ;;
        esac
    done
    if test -z "$method"; then
        if test -n "$has_body"; then method=POST; else method=GET; fi
    fi
    method=$(printf '%s' "$method" | tr '[:lower:]' '[:upper:]')
    case "$endpoint" in
        graphql)
            if test -n "$unreadable"; then
                printf '%s' gh_api_graphql_unreadable
                return 0
            fi
            query=$(printf '%s' "$query" | tr '[:upper:]' '[:lower:]')
            case "$query" in
                *mergepullrequest*) printf '%s' gh_api_graphql_merge ;;
                *createpullrequest*) printf '%s' gh_api_graphql_create ;;
                *markpullrequestreadyforreview*) printf '%s' gh_api_graphql_ready ;;
                *updatepullrequest*) printf '%s' gh_api_graphql_edit ;;
                *enablepullrequestautomerge*|*disablepullrequestautomerge*)
                    printf '%s' gh_api_graphql_auto_merge ;;
                *) return 1 ;;
            esac
            ;;
        /repos/*/pulls/*/merge|repos/*/pulls/*/merge)
            test "$method" = PUT && printf '%s' gh_api_merge
            ;;
        /repos/*/pulls|repos/*/pulls)
            test "$method" = POST && printf '%s' gh_api_create
            ;;
        /repos/*/pulls/*/*|repos/*/pulls/*/*)
            test "$method" = PATCH && printf '%s' gh_api_edit
            ;;
        /repos/*/pulls/*|repos/*/pulls/*)
            test "$method" != GET && test "$method" != HEAD && printf '%s' gh_api_edit
            ;;
        *) return 1 ;;
    esac
}

livespec_agent_publication_guard_is_active() {
    case "${LIVESPEC_AGENT_STAGE:-}" in
        ''|publish_draft|pr_refresh|pr) return 1 ;;
        *) return 0 ;;
    esac
}

if livespec_agent_publication_guard_is_active \
    && action="$(livespec_agent_publication_action "$@")"; then
    printf 'LIVESPEC_AGENT_PUBLICATION_DENIED: stage=%s action=%s\n' \
        "$LIVESPEC_AGENT_STAGE" "$action" >&2
    exit 1
fi
"""


def refreshing_gh_prepare_steps_block() -> str:
    """Install a sandbox-local refreshing `gh` wrapper when App inputs exist.

    The support bundle is streamed to a file inside the sandbox across SEVERAL
    prepare steps rather than embedded in one. Fabro executes each step as
    `bash -c <script>`, so a step is a single argv argument and is bounded by
    MAX_ARG_STRLEN, not by the much larger ARG_MAX total (bd-ib-gnli).

    The default root is outside the run's working tree, so the exclusion below
    only matters for a root a lever places inside it. The FIRST step hides the
    bundle from the run's git worktree, and its position is load-bearing: the
    Petri-era engine runs each prepare step as a graph node and checkpoints
    after it, so a step that writes a byte of the bundle before the exclusion
    is in place is a step whose checkpoint commits it (bd-ib-dud2ww).

    BOTH bundle paths are excluded, and the payload is not an afterthought: the
    chunk steps stream the base64 archive to `<bundle_root>.b64` and only the
    unpack step deletes it, so on a per-node-checkpointing engine every chunk
    step's own checkpoint commits that file. Excluding the unpacked tree alone
    leaves the same defect one path over.
    """
    if not github_app_env_present():
        return ""
    bundle_root = resolve_sandbox_gh_refresh_root(environ=os.environ)
    mint_helper = f"{bundle_root}/bin/mint_app_token.py"
    payload_path = f"{bundle_root}.b64"
    exclude = PrepareStep(
        script=worktree_exclude_script(
            paths=(bundle_root, payload_path),
            label="livespec-gh-refresh",
        )
    )
    steps = [
        exclude,
        *_payload_chunk_steps(payload_path=payload_path),
        _unpack_step(bundle_root=bundle_root, mint_helper=mint_helper, payload_path=payload_path),
    ]
    return "\n# --- Dispatcher-materialized livespec-refreshing-gh-wrapper ---\n" + "".join(
        render_prepare_step(step=step) for step in steps
    )


def _payload_chunk_steps(*, payload_path: str) -> list[PrepareStep]:
    """Stream the base64 support bundle into a sandbox file, chunk by chunk.

    Each chunk rides its step's `env`, not its script, so the engine's compact
    preamble does not re-send 185k characters of base64 on every agent request.
    """
    archive_b64 = github_auth_support_archive_b64()
    steps: list[PrepareStep] = []
    for index in range(0, len(archive_b64), _B64_CHUNK_CHARS):
        chunk = archive_b64[index : index + _B64_CHUNK_CHARS]
        write = payload_write_command(path_word=f'"{payload_path}"', append=index > 0)
        steps.append(
            PrepareStep(
                script=f'set -eu\nmkdir -p "$(dirname "{payload_path}")"\n{write}',
                env={PAYLOAD_ENV_VAR: chunk},
            )
        )
    return steps


_MINT_VAR = f"{PAYLOAD_ENV_VAR}_MINT"
_PUSH_VAR = f"{PAYLOAD_ENV_VAR}_PUSH"
_WRAPPER_TAIL_VAR = f"{PAYLOAD_ENV_VAR}_WRAPPER_TAIL"
_WRAPPER_TAIL = (
    _AGENT_PUBLICATION_GUARD_SOURCE
    + """token="$(python3 "$mint")"
export GH_TOKEN="$token"
export GITHUB_TOKEN="$token"
exec "$real_gh" "$@"
"""
)
_EXTRACT_PROGRAM = """import base64, io, pathlib, sys, tarfile
payload = base64.b64decode(pathlib.Path(sys.argv[1]).read_text())
with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
    archive.extractall(sys.argv[2])"""


def _unpack_step(*, bundle_root: str, mint_helper: str, payload_path: str) -> PrepareStep:
    """Unpack the streamed bundle and install the refreshing `gh` wrapper.

    The three helper sources (the mint helper, the push helper and the wrapper's
    fixed tail) ride the step's `env`; the script only writes them.
    """
    push_helper = f"{bundle_root}/bin/push_origin"
    write_mint = payload_write_command(path_word='"$mint"', var=_MINT_VAR)
    write_push = payload_write_command(path_word=f'"{push_helper}"', var=_PUSH_VAR)
    write_tail = payload_write_command(path_word='"$real_gh"', var=_WRAPPER_TAIL_VAR, append=True)
    script = (
        "set -eu\n"
        f'bundle_root="{bundle_root}"\n'
        f'mint="{mint_helper}"\n'
        'rm -rf "$bundle_root"\n'
        'mkdir -p "$bundle_root/bin"\n'
        f'python3 -c \'{_EXTRACT_PROGRAM}\' "{payload_path}" "$bundle_root"\n'
        f'rm -f "{payload_path}"\n'
        f"{write_mint}\n"
        f"{write_push}\n"
        f'chmod 755 "{push_helper}"\n'
        'chmod 755 "$mint"\n'
        'real_gh="$(command -v gh)"\n'
        'case "$real_gh" in\n'
        "  /*) ;;\n"
        '  *) echo "gh did not resolve to an absolute path" >&2; exit 1 ;;\n'
        "esac\n"
        'wrapped_gh="${real_gh}.livespec-real"\n'
        'if [ ! -x "$wrapped_gh" ]; then mv "$real_gh" "$wrapped_gh"; fi\n'
        "printf '%s\\n' '#!/usr/bin/env bash' 'set -euo pipefail'"
        ' "mint=\\"$mint\\"" "real_gh=\\"$wrapped_gh\\"" > "$real_gh"\n'
        f"{write_tail}\n"
        'chmod 755 "$real_gh"'
    )
    return PrepareStep(
        script=script,
        env={
            _MINT_VAR: _MINT_HELPER_SOURCE,
            _PUSH_VAR: PUSH_ORIGIN_SOURCE,
            _WRAPPER_TAIL_VAR: _WRAPPER_TAIL,
        },
    )


def refreshing_gh_env_lines() -> str:
    """Project GitHub App inputs for the sandbox-local mint helper."""
    if not github_app_env_present():
        return ""
    return "".join(
        f"{key} = {json.dumps(value)}\n"
        for key in _GITHUB_APP_ENV_KEYS
        if (value := os.environ.get(key)) not in (None, "")
    )


def github_app_env_present() -> bool:
    """Whether the minimum GitHub App inputs are present."""
    return all(os.environ.get(key) not in (None, "") for key in _GITHUB_APP_ENV_KEYS[:2])


def github_auth_support_archive_b64(*, scripts_root: Path | None = None) -> str:
    """Return the dispatching plugin build's minimal GitHub auth support bundle."""
    root = scripts_root if scripts_root is not None else Path(__file__).resolve().parents[2]
    buffer = io.BytesIO()
    # Fix only the gzip header clock; tar members retain their source metadata.
    with (
        gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w") as archive,
    ):
        for relpath in _SUPPORT_ARCHIVE_RELPATHS:
            source = root / relpath
            if source.is_dir():
                for child in sorted(source.rglob("*.py")):
                    archive.add(child, arcname=str(child.relative_to(root)))
            else:
                archive.add(source, arcname=str(relpath))
    return base64.b64encode(buffer.getvalue()).decode("ascii")
