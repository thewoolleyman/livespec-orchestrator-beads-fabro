"""The clones a sandbox RUNS other repositories' tools from, and how they follow the tree.

WHAT THIS DEFENDS AGAINST (run 01M6Y1Q7ZFWZ, `bd-ib-bacahf`). The run failed
`check-doctor-static` with a `RecursionError` from a livespec checker cloned at a
0.47.0-era tip, while the tree it had refreshed onto pinned v0.47.1 and passed CI.
The sandbox's checker version was set by WHEN THE POD STARTED, not by the tree under
test: the checker was read out of a depth-1 default-branch clone under
`/livespec-siblings`, which is also the checkout the agent reads and edits.

THE CONTRACT (`SPECIFICATION/contracts.md` "A sandbox runs its tools from pinned
clones and works in the latest clones"). Two kinds of clone of another repository,
never used for each other's purpose. A WORK clone is the default branch's latest
commit, writable and deep enough to debug in; `_dispatcher_overlay_siblings` renders
those. A RUN-FROM clone is what this module owns: it is separate from every work
clone, checked out at the release the governed tree declares for that repository
(for livespec core, `.livespec.jsonc` `compat.pinned`, the very ref the repository's
CI checks core out at), shallow, and read-only. A repository the tree declares no
release for is taken at its newest release tag, NEVER its default-branch tip.

WHY A PROGRAM THE SANDBOX RUNS, NOT A CLONE COMMAND. The release is a fact about the
tree under test, and the tree changes during a run: the janitor refresh and both
publication refreshes move the run onto a default branch that may pin a different
release. The contract requires each run-from clone's release to be RE-RESOLVED from
the refreshed tree and any clone whose release changed to be re-cloned BEFORE that
tree is checked. A prepare-step clone command runs once; a program that is written to
disk, as the plugin-cache gate and the publication helpers are, can be run again by
each node that checks a refreshed tree. The program is therefore one idempotent
`ensure` over every planned repository, run at prepare time and again before every
declared check suite.

WHY THE PROGRAM HOLDS ITS OWN PIN READER. The sandbox clone is the GOVERNED
repository, which carries no copy of this plugin, so the program is stdlib-only and
reads the declaration itself. It reads the same key this plugin's own contract reads
(`livespec-orchestrator-beads-fabro.compat.pinned`), through a JSONC reader that
treats an unreadable file as declaring nothing, as the host-side janitor does. A
declared value is honored VERBATIM, branch or tag, because the repository chose it;
only an ABSENT declaration falls to the newest release tag.

THE FAILURE POLICY HAS THREE ARMS, and they are not interchangeable. A repository the
forge cannot reach is SKIPPED with a diagnostic and exit 0, exactly as an unborn
sibling is, because registration precedes birth and one absent repository must not
kill every dispatch. A repository that is reachable but whose declared release does
not exist, or which declares none and publishes no release tag, FAILS CLOSED: the
only available substitute is a checkout the declaration did not choose, which is the
incident again. And a failed RE-clone leaves the clone already on disk in place
rather than half-replacing it, because the new tree is cloned beside it and swapped in
only once it is whole.

WHAT READ-ONLY CAN AND CANNOT MEAN HERE. The program strips every write bit and asks
for the immutable flag, then PROBES with a real write and REPORTS which of two
markers is true. That reporting is the design, not decoration: measured in a family
sandbox, a root process holds CAP_DAC_OVERRIDE (write bits do not bind it) and neither
CAP_LINUX_IMMUTABLE nor CAP_SYS_ADMIN (no immutable flag, no read-only bind mount),
so on that image the clone is writable by the very processes the contract names no
matter what a prepare step does. The enforcement is a property of the sandbox image
and the user its agent runs as, which lands in livespec-dev-tooling through a
cross-tenant execution mirror; this program uses it the moment it exists and says
plainly, in the setup log, when it does not. Claiming `read-only` on the strength of
a `chmod` that root ignores would be the one answer a later reader cannot check.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_declaration import (
    PLUGIN_BLOCK,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay_siblings import (
    RUN_FROM_CLONES_ROOT,
    RUN_FROM_CLONES_ROOT_ENV_VAR,
    SIBLING_CLONES_ROOT_ENV_VAR,
    SiblingClones,
    core_plugin_env_line,
    sibling_clone_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_prepare_payload import (
    PAYLOAD_ENV_VAR,
    PrepareStep,
    pack_payload,
    packed_payload_write_command,
    render_prepare_step,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    sandbox_plugins_root_expansion,
)

__all__: list[str] = [
    "RUN_FROM_CLONES_ROOT",
    "RUN_FROM_FAILED_MARKER",
    "RUN_FROM_PROGRAM_FILENAME",
    "RUN_FROM_READ_ONLY_MARKER",
    "RUN_FROM_REPOS",
    "RUN_FROM_WRITABLE_MARKER",
    "SandboxCloneFragments",
    "run_from_clone_steps_block",
    "run_from_clones_env_line",
    "run_from_program_source",
    "run_from_repos",
    "sandbox_clone_fragments",
]

# EVERY CROSS-REPOSITORY TOOL A SANDBOX EXECUTES, enumerated rather than assumed. The
# fleet scope of work-item `bd-ib-lupzxt` is "every repository whose tools run in a
# sandbox", with livespec core's checker the measured case and not the whole scope, so
# the family was read for what actually executes out of another repository's checkout:
# every `LIVESPEC_CORE_PLUGIN_ROOT` and `LIVESPEC_SIBLING_CLONES_ROOT` consumer in the
# eight sibling repositories' recipes and scripts (2026-11-10). The result is ONE
# executed tool, livespec core's doctor checks, which each repository's
# `check-doctor-static` runs through `LIVESPEC_CORE_PLUGIN_ROOT`; the drivers, the
# runtime and the dev-tooling package reach a sandbox as pinned dependencies or
# vendored code, and every other `LIVESPEC_SIBLING_CLONES_ROOT` consumer READS the
# work clones (livespec's `wiring-completeness-cross-repo`, run FROM the core clone,
# reads the siblings). A repository added here gets a run-from clone with no other
# change, and a repository that starts executing another's tool owes an entry.
RUN_FROM_REPOS: tuple[str, ...] = ("livespec",)

# The program the prepare step writes below the plugins root and every refreshing
# node re-runs. A constant, because the prepare step that writes it and the graph
# nodes that run it must agree on one name.
RUN_FROM_PROGRAM_FILENAME = "livespec-run-from-clones.py"

# The named conditions the program reports on stderr, constants for the reason the
# plugin-cache gate's are: the sandbox emits them, the graph nodes report them and
# the tests prove them, and a signature nobody can grep for is not one.
RUN_FROM_FAILED_MARKER = "LIVESPEC_RUN_FROM_CLONE_FAILED"
RUN_FROM_READ_ONLY_MARKER = "LIVESPEC_RUN_FROM_CLONE_READ_ONLY"
RUN_FROM_WRITABLE_MARKER = "LIVESPEC_RUN_FROM_CLONE_WRITABLE"

# Where the program reads the release each repository's tools are pinned at. A
# mapping because only livespec core has a declared key today; a repository absent
# from it is "declares nothing" and runs from its newest release tag.
_DECLARED_RELEASE_KEYS = {"livespec": "pinned"}

# Stdlib-only and free of any livespec import, for the reason the module docstring
# gives. Every diagnostic goes to stderr so it lands in the run's setup log. The
# `@@...@@` tokens are substituted at render time; the program has no other
# deployment-time input.
_PROGRAM_SOURCE = r"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PLAN = json.loads(@@PLAN@@)
FAILED = "@@FAILED@@"
READ_ONLY = "@@READ_ONLY@@"
WRITABLE = "@@WRITABLE@@"
PLUGIN_BLOCK = "@@PLUGIN_BLOCK@@"
DECLARED_KEYS = json.loads(@@DECLARED_KEYS@@)
RELEASE = re.compile(r"^v?(\d+)[.](\d+)[.](\d+)$")
PROBE = ".livespec-write-probe"


def note(message):
    sys.stderr.write("livespec run-from clones: " + message + "\n")


def git(*args):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          check=False, env=env)


def quietly(argv):
    # A missing `chattr` is the same answer as a refused one: no flag was set.
    try:
        subprocess.run(argv, capture_output=True, check=False)
    except OSError:
        pass


def project_root():
    # The node runs at the clone root, which is where the declaration lives; ask git
    # only when it does not, so a checkout nested in another repository still reads
    # its own file first.
    here = Path.cwd()
    if (here / ".livespec.jsonc").is_file():
        return here
    top = git("rev-parse", "--show-toplevel")
    found = top.stdout.strip()
    return Path(found) if top.returncode == 0 and found else here


def strip_jsonc(text):
    kept = []
    index = 0
    quoted = False
    while index < len(text):
        char = text[index]
        pair = text[index:index + 2]
        if quoted and char == "\\":
            kept.append(pair)
            index += 2
            continue
        if char == '"':
            quoted = not quoted
        if not quoted and pair == "//":
            end = text.find("\n", index)
            index = len(text) if end == -1 else end
            continue
        if not quoted and pair == "/*":
            end = text.find("*/", index + 2)
            index = len(text) if end == -1 else end + 2
            continue
        kept.append(char)
        index += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(kept))


def declared_release(repo, project):
    # None is "declares nothing": no key for this repository, no file, an unreadable
    # file or an empty value all read the same, so the newest release tag governs.
    key = DECLARED_KEYS.get(repo)
    config = project / ".livespec.jsonc"
    if key is None or not config.is_file():
        return None
    try:
        document = json.loads(strip_jsonc(config.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        note("could not read " + str(config) + "; treating " + repo
             + " as declaring no release")
        return None
    block = document.get(PLUGIN_BLOCK) if isinstance(document, dict) else None
    compat = block.get("compat") if isinstance(block, dict) else None
    value = compat.get(key) if isinstance(compat, dict) else None
    return value if isinstance(value, str) and value else None


def newest_release_tag(url):
    # Release tags are plain versions. A pre-release suffix is not a release, so
    # `v1.0.0-rc.1` never outranks `v0.47.2`, and ordering is numeric, so `v0.10.0`
    # outranks `v0.9.0`.
    listing = git("ls-remote", "--tags", "--refs", url)
    releases = []
    for line in listing.stdout.splitlines():
        name = line.rsplit("refs/tags/", 1)[-1]
        found = RELEASE.match(name)
        if found:
            releases.append((tuple(int(part) for part in found.groups()), name))
    return max(releases)[1] if releases else None


def remote_commit(url, ref):
    # The commit `ref` names on the remote: a tag's peeled commit first, then the tag
    # object itself (a lightweight tag), then a branch.
    names = ["refs/tags/" + ref + "^{}", "refs/tags/" + ref, "refs/heads/" + ref]
    listing = git("ls-remote", url, *names)
    shas = {}
    for line in listing.stdout.splitlines():
        sha, _, name = line.partition("\t")
        shas[name] = sha
    for name in names:
        if name in shas:
            return shas[name]
    return None


def discard(path):
    if not path.exists():
        return
    quietly(["chattr", "-R", "-i", str(path)])
    quietly(["chmod", "-R", "u+w", str(path)])
    shutil.rmtree(path, ignore_errors=True)


def lock(path, repo):
    quietly(["chmod", "-R", "a-w", str(path)])
    quietly(["chattr", "-R", "+i", str(path)])
    probe = path / PROBE
    try:
        probe.touch(exist_ok=False)
    except OSError:
        note(READ_ONLY + ": " + repo + " at " + str(path)
             + " refuses a write by uid " + str(os.getuid()))
        return
    probe.unlink()
    note(WRITABLE + ": " + repo + " at " + str(path) + " accepted a write by uid "
         + str(os.getuid()) + "; the write bits are stripped, but this sandbox"
         " grants that user a capability that bypasses them, so read-only needs the"
         " sandbox image change")


def reclone(repo, url, release, dest):
    # The new tree is cloned BESIDE the current one and swapped in only once whole, so
    # a failed re-clone leaves the clone the run was already using.
    staging = dest.parent / ("." + repo + ".staging")
    discard(staging)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cloned = git("clone", "--quiet", "--depth", "1", "--branch", release, url,
                 str(staging))
    if cloned.returncode != 0:
        note(FAILED + ": could not clone " + repo + " at " + release + ": "
             + cloned.stderr.strip())
        discard(staging)
        return 1
    discard(dest)
    staging.rename(dest)
    lock(dest, repo)
    note("cloned " + repo + " at " + release + " into " + str(dest))
    return 0


def ensure(repo, project):
    dest = Path(PLAN["root"]) / repo
    url = PLAN["url_base"] + "/" + repo + ".git"
    if git("ls-remote", "--exit-code", url, "HEAD").returncode != 0:
        note("skipped " + repo + ": repository not reachable (nonexistent or no access)")
        return 0
    declared = declared_release(repo, project)
    release = declared or newest_release_tag(url)
    if release is None:
        note(FAILED + ": " + repo + " declares no release in .livespec.jsonc and"
             " publishes no release tag, so there is nothing to run its tools from")
        return 1
    source = "declared" if declared else "newest release tag, none declared"
    wanted = remote_commit(url, release)
    if wanted is None:
        note(FAILED + ": " + repo + " release " + release + " (" + source
             + ") does not exist at " + url)
        return 1
    current = git("-C", str(dest), "rev-parse", "HEAD") if dest.is_dir() else None
    if current is not None and current.returncode == 0 and current.stdout.strip() == wanted:
        note(repo + " already at " + release + " (" + source + ")")
        return 0
    return reclone(repo, url, release, dest)


project = project_root()
status = 0
for repo in PLAN["repos"]:
    status = max(status, ensure(repo, project))
raise SystemExit(status)
"""


def run_from_repos(*, siblings: SiblingClones | None) -> tuple[str, ...]:
    """The planned repositories a run-from clone is taken of, in `RUN_FROM_REPOS` order.

    A repository is planned only when it is among the fleet members the sandbox
    clones: the dispatch target is excluded from those, and a target's OWN tooling
    runs from its own clone, which is the tree under test. That is also what keeps
    the `LIVESPEC_CORE_PLUGIN_ROOT` projection from naming a path no step creates.
    """
    if siblings is None:
        return ()
    return tuple(repo for repo in RUN_FROM_REPOS if repo in siblings.repos)


def run_from_program_source(*, url_base: str, root: str, repos: tuple[str, ...]) -> str:
    """The program, with this dispatch's plan substituted in.

    `url_base` is everything before `/<repo>.git`, so a test can point the one
    program at a local bare repository instead of the forge.
    """
    plan = json.dumps({"url_base": url_base, "root": root, "repos": list(repos)})
    program = _PROGRAM_SOURCE
    for token, value in (
        ("@@PLAN@@", repr(plan)),
        ("@@DECLARED_KEYS@@", repr(json.dumps(_DECLARED_RELEASE_KEYS))),
        ("@@FAILED@@", RUN_FROM_FAILED_MARKER),
        ("@@READ_ONLY@@", RUN_FROM_READ_ONLY_MARKER),
        ("@@WRITABLE@@", RUN_FROM_WRITABLE_MARKER),
        ("@@PLUGIN_BLOCK@@", PLUGIN_BLOCK),
    ):
        program = program.replace(token, value)
    return program.strip() + "\n"


def run_from_clone_steps_block(
    *,
    siblings: SiblingClones,
    remote_base: str = "https://github.com",
    run_from_root: str = RUN_FROM_CLONES_ROOT,
) -> str:
    """The prepare step that materializes the program and takes the run-from clones.

    Empty when nothing is planned: a target that IS livespec, or a fleet with no
    livespec among its members, has no tool to run from another checkout, and the
    program is then not materialized at all -- which is why the refreshing nodes
    run it only when it exists. The program rides the step's `env`, written with
    `printf %s`, and is written BEFORE it is run so the nodes that check a refreshed
    tree have something on disk to re-enter. `exec` makes its exit code the step's,
    so a declared release that cannot be satisfied stops the run in setup rather
    than after the hour of agent nodes the incident spent.

    `remote_base` and `run_from_root` default to the forge and the sandbox's own
    path; they exist so a test can run the rendered step for real against a local
    repository in a scratch directory.
    """
    repos = run_from_repos(siblings=siblings)
    if not repos:
        return ""
    program = run_from_program_source(
        url_base=f"{remote_base}/{siblings.owner}", root=run_from_root, repos=repos
    )
    script = "\n".join(
        [
            "set -eu",
            f'root="{sandbox_plugins_root_expansion()}"',
            'mkdir -p "$root"',
            packed_payload_write_command(path_word=f'"$root/{RUN_FROM_PROGRAM_FILENAME}"'),
            f'exec python3 "$root/{RUN_FROM_PROGRAM_FILENAME}"',
        ]
    )
    header = (
        "\n# --- Dispatcher-materialized run-from clones: shallow, read-only clones"
        " of the repositories whose tools this sandbox executes, at the release the"
        f" governed tree pins, under {run_from_root} ---\n"
    )
    return header + render_prepare_step(
        step=PrepareStep(script=script, env={PAYLOAD_ENV_VAR: pack_payload(text=program)})
    )


def run_from_clones_env_line(*, siblings: SiblingClones | None) -> str:
    """The non-secret env line naming the run-from root; empty when nothing is planned."""
    if not run_from_repos(siblings=siblings):
        return ""
    return f"{RUN_FROM_CLONES_ROOT_ENV_VAR} = {json.dumps(RUN_FROM_CLONES_ROOT)}\n"


@dataclass(frozen=True, kw_only=True)
class SandboxCloneFragments:
    """Everything the overlay appends for a sandbox's clones of other repositories.

    `steps` is the `[[run.prepare.steps]]` text, WORK clones first and the run-from
    program after them; `env_lines` is the non-secret env text that points at both
    kinds. They travel together because the env lines name paths only the steps
    create, so rendering one without the other is how a sandbox ends up with an env
    key naming a directory nothing cloned.
    """

    steps: str
    env_lines: str


def sandbox_clone_fragments(*, siblings: SiblingClones | None) -> SandboxCloneFragments:
    """The steps and env lines for BOTH kinds of clone, empty when no fleet is planned.

    The one composition the overlay calls, so the two kinds are rendered together or
    not at all. It lives here and not in the overlay because the overlay sits at its
    file LLOC ceiling and renders a run config, while this answers which clones a
    dispatched sandbox takes and which env keys point at them.
    """
    if siblings is None:
        return SandboxCloneFragments(steps="", env_lines="")
    return SandboxCloneFragments(
        steps=sibling_clone_steps_block(siblings=siblings)
        + run_from_clone_steps_block(siblings=siblings),
        env_lines=f"{SIBLING_CLONES_ROOT_ENV_VAR} = {json.dumps(siblings.clones_root)}\n"
        + core_plugin_env_line(siblings=siblings)
        + run_from_clones_env_line(siblings=siblings),
    )
