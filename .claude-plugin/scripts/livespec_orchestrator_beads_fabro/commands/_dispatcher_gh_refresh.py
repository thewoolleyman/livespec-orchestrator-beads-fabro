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

__all__: list[str] = [
    "DEFAULT_SANDBOX_GH_REFRESH_ROOT",
    "MAX_PREPARE_STEP_BYTES",
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
# wrapper into. `/workspace` is the fabro sandbox's own mount, so this absolute
# path is correct in production and WRONG anywhere else -- on a CI runner it
# resolves to the runner's filesystem root, where `rm -rf` + `mkdir` either is
# refused (uid 1000: `mkdir: Permission denied`) or, worse, succeeds under uid 0
# and destroys a real /workspace. The lever below exists so a test can execute
# the rendered script for real against a temporary root; production never sets
# it. Mirrors `LIVESPEC_SANDBOX_OTEL_ENDPOINT` in `_dispatcher_projection`.
SANDBOX_GH_REFRESH_ROOT_ENV_VAR = "LIVESPEC_SANDBOX_GH_REFRESH_ROOT"

# Fabro runs each prepare step as `bash -c <script>`, so the WHOLE script is one
# argv argument. Linux caps a SINGLE argument at MAX_ARG_STRLEN (131072 bytes),
# independently of the much larger ARG_MAX total -- so a big step fails `execve`
# with E2BIG and the run dies at launch, before any work, leaving no branch.
# bd-ib-gnli: one 186KB step did exactly that to every dispatch in two repos.
# This cap is deliberately well under the kernel limit to leave room for the
# shell wrapper fabro adds around the script.
MAX_PREPARE_STEP_BYTES = 96000

# Base64 chunk size, chosen so one chunk plus its shell wrapper stays well
# inside MAX_PREPARE_STEP_BYTES. The base64 alphabet is A-Za-z0-9+/= only, so a
# chunk can be single-quoted in shell without escaping; _assert_shell_safe below
# holds that invariant rather than trusting it.
_B64_CHUNK_CHARS = 48000
_B64_ALPHABET = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
DEFAULT_SANDBOX_GH_REFRESH_ROOT = "/workspace/.livespec-gh-refresh"


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


def refreshing_gh_prepare_steps_block() -> str:
    """Install a sandbox-local refreshing `gh` wrapper when App inputs exist.

    The support bundle is streamed to a file inside the sandbox across SEVERAL
    prepare steps rather than embedded in one. Fabro executes each step as
    `bash -c <script>`, so a step is a single argv argument and is bounded by
    MAX_ARG_STRLEN, not by the much larger ARG_MAX total (bd-ib-gnli).

    The FIRST step hides the bundle from the run's git worktree, and its
    position is load-bearing: the Petri-era engine runs each prepare step as a
    graph node and checkpoints after it, so a step that writes a byte of the
    bundle before the exclusion is in place is a step whose checkpoint commits
    it (bd-ib-dud2ww).
    """
    if not github_app_env_present():
        return ""
    bundle_root = resolve_sandbox_gh_refresh_root(environ=os.environ)
    mint_helper = f"{bundle_root}/bin/mint_app_token.py"
    payload_path = f"{bundle_root}.b64"
    scripts = [
        _worktree_exclude_script(bundle_root=bundle_root, payload_path=payload_path),
        *_payload_chunk_scripts(payload_path=payload_path),
        _unpack_script(bundle_root=bundle_root, mint_helper=mint_helper, payload_path=payload_path),
    ]
    lines = ["", "# --- Dispatcher-materialized livespec-refreshing-gh-wrapper ---"]
    for script in scripts:
        _assert_step_within_limit(script=script)
        lines.extend(["[[run.prepare.steps]]", f"script = '''\n{script}\n'''"])
    return "\n".join(lines) + "\n"


def _assert_shell_safe(*, chunk: str) -> None:
    """Refuse a chunk that could break out of its single-quoted shell literal."""
    if not set(chunk) <= _B64_ALPHABET:
        msg = "gh-refresh payload chunk carries characters outside the base64 alphabet"
        raise ValueError(msg)


def _assert_step_within_limit(*, script: str) -> None:
    """Refuse loudly BEFORE submission rather than dying at execve.

    A step over the kernel's per-argument limit does not degrade: the run dies
    at launch with "argument list too long", having done no work and pushed no
    branch. Failing here names the cause instead.
    """
    size = len(script.encode())
    if size > MAX_PREPARE_STEP_BYTES:
        msg = (
            f"gh-refresh prepare step is {size} bytes, over the "
            f"{MAX_PREPARE_STEP_BYTES}-byte per-step limit; it would fail execve "
            "with 'argument list too long' and destroy the run"
        )
        raise ValueError(msg)


def _worktree_exclude_script(*, bundle_root: str, payload_path: str) -> str:
    """Make the bundle invisible to git BEFORE a byte of it is written.

    The bundle root is inside the run's own git worktree (`/workspace` is the
    sandbox clone's top level), and nothing ignored it. The Petri-era engine
    checkpoints after every graph node, prepare steps included, so each
    checkpoint staged the bundle into the run branch -- and `publish_draft`'s
    `git rebase origin/$default_branch` then met its own committed copy as an
    untracked file on disk and refused at that checkpoint's pick (measured on
    hp-candidate run 01M4Q45S5AGK, bd-ib-dud2ww).

    The exclusion is written to the clone's OWN exclude file rather than to a
    tracked `.gitignore`: the bundle is an artifact of how this Dispatcher
    projects credentials into one sandbox, so a governed repository must not
    have to carry a rule about it, and a rule this step added to a tracked file
    would itself be a change every checkpoint commits.

    `--git-common-dir` and not `--git-dir`, because that is the directory whose
    `info/exclude` git actually reads in a linked worktree; it answers the same
    path in an ordinary clone, which is what the sandbox has.

    BOTH paths are excluded, and the payload is not an afterthought: the chunk
    steps stream the base64 archive to `<bundle_root>.b64` and only the unpack
    step deletes it, so on a per-node-checkpointing engine every chunk step's
    own checkpoint commits that file. Excluding the unpacked tree alone leaves
    the same defect one path over.

    Both sides of the inside-the-worktree comparison are reduced to their
    PHYSICAL spelling first, and that normalization is load-bearing rather
    than tidy: `git rev-parse --show-toplevel` answers the physical path and
    DISCARDS the spelling it was handed, while the configured root reaches
    this sandbox family as `/workspace/<repo>`, which is a symlink to the
    clone's real path. Comparing the two as given therefore sent a path
    squarely INSIDE the worktree down the outside-any-worktree arm, writing
    no entry at all -- the whole defect, intact, behind a step that exits 0.

    Every arm that cannot MEASURE where a path sits is passed over without
    writing, and SAYS SO on stderr: a prepare step that fails kills the run
    at launch, before any work is driven, and a path outside any worktree is
    one git was never going to stage -- but a silent pass-over is
    indistinguishable from a successful exclusion until `publish_draft`
    refuses at the end of a full run. Each pattern is anchored with a leading
    `/` because `info/exclude` patterns resolve against the worktree top.
    """
    return (
        "set -eu\n"
        f'bundle_root="{bundle_root}"\n'
        f'payload_path="{payload_path}"\n'
        'parent="$(dirname "$bundle_root")"\n'
        'mkdir -p "$parent"\n'
        'toplevel="$(git -C "$parent" rev-parse --show-toplevel 2>/dev/null || true)"\n'
        'if [ -n "$toplevel" ]; then\n'
        '  toplevel="$(cd "$toplevel" 2>/dev/null && pwd -P || true)"\n'
        "fi\n"
        'if [ -z "$toplevel" ]; then\n'
        "  echo \"livespec-gh-refresh: no git worktree top resolved for '$parent',"
        ' so no exclude entry was written" >&2\n'
        "  exit 0\n"
        "fi\n"
        'common_dir="$(cd "$toplevel" && git rev-parse --git-common-dir)"\n'
        'case "$common_dir" in\n'
        "  /*) ;;\n"
        '  *) common_dir="$toplevel/$common_dir" ;;\n'
        "esac\n"
        'exclude_file="$common_dir/info/exclude"\n'
        'mkdir -p "$common_dir/info"\n'
        'for path in "$bundle_root" "$payload_path"; do\n'
        '  path_dir="$(cd "$(dirname "$path")" 2>/dev/null && pwd -P || true)"\n'
        '  if [ -n "$path_dir" ]; then path="$path_dir/$(basename "$path")"; fi\n'
        '  case "$path" in\n'
        '    "$toplevel"/*) entry="/${path#"$toplevel"/}" ;;\n'
        "    *)\n"
        "      echo \"livespec-gh-refresh: '$path' did not resolve inside the worktree"
        " at '$toplevel', so no exclude entry was written for it\" >&2\n"
        "      continue\n"
        "      ;;\n"
        "  esac\n"
        '  if ! grep -qxF "$entry" "$exclude_file" 2>/dev/null; then\n'
        '    printf \'%s\\n\' "$entry" >> "$exclude_file"\n'
        "  fi\n"
        "done"
    )


def _payload_chunk_scripts(*, payload_path: str) -> list[str]:
    """Stream the base64 support bundle into a sandbox file, chunk by chunk."""
    archive_b64 = github_auth_support_archive_b64()
    scripts: list[str] = []
    for index in range(0, len(archive_b64), _B64_CHUNK_CHARS):
        chunk = archive_b64[index : index + _B64_CHUNK_CHARS]
        _assert_shell_safe(chunk=chunk)
        redirect = ">" if index == 0 else ">>"
        script = (
            "set -eu\n"
            f'mkdir -p "$(dirname "{payload_path}")"\n'
            f"printf '%s' '{chunk}' {redirect} \"{payload_path}\""
        )
        scripts.append(script)
    return scripts


def _unpack_script(*, bundle_root: str, mint_helper: str, payload_path: str) -> str:
    """Unpack the streamed bundle and install the refreshing `gh` wrapper."""
    helper_source_literal = json.dumps(_MINT_HELPER_SOURCE)
    push_helper = f"{bundle_root}/bin/push_origin"
    return (
        "set -eu\n"
        f'bundle_root="{bundle_root}"\n'
        f'mint="{mint_helper}"\n'
        'rm -rf "$bundle_root"\n'
        'mkdir -p "$bundle_root/bin"\n'
        "python3 - <<'PY'\n"
        "import base64\n"
        "import io\n"
        "import pathlib\n"
        "import tarfile\n"
        f"payload = base64.b64decode(pathlib.Path({payload_path!r}).read_text())\n"
        f"target = {bundle_root!r}\n"
        'with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:\n'
        "    archive.extractall(target)\n"
        "PY\n"
        f'rm -f "{payload_path}"\n'
        "python3 - <<'PY'\n"
        "from pathlib import Path\n"
        f"Path({mint_helper!r}).write_text({helper_source_literal}, encoding='utf-8')\n"
        "PY\n"
        "python3 - <<'PY'\n"
        "from pathlib import Path\n"
        f"Path({push_helper!r}).write_text({json.dumps(PUSH_ORIGIN_SOURCE)}, encoding='utf-8')\n"
        "PY\n"
        f'chmod 755 "{push_helper}"\n'
        'chmod 755 "$mint"\n'
        'real_gh="$(command -v gh)"\n'
        'case "$real_gh" in\n'
        "  /*) ;;\n"
        '  *) echo "gh did not resolve to an absolute path" >&2; exit 1 ;;\n'
        "esac\n"
        'wrapped_gh="${real_gh}.livespec-real"\n'
        'if [ ! -x "$wrapped_gh" ]; then mv "$real_gh" "$wrapped_gh"; fi\n'
        'cat > "$real_gh" <<EOF\n'
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'mint="$mint"\n'
        'real_gh="$wrapped_gh"\n'
        "EOF\n"
        "cat >> \"$real_gh\" <<'EOF'\n"
        'token="$(python3 "$mint")"\n'
        'export GH_TOKEN="$token"\n'
        'export GITHUB_TOKEN="$token"\n'
        'exec "$real_gh" "$@"\n'
        "EOF\n"
        'chmod 755 "$real_gh"'
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
    # The overlay is a reproducible bundle: its bytes must not depend on the mint clock.
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
