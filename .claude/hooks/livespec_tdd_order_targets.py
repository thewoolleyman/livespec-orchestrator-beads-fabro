"""Write-target extraction for the livespec TDD order guard.

ONE concern, two surfaces. `livespec_tdd_order_guard` has to answer "which
paths is this tool about to write?" before `livespec_tdd_order_policy` can
decide whether writing them is permitted, and the answer arrives two very
different ways: a structured `Write`/`Edit`/`MultiEdit` names its target
outright, while a `Bash` command has to have its targets PARSED out. Both land
in one list of repo paths, which is what lets the guard apply one decision
table to both — the Bash leg is a parity surface, not a second policy.

This module is deliberately separate from the policy: extraction is a shell-
grammar concern with its own vocabulary of operators and command forms, and
the policy is a four-state decision table. Everything here is PURE — no git,
no environment, no process output.
"""

from __future__ import annotations

import re
import shlex

__all__: list[str] = [
    "STRUCTURED_WRITE_TOOLS",
    "shell_write_targets",
    "write_targets",
]

STRUCTURED_WRITE_TOOLS = ("Write", "Edit", "MultiEdit")

_BASH_TOOL = "Bash"
_FILE_PATH_KEY = "file_path"
_COMMAND_KEY = "command"

_REDIRECT_OPERATORS = (">", ">>")
_HEREDOC_OPERATORS = ("<<", "<<-")
_SEGMENT_OPERATORS = (";", "&", "&&", "|", "||", "(", ")")
_ARGUMENT_TERMINATOR = "--"
_ENV_ASSIGNMENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*")
# Wrappers that still leave a LATER word in command position, plus the
# subcommand words those wrappers take before it. Same discrimination the
# footgun guard makes: the EXECUTED leading command is what classifies a
# segment, never a word that merely appears somewhere in it.
_COMMAND_WRAPPERS = ("command", "env", "mise", "nice", "sudo", "time", "uv", "xargs")
_WRAPPER_SUBCOMMANDS = ("exec", "run", "x")
_TEE_COMMAND = "tee"
_SED_COMMAND = "sed"
# `cp`, `mv` and `install` all write their LAST operand, which is what lets one
# rule cover the three of them — and makes it robust to a flag that takes an
# argument, such as `install -m 644`.
_LAST_OPERAND_COMMANDS = ("cp", "install", "mv")
_SED_SCRIPT_FLAGS = ("-e", "-f", "--expression", "--file")
_SED_IN_PLACE_LONG_FLAG = "--in-place"


def write_targets(*, tool_name: str, tool_input: dict[str, object]) -> list[str]:
    """Return every path `tool_name` would write, given its hook `tool_input`.

    An unrecognized tool writes nothing: this guard governs file writes, and a
    tool it does not model must not be guessed at.
    """
    if tool_name in STRUCTURED_WRITE_TOOLS:
        path = tool_input.get(_FILE_PATH_KEY)
        return [path] if isinstance(path, str) and path else []
    if tool_name == _BASH_TOOL:
        command = tool_input.get(_COMMAND_KEY)
        return shell_write_targets(command=command) if isinstance(command, str) else []
    return []


def shell_write_targets(*, command: str) -> list[str]:
    """Return the paths `command` writes, by shell write form.

    Five forms are recognized: `>`/`>>` redirection — which also covers a
    here-doc, whose redirection sits on the INTRODUCING line — `tee`, `sed` in
    place, and the last operand of `cp`/`mv`/`install`. Here-doc BODIES are
    removed first, because a body is file data: a body line reading
    `cp decoy.py x.py` is not a command.

    FAIL-OPEN at the tokenizer, deliberately and asymmetrically. A command the
    shell lexer cannot parse at all yields NO targets, which is the behaviour
    the plan behind this guard prescribes for the Bash leg specifically — a
    tokenizer error must not refuse legitimate work. The structured tools,
    whose target needs no parsing, stay fail-CLOSED.

    Segmentation is per LINE and then per shell operator, because a multi-line
    Bash block whose commands sit on their own lines with no `&&` between them
    is ordinary usage and its later lines must still be seen. A line whose
    quoting does not close is skipped; the gate above means that only happens
    when some token legitimately spans lines.
    """
    cleaned = _without_heredoc_bodies(command=command)
    if not _is_tokenizable(command=cleaned):
        return []
    targets: list[str] = []
    for line in cleaned.splitlines():
        targets.extend(_line_targets(line=line))
    return targets


def _is_tokenizable(*, command: str) -> bool:
    """True iff the shell lexer can split `command` into words at all."""
    try:
        _ = _shell_tokens(command=command)
    except ValueError:
        return False
    return True


def _shell_tokens(*, command: str) -> list[str]:
    """Split `command` into shell-like words and control operators."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def _without_heredoc_bodies(*, command: str) -> str:
    """Return `command` with here-document body lines removed."""
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
    try:
        tokens = _shell_tokens(command=line)
    except ValueError:
        return []
    delimiters: list[str] = []
    iterator = iter(tokens)
    for token in iterator:
        if token in _HEREDOC_OPERATORS:
            delimiters.append(next(iterator, "").lstrip("-"))
    return delimiters


def _line_targets(*, line: str) -> list[str]:
    """Return the write targets of one command line, across its segments."""
    try:
        tokens = _shell_tokens(command=line)
    except ValueError:
        return []
    targets: list[str] = []
    for segment in _segments(tokens=tokens):
        targets.extend(_segment_targets(tokens=segment))
    return targets


def _segments(*, tokens: list[str]) -> list[list[str]]:
    """Split a token list on shell control operators into command segments."""
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in _SEGMENT_OPERATORS:
            segments.append([])
            continue
        segments[-1].append(token)
    return [segment for segment in segments if segment]


def _segment_targets(*, tokens: list[str]) -> list[str]:
    """Return the write targets of one command segment."""
    targets = _redirect_targets(tokens=tokens)
    index = _leading_command_index(tokens=tokens)
    if index >= len(tokens):
        return targets
    command = tokens[index].rsplit("/", 1)[-1]
    arguments = tokens[index + 1 :]
    if command == _TEE_COMMAND:
        targets.extend(_operands(tokens=arguments))
    elif command == _SED_COMMAND and _requests_in_place(tokens=arguments):
        targets.extend(_sed_targets(tokens=arguments))
    elif command in _LAST_OPERAND_COMMANDS:
        operands = _operands(tokens=arguments)
        if operands:
            targets.append(operands[-1])
    return targets


def _redirect_targets(*, tokens: list[str]) -> list[str]:
    """Return the operand of every `>`/`>>` redirection in a segment."""
    return [
        tokens[index + 1]
        for index, token in enumerate(tokens)
        if token in _REDIRECT_OPERATORS and index + 1 < len(tokens)
    ]


def _leading_command_index(*, tokens: list[str]) -> int:
    """Return the index of the word that actually EXECUTES in a segment."""
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


def _operands(*, tokens: list[str]) -> list[str]:
    """Return the non-flag words of an argument list."""
    return [token for token in tokens if not token.startswith("-")]


def _requests_in_place(*, tokens: list[str]) -> bool:
    """True iff a `sed` argument list asks for an in-place edit."""
    return any(_token_requests_in_place(token=token) for token in tokens)


def _token_requests_in_place(*, token: str) -> bool:
    if token.startswith("--"):
        return token == _SED_IN_PLACE_LONG_FLAG or token.startswith(f"{_SED_IN_PLACE_LONG_FLAG}=")
    if not token.startswith("-"):
        return False
    # `-i`, `-i.bak` and a cluster such as `-ni` all request in place; what
    # follows a dot is the backup extension, never another short flag.
    return "i" in token.lstrip("-").split(".", 1)[0]


def _sed_targets(*, tokens: list[str]) -> list[str]:
    """Return the FILE operands of an in-place `sed` argument list.

    With no `-e`/`-f` to supply the script, `sed` takes it as the first
    operand, so that operand is dropped; with one, every operand is a file.
    The argument of `-e`/`-f` is consumed either way, so a script that happens
    to look like a path can never be read as a target.
    """
    operands: list[str] = []
    script_supplied = False
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if token in _SED_SCRIPT_FLAGS:
            script_supplied = True
            index += 1
            continue
        if not token.startswith("-"):
            operands.append(token)
    return operands if script_supplied else operands[1:]
