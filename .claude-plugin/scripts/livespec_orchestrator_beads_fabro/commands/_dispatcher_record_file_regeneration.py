"""The generated-record-file resolution, as the Dispatcher materializes it.

The declared-record-file clause of `SPECIFICATION/contracts.md` says that "A
file whose entry names a generator is a GENERATED record file. Its correct
content is its generator's output over the tree it sits in, so a conflict in it
is never resolved by merging its text, on any route", that a refresh "MUST run
the file's generator over that tree and write its output as the resolution", that
such a resolution "is not a refresh-repair round", that a brief whose conflicted
paths include one "MUST carry one line `regenerate: <path> via <generator argv>`
per such file", and that the same line rides beside a failed gate target naming
one. Scenario 238 exercises all three. This module is the program that decides
them, and the prepare step that lands it in the sandbox.

WHY A MATERIALIZED PROGRAM RATHER THAN SHELL IN THE NODE, which is the same
answer `_dispatcher_carry_forward_program` gives and for the same measured
reason. The decision reads a committed JSONC declaration, pairs each entry's
path with its generator argv, classifies every conflicted path against that
pairing, EXECUTES an argv per file, and compares a committed blob against that
argv's output byte for byte. None of that is expressible in a node `script`, and
the half that is — the declaration read — is the half a hand-rolled shell reader
gets wrong silently, because a declaration it failed to parse and a repository
that declares nothing produce the SAME answer: no generated file here.

WHY THE PROGRAM READS THE DECLARATION ITSELF RATHER THAN BEING HANDED IT. The
governed clone is the repository whose `.livespec.jsonc` this is, so the
declaration is right there, and the host-side grade this module's sibling
`_dispatcher_record_files` performs has ALREADY refused a malformed `generator`
before any item was claimed. The program therefore reads an already-graded
declaration and its job on anything it cannot read is to HOLD, never to guess —
which is why every unreadable reading below returns the one `None` the caller
turns into a refusal rather than into an empty declaration.

WHY `path` IS READ HERE WHEN THE SIBLING DELIBERATELY DOES NOT GRADE IT. The
sibling grades `generator` alone, because the entry grammar's `path` / `format` /
`key` parse belongs to the entry-wise merge that work-item bd-ib-davaxq owns.
That split cannot survive here: a generator is an argv that rewrites a FILE, so
without the path there is nothing to rewrite and no way to ask whether a
conflicted path is the file an entry declares. What this program does with a
`path` it cannot use is the whole of the distinction — it refuses the resolution
outright rather than dropping the entry. Dropping it is the fail-OPEN reading:
the file would then read as undeclared, which is exactly the state in which a
`fix` turn hand-merges the register and loses the default branch's rows.

WHY AN UNGENERATED CONFLICTED RECORD FILE IS A REFUSAL AND NOT A NO-OP. The
clause resolves such a file by an entry-wise three-way merge, which is
implemented nowhere in this repository. A resolution that wrote the generated
half of a wider conflict and reported success would stage a tree still carrying
the other file's conflict markers, and the refreshed head would then be gated,
pushed and proved against text no side wrote.

WHY THE HEAD CHECK RESTORES EVERY PATH IT TOUCHED. It takes its reading by
RUNNING each generator, so it necessarily writes into the working tree. The
repository-declared gate runs on the refreshed head immediately after it, so a
check that left its own output behind would gate a tree nobody committed — and a
gate failure earned that way names the repository's own targets, which is the
wrong half of the seam entirely.
"""

from __future__ import annotations

import json

from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_declaration import (
    PLUGIN_BLOCK,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_files import (
    GENERATOR_KEY,
    RECORD_FILES_KEY,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    sandbox_plugins_root_expansion,
)

__all__: list[str] = [
    "GENERATED_RECORD_FILE_GATE_TARGET",
    "RECORD_FILE_BRIEF_FILENAME",
    "RECORD_FILE_PROGRAM_FILENAME",
    "RECORD_FILE_TARGETS_FILENAME",
    "REGENERATE_BRIEF_LABEL",
    "record_file_program_path_expansion",
    "record_file_program_prepare_steps_block",
    "record_file_program_source",
]

# The program's filename below the sandbox plugins root. Fail-closed is the
# node's own existence check, exactly as the carry-forward program records: a
# sandbox the prepare step did not reach carries no program, and a refresh that
# gated a head whose generated register nobody checked is the one outcome that
# must not be reachable.
RECORD_FILE_PROGRAM_FILENAME = "livespec-record-file-resolution.py"

# The gate target a refreshed head's hand-edited generated record file fails
# with, and the brief label the `fix` turn reads. Both are ratified SPELLINGS
# rather than wording this module chose, so they are constants the program
# substitutes rather than literals typed twice.
GENERATED_RECORD_FILE_GATE_TARGET = "generated-record-file"
REGENERATE_BRIEF_LABEL = "regenerate"

# The two files the program writes into the run's publication state directory.
# The stage reads them rather than parsing the program's narration, because a
# narration a shell greps is a second grammar nobody declared — and an empty
# targets file is how the stage tells "the register was hand-edited" apart from
# "the reading could not be taken at all", which have different remedies.
RECORD_FILE_BRIEF_FILENAME = "livespec-record-file-regenerate"
RECORD_FILE_TARGETS_FILENAME = "livespec-record-file-targets"

_PROGRAM = '''"""The generated-record-file resolution, materialized by the Dispatcher.

Assembled from `_dispatcher_record_file_regeneration`. Do not edit this file in
a sandbox: it is rewritten from that module on every dispatch.
"""

import json
import os
import re
import shlex
import subprocess
import sys

RECORD_FILES_KEY = "__RECORD_FILES_KEY__"
GENERATOR_KEY = "__GENERATOR_KEY__"
PATH_KEY = "path"
GATE_TARGET = "__GATE_TARGET__"
BRIEF_LABEL = "__BRIEF_LABEL__"
BRIEF_FILENAME = "__BRIEF_FILENAME__"
TARGETS_FILENAME = "__TARGETS_FILENAME__"
CONFIG_FILENAME = ".livespec.jsonc"
PLUGIN_BLOCK = "__PLUGIN_BLOCK__"
DISPATCHER_KEY = "dispatcher"
RESOLVED_MARKER = "LIVESPEC_RECORD_FILE_REGENERATED"
HELD_MARKER = "LIVESPEC_RECORD_FILE_HELD"
TARGET_MARKER = "LIVESPEC_GENERATED_RECORD_FILE"
MODES = ("--resolve", "--brief", "--check-head")

# `//` line comments only, which is the form every `.livespec.jsonc` in this
# family uses and the form the package's own reader admits. The capture keeps a
# string literal whole so a `//` INSIDE one -- a URL, a path -- is not read as
# the start of a comment.
COMMENT = re.compile(r'("(?:\\\\.|[^"\\\\])*")|(//[^\\n]*)')


def note(message):
    sys.stderr.write(message + "\\n")


def run(argv, cwd=None):
    """One subprocess reading, with standard input closed."""
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False,
                          stdin=subprocess.DEVNULL)


def repository_root():
    """The clone this program is resolving, or None when git will not say."""
    result = run(["git", "rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def canonical_path(value):
    """One declared path interpreted relative to the repository root, or None.

    None is the REJECTION: an absent, non-string, empty, absolute or
    parent-bearing value. `.` segments and repeated separators collapse, so
    `./tests//register.json` and `tests/register.json` are one path and a
    conflict in that file is recognised as the file the entry declares.
    """
    if not isinstance(value, str) or not value or value.startswith("/"):
        return None
    parts = []
    for part in value.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            return None
        parts.append(part)
    return "/".join(parts) if parts else None


def declaration(root):
    """(every declared path, path -> generator argv), or None when unreadable.

    None is the UNREADABLE answer and is deliberately NOT an empty declaration.
    Both read as "no generated record file is declared here", and a resolution
    that could not tell them apart would hand-merge a register whose declaration
    it had merely failed to parse -- which is the exact loss this program exists
    to stop, reached through the one state nothing announces.

    An ABSENT file is on the ANSWER side of that line, exactly as an absent key
    is: a clone whose configuration has not been written declares no record
    files. A reading that held on it would refuse the refresh of every such
    clone before the repository-declared gate, which is a refusal about the
    clone rather than about any register.

    The block is read where a GOVERNED repository carries it -- nested under the
    plugin block, which is where this package's own `dispatcher_block` reads it
    from. A top-level `dispatcher` key is carried by no `.livespec.jsonc` in this
    fleet, so a reader pointed there cannot return a hit and reports none.
    """
    path = os.path.join(root, CONFIG_FILENAME)
    if not os.path.isfile(path):
        return ((), {})
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return None
    stripped = COMMENT.sub(lambda match: match.group(1) or "", text)
    try:
        document = json.loads(stripped)
    except ValueError:
        return None
    if not isinstance(document, dict):
        return None
    return dispatcher_entries(document)


def dispatcher_entries(document):
    """The declaration's entries read out of the plugin's own nested block."""
    plugin = document.get(PLUGIN_BLOCK)
    if plugin is None:
        return ((), {})
    if not isinstance(plugin, dict):
        return None
    block = plugin.get(DISPATCHER_KEY)
    if block is None:
        return ((), {})
    if not isinstance(block, dict):
        return None
    return entries_of(block.get(RECORD_FILES_KEY))


def entries_of(raw):
    """The declaration's entries paired, or None when one of them cannot be.

    An absent or empty array declares no record files, which the clause states
    outright and which is an answer. Anything else that will not pair -- an entry
    that is not an object, a `path` that is not a usable repository-relative
    path -- holds the WHOLE resolution rather than dropping that entry, for the
    reason the assembling module's docstring records.
    """
    if raw is None:
        return ((), {})
    if not isinstance(raw, list):
        return None
    paths = []
    generators = {}
    for entry in raw:
        if not isinstance(entry, dict):
            return None
        declared = canonical_path(entry.get(PATH_KEY))
        if declared is None:
            return None
        paths.append(declared)
        argv = entry.get(GENERATOR_KEY)
        if argv is None:
            continue
        if not isinstance(argv, list) or not argv:
            return None
        if not all(isinstance(token, str) and token for token in argv):
            return None
        generators[declared] = tuple(argv)
    return (tuple(paths), generators)


def regenerate_lines(generators, paths):
    """One `regenerate: <path> via <argv>` line per generated file, in order."""
    return [BRIEF_LABEL + ": " + one + " via " + shlex.join(list(generators[one]))
            for one in paths if one in generators]


def write_state(state, name, lines):
    """One state file, written whether or not it carries anything.

    An ABSENT file and an EMPTY one are not the same reading to the stage: the
    stage distinguishes a hand-edited register from an unestablishable reading by
    whether the targets file carries a target, so a mode that skipped the write
    on an empty answer would leave the previous visit's file standing and the
    stage would act on a stale target.
    """
    with open(os.path.join(state, name), "w", encoding="utf-8") as handle:
        for line in lines:
            handle.write(line + "\\n")


def resolve(root, paths, generators, conflicted):
    """Write every conflicted generated record file from its generator, or refuse.

    Returns None on success, or the reason it refused. The files are rewritten in
    DECLARATION order rather than in the order the conflict reported them,
    because a generator derives its file from the tree and may read another
    declared record file -- the register this work-item was filed for derives
    from the registry beside it -- and declaration order is the operator's own
    statement of that dependency.
    """
    if not conflicted:
        return "no conflicted path was named, so there is nothing to resolve"
    undeclared = [one for one in conflicted if one not in paths]
    if undeclared:
        return ("these conflicted paths are not declared record files, so this"
                " conflict takes the refresh-repair route unchanged: "
                + ", ".join(undeclared))
    ungenerated = [one for one in conflicted if one not in generators]
    if ungenerated:
        return ("these conflicted declared record files name no generator, so"
                " only the entry-wise three-way merge of the same clause could"
                " resolve them and this resolution writes nothing rather than"
                " staging a tree still carrying their conflict: "
                + ", ".join(ungenerated))
    for one in [path for path in paths if path in conflicted]:
        refusal = regenerate(root, one, generators[one])
        if refusal is not None:
            return refusal
    return None


def regenerate(root, path, argv):
    """Run one generator and stage its output, or say why that is no resolution."""
    spelled = shlex.join(list(argv))
    produced = run(list(argv), cwd=root)
    if produced.returncode != 0:
        return ("the generator " + spelled + " for " + path + " exited "
                + str(produced.returncode) + ", so the clause does not make that"
                " file resolvable: " + " ".join(produced.stderr.split())[:400])
    if not os.path.isfile(os.path.join(root, path)):
        return ("the generator " + spelled + " exited zero but wrote no file at "
                + path + ", so there is nothing to stage as the resolution")
    staged = run(["git", "add", "--", path], cwd=root)
    if staged.returncode != 0:
        return ("the regenerated " + path + " could not be staged: "
                + " ".join(staged.stderr.split())[:400])
    note(RESOLVED_MARKER + ": " + path + " was written from its generator "
         + spelled + " rather than by merging its text, so no refresh-repair"
         " round is owed for it")
    return None


def check_head(root, generators):
    """(the paths whose committed bytes are not their output, the reason to hold).

    Both halves can be empty, and the pair is what the stage routes on: a path
    names the register and takes the refresh-repair route, while a reason names a
    reading that could not be taken at all and fails the stage closed. Collapsing
    them would blame the repository's register for an unreadable tree.

    The residue reading compares the tree's own status against the one taken
    BEFORE any generator ran, rather than requiring a clean tree. A sandbox
    clone legitimately carries its own provisioning residue, so a check demanding
    cleanliness would hold on every refresh in the fleet while reporting a
    generator that did nothing wrong.
    """
    baseline = porcelain(root)
    differing = []
    for path in sorted(generators):
        present = run(["git", "cat-file", "-e", "HEAD:" + path], cwd=root)
        if present.returncode != 0:
            continue
        if dirty(root, path):
            return ([], "the working tree already differs from HEAD at " + path
                    + " before any generator ran, so a reading taken now would be"
                    " about that change rather than about the committed file")
        held = compare(root, path, generators[path], differing)
        if held is not None:
            return ([], held)
    residue = porcelain(root)
    if residue != baseline:
        return ([], "a generator changed the working tree beyond the declared"
                " record files it rewrites, so the repository-declared gate would"
                " run on a head nobody committed: " + residue[:400])
    return (differing, None)


def compare(root, path, argv, differing):
    """Note whether one committed generated file is its generator's output.

    Appends to `differing` rather than returning, because the only other thing
    this can produce is a REASON TO HOLD and the two are different routes. The
    reading is taken BEFORE the restoration and reported after it, so the tree
    is put back on every arm including the two that hold.
    """
    produced = run(list(argv), cwd=root)
    changed = dirty(root, path)
    restored = run(["git", "checkout", "HEAD", "--", path], cwd=root)
    if produced.returncode != 0:
        return ("the generator " + shlex.join(list(argv)) + " for " + path
                + " exited " + str(produced.returncode) + " over this head, so"
                " whether the committed file is its output cannot be established: "
                + " ".join(produced.stderr.split())[:400])
    if restored.returncode != 0:
        return ("the generator output at " + path + " could not be restored to the"
                " committed bytes, so the repository-declared gate would run on a"
                " head nobody committed: " + " ".join(restored.stderr.split())[:400])
    if changed:
        differing.append(path)
    return None


def porcelain(root):
    """The clone's own status, as one string, or a marker when git will not say."""
    result = run(["git", "status", "--porcelain"], cwd=root)
    if result.returncode != 0:
        return HELD_MARKER
    return result.stdout


def dirty(root, path):
    """Whether the working tree differs from HEAD at one path."""
    return run(["git", "diff", "--quiet", "HEAD", "--", path], cwd=root).returncode != 0


def parse_argv(argv):
    """(state directory, mode, named paths), or None when an input is absent.

    Neither input has a safe default. A mode defaulted to `--resolve` would
    regenerate on an invocation that meant to ask a question, and a state
    directory defaulted anywhere would write the brief where no stage reads
    it -- which reads downstream as a brief that named no generated file.
    """
    state = None
    mode = None
    paths = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--state-dir":
            if index + 1 >= len(argv):
                return None
            state = argv[index + 1]
            index += 2
            continue
        if token in MODES:
            if mode is not None:
                return None
            mode = token
            index += 1
            continue
        paths.append(token)
        index += 1
    if state is None or mode is None:
        return None
    return (state, mode, paths)


def main(argv):
    parsed = parse_argv(argv)
    if parsed is None:
        note("LIVESPEC_RECORD_FILE_USAGE: --state-dir <dir> and exactly one of "
             + ", ".join(MODES) + " are both required")
        return 2
    state, mode, named = parsed
    root = repository_root()
    if root is None:
        note(HELD_MARKER + ": no git clone resolved from this working directory,"
             " so the committed declaration cannot be read")
        return 1
    declared = declaration(root)
    if declared is None:
        note(HELD_MARKER + ": the committed " + CONFIG_FILENAME + " declaration of "
             + DISPATCHER_KEY + "." + RECORD_FILES_KEY + " could not be read as an"
             " array of entries each naming a repository-relative path, so no"
             " generated record file can be resolved from it")
        if mode != "--resolve":
            write_state(state, TARGETS_FILENAME, [])
            write_state(state, BRIEF_FILENAME, [])
        return 1
    paths, generators = declared
    if mode == "--brief":
        write_state(state, BRIEF_FILENAME, regenerate_lines(generators, named))
        return 0
    if mode == "--resolve":
        refusal = resolve(root, paths, generators, named)
        if refusal is None:
            return 0
        note(HELD_MARKER + ": " + refusal)
        return 1
    return head_outcome(root, state, generators)


def head_outcome(root, state, generators):
    """The `--check-head` verdict, with both state files written either way."""
    differing, held = check_head(root, generators)
    write_state(state, TARGETS_FILENAME,
                [GATE_TARGET + ":" + one for one in differing])
    write_state(state, BRIEF_FILENAME, regenerate_lines(generators, differing))
    if held is not None:
        note(HELD_MARKER + ": " + held)
        return 1
    if not differing:
        return 0
    note(TARGET_MARKER + ": the committed " + ", ".join(differing) + " differs from"
         " its generator output over this head, so the head carries a hand-merged"
         " generated record file and fails before the repository-declared gate")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''


def record_file_program_source() -> str:
    """The program's exact bytes, with every owned spelling substituted.

    A function rather than a constant for the reason the carry-forward program's
    own fragment gives: a reader must be able to see that the plugin block, the
    two configuration keys, the gate target and the brief label came from the
    modules that own them, not from literals typed twice on either side of a
    sandbox boundary. The plugin block is the one a wrong literal would make
    INVISIBLE: the program would read a key no governed repository carries and
    report every register as undeclared.
    """
    return (
        _PROGRAM.replace("__RECORD_FILES_KEY__", RECORD_FILES_KEY)
        .replace("__GENERATOR_KEY__", GENERATOR_KEY)
        .replace("__PLUGIN_BLOCK__", PLUGIN_BLOCK)
        .replace("__GATE_TARGET__", GENERATED_RECORD_FILE_GATE_TARGET)
        .replace("__BRIEF_LABEL__", REGENERATE_BRIEF_LABEL)
        .replace("__BRIEF_FILENAME__", RECORD_FILE_BRIEF_FILENAME)
        .replace("__TARGETS_FILENAME__", RECORD_FILE_TARGETS_FILENAME)
    )


def record_file_program_path_expansion() -> str:
    """The shell expansion a refreshing node resolves the program through.

    PUBLIC and spelled once, for the reason the publication-head program's own
    expansion records: a node resolving a DIFFERENT root than the prepare pass
    would find no program at all, and the failure would then read as a Dispatcher
    that never materialized one.
    """
    return f"{sandbox_plugins_root_expansion()}/{RECORD_FILE_PROGRAM_FILENAME}"


def record_file_program_prepare_steps_block() -> str:
    """The prepare step that lands the program below the sandbox plugins root.

    Written through a heredoc with a QUOTED delimiter, so the shell expands
    nothing inside the program: the program carries dollar-bearing,
    shell-looking text of its own, and an unquoted heredoc would substitute into
    it at prepare time and land bytes nobody wrote.
    """
    root = sandbox_plugins_root_expansion()
    script = (
        f'set -eu\nmkdir -p "{root}"\n'
        f'cat > "{root}/{RECORD_FILE_PROGRAM_FILENAME}" '
        f"<<'LIVESPEC_RECORD_FILE_PROGRAM'\n"
        f"{record_file_program_source()}"
        "LIVESPEC_RECORD_FILE_PROGRAM"
    )
    return (
        "\n# --- Dispatcher-materialized generated-record-file resolution: a\n"
        "# --- conflicted generated register is written from its generator, never\n"
        "# --- merged as text, and a refreshed head carrying a hand-merged one\n"
        "# --- fails before the repository-declared gate (bd-ib-ze7xxj) ---\n"
        "[[run.prepare.steps]]\n"
        f"script = {json.dumps(script)}\n"
    )
