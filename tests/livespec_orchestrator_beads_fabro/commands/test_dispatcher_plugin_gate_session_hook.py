"""The plugin-cache gate re-entered INSIDE an agent session, before every check.

WHAT THIS COVERS THAT THE NODE RE-ENTRY CANNOT (bd-ib-3f79, the R497 rework).
`18d15348` re-entered the materialized gate in front of every DECLARED check
suite, which is the `janitor` and `pr_refresh` path. Console run
01M5FGRSA3GE4DYGHPQ0Q50Y7J then failed at the IMPLEMENT stage on the identical
condition, under orchestrator build `c6f61c5856ac` -- a release that CONTAINS
that fix (`git tag --contains 18d1534...` returns v0.229.9). The implement
agent's own in-run `just check` is not a declared check suite, so no node
boundary stands between the poisoned registry and that run of the repository's
checks: `validate_plugin_root` hard-errored "orchestrator plugin root ... is
missing a scripts/bin directory" and check-nextest, check-coverage,
check-e2e-tmux and check-real-store-smoke all went red.

NO SCRIPTED NODE CAN COVER IT, and that is why the carrier here is a HOOK rather
than a fourth re-entry in the graph. The registry is poisoned by the implement
session's OWN start, so every surface upstream of that session is upstream of
the write it has to observe. Measured in this repository's own sandbox on
2026-10-21, in the order the clock recorded it:

- 19:53:07.162 the prepare-step gate program lands; 19:53:07.188 it records the
  pin as `{"builds": {}, "marketplaces": {}}` -- there is no registry and no
  marketplace to read yet.
- 19:53:14.128 .. 19:53:19.393 the four marketplace clones appear, 7 to 12
  seconds AFTER the last prepare step ran.
- 19:56:07.629 `installed_plugins.json` is written, naming four `installPath`
  values under `/root/.claude/plugins/cache`, nearly three minutes later.
- `/root/.claude/plugins/cache` does not exist at all.

So the poisoning write lands between the last prepare step and the agent's first
action, and the only lever in that window is the harness's own hook surface.

WHY `PreToolUse` AND NOT `SessionStart`. Two independent reasons, both measured
rather than assumed. The ordering of a session-start hook against the engine's
own registry SYNC is not established, and a repair that runs before the write it
repairs is no repair at all; `PreToolUse` is unambiguous, because a tool call is
strictly later than session start on any ordering. And it is re-entrant per call,
so a sync that re-runs mid-session cannot reopen the window -- the repair is the
last thing that happens before the check command does.

THE HOOK SURFACE IS LOADED, read off the engine the sandbox actually runs rather
than from documentation. `@agentclientprotocol/claude-agent-acp`'s
`dist/acp-agent.js` starts the SDK with `settingSources: ["user", "project",
"local"]`, and the bundled engine's own settings schema says of its
managed-hooks switch: "When true (and set in managed settings), only hooks from
managed settings run. User, project, and local hooks are ignored." So
user/project/local hooks run by default, and `settings.local.json` -- the source
`_dispatcher_harness_shell_policy` already writes and already measured as
outranking the committed project file -- is a hook source inside the sandbox.

IT NEVER BLOCKS A TOOL CALL, deliberately, and the last case below is what holds
that. The engine treats a `PreToolUse` hook's exit code 2 as a BLOCKING error and
every other non-zero status as non-blocking ("Failed with non-blocking status
code"). `python3 <missing file>` exits 2, so a sandbox whose prepare pass never
landed the gate program would, through the bare command, block EVERY Bash call
the turn makes -- a provisioning fault converted into a turn that can do nothing
at all. The hook therefore collapses any failure to exit 1, which the engine
shows to the operator and lets the call proceed. Nothing weakens by that: the
mechanical REFUSALS stay exactly where `18d15348` put them, at the janitor and at
`pr_refresh`, where a node can fail closed without stranding the turn.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_harness_shell_policy import (
    harness_settings_merge_program,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_cache_gate import (
    plugin_cache_gate_script,
)

# The hook event and matcher, spelled as LITERALS rather than imported from the
# rendering under test. The engine reads these two words and nothing else
# decides whether the hook fires, so a rendering that named something the engine
# ignores has to FAIL here -- which an import would make impossible, since it
# would compare the rendering against itself.
_EVENT = "PreToolUse"
_MATCHER = "Bash"

# The gate program's own filename, as the prepare pass lands it. Asserted for
# the same reason the sibling re-entry module asserts it: a hook command that
# named nothing would still be a well-formed hook.
_GATE_PROGRAM = "livespec-run-plugin-gate.py"

# The exit code the engine treats as a BLOCKING error for a `PreToolUse` hook.
# Named because the whole point of the last case is that this status is the one
# the hook can never return.
_BLOCKING_EXIT_CODE = 2


def _run_merge_program(
    *,
    target: Path,
    scratch: Path,
    module_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    """Run the SHIPPED merge program against `target` and return what it wrote.

    Materialized and imported exactly as the prepare step runs it, rather than
    re-implemented: a transcription of the merge would be a second account of
    it, and only the one the sandbox runs decides anything.
    """
    fragment = scratch / "fragment.py"
    _ = fragment.write_text(harness_settings_merge_program(), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [str(fragment), str(target)])
    spec = importlib.util.spec_from_file_location(module_name, fragment)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    document: dict[str, object] = json.loads(target.read_text(encoding="utf-8"))
    return document


def _matcher_groups(*, document: dict[str, object], event: str) -> list[dict[str, object]]:
    """The hook matcher groups one settings document declares for one event.

    Asserted into shape rather than filtered into it: every group here is one
    this projection wrote or one a case put there, so a group of another shape
    is a defect to report and not an entry to skip past.
    """
    hooks = document.get("hooks")
    assert isinstance(hooks, dict), document
    groups = hooks.get(event)
    assert isinstance(groups, list), hooks
    return groups


def _bash_commands(*, document: dict[str, object]) -> list[str]:
    """Every command of every `PreToolUse` Bash group, in declaration order."""
    found: list[str] = []
    for group in _matcher_groups(document=document, event=_EVENT):
        if group.get("matcher") != _MATCHER:
            continue
        entries = group["hooks"]
        assert isinstance(entries, list), group
        found.extend(str(one["command"]) for one in entries)
    return found


def test_the_merge_program_installs_the_gate_re_entry_as_a_pretooluse_bash_hook(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The settings source the sandbox agent loads declares the in-session re-entry.

    This is the item's own headline condition. Before the repair the merge
    program wrote only `env`, so the sandbox carried no hook at all and the
    implement turn's in-run `just check` ran against whatever registry the
    session start had left -- which on the measured runs named four cache
    directories that did not exist.
    """
    document = _run_merge_program(
        target=tmp_path / "settings.local.json",
        scratch=tmp_path,
        module_name="livespec_plugin_gate_hook_fragment_absent",
        monkeypatch=monkeypatch,
    )

    groups = _matcher_groups(document=document, event=_EVENT)
    assert [group.get("matcher") for group in groups] == [_MATCHER]
    commands = _bash_commands(document=document)
    assert len(commands) == 1
    assert _GATE_PROGRAM in commands[0]


def test_the_merge_program_keeps_a_foreign_hook_and_installs_exactly_one_of_its_own(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Additive AND idempotent, which are two different failures of one write.

    The harness rewrites this very file while the run is driving, and a governed
    repository may declare `PreToolUse` hooks of its own, so a write that
    replaced the event's group list would discard them. A write that merely
    APPENDED would instead stack a duplicate of this projection's own entry
    every time the prepare pass runs, and the gate would then be re-entered
    twice before every Bash call for no gain. One case holds both, because the
    obvious implementation of either defeats the other.
    """
    target = tmp_path / "settings.local.json"
    foreign = {
        "matcher": "Write",
        "hooks": [{"type": "command", "command": "echo foreign"}],
    }
    _ = target.write_text(
        json.dumps({"hooks": {_EVENT: [foreign]}, "env": {"KEEP_ME": "yes"}}),
        encoding="utf-8",
    )

    first = _run_merge_program(
        target=target,
        scratch=tmp_path,
        module_name="livespec_plugin_gate_hook_fragment_first",
        monkeypatch=monkeypatch,
    )
    second = _run_merge_program(
        target=target,
        scratch=tmp_path,
        module_name="livespec_plugin_gate_hook_fragment_second",
        monkeypatch=monkeypatch,
    )

    assert len(_bash_commands(document=first)) == 1
    assert len(_bash_commands(document=second)) == 1
    assert foreign in _matcher_groups(document=second, event=_EVENT)
    env = second.get("env")
    assert isinstance(env, dict)
    assert env.get("KEEP_ME") == "yes"


def _hook_command(*, document: dict[str, object]) -> str:
    commands = _bash_commands(document=document)
    assert len(commands) == 1, commands
    return commands[0]


def _rendered_hook_command(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module_name: str
) -> str:
    """The shipped hook command, read back out of the settings file it writes.

    Taken from the WRITTEN document rather than from the rendering helper, so
    what is executed below is the string the engine would hand to its shell.
    """
    document = _run_merge_program(
        target=tmp_path / "settings.local.json",
        scratch=tmp_path,
        module_name=module_name,
        monkeypatch=monkeypatch,
    )
    return _hook_command(document=document)


def _child_env(*, plugins_root: Path, home: Path) -> dict[str, str]:
    """The hook's environment, EXPLICIT rather than inherited.

    An inherited `LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT` would point the hook at
    the ENCLOSING factory run's own plugins root, so a case that poisons a
    fixture registry would poison the live run's instead.
    """
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(home),
        "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(plugins_root),
    }


def _write_unmaterialized_registry(*, plugins_root: Path) -> None:
    """The measured 2026-10-21 shape: a record naming a cache that never arrived.

    The `installPath` is below the root's own `cache/`, which is the production
    relationship -- a path anywhere else would take the gate's REFUSED-to-remove
    arm and prove the wrong thing.
    """
    build = "c6f61c5856ac"
    plugin = "livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"
    install_path = (
        plugins_root
        / "cache"
        / "livespec-orchestrator-beads-fabro"
        / "livespec-orchestrator-beads-fabro"
        / build
    )
    _ = (plugins_root / "installed_plugins.json").write_text(
        json.dumps(
            {
                "version": 2,
                "plugins": {
                    plugin: [
                        {
                            "scope": "project",
                            "installPath": str(install_path),
                            "version": build,
                        }
                    ]
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _recorded_builds(*, plugins_root: Path) -> list[str]:
    payload = json.loads((plugins_root / "installed_plugins.json").read_text(encoding="utf-8"))
    records = payload["plugins"][
        "livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"
    ]
    return [str(record.get("version")) for record in records]


def test_the_hook_command_repairs_an_unmaterialized_record_and_lets_the_call_proceed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EXECUTED, against the shape run 01M5FGRSA3GE4DYGHPQ0Q50Y7J met at implement.

    The gate program is landed by its OWN prepare-step body, so the pin this
    records is the real one and the hook's run is the ENFORCEMENT arm rather
    than a first recording. Exit 0 is as load-bearing as the repair: a non-zero
    status would surface on every Bash call of a perfectly healthy turn.
    """
    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    env = _child_env(plugins_root=plugins_root, home=home)
    installer = tmp_path / "install-plugin-gate.sh"
    _ = installer.write_text(plugin_cache_gate_script(), encoding="utf-8")
    _ = subprocess.run(["bash", str(installer)], check=True, capture_output=True, env=env)
    _write_unmaterialized_registry(plugins_root=plugins_root)
    assert _recorded_builds(plugins_root=plugins_root) == ["c6f61c5856ac"]
    command = _rendered_hook_command(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        module_name="livespec_plugin_gate_hook_fragment_repair",
    )

    completed = subprocess.run(
        ["bash", "-c", command], check=False, capture_output=True, text=True, env=env
    )

    assert completed.returncode == 0, completed.stderr
    assert "LIVESPEC_PLUGIN_CACHE_UNMATERIALIZED" in completed.stderr
    assert _recorded_builds(plugins_root=plugins_root) == []


def test_the_hook_never_returns_the_engines_blocking_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A sandbox carrying no gate program degrades to NON-blocking, not to a wedge.

    `python3 <missing file>` exits 2, and 2 is the one status the engine reads as
    a blocking error for a `PreToolUse` hook. Through the bare command that
    turns a provisioning fault into a turn whose every Bash call is refused, so
    the hook collapses the failure to 1 and names the condition on stderr.
    """
    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    assert not (plugins_root / _GATE_PROGRAM).exists()
    command = _rendered_hook_command(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        module_name="livespec_plugin_gate_hook_fragment_absent_program",
    )

    completed = subprocess.run(
        ["bash", "-c", command],
        check=False,
        capture_output=True,
        text=True,
        env=_child_env(plugins_root=plugins_root, home=home),
    )

    assert completed.returncode != 0
    assert completed.returncode != _BLOCKING_EXIT_CODE
    assert "LIVESPEC_PLUGIN_GATE_HOOK_UNREPAIRED" in completed.stderr
