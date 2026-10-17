"""Shell-command shape: which words a shell would EXECUTE, and which are DATA.

Two repo-local Bash guards have to answer this before they can decide anything.
`livespec_tdd_order_targets` asks which paths a command WRITES;
`livespec_sandbox_path_policy` asks which paths a command REMOVES. Neither
question can be answered without first separating the words a shell would run
from the bytes it would merely carry: a here-document body is file data, a `&&`
or a `;` starts a new command, and a wrapper such as `sudo` or `mise exec --`
leaves the real command one or more words later.

THAT SEPARATION IS ONE CONCERN WITH TWO CONSUMERS, which is why it lives here.
It was extracted from `livespec_tdd_order_targets`, where it was private, when
the sandbox path guard needed the same reading. A second copy would have
drifted from the first the moment either was fixed, and the two guards would
then disagree about which half of a command is data — the exact distinction
both of them exist to make.

PURE: no filesystem, no environment, no process output.

The tokenizer is the ONE sanctioned fail-open, and it is deliberate rather than
defensive: a command the shell lexer cannot split at all yields `None` instead
of raising, because a lexer error must never refuse legitimate work. Every
caller reads `None` as "nothing can be said about this command".
"""

from __future__ import annotations

import re
import shlex

__all__: list[str] = [
    "leading_assignments",
    "leading_command_index",
    "operands",
    "shell_tokens",
    "token_segments",
    "without_heredoc_bodies",
]

_HEREDOC_OPERATORS = ("<<", "<<-")
_SEGMENT_OPERATORS = (";", "&", "&&", "|", "||", "(", ")")
_ARGUMENT_TERMINATOR = "--"
# Capturing, because `leading_assignments` needs the name and the value while
# `leading_command_index` needs only to know the token IS one. One pattern
# rather than two, so the two readings can never disagree about what counts as
# an assignment.
_ENV_ASSIGNMENT_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)")
# Wrappers that still leave a LATER word in command position, plus the
# subcommand words those wrappers take before it. The EXECUTED leading command
# is what classifies a segment, never a word that merely appears somewhere in
# it.
_COMMAND_WRAPPERS = ("command", "env", "mise", "nice", "sudo", "time", "uv", "xargs")
_WRAPPER_SUBCOMMANDS = ("exec", "run", "x")


def shell_tokens(*, command: str) -> list[str] | None:
    """Split `command` into shell-like words and control operators, or `None`.

    `None` means the lexer could not split the string at all — an unbalanced
    quote, most often a token that legitimately spans lines.
    """
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError:
        return None


def without_heredoc_bodies(*, command: str) -> str:
    """Return `command` with here-document body lines removed.

    A body is file data rather than a command, so a body line reading
    `rm -rf /workspace` removes nothing and must not be read as a removal. The
    INTRODUCING line is kept, because the redirection that names the target
    sits on it.
    """
    kept: list[str] = []
    pending: list[str] = []
    for line in command.splitlines():
        if pending:
            if line.strip() == pending[0]:
                pending.pop(0)
            continue
        kept.append(line)
        pending.extend(_heredoc_delimiters(line=line))
    return "\n".join(kept)


def _heredoc_delimiters(*, line: str) -> list[str]:
    """Return the here-document delimiters introduced on one command line.

    The lexer splits `<<-EOF` into `<<` and `-EOF`, so the leading dash of the
    `<<-` form is stripped off the delimiter; the terminator line is matched on
    `strip()`, which is what makes that form's indented terminator work.
    """
    tokens = shell_tokens(command=line)
    if tokens is None:
        return []
    delimiters: list[str] = []
    iterator = iter(tokens)
    for token in iterator:
        if token in _HEREDOC_OPERATORS:
            delimiters.append(next(iterator, "").lstrip("-"))
    return delimiters


def token_segments(*, tokens: list[str]) -> list[list[str]]:
    """Split a token list on shell control operators into command segments.

    `(` and `)` are among the operators, so a subshell's body is read as
    segments of its own rather than as one opaque word.
    """
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in _SEGMENT_OPERATORS:
            segments.append([])
            continue
        segments[-1].append(token)
    return [segment for segment in segments if segment]


def leading_command_index(*, tokens: list[str]) -> int:
    """Return the index of the word that actually EXECUTES in a segment.

    An index at or past the end means the segment executes nothing — it is all
    flags, assignments and wrappers.
    """
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if (
            token == _ARGUMENT_TERMINATOR
            or token.startswith("-")
            or _ENV_ASSIGNMENT_RE.fullmatch(token)
        ):
            index += 1
            continue
        if token.rsplit("/", 1)[-1] in _COMMAND_WRAPPERS:
            index += 1
            while index < len(tokens) and tokens[index] in _WRAPPER_SUBCOMMANDS:
                index += 1
            continue
        return index
    return index


def leading_assignments(*, tokens: list[str]) -> dict[str, str]:
    """The `NAME=value` pairs a segment sets before the word that executes.

    Recorded rather than merely skipped, because a value can BE the thing a
    guard is looking for: in `d=/workspace; rm -rf "$d"` the protected path is
    named once, in a word that is not an operand of the removal.

    Only the LEADING run is read. An assignment cannot follow a command word —
    after that the shell is parsing arguments — so the scan stops at the first
    token that is not one.
    """
    assignments: dict[str, str] = {}
    for token in tokens:
        assignment = _ENV_ASSIGNMENT_RE.fullmatch(token)
        if assignment is None:
            break
        assignments[assignment.group(1)] = assignment.group(2)
    return assignments


def operands(*, tokens: list[str]) -> list[str]:
    """Return the non-flag words of an argument list."""
    return [token for token in tokens if not token.startswith("-")]
