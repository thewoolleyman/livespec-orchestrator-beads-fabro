"""THE ONE LIST of helper programs the Dispatcher materializes into a sandbox.

`SPECIFICATION/contracts.md` section "Self-contained plugin dispatch", paragraph
"Helper programs are fetched in the sandbox from the dispatching build's own
commit". A *helper program* is a fixed program this plugin composes from its own
source and writes into a dispatch's sandbox: the commit runner, the plugin-cache
gate, the refreshing `gh` wrapper's support files, the credential-use guard. The
rendered run configuration no longer carries their bytes. It carries a manifest
naming each one and its sha256, and a setup step fetches this plugin at the
installed build's commit, composes every helper there through THIS registry, and
refuses unless every composed digest matches.

ONE REGISTRY, TWO SIDES. The Dispatcher digests `helper_registry()`'s bytes to
write the manifest (`helper_manifest`), and the sandbox materializer
(`_dispatcher_helper_materialize`) composes the same registry from the fetched
checkout and writes those bytes. The registry is the only place a helper is
named, so the two sides cannot disagree about which helpers exist, where each
lands, or which mode it takes. A helper added here is fetched everywhere; a
helper composed anywhere else is not a helper the sandbox will receive.

EVERY COMPOSER IS A PURE FUNCTION OF THE PLUGIN TREE. Each `compose` reads only
this plugin's own files and constants, never a dispatch input: that is what makes
a composition at the installed build's commit byte-identical to the Dispatcher's
own. Per-dispatch data (the Definition-of-Done subject, the pull-request body,
the hook-limit figures, the run-from plan) is not a helper and rides the overlay.

THREE SANDBOX ROOTS, NAMED, NOT SPELLED. Each helper's `path` is relative to one
named root, and the setup step resolves each root at run time exactly as the
steps that consume the helpers do: the Claude plugins root by shell expansion
(`_dispatcher_sandbox_plugins`), the refreshing-`gh` bundle root as the overlay
resolves it (`_dispatcher_gh_refresh`), and the credential-use guard's directory.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from livespec_orchestrator_beads_fabro.commands._dispatcher_carry_forward_program import (
    CARRY_FORWARD_PROGRAM_FILENAME,
    carry_forward_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_program import (
    COMMIT_RUNNER_PROGRAM_FILENAME,
    commit_runner_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard import (
    GUARD_SCRIPT_PATH,
    guard_script_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_projection import (
    proof_capture_asset_sources,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_gh_refresh import (
    GH_MINT_HELPER_RELPATH,
    GH_PUSH_HELPER_RELPATH,
    GH_WRAPPER_TAIL_RELPATH,
    gh_mint_helper_source,
    gh_wrapper_tail_source,
    github_auth_support_relpaths,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_push import PUSH_ORIGIN_SOURCE
from livespec_orchestrator_beads_fabro.commands._dispatcher_harness_shell_policy import (
    HARNESS_SETTINGS_MERGE_PROGRAM_FILENAME,
    harness_settings_merge_program,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_limit_program import (
    HOOK_LIMIT_PROGRAM_FILENAME,
    hook_limit_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_implement_commit_programs import (
    COMMIT_GREEN_PROGRAM_FILENAME,
    COMMIT_RED_PROGRAM_FILENAME,
    commit_green_program_source,
    commit_red_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_cache_gate import (
    PLUGIN_GATE_PROGRAM_FILENAME,
    plugin_cache_gate_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_grade_program import (
    PROOF_GRADE_PROGRAM_FILENAME,
    PROOF_GRADE_READER_DIRECTORY,
    proof_grade_program_source,
    proof_record_reader_sources,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_head import (
    PROOF_HEAD_PROGRAM_FILENAME,
    proof_head_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_push import (
    PUBLICATION_PUSH_PROGRAM_FILENAME,
    publication_push_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_merge import (
    RECORD_FILE_MERGE_PROGRAM_FILENAME,
    record_file_merge_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_regeneration import (
    RECORD_FILE_PROGRAM_FILENAME,
    record_file_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_review_guard import (
    REVIEW_GUARD_PROGRAM_FILENAME,
    review_guard_program_source,
)

__all__: list[str] = [
    "GH_REFRESH_ROOT",
    "HELPER_ROOTS",
    "LIVESPEC_ROOT",
    "LIVESPEC_SANDBOX_ROOT_PATH",
    "PLUGINS_ROOT",
    "Helper",
    "helper_digest",
    "helper_manifest",
    "helper_manifest_text",
    "helper_registry",
]

# The three named sandbox roots a helper's `path` is relative to.
PLUGINS_ROOT = "plugins"
GH_REFRESH_ROOT = "gh-refresh"
LIVESPEC_ROOT = "livespec"
HELPER_ROOTS = (PLUGINS_ROOT, GH_REFRESH_ROOT, LIVESPEC_ROOT)
# The fixed sandbox directory the credential-use guard and the proof-capture
# launcher live in, read off the guard's own path so the two cannot drift.
LIVESPEC_SANDBOX_ROOT_PATH = str(PurePosixPath(GUARD_SCRIPT_PATH).parent)

_PRIVATE_EXECUTABLE = 0o700
_EXECUTABLE = 0o755
_READABLE = 0o644
# The plugins-root programs a node executes directly rather than through an
# interpreter; every other plugins-root program is read by `python3`.
_PRIVATE_PROGRAMS = frozenset(
    (PUBLICATION_PUSH_PROGRAM_FILENAME, COMMIT_RED_PROGRAM_FILENAME, COMMIT_GREEN_PROGRAM_FILENAME)
)
_MERGE_FILENAME = HARNESS_SETTINGS_MERGE_PROGRAM_FILENAME


@dataclass(frozen=True, kw_only=True)
class Helper:
    """One helper program: its name, where it lands, its mode, and what composes its bytes."""

    name: str
    root: str
    path: str
    mode: int
    compose: Callable[[], bytes]


def _text(*, source: Callable[[], str]) -> Callable[[], bytes]:
    return lambda: source().encode("utf-8")


def _constant(*, text: str) -> Callable[[], bytes]:
    return lambda: text.encode("utf-8")


def _file(*, path: Path) -> Callable[[], bytes]:
    return path.read_bytes


def _plugin_root_programs() -> tuple[Helper, ...]:
    """Every program that lands directly below the sandbox plugins root."""
    named: tuple[tuple[str, str, Callable[[], str]], ...] = (
        ("plugin-cache-gate", PLUGIN_GATE_PROGRAM_FILENAME, plugin_cache_gate_program_source),
        ("publication-head", PROOF_HEAD_PROGRAM_FILENAME, proof_head_program_source),
        ("publication-push", PUBLICATION_PUSH_PROGRAM_FILENAME, publication_push_program_source),
        ("carry-forward", CARRY_FORWARD_PROGRAM_FILENAME, carry_forward_program_source),
        ("proof-grade", PROOF_GRADE_PROGRAM_FILENAME, proof_grade_program_source),
        ("record-file-resolution", RECORD_FILE_PROGRAM_FILENAME, record_file_program_source),
        ("record-file-merge", RECORD_FILE_MERGE_PROGRAM_FILENAME, record_file_merge_program_source),
        ("hook-limit", HOOK_LIMIT_PROGRAM_FILENAME, hook_limit_program_source),
        ("commit-runner", COMMIT_RUNNER_PROGRAM_FILENAME, commit_runner_program_source),
        ("commit-red", COMMIT_RED_PROGRAM_FILENAME, commit_red_program_source),
        ("commit-green", COMMIT_GREEN_PROGRAM_FILENAME, commit_green_program_source),
        ("review-guard", REVIEW_GUARD_PROGRAM_FILENAME, review_guard_program_source),
        ("harness-settings-merge", _MERGE_FILENAME, harness_settings_merge_program),
    )
    programs = tuple(
        Helper(
            name=name,
            root=PLUGINS_ROOT,
            path=path,
            mode=_PRIVATE_EXECUTABLE if path in _PRIVATE_PROGRAMS else _READABLE,
            compose=_text(source=source),
        )
        for name, path, source in named
    )
    readers = tuple(
        Helper(
            name=f"proof-record-reader/{module}",
            root=PLUGINS_ROOT,
            path=f"{PROOF_GRADE_READER_DIRECTORY}/{module}",
            mode=_READABLE,
            compose=_constant(text=source),
        )
        for module, source in proof_record_reader_sources()
    )
    return programs + readers


def _gh_refresh_helpers(*, scripts_root: Path) -> tuple[Helper, ...]:
    """The refreshing `gh` wrapper's fixed pieces and, file by file, its vendored support."""
    fixed = (
        Helper(
            name="gh-mint-helper",
            root=GH_REFRESH_ROOT,
            path=GH_MINT_HELPER_RELPATH,
            mode=_EXECUTABLE,
            compose=_text(source=gh_mint_helper_source),
        ),
        Helper(
            name="gh-push-origin",
            root=GH_REFRESH_ROOT,
            path=GH_PUSH_HELPER_RELPATH,
            mode=_EXECUTABLE,
            compose=_constant(text=PUSH_ORIGIN_SOURCE),
        ),
        Helper(
            name="gh-wrapper-tail",
            root=GH_REFRESH_ROOT,
            path=GH_WRAPPER_TAIL_RELPATH,
            mode=_READABLE,
            compose=_text(source=gh_wrapper_tail_source),
        ),
    )
    support = tuple(
        Helper(
            name=f"gh-refresh-support/{relpath.as_posix()}",
            root=GH_REFRESH_ROOT,
            path=relpath.as_posix(),
            mode=_READABLE,
            compose=_file(path=scripts_root / relpath),
        )
        for relpath in github_auth_support_relpaths(scripts_root=scripts_root)
    )
    return fixed + support


def _credential_use_helpers() -> tuple[Helper, ...]:
    """The credential-use guard and the proof-capture launcher and hooks."""
    guard = Helper(
        name="credential-use-guard",
        root=LIVESPEC_ROOT,
        path=_livespec_relative(sandbox_path=GUARD_SCRIPT_PATH),
        mode=_PRIVATE_EXECUTABLE,
        compose=_text(source=guard_script_text),
    )
    assets = tuple(
        Helper(
            name=f"proof-capture/{_livespec_relative(sandbox_path=sandbox_path)}",
            root=LIVESPEC_ROOT,
            path=_livespec_relative(sandbox_path=sandbox_path),
            mode=_PRIVATE_EXECUTABLE,
            compose=_constant(text=text),
        )
        for sandbox_path, text in proof_capture_asset_sources()
    )
    return (guard, *assets)


def _livespec_relative(*, sandbox_path: str) -> str:
    return str(PurePosixPath(sandbox_path).relative_to(LIVESPEC_SANDBOX_ROOT_PATH))


def helper_registry(*, scripts_root: Path | None = None) -> tuple[Helper, ...]:
    """Every helper program, in the order the setup step writes them.

    `scripts_root` is the plugin's `scripts/` directory the vendored support files
    are read from; it defaults to the tree this module itself was imported from,
    which is the installed build on the host and the fetched checkout in the
    sandbox.
    """
    root = Path(__file__).resolve().parents[2] if scripts_root is None else scripts_root
    return (
        _plugin_root_programs() + _gh_refresh_helpers(scripts_root=root) + _credential_use_helpers()
    )


def helper_digest(*, composed: bytes) -> str:
    """The sha256 the manifest records for one helper's composed bytes."""
    return hashlib.sha256(composed).hexdigest()


def helper_manifest(
    *, repository: str, commit: str, helpers: tuple[Helper, ...] | None = None
) -> dict[str, object]:
    """The manifest a dispatch's run configuration carries in place of the helpers' bytes."""
    listed = helper_registry() if helpers is None else helpers
    return {
        "repository": repository,
        "commit": commit,
        "helpers": [
            {
                "name": helper.name,
                "root": helper.root,
                "path": helper.path,
                "mode": helper.mode,
                "sha256": helper_digest(composed=helper.compose()),
            }
            for helper in listed
        ],
    }


def helper_manifest_text(*, repository: str, commit: str) -> str:
    """The manifest as the one compact JSON line the setup step's env value carries."""
    return json.dumps(helper_manifest(repository=repository, commit=commit), separators=(",", ":"))
