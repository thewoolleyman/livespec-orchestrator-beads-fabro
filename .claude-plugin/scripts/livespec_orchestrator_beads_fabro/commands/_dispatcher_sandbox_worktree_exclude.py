"""Making a Dispatcher-materialized sandbox path invisible to the run's worktree.

WHY THIS EXISTS AT ALL, which is a fact about the ENGINE rather than about any
one artifact. The Petri-era engine runs each prepare step as a GRAPH NODE and
checkpoints after it, staging every change the step left in the worktree. So a
prepare step that writes a file inside the run's own clone is a step whose
checkpoint COMMITS that file into the run branch -- and from there into the draft
pull request's diff against the default branch, as a change no implementer wrote.

AND WHY IT IS NOT ONE ARTIFACT'S PROBLEM. Whether a materialized path lands
inside the clone is decided by the SANDBOX LAYOUT, which differs by engine: on
the pinned engine the clone is `/workspace/<repo>`, so a `/workspace/...` path
sits outside it and nothing git does can reach it, while on the Petri-era engine
the clone IS `/workspace` and the same path is inside the repository. Every
Dispatcher-materialized `/workspace` path therefore has the defect latent in it,
which is why the mechanism is ONE shared renderer rather than a rule each
projection re-implements. Two have already hit it: the gh-refresh bundle
(`bd-ib-dud2ww`, hp-candidate run 01M4Q45S5AGK, where `publish_draft`'s
`git rebase origin/$default_branch` met its own committed copy as an untracked
file and refused at pick 26) and the credential-use guard (`bd-ib-ccywva`,
hp-candidate run 01M4XNM4BBMYFPQDA6X5JCBDYM, where checkpoint `run_prepare_33`
committed 286 lines into draft pull request 2977).

THE EXCLUSION IS WRITTEN TO THE CLONE'S OWN EXCLUDE FILE rather than to a tracked
`.gitignore`: a materialized path is an artifact of how this Dispatcher prepares
ONE sandbox, so a governed repository must not have to carry a rule about it --
and a rule this step added to a tracked file would itself be a change every
checkpoint commits.

EVERY PATH THE CHAIN WRITES MUST BE LISTED, not only the artifact it ends up
with. An intermediate the chain deletes later is as committable as the final
one, because the checkpoint lands after the step that wrote it: the gh-refresh
caller lists its base64 payload beside the unpacked bundle for exactly that
reason, and excluding the final tree alone leaves the same defect one path over.

CALLERS MUST ALSO NAME PATHS NARROWLY. The entries land in the exclude file of a
GOVERNED repository's clone, so excluding a whole directory that a repository
could legitimately track would hide that repository's own content from git. A
projection that writes one file names that file.

Both sides of the inside-the-worktree comparison are reduced to their PHYSICAL
spelling first, and that normalization is load-bearing rather than tidy:
`git rev-parse --show-toplevel` answers the physical path and DISCARDS the
spelling it was handed, while a configured root reaches this sandbox family as
`/workspace/<repo>`, which is a symlink to the clone's real path. Comparing the
two as given therefore sent a path squarely INSIDE the worktree down the
outside-any-worktree arm, writing no entry at all -- the whole defect, intact,
behind a step that exits 0.

`--git-common-dir` and not `--git-dir`, because that is the directory whose
`info/exclude` git actually reads in a linked worktree; it answers the same path
in an ordinary clone, which is what the sandbox has.

EVERY ARM THAT CANNOT MEASURE where a path sits is passed over without writing,
and SAYS SO on stderr: a prepare step that fails kills the run at launch, before
any work is driven, and a path outside any worktree is one git was never going to
stage -- but a silent pass-over is indistinguishable from a successful exclusion
until `publish_draft` refuses at the end of a full run. The LABEL is what makes
that line attributable to the projection that wrote it, since several of them
render this same script.
"""

from __future__ import annotations

__all__: list[str] = [
    "worktree_exclude_script",
]


def worktree_exclude_script(*, paths: tuple[str, ...], label: str) -> str:
    """Render the prepare-step script that hides `paths` from the run's worktree.

    The paths ride the script's own POSITIONAL PARAMETERS rather than being
    interpolated into a `for` list, so one spelling of each path serves both the
    worktree resolution (taken from the FIRST path's parent, which the step
    creates) and the per-path loop. Each pattern is anchored with a leading `/`
    because `info/exclude` patterns resolve against the worktree top.

    `label` prefixes every diagnostic this script can emit. It is required rather
    than defaulted: the whole value of those lines is naming WHICH projection
    passed a path over, and a default would quietly attribute one projection's
    silence to another.
    """
    listed = " ".join(f'"{path}"' for path in paths)
    return (
        "set -eu\n"
        f"set -- {listed}\n"
        'parent="$(dirname "$1")"\n'
        'mkdir -p "$parent"\n'
        'toplevel="$(git -C "$parent" rev-parse --show-toplevel 2>/dev/null || true)"\n'
        'if [ -n "$toplevel" ]; then\n'
        '  toplevel="$(cd "$toplevel" 2>/dev/null && pwd -P || true)"\n'
        "fi\n"
        'if [ -z "$toplevel" ]; then\n'
        f"  echo \"{label}: no git worktree top resolved for '$parent',"
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
        'for path in "$@"; do\n'
        '  path_dir="$(cd "$(dirname "$path")" 2>/dev/null && pwd -P || true)"\n'
        '  if [ -n "$path_dir" ]; then path="$path_dir/$(basename "$path")"; fi\n'
        '  case "$path" in\n'
        '    "$toplevel"/*) entry="/${path#"$toplevel"/}" ;;\n'
        "    *)\n"
        f"      echo \"{label}: '$path' did not resolve inside the worktree"
        " at '$toplevel', so no exclude entry was written for it\" >&2\n"
        "      continue\n"
        "      ;;\n"
        "  esac\n"
        '  if ! grep -qxF "$entry" "$exclude_file" 2>/dev/null; then\n'
        '    printf \'%s\\n\' "$entry" >> "$exclude_file"\n'
        "  fi\n"
        "done"
    )
