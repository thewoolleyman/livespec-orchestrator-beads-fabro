"""The setup step that fetches this plugin at the installed build's commit and lands its helpers.

`SPECIFICATION/contracts.md` section "Self-contained plugin dispatch", paragraph
"Helper programs are fetched in the sandbox from the dispatching build's own
commit". This renders ONE ordinary prepare step, first among the Dispatcher's
own, so the setup-node splice (`_dispatcher_setup_nodes`) turns it into a
`run_prepare_<N>` node like every other step and it re-runs when a resumed run
re-acquires its sandbox.

THE SCRIPT IS SHORT AND CARRIES NO HELPER SOURCE. The engine renders a completed
command stage's script into the prompt of every later agent stage, so the step
carries only the fetch and one call: a sparse, shallow checkout of this plugin's
`scripts/` and `.fabro/` trees at the manifest's commit (`fetch --depth=1
--filter=blob:none`, measured at 0.68 s to fetch and 1.84 s to check out, research
note 004), then the CHECKOUT's own materializer (`_dispatcher_helper_materialize`).
The manifest rides the step's `env` and reaches the materializer on standard
input, which survives the setup-node splice renaming the variable.

EVERY FAILURE IS NAMED. A commit the forge does not serve, a materializer missing at
it, and anything the materializer refuses all end the step non-zero with
`LIVESPEC_PREPARE_PAYLOAD_DIGEST_MISMATCH: <helper>: <reason>`, and a failed setup
step ends the run before `dod_gate` (`_dispatcher_setup_nodes`).

THE ROOTS ARE RESOLVED THE WAY THEIR CONSUMERS RESOLVE THEM. The plugins root is
the shell expansion every consuming step uses, the refreshing-`gh` bundle root is
resolved host-side exactly as `_dispatcher_gh_refresh` resolves it, and the
credential-use guard's directory is the guard's own fixed path. `roots` overrides
them so a test can run the step for real against scratch directories.
"""

from __future__ import annotations

import os
import shlex
from collections.abc import Mapping

from livespec_orchestrator_beads_fabro.commands import _dispatcher_helper_build
from livespec_orchestrator_beads_fabro.commands._dispatcher_gh_refresh import (
    resolve_sandbox_gh_refresh_root,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_helper_build import HelperSource
from livespec_orchestrator_beads_fabro.commands._dispatcher_helper_materialize import (
    HELPER_DIGEST_MISMATCH_CAUSE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_helper_registry import (
    GH_REFRESH_ROOT,
    LIVESPEC_ROOT,
    LIVESPEC_SANDBOX_ROOT_PATH,
    PLUGINS_ROOT,
    helper_manifest_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_prepare_payload import (
    PrepareStep,
    payload_guard_command,
    render_prepare_step,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    sandbox_plugins_root_expansion,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import ShellCommandRunner

__all__: list[str] = [
    "HELPER_MANIFEST_ENV",
    "default_helper_roots",
    "helper_fetch_prepare_step",
    "helper_fetch_prepare_steps_block",
]

HELPER_MANIFEST_ENV = "LIVESPEC_DISPATCH_HELPER_MANIFEST"
_SPARSE_PATHS = ("/.claude-plugin/scripts/", "/.claude-plugin/.fabro/")
_MATERIALIZER = "livespec_orchestrator_beads_fabro/commands/_dispatcher_helper_materialize.py"
_ENTRY = (
    "import sys;from livespec_orchestrator_beads_fabro.commands._dispatcher_helper_materialize"
    " import main;sys.exit(main(argv=sys.argv[1:],manifest_text=sys.stdin.read()))"
)


def default_helper_roots(*, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Each named sandbox root as the step's shell spells it, resolved as its consumers do."""
    env = os.environ if environ is None else environ
    return {
        PLUGINS_ROOT: sandbox_plugins_root_expansion(),
        GH_REFRESH_ROOT: resolve_sandbox_gh_refresh_root(environ=env),
        LIVESPEC_ROOT: LIVESPEC_SANDBOX_ROOT_PATH,
    }


def helper_fetch_prepare_step(
    *, source: HelperSource, roots: Mapping[str, str] | None = None
) -> PrepareStep:
    """The one step: fetch `source.commit` sparse and shallow, then materialize from it."""
    spelled = default_helper_roots() if roots is None else roots
    repository = shlex.quote(source.repository)
    commit = shlex.quote(source.commit)
    arguments = " ".join(f'"{name}={spelled[name]}"' for name in sorted(spelled))
    fail = f"{HELPER_DIGEST_MISMATCH_CAUSE}: helper-manifest:"
    unfetchable = f"commit {source.commit} cannot be fetched from {source.repository}"
    unchecked = f"commit {source.commit} does not check out"
    no_materializer = f"source path {_MATERIALIZER} missing at commit {source.commit}"
    fetch = f"fetch -q --depth=1 --filter=blob:none --no-tags origin {commit}"
    run = f"PYTHONPATH=\"$s:$s/_vendor\" python3 -c '{_ENTRY}' {arguments}"
    script = "\n".join(
        (
            "set -eu",
            "export GIT_TERMINAL_PROMPT=0",
            payload_guard_command(var=HELPER_MANIFEST_ENV),
            f'fail() {{ echo "{fail} $1" >&2; exit 1; }}',
            'c="$(mktemp -d)"',
            "trap 'rm -rf \"$c\"' EXIT",
            'git init -q "$c"',
            f'git -C "$c" sparse-checkout set --no-cone {" ".join(_SPARSE_PATHS)}',
            f'git -C "$c" remote add origin {repository}',
            f'git -C "$c" {fetch} || fail "{unfetchable}"',
            f'git -C "$c" checkout -q --detach FETCH_HEAD || fail "{unchecked}"',
            's="$c/.claude-plugin/scripts"',
            f'test -f "$s/{_MATERIALIZER}" || fail "{no_materializer}"',
            f'printf %s "${HELPER_MANIFEST_ENV}" | (cd "$c" && {run})',
        )
    )
    manifest = helper_manifest_text(repository=source.repository, commit=source.commit)
    return PrepareStep(script=script, env={HELPER_MANIFEST_ENV: manifest})


def helper_fetch_prepare_steps_block(
    *, source: HelperSource | None, roots: Mapping[str, str] | None = None
) -> str | None:
    """The step rendered as overlay TOML, under a header naming what it fetches.

    `source` None reads the installed build's identity from the install record
    the pre-dispatch wall already probed the forge for: a local read, with no
    second forge call. A build with no identity has no commit for the sandbox to
    fetch, so it renders nothing and the caller renders no overlay.
    """
    if source is None:
        source = _dispatcher_helper_build.read_helper_source(runner=ShellCommandRunner())
    if source is None:
        return None
    header = (
        "\n# --- Dispatcher-fetched helper programs: this plugin at the installed"
        f"\n# --- build's commit {source.commit}, every helper digest-verified ---\n"
    )
    return header + render_prepare_step(step=helper_fetch_prepare_step(source=source, roots=roots))
