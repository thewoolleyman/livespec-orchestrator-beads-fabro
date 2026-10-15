"""The sandbox-local tmux socket root the Dispatcher overlay materializes.

Split out of `_dispatcher_overlay` by cohesion once the socket root gained its
worktree exclusion: that file ASSEMBLES the overlay, while this — like
`_dispatcher_codex_auth_projection`, `_dispatcher_gh_refresh` and every other
Dispatcher-materialized `/workspace` path — is ONE projection, carrying the
path, the prepare steps that make it, and the `[environments.<id>.env]` line
that tells the sandbox where it is. Keeping the three together is the point:
the exclusion, the creation and `TMUX_TMPDIR` must all name the same
directory, and splitting them across modules is how two of them come to name
different ones.
"""

from __future__ import annotations

import json

from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_worktree_exclude import (
    worktree_exclude_script,
)

__all__: list[str] = [
    "tmux_tmpdir_env_lines",
    "tmux_tmpdir_prepare_steps_block",
]

# Sandbox-local tmux socket root. tmux appends its own tmux-<uid>/default
# socket below TMUX_TMPDIR, so bare `tmux kill-server` inside a Fabro sandbox
# resolves only sandbox-local sockets and never the host default under /tmp.
#
# IT IS A FIXED `/workspace` PATH, so on the Petri-era engine — where the
# repository clone IS `/workspace` — it lands INSIDE the repository, and that
# engine checkpoints after every graph node. The prepare step creates only the
# root, which git does not track; tmux populates it LATER, while the agent
# nodes drive, and those nodes checkpoint too, so without the exclusion below
# the state reaches the run branch and the draft pull request's diff.
# `_dispatcher_sandbox_worktree_exclude` carries the whole mechanism.
_SANDBOX_TMUX_TMPDIR = "/workspace/.tmux"


def tmux_tmpdir_prepare_steps_block() -> str:
    """Render the exclude + create `[[run.prepare.steps]]` blocks for the socket root.

    The EXCLUDE step comes first, and its position is load-bearing for the
    same reason it is at the three sibling call sites: the Petri-era engine
    checkpoints after every prepare step, so a step that writes under the root
    before the exclusion is in place is a step whose checkpoint commits it.

    THE WHOLE SOCKET ROOT IS NAMED rather than one file inside it, which is
    the one case `_dispatcher_sandbox_worktree_exclude`'s narrowness rule
    admits: that rule asks a projection writing ONE FILE to name that file,
    and this step writes no file at all — it creates a root that the sandbox's
    tmux server then populates with paths no step here can spell. There is no
    narrower path available, and anything tmux puts under it is as committable
    as the root itself.

    The exclusion changes nothing about tmux: `TMUX_TMPDIR` still names this
    directory, so a sandbox-local `tmux kill-server` still resolves only
    sandbox-local sockets. Hiding it from git is not hiding it from tmux.
    """
    exclude = worktree_exclude_script(
        paths=(_SANDBOX_TMUX_TMPDIR,),
        label="livespec-sandbox-tmux",
    )
    script = f"mkdir -p {_SANDBOX_TMUX_TMPDIR} && chmod 700 {_SANDBOX_TMUX_TMPDIR}"
    lines = [
        "",
        "# --- Dispatcher-materialized sandbox-local tmux socket root: hide it",
        "# --- from the run's worktree, then create it ---",
        "[[run.prepare.steps]]",
        f"script = {json.dumps(exclude)}",
        "",
        "[[run.prepare.steps]]",
        f"script = {json.dumps(script)}",
    ]
    return "\n".join(lines) + "\n"


def tmux_tmpdir_env_lines() -> str:
    """Render the `TMUX_TMPDIR` `[environments.<id>.env]` line.

    One line, rendered unconditionally: every sandbox gets the socket root,
    because the root is what keeps a sandbox-local `tmux kill-server` away
    from the host default. The value is `json.dumps`-ed for the same reason
    every other line in that table is — the table is TOML, and a value
    written raw is a parse hazard rather than a string.
    """
    return f"TMUX_TMPDIR = {json.dumps(_SANDBOX_TMUX_TMPDIR)}\n"
