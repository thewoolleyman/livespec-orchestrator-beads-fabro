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
from collections.abc import Mapping, Sequence

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
    "protected_paths",
    "refusal_message",
    "refused_path",
    "removal_targets",
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
_FORCE_LONG_FLAG = "--force"


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


def removal_targets(*, command: str, working_directory: str) -> tuple[str, ...]:
    """The paths the executed destructive segment of `command` would act on.

    EVERY segment is read, not just the first, and that is the whole shape of
    the measured incident: `cd /tmp && rm -rf /workspace && mkdir -p /workspace`
    leads with `cd`, so a reading that classified the command by its first word
    would call it a directory change and let the removal through.

    The whole operand list is read rather than just the first or last word,
    because a protected path can sit anywhere in it: `rm -rf /tmp/sim
    /workspace` destroys the root with its SECOND operand, and `mv /tmp/x
    /workspace` destroys it with its second as well. An operand list read
    head-first or tail-first misses one of those.

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
    found: list[str] = []
    for line in without_heredoc_bodies(command=command).splitlines():
        tokens = shell_tokens(command=line)
        if tokens is None:
            continue
        for segment in token_segments(tokens=tokens):
            assigned.update(leading_assignments(tokens=segment))
            directory, targets = _walked(segment=segment, directory=directory, assigned=assigned)
            found.extend(targets)
    return tuple(found)


def refused_path(
    *,
    targets: Sequence[str],
    resolved: Mapping[str, str],
    protected: Sequence[str],
) -> str | None:
    """The protected path `targets` would destroy, or `None` if they would not.

    `resolved` maps a target to what it really is, so a symbolic link an agent
    made itself cannot stand in for the path it points at.

    A target carrying a glob is matched as a PATTERN rather than compared, and
    it is never looked up in `resolved`: a pattern is not a path, so there is
    nothing on disk to resolve, and the only question worth asking is whether a
    protected path is among what the shell would expand it to.
    """
    refusable = _refusable_targets(protected=protected)
    for target in targets:
        if _GLOB_CHARACTERS & set(target):
            matched = _matched_pattern(pattern=target, refusable=refusable)
            if matched is not None:
                return matched
            continue
        for candidate in (target, resolved.get(target, target)):
            victim = _victim(candidate=candidate, refusable=refusable)
            if victim is not None:
                return victim
    return None


def refusal_message(*, protected_path: str, command: str) -> str:
    """Render the operator-facing refusal naming the protected path it matched."""
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
        "This refusal is deterministic, not a transient failure. Do NOT retry the same "
        "command. To simulate a sandbox layout, build the whole simulation under a "
        "scratch directory such as /tmp and leave this run's own paths alone."
    )


def _walked(
    *, segment: list[str], directory: str, assigned: Mapping[str, str]
) -> tuple[str, list[str]]:
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
    return directory, [_resolve(word=word, directory=directory) for word in words]


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
    return any(_forces(argument=argument) for argument in arguments)


def _forces(*, argument: str) -> bool:
    """True iff one argument asks a force-only verb to replace what is there.

    A short-flag CLUSTER counts, because `-sfn` is how a link is re-pointed and
    the `f` in it is the whole reason that works.
    """
    if argument.startswith("--"):
        return argument == _FORCE_LONG_FLAG
    return argument.startswith("-") and "f" in argument


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
