"""The generated-record-file resolution program, as a sandbox actually receives it.

Its own module test loads the program from `record_file_program_source()`, which
is the right subject for the program's DECISIONS and says nothing about whether a
dispatch ever lands those bytes. The two are a different claim, and the gap
between them fails in the quiet direction: a program assembled perfectly and
never materialized leaves a refresh resolving nothing, and the refusal then reads
as a Dispatcher that never wrote one — which points at the wrong half of the
seam.

So this module asserts the step rides the ONE prepare block the five sibling
helpers ride, and then RUNS that step's shell against a scratch root and loads
what landed. A heredoc whose delimiter the shell expands inside, or a root the
step resolves differently from the node, is invisible to every assertion that
reads the assembled string alone.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_cache_gate import (
    plugin_cache_gate_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_regeneration import (
    RECORD_FILE_PROGRAM_FILENAME,
    record_file_program_prepare_steps_block,
    record_file_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR,
)

from tests.prepare_step_support import env_of, steps_in


def test_the_resolution_program_rides_the_one_prepare_block() -> None:
    """One block lands every materialized helper, so none can arrive alone."""
    assert record_file_program_prepare_steps_block() in plugin_cache_gate_prepare_steps_block()


def test_the_prepare_step_lands_bytes_a_sandbox_can_import(tmp_path: Path) -> None:
    """The step's own shell is run, because only that can observe an expansion.

    The program's source carries `${...}`, a literal dollar and shell-looking
    text of its own. An assertion over the assembled string cannot tell a write
    that expands nothing from one that substitutes into the program, and the
    substituted bytes still look like a program.
    """
    root = tmp_path / "plugins"
    block = record_file_program_prepare_steps_block()
    [step] = steps_in(block=block)
    completed = subprocess.run(
        ["sh", "-c", step.script],
        env=env_of(
            step=step,
            base={
                "PATH": "/usr/bin:/bin",
                "HOME": str(tmp_path / "home"),
                SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR: str(root),
            },
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    landed = root / RECORD_FILE_PROGRAM_FILENAME
    assert landed.read_text(encoding="utf-8") == record_file_program_source()
    spec = importlib.util.spec_from_file_location("livespec_landed_resolution", landed)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main([]) != 0
