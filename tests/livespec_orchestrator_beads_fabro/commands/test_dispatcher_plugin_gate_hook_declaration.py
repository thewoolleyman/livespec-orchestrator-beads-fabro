"""The in-session plugin-gate hook's own declaration, apart from its install.

Companion to `test_dispatcher_plugin_gate_session_hook.py`, which drives the
merge program that INSTALLS this declaration into the sandbox's settings source.
What that module cannot observe is the declaration's own shell correctness: it
reads the command back out of the written document and executes it, so a command
whose quoting is subtly wrong still reaches the gate and still prints the marker
it asserts on. These cases grade the command as SHELL.

THE ONE THAT MATTERS IS THE MESSAGE ROUND TRIP, and it is not fussiness. The
named condition is a sentence carrying two apostrophes -- "the sandbox's
provisioning as the repository's own failure" -- and a hand-quoted single-quoted
literal BALANCES on exactly two of them, so the mangled form prints the marker,
the test asserting the marker passes, and the sentence an operator reads has lost
two words. Add or remove one apostrophe and the command stops parsing at all:
bash then exits 2, which is the one status the hook's collapse-to-1 exists to
make unreachable, so a quoting slip would reinstate the wedge that collapse
prevents. The round trip is what holds both ends.
"""

from __future__ import annotations

import subprocess

from livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_cache_gate import (
    PLUGIN_GATE_HOOK_EVENT,
    PLUGIN_GATE_HOOK_MATCHER,
    PLUGIN_GATE_HOOK_TIMEOUT_SECONDS,
    PLUGIN_GATE_HOOK_UNREPAIRED_MARKER,
    plugin_gate_session_hook_declaration,
)

# The engine's `PreToolUse` hook grammar, spelled as the literals the engine
# reads. Bound to the exported names by the last case, for the reason the
# sibling `test_plan_epoch_*` family gives: a rename that left every other case
# passing would leave a declaration no engine fires.
_EVENT = "PreToolUse"
_MATCHER = "Bash"
_COMMAND_TYPE = "command"


def _hook() -> dict[str, object]:
    groups = plugin_gate_session_hook_declaration()[_EVENT]
    assert len(groups) == 1, groups
    entries = groups[0]["hooks"]
    assert isinstance(entries, list) and len(entries) == 1, groups
    entry: dict[str, object] = entries[0]
    return entry


def test_the_declaration_is_one_command_hook_on_the_engines_own_bash_matcher() -> None:
    """Event, matcher and type are the three words the engine decides on."""
    declaration = plugin_gate_session_hook_declaration()

    assert list(declaration) == [_EVENT]
    assert declaration[_EVENT][0]["matcher"] == _MATCHER
    assert _hook()["type"] == _COMMAND_TYPE
    assert _hook()["timeout"] == PLUGIN_GATE_HOOK_TIMEOUT_SECONDS


def test_the_hook_command_prints_the_named_condition_verbatim() -> None:
    """The refusal sentence survives shell quoting, apostrophes included.

    Executed with the gate program deliberately unresolvable, which is the one
    arm that reaches the message at all: the hook's whole non-blocking posture
    rests on this branch, so a mangled sentence here is the diagnostic an
    operator gets for a sandbox that never provisioned.
    """
    command = str(_hook()["command"])

    completed = subprocess.run(
        ["bash", "-c", command],
        check=False,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": "/nonexistent-plugins-root",
        },
    )

    assert completed.returncode == 1, completed.stderr
    assert PLUGIN_GATE_HOOK_UNREPAIRED_MARKER in completed.stderr
    assert "the sandbox's provisioning as the repository's own failure" in completed.stderr


def test_the_hook_command_is_parseable_shell() -> None:
    """A syntax check, which is the failure a round trip cannot distinguish.

    `bash -n` parses without executing, so this case fails for a quoting slip
    even on a host where the gate program happens to resolve -- the round trip
    above would then take the success arm and never reach the message.
    """
    parsed = subprocess.run(
        ["bash", "-n", "-c", str(_hook()["command"])],
        check=False,
        capture_output=True,
        text=True,
    )

    assert parsed.returncode == 0, parsed.stderr


def test_the_literals_here_are_the_ones_the_gate_module_exports() -> None:
    """Bind the spelled grammar to the names production renders from."""
    assert PLUGIN_GATE_HOOK_EVENT == _EVENT
    assert PLUGIN_GATE_HOOK_MATCHER == _MATCHER
    assert PLUGIN_GATE_HOOK_UNREPAIRED_MARKER == "LIVESPEC_PLUGIN_GATE_HOOK_UNREPAIRED"
