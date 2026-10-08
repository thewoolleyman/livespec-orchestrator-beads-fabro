"""What a dispatched sandbox needs in order to see its family siblings.

Split out of `_dispatcher_overlay` by COHESION: the overlay's job is to render a
run config, while this module answers one narrower question — which family repos
a dispatched sandbox clones, where they land, and which env keys point at them.
Three surfaces serve that one question (the plan, the prepare steps that realize
it, and the core-plugin projection that depends on a particular sibling being
among them), and nothing else in the overlay reads any of them.

IT IS A LEAF, DELIBERATELY. `_dispatcher_sibling_clones` RESOLVES the plan and
`_dispatcher_overlay` RENDERS it, so both depend on the type; defining it in
either would make the other's import an edge back into a module that already
imports it. Nothing here imports from either.

The two functions are PUBLIC because they now cross a module boundary, which is
what the private-call rule requires: a `_`-prefixed name imported from another
module is rejected by pyright strict and by the `private_calls` check alike.
Their bodies, their docstrings and every measurement those docstrings record
moved VERBATIM — the rationale for the per-member failure tolerance and for
`GIT_TERMINAL_PROMPT=0` is the design record of a real fleet outage and a real
misdiagnosis, and it belongs with the code it explains.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

__all__: list[str] = [
    "CORE_PLUGIN_ROOT_ENV_VAR",
    "SIBLING_CLONES_ROOT_ENV_VAR",
    "SiblingClones",
    "core_plugin_env_line",
    "sibling_clone_steps_block",
]

SIBLING_CLONES_ROOT_ENV_VAR = "LIVESPEC_SIBLING_CLONES_ROOT"

# The env-var a fleet repo's janitor reads to resolve the livespec CORE plugin
# inside the Fabro sandbox (the console's `check-doctor-static`). The sandbox
# spawns with a fail-closed env allowlist (fabro-server/src/spawn_env.rs) and
# carries no installed-plugin registry, so without this projection a
# CORE-dependent `just check` cannot find core. The Dispatcher's overlay
# projects it at the in-sandbox core-sibling clone path
# (`<clones_root>/livespec/.claude-plugin`); `_CORE_SIBLING_SLUG` is the livespec
# CORE repo's clone slug.
CORE_PLUGIN_ROOT_ENV_VAR = "LIVESPEC_CORE_PLUGIN_ROOT"
_CORE_SIBLING_SLUG = "livespec"


@dataclass(frozen=True, kw_only=True)
class SiblingClones:
    """The per-dispatch sandbox sibling-clone plan.

    `repos` is the fleet member set MINUS the dispatch target (the
    target is already the sandbox workspace clone); `clones_root` is
    the in-sandbox directory the clones land under — the same path the
    overlay projects as `LIVESPEC_SIBLING_CLONES_ROOT`.
    """

    owner: str
    repos: tuple[str, ...]
    clones_root: str


def core_plugin_env_line(*, siblings: SiblingClones | None) -> str:
    """Project LIVESPEC_CORE_PLUGIN_ROOT at the in-sandbox core-sibling clone.

    A fleet repo whose janitor resolves the livespec CORE plugin (the console's
    `check-doctor-static`) cannot find core inside the sandbox: the worker env
    is a fail-closed allowlist and the container carries no installed-plugin
    registry. So the overlay projects CORE's location as a container-level env
    key — the SAME mechanism that carries GITHUB_TOKEN — valued at the cloned core
    sibling's plugin root (`<clones_root>/livespec/.claude-plugin`). Returns the
    empty string when no core sibling is cloned (the derived path would not
    resolve), mirroring the sibling-clones-root guard.
    """
    if siblings is None or _CORE_SIBLING_SLUG not in siblings.repos:
        return ""
    core_plugin_root = f"{siblings.clones_root}/{_CORE_SIBLING_SLUG}/.claude-plugin"
    return f"{CORE_PLUGIN_ROOT_ENV_VAR} = {json.dumps(core_plugin_root)}\n"


def sibling_clone_steps_block(*, siblings: SiblingClones) -> str:
    """Render the appended sibling-clone `[[run.prepare.steps]]` blocks.

    One step per fleet member (the dispatch target is excluded
    upstream): a depth-1 default-branch `git clone` into
    `<clones_root>/<repo>` — mirroring how livespec CI provisions the
    `LIVESPEC_SIBLING_CLONES_ROOT` siblings-root for the cross-repo
    wiring check. Plain `git clone` over https is used (NOT `gh`): the
    sandbox clones its own workspace repo the same way, while `gh api`
    is unauthenticated there.

    Each step TOLERATES its own member's failure: a member that cannot
    be cloned is reported as a one-line stderr diagnostic and skipped
    (`exit 0`), never failing the whole prepare step. The manifest is
    fetched fresh from livespec master on every dispatch, so an entry
    naming a repo that does not exist YET (registration precedes birth)
    would otherwise kill every dispatch across the fleet — the
    2026-08-15 livespec-driver-pi outage. Manifest consumers other than
    the conformance check MUST degrade per-member: livespec core
    `SPECIFICATION/non-functional-requirements.md`, Fleet membership
    contract / Repo birth procedure, ratified v210.

    `GIT_TERMINAL_PROMPT=0` on both git invocations is what makes the
    diagnostic honest: without it, an unreachable repo makes git's https
    backend fall back to a credential prompt, which in the TTY-less
    sandbox surfaces as `could not read Username ... No such device or
    address` and reads as an auth failure (it cost a real
    misdiagnosis). The explicit `git ls-remote --exit-code` probe then
    separates "repository not reachable (nonexistent or no access)"
    from a "clone failed after a successful reachability probe
    (transient)". Only the `mkdir` can fail the step. On the
    all-members-healthy path the observable result is unchanged: the
    same depth-1 quiet https clone into the same `<clones_root>/<repo>`.
    """
    lines: list[str] = [
        "",
        "# --- Dispatcher-materialized sibling clones (from livespec master's",
        "# --- .livespec-fleet-manifest.jsonc): depth-1 default-branch clones so",
        "# --- cross-repo checks resolve every family sibling under",
        f"# --- {siblings.clones_root} inside the sandbox ---",
    ]
    for repo_name in siblings.repos:
        url = f"https://github.com/{siblings.owner}/{repo_name}.git"
        diagnostic = (
            "livespec-orchestrator-beads-fabro dispatcher: sibling clone skipped"
            f" for {repo_name}: "
        )
        script = (
            f"mkdir -p {siblings.clones_root} || exit 1;"
            f" GIT_TERMINAL_PROMPT=0 git ls-remote --exit-code {url} HEAD"
            " >/dev/null 2>&1 ||"
            f" {{ echo '{diagnostic}repository not reachable"
            " (nonexistent or no access)' >&2; exit 0; };"
            f" GIT_TERMINAL_PROMPT=0 git clone --quiet --depth 1 {url}"
            f" {siblings.clones_root}/{repo_name} ||"
            f" {{ echo '{diagnostic}clone failed after a successful"
            " reachability probe (transient)' >&2; exit 0; }"
        )
        lines.append("[[run.prepare.steps]]")
        lines.append(f"script = {json.dumps(script)}")
    return "\n".join(lines) + "\n"
