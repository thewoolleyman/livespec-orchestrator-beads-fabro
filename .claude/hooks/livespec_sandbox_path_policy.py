"""Pure sandbox-path policy: what a factory run cannot survive losing.

WHY THIS EXISTS. Measured 2026-10-15, run 01M4YJGC55V86C9V1X07QG3Y2H: an
implement-stage agent simulating a sandbox layout for a test it was writing ran
`cd /tmp && rm -rf /workspace && mkdir -p /workspace && git init ...`. That
deleted the working-directory LINK the engine had set its working directory to.
The agent itself never noticed — it kept working in the clone under `/repos`,
ran the full check suite green and committed — and then the engine's own
checkpoint died with `git add failed (exit 127)`, tail `chdir to cwd
("/workspace/livespec-orchestrator-beads-fabro") ... no such file or directory`.
The run ended `workflow_error` with its final commit sha equal to the base, so
roughly 47 minutes of finished, tested, committed work existed only inside a
stopped container. The governing clause (`contracts.md`, "The run's working
tree survives the agent.", with Scenario 180) answers that by PREVENTING the
destruction rather than surviving it.

THE THREE QUESTIONS, EACH ITS OWN FUNCTION, because they fail in opposite
directions:

- `protected_paths` — which paths this run cannot survive losing. It must be
  EXACT in the narrow direction: a path it names wrongly refuses legitimate
  work, so it names the sandbox root, the working directory, the link and the
  clone and nothing else. Every Dispatcher-materialized sibling under the root
  (the credential-use guard, the projected Codex home, the tmux socket root)
  is deliberately NOT protected.
- `removal_targets` — which paths an executed segment of a command would act
  on. It must be GENEROUS: a target it fails to see is a path nothing protects.
- `refused_path` — whether any of those targets destroys any protected path.
  Exact again, and the one place ancestry enters: a command naming a directory
  ABOVE a protected path destroys it just as surely as one naming it.

WHAT A DESTINATION IS, and why it is the one target that can be spared. `mv`
and `ln` WRITE their last operand, and when that operand is already a directory
they create the moved or linked path INSIDE it rather than replacing it — the
very semantics that keep `cp` out of `DESTRUCTIVE_VERBS` altogether. So `mv
/tmp/patch.diff .` destroys nothing and the governing clause's refusal
condition is not met by it, while refusing it would stop an agent restoring a
scratch file into the tree it is working in. The SOURCE side is untouched by
that reading: `mv /workspace /tmp/moved-root` really does move the root away.
Whether a destination IS a directory is a filesystem reading, so it reaches
`refused_path` as an argument like every other one, and the mark that says
WHICH target is a destination travels with the target rather than as a set of
paths — one command can carry the same path in both roles.

WHAT "DESTROYS" MEANS, and why ancestry is in it. `rm -rf ..` from the
repository root removes the repository. So does `rm -rf /repos`. Neither names
a protected path, and both end the run exactly as the incident above did, so
the comparison is against every protected path AND every directory above one.
The reverse does NOT hold: a path BELOW a protected path is in-tree, and v142
allows removing the clone's `.git` or emptying the whole tree (tracked
separately as bd-ib-quzpge).

WHY THE SET IS DISCOVERED RATHER THAN CONFIGURED. The two engine layouts
disagree about where the clone sits — the pinned engine checks it out at
`/workspace/<repo>`, the Petri-era engine at `/repos/<owner>/<repo>` with a
link to it under the root, or at the root itself — and nothing in the sandbox
announces which. So the caller supplies what it can READ (the root, the
repository path, what the repository really is, and what each child of the root
really is) and this module derives the set. Deriving it is also what makes the
policy INERT outside a factory sandbox: a repository the sandbox root does not
hold, directly or through a link, protects nothing. That is the clause's own
scope, not caution — the paragraph governs the run's layout inside the sandbox,
and a guard that also refused a removal in a developer's checkout would be
enforcing a rule nobody ratified.

PURE: every filesystem reading is an argument. The hook that takes those
readings and emits the deny payload is `livespec_sandbox_path_guard`.
"""

from __future__ import annotations

import fnmatch
import posixpath
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

from livespec_sandbox_repository_policy import repository_emptying_path as _repository_emptying_path
from livespec_shell_shape import (
    leading_assignments,
    leading_command_index,
    operands,
    shell_tokens,
    token_segments,
    without_heredoc_bodies,
)

__all__: list[str] = [
    "DESTRUCTIVE_VERBS",
    "Target",
    "protected_paths",
    "refusal_message",
    "refused_path",
    "removal_targets",
    "repository_emptying_path",
    "stand_in_targets",
]

_ROOT = "/"
_UNREADABLE = ("", _ROOT, ".")
_CHANGE_DIRECTORY = "cd"
# The characters that make a word a shell PATTERN rather than a path.
_GLOB_CHARACTERS = frozenset("*?[")

# The verbs that can REMOVE, MOVE or REPLACE a path outright, which is the
# triple the governing clause names. `cp` is deliberately absent: its
# destination semantics are to create INSIDE an existing directory, so reading
# its operands as replacements would refuse `cp x /workspace/.livespec/` while
# protecting nothing extra.
DESTRUCTIVE_VERBS = frozenset({"ln", "mv", "rm", "rmdir", "shred", "unlink"})
# `ln` destroys its target only when forced — without a force flag it refuses
# an existing path itself, so an unforced `ln` is not a replacement.
_FORCE_ONLY_VERBS = frozenset({"ln"})
_FORCE_SHORT_FLAG = "f"
_FORCE_LONG_FLAG = "--force"
# The verbs whose LAST operand is a path they WRITE rather than one they
# consume. These two are exactly the ones that share `cp`'s into-directory
# semantics for that operand, which is why they need the narrower reading and
# why `rm`, `rmdir`, `shred` and `unlink` do not: those take no destination.
_DESTINATION_VERBS = frozenset({"ln", "mv"})
_NO_DESTINATION = -1
# A destination means nothing without a source beside it, so a segment needs
# both before its last operand is read as one.
_DESTINATION_NEEDS_OPERANDS = 2
# The flag spellings that make a destination a PLAIN NAME the segment
# replaces, rather than a directory it writes inside — each paired with the
# verbs it may be read for, because the two spellings do NOT share a verb set.
#
# `-T` / `--no-target-directory` is coreutils' "treat DEST as a normal file",
# and it means that to BOTH verbs: under it `ln` RE-POINTS a link instead of
# writing through it, and `mv` overwrites the name instead of moving inside
# it. It is also `mv`'s ONLY spelling of that semantic.
#
# `-n` / `--no-dereference` is the same reading for `ln`, and `ln -sfn` is
# exactly how the engine's own working-directory link would be destroyed. It
# is read for `ln` ALONE: GNU `mv -n` is `--no-clobber`, a flag whose whole
# purpose is to destroy less, and reading it here would turn the safest move
# an agent can type into a refusal.
_PLAIN_DESTINATION_FLAGS = (
    (frozenset({"ln", "mv"}), "T", "--no-target-directory"),
    (frozenset({"ln"}), "n", "--no-dereference"),
)


@dataclass(frozen=True, kw_only=True)
class Target:
    """One path an executed destructive segment would act on.

    `into_directory` marks the segment's DESTINATION — the last operand of
    `mv` or of a dereferencing `ln` — which destroys nothing when the path is
    already a directory, because the moved or linked path is then created
    inside it. Every other target is destroyed outright.

    The mark travels WITH the path rather than as a set of paths, because one
    command can carry the same path in both roles: `mv /tmp/x /workspace && rm
    -rf /workspace` writes into the root and then removes it, and sparing by
    value would spare the removal too.
    """

    path: str
    into_directory: bool


def protected_paths(
    *,
    sandbox_root: str,
    repository_path: str,
    repository_clone: str,
    sandbox_entry_targets: Mapping[str, str],
) -> tuple[str, ...]:
    """The paths this run cannot survive losing, most general first.

    `sandbox_entry_targets` maps each immediate child of the sandbox root to
    what that child really is. The working-directory link is identified by WHAT
    IT POINTS AT rather than by a name this module predicts, because the engine
    chooses that name and the two engine layouts choose differently.

    Ordered most-general-first so a refusal names the sandbox root rather than
    something inside it when a command targets the root itself.
    """
    root = posixpath.normpath(sandbox_root)
    repository = posixpath.normpath(repository_path)
    clone = posixpath.normpath(repository_clone)
    if root in _UNREADABLE or repository in _UNREADABLE:
        return ()
    links = sorted(
        entry
        for entry, target in sandbox_entry_targets.items()
        if posixpath.normpath(target) == clone
    )
    held = repository == root or repository.startswith(f"{root}/")
    if not links and not held:
        return ()
    return tuple(dict.fromkeys((root, *links, repository, clone)))


def removal_targets(*, command: str, working_directory: str) -> tuple[Target, ...]:
    """The paths the executed destructive segment of `command` would act on.

    EVERY segment is read, not just the first, and that is the whole shape of
    the measured incident: `cd /tmp && rm -rf /workspace && mkdir -p /workspace`
    leads with `cd`, so a reading that classified the command by its first word
    would call it a directory change and let the removal through.

    The whole operand list is read rather than just the first or last word,
    because a protected path can sit anywhere in it: `rm -rf /tmp/sim
    /workspace` destroys the root with its SECOND operand, and `mv /workspace
    /tmp/moved-root` destroys it with its first. An operand list read
    head-first or tail-first misses one of those. What each operand MEANS
    still differs by position — the last operand of `mv` or of a dereferencing
    `ln` is a destination, marked as such on its `Target` — but that is a
    reading of the operand, not a reason to stop looking at it.

    HERE-DOCUMENT BODIES GO FIRST, before the command is read at all. A body is
    file data, so its words are not commands — and because a body can carry a
    `&&`, reading one would split on that operator and take the body's second
    half for something the shell would run. The case that makes that concrete
    is a test fixture ABOUT this incident, which would otherwise be refused as
    if it WERE the incident.

    THEN LINE BY LINE, and only then by segment. Newline is not a shell control
    operator, so a two-line command tokenizes into one flat word list whose
    leading word belongs to the FIRST line: without the per-line split, `git
    status` followed by `rm -rf /workspace` on the next line reads as a `git`
    command and the removal is never seen. A line whose quoting does not close
    is skipped, which happens only when a token legitimately spans lines.

    The working directory and the assigned values carry ACROSS lines as well as
    across segments, because a shell's state does.
    """
    directory = working_directory
    assigned: dict[str, str] = {}
    found: list[Target] = []
    for line in without_heredoc_bodies(command=command).splitlines():
        tokens = shell_tokens(command=line)
        if tokens is None:
            continue
        for segment in token_segments(tokens=tokens):
            assigned.update(leading_assignments(tokens=segment))
            directory, targets = _walked(segment=segment, directory=directory, assigned=assigned)
            found.extend(targets)
    return tuple(found)


def repository_emptying_path(
    *,
    command: str,
    working_directory: str,
    clone: str,
    top_level_entries: Sequence[str],
) -> str | None:
    return _repository_emptying_path(
        command=command,
        working_directory=working_directory,
        clone=clone,
        top_level_entries=top_level_entries,
        walk_segment=_walked,
        executed=_executed,
    )


def refused_path(
    *,
    targets: Sequence[Target],
    resolved: Mapping[str, str],
    directories: Collection[str],
    protected: Sequence[str],
) -> str | None:
    """The protected path `targets` would destroy, or `None` if they would not.

    Both filesystem readings arrive as arguments, because this module has
    none. `resolved` maps a target's path to what it really is, so a symbolic
    link an agent made itself cannot stand in for the path it points at.
    `directories` holds the target paths that are ALREADY directories, which
    is what settles a destination: `mv /tmp/patch.diff .` writes into the
    working directory and destroys nothing, while `mv /workspace
    /tmp/moved-root` destroys the root it names.

    A reading the caller could not take is simply absent from either, which is
    the fail-closed direction: an unreadable destination stays a replacement.
    """
    refusable = _refusable_targets(protected=protected)
    for target in targets:
        victim = _destroyed(
            target=target, resolved=resolved, directories=directories, refusable=refusable
        )
        if victim is not None:
            return victim
    return None


def stand_in_targets(
    *,
    targets: Sequence[Target],
    resolved: Mapping[str, str],
    directories: Collection[str],
    protected: Sequence[str],
) -> tuple[str, ...]:
    """The words this command wrote that reach a protected path only by RESOLVING to one.

    WHY THIS IS A SEPARATE QUESTION FROM `refused_path`. That function answers
    WHICH protected path dies, which is what the refusal must name. This one
    answers HOW the command reached it, which is what an agent needs to act.
    A refusal naming a path the command never wrote is the one refusal an
    agent cannot act on: measured 2026-10-18, `rm -f
    /tmp/proof-capture/agent-made-link` was refused naming `/workspace` —
    absent from the command — while the remedy offered was to build the
    simulation under a scratch directory, which is exactly where that link
    already was.

    The same two readings `refused_path` compares against are compared here,
    so the two answers cannot disagree. A target SPARED there is absent, because
    naming a destination that destroyed nothing would blame the wrong operand of
    a command some other target got refused for. A GLOB is absent too: a pattern
    is matched rather than resolved, so it stands in for nothing. And a target
    that IS a protected path is absent, because the message already names it.
    """
    refusable = _refusable_targets(protected=protected)
    found: list[str] = []
    for target in targets:
        if _spared(target=target, directories=directories):
            continue
        if _GLOB_CHARACTERS & set(target.path):
            continue
        if _victim(candidate=target.path, refusable=refusable) is not None:
            continue
        if _victim(candidate=resolved.get(target.path, target.path), refusable=refusable):
            found.append(target.path)
    return tuple(dict.fromkeys(found))


def refusal_message(*, protected_path: str, command: str, stand_ins: Sequence[str] = ()) -> str:
    """Render the operator-facing refusal naming the protected path it matched.

    `stand_ins` are the words the command actually wrote that reach that path
    only by resolving to it. They are rendered as their own paragraph, and
    only when there are any, because a command that wrote the path down needs
    no account of how the match happened — while one that did not cannot
    otherwise get one.

    The paragraph has to say that the link is PERMANENT, not merely that it
    matched. A link pointing at a protected path is refused exactly as that
    path is, and that includes the command removing the link itself, so the
    name can never be reclaimed. An agent told only that it matched will
    reasonably try to clean up and be refused again.
    """
    disclosure = ""
    if stand_ins:
        disclosure = (
            f"This command does not name {protected_path}. What it writes resolves to "
            f"it: {', '.join(stand_ins)}. A target counts for what it REALLY is, so a "
            "symbolic link you made that points at a protected path is refused exactly "
            "as that path is — including the command that would remove the link itself. "
            "Such a link cannot be cleaned up once it exists, so a fixed name an earlier "
            "run left behind can never be reused.\n\n"
        )
    return (
        "REFUSED by livespec_sandbox_path_guard: this command would remove, move or "
        f"replace {protected_path}, which is one of this run's protected paths — the "
        "factory sandbox root, the run's working directory, the working-directory link "
        "the engine sets that directory to, or the run's clone. The run cannot survive "
        "losing any of them: the engine's next checkpoint runs `git add` in the working "
        "directory, so a run whose working directory is gone dies with `chdir to cwd ... "
        "no such file or directory` and publishes nothing, losing every commit the stage "
        "had already made.\n\n"
        f"Command: {command}\n\n"
        f"{disclosure}"
        "This refusal is deterministic, not a transient failure. Do NOT retry the same "
        "command. To simulate a sandbox layout, build the whole simulation under a "
        "scratch directory such as /tmp, point every link inside it at a path inside "
        "that same simulation rather than at one of this run's, and give it a name no "
        "earlier run has used."
    )


def _destroyed(
    *,
    target: Target,
    resolved: Mapping[str, str],
    directories: Collection[str],
    refusable: Sequence[tuple[str, str]],
) -> str | None:
    """The protected path ONE target destroys, or `None` if it destroys none.

    A destination that is already a directory destroys nothing, so it is the
    one target a reading can spare. Everything after that is the ordinary
    comparison: a target carrying a glob is matched as a PATTERN rather than
    compared, and is never looked up in `resolved` — a pattern is not a path,
    so there is nothing on disk to resolve, and the only question worth asking
    is whether a protected path is among what the shell would expand it to.
    """
    if _spared(target=target, directories=directories):
        return None
    if _GLOB_CHARACTERS & set(target.path):
        return _matched_pattern(pattern=target.path, refusable=refusable)
    for candidate in (target.path, resolved.get(target.path, target.path)):
        victim = _victim(candidate=candidate, refusable=refusable)
        if victim is not None:
            return victim
    return None


def _spared(*, target: Target, directories: Collection[str]) -> bool:
    """True iff this target is a destination the segment writes INTO rather than replaces.

    Read by `_destroyed` and by `stand_in_targets`, which is the whole point of
    naming it: a target spared from the refusal must also be spared from the
    account of why the refusal happened.
    """
    return target.into_directory and target.path in directories


def _walked(
    *, segment: list[str], directory: str, assigned: Mapping[str, str]
) -> tuple[str, list[Target]]:
    """One segment: where it leaves the shell, and what it would destroy.

    The directory is returned rather than only the targets because a `cd`
    destroys nothing and still changes what every later word means, so the two
    answers are one reading.
    """
    verb, arguments = _executed(segment=segment)
    words = [_expand(word=word, assigned=assigned) for word in operands(tokens=arguments)]
    if verb == _CHANGE_DIRECTORY:
        return _changed_directory(words=words, directory=directory), []
    if not _is_destructive(verb=verb, arguments=arguments):
        return directory, []
    paths = [_resolve(word=word, directory=directory) for word in words]
    destination = _destination_index(verb=verb, arguments=arguments, operand_count=len(paths))
    return directory, [
        Target(path=path, into_directory=index == destination) for index, path in enumerate(paths)
    ]


def _destination_index(*, verb: str, arguments: Sequence[str], operand_count: int) -> int:
    """Which operand this segment WRITES INTO, or `_NO_DESTINATION` for none.

    A destination means nothing without a source beside it: `mv /workspace` is
    an error the shell reports without touching anything, and `ln -s
    /workspace` links INTO the working directory rather than writing the word
    it names. So a lone operand is never one.

    A PLAIN-DESTINATION flag is the exception inside the exception, and it is
    the one that matters most here. It is how a symbolic link to a directory
    is RE-POINTED — `ln -sfn` and `ln -sfT` are exactly how the engine's own
    working-directory link would be destroyed, and `mv -T` overwrites that
    link with whatever it is handed — so under one the last operand is a
    replacement again, however plainly the filesystem reports it as a
    directory.
    """
    if verb not in _DESTINATION_VERBS or operand_count < _DESTINATION_NEEDS_OPERANDS:
        return _NO_DESTINATION
    if _replaces_its_destination(verb=verb, arguments=arguments):
        return _NO_DESTINATION
    return operand_count - 1


def _replaces_its_destination(*, verb: str, arguments: Sequence[str]) -> bool:
    """True iff this segment's own flags make its last operand a replacement.

    Each spelling is paired with its verbs rather than tested against one
    shared set, because `-T` is read for `ln` AND `mv` while `-n` is read for
    `ln` alone — and a single set would have to be wrong for one of them.
    """
    for verbs, short, long_flag in _PLAIN_DESTINATION_FLAGS:
        if verb in verbs and _asks(arguments=arguments, short=short, long_flag=long_flag):
            return True
    return False


def _executed(*, segment: list[str]) -> tuple[str, list[str]]:
    """The command word one segment runs, and its arguments.

    An empty verb means the segment runs nothing — it is all flags,
    assignments and wrappers. Such a segment is still WALKED rather than
    short-circuited, because the segment after it is where a removal lives.
    """
    index = leading_command_index(tokens=segment)
    if index >= len(segment):
        return "", []
    return segment[index].rsplit("/", 1)[-1], segment[index + 1 :]


def _changed_directory(*, words: list[str], directory: str) -> str:
    """Where a `cd` leaves the shell, so a later relative word means the right path.

    A `cd` with no operand goes somewhere this module cannot know. Keeping the
    last KNOWN directory is the deliberate direction: resolving later relative
    words against a home directory the policy invented would make every one of
    those readings fiction, and the cost of keeping the known one is at worst a
    refusal of a removal that would have happened elsewhere.
    """
    return _resolve(word=words[0], directory=directory) if words else directory


def _expand(*, word: str, assigned: Mapping[str, str]) -> str:
    """One word with every variable THIS command assigned substituted into it.

    LONGEST NAME FIRST, which is the one ordering here that is not
    interchangeable: with both `d` and `dd` assigned, substituting `d` first
    rewrites the `$d` inside `$dd` and leaves a stray `d` glued to the wrong
    value — a word that then matches nothing, reported as a clean allow.

    Only names this command assigned are substituted. A variable the
    environment carries is deliberately left alone: its value is not in the
    command, so expanding it would be the guard deciding against a value the
    agent's own shell may never see, and leaving the reference intact is what
    keeps the word from matching anything.
    """
    expanded = word
    for name in sorted(assigned, key=len, reverse=True):
        value = assigned[name]
        expanded = expanded.replace("${" + name + "}", value).replace("$" + name, value)
    return expanded


def _is_destructive(*, verb: str, arguments: Sequence[str]) -> bool:
    if verb not in DESTRUCTIVE_VERBS:
        return False
    if verb not in _FORCE_ONLY_VERBS:
        return True
    return _asks(arguments=arguments, short=_FORCE_SHORT_FLAG, long_flag=_FORCE_LONG_FLAG)


def _asks(*, arguments: Sequence[str], short: str, long_flag: str) -> bool:
    """True iff one argument asks for a flag, as a long flag or inside a cluster.

    A short-flag CLUSTER counts, because `-sfn` is how a link is re-pointed
    and BOTH letters in it are load-bearing: the `f` is what lets the link
    replace what is already there, and the `n` is what makes it replace the
    LINK rather than write inside the directory the link points at. `-sfT`
    says the same thing with the other letter, so the cluster reading is what
    covers both without enumerating their orderings.

    CASE-SENSITIVE, which here separates two different flags rather than two
    spellings of one: coreutils reads `-T` as `--no-target-directory` and `-t`
    as `--target-directory`, and only the capital makes a destination plain.
    """
    for argument in arguments:
        if argument.startswith("--"):
            if argument == long_flag:
                return True
        elif argument.startswith("-") and short in argument:
            return True
    return False


def _resolve(*, word: str, directory: str) -> str:
    """One operand as the single absolute path it names.

    NORMALIZED rather than merely made absolute, and both halves are
    load-bearing. A relative word means nothing without the directory it is
    read from, so `rm -rf .` and `rm -rf ..` are the working directory and its
    parent. And a path can be SPELLED many ways — a trailing slash, a `.`, a
    `..` in the middle — so `/tmp/../workspace` is `/workspace` written the
    long way, and a comparison against unnormalized text would miss every one
    of those spellings while reporting a clean allow.

    Symbolic links are deliberately NOT followed here: `livespec_shell_shape`
    has no filesystem, and the link an agent made is resolved by the caller
    that can read one.
    """
    absolute = word if word.startswith(_ROOT) else posixpath.join(directory, word)
    return posixpath.normpath(absolute)


def _refusable_targets(*, protected: Sequence[str]) -> tuple[tuple[str, str], ...]:
    """Every path whose destruction destroys a protected path, with its victim.

    Exact matches are listed first so a refusal names the path the command
    actually wrote whenever it wrote one.
    """
    exact = tuple((path, path) for path in protected)
    above = tuple((ancestor, path) for path in protected for ancestor in _ancestors(path=path))
    return exact + above


def _ancestors(*, path: str) -> tuple[str, ...]:
    found: list[str] = []
    current = posixpath.dirname(path)
    while current not in ("", _ROOT):
        found.append(current)
        current = posixpath.dirname(current)
    return (*found, _ROOT)


def _victim(*, candidate: str, refusable: Sequence[tuple[str, str]]) -> str | None:
    for refusable_path, victim in refusable:
        if candidate == refusable_path:
            return victim
    return None


def _matched_pattern(*, pattern: str, refusable: Sequence[tuple[str, str]]) -> str | None:
    """The protected path a glob would expand onto, if any.

    `fnmatchcase` rather than `fnmatch` because the sandbox filesystem is
    case-sensitive, and a case-folding comparison would refuse `/WORKSPACE`
    while a shell would not have touched the root at all.
    """
    for refusable_path, victim in refusable:
        if fnmatch.fnmatchcase(refusable_path, pattern):
            return victim
    return None
