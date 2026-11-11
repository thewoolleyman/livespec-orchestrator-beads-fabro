"""The generated-record-file resolution program, as a sandbox actually receives it.

Its own module test loads the program from `record_file_program_source()`, which
is the right subject for the program's DECISIONS and says nothing about whether a
dispatch ever lands those bytes. The two are a different claim, and the gap
between them fails in the quiet direction: a program assembled perfectly and
never materialized leaves a refresh resolving nothing, and the refusal then reads
as a Dispatcher that never wrote one — which points at the wrong half of the
seam.

So this module asserts the program is one of the helper programs the one
helper-fetch setup step writes with its siblings, and then LANDS the registry's
bytes in a scratch root and loads what landed.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_helper_registry import (
    PLUGINS_ROOT,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_regeneration import (
    RECORD_FILE_PROGRAM_FILENAME,
    record_file_program_source,
)

from tests.prepare_step_support import land_helpers, plugins_helper


def test_the_resolution_program_is_a_fetched_helper() -> None:
    """The one helper registry names it, so it is fetched with every sibling."""
    helper = plugins_helper(path=RECORD_FILE_PROGRAM_FILENAME)
    assert helper.compose() == record_file_program_source().encode("utf-8")


def test_the_landed_bytes_are_a_program_a_sandbox_can_import(tmp_path: Path) -> None:
    """What lands below the plugins root loads and refuses an empty invocation."""
    root = tmp_path / "plugins"
    _ = land_helpers(roots={PLUGINS_ROOT: root})
    landed = root / RECORD_FILE_PROGRAM_FILENAME
    assert landed.read_text(encoding="utf-8") == record_file_program_source()
    spec = importlib.util.spec_from_file_location("livespec_landed_resolution", landed)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main([]) != 0
