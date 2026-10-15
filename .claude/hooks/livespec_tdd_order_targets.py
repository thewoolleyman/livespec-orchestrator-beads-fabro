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

The GENERIC half of that shell grammar — tokenizing, dropping here-document
bodies, splitting on control operators, finding the word that actually
executes, and listing the non-flag operands — now lives in
`livespec_shell_shape`, because `livespec_sandbox_path_policy` asks the same
first question of a command before it can decide which paths a REMOVAL would
act on. What stays here is the part that is about WRITES specifically: the
redirection operators, `tee`, in-place `sed`, and the last-operand rule for
`cp`/`mv`/`install`.
"""

from __future__ import annotations

from livespec_shell_shape import (
    leading_command_index,
    operands,
    shell_tokens,
    token_segments,
    without_heredoc_bodies,
)

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
    cleaned = without_heredoc_bodies(command=command)
    if shell_tokens(command=cleaned) is None:
        return []
    targets: list[str] = []
    for line in cleaned.splitlines():
        targets.extend(_line_targets(line=line))
    return targets


def _line_targets(*, line: str) -> list[str]:
    """Return the write targets of one command line, across its segments."""
    tokens = shell_tokens(command=line)
    if tokens is None:
        return []
    targets: list[str] = []
    for segment in token_segments(tokens=tokens):
        targets.extend(_segment_targets(tokens=segment))
    return targets


def _segment_targets(*, tokens: list[str]) -> list[str]:
    """Return the write targets of one command segment."""
    targets = _redirect_targets(tokens=tokens)
    index = leading_command_index(tokens=tokens)
    if index >= len(tokens):
        return targets
    command = tokens[index].rsplit("/", 1)[-1]
    arguments = tokens[index + 1 :]
    if command == _TEE_COMMAND:
        targets.extend(operands(tokens=arguments))
    elif command == _SED_COMMAND and _requests_in_place(tokens=arguments):
        targets.extend(_sed_targets(tokens=arguments))
    elif command in _LAST_OPERAND_COMMANDS:
        written = operands(tokens=arguments)
        if written:
            targets.append(written[-1])
    return targets


def _redirect_targets(*, tokens: list[str]) -> list[str]:
    """Return the operand of every `>`/`>>` redirection in a segment."""
    return [
        tokens[index + 1]
        for index, token in enumerate(tokens)
        if token in _REDIRECT_OPERATORS and index + 1 < len(tokens)
    ]


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
