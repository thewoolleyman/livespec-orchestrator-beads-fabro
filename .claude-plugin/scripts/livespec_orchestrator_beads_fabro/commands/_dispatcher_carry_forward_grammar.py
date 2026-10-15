"""The DIRECT-READ GRAMMAR a verified proof must sit inside to be carried forward.

`SPECIFICATION/contracts.md` section "Definition-of-Done and Proof-of-Done
stages" -> "The observation scope" (v138) closes the set of commands a
`pr_refresh` carry-forward decision may reason about. Everything else is
`reproof_required`. The closure is the whole safety argument: the decision
concludes that a refresh "cannot affect what the proof observed", and that
conclusion is only available when the proof's reads are ENUMERABLE from its own
text. A command that pipes, substitutes, globs or recurses reads an unbounded
set of paths, so nothing can be said about whether the incoming commits touched
one of them.

WHY THIS MODULE SHIPS A PROGRAM FRAGMENT RATHER THAN HOST-SIDE FUNCTIONS. The
decision is taken INSIDE the sandbox, by the `pr_refresh_head` stage, against
the clone's own working tree and object store. There is no host-side caller and
there never will be one, so a host-side implementation would be a SECOND account
of one grammar with no consumer -- the shape `_dispatcher_publication_head`
records the cost of, one level up. The fragment is therefore the single
implementation, it is stdlib-only for the reason that module gives (the sandbox
clone is the GOVERNED repository and carries no copy of this package), and its
paired test loads the shipped bytes and exercises them directly rather than
re-deriving the grammar in Python nobody runs.

WHY THE CHARACTER TEST COMES BEFORE THE PRODUCTION TEST. The productions are
matched against WORDS, and words come from POSIX splitting, which has already
thrown the shell metacharacters away: `cat $(ls)` splits to two perfectly
ordinary words. Testing the raw text first is what makes "no expansion,
substitution or hidden read can occur anywhere in the command, quoted or not"
an assertion about the command as WRITTEN rather than about the tokens left
over.

WHY A REJECTED PATH OPERAND IS NOT "OUTSIDE THE GRAMMAR". Both answers send the
run to `proof_capture`, so the distinction buys nothing in routing -- it buys
the RECORD. A step whose command is `cat docs/../AGENTS.md` matched a production
perfectly and was refused on its operand; reporting it as an unrecognised
command would point its reader at the command's shape, which is fine, and away
from the `..` segment, which is the whole finding. The two reasons are kept
apart for the same reason the clause enumerates them apart.
"""

from __future__ import annotations

__all__: list[str] = [
    "READ_IDENTITY_LABEL",
    "WORKING_DIRECTORY_LINE",
    "WORKING_DIRECTORY_PREFIX",
    "grammar_program_fragment",
]

# The line the clause requires a verified record to state ahead of its numbered
# steps, meaning every step ran from the repository root. Spelled ONCE here and
# substituted into the fragment, so the two capture prompts, the prompt
# discipline test and the decision all name one line.
WORKING_DIRECTORY_LINE = "Working directory: ."

# The PREFIX the decision recognises a working-directory declaration by, which
# is deliberately wider than the line above: a record naming some OTHER working
# directory must put every step outside the grammar, and a reader that only
# matched the exact line could not tell that record from one that declared
# nothing at all. The clause gives the two the same answer; the record is what
# differs, and only the prefix can name the directory the record did state.
WORKING_DIRECTORY_PREFIX = "Working directory:"

# The label of a read identity line, `Read: <canonical path> <identity>`.
READ_IDENTITY_LABEL = "Read"

# The grammar as the sandbox executes it. A RAW outer string, so every backslash
# below is the backslash the inner source needs: the forbidden-character set
# carries one, and doubling it here would make the fragment test for two.
_GRAMMAR_FRAGMENT = r'''
import re
import shlex

WORKING_DIRECTORY_LINE = "__WORKING_DIRECTORY_LINE__"
WORKING_DIRECTORY_PREFIX = "__WORKING_DIRECTORY_PREFIX__"
READ_IDENTITY_LABEL = "__READ_IDENTITY_LABEL__"

# Outside single quotes, any of these puts the command outside the grammar, so
# that no expansion, substitution or hidden read can occur anywhere in it.
FORBIDDEN_OUTSIDE_SINGLE_QUOTES = "|;&<>$`\\!*?[~\n"
# The same rule stated again for DOUBLE-quoted text, which the clause names
# separately. It is implied by the set above -- double-quoted text is outside
# single quotes -- and is kept because the implication is one refactor away from
# being lost, and losing it re-opens `grep -n "$(cat pattern)" file`.
FORBIDDEN_IN_DOUBLE_QUOTES = "$`\\!"

GREP_FLAGS = ("-n", "-c", "-i", "-F", "-E", "-x", "-w", "-v", "-o")
GREP_COUNT_FLAGS = ("-A", "-B", "-C")
WC_FLAGS = ("-l", "-w", "-c")
# Line numbers, line ranges and the `p` command, and nothing else. `$` is not a
# line number, so `sed -n '1,$p'` is outside the grammar even though its `$` is
# single-quoted and therefore passes the character test.
SED_SCRIPT = re.compile(r"^[0-9]+(,[0-9]+)?p(;[0-9]+(,[0-9]+)?p)*$")
GIT_SHOW_PREFIX = "HEAD:"

NO_COMMAND = "it carries no command"
TWO_COMMANDS = "it carries more than one command"
UNSPLITTABLE = "its command does not split into words by POSIX shell quoting rules"
NO_PRODUCTION = "its command matches no direct-read production"


def forbidden_character(command):
    """The first character that puts one command outside the grammar, else None."""
    in_single = False
    in_double = False
    for character in command:
        if character == "'" and not in_double:
            in_single = not in_single
            continue
        if in_single:
            continue
        if character == '"':
            in_double = not in_double
            continue
        if in_double and character in FORBIDDEN_IN_DOUBLE_QUOTES:
            return character
        if character in FORBIDDEN_OUTSIDE_SINGLE_QUOTES:
            return character
    return None


def is_count(word):
    """Whether one word is a `<count>`: decimal digits and nothing else."""
    return word.isascii() and word.isdigit()


def file_operands(words):
    """Every word as a file operand, or None when any begins with `-` or none remain.

    An empty result is None rather than an empty list: a command that reads no
    file operand would read standard input, which the clause puts outside the
    grammar, and an empty list would read downstream as "reads nothing".
    """
    if not words:
        return None
    for word in words:
        if word.startswith("-"):
            return None
    return list(words)


def grep_operands(rest):
    """`grep`'s path operands, or None when its options or pattern are not admitted."""
    index = 0
    while index < len(rest):
        token = rest[index]
        if token in GREP_FLAGS:
            index += 1
            continue
        if token in GREP_COUNT_FLAGS:
            if index + 1 >= len(rest) or not is_count(rest[index + 1]):
                return None
            index += 2
            continue
        break
    if index < len(rest) and rest[index] == "-e":
        if index + 1 >= len(rest):
            return None
        index += 2
    elif index < len(rest) and not rest[index].startswith("-"):
        index += 1
    else:
        return None
    return file_operands(rest[index:])


def production_operands(words):
    """The path operands of a command matching one production exactly, else None."""
    name = words[0]
    rest = words[1:]
    if name == "cat":
        return file_operands(rest)
    if name in ("head", "tail"):
        if rest[:1] == ["-n"]:
            if len(rest) < 2 or not is_count(rest[1]):
                return None
            rest = rest[2:]
        return file_operands(rest)
    if name == "wc":
        if rest and rest[0] in WC_FLAGS:
            rest = rest[1:]
        return file_operands(rest)
    if name == "grep":
        return grep_operands(rest)
    if name == "sed":
        if len(rest) < 2 or rest[0] != "-n" or SED_SCRIPT.match(rest[1]) is None:
            return None
        return file_operands(rest[2:])
    if name == "diff":
        if rest[:1] == ["-u"]:
            rest = rest[1:]
        operands = file_operands(rest)
        return operands if operands is not None and len(operands) == 2 else None
    if name == "git":
        if len(rest) != 2 or rest[0] != "show" or not rest[1].startswith(GIT_SHOW_PREFIX):
            return None
        path = rest[1][len(GIT_SHOW_PREFIX):]
        return [path] if path else None
    return None


def classify_command(command):
    """One step's command, graded against the grammar.

    Returns a mapping carrying `inside`, the `reason` an outside command is
    outside, its `operands`, and whether it reads the WORKING TREE -- which is
    every production but `git show`, the one that reads the object store and so
    owes no read identity.
    """
    text = command.strip()
    if not text:
        return {"inside": False, "reason": NO_COMMAND, "operands": [], "working_tree": False}
    character = forbidden_character(text)
    if character is not None:
        reason = "its command contains " + repr(character) + " outside single quotes"
        return {"inside": False, "reason": reason, "operands": [], "working_tree": False}
    try:
        words = shlex.split(text)
    except ValueError:
        return {"inside": False, "reason": UNSPLITTABLE, "operands": [], "working_tree": False}
    if not words:
        return {"inside": False, "reason": NO_COMMAND, "operands": [], "working_tree": False}
    operands = production_operands(words)
    if operands is None:
        return {"inside": False, "reason": NO_PRODUCTION, "operands": [], "working_tree": False}
    return {
        "inside": True,
        "reason": None,
        "operands": operands,
        "working_tree": words[0] != "git",
    }


def canonical_path(operand):
    """One path operand interpreted relative to the repository root, or None.

    None is the REJECTION the clause names: an absolute, empty or
    parent-bearing operand. `.` segments and repeated separators collapse, so
    `./plan//topic/note.md` and `plan/topic/note.md` are one path and an
    incoming change to that file is seen as inside the observation scope.
    """
    if not operand or operand.startswith("/"):
        return None
    parts = []
    for part in operand.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            return None
        parts.append(part)
    return "/".join(parts) if parts else None
'''


def grammar_program_fragment() -> str:
    """The grammar's exact bytes, with the two record-line spellings substituted.

    A function rather than a constant for the reason `proof_head_program_source`
    gives: a reader must be able to SEE that the lines the fragment parses came
    from the constants the prompts are held to, not from literals typed twice.
    """
    return (
        _GRAMMAR_FRAGMENT.replace("__WORKING_DIRECTORY_LINE__", WORKING_DIRECTORY_LINE)
        .replace("__WORKING_DIRECTORY_PREFIX__", WORKING_DIRECTORY_PREFIX)
        .replace("__READ_IDENTITY_LABEL__", READ_IDENTITY_LABEL)
    )
